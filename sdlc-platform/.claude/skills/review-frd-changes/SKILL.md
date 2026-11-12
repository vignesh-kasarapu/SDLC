---
name: review-frd-changes
description: Phase 1 - before any FRD rewrite, propose the changes, show them to the human with before/after text, and let them approve, reject, edit or pick an option for each. Used by /evaluate-frd and /revise-frd; run it directly to review a pending plan again.
argument-hint: "[your name]"
disable-model-invocation: true
---
Review the proposed FRD changes with the user. `P = ../projects/<id>`. Arguments: `$ARGUMENTS`.

Let N be the latest FRD version (highest `frd.vN.json`), and `T = N + 1`, the version to be written.

## 1. Propose (skip if `P/01-frd/change-plan.vT.json` already exists)
Dispatch **frd-writer**:
`PROJECT=P. MODE=plan. Target version T. Propose changes from eval.vN.json, checklist.vN.json, reviewer-feedback.md, feature-recommendations.json and these instructions: <feedback text, if any>. Write 01-frd/change-plan.vT.json only.`
Log it.

## 2. Display
Run `python tools/changes.py show --target T` and show the output to the user as it is. It lists every change with its severity, before and after text, reason and options. Then add a one-line overview: "n changes: x blocker, y major, z minor/feedback".

## 3. Ask (never apply anything without an answer)
Use the AskUserQuestion tool. Every pending change must get a decision.

1. **Changes with `options`** (policy choices). Ask one single-select question per change, with up to 4 questions per call:
   - question: `CH-nnn: <summary>. Which option?`
   - options: each entry in `options`, plus "Reject this change"

   The user can type their own value under "Other"; record it as an edit.
2. **All other pending changes.** Ask multiSelect questions grouped by severity, blocker first, with up to 4 changes per question and 4 questions per call. Repeat until every change has been offered.
   - question: `Which <severity> changes should be applied?`
   - option label: `CH-nnn <short summary>`; description: `<action> <req ids>: <after text, shortened>`

   Explain once, in the first question's text:
   - selected changes are applied
   - unselected ones are rejected
   - typing `CH-nnn: <instruction>` under "Other" applies the change with your adjustment
3. Before recording, show a 3-line confirmation: apply, reject, edited. If the user rejects a **blocker**, warn them that the FRD quality gate will probably still fail, then accept their choice.

## 4. Record
Use the approver name from `$ARGUMENTS`, or ask for it. Run `python tools/changes.py decide --target T --by "<name>"` with the matching flags:
- `--approve CH-001,CH-004`
- `--reject CH-002`
- `--option CH-003="<chosen option>"`
- `--edit CH-005="<user instruction>"`

Then run `python tools/changes.py status --target T`. It must report ALL DECIDED; if anything is still pending, ask about it.

## 5. Apply
Dispatch **frd-writer**:
`PROJECT=P. MODE=revise. Target version T. Intake mode: <yes|no>. Apply ONLY the approved/edited changes in 01-frd/change-plan.vT.json; record them in change_log.`
Log it. In intake mode (`python tools/frd_intake.py mode` prints `frd`), frd-writer writes only `frd.vT.json`. Run `python tools/frd_intake.py build --version T` to render `frd.vT.md`, and stop on failure. Then return to the calling command, which re-evaluates the new version.
