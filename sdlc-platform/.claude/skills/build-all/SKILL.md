---
name: build-all
description: Phase 3 - autonomously build every remaining feature in dependency order by repeating the build-feature workflow until all are complete or one is blocked.
argument-hint: "[max features, default all]"
disable-model-invocation: true
---
Build the remaining features automatically. Optional limit: `$ARGUMENTS`.

1. Run `python tools/gate.py build-ready`. Stop if it fails.
2. Warn the user once that each feature uses many agent runs. On Claude Pro, consider `/models fallback`, or limit the run, e.g. `/build-all 2`.
3. **Loop:**
   1. Read `.claude/skills/build-feature/SKILL.md` and execute it with the argument `next`.
   2. After each feature, print one progress line: `F-nnn: Completed | Blocked (reason) — k/N done`.
   3. Stop the loop when any of these happens:
      - `state.py next` prints `ALL_COMPLETE`
      - it prints `NONE_READY`, meaning the remaining features are Blocked or waiting on a Blocked prerequisite
      - a feature becomes Blocked, because human input is needed
      - the optional limit is reached
4. **Final summary:**
   - run `python tools/state.py show`
   - list the completed features
   - list the blocked features with their reasons and the exact questions for the human
   - give the next step: `/qa-system` if everything is complete; otherwise resolve the blockers and re-run `/build-all`

The orchestration is resumable. If the session ends, `/build-all` picks up from `state.json`, because `state.py next` resumes an in-flight feature first.
