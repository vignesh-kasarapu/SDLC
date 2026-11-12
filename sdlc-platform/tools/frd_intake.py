#!/usr/bin/env python
"""FRD intake mode: the client already supplied an FRD. Keep it; never rewrite it.

frd.vN.md is RENDERED here, never written by an agent:
  Part A  the client's document, verbatim, with its block IDs [C-nnn] (from 01-frd/crd.md)
  Part B  a compact platform addendum: requirement register, gap questions, additions and
          clarifications, recommended-feature decisions, and the binding sections
          19 (technology stack) and 20 (architecture pattern and programming standards)

frd.vN.json is still the structured source of truth that every later agent reads. In intake mode
every requirement that cites a client block (C-nnn) must QUOTE the client's wording: its
`statement` has to appear verbatim in the cited blocks (whitespace, case and table pipes are
ignored; "..." joins quoted fragments). Interpretations go in `clarification`, never in the
statement. Requirements without a C source (accepted recommendations, checklist defaults,
stack constraints, reviewer feedback) are platform additions and are listed in Part B.

Usage:
  frd_intake.py mode                  print "frd" (intake) or "crd" (full FRD writing)
  frd_intake.py build --version N     write 01-frd/frd.vN.md from frd.vN.json
  frd_intake.py check --version N     verify verbatim wording and that the .md is the rendered one
"""
from __future__ import annotations

import argparse
import re
import sys

from common import latest_version, project_dir, read_json, rel

ADDITION_SOURCES = re.compile(r"^(SUG-|CHECKLIST-|USER-STACK|REVIEW-)")


def is_intake(pdir) -> bool:
    return read_json(pdir / "01-frd" / "intake.json", default={}).get("doc_type") == "frd"


def _norm(text: str) -> str:
    text = text.replace("|", " ").replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-")
    text = re.sub(r"^\s*-\s+", " ", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip().lower()


def _cell(v) -> str:
    if v is None or v == "" or v == []:
        return "-"
    if isinstance(v, (list, tuple)):
        v = ", ".join(map(str, v))
    return str(v).replace("|", "/").replace("\n", " ")


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return out + ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]


def verbatim_errors(pdir, frd: dict) -> list[str]:
    blocks = read_json(pdir / "01-frd" / "crd-index.json")["blocks"]
    errs = []
    for r in frd["requirements"]:
        cids = [s for s in r.get("source", []) if s.startswith("C-")]
        if not cids or r.get("priority") == "wont":
            continue
        corpus = _norm(" ".join(blocks.get(c, {}).get("text", "") for c in cids))
        fragments = [f for f in re.split(r"\s*(?:\.\.\.|…)\s*", _norm(r["statement"]).rstrip(".;:")) if f]
        missing = [f for f in fragments if f not in corpus]
        if missing:
            errs.append(f"{r['id']}: statement is not the client's wording from {', '.join(cids)} "
                        f"(intake mode quotes the client; put interpretations in 'clarification'): \"{missing[0][:80]}\"")
    return errs


def _version_history(pdir, v, frd) -> list[str]:
    rows = [[1, "Client FRD ingested (intake mode); requirements extracted with the client's wording"]]
    for n in range(2, v + 1):
        plan = read_json(pdir / "01-frd" / f"change-plan.v{n}.json", default={})
        applied = [c["id"] for c in plan.get("changes", []) if c.get("decision") in ("approved", "edited")]
        declined = [f"{c['id']} (declined by {c.get('decided_by', 'reviewer')})"
                    for c in plan.get("changes", []) if c.get("decision") == "rejected"]
        text = "Applied " + (", ".join(applied) or "none")
        if declined:
            text += "; declined " + ", ".join(declined)
        rows.append([n, text])
    return _table(["Version", "Changes"], rows)


def render(pdir, v: int) -> str:
    fdir = pdir / "01-frd"
    frd = read_json(fdir / f"frd.v{v}.json")
    crd = (fdir / "crd.md").read_text(encoding="utf-8")
    crd = re.sub(r"^<!--.*?-->\s*", "", crd, count=1, flags=re.S)
    reqs = frd["requirements"]
    md = [f"# Functional Requirements Document v{v}: {pdir.name}", "",
          "> **Intake mode.** Part A is the client's FRD, reproduced verbatim with block IDs `[C-nnn]`; "
          "the platform does not rewrite it. Part B is the platform addendum. The structured requirement "
          f"set is `01-frd/frd.v{v}.json`; each client requirement there quotes the client's wording.", "",
          "## 1. Version history", ""]
    md += _version_history(pdir, v, frd)
    md += ["", "## Part A. Client FRD (verbatim)", "", crd.strip(), "", "## Part B. Platform addendum", "",
           "### B1. Requirement register", ""]
    md += _table(["ID", "Client ref", "Type", "Priority", "Status", "Source", "Title"],
                 [[r["id"], r.get("client_ref"), r["type"], r["priority"], r["status"], r["source"], r["title"]]
                  for r in reqs])
    qs = frd.get("open_questions", [])
    md += ["", "### B2. Gap questions for the client", ""]
    md += _table(["ID", "Question", "Blocking", "Related", "Resolution"],
                 [[q["id"], q["question"], "yes" if q.get("blocking") else "no",
                   (q.get("related") or []) + (q.get("source") or []), q.get("resolution")] for q in qs]) \
        if qs else ["None."]
    adds = [r for r in reqs if not any(s.startswith("C-") for s in r["source"])]
    clar = [r for r in reqs if r.get("clarification")]
    md += ["", "### B3. Platform additions and clarifications", ""]
    if not adds and not clar:
        md.append("None.")
    for r in adds:
        md += [f"**{r['id']}: {r['title']}** ({r['priority']}, {r['status']}, source {', '.join(r['source'])})  ",
               r["statement"]]
        md += [f"- {ac}" for ac in r.get("acceptance_criteria", [])]
        if r.get("notes"):
            md.append(f"- Note: {r['notes']}")
        md.append("")
    for r in clar:
        md += [f"**{r['id']}** ({r.get('client_ref') or ', '.join(r['source'])}) clarification: {r['clarification']}", ""]
    recs = read_json(fdir / "feature-recommendations.json", default={}).get("recommended", [])
    md += ["### B4. Recommended features", ""]
    md += _table(["ID", "Feature", "Importance", "Decision", "Decided by"],
                 [[s["id"], s["title"], s.get("importance"), s.get("decision"), s.get("decided_by")] for s in recs]) \
        if recs else ["None reviewed."]
    ts = read_json(fdir / "tech-stack.json", default={})
    md += ["", "## 19. Technology stack", ""]
    rows = []
    for part in ("frontend", "backend"):
        d = ts.get(part, {})
        rows.append([part.capitalize(), f"{d.get('language', '-')} / {d.get('framework', '-')}", d.get("libraries")])
    db = ts.get("database", {})
    rows.append(["Database", db.get("engine"), ", ".join(x for x in (db.get("orm"), db.get("migrations")) if x)])
    for k in ("testing", "deployment", "authentication"):
        val = ts.get(k)
        if isinstance(val, dict):
            val = "; ".join(f"{a}: {b}" for a, b in val.items())
        rows.append([k.capitalize(), val, ""])
    md += _table(["Part", "Choice", "Details"], rows)
    md += [f"", f"Confirmed by {ts.get('confirmed_by', '-')} on {ts.get('confirmed_at', '-')}."]
    if ts.get("constraints"):
        md += ["", "Constraints:"] + [f"- {c}" for c in ts["constraints"]]
    pattern = ts.get("architecture_pattern", "MVC")
    md += ["", "## 20. Architecture pattern and programming standards", "",
           f"- Pattern: **{pattern}**" + (f" ({ts['pattern_rationale']})" if ts.get("pattern_rationale") else "")]
    if pattern == "MVC":
        md.append("- Dependency rule: Controller -> Service -> Repository -> Model; views use frontend controllers "
                  "and services only. Enforced by `tools/layer_check.py`.")
    md += ["- Standards:"] + [f"  - {c}" for c in ts.get("coding_standards", [])]
    md += ["- Full standards: `knowledge/standards/mvc-coding-standards.md`; the stack-specific version is "
           "written in Phase 2 as `02-spec/coding-standards.md`."]
    return "\n".join(md) + "\n"


def check(pdir, v: int) -> list[str]:
    fdir = pdir / "01-frd"
    errs = verbatim_errors(pdir, read_json(fdir / f"frd.v{v}.json"))
    md = fdir / f"frd.v{v}.md"
    if not md.exists() or md.read_text(encoding="utf-8") != render(pdir, v):
        errs.append(f"frd.v{v}.md is not the rendered intake document (agents must not write it) — "
                    f"run python tools/frd_intake.py build --version {v}")
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["mode", "build", "check"])
    ap.add_argument("--version", type=int)
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    if a.cmd == "mode":
        print("frd" if is_intake(pdir) else "crd")
        return
    v = a.version or latest_version(pdir / "01-frd", "frd", "json")
    if not v:
        sys.exit("no frd.vN.json")
    if a.cmd == "build":
        out = pdir / "01-frd" / f"frd.v{v}.md"
        out.write_text(render(pdir, v), encoding="utf-8")
        size = out.stat().st_size
        src = (pdir / "01-frd" / "crd.md").stat().st_size
        print(f"wrote {rel(out)} ({size // 1024} KB; client text {src // 1024} KB + addendum)")
        errs = verbatim_errors(pdir, read_json(pdir / "01-frd" / f"frd.v{v}.json"))
    else:
        errs = check(pdir, v)
    if errs:
        print(f"INTAKE CHECK FAILED ({len(errs)}):")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    print(f"INTAKE CHECK OK: frd.v{v} keeps the client's wording")


if __name__ == "__main__":
    main()
