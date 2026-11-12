---
name: generate-frd
description: Phase 1 - generate the domain-validated FRD from the ingested CRD (domain identification, business context, requirement extraction, FRD writing), then run evaluation and the revision loop.
disable-model-invocation: true
---
Generate the Functional Requirements Document for the active project. You are the orchestrator: follow CLAUDE.md. `P` means `../projects/<id>`, taken from `../projects/.active`.

## 1. Gate
Run `python tools/gate.py crd-parsed`. Stop if it fails.

If `P/01-frd/frd.v1.json` already exists, ask the user whether to regenerate from scratch (which overwrites v1, and is only allowed if the FRD is not approved) or to use `/revise-frd`. Then stop.

## 2. Domain and context
Run these two **sequentially**, because context needs the domain:
1. Dispatch **domain-identifier**: `PROJECT=P. Identify domain/subdomain from 01-frd/crd.md + crd-outline.md; write 01-frd/domain.json.`
2. Dispatch **business-context**: `PROJECT=P. Write 01-frd/context.json.`

Log each agent with `tools/state.py log`.

If `domain.json` has `confidence` below 0.6, or `known_domain_pack` is false, tell the user. Ask them to confirm the domain, or to continue with generic checks only. Wait for their answer.

## 2b. Technology stack (ask the user)
If `P/01-frd/tech-stack.json` does not exist yet:
1. Read `.claude/skills/set-tech-stack/SKILL.md` and carry out its steps. This asks the user to choose the frontend, backend, database and deployment target. MVC is mandatory.
2. Wait for the answers, then run `python tools/gate.py tech-stack`. Stop if it fails.

## 3. Requirements
Run `python tools/frd_intake.py mode`. It prints `frd` (**intake mode**: the client supplied an FRD) or `crd`.

Dispatch **requirements-extractor**: `PROJECT=P. MODE=<intake if mode is frd, otherwise normal>. Write 01-frd/requirements.json.` Log it.

## 3b. Recommended features (ask the user)
Read `.claude/skills/recommend-features/SKILL.md` and carry out steps 2–3. The user decides which domain-recommended features go into the FRD before anything is evaluated.

## 4. FRD v1
**Intake mode** (`frd`): do not rewrite the client's document.
1. Dispatch **frd-writer**: `PROJECT=P. MODE=intake. Target version N=1. Write 01-frd/frd.v1.json only (requirements.json plus accepted SUG items, USER-STACK NFRs, checklist defaults and gap questions).` Log it.
2. Run `python tools/frd_intake.py build --version 1`. It renders `frd.v1.md` as the client's text plus the addendum, and checks that every client requirement quotes the client. If the check fails, send the errors back to frd-writer (or requirements-extractor for statements), at most 2 rounds.

**Full mode** (`crd`): dispatch **frd-writer**: `PROJECT=P. MODE=create. Target version N=1. Write 01-frd/frd.v1.json and 01-frd/frd.v1.md (all 20 sections; sections 19-20 come from 01-frd/tech-stack.json and knowledge/standards/mvc-coding-standards.md; include the accepted features from 01-frd/feature-recommendations.json).` Log it.

## 5. Evaluate and revise
Read `.claude/skills/evaluate-frd/SKILL.md` and carry out its steps in full, including the bounded revision loop.

## 6. Report
In at most 15 lines, show the user:
- the domain and subdomain
- the chosen tech stack, in one line, with the MVC pattern
- the requirement counts
- the feature recommendations: accepted, rejected and sent to the client
- the checklist result, with the paths `P/01-frd/checklist.vN.md` and `P/01-frd/feature-recommendations.md`
- the open questions; list the blocking ones in full, because the client must answer them
- the gate result
- the next step: `/approve-frd` if the gate passed, or `/revise-frd "<answers/feedback>"` if it did not
