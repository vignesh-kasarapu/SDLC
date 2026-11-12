---
name: checklist
description: Show the domain checklist for the active project - the items that apply, and how the latest FRD version scores against them.
argument-hint: "[domain slug, to preview a domain's checklist]"
disable-model-invocation: true
allowed-tools: Bash(python tools/*), Read
---
Arguments: `$ARGUMENTS`

- If a domain slug was given, run `python tools/checklist.py --show --domain $ARGUMENTS` and present the items. Stop.
- Otherwise:
  1. Run `python tools/checklist.py --show` to list the items for the project's domain.
  2. If an FRD version exists, run `python tools/checklist.py`. This re-evaluates the latest version and writes `01-frd/checklist.vN.json` and `.md`. A non-zero exit only means items are failing; report them.
  3. Present a compact table: item, level, status, covering requirements. List failures first.
  4. Give the file paths:
     - the results report: `../projects/<id>/01-frd/checklist.vN.md`
     - the checklist definitions: `knowledge/domains/_generic/checklist.yaml` and `knowledge/domains/<domain>/checklist.yaml`
     - the feature recommendations: `../projects/<id>/01-frd/feature-recommendations.md`, if present
