---
name: evaluate-frd
description: Phase 1 - evaluate the latest FRD version (rule-based domain checklist + independent Opus evaluator), apply the quality gate, and auto-revise up to 3 rounds.
disable-model-invocation: true
---
Evaluate the latest FRD for the active project. `P = ../projects/<id>`. Follow CLAUDE.md.

## Loop
Repeat this loop at most 3 times. Let `N` be the latest version: the highest `frd.vN.json`.

1. Run `python tools/gate.py frd-exists`. Stop if it fails.
2. **Checklist (deterministic).** Run `python tools/checklist.py --version N`. A non-zero exit is expected when mandatory items fail; continue, because the evaluator must see the result.
3. **Traceability.** Run `python tools/traceability.py frd --version N`.
4. **Independent evaluation.** Dispatch **frd-evaluator** with:
   `PROJECT=P. Evaluate FRD version N: 01-frd/frd.vN.md + frd.vN.json against 01-frd/crd.md. Checklist results: 01-frd/checklist.vN.json. Write 01-frd/eval.vN.json.`
   Log it.
5. **Gate.** Run `python tools/state.py phase frd evaluated`, then `python tools/gate.py frd-quality`.
   - **Passed:** run `python tools/state.py phase frd passed` and exit the loop.
   - **Failed:** decide whether an automatic revision can fix the failures:
     - **Can fix** (missing coverage, unclear or untestable wording, missing acceptance criteria, wrong sources): show the user the gate failures, then read `.claude/skills/review-frd-changes/SKILL.md` and carry out its steps. The user sees every proposed change and chooses which to apply before anything is rewritten. Then repeat the loop.
       If the user rejects every change, exit the loop and report the gate failures.
     - **Cannot fix** (blocking open questions only the client can answer, contradictions in the CRD itself, a domain or policy decision): exit the loop and escalate.

## After the loop
- If the gate still fails after 3 rounds, or failed on a cannot-fix item, report the remaining gate failures and the blocking questions. The user answers them with `/revise-frd "<answers>"`.
- Show a compact scorecard:
  - the 8 dimension scores
  - issue counts by severity
  - checklist mandatory failures, applicable conditional failures and missing recommended items
  - `needs_client_confirmation` items: requirements that exist only as assumptions
- State clearly that a high score does not override a mandatory failure.
