---
name: qa-system
description: Phase 4 - system integration QA - end-to-end, regression, security, performance, NFR validation and FRD traceability - with the final quality gate and a bounded fix loop.
disable-model-invocation: true
---
Run whole-system quality assurance. `P = ../projects/<id>`, `APP = ../app-development/<id>`; every agent prompt starts with `PROJECT=P. APP=APP.` Work on `develop`; defect fixes go on `fix/D-nnn-<slug>` branches merged back with `--no-ff`. Follow CLAUDE.md.

1. **Gate.** Run `python tools/gate.py features-complete`. Stop if it fails.
2. Run `python tools/state.py phase qa in_progress`.
3. **Functional verification.** Dispatch **system-tester**:
   `PROJECT=P. Write 04-delivery/reports/system.test.json, regression.test.json, and defects in 04-delivery/defects/.`
   Run `python tools/ownership.py check tester` (the system tester only owns test paths), commit the tests, and log the agent.
4. **Non-functional verification.** Dispatch **security-auditor** (Opus) and **perf-tester** (Haiku) in parallel.
   - security-auditor writes `security.review.json`.
   - perf-tester writes `performance.review.json`.
   - Commit their probe scripts and log both.
5. **Traceability and NFR roll-up.** Dispatch **traceability-auditor**. It runs `tools/traceability.py report` and writes `nfr.review.json`. Log it.
6. **Final gate.** Run `python tools/qa_gate.py`.
   - **Passed:** run `python tools/state.py phase qa passed`, then go to step 8.
   - **Failed:** go to step 7, the fix loop.
7. **Fix loop** (at most 3 rounds):
   1. Dispatch **fix-triager** with `PROJECT=P. Phase 4.` It writes `04-delivery/fix-plan.json`.
   2. If anything is assigned to `human`, escalate it and stop.
   3. Dispatch the owning developer agents in plan order, each with its defect and finding IDs. Run the ownership check and commit after each one.
   4. Re-run only the failed checks: system-tester for test failures, security-auditor for security findings, perf-tester for performance findings. Always re-run the traceability-auditor last.
   5. Run `python tools/qa_gate.py` again.

   After 3 rounds, escalate the remaining failures to the user.
8. **Report.** Show the QA scorecard from `04-delivery/qa-gate.json`: the test totals per suite, the findings by severity, and the traceability percentage. Give the next step, `/release`.
