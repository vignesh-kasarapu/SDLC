#!/usr/bin/env python
"""Rule-based content checks for the Phase 2 specification (no LLM judgement).

Every rule has a code. Blockers fail the specs-exist gate; warnings are reported and sent back to
the owning agent once, but do not block.

  SV01 blocker  unknown ID: requirement (FR/NFR/BR/DR/IR/SR), CRD block (C-), feature (F-) or screen (S-)
  SV02 blocker  uncited spec item: a business-rule row without a requirement ID, or a requirement
                assigned to the feature that its spec never addresses
  SV03 blocker  TBD / TODO / FIXME / XXX / TBC / lorem ipsum / ??? left in a spec (OPEN: items are allowed)
  SV04 blocker  forbidden technology (outside the user's stack, see config/tech-catalog.yaml)
  SV05 warning  a number in a rule, criterion or NFR that appears nowhere in the client input or FRD
  SV06 blocker  cites a requirement with priority 'wont' (out of scope)
       warning  an obligation (must/shall/will) that restates something declared out of scope
  SV07 blocker  acceptance criteria: unique AC-Fnnn-nn IDs, Given/When/Then, linked to the feature's
                requirements, and every FR/BR of the feature covered by at least one criterion
  SV08 blocker  test cases: unique T-Fnnn-nn IDs, each criterion covered by a test, no unknown AC refs
  SV09 blocker  contracts disagree: entity without a table, API schema field without a column
                (unless x-derived), UI field mapped to an unknown API schema field
       warning  UI forms not mapped to API fields at all
  SV11 warning  a feature screen that is not one of the approved wireframes (generated wireframes only)
  SV10 blocker  existing code (when 00-discovery/project-facts.json exists): the spec re-creates a
                table, endpoint, file or class that already exists instead of modifying it

Usage: spec_rules.py [--project ID]   print every finding; exit 1 on blockers
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from common import ROOT, project_dir, read_json, read_yaml

CODES = {
    "SV01": "unknown ID", "SV02": "uncited spec item", "SV03": "placeholder text", "SV04": "forbidden technology",
    "SV05": "number not in source", "SV06": "out-of-scope contradiction", "SV07": "acceptance criteria",
    "SV08": "test coverage of criteria", "SV09": "contract mismatch", "SV10": "re-creates existing code",
    "SV11": "screen not in approved wireframes",
}
REQ_ID = re.compile(r"\b(?:FR|NFR|BR|DR|IR|SR)-\d{3}\b")
C_ID = re.compile(r"\bC-\d{3,}\b")
F_ID = re.compile(r"\bF-\d{3}\b")
S_ID = re.compile(r"\bS-\d{3}\b")
PLACEHOLDER = re.compile(r"\b(TBD|TBC|TODO|FIXME|XXX)\b|lorem ipsum|\?\?\?|\[insert[^\]]*\]|<placeholder>", re.I)
NEGATION = re.compile(r"\b(not|never|no|avoid|instead of|rather than|over|vs\.?|versus|rejected|"
                      r"alternatives?|considered|replac\w*|forbidden|excluded?|without)\b", re.I)
OBLIGATION = re.compile(r"\b(must|shall|will|should)\b", re.I)
HTTP_CODES = {"200", "201", "202", "204", "301", "302", "304", "400", "401", "403", "404", "405", "409",
              "410", "415", "422", "429", "500", "502", "503"}
AGENT_DOCS = ["architecture.md", "coding-standards.md", "database.md", "ui-spec.md"]


class Findings:
    def __init__(self):
        self.blockers: list[str] = []
        self.warnings: list[str] = []

    def add(self, code, where, msg, warn=False):
        (self.warnings if warn else self.blockers).append(f"{code} {where}: {msg}")


# ---------------------------------------------------------------- markdown helpers
def sections(text: str) -> dict[str, str]:
    """'## 2. Business rules' -> {'2. Business rules': body}."""
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            if cur is not None:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf)
    return out


def section(text: str, number: int) -> str:
    for title, body in sections(text).items():
        if re.match(rf"{number}\.\s", title):
            return body
    return ""


def md_tables(body: str) -> list[list[dict]]:
    tables, cur = [], []
    for line in body.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|"):
            cur.append([c.strip() for c in s.strip("|").split("|")])
        elif cur:
            if len(cur) >= 2 and re.fullmatch(r"[\s:|-]+", "|".join(cur[1])):
                head = [h.lower() for h in cur[0]]
                rows = [dict(zip(head, r + [""] * (len(head) - len(r)))) for r in cur[2:]]
                tables.append(rows)
            cur = []
    return tables


def col(row: dict, *keys) -> str:
    for k in row:
        if any(key in k for key in keys):
            return row[k]
    return ""


def snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).replace("-", "_").replace(" ", "_").lower()


def table_candidates(entity: str) -> set[str]:
    s = snake(entity)
    c = {s, s + "s", s + "es"}
    if s.endswith("y"):
        c.add(s[:-1] + "ies")
    return c


# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, pdir: Path):
        self.pdir, self.sdir, self.fdir = pdir, pdir / "02-spec", pdir / "01-frd"
        v = read_json(self.fdir / "approval.json", default={}).get("version")
        if not v:
            from common import latest_version
            v = latest_version(self.fdir, "frd", "json")
        self.frd = read_json(self.fdir / f"frd.v{v}.json", default={"requirements": []}) if v else {"requirements": []}
        self.reqs = {r["id"]: r for r in self.frd.get("requirements", [])}
        self.wont = {rid for rid, r in self.reqs.items() if r.get("priority") == "wont"}
        self.blocks = read_json(self.fdir / "crd-index.json", default={}).get("blocks", {})
        self.features = read_json(self.sdir / "features.json", default={}).get("features", [])
        self.fids = {f["id"] for f in self.features}
        ui = self.sdir / "ui-spec.md"
        self.ui = ui.read_text(encoding="utf-8") if ui.exists() else ""
        self.sids = set(S_ID.findall(self.ui))
        api = self.sdir / "openapi.yaml"
        self.api = read_yaml(api) if api.exists() else {}
        self.tables = parse_schema_sql((self.sdir / "schema.sql").read_text(encoding="utf-8")) \
            if (self.sdir / "schema.sql").exists() else {}
        self.ts = read_json(self.fdir / "tech-stack.json", default={})
        self.context = read_json(self.fdir / "context.json", default={})
        crd = self.fdir / "crd.md"
        corpus = (crd.read_text(encoding="utf-8") if crd.exists() else "") + json.dumps(self.frd) + \
            json.dumps(self.ts) + json.dumps(self.context)
        self.numbers = set(re.findall(r"\d+(?:\.\d+)?", corpus))
        facts = pdir / "00-discovery" / "project-facts.json"
        self.facts = read_json(facts) if facts.exists() else None


# ---------------------------------------------------------------- schema.sql
def parse_schema_sql(sql: str) -> dict[str, dict]:
    """{table: {"columns": set, "start": offset, "comment": preceding comment lines}}"""
    out = {}
    for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`\[\]]+)\s*\(", sql, re.I):
        name = re.sub(r"[\"`\[\]]", "", m.group(1)).split(".")[-1].lower()
        depth, i = 1, m.end()
        while i < len(sql) and depth:
            depth += {"(": 1, ")": -1}.get(sql[i], 0)
            i += 1
        body = sql[m.end():i - 1]
        parts, depth, cur = [], 0, ""
        for ch in body:
            depth += {"(": 1, ")": -1}.get(ch, 0)
            if ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        cols = set()
        for p in parts:
            p = re.sub(r"--[^\n]*", "", p).strip()
            if not p or re.match(r"(?i)(primary|foreign|constraint|unique|check|index|key|exclude)\b", p):
                continue
            cols.add(re.sub(r"[\"`\[\]]", "", p.split()[0]).lower())
        before = sql[:m.start()].rstrip().splitlines()[-3:]
        out[name] = {"columns": cols, "comment": " ".join(l for l in before if l.strip().startswith("--")),
                     "statement": sql[m.start():i].strip() + ";"}
    return out


# ---------------------------------------------------------------- rules
def forbidden_terms(ctx: Ctx) -> list[str]:
    cat = read_yaml(ROOT / "config" / "tech-catalog.yaml")
    stack_text = json.dumps({k: v for k, v in ctx.ts.items() if k not in ("forbidden", "allowed_mentions", "notes")})
    aliases = cat.get("aliases", {})

    def names(term):
        return [term] + aliases.get(term, [])

    def in_stack(term):
        return any(re.search(rf"(?<![\w.]){re.escape(n)}(?![\w])", stack_text, re.I) for n in names(term))

    allowed = set(cat.get("always_allowed", [])) | set(ctx.ts.get("allowed_mentions", []))
    out = list(ctx.ts.get("forbidden", []))
    for terms in cat["categories"].values():
        chosen = [t for t in terms if in_stack(t)]
        if not chosen:
            continue
        for t in terms:
            if t in chosen or t in allowed or any(t in c or c in t for c in chosen):
                continue
            out += names(t)
    return out


def check_text_rules(f: Findings, ctx: Ctx, where: str, text: str, forbidden: list[str]):
    in_open = False
    for line in text.splitlines():
        if re.match(r"^##\s+13\.", line):
            in_open = True
        if not in_open and "OPEN:" not in line and PLACEHOLDER.search(line):
            f.add("SV03", where, f"placeholder left: '{line.strip()[:90]}'")
        if not NEGATION.search(line):
            for t in forbidden:
                if re.search(rf"(?<![\w.]){re.escape(t)}(?![\w])", line):
                    f.add("SV04", where, f"mentions '{t}', which is not part of the chosen stack: '{line.strip()[:90]}'")
    for rid in sorted(set(REQ_ID.findall(text))):
        if ctx.reqs and rid not in ctx.reqs:
            f.add("SV01", where, f"unknown requirement {rid}")
        elif rid in ctx.wont:
            f.add("SV06", where, f"cites {rid}, which has priority 'wont' (out of scope)")
    for cid in sorted(set(C_ID.findall(text))):
        if ctx.blocks and cid not in ctx.blocks:
            f.add("SV01", where, f"unknown CRD block {cid}")
    for fid in sorted(set(F_ID.findall(text))):
        if ctx.fids and fid not in ctx.fids:
            f.add("SV01", where, f"unknown feature {fid}")


def check_feature(f: Findings, ctx: Ctx, feat: dict, text: str):
    fid, num = feat["id"], feat["id"][2:]
    where = f"features/{fid}.md"
    for sid in sorted(set(S_ID.findall(text))):
        if ctx.sids and sid not in ctx.sids:
            f.add("SV01", where, f"unknown screen {sid} (not in ui-spec.md)")
    own = set(feat["requirement_ids"])
    cited = set(REQ_ID.findall(text))
    for rid in sorted(own - cited - ctx.wont):
        f.add("SV02", where, f"assigned requirement {rid} is never addressed in the spec")
    # business rules cite their requirement
    for t in md_tables(section(text, 2)):
        for row in t:
            if any(v.strip() for v in row.values()) and not REQ_ID.search(" ".join(row.values())) \
                    and "none" not in " ".join(row.values()).lower():
                f.add("SV02", where, f"business rule without a requirement ID: '{' | '.join(row.values())[:80]}'")
    # numbers must come from the source
    for n in (2, 3, 9):
        body = re.sub(r"\b[A-Z]{1,4}(?:-[A-Z]?\d+)+\b|\bT-F\d{3}-\d{2}\b|\bAC-F\d{3}-\d{2}\b", " ", section(text, n))
        for line in body.splitlines():
            for num_ in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", line):
                if num_ in ("0", "1") or num_ in HTTP_CODES or num_ in ctx.numbers:
                    continue
                f.add("SV05", where, f"section {n}: number {num_} does not appear in the client input or FRD "
                                     f"(invented value?): '{line.strip()[:80]}'", warn=True)
    # out-of-scope phrases restated as obligations
    for item in ctx.context.get("scope", {}).get("out", []):
        words = [w for w in re.findall(r"[a-z]{4,}", item.lower()) if w not in
                 {"with", "that", "this", "from", "will", "into", "only", "other", "their", "phase", "system", "module"}][:4]
        if len(words) < 2:
            continue
        for line in text.splitlines():
            low = line.lower()
            if OBLIGATION.search(line) and not NEGATION.search(line) and all(w in low for w in words):
                f.add("SV06", where, f"obligation restates out-of-scope item '{item[:60]}': '{line.strip()[:80]}'", warn=True)
                break
    # SV07 acceptance criteria
    acs = {}
    tables = md_tables(section(text, 3))
    if not tables or not tables[0]:
        f.add("SV07", where, "section 3 has no acceptance-criteria table (| ID | Criterion (Given/When/Then) | Requirements |)")
    for t in tables:
        for row in t:
            aid = col(row, "id").strip("` ")
            crit = col(row, "criterion", "given")
            reqs = set(REQ_ID.findall(col(row, "requirement")))
            if not re.fullmatch(rf"AC-F{num}-\d{{2}}", aid):
                f.add("SV07", where, f"criterion ID '{aid}' must look like AC-F{num}-01")
                continue
            if aid in acs:
                f.add("SV07", where, f"duplicate criterion ID {aid}")
            low = crit.lower()
            if not all(re.search(rf"\b{k}\b", low) for k in ("given", "when", "then")):
                f.add("SV07", where, f"{aid} is not in Given/When/Then form")
            if not reqs & own:
                f.add("SV07", where, f"{aid} is not linked to any of the feature's requirements ({', '.join(sorted(own))})")
            acs[aid] = reqs
    if acs:
        covered = set().union(*acs.values())
        for rid in sorted(own):
            if rid.split("-")[0] in ("FR", "BR") and rid not in covered and rid not in ctx.wont:
                f.add("SV07", where, f"{rid} has no acceptance criterion")
    # SV08 test cases
    tested, tids = set(), set()
    for t in md_tables(section(text, 11)):
        for row in t:
            tid = col(row, "id").strip("` ")
            if not re.fullmatch(rf"T-F{num}-\d{{2}}", tid):
                f.add("SV08", where, f"test case ID '{tid}' must look like T-F{num}-01")
                continue
            if tid in tids:
                f.add("SV08", where, f"duplicate test case ID {tid}")
            tids.add(tid)
            refs = set(re.findall(r"AC-F\d{3}-\d{2}", col(row, "cover", "ac")))
            for r in refs - set(acs):
                f.add("SV08", where, f"{tid} covers unknown criterion {r}")
            tested |= refs
    for aid in sorted(set(acs) - tested):
        f.add("SV08", where, f"criterion {aid} has no test case")


def check_contracts(f: Findings, ctx: Ctx):
    tables = ctx.tables
    if ctx.tables or (ctx.sdir / "schema.sql").exists():
        for feat in ctx.features:
            for e in feat.get("entities", []):
                if not table_candidates(e) & set(tables):
                    f.add("SV09", "schema.sql", f"entity {e} ({feat['id']}) has no table (expected one of "
                                                f"{', '.join(sorted(table_candidates(e)))})")
    schemas = (ctx.api.get("components") or {}).get("schemas") or {}
    entities = {e for feat in ctx.features for e in feat.get("entities", [])}
    suffix = re.compile(r"(Create|Update|Patch|Response|Request|Read|Out|In|Summary|Detail|Details|List|Item|Dto|DTO|Input|Output)$")
    for name, s in schemas.items():
        ent = s.get("x-entity")
        base = name
        while not ent and suffix.search(base):
            base = suffix.sub("", base)
        ent = ent or base
        if ent not in entities:
            continue
        tbl = next((tables[t] for t in table_candidates(ent) if t in tables), None)
        if tbl is None:
            continue
        derived = set(s.get("x-derived-fields", []))
        for prop, d in (s.get("properties") or {}).items():
            if not isinstance(d, dict) or "$ref" in d or d.get("type") in ("object", "array") or d.get("x-derived") \
                    or prop in derived:
                continue
            if snake(prop) not in tbl["columns"] and snake(prop) + "_id" not in tbl["columns"]:
                f.add("SV09", "openapi.yaml", f"{name}.{prop} has no column in table for {ent} "
                                              f"(add the column, or mark the field x-derived: true)")
    if ctx.ui:
        mapped = False
        for t in md_tables(ctx.ui):
            for row in t:
                ref = next((v for k, v in row.items() if "api field" in k), None)
                if ref is None:
                    continue
                mapped = True
                ref = ref.strip("` ")
                if not ref or ref in ("-", "—") or ref.lower() in ("n/a", "none"):
                    continue
                sch, _, prop = ref.partition(".")
                if sch not in schemas:
                    f.add("SV09", "ui-spec.md", f"field mapped to unknown API schema '{ref}'")
                elif prop and prop not in ((schemas[sch].get("properties") or {})):
                    f.add("SV09", "ui-spec.md", f"field mapped to unknown property '{ref}'")
        if not mapped and re.search(r"(?i)validation", ctx.ui):
            f.add("SV09", "ui-spec.md", "form fields are not mapped to API fields (add an 'API field' column, "
                                        "e.g. JobCreate.title)", warn=True)


def run(pdir: Path) -> Findings:
    ctx = Ctx(pdir)
    f = Findings()
    forbidden = forbidden_terms(ctx) if ctx.ts else []
    for name in AGENT_DOCS:
        p = ctx.sdir / name
        if p.exists():
            check_text_rules(f, ctx, name, p.read_text(encoding="utf-8"), forbidden)
    for feat in ctx.features:
        p = ctx.sdir / "features" / f"{feat['id']}.md"
        if p.exists():
            text = p.read_text(encoding="utf-8")
            check_text_rules(f, ctx, f"features/{feat['id']}.md", text, forbidden)
            check_feature(f, ctx, feat, text)
    check_contracts(f, ctx)
    from wireframes import approved_screens
    wf = {s["name"].lower() for s in approved_screens(pdir)}
    if wf:
        for feat in ctx.features:
            for scr in feat.get("screens", []):
                if scr.lower() not in wf:
                    f.add("SV11", "features.json", f"{feat['id']} screen '{scr}' is not an approved wireframe "
                                                   f"(use the wireframe's name, or get the new screen approved)", warn=True)
    if ctx.facts is not None:
        from discover import existing_findings
        for where, msg in existing_findings(ctx):
            f.add("SV10", where, msg)
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    a = ap.parse_args()
    f = run(project_dir(a.project))
    for b in f.blockers:
        print(f"BLOCKER {b}")
    for w in f.warnings:
        print(f"WARNING {w}")
    print(f"spec rules: {len(f.blockers)} blocker(s), {len(f.warnings)} warning(s)")
    sys.exit(1 if f.blockers else 0)


if __name__ == "__main__":
    main()
