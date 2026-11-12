#!/usr/bin/env python
"""Traceability engine: CRD -> FRD -> Feature -> Test evidence (roadmap §6.1).

Usage:
  traceability.py frd [--version N]   every requirement cites existing CRD blocks; reports uncited CRD blocks
  traceability.py spec                every approved FRD requirement maps to >=1 feature (writes 02-spec/trace.json)
  traceability.py report              full chain incl. test evidence (writes 04-delivery/reports/traceability.json)
  traceability.py show <ID>           trace one C-nnn / FR-nnn / F-nnn forwards and backwards
Exit 1 when a check fails.
"""
from __future__ import annotations

import argparse
import re
import sys

from common import die, latest_version, project_dir, read_json, rel, write_json, now


def approved_frd(pdir):
    appr = read_json(pdir / "01-frd" / "approval.json", default={})
    v = appr.get("version") if appr.get("decision") == "approved" else None
    if not v:
        die("FRD is not approved yet")
    return v, read_json(pdir / "01-frd" / f"frd.v{v}.json")


def check_frd(pdir, version=None):
    fdir = pdir / "01-frd"
    v = version or latest_version(fdir, "frd", "json")
    frd = read_json(fdir / f"frd.v{v}.json")
    blocks = read_json(fdir / "crd-index.json")["blocks"]
    bad, cited = [], set()
    for r in frd["requirements"]:
        for s in r.get("source", []):
            if s.startswith("C-"):
                if s not in blocks:
                    bad.append(f"{r['id']} cites unknown CRD block {s}")
                cited.add(s)
    for q in frd.get("open_questions", []):
        cited.update(q.get("source", []))
    cited.update(frd.get("non_requirement_blocks", []))  # blocks the writer marked as background/boilerplate
    content = [cid for cid, b in blocks.items() if b["kind"] in ("para", "list", "table", "ui", "image")]
    uncited = [cid for cid in content if cid not in cited]
    coverage = round(100 * (len(content) - len(uncited)) / max(len(content), 1), 1)
    return {"version": v, "invalid_sources": bad, "uncited_blocks": uncited, "crd_coverage_pct": coverage}


def cmd_frd(a):
    pdir = project_dir()
    res = check_frd(pdir, a.version)
    print(f"frd.v{res['version']}: CRD content coverage {res['crd_coverage_pct']}%")
    for b in res["invalid_sources"]:
        print(f"  INVALID: {b}")
    if res["uncited_blocks"]:
        print(f"  Uncited CRD blocks (verify nothing was missed): {', '.join(res['uncited_blocks'])}")
    sys.exit(1 if res["invalid_sources"] else 0)


def cmd_spec(a):
    pdir = project_dir()
    v, frd = approved_frd(pdir)
    feats = read_json(pdir / "02-spec" / "features.json")["features"]
    req_ids = {r["id"] for r in frd["requirements"] if r.get("priority") != "wont"}
    req_to_feat = {rid: [] for rid in req_ids}
    unknown = []
    for f in feats:
        for rid in f["requirement_ids"]:
            if rid in req_to_feat:
                req_to_feat[rid].append(f["id"])
            else:
                unknown.append(f"{f['id']} references unknown requirement {rid}")
    unmapped = sorted(r for r, fs in req_to_feat.items() if not fs)
    out = {"frd_version": v, "generated_at": now(), "requirement_to_features": req_to_feat,
           "unmapped_requirements": unmapped, "unknown_references": unknown,
           "passed": not unmapped and not unknown}
    write_json(pdir / "02-spec" / "trace.json", out)
    print(f"{len(req_ids) - len(unmapped)}/{len(req_ids)} requirements mapped to features")
    for u in unmapped:
        print(f"  UNMAPPED: {u}")
    for u in unknown:
        print(f"  UNKNOWN: {u}")
    sys.exit(0 if out["passed"] else 1)


def feature_tests(pdir):
    """requirement_id -> list of {feature, test, status} from feature test reports."""
    out = {}
    rdir = pdir / "03-build" / "reports"
    if rdir.exists():
        for p in sorted(rdir.glob("F-*.test.json")):
            rep = read_json(p)
            for acc in rep.get("acceptance", []):
                rid = acc.get("requirement_id")
                if rid:
                    out.setdefault(rid, []).append({"feature": rep.get("scope"), "test": acc.get("test"),
                                                    "status": acc.get("status"), "report": rel(p)})
    return out


def cmd_report(a):
    pdir = project_dir()
    v, frd = approved_frd(pdir)
    feats = read_json(pdir / "02-spec" / "features.json")["features"]
    st = read_json(pdir / "state.json")
    tests = feature_tests(pdir)
    rows, gaps = [], []
    for r in frd["requirements"]:
        if r.get("priority") == "wont":
            continue
        fs = [f["id"] for f in feats if r["id"] in f["requirement_ids"]]
        done = [f for f in fs if st["features"].get(f, {}).get("status") == "Completed"]
        t = tests.get(r["id"], [])
        passed = [x for x in t if x["status"] == "pass"]
        row = {"requirement": r["id"], "priority": r["priority"], "crd_sources": r.get("source", []),
               "features": fs, "features_completed": done, "tests": t,
               "verified": bool(passed) and len(done) == len(fs) and bool(fs)}
        rows.append(row)
        if r["priority"] == "must" and not row["verified"]:
            gaps.append(r["id"])
    out = {"frd_version": v, "generated_at": now(), "rows": rows, "unverified_must": gaps,
           "verified_pct": round(100 * sum(x["verified"] for x in rows) / max(len(rows), 1), 1),
           "passed": not gaps}
    dest = pdir / "04-delivery" / "reports" / "traceability.json"
    write_json(dest, out)
    print(f"verified {out['verified_pct']}% of requirements; unverified MUST: {gaps or 'none'} -> {rel(dest)}")
    sys.exit(0 if out["passed"] else 1)


def cmd_show(a):
    pdir = project_dir()
    ident = a.id.upper()
    fdir = pdir / "01-frd"
    v = latest_version(fdir, "frd", "json")
    frd = read_json(fdir / f"frd.v{v}.json") if v else {"requirements": []}
    blocks = read_json(fdir / "crd-index.json", default={"blocks": {}})["blocks"]
    feats = read_json(pdir / "02-spec" / "features.json", default={"features": []})["features"]
    tests = feature_tests(pdir)
    if re.match(r"^C-\d+$", ident):
        print(f"{ident}: {blocks.get(ident, {}).get('text', '?')[:300]}")
        for r in frd["requirements"]:
            if ident in r.get("source", []):
                print(f"  -> {r['id']} {r['title']}")
                for f in feats:
                    if r["id"] in f["requirement_ids"]:
                        print(f"     -> {f['id']} {f['title']}")
    elif re.match(r"^F-\d+$", ident):
        f = next((x for x in feats if x["id"] == ident), None)
        if not f:
            die(f"unknown feature {ident}")
        print(f"{ident} {f['title']}")
        for rid in f["requirement_ids"]:
            r = next((x for x in frd["requirements"] if x["id"] == rid), {})
            print(f"  <- {rid} {r.get('title', '?')}  (CRD {', '.join(r.get('source', []))})")
            for t in tests.get(rid, []):
                print(f"     test: {t['test']} [{t['status']}]")
    else:
        r = next((x for x in frd["requirements"] if x["id"] == ident), None)
        if not r:
            die(f"unknown id {ident}")
        print(f"{ident} {r['title']}: {r['statement']}")
        for s in r.get("source", []):
            print(f"  <- {s}: {blocks.get(s, {}).get('text', '')[:200]}")
        for f in feats:
            if ident in f["requirement_ids"]:
                print(f"  -> {f['id']} {f['title']}")
        for t in tests.get(ident, []):
            print(f"  -> test {t['test']} [{t['status']}] ({t['report']})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("frd"); p.add_argument("--version", type=int); p.set_defaults(fn=cmd_frd)
    p = sub.add_parser("spec"); p.set_defaults(fn=cmd_spec)
    p = sub.add_parser("report"); p.set_defaults(fn=cmd_report)
    p = sub.add_parser("show"); p.add_argument("id"); p.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
