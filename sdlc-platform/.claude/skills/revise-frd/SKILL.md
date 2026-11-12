---
name: revise-frd
description: Phase 1 - create a new FRD version from reviewer feedback and/or client answers to open questions, then re-evaluate.
argument-hint: "<feedback or answers, e.g. Q-003: carry forward max 10 days; REVIEW: add half-day leave>"
disable-model-invocation: true
---
Revise the FRD using this feedback: `$ARGUMENTS`. `P = ../projects/<id>`.

1. Run `python tools/gate.py frd-exists`. Stop if it fails.
2. If the FRD is already approved (`P/01-frd/approval.json` has decision approved), warn the user:
   - A revision creates a new version that needs re-approval.
   - It also invalidates any Phase 2 work that was built on the old version.

   Ask them to confirm before continuing.
3. If `$ARGUMENTS` is empty, check for `P/01-frd/reviewer-feedback.md` and use it. If neither exists, ask the user what to change and stop.
4. Record the feedback:
   - Append the free-text feedback to `P/01-frd/reviewer-feedback.md` under a new `## REVIEW-n (<date>)` heading. Number it after the existing headings.
   - Keep answers to open questions (`Q-nnn: …`) verbatim in the same entry.
5. **Propose, review, apply.** Read `.claude/skills/review-frd-changes/SKILL.md` and carry out its steps. Pass this instruction to the plan: `Apply reviewer feedback REVIEW-n from 01-frd/reviewer-feedback.md (answered open questions: set resolution and update/add requirements with source REVIEW-n). Also address open issues in eval.vN.json and checklist.vN.json.`
   The user sees every proposed change, with before and after text, and chooses which ones to apply. Nothing is rewritten without that choice.
6. Read `.claude/skills/evaluate-frd/SKILL.md` and carry out its steps.
7. Report the new version, what changed (from section 1 of the FRD) and the gate result.
