---
name: approve-specs
description: HUMAN ACTION - approve the technical baseline (architecture, contracts, feature specs, execution plan). Locks Phase 2 artifacts, loads features into the state machine. (The app repository already exists: it is created at FRD approval.)
argument-hint: "[approver name] [comment]"
disable-model-invocation: true
---
The user is approving the technical baseline. Arguments: `$ARGUMENTS`. `P = ../projects/<id>`.

1. Run `python tools/gate.py plan-valid`. If it fails, show the failures and stop.
2. Summarise for the user:
   - the stack
   - the number of features and waves
   - the total number of `OPEN` items across feature specs; these are resolved by the SME agent, or escalated, in Phase 3
3. Determine the approver name, or ask for it. Then run:
   `python tools/approve.py specs --by "<name>" --decision approved --comment "<comment>"`
   If the user wants to reject instead, run the same command with `--decision rejected`, then ask what should change and re-run `/generate-specs` after the fixes.
4. Once approved, run:
   - `python tools/state.py load-plan`
   - if `../app-development/<id>/.git` is missing (a project approved before this rule), run `python tools/scaffold.py init`
   - `python tools/gate.py build-ready`
5. Report:
   - the features that are Ready now (`python tools/state.py features`)
   - the next step: `/build-feature next` for one feature at a time, recommended for the first feature, or `/build-all`
