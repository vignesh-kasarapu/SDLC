---
name: status
description: Show the active project's lifecycle status - phases, features, locks, recent history, agent/model usage - and the recommended next command.
disable-model-invocation: true
allowed-tools: Bash(python tools/*), Read
---
1. Run `python tools/state.py show`.
2. If `../projects/<id>/03-build/logs/agents.jsonl` exists, run `python tools/usage.py --by phase` and summarise it: runs, failures, time and estimated tokens per phase. Also show the top 3 agents from `python tools/usage.py`.
3. Recommend exactly one next command, based on the phase statuses:

| State | Next command |
|---|---|
| No `crd.md` yet | `/ingest-crd` (or `/import-existing` first, for an existing app) |
| Pending visuals (`gate.py crd-parsed` fails) | finish `/ingest-crd` step 3 |
| frd not_started or rejected | `/generate-frd` or `/revise-frd` |
| frd evaluated, gate failing | `/revise-frd` |
| frd passed | `/approve-frd` (a human action) |
| frd approved, wireframes not settled (`gate.py wireframes-ready` fails) | `/generate-wireframes`, or `/approve-wireframes` once they are reviewed |
| frd approved and wireframes settled | `/generate-specs` |
| spec in_progress | `/plan-features` |
| spec passed | `/approve-specs` (a human action) |
| spec approved | `/build-feature next` or `/build-all` |
| All features Completed | `/qa-system` |
| qa passed | `/release` |

Keep the whole reply under 25 lines.
