#!/usr/bin/env python
"""File-ownership enforcement for specialist agents (roadmap §4.4).

Usage:
  ownership.py check <agent[,agent2]> [--project ID]   changed (uncommitted) files in app/ must belong to one of the agents
  ownership.py owner <path>                   which agent owns a path
  ownership.py show                           print effective ownership map
Exit 1 on violations; the orchestrator then reverts or reassigns those files.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys

from common import app_dir, ROOT, die, project_dir, read_yaml


def ownership_map(pdir):
    override = pdir / "02-spec" / "ownership.yaml"
    src = override if override.exists() else ROOT / "config" / "ownership.yaml"
    return read_yaml(src)["owners"]


def owners_of(path, omap):
    return [a for a, pats in omap.items() if any(fnmatch.fnmatch(path, p) for p in pats)]


def changed_files(app):
    r = subprocess.run(["git", "-C", str(app), "status", "--porcelain", "--untracked-files=all"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(f"git status failed in {app}: {r.stderr.strip()}")
    files = []
    for line in r.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("agent"); p.add_argument("--project")
    p = sub.add_parser("owner"); p.add_argument("path"); p.add_argument("--project")
    p = sub.add_parser("show"); p.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    omap = ownership_map(pdir)
    if a.cmd == "show":
        for agent, pats in omap.items():
            print(f"{agent}: {', '.join(pats)}")
    elif a.cmd == "owner":
        print(", ".join(owners_of(a.path.replace("\\", "/"), omap)) or "UNOWNED")
    else:
        agents = [x.strip() for x in a.agent.split(",") if x.strip()]  # "backend-dev,api-dev" for parallel runs
        for ag in agents:
            if ag not in omap:
                die(f"agent '{ag}' has no ownership entry")
        violations = []
        files = changed_files(app_dir(pdir))
        for f in files:
            owners = owners_of(f, omap)
            if not set(agents) & set(owners):
                violations.append(f"{f} (owned by: {', '.join(owners) or 'nobody'})")
        if violations:
            print(f"OWNERSHIP VIOLATIONS for {a.agent}:")
            for v in violations:
                print(f"  - {v}")
            sys.exit(1)
        print(f"ownership OK for {a.agent}: {len(files)} changed file(s)")


if __name__ == "__main__":
    main()
