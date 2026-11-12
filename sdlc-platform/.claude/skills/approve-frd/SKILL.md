---
name: approve-frd
description: HUMAN ACTION - approve the latest FRD version. Requires the FRD quality gate to pass; locks the FRD as the immutable Phase 2 input.
argument-hint: "[approver name] [comment]"
disable-model-invocation: true
---
The user is approving the FRD. Arguments: `$ARGUMENTS`

1. Run `python tools/gate.py frd-quality`. If it fails, show the failures and **stop**. Approval is impossible until the gate passes.
2. Before recording approval, show a short confirmation summary:
   - the version
   - the requirement counts
   - every `assumed` requirement (these are defaults the client never stated)
   - the non-blocking open questions that remain
   - the checklist `needs_client_confirmation` items
3. Determine the approver name: use the first word or quoted name in `$ARGUMENTS`, or otherwise ask the user. Then run:
   `python tools/approve.py frd --by "<name>" --decision approved --comment "<rest of arguments>"`
4. Report:
   - that the FRD is approved, with its version
   - that its files are now locked; edits are blocked by the hook, and changes require `/revise-frd` and re-approval
   - the app repository `approve.py` just created (its `APP REPOSITORY` output line): `../app-development/<id>/`, with branches `main` and `develop`. Show its top-level tree with `git -C ../app-development/<id> ls-files | cut -d/ -f1-2 | sort -u`
   - the next step, `/generate-wireframes`. It checks whether wireframes exist and, if not, asks whether to create them. Specs and development wait until the screens are settled.
