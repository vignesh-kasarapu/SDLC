#!/usr/bin/env python
"""Usage report from the agent log (../projects/<id>/03-build/logs/agents.jsonl).

Shows, per agent and per phase: runs, failures, total and average duration, and estimated tokens
in/out. These numbers only exist for runs logged with `state.py start` before the dispatch and
`state.py log ... --inputs ... --outputs ...` after it. Token counts are estimates (bytes / 4):
use them to compare runs and to plan against Claude Pro limits, not as billing figures.

Usage: usage.py [--by agent|phase|model|key] [--json] [--project ID]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from common import project_dir


def load(pdir):
    log = pdir / "03-build" / "logs" / "agents.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarise(entries, by="agent"):
    rows = defaultdict(lambda: {"runs": 0, "failed": 0, "duration_s": 0, "timed": 0, "tokens_in": 0, "tokens_out": 0})
    for e in entries:
        r = rows[e.get(by) or "-"]
        r["runs"] += 1
        r["failed"] += e.get("event") == "failed"
        if "duration_s" in e:
            r["duration_s"] += e["duration_s"]
            r["timed"] += 1
        r["tokens_in"] += e.get("est_tokens_in", 0)
        r["tokens_out"] += e.get("est_tokens_out", 0)
    return dict(sorted(rows.items(), key=lambda kv: -kv[1]["tokens_in"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--by", choices=["agent", "phase", "model", "key"], default="agent")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--project")
    a = ap.parse_args()
    entries = load(project_dir(a.project))
    rows = summarise(entries, a.by)
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    if not entries:
        print("no agent runs logged yet")
        return
    print(f"{a.by:<24}{'runs':>6}{'fail':>6}{'total min':>11}{'avg s':>8}{'~tok in':>10}{'~tok out':>10}")
    tot = defaultdict(int)
    for k, r in rows.items():
        avg = r["duration_s"] // r["timed"] if r["timed"] else 0
        print(f"{k:<24}{r['runs']:>6}{r['failed']:>6}{r['duration_s'] / 60:>11.1f}{avg:>8}{r['tokens_in']:>10}{r['tokens_out']:>10}")
        for x in ("runs", "failed", "duration_s", "tokens_in", "tokens_out"):
            tot[x] += r[x]
    print(f"{'TOTAL':<24}{tot['runs']:>6}{tot['failed']:>6}{tot['duration_s'] / 60:>11.1f}{'':>8}{tot['tokens_in']:>10}{tot['tokens_out']:>10}")
    untimed = sum(1 for e in entries if "duration_s" not in e)
    if untimed:
        print(f"({untimed} run(s) without timing: log them with `state.py start` before dispatching)")


if __name__ == "__main__":
    main()
