#!/usr/bin/env python
"""Build a clean, shareable zip of the platform (this folder only).

Excludes caches, local settings and anything that must never leave your machine:
__pycache__, .pytest_cache, .mypy_cache, .venv, .git, .claude/settings.local.json, and any
projects/ or app-development/ folder that ended up inside the platform by mistake.

Usage: package.py [--out PATH]      default: ../sdlc-platform-<YYYYMMDD>.zip
"""
from __future__ import annotations

import argparse
import datetime as dt
import zipfile
from pathlib import Path

from common import ROOT, rel

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", ".git",
                "projects", "app-development", "node_modules"}
EXCLUDE_FILES = {".claude/settings.local.json", ".DS_Store", "Thumbs.db"}


def files():
    for p in sorted(ROOT.rglob("*")):
        r = p.relative_to(ROOT)
        if p.is_dir() or set(r.parts) & EXCLUDE_DIRS or r.as_posix() in EXCLUDE_FILES or p.suffix in (".pyc", ".zip"):
            continue
        yield p, r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT.parent / f"sdlc-platform-{dt.date.today():%Y%m%d}.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, r in files():
            z.write(p, Path("sdlc-platform") / r)
            n += 1
    print(f"wrote {rel(out)}: {n} files, {out.stat().st_size // 1024} KB (no caches, no client data)")


if __name__ == "__main__":
    main()
