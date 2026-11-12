#!/usr/bin/env python
"""Dependency analysis engine (roadmap §3.6). Deterministic — the LLM only *proposes* edges.

Usage: dag.py build [--project ID]
Reads  02-spec/features.json, 02-spec/dependencies.json
Writes 02-spec/dag.json   nodes, hard/soft edges, cycles (if any)
       02-spec/plan.json  {valid, order, groups (parallelisable waves), features[{id,title,depends_on}]}
       02-spec/dag.md     mermaid diagram for humans
Exit 1 if edges reference unknown features or hard dependencies form a cycle.
"""
from __future__ import annotations

import argparse
import sys

from common import project_dir, read_json, rel, write_json, now


def find_cycles(nodes, adj):
    """Return list of cycles (each a list of node ids) using DFS colouring."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    stack, cycles = [], []

    def dfs(u):
        color[u] = GREY
        stack.append(u)
        for v in sorted(adj.get(u, ())):
            if color[v] == GREY:
                cycles.append(stack[stack.index(v):] + [v])
            elif color[v] == WHITE:
                dfs(v)
        stack.pop()
        color[u] = BLACK

    for n in sorted(nodes):
        if color[n] == WHITE:
            dfs(n)
    return cycles


def waves(nodes, preds):
    """Kahn's algorithm grouped into waves: every feature in a wave can run in parallel."""
    remaining = {n: set(preds.get(n, ())) for n in nodes}
    groups = []
    while remaining:
        ready = sorted(n for n, p in remaining.items() if not p)
        if not ready:
            return groups, sorted(remaining)  # cycle residue
        groups.append(ready)
        for n in ready:
            del remaining[n]
        for p in remaining.values():
            p.difference_update(ready)
    return groups, []


def build(pdir):
    sdir = pdir / "02-spec"
    feats = read_json(sdir / "features.json")["features"]
    deps = read_json(sdir / "dependencies.json")["edges"]
    ids = {f["id"] for f in feats}
    errors = []
    hard_adj, preds, soft = {}, {}, []
    for e in deps:
        if e["from"] not in ids or e["to"] not in ids:
            errors.append(f"edge {e['from']}->{e['to']} references unknown feature")
            continue
        if e["from"] == e["to"]:
            errors.append(f"self-dependency on {e['from']}")
            continue
        if e["type"] == "hard":
            hard_adj.setdefault(e["from"], set()).add(e["to"])
            preds.setdefault(e["to"], set()).add(e["from"])
        else:
            soft.append(e)
    cycles = find_cycles(ids, hard_adj)
    for c in cycles:
        errors.append("circular hard dependency: " + " -> ".join(c))
    groups, residue = waves(ids, preds)
    order = [n for g in groups for n in g]
    valid = not errors and not residue

    write_json(sdir / "dag.json", {
        "generated_at": now(), "nodes": sorted(ids),
        "hard_edges": [e for e in deps if e["type"] == "hard"], "soft_edges": soft,
        "cycles": cycles, "errors": errors})
    plan = {
        "generated_at": now(), "valid": valid, "errors": errors,
        "order": order if valid else [], "groups": groups if valid else [],
        "features": [{"id": f["id"], "title": f["title"],
                      "depends_on": sorted(preds.get(f["id"], ())),
                      "soft_depends_on": sorted(e["from"] for e in soft if e["to"] == f["id"]),
                      "group": next((i + 1 for i, g in enumerate(groups) if f["id"] in g), None)}
                     for f in feats],
    }
    write_json(sdir / "plan.json", plan)

    title = {f["id"]: f["title"].replace('"', "'") for f in feats}
    md = ["# Feature dependency graph", "", "```mermaid", "flowchart TD"]
    md += [f'    {i.replace("-", "")}["{i}: {title[i]}"]' for i in sorted(ids)]
    md += [f'    {e["from"].replace("-", "")} --> {e["to"].replace("-", "")}' for e in deps if e["type"] == "hard" and e["from"] in ids and e["to"] in ids]
    md += [f'    {e["from"].replace("-", "")} -.-> {e["to"].replace("-", "")}' for e in soft]
    md += ["```", "", "Solid = hard dependency (blocks execution); dotted = soft (informational).", "",
           "## Execution waves (features in the same wave are independent)"]
    md += [f"{i}. {', '.join(g)}" for i, g in enumerate(groups, 1)]
    if errors:
        md += ["", "## Errors"] + [f"- {e}" for e in errors]
    (sdir / "dag.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    from spec_docs import render  # keep 02-spec/index.md (waves, dependencies) current
    render(pdir)
    return plan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    plan = build(pdir)
    if plan["valid"]:
        print(f"VALID plan: {len(plan['order'])} features in {len(plan['groups'])} wave(s)")
        for i, g in enumerate(plan["groups"], 1):
            print(f"  wave {i}: {', '.join(g)}")
        print(f"-> {rel(pdir / '02-spec' / 'plan.json')}")
    else:
        print("INVALID plan:")
        for e in plan["errors"]:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
