#!/usr/bin/env python
"""PreToolUse hook: block edits to locked (approved) artifacts and to platform files during runs.

Claude Code passes the tool call as JSON on stdin. Exit code 2 blocks the call and the
stderr message is shown to Claude. Approved artifacts are immutable: changes require a
new version (e.g. /revise-frd creates frd.v(N+1).md), never an in-place edit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROJECTS, ROOT, rel  # noqa: E402

PROTECTED_NAMES = {"approval.json", "release-approval.json", "state.json"}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # never break the session on malformed input
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        sys.exit(0)
    path = Path(target)
    if not path.is_absolute():
        path = Path(payload.get("cwd") or ROOT) / path
    try:
        path.resolve().relative_to(PROJECTS)
    except ValueError:
        sys.exit(0)  # not client project data
    key = rel(path)  # same form as the lock keys written by approve.py
    parts = path.resolve().relative_to(PROJECTS).parts
    if len(parts) >= 2:
        # Approval and state files are written only by tools/*.py, never by Claude directly.
        if parts[-1] in PROTECTED_NAMES:
            print(f"BLOCKED: {key} is managed by tools/ scripts (state.py / approve.py). "
                  f"Use the slash command instead of editing it.", file=sys.stderr)
            sys.exit(2)
        state_file = PROJECTS / parts[0] / "state.json"
        if state_file.exists():
            try:
                locks = json.loads(state_file.read_text(encoding="utf-8")).get("locks", {})
            except Exception:
                locks = {}
            if key in locks:
                print(f"BLOCKED: {key} is an approved, locked artifact (sha256 recorded at "
                      f"{locks[key].get('locked_at')}). Create a new version instead "
                      f"(e.g. /revise-frd) — approved baselines are immutable.", file=sys.stderr)
                sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
