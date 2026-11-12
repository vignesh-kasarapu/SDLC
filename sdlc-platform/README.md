# Agentic SDLC Platform

This platform runs inside Claude Code. It takes a client requirements document and produces a tested, deployment-ready application. You drive it with slash commands in the Claude Code CLI; it is designed to run on a Claude Pro subscription. The full design is in [the roadmap](agentic_software_development_platform_4_phase_roadmap.md).

## Folder layout
```
<workspace>/
├── sdlc-platform/      this folder: the platform. Share only this. Open Claude Code here.
├── projects/           client project data (CRD, FRD, specs, build logs), one folder per project. Never shared.
└── app-development/    generated application repos, one per project, created at FRD approval.
```
The tools create `../projects/` and `../app-development/` next to this folder on first use. To put them
somewhere else, set the `SDLC_WORKSPACE` environment variable to the folder that should contain them.

## Sharing the platform
Share the `sdlc-platform/` folder only (as a git repository or a zip). It contains no client data.
The recipient puts it in any folder, runs `pip install -r requirements.txt` and opens Claude Code in it.

## Prerequisites
- Claude Code, signed in with your own Claude subscription (Pro or higher)
- Python 3.10+ and git
- Optional, for better PDF input: `pip install pdfplumber` (PDF tables) and `pytesseract` (OCR of scanned pages)
- To build and run the generated apps: Node 18+; Docker is optional

## Setup (once)
```
cd <workspace>/sdlc-platform
pip install -r requirements.txt
python -m pytest              # all tests should pass
claude                        # or open this folder in VS Code with the Claude Code extension
```
Always open Claude Code **in `sdlc-platform/`**. The slash commands and agents only load from here.

## How to run a project

### 1. Create the project
```
/new-project recruitment-portal
```
This creates `../projects/recruitment-portal/` and makes it the active project. Switch between projects with `python tools/state.py use <id>`.

### 2. Put the client's inputs in place
Copy everything the client gave you into the project's **input folder**:
```
<workspace>/projects/recruitment-portal/input/
├── Recruiting_Portal_FRD.docx     requirements: CRD or FRD (DOCX, PDF, MD, TXT)
├── field-list.xlsx                 spreadsheets: data fields, requirement matrices (XLSX, CSV)
└── wireframes/                     the client's screens, if any:
    ├── job-form.html                 HTML mockups
    ├── candidate-list.png            screenshots, sketches, photos of whiteboards (PNG, JPG, …)
    └── old-system.pdf                scanned or exported screen PDFs
```
- Subfolders are fine. Wireframes embedded **inside** the DOCX or PDF are found automatically.
- Supported formats: DOCX, PDF, XLSX, CSV/TSV, HTML, PNG/JPG/GIF/WEBP/BMP/TIFF, MD, TXT. Save legacy `.doc` files as `.docx`.
- You can also point `/ingest-crd` at files anywhere on disk; it copies them into `input/`.

### 3. Requirements (Phase 1)
```
/ingest-crd ../projects/recruitment-portal/input
/generate-frd
/revise-frd "Q-001: max 10 open requisitions per recruiter; Q-002: HR approves offers"
/approve-frd "Your Name"
```
- **`/ingest-crd`** parses every file into numbered blocks (`[C-001]`…). Images, wireframes and scanned pages are read by the **visual-analyst** agent, using Claude vision.
- **Document type.** It also tells you whether the input is a raw requirements document (**CRD**: the platform writes the FRD) or already an **FRD** (**intake mode**: the client's wording is kept, never rewritten). Override with `/ingest-crd <path> --as frd` or `--as crd`.
- **`/generate-frd`** asks you two things along the way: the **tech stack**, and which **recommended features** to include. It then writes and evaluates the FRD.
- **Open questions.** Answer them with `/revise-frd "<answers>"`. Every proposed change is shown to you to accept or reject before the FRD changes.
- **`/approve-frd`** locks the FRD and creates the app repository in `../app-development/<id>/`.

### 4. Wireframes
```
/generate-wireframes
/generate-wireframes "Job form: add a salary band field; merge the two approval screens"
/approve-wireframes "Your Name"
```
- **If the client's input had wireframes**, you can confirm them as they are.
- **Otherwise you're asked** whether to create them (recommended), wait for the client, or skip (with a reason).
- **Generated wireframes** go to `../projects/<id>/01b-wireframes/v1/`. Open **`index.html` in your browser** to click through the screens. Request changes with `/generate-wireframes "<changes>"` (at most 3 rounds), then approve.
- **Wireframes arriving after FRD approval:** put them in `../projects/<id>/input/wireframes-late/` and run `/generate-wireframes ../projects/<id>/input/wireframes-late`. The designer uses them as the basis for the review set.

### 5. Specifications (Phase 2)
```
/generate-specs
/plan-features
/approve-specs "Your Name"
```
- **Where to start reading:** `../projects/<id>/02-spec/index.md` links every spec document and each feature's spec.

### 6. Build and deliver (Phases 3 and 4)
```
/build-feature next           # one feature at a time (recommended for the first one)
/build-all                    # or all remaining features
/qa-system
/release "Your Name"
```
- The code is in `../app-development/<id>/`. Each feature is built on its own `feature/F-nnn-…` branch and merged into `develop` when its tests pass.

### Anytime
| Command | What it does |
|---|---|
| `/status` | Where the project is, and the next command to run |
| `/trace FR-007` | Follows a requirement from the client text to features, specs, code and tests |
| `/checklist` | The domain checklist for the current FRD |
| `python tools/usage.py` | Time and estimated tokens per agent and phase |

### Working on an existing application
Run `/import-existing <app folder or git URL>` right after `/new-project`, then continue with step 2. The input documents describe the **changes** you want.

## Where to find things
| What | Where |
|---|---|
| Client inputs (copies) | `../projects/<id>/input/` |
| Parsed input with block IDs | `../projects/<id>/01-frd/crd.md` |
| FRD, evaluation, checklist | `../projects/<id>/01-frd/frd.vN.md`, `eval.vN.json`, `checklist.vN.md` |
| Recommended features | `../projects/<id>/01-frd/feature-recommendations.md` |
| Wireframes | `../projects/<id>/01b-wireframes/vN/index.html` |
| Specifications | `../projects/<id>/02-spec/index.md` |
| Build reports, defects, agent log | `../projects/<id>/03-build/` |
| QA reports, docs, deployment package | `../projects/<id>/04-delivery/` |
| The application code | `../app-development/<id>/` (its own git repository) |

## Try it on the sample
```
/new-project leave-demo
/ingest-crd samples/leave_crd.md
/generate-frd
```

## Input and FRD intake mode
- `/ingest-crd` takes one or more files or a whole folder: DOCX (including embedded wireframe images), PDF, XLSX, CSV, HTML wireframes, images and MD/TXT. With `pdfplumber` installed, PDF tables come out as tables. Scanned pages and images are read by the **visual-analyst** agent (Claude vision) and become citable blocks.
- If the client's document is **already an FRD**, the platform detects it and runs **intake mode**. It keeps the client's document verbatim, extracts requirements that quote the client's wording, evaluates the result, and asks gap questions. It adds only a compact addendum (stack, standards, accepted additions) and never rewrites the document. Override the detection with `--as frd` or `--as crd`.

## Wireframes (after FRD approval, before specs)
`/generate-wireframes` checks whether the client's input already contains wireframes (HTML mockups or screen images).
- **Client wireframes found:** you confirm them.
- **None found:** it asks whether to create them. The **wireframe-designer** agent then drafts one self-contained, low-fidelity HTML page per screen, annotated with requirement IDs. Open `index.html` in a browser to click through.
- **Review:** give feedback with `/generate-wireframes "<changes>"` (at most 3 rounds), then `/approve-wireframes`.
- **Skipping:** allowed, with a reason, for example for an API-only system.

`/generate-specs`, and therefore development, starts only after this step. The feature breakdown, UI spec and frontend developer build on the approved screens.

## Specification quality (Phase 2)
`tools/spec_docs.py check` (run by the `specs-exist` gate) applies rule-based checks on top of the agents' work:

| Code | Rule |
|---|---|
| SV01 | Unknown requirement, CRD block, feature or screen ID |
| SV02 | A business rule without a requirement ID, or an assigned requirement the spec never addresses |
| SV03 | TBD, TODO or placeholder text (use `OPEN:` items instead) |
| SV04 | A technology outside the chosen stack (`config/tech-catalog.yaml`) |
| SV05 | A number that appears nowhere in the client input or FRD (warning) |
| SV06 | Cites an out-of-scope (`wont`) requirement, or restates an out-of-scope item as an obligation (warning) |
| SV07 | Acceptance criteria: `AC-Fnnn-nn` IDs, Given/When/Then form, linked requirements, every FR and BR covered |
| SV08 | Every acceptance criterion has a test case |
| SV09 | Database, API and UI disagree: entity without a table, API field without a column, UI field mapped to an unknown API field |
| SV10 | Existing apps: re-creates a table, endpoint, file or class that already exists |
| SV11 | A feature screen that is not one of the approved wireframes (warning) |

Each feature-spec writer reads only its own slice (`02-spec/slices/F-nnn.md`), not the whole FRD. An interrupted run resumes with only the missing or failing specs (`spec_docs.py pending`).

## Existing applications
`/import-existing <folder or git URL>` copies the app into `../app-development/<id>/` and records its stack, routes, tables and classes in `00-discovery/project-facts.md`. FRD approval then does not scaffold over it, and rule SV10 makes the specs modify the existing code instead of re-creating it. The architecture pattern can be MVC (default), MVT, `framework-native` or `existing`; the user chooses it in `/set-tech-stack`.

## Usage tracking
Each agent run is logged with its model, its duration and the estimated tokens it read and wrote. `python tools/usage.py` (or `--by phase`, `--by key`) shows where your Claude Pro usage goes.

## Full lifecycle
| Phase | Commands | Output |
|---|---|---|
| 1. Requirements | `/ingest-crd`, `/generate-frd`, `/evaluate-frd`, `/revise-frd`, `/approve-frd` | `01-frd/frd.vN.md` (approved, locked) |
| 1b. Wireframes | `/generate-wireframes`, `/approve-wireframes` | `01b-wireframes/vN/`: one low-fidelity HTML screen per task, a clickable `index.html`, approved and locked |
| 2. Specification | `/generate-specs`, `/plan-features`, `/approve-specs` | `02-spec/`: separate Markdown specs (`index.md`, `architecture.md`, `coding-standards.md`, `features.md`, `database.md`, `api-spec.md`, `ui-spec.md`, `features/F-nnn.md`), plus `openapi.yaml`, `schema.sql`, DAG and plan |
| 3. Build | `/build-feature next`, `/build-all` | `../app-development/<id>/`, with feature commits, test reports and NFR reviews |
| 4. Delivery | `/qa-system`, `/release` | `04-delivery/`: QA gate, reports, docs, deployment package |

`/status` shows where you are and what to run next. `/trace FR-007` follows a requirement through the whole chain.

## How it is built
- **Orchestrator:** the slash command running in your main Claude session.
- **Specialist agents:** 31 subagents in `.claude/agents/`, each with a contract: inputs, output schema, allowed tools and completion check.
- **Deterministic engine:** `tools/`, made up of:
  - input parsing (`parse_doc.py`) and FRD intake mode (`frd_intake.py`)
  - the state machine (`state.py`), gates (`gate.py`) and approvals (`approve.py`)
  - the domain checklist (`checklist.py`)
  - wireframes (`wireframes.py`)
  - spec documents, rules and slices (`spec_docs.py`, `spec_rules.py`, `spec_slice.py`)
  - the dependency graph (`dag.py`) and traceability (`traceability.py`)
  - the app scaffold (`scaffold.py`) and existing-app discovery (`discover.py`)
  - file ownership (`ownership.py`) and MVC layers (`layer_check.py`)
  - the final QA gate (`qa_gate.py`), usage reports (`usage.py`) and packaging (`package.py`)

  The LLM never decides phase transitions.
- **Safety:** a `PreToolUse` hook (`tools/lock_guard.py`) blocks edits to approved artifacts and to state and approval files. Generated code lives in its own git repository under `../app-development/<id>/`. Nothing is ever deployed or pushed.

## Tech stack and MVC
- **Your choice of stack.** `/generate-frd` asks you to choose the backend, frontend, database and deployment target. You can change them later with `/set-tech-stack`, as long as the FRD isn't approved yet. The choice is written into FRD section 19 and binds the architect.
- **MVC is the default.** Unless you choose another pattern in `/set-tech-stack` (`MVT`, `framework-native` or `existing`, with a reason), every generated app uses Controller → Service → Repository → Model on the backend, and views, components, frontend controllers and frontend services on the frontend. The folder structure and programming standards come from [knowledge/standards/mvc-coding-standards.md](knowledge/standards/mvc-coding-standards.md), and appear in FRD section 20.
- **Enforcement.** `tools/layer_check.py` blocks imports that go the wrong way between layers, linting runs in every build, and the NFR reviewer checks the standards.

## Model routing
Models are configured in `config/models.yaml`.

| Model | Agents |
|---|---|
| Opus | frd-evaluator, architect, nfr-reviewer, security-auditor |
| Haiku | doc-normalizer, fix-triager, perf-tester, traceability-auditor, doc-writer |
| Sonnet | All other agents, including every code writer |

If your plan has no Opus access, or you want to save Pro usage, run `/models fallback` and restart Claude Code.

## Tests
```
python -m pytest
```
To share the platform as a clean zip (no caches, no client data): `python tools/package.py`.
