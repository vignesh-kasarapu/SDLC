---
name: trace
description: Trace any ID (C-nnn CRD block, FR/NFR/BR-nnn requirement, F-nnn feature) forwards and backwards through CRD -> FRD -> feature -> tests.
argument-hint: <ID>
disable-model-invocation: true
allowed-tools: Bash(python tools/*)
---
Run `python tools/traceability.py show $ARGUMENTS` and present the chain to the user. If no ID was given, run `python tools/traceability.py frd` to show CRD coverage instead.
