---
name: generate-wireframes
description: After FRD approval, before specs - check whether wireframes exist; if not, ask the user whether to create them, then generate low-fidelity HTML wireframes (one per screen) for review. With feedback text, revise the latest unapproved version (max 3 rounds).
argument-hint: "[feedback on the current wireframes | path to client sketches]"
disable-model-invocation: true
---
Settle the screens for the active project before specs and development start. Arguments: `$ARGUMENTS`. `P = ../projects/<id>`. Follow CLAUDE.md.

## 1. Gate and status
1. Run `python tools/gate.py frd-approved`. Stop if it fails: wireframes come after FRD approval.
2. Run `python tools/wireframes.py status` and read its `NEXT:` line.

## 2. Decide (only if the status shows `decision: none`)
Ask the user with **one** AskUserQuestion call. Start the question with what the status found, e.g. "The approved input contains no wireframes." or "The client supplied 4 wireframe screens."

| Option | When to offer |
|---|---|
| **Create wireframes now (Recommended)** | always. The wireframe-designer drafts one low-fidelity HTML screen per task; you review and approve them before specs. |
| **Use the client's wireframes** | only if the status found client wireframes. They are already part of the approved FRD. |
| **The client will send wireframes** | always. Stop now; when they arrive, run `/generate-wireframes <folder>` to turn them into the reviewed set. |
| **Skip wireframes** | always. For example, an API-only or back-office system. Ask for the reason. |

Record the answer, using the approver name the user gives (or ask for it):
- create: `python tools/wireframes.py decide generate --by "<name>"`
- client's: `python tools/wireframes.py decide provided --by "<name>"`. Then go to step 5.
- skip: `python tools/wireframes.py decide skip --by "<name>" --reason "<reason>"`. Then go to step 5.
- client will send: record nothing. Tell the user the next step and stop.

## 3. Generate or revise
- **No version yet:**
  1. Run `python tools/wireframes.py new-version`. It creates `v1`.
  2. Run `python tools/state.py start wireframe-designer`.
  3. Dispatch **wireframe-designer**: `PROJECT=P. Version folder: 01b-wireframes/v1/. Approved FRD: 01-frd/frd.vN.json. Reference sketches: <$ARGUMENTS if it is a path, else the client ui_screen images, if any>. Write the screens, screens.json, index.html and wireframes.md.`
- **`$ARGUMENTS` is feedback, and the latest version is not approved:**
  1. Run `python tools/wireframes.py feedback "$ARGUMENTS" --by "<name>"`. If it prints `ESCALATE` (more than 3 rounds), show the user the remaining points and stop.
  2. Run `python tools/state.py start wireframe-designer`.
  3. Dispatch **wireframe-designer**: `PROJECT=P. REVISION. Version folder: 01b-wireframes/vN/. Apply the latest WF-REVIEW in 01b-wireframes/feedback.md; change nothing else.`
- **The latest version is already approved and the user wants changes:**
  1. Run `python tools/wireframes.py new-version`.
  2. Record the feedback as above.
  3. Revise the new version. It needs a new approval.

Then:
1. Run `python tools/state.py log wireframe-designer done --detail "<screens>" --outputs P/01b-wireframes/vN`.
2. Run `python tools/gate.py wireframes-check`. If it fails, send the findings back to the wireframe-designer once, then stop and report.

## 4. Review
Show the user:
- the screen table from `P/01b-wireframes/vN/wireframes.md`: screen, roles, requirements
- the open questions
- how to view the wireframes: open `P/01b-wireframes/vN/index.html` in a browser. It is a clickable prototype.
- the choices:
  - `/approve-wireframes "<your name>"` to accept them
  - `/generate-wireframes "<what to change>"` for another round, at most 3

## 5. Next step
Run `python tools/gate.py wireframes-ready`. If it passes, the next step is `/generate-specs`.
