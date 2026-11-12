---
name: reject-frd
description: HUMAN ACTION - reject the latest FRD version with reviewer feedback that drives the next revision.
argument-hint: "<approver name> <reason / feedback>"
disable-model-invocation: true
---
The user is rejecting the FRD. Arguments: `$ARGUMENTS`

1. If no reason was given, ask the user for one. Rejection feedback drives the next revision.
2. Run:
   `python tools/approve.py frd --by "<name>" --decision rejected --comment "<feedback>"`
   This appends the feedback as `REVIEW-n` to `01-frd/reviewer-feedback.md`.
3. Ask the user whether to run `/revise-frd` now, which applies the feedback and re-evaluates.
