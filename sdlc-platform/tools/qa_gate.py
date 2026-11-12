#!/usr/bin/env python
"""Final quality gate (roadmap §5.5). Aggregates Phase 4 reports into 04-delivery/qa-gate.json.

Usage: qa_gate.py [--project ID]
Required reports in 04-delivery/reports/:
  system.test.json, regression.test.json         (test-report schema)
  security.review.json, nfr.review.json,
  performance.review.json                         (review schema)
  traceability.json                               (tools/traceability.py report)
Fails on: any failing suite, any critical/high finding, unverified MUST requirement,
open critical/high defects in 04-delivery/defects/, or incomplete features.
"""
from __future__ import annotations

import argparse
import sys

from common import project_dir, read_json, rel, write_json, now
from validate import validate

TESTS = ["system.test.json", "regression.test.json"]
REVIEWS = ["security.review.json", "nfr.review.json", "performance.review.json"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    rdir = pdir / "04-delivery" / "reports"
    failures, summary = [], {}

    st = read_json(pdir / "state.json")
    incomplete = [f for f, v in st["features"].items() if v["status"] != "Completed"]
    if incomplete:
        failures.append(f"features not completed: {incomplete}")

    for name in TESTS:
        p = rdir / name
        if not p.exists():
            failures.append(f"missing report {name}")
            continue
        errs = validate("test-report", p)
        rep = read_json(p)
        summary[name] = {"verdict": rep.get("verdict"), **rep.get("totals", {})}
        if errs:
            failures.append(f"{name} invalid: {errs[:3]}")
        if rep.get("verdict") != "pass" or rep.get("totals", {}).get("failed", 1) > 0:
            failures.append(f"{name}: verdict={rep.get('verdict')} failed={rep.get('totals', {}).get('failed')}")
        if any(c.get("exit_code") != 0 for c in rep.get("commands", [])):
            failures.append(f"{name}: a test command exited non-zero")

    for name in REVIEWS:
        p = rdir / name
        if not p.exists():
            failures.append(f"missing report {name}")
            continue
        errs = validate("review", p)
        rep = read_json(p)
        sev = {}
        for f in rep.get("findings", []):
            sev[f["severity"]] = sev.get(f["severity"], 0) + 1
        summary[name] = {"verdict": rep.get("verdict"), **sev}
        if errs:
            failures.append(f"{name} invalid: {errs[:3]}")
        blocking = [f["id"] for f in rep.get("findings", []) if f["severity"] in ("critical", "high")]
        if blocking:
            failures.append(f"{name}: unresolved critical/high findings {blocking}")

    tr = read_json(rdir / "traceability.json", default=None) if (rdir / "traceability.json").exists() else None
    if not tr:
        failures.append("missing report traceability.json (run tools/traceability.py report)")
    else:
        summary["traceability"] = {"verified_pct": tr["verified_pct"], "unverified_must": tr["unverified_must"]}
        if not tr["passed"]:
            failures.append(f"unverified MUST requirements: {tr['unverified_must']}")

    ddir = pdir / "04-delivery" / "defects"
    if ddir.exists():
        open_bad = [read_json(p)["id"] for p in ddir.glob("D-*.json")
                    if read_json(p).get("status") in ("open", "fixed") and read_json(p).get("severity") in ("critical", "high")]
        if open_bad:
            failures.append(f"open critical/high defects: {open_bad}")

    out = {"evaluated_at": now(), "passed": not failures, "failures": failures, "summary": summary}
    write_json(pdir / "04-delivery" / "qa-gate.json", out)
    print(("QA GATE PASSED" if out["passed"] else "QA GATE FAILED") + f" -> {rel(pdir / '04-delivery' / 'qa-gate.json')}")
    for f in failures:
        print(f"  - {f}")
    sys.exit(0 if out["passed"] else 1)


if __name__ == "__main__":
    main()
