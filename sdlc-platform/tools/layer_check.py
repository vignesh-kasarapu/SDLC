#!/usr/bin/env python
"""MVC layer dependency check (knowledge/standards/mvc-coding-standards.md).

Usage: layer_check.py [--project ID] [--all]
Checks Python and TS/JS files in app-development/<id>/ against config/layers.yaml
(or 02-spec/layers.yaml when the architect provided one). By default only files changed
since HEAD (plus untracked files) are checked; --all checks the whole app.
Exit 1 on violations, e.g. a controller importing a repository or a view calling a service directly.
Languages other than Python/TS/JS are skipped (the nfr-reviewer covers them by inspection).
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import posixpath
import re
import subprocess
import sys
from pathlib import Path

from common import app_dir, ROOT, project_dir, read_yaml

TS_EXT = (".ts", ".tsx", ".js", ".jsx")
TS_IMPORT = re.compile(r"""(?:import|export)\s[^'"]*?from\s+['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|require\(\s*['"]([^'"]+)['"]\s*\)""")


def load_rules(pdir):
    override = pdir / "02-spec" / "layers.yaml"
    return read_yaml(override if override.exists() else ROOT / "config" / "layers.yaml")


def layer_of(path, layers):
    for name, spec in layers.items():
        if any(fnmatch.fnmatch(path, p) for p in spec["paths"]):
            return name
    return None


def py_imports(file: Path, rel_path: str, roots: dict):
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    targets = []
    pkg_dir = posixpath.dirname(rel_path)
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                base = pkg_dir
                for _ in range(node.level - 1):
                    base = posixpath.dirname(base)
                mod_path = posixpath.join(base, *(node.module or "").split(".")) if node.module else base
                targets.append((node.lineno, mod_path))
                for a in node.names:
                    targets.append((node.lineno, posixpath.join(mod_path, a.name)))
                continue
            mods = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
        for m in mods:
            head = m.split(".")[0]
            if head in roots:
                targets.append((node.lineno, posixpath.join(roots[head], *m.split(".")[1:])))
    return targets


def ts_imports(file: Path, rel_path: str):
    out = []
    for i, line in enumerate(file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for m in TS_IMPORT.finditer(line):
            spec = next(g for g in m.groups() if g)
            if spec.startswith("."):
                out.append((i, posixpath.normpath(posixpath.join(posixpath.dirname(rel_path), spec))))
            elif spec.startswith("@/"):  # common Vite alias for src/
                out.append((i, "frontend/src/" + spec[2:]))
    return out


def resolve_layer(target: str, layers):
    """A module path may be a file (with any extension) or a package directory."""
    for cand in (target, target + ".py", target + "/__init__.py", *(target + e for e in TS_EXT),
                 *(target + "/index" + e for e in TS_EXT)):
        lay = layer_of(cand, layers)
        if lay:
            return lay
    return layer_of(target + "/x", layers)  # directory import


def files_to_check(app: Path, check_all: bool):
    if check_all or not (app / ".git").exists():
        return [p.relative_to(app).as_posix() for p in app.rglob("*")
                if p.is_file() and p.suffix in (".py", *TS_EXT)
                and not any(x in p.parts for x in ("node_modules", ".venv", "dist", "build", "__pycache__"))]
    r = subprocess.run(["git", "-C", str(app), "status", "--porcelain", "--untracked-files=all"],
                       capture_output=True, text=True)
    files = []
    for line in r.stdout.splitlines():
        p = line[3:].strip().strip('"').split(" -> ")[-1]
        if p.endswith((".py", *TS_EXT)) and (app / p).exists():
            files.append(p)
    return files


def check(app: Path, rules: dict, check_all: bool):
    layers = rules["layers"]
    roots = rules.get("python_package_roots", {})
    violations = []
    for f in files_to_check(app, check_all):
        src_layer = layer_of(f, layers)
        if not src_layer:
            continue
        imports = py_imports(app / f, f, roots) if f.endswith(".py") else ts_imports(app / f, f)
        allowed = set(layers[src_layer].get("may_import", [])) | {src_layer}
        for line, target in imports:
            tgt_layer = resolve_layer(target, layers)
            if tgt_layer and tgt_layer not in allowed:
                violations.append(f"{f}:{line} [{src_layer}] imports [{tgt_layer}] ({target}) - allowed: {sorted(allowed)}")
    return sorted(set(violations))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    from common import read_json
    pattern = read_json(pdir / "01-frd" / "tech-stack.json", default={}).get("architecture_pattern", "MVC")
    if pattern != "MVC" and not (pdir / "02-spec" / "layers.yaml").exists():
        print(f"layer check skipped: pattern '{pattern}' has no layer rules (the architect may add 02-spec/layers.yaml)")
        return
    violations = check(app_dir(pdir), load_rules(pdir), a.all)
    if violations:
        print("MVC LAYER VIOLATIONS:")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    print("MVC layer check OK")


if __name__ == "__main__":
    main()
