---
name: build-feature
description: Phase 3 - build ONE feature end-to-end with specialist agents (SME, database, backend, API, frontend, integration, NFR review, independent testing) including the bounded fix-and-retest loop.
argument-hint: "[F-nnn | next]"
disable-model-invocation: true
---
Build a feature for the active project. Arguments: `$ARGUMENTS` (default `next`). `P = ../projects/<id>` and `APP = ../app-development/<id>`, the app repository created at FRD approval. Every agent prompt starts with `PROJECT=P. APP=APP.` Follow CLAUDE.md strictly: the state machine decides; you do not.

**Git workflow** (see `APP/CONTRIBUTING.md`): each feature is built on its own branch `feature/F-nnn-<slug>` cut from `develop`, with Conventional Commits, and merged back into `develop` with `--no-ff` only when it passes. `main` only receives releases.

## 0. Gate and select
1. Run `python tools/gate.py build-ready`. Stop if it fails.
2. Select the feature:
   - **`next` or empty:** run `python tools/state.py next --claim`.
     - `F-nnn CLAIMED`: continue with that feature.
     - `F-nnn RESUME <state>`: an interrupted feature. Continue from the step that matches its state.
     - `ALL_COMPLETE`: tell the user to run `/qa-system`, then stop.
     - `NONE_READY`: report what is blocked, then stop.
   - **A specific F-nnn:** it must be `Ready` (or a resumable state). Run `python tools/state.py transition F-nnn InProgress`. If the tool refuses, report why and stop.
3. Read `P/02-spec/features/F-nnn.md` to learn which layers the feature touches.

## 1. Bootstrap (first feature only) and feature branch
1. If `git -C APP tag -l bootstrap` prints nothing:
   1. Run `git -C APP checkout develop`.
   2. Dispatch **integrator** with `PROJECT=P. APP=APP. MODE=scaffold.`
   3. If its first reply line is not `INTEGRATION: pass`, retry once, then escalate.
   4. On pass: `git -C APP add -A && git -C APP commit -m "chore: bootstrap MVC skeleton" && git -C APP tag bootstrap`.
2. Branch `B = feature/F-nnn-<slug of the title>`:
   - new feature: `git -C APP checkout develop && git -C APP checkout -b B`
   - resumed feature: `git -C APP checkout B`

## 2. SME brief
Dispatch **sme**: `PROJECT=P. FEATURE=F-nnn. Write 03-build/briefs/F-nnn.md.` Log it.

If the first reply line is not `NEEDS_HUMAN: none`:
1. Run `python tools/state.py transition F-nnn Blocked --note "<items>"`.
2. Show the user the questions.
3. Tell them that after they answer, they unblock the feature with `python tools/state.py transition F-nnn Ready` and re-run `/build-feature F-nnn`.
4. Stop.

## 3. Implement
Run the agents in MVC order: Model, then Service/Repository, then Controller, then View. After each one, run these checks on its uncommitted changes:
- `python tools/ownership.py check <agent>`
- `python tools/layer_check.py`, which enforces the MVC dependency rules

On an ownership violation, discard that agent's out-of-scope changes with `git -C APP checkout -- <file>` (or delete them if untracked), then re-dispatch the agent once with the violation list. On a layer violation, re-dispatch the agent once with the violation list. Then commit:

```
git -C APP add -A && git -C APP commit -m "feat(F-nnn): <layer> (<agent>)"
```

Committing after each agent keeps the ownership checks per-agent and gives a rollback point.

1. **database-dev**, if the feature has a database layer: `PROJECT=P. FEATURE=F-nnn. Brief: 03-build/briefs/F-nnn.md.` If the reply contains `RISKY_MIGRATION`, block the feature and escalate to the user (roadmap §9.2).
2. **backend-dev** and **api-dev** in parallel (one message, two Agent calls). Their files are disjoint and both follow the brief's shared contracts. Check them together with `python tools/ownership.py check backend-dev,api-dev`, then make one commit.
3. **frontend-dev**, if the feature has a frontend layer.

Pass each agent the "Requests for other agents" collected so far. Log every agent.

## 4. Integrate
1. Run `python tools/state.py transition F-nnn Integrating`.
2. Dispatch **integrator** with `PROJECT=P. MODE=integrate. FEATURE=F-nnn. Requests: <collected requests>.` Then run the ownership check and commit.
3. Run `python tools/layer_check.py --all` yourself. Don't rely on the agent's report.
4. If the reply is `INTEGRATION: fail`, or the layer check fails, run `python tools/state.py transition F-nnn FixRequired` and go to step 6.

## 5. Verify independently
1. Run `python tools/state.py transition F-nnn Testing`.
2. Dispatch, in parallel:
   - **tester**: `PROJECT=P. FEATURE=F-nnn. ATTEMPT=<k>. Write 03-build/reports/F-nnn.test.json and defects.`
   - **nfr-reviewer**: `PROJECT=P. FEATURE=F-nnn. Changed files: <git -C APP diff --name-only develop...HEAD>. Write 03-build/reports/F-nnn.nfr.json.`
3. Run the ownership check for `tester`, commit the tests, and log both agents.
4. Then run `python tools/validate.py test-report P/03-build/reports/F-nnn.test.json`.
5. **The feature passes only if all of these hold:**
   - the test report verdict is `pass`
   - the NFR verdict is `pass` (no critical or high findings, which includes MVC layer violations)
   - `python tools/layer_check.py --all` exits 0
6. **On pass:** run `python tools/state.py complete F-nnn --evidence P/03-build/reports/F-nnn.test.json`. Then merge and tag:
   `git -C APP checkout develop && git -C APP merge --no-ff B -m "Merge B: <title>" && git -C APP tag F-nnn-done`. Go to step 7.
7. **On fail:** run `python tools/state.py transition F-nnn FixRequired`. If the tool refuses because the retry limit is reached, run `python tools/state.py transition F-nnn Blocked --note "retry limit"`, escalate to the user with the open defects and findings, and stop. The work stays on branch `B`, unmerged.

## 6. Fix loop
This loop is bounded by `state.py` (3 retries).
1. Dispatch **fix-triager**: `PROJECT=P. FEATURE=F-nnn. Phase 3.` It writes `03-build/fix-plan.json`.
2. If any assignment is for `human`, block the feature and escalate.
3. Run `python tools/state.py transition F-nnn InProgress`.
4. For each assignment, in the plan's order, dispatch the owning agent with `PROJECT=P. FEATURE=F-nnn. FIX ROUND. Defects/findings: <ids + paths>. Instruction: <instruction>.` Run the ownership check and commit after each one.
5. Return to step 4 (Integrate).

## 7. Report
In at most 12 lines:
- the feature result
- the test totals and acceptance criteria passed
- the NFR findings
- the commits made
- the features that became Ready (from `state.py complete` output)
- the next step: `/build-feature next`, or `/qa-system` once every feature is complete
