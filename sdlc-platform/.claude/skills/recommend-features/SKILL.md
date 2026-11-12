---
name: recommend-features
description: Phase 1 - recommend features the domain usually needs but the CRD did not ask for, and let the user accept, reject or send each one to the client. Runs automatically inside /generate-frd before evaluation; run it directly to review recommendations for an existing FRD.
argument-hint: "[your name]"
disable-model-invocation: true
---
Recommend features for the active project. Arguments: `$ARGUMENTS`. `P = ../projects/<id>`.

## 1. Preconditions
- Run `python tools/gate.py crd-parsed`. Stop if it fails.
- `P/01-frd/requirements.json` must exist. If not, tell the user to run `/generate-frd` first, then stop.
- If the FRD is already approved (`P/01-frd/approval.json` decision approved), warn that accepting features needs a new FRD version and a re-approval. Ask whether to continue.

## 2. Recommend
Dispatch **feature-advisor**: `PROJECT=P. Write 01-frd/feature-recommendations.json and .md.` Log it with `python tools/state.py log feature-advisor done --detail "<counts>"`.

## 3. Let the user decide
1. Show the user the covered capabilities, one line each, so they see what is already in scope.
2. For the recommendations with `decision: "pending"`, ask with the AskUserQuestion tool. Group them by importance (essential first), up to 4 options per question and up to 4 questions per call; use more calls if needed.
   - Use `multiSelect: true`. Question text: "Which of these <importance> features should the FRD include?"
   - Each option's label is `SUG-nnn <title>` (shortened if needed), and its description is the rationale plus the basis ("from domain checklist" or "AI suggestion").
   - Tell the user that anything they don't select is rejected, and that they can type "ask client: SUG-nnn, ..." under Other to turn items into open questions for the client instead.
3. Record the decisions in `P/01-frd/feature-recommendations.json`:
   - selected: `accepted`
   - named under "ask client": `ask_client`
   - not selected: `rejected`

   Set `decided_by` to the name in `$ARGUMENTS`, or ask for it. Leave everything else unchanged.
4. Run `python tools/validate.py feature-recommendations P/01-frd/feature-recommendations.json`.

## 4. Next step
- Inside `/generate-frd`: return and continue with FRD writing. The frd-writer turns accepted features into requirements.
- Run on its own with an FRD already present: tell the user to run `/revise-frd "feature recommendations decided"`, which creates a new version with the accepted features and re-evaluates it.

Finish with one line: `accepted n, rejected n, ask client n`, and the path `P/01-frd/feature-recommendations.md`.
