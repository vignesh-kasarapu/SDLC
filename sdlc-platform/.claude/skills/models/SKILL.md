---
name: models
description: Show or switch which Claude model each platform agent uses (primary vs fallback profile, or per agent).
argument-hint: "[show | primary | fallback | <agent> <opus|sonnet|haiku>]"
disable-model-invocation: true
allowed-tools: Bash(python tools/models.py*)
---
Arguments: `$ARGUMENTS`

| Argument | Command to run |
|---|---|
| empty or `show` | `python tools/models.py show` |
| `primary` or `fallback` | `python tools/models.py apply <arg>` |
| `<agent> <model>` | `python tools/models.py set <agent> <model>` |

After any change, tell the user to restart Claude Code (or reopen `/agents`) so the new agent definitions load.

Explain the trade-off in one line:
- **fallback** moves the Opus agents (frd-evaluator, architect, nfr-reviewer, security-auditor) to Sonnet. This saves Pro usage and works on plans without Opus.
- **primary** gives the strongest critique and review.
