---
name: release
description: Phase 4 - generate documentation and the deployment package, then record HUMAN release approval. Nothing is deployed.
argument-hint: "[approver name] [comment]"
disable-model-invocation: true
---
Prepare the release. Arguments: `$ARGUMENTS`. `P = ../projects/<id>`.

1. **Gate.** Run `python tools/gate.py qa-passed`. Stop if it fails.
2. **Documentation and packaging.** Dispatch **doc-writer** and **deployer** in parallel, each with `PROJECT=P.` and its output paths. When both finish, run `python tools/ownership.py check doc-writer,deployer`. Do this on a release branch: first `git -C APP checkout -b release/v1.0.0 develop`, then after the agents `git -C APP add -A && git -C APP commit -m "docs: release documentation and deployment package"`. (`APP = ../app-development/<id>`; pass `APP=APP` to the agents.) Log both agents.
3. **Re-check.** Re-run `python tools/qa_gate.py`, because packaging changes must not break anything. Also run the backend and frontend tests from `02-spec/commands.json` one last time. If anything fails, stop and report.
4. **Package summary.** Write `P/04-delivery/release-summary.md` listing:
   - the deliverables from roadmap §5.4, with the path of each
   - the git tag that will be created
   - known limitations, taken from the release notes
5. **Human approval.** Show the summary and ask the user to confirm the release. Ask for the approver name if it was not given. On confirmation, run:
   `python tools/approve.py release --by "<name>" --decision approved --comment "<comment>"`
   Then merge and tag: `git -C APP checkout main && git -C APP merge --no-ff release/v1.0.0 -m "Release v1.0.0" && git -C APP tag v1.0.0 && git -C APP checkout develop && git -C APP merge --no-ff main`. Never push. The approval tool sets the release phase to approved.
6. **Report.** Tell the user:
   - the release is approved
   - where the repository and package are
   - how to run the app, from the README
   - that deployment itself is a manual, human step
