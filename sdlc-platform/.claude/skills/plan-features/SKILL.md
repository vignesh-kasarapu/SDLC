---
name: plan-features
description: Phase 2 - analyse feature dependencies, validate the DAG (cycles, unknown refs), compute execution order and parallel waves, and produce plan.json.
disable-model-invocation: true
---
Build the dependency-aware execution plan. `P = ../projects/<id>`. Follow CLAUDE.md.

1. **Gate.** Run `python tools/gate.py specs-exist`. Stop if it fails.
2. **Dependencies.** Dispatch **dependency-analyst**:
   `PROJECT=P. Write 02-spec/dependencies.json, then run python tools/dag.py build until VALID.`
   Log it.
3. **Deterministic check.** Run `python tools/dag.py build` yourself; it also refreshes `02-spec/index.md` with the waves. Then run `python tools/traceability.py spec`. If either fails, report it and stop.
4. **Planning gate.** Run `python tools/gate.py plan-valid`. If it passes, run `python tools/state.py phase spec passed`.
5. **Report.**
   - Show the contents of `02-spec/dag.md`: the mermaid graph and the waves.
   - Show the requirement-to-feature coverage.
   - List what the reviewer must check before approving: start at `02-spec/index.md`, then `architecture.md`, `coding-standards.md`, `features.md`, `database.md`, `api-spec.md` (and `openapi.yaml`), `ui-spec.md` and every `features/F-nnn.md`.
   - Give the next step: `/approve-specs`, which is a human action.
