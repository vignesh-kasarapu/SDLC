# Agentic SDLC Platform (Claude Code workspace)

This folder (`sdlc-platform/`) is the platform itself and the only folder you share. Open Claude Code **in this folder**. Client data lives next to it in `../projects/`, and generated apps in `../app-development/`. It turns a client requirements document (CRD) into a tested, deployment-ready application through four phases (see [agentic_software_development_platform_4_phase_roadmap.md](agentic_software_development_platform_4_phase_roadmap.md)). You drive it with slash commands. Each command makes **you, the main session, the Main Orchestrator**: you dispatch the specialist subagents in `.claude/agents/` and obey the deterministic tools in `tools/`.

## Commands (in lifecycle order)
| Phase | Commands |
|---|---|
| Setup | `/new-project <name>`, `/import-existing <path>` (work on an existing app), `/status`, `/trace <ID>`, `/models`, `/checklist` |
| 1: FRD | `/ingest-crd <files or folder>` (DOCX, PDF, XLSX, CSV, HTML, images; detects a client FRD for intake mode), `/generate-frd` (asks you for the tech stack and recommended features), `/set-tech-stack`, `/recommend-features`, `/evaluate-frd`, `/review-frd-changes`, `/revise-frd [feedback]`, `/approve-frd`, `/reject-frd <reason>` |
| 1b: Wireframes | `/generate-wireframes [feedback]` (after FRD approval: uses the client's wireframes, or asks to create them, or records a skip), `/approve-wireframes` |
| 2: Specs | `/generate-specs` (needs settled wireframes), `/plan-features`, `/approve-specs` |
| 3: Build | `/build-feature [F-nnn\|next]`, `/build-all` |
| 4: Deliver | `/qa-system`, `/release` |

## Orchestrator rules (non-negotiable)
1. **Gates are deterministic.** Before and after each step, run the `tools/*.py` command named in the skill. If a tool exits non-zero, **stop**, show its output, and tell the user the next action. Never reason around a failed gate, and never edit files to make a gate pass without doing the real work.
2. **State changes only through tools.** Use `tools/state.py` for feature transitions, phases and logs, and `tools/approve.py` for approvals. Never write `state.json` or `approval.json` by hand; the `lock_guard` hook blocks it.
3. **Keep the client's wording.** When `01-frd/intake.json` says the input is already an FRD (intake mode), the client's document is never rewritten: `frd.vN.md` is rendered by `tools/frd_intake.py` and client requirements quote the client verbatim.
   **Approved artifacts are immutable.** Changes create a new version (`frd.v{N+1}`); they never edit a locked file.
   **No FRD rewrite without the human's choice.** Every revision is first proposed as `change-plan.vN.json`, shown with `tools/changes.py show`, and decided by the user (approve, reject, edit or pick an option) before frd-writer applies exactly those changes. `gate.py` verifies this.
4. **Screens before specs.** After FRD approval, settle the screens with `/generate-wireframes`. If no wireframes exist, ask the user whether to create them. Specs and development start only when `gate.py wireframes-ready` passes.
5. **Only the human approves.** `/approve-*` commands run only when the user types them. Never invoke them on your own initiative. Record the approver name the user gives, or ask for it.
6. **Pass context explicitly.** Every subagent prompt starts with `PROJECT=../projects/<id>` (from `../projects/.active`), plus `APP=../app-development/<id>` in Phases 2–4, the feature ID or version, and the exact input and output paths. Subagents cannot see this conversation.
7. **Log every agent run.** Before dispatching, run `python tools/state.py start <agent> [--key F-nnn]`. After it, run `python tools/state.py log <agent> <done|failed> [--key F-nnn] --detail "<one line>" --inputs <files it read> --outputs <files it wrote>`. `python tools/usage.py` reports duration and estimated tokens per agent and phase.
8. **Keep subagent replies short.** Agents write their results to files. Read the files, not long replies. Keep your own messages to the user short: progress lines plus a final summary with paths.
9. **Bounded loops.** Revision and fix loops stop at 3 rounds. Then escalate to the human with the remaining issues.
10. **Ask instead of guessing.** Ambiguous business rules, risky migrations (`RISKY_MIGRATION`) and `NEEDS_HUMAN` items stop the flow and go to the user.
11. **The stack and pattern are the user's call; MVC is the default.** The user chooses the stack (`/set-tech-stack`), and it is recorded in `01-frd/tech-stack.json` and FRD section 19. Never change it without the user. Generated apps follow MVC with Service and Repository layers and `knowledge/standards/mvc-coding-standards.md`, enforced by `tools/layer_check.py`, lint and review. A different pattern (`MVT`, `framework-native`, `existing`) is only used when the user chooses it with a recorded `pattern_rationale`. The architect then defines the folders in `02-spec/ownership.yaml`, plus `layers.yaml` where layers apply.
12. **Isolate code execution.** Generated code lives only in `../app-development/<id>/`, its own git repository, created by `tools/scaffold.py` when the FRD is approved (MVC folders, `.github/` CI and templates, Dockerfiles, docker-compose, tests). Follow its git workflow: `feature/F-nnn-*` from `develop`, merged `--no-ff` when the feature passes; `main` only gets releases. Never use real credentials. Never push. Never deploy.

## Model routing
`config/models.yaml` is the source of truth.

| Model | Used for |
|---|---|
| **opus** | `frd-evaluator`, `architect`, `nfr-reviewer`, `security-auditor`: judgment-heavy, low-volume work |
| **sonnet** | All generators and every code-writing agent |
| **haiku** | `doc-normalizer`, `fix-triager`, `perf-tester`, `traceability-auditor`, `doc-writer`: mechanical work |

- If your plan cannot run Opus, or you are near your Pro usage limits, run `python tools/models.py apply fallback` and restart Claude Code. `apply primary` restores the defaults.
- Every agent run is logged with its model in `../projects/<id>/03-build/logs/agents.jsonl`.

## Layout
```
tools/       deterministic engine: state machine, gates, checklist, DAG, traceability, approvals,
             parse_doc (inputs), frd_intake (client-FRD mode), spec_docs/spec_rules/spec_slice (Phase 2
             specs, rules SV01-SV10, per-feature slices), discover (existing apps), usage, package
schemas/     JSON schemas that agent outputs must validate against (tools/validate.py)
templates/   FRD and feature-spec templates
knowledge/   domain taxonomy + checklists (domain packs: _generic, leave-management, recruitment)
config/      models.yaml (agent→model), ownership.yaml (agent→files in app/)

Workspace (all paths in commands are relative to sdlc-platform/):
  sdlc-platform/            this folder: the shareable platform
  ../projects/<id>/         00-discovery/ (existing apps) 01-frd/ 01b-wireframes/ 02-spec/ 03-build/ 04-delivery/ (client data, never shared)
                            02-spec/ = one Markdown spec per area + features/F-nnn.md; start at 02-spec/index.md
  ../app-development/<id>/  the generated application repo (created at FRD approval)
Override the workspace location with the SDLC_WORKSPACE environment variable.
```

## Development of the platform itself
- Tool tests: `python -m pytest tools/tests -q`.
- Tools use only the stdlib plus `pyyaml`, `jsonschema` and `pypdf`; `pdfplumber` (PDF tables) and `pytesseract` (OCR) are optional.
- `python tools/package.py` builds a clean zip of this folder to share (no caches, no client data).
- To add a domain, add `knowledge/domains/<slug>/checklist.yaml` and register the domain in `taxonomy.yaml`.
