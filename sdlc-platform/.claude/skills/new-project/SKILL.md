---
name: new-project
description: Create a new client project workspace under projects/ and make it the active project.
argument-hint: <project name> [--domain slug]
disable-model-invocation: true
---
Create a new SDLC project from these arguments: `$ARGUMENTS`

1. If no name was given, ask the user for one and stop.
2. Run `python tools/state.py init "<name>"`. Add `--domain <slug>` only if the user passed one.
3. Run `python tools/state.py show`.
4. Tell the user:
   - the project ID and folder
   - the next step: `/ingest-crd <path-to-CRD>` (supported formats: PDF, DOCX, TXT, MD)
   - that other projects can be selected with `python tools/state.py use <id>`
