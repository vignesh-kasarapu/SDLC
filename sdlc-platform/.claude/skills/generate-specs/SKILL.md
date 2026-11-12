---
name: generate-specs
description: Phase 2 - convert the approved FRD into a set of separate Markdown specification documents (architecture, coding standards, feature breakdown, database, API, UI, index) plus one technical spec per feature.
disable-model-invocation: true
---
Generate the technical specifications for the active project. `P = ../projects/<id>`. Follow CLAUDE.md. Let `N` be the approved FRD version (`P/01-frd/approval.json` → `version`).

## Output: the Markdown spec set (`P/02-spec/`)
| File | Written by |
|---|---|
| `architecture.md`, `coding-standards.md` | architect |
| `features.md` | `tools/spec_docs.py render`, from `features.json` |
| `database.md` (with `schema.sql`) | db-spec |
| `api-spec.md` | `tools/spec_docs.py render`, from `openapi.yaml` |
| `ui-spec.md` | ui-spec |
| `features/F-nnn.md`, one per feature | feature-spec-writer |
| `index.md`, the table of contents and per-feature status | `tools/spec_docs.py render` |

Never hand-edit the rendered files; change their JSON/YAML source and re-render.

## Steps
0. **Resume.** If `P/02-spec/` already has outputs from an interrupted run, skip each step whose outputs exist and pass their checks: architecture (step 3), `features.json` with a passing trace (step 4), contracts (step 5). Feature specs resume through `spec_docs.py pending`.
1. **Gate.** Run `python tools/gate.py wireframes-ready`. This means the FRD is approved and the screens are settled (approved wireframes, confirmed client wireframes, or an explicit skip). Stop if it fails; the next step is then `/generate-wireframes`.
   If `P/02-spec/approval.json` exists with decision approved, the specs are locked. Tell the user, then stop.
2. Run `python tools/state.py phase spec in_progress`.
3. **Architecture (Opus).** Dispatch **architect**:
   `PROJECT=P. Approved FRD: 01-frd/frd.vN.json/.md. Approved wireframes: 01b-wireframes/vW/screens.json (if any). Binding stack: 01-frd/tech-stack.json. MVC is mandatory (knowledge/standards/mvc-coding-standards.md). Write 02-spec/architecture.md, 02-spec/coding-standards.md, 02-spec/commands.json, and 02-spec/ownership.yaml + layers.yaml (required unless the stack is FastAPI + React).`
   Log it. Show the user the stack, the MVC root folders and any "Gaps", one line each.
4. **Feature breakdown.** Dispatch **feature-breakdown**: `PROJECT=P. FRD vN. Approved wireframes: 01b-wireframes/vW/screens.json (if any). Write 02-spec/features.json.` Log it.
   Then run `python tools/traceability.py spec`. If it fails because of unmapped requirements, send the output back to feature-breakdown to fix. Allow at most 2 rounds.
5. **Contracts.** Dispatch **db-spec**, **api-spec** and **ui-spec** in parallel (one message, three Agent calls), each with `PROJECT=P. FRD vN.` and its output paths:
   - db-spec: `02-spec/schema.sql` and `02-spec/database.md`
   - api-spec: `02-spec/openapi.yaml`
   - ui-spec: `02-spec/ui-spec.md`

   Log all three. Then run `python tools/spec_docs.py render` to write `features.md` and `api-spec.md`.
6. **Per-feature specs.**
   1. Run `python tools/spec_docs.py slice all`. It writes `02-spec/slices/F-nnn.md` per feature: only that feature's requirements, cited client text, tables, operations, screens and architecture excerpts.
   2. Run `python tools/spec_docs.py pending` for the features still to write. **Resume:** after an interruption this lists only the missing or failing specs. Never re-dispatch a completed one.
   3. For each pending feature, run `python tools/state.py start feature-spec-writer --key F-nnn`, then dispatch **feature-spec-writer** with `PROJECT=P. FEATURE=F-nnn. Read 02-spec/slices/F-nnn.md (not the full FRD). Write 02-spec/features/F-nnn.md.`
      - Run up to 4 in parallel per message, to respect usage limits.
      - Log each one with `python tools/state.py log feature-spec-writer done --key F-nnn --inputs P/02-spec/slices/F-nnn.md --outputs P/02-spec/features/F-nnn.md`.
      - Collect the `OPEN` counts from their replies.
7. **Render and check.**
   1. Run `python tools/spec_docs.py render` to refresh `index.md` with the per-feature OPEN counts.
   2. Run `python tools/spec_docs.py check`. It checks structure and content rules SV01–SV10: unknown IDs, uncited items, placeholders, forbidden technology, invented numbers, out-of-scope contradictions, acceptance criteria and test coverage, database/API/UI contract agreement, and re-creating existing code. Send each **blocker** back to the agent that owns the file, then re-render and re-check:
      - endpoint or tag mismatch: api-spec
      - screen name mismatch: ui-spec
      - feature spec structure: feature-spec-writer for that feature
      - missing `database.md`, an entity without a table, or a missing column: db-spec (or api-spec, when the field should be `x-derived`)
      - SV01–SV08 in `features/F-nnn.md`: feature-spec-writer for that feature

      Send **warnings** (SV05 numbers, SV06 scope, unmapped UI fields) to the owning agent once, together with the blockers. Report any warnings that remain to the user. They do not block the gate.

      Allow at most 2 rounds, then escalate to the user with the remaining failures.
   3. Run `python tools/gate.py specs-exist`. Stop and report if it fails.
8. **Report.** Show the user:
   - usage for this phase: `python tools/usage.py --by agent`
   - the spec set: the path `P/02-spec/index.md` and one line per Markdown document
   - the features (ID and title)
   - the open items per feature
   - the next step, `/plan-features`
