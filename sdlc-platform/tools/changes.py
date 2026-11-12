#!/usr/bin/env python
"""Human review of proposed FRD changes, before the next FRD version is written.

Usage:
  changes.py show [--target N]                       print the proposed changes as a table
  changes.py decide --by NAME [--target N]
        [--approve CH-001,CH-002|all|pending] [--reject ...]
        [--edit CH-003="use 10 days instead"] [--option CH-004="Option B"]
  changes.py status [--target N]                      exit 1 while any change is still pending

Plans live in projects/<id>/01-frd/change-plan.v<N>.json, where N is the version they will produce.
The frd-writer applies ONLY approved/edited changes; gate.py checks that against the FRD's change_log.
"""
from __future__ import annotations

import argparse
import sys
import textwrap

from common import die, latest_version, now, project_dir, read_json, rel, write_json

DECIDED = ("approved", "rejected", "edited")


def plan_path(pdir, target):
    fdir = pdir / "01-frd"
    if target is None:
        target = latest_version(fdir, "change-plan", "json")
        if not target:
            die("no change plan found — the FRD writer proposes one before each revision")
    return fdir / f"change-plan.v{target}.json"


def ids(arg, changes):
    if not arg:
        return []
    if arg == "all":
        return [c["id"] for c in changes]
    if arg == "pending":
        return [c["id"] for c in changes if c["decision"] == "pending"]
    return [x.strip().upper() for x in arg.split(",") if x.strip()]


def cmd_show(a):
    path = plan_path(project_dir(), a.target)
    plan = read_json(path)
    order = {"blocker": 0, "major": 1, "feedback": 2, "minor": 3}
    print(f"Proposed changes: FRD v{plan['from_version']} -> v{plan['target_version']}  ({rel(path)})")
    for c in sorted(plan["changes"], key=lambda c: (order.get(c.get("severity"), 4), c["id"])):
        reqs = ",".join(c.get("requirement_ids", [])) or "-"
        print(f"\n{c['id']} [{c.get('severity', '-')}] {c['action'].upper()} {reqs}   decision: {c['decision']}")
        print(textwrap.indent(textwrap.fill(c["summary"], 100), "  "))
        print(f"  why: {c['reason']}  (from {', '.join(c['triggered_by'])})")
        if c.get("before"):
            print(textwrap.indent(textwrap.fill("before: " + c["before"], 100), "  "))
        if c.get("after"):
            print(textwrap.indent(textwrap.fill("after:  " + c["after"], 100), "  "))
        for i, o in enumerate(c.get("options", []), 1):
            print(f"  option {i}: {o}")
        if c.get("user_note"):
            print(f"  your note: {c['user_note']}")
    counts = {}
    for c in plan["changes"]:
        counts[c["decision"]] = counts.get(c["decision"], 0) + 1
    print("\nTotals: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def cmd_decide(a):
    path = plan_path(project_dir(), a.target)
    plan = read_json(path)
    by_id = {c["id"]: c for c in plan["changes"]}

    def setd(cid, decision, **extra):
        if cid not in by_id:
            die(f"unknown change {cid}")
        by_id[cid].update(decision=decision, decided_by=a.by, decided_at=now(), **extra)

    for cid in ids(a.approve, plan["changes"]):
        setd(cid, "approved")
    for cid in ids(a.reject, plan["changes"]):
        setd(cid, "rejected")
    for item in a.edit or []:
        cid, _, note = item.partition("=")
        if not note.strip():
            die(f"--edit needs CH-nnn=\"instruction\", got {item!r}")
        setd(cid.strip().upper(), "edited", user_note=note.strip())
    for item in a.option or []:
        cid, _, opt = item.partition("=")
        setd(cid.strip().upper(), "approved", chosen_option=opt.strip())
    write_json(path, plan)
    pending = [c["id"] for c in plan["changes"] if c["decision"] == "pending"]
    print(f"recorded decisions by {a.by}; pending: {', '.join(pending) or 'none'}")


def cmd_status(a):
    plan = read_json(plan_path(project_dir(), a.target))
    pending = [c["id"] for c in plan["changes"] if c["decision"] == "pending"]
    if pending:
        print(f"PENDING: {', '.join(pending)}")
        sys.exit(1)
    approved = [c["id"] for c in plan["changes"] if c["decision"] in ("approved", "edited")]
    print(f"ALL DECIDED: apply {', '.join(approved) or 'nothing'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show"); p.add_argument("--target", type=int); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("decide"); p.add_argument("--target", type=int); p.add_argument("--by", required=True)
    p.add_argument("--approve"); p.add_argument("--reject")
    p.add_argument("--edit", action="append"); p.add_argument("--option", action="append")
    p.set_defaults(fn=cmd_decide)
    p = sub.add_parser("status"); p.add_argument("--target", type=int); p.set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
