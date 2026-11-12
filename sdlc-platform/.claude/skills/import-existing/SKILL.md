---
name: import-existing
description: Setup - work on an EXISTING application instead of a new one. Copies or clones it into ../app-development/<id>/, scans it into project facts (stack, routes, tables, classes), and switches the specs to "modify, don't re-create".
argument-hint: <path to the app folder, or a git URL>
disable-model-invocation: true
---
Import an existing application into the active project. Arguments: `$ARGUMENTS`. `P = ../projects/<id>`.

1. Run `python tools/gate.py project`. Stop if it fails.
2. Run `python tools/discover.py import "$ARGUMENTS"`. It copies or clones the app into `../app-development/<id>/` (its own git repository, branch `develop`). It then writes `P/00-discovery/project-facts.json` and `project-facts.md`. Stop on error.
   - If the app already sits in `../app-development/<id>/`, run `python tools/discover.py scan` instead.
3. Show the user, from `project-facts.md`:
   - the detected languages and frameworks
   - the number of routes, tables and classes
   - anything surprising, for example no tests
4. Explain what changes for this project:
   - The CRD or FRD describes the **changes**. Ingest it with `/ingest-crd` as usual.
   - `/set-tech-stack` should record the existing stack. Pick the architecture pattern the app already follows (MVC or its framework's own convention).
   - FRD approval does **not** scaffold over the existing code.
   - In Phase 2, every agent reads the project facts. Spec rule **SV10** blocks any spec that re-creates an existing table, endpoint, file or class instead of modifying it.
   - Re-run `python tools/discover.py scan` after each merged feature to keep the facts current.
5. Next step: `/ingest-crd <change request>`.
