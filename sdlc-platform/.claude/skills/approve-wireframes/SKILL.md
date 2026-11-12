---
name: approve-wireframes
description: HUMAN ACTION - approve (or reject) the generated wireframes. Locks the wireframe version as the binding screen design for specs and development.
argument-hint: "[approver name] [comment]"
disable-model-invocation: true
---
The user is approving the wireframes. Arguments: `$ARGUMENTS`. `P = ../projects/<id>`.

1. Run `python tools/gate.py wireframes-check`. If it fails, show the failures and **stop**. Approval is impossible until the set is complete.
2. Show a short confirmation summary:
   - the version and number of screens
   - the screens per role
   - the open questions still on the screens. They go into the specs as `OPEN:` items, or to the client.
   - the path of `index.html`
3. Determine the approver name: the first word or quoted name in `$ARGUMENTS`, or ask. Then run:
   `python tools/approve.py wireframes --by "<name>" --decision approved --comment "<rest of arguments>"`
   To reject instead, run it with `--decision rejected --comment "<what must change>"`. The comment is recorded as review feedback; then run `/generate-wireframes "<what must change>"`.
4. Once approved, run `python tools/gate.py wireframes-ready`. Report:
   - that the wireframes are approved and locked. Changes now need a new version (`/generate-wireframes "<change>"`) and re-approval.
   - the next step, `/generate-specs`. The architect, feature breakdown, UI spec and frontend developer all build on these screens.
