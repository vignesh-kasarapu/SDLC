#!/usr/bin/env python
"""Switch subagent models from config/models.yaml (rewrites the `model:` line in .claude/agents/*.md).

Usage:
  models.py show                         current model per agent vs. config
  models.py apply primary|fallback       set every agent to its primary or fallback model
  models.py set <agent> <opus|sonnet|haiku|inherit>
Restart Claude Code (or run /agents) after changing models so the agent definitions reload.
"""
from __future__ import annotations

import re
import sys

from common import AGENTS_DIR, ROOT, agent_model, die, read_yaml

VALID = {"opus", "sonnet", "haiku", "inherit"}


def set_model(agent: str, model: str):
    if model not in VALID:
        die(f"model must be one of {sorted(VALID)}")
    p = AGENTS_DIR / f"{agent}.md"
    if not p.exists():
        die(f"no agent file {p}")
    text = p.read_text(encoding="utf-8")
    new, n = re.subn(r"(?m)^model:.*$", f"model: {model}", text, count=1)
    if n == 0:
        new = text.replace("---\n", f"---\nmodel: {model}\n", 1)
    p.write_text(new, encoding="utf-8")


def main():
    cfg = read_yaml(ROOT / "config" / "models.yaml")["agents"]
    if len(sys.argv) < 2 or sys.argv[1] == "show":
        print(f"{'agent':<24}{'current':<10}{'primary':<10}fallback")
        for agent, m in cfg.items():
            print(f"{agent:<24}{agent_model(agent):<10}{m['primary']:<10}{m['fallback']}")
        return
    if sys.argv[1] == "apply" and len(sys.argv) == 3 and sys.argv[2] in ("primary", "fallback"):
        for agent, m in cfg.items():
            set_model(agent, m[sys.argv[2]])
        print(f"applied {sys.argv[2]} models to {len(cfg)} agents; restart Claude Code to reload them")
    elif sys.argv[1] == "set" and len(sys.argv) == 4:
        set_model(sys.argv[2], sys.argv[3])
        print(f"{sys.argv[2]} -> {sys.argv[3]}")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
