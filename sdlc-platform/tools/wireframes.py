#!/usr/bin/env python
"""Wireframe stage, between FRD approval and spec generation (and therefore before development).

After the FRD is approved the user decides, once, how screens are settled:
  provided   the client's input already contains wireframes (HTML mockups, or images the
             visual-analyst classified as ui_screen); they are part of the approved FRD
  generate   the wireframe-designer agent creates low-fidelity HTML wireframes, one per screen,
             which the human reviews (feedback rounds <= 3) and approves with /approve-wireframes
  skip       no wireframes (e.g. an API-only system); a reason is required

Specs (/generate-specs) and therefore development cannot start until `gate.py wireframes-ready` passes.

Files (../projects/<id>/01b-wireframes/):
  decision.json           the user's choice, who made it and why
  vN/screens.json         screen list (schemas/wireframes.schema.json)
  vN/W-nnn-<slug>.html    one self-contained low-fidelity wireframe per screen
  vN/index.html           clickable overview linking every screen
  vN/wireframes.md        flow diagram and per-screen summary for reviewers
  feedback.md             review rounds (WF-REVIEW-n)
  approval.json           written only by tools/approve.py wireframes (locks vN)

An approved version is locked. Changes after approval go into a new version (new-version), which
must be approved again.

Usage:
  wireframes.py status                                  what exists, what was decided, what is next
  wireframes.py decide provided|generate|skip --by NAME [--reason TEXT]
  wireframes.py new-version                             create the next vN folder (copy of the approved one)
  wireframes.py feedback "<text>" --by NAME             record a review round on the latest version
  wireframes.py check [--version N]                     validate a generated wireframe set
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from common import latest_version, now, project_dir, read_json, rel, write_json

MAX_ROUNDS = 3
EXTERNAL = re.compile(r"<script[^>]+src\s*=|<link[^>]+href\s*=\s*[\"']?(https?:)?//|@import|url\(\s*[\"']?(https?:)?//|"
                      r"<img[^>]+src\s*=\s*[\"']?(https?:)?//", re.I)
PLACEHOLDER = re.compile(r"\{\{|\b(TBD|TODO|FIXME)\b|lorem ipsum", re.I)


def wdir(pdir) -> Path:
    return pdir / "01b-wireframes"


def versions(pdir) -> list[int]:
    d = wdir(pdir)
    return sorted(int(p.name[1:]) for p in d.glob("v*") if p.is_dir() and re.fullmatch(r"v\d+", p.name)) if d.exists() else []


def latest(pdir) -> int | None:
    v = versions(pdir)
    return v[-1] if v else None


def decision(pdir) -> dict:
    return read_json(wdir(pdir) / "decision.json", default={})


def approval(pdir) -> dict:
    return read_json(wdir(pdir) / "approval.json", default={})


def client_wireframes(pdir) -> list[str]:
    """Screens the client already supplied: HTML mockups and images the vision agent read as screens."""
    idx = read_json(pdir / "01-frd" / "crd-index.json", default={}).get("blocks", {})
    found = []
    for cid, b in idx.items():
        if b["kind"] == "ui" and b["text"].startswith("UI form"):
            found.append(f"{cid} {b['text'][:70]}")
        elif b["kind"] == "image" and (b.get("visual") or {}).get("kind") == "ui_screen":
            name = (b["visual"].get("screen") or {}).get("screen_name") or b["visual"]["summary"][:50]
            found.append(f"{cid} screen image: {name}")
    return found


def _approved_frd(pdir) -> dict:
    v = read_json(pdir / "01-frd" / "approval.json", default={}).get("version") or latest_version(pdir / "01-frd", "frd", "json")
    return read_json(pdir / "01-frd" / f"frd.v{v}.json", default={"requirements": []}) if v else {"requirements": []}


def approved_screens(pdir) -> list[dict]:
    """Screens of the approved generated version, with their file paths; [] when not generated/approved."""
    appr = approval(pdir)
    if decision(pdir).get("mode") != "generate" or appr.get("decision") != "approved":
        return []
    v = appr["version"]
    screens = read_json(wdir(pdir) / f"v{v}" / "screens.json", default={}).get("screens", [])
    return [{**s, "path": rel(wdir(pdir) / f"v{v}" / s["file"])} for s in screens]


def check_set(pdir, v: int) -> list[str]:
    from validate import validate
    vdir = wdir(pdir) / f"v{v}"
    sj = vdir / "screens.json"
    if not sj.exists():
        return [f"{rel(sj)} missing — the wireframe-designer writes it"]
    errs = [f"screens.json: {e}" for e in validate("wireframes", sj)]
    if errs:
        return errs
    data = read_json(sj)
    reqs = {r["id"]: r for r in _approved_frd(pdir)["requirements"]}
    ids = [s["id"] for s in data["screens"]]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errs.append(f"duplicate screen id {dup}")
    names = [s["name"].lower() for s in data["screens"]]
    for dup in sorted({n for n in names if names.count(n) > 1}):
        errs.append(f"duplicate screen name '{dup}' (Phase 2 uses names verbatim)")
    covered = set()
    for s in data["screens"]:
        f = vdir / s["file"]
        if not s["file"].startswith(s["id"]):
            errs.append(f"{s['id']}: file name must start with the screen id ({s['file']})")
        if not f.exists():
            errs.append(f"{s['id']}: {s['file']} missing")
        else:
            html = f.read_text(encoding="utf-8")
            if not re.search(rf"<title>[^<]*{s['id']}", html):
                errs.append(f"{s['file']}: <title> must contain {s['id']}")
            if f'data-screen="{s["id"]}"' not in html:
                errs.append(f"{s['file']}: <body> needs data-screen=\"{s['id']}\"")
            if EXTERNAL.search(html):
                errs.append(f"{s['file']}: external script/style/image found; wireframes must be self-contained")
            if PLACEHOLDER.search(html):
                errs.append(f"{s['file']}: placeholder text left (TBD/TODO/lorem/{{{{)")
            for rid in s["requirement_ids"]:
                if rid not in html:
                    errs.append(f"{s['file']}: requirement {rid} is not annotated on the screen")
        for rid in s["requirement_ids"]:
            if rid not in reqs:
                errs.append(f"{s['id']}: unknown requirement {rid} (not in the approved FRD)")
            elif reqs[rid].get("priority") == "wont":
                errs.append(f"{s['id']}: {rid} is out of scope (priority wont)")
            covered.add(rid)
        for t in s.get("navigates_to", []):
            if t not in ids:
                errs.append(f"{s['id']}: navigates to unknown screen {t}")
    no_ui = {x["id"] for x in data["no_ui_requirements"]}
    for rid in sorted(no_ui - set(reqs)):
        errs.append(f"no_ui_requirements: unknown requirement {rid}")
    for rid, r in sorted(reqs.items()):
        if r["type"] == "functional" and r.get("priority") != "wont" and rid not in covered | no_ui:
            errs.append(f"{rid} ({r['title']}) has no screen; add it to a screen or to no_ui_requirements with a reason")
    index = vdir / "index.html"
    if not index.exists():
        errs.append("index.html missing (overview linking every screen)")
    else:
        text = index.read_text(encoding="utf-8")
        errs += [f"index.html does not link {s['file']}" for s in data["screens"] if s["file"] not in text]
    if not (vdir / "wireframes.md").exists():
        errs.append("wireframes.md missing (flow and per-screen summary for reviewers)")
    return errs


def check_errors(pdir) -> list[str]:
    """Gate wireframes-check: a generated set that is complete and valid (required before approval)."""
    from gate import g_frd_approved
    errs = g_frd_approved(pdir)
    if decision(pdir).get("mode") != "generate":
        return errs + ["wireframes are not being generated for this project (see wireframes.py status)"]
    v = latest(pdir)
    if not v:
        return errs + ["no wireframe version yet — run /generate-wireframes"]
    return errs + check_set(pdir, v)


def ready_errors(pdir) -> list[str]:
    """Gate wireframes-ready: screens are settled, so specs and development may start."""
    from gate import g_frd_approved, _approval_ok
    errs = g_frd_approved(pdir)
    d = decision(pdir)
    if not d:
        hint = (f"the client supplied {len(client_wireframes(pdir))} wireframe(s); confirm them"
                if client_wireframes(pdir) else "no wireframes exist yet")
        return errs + [f"wireframes not settled ({hint}) — run /generate-wireframes"]
    if d["mode"] in ("provided", "skip"):
        return errs
    errs += _approval_ok(pdir, "01b-wireframes")
    if not errs and approval(pdir).get("version") != latest(pdir):
        errs.append(f"wireframes v{approval(pdir).get('version')} are approved but v{latest(pdir)} is the latest — "
                    f"run /approve-wireframes")
    return errs


def _set_phase(pdir, status, **kw):
    import state as S
    st = S.load(pdir)
    st["phases"]["wireframes"] = status
    S.append_history(st, "wireframes", status=status, **kw)
    S.save(pdir, st)


def cmd_status(pdir):
    found, d, vs, appr = client_wireframes(pdir), decision(pdir), versions(pdir), approval(pdir)
    print(f"client wireframes in the approved input: {len(found)}")
    for f in found[:10]:
        print(f"  - {f}")
    print(f"decision: {d.get('mode', 'none')}" + (f" by {d['by']} ({d.get('reason', '')})" if d else ""))
    if vs:
        v = vs[-1]
        n = len(read_json(wdir(pdir) / f"v{v}" / "screens.json", default={}).get("screens", []))
        rounds = _rounds(pdir, v)
        print(f"generated versions: {', '.join(f'v{x}' for x in vs)}; latest v{v}: {n} screen(s), {rounds} review round(s)")
    if appr:
        print(f"approval: {appr.get('decision')} v{appr.get('version')} by {appr.get('by')}")
    errs = ready_errors(pdir)
    from gate import g_frd_approved
    if g_frd_approved(pdir):
        print("NEXT: the FRD must be approved first (/approve-frd); wireframes come right after it")
    elif not errs:
        print("NEXT: /generate-specs (wireframes settled)")
    elif not d:
        print("NEXT: ask the user: " + ("confirm the client's wireframes (provided), " if found else "") +
              "create wireframes (generate), or skip with a reason")
    elif d["mode"] == "generate" and not vs:
        print("NEXT: dispatch wireframe-designer for v1 (/generate-wireframes)")
    else:
        print("NEXT: review the wireframes, then /approve-wireframes or /generate-wireframes \"<feedback>\"")


def cmd_decide(pdir, a):
    from gate import g_frd_approved
    errs = g_frd_approved(pdir)
    if errs:
        sys.exit("REFUSED: wireframes come after FRD approval: " + "; ".join(errs))
    if appr := approval(pdir):
        if appr.get("decision") == "approved":
            sys.exit("REFUSED: wireframes are already approved; use new-version to change them")
    if a.mode == "provided" and not client_wireframes(pdir):
        sys.exit("REFUSED: the approved input contains no wireframes; choose 'generate' or 'skip'")
    if a.mode == "skip" and not (a.reason or "").strip():
        sys.exit("REFUSED: skipping wireframes needs --reason")
    write_json(wdir(pdir) / "decision.json", {"mode": a.mode, "by": a.by, "at": now(), "reason": a.reason or "",
                                             "client_wireframes": client_wireframes(pdir)})
    _set_phase(pdir, {"provided": "approved", "skip": "skipped", "generate": "in_progress"}[a.mode], by=a.by, mode=a.mode)
    print(f"wireframes: {a.mode} (decided by {a.by})")


def cmd_new_version(pdir):
    if decision(pdir).get("mode") != "generate":
        sys.exit("REFUSED: run `wireframes.py decide generate` first")
    v = latest(pdir)
    appr = approval(pdir)
    if v and not (appr.get("decision") == "approved" and appr.get("version") == v):
        sys.exit(f"v{v} is not approved yet; revise it in place (feedback rounds) instead of creating a new version")
    nv = (v or 0) + 1
    dest = wdir(pdir) / f"v{nv}"
    if v:
        shutil.copytree(wdir(pdir) / f"v{v}", dest)
        sj = read_json(dest / "screens.json")
        sj["version"] = nv
        write_json(dest / "screens.json", sj)
        _set_phase(pdir, "in_progress", version=nv)
    else:
        dest.mkdir(parents=True)
    print(f"created {rel(dest)}")


def _rounds(pdir, v) -> int:
    fb = wdir(pdir) / "feedback.md"
    return len(re.findall(rf"^## WF-REVIEW-\d+ .*on v{v}\)", fb.read_text(encoding="utf-8"), re.M)) if fb.exists() else 0


def cmd_feedback(pdir, a):
    v = latest(pdir)
    if not v:
        sys.exit("no wireframes to give feedback on")
    if _rounds(pdir, v) >= MAX_ROUNDS:
        sys.exit(f"ESCALATE: v{v} already had {MAX_ROUNDS} review rounds; resolve the remaining points with the user "
                 f"directly, or approve/reject")
    fb = wdir(pdir) / "feedback.md"
    n = len(re.findall(r"^## WF-REVIEW-\d+", fb.read_text(encoding="utf-8"), re.M)) + 1 if fb.exists() else 1
    with open(fb, "a", encoding="utf-8") as f:
        f.write(f"\n## WF-REVIEW-{n} ({now()}, {a.by}, on v{v})\n{a.text}\n")
    print(f"recorded WF-REVIEW-{n} on v{v} (round {_rounds(pdir, v)} of {MAX_ROUNDS})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["status", "decide", "new-version", "feedback", "check"])
    ap.add_argument("arg", nargs="?", help="decide: provided|generate|skip; feedback: the text")
    ap.add_argument("--by")
    ap.add_argument("--reason")
    ap.add_argument("--version", type=int)
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    if a.cmd == "status":
        return cmd_status(pdir)
    if a.cmd == "decide":
        if a.arg not in ("provided", "generate", "skip") or not a.by:
            ap.error("decide provided|generate|skip --by NAME [--reason TEXT]")
        a.mode = a.arg
        return cmd_decide(pdir, a)
    if a.cmd == "new-version":
        return cmd_new_version(pdir)
    if a.cmd == "feedback":
        if not a.arg or not a.by:
            ap.error('feedback "<text>" --by NAME')
        a.text = a.arg
        return cmd_feedback(pdir, a)
    v = a.version or latest(pdir)
    errs = check_set(pdir, v) if v else ["no wireframe version yet"]
    if errs:
        print(f"WIREFRAMES INCOMPLETE ({len(errs)}):")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    n = len(read_json(wdir(pdir) / f"v{v}" / "screens.json")["screens"])
    print(f"WIREFRAMES OK: v{v}, {n} screen(s), every functional requirement has a screen or a no-UI reason")


if __name__ == "__main__":
    main()
