#!/usr/bin/env python
"""Existing-code support: import an existing application and record what it already contains.

Usage:
  discover.py import <path-or-git-url> [--project ID]   copy/clone it into ../app-development/<id>/
                                                         (its own git repo), then scan it
  discover.py scan [--project ID]                        (re)scan ../app-development/<id>/

Writes ../projects/<id>/00-discovery/project-facts.json and project-facts.md:
  stack       languages (by file count), manifests and detected frameworks
  files       every source file (vendor/build folders excluded)
  routes      HTTP endpoints: FastAPI/Flask, Django urls, Express/Nest, Spring, ASP.NET, Laravel
  tables      database tables: SQL DDL/migrations, SQLAlchemy, Django models, JPA, EF, Laravel, TypeORM
  classes     controllers, services, repositories, models
  ui_routes   frontend routes (React Router, Angular, Vue)
  tests       test file count

When project-facts.json exists the project is "existing":
  - FRD approval does not scaffold over the existing code (tools/approve.py)
  - spec rule SV10 (tools/spec_rules.py) blocks specs that re-create a table, endpoint, file or
    class that already exists instead of modifying it; see existing_findings() below
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from common import app_dir, now, project_dir, read_json, rel, write_json

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", "bin", "obj", ".venv", "venv", "__pycache__",
             ".next", ".nuxt", "coverage", ".idea", ".vscode", ".pytest_cache", ".mypy_cache", "storage"}
LANG = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
        ".java": "Java", ".kt": "Kotlin", ".cs": "C#", ".php": "PHP", ".rb": "Ruby", ".go": "Go", ".vue": "Vue",
        ".sql": "SQL", ".html": "HTML", ".scss": "SCSS", ".css": "CSS"}
FRAMEWORK_HINTS = {
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "sqlalchemy": "SQLAlchemy", "alembic": "Alembic",
    "express": "Express", "@nestjs/core": "NestJS", "react": "React", "@angular/core": "Angular", "vue": "Vue",
    "next": "Next.js", "spring-boot": "Spring Boot", "laravel/framework": "Laravel", "typeorm": "TypeORM",
    "prisma": "Prisma", "Microsoft.AspNetCore": "ASP.NET Core", "Microsoft.EntityFrameworkCore": "EF Core",
}

ROUTE_PATTERNS = [
    re.compile(r"@(?:\w+)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"']"),                 # FastAPI/Flask/Express
    re.compile(r"\b(?:app|router)\.(get|post|put|patch|delete)\(\s*[\"'`]([^\"'`]*)[\"'`]"),       # Express
    re.compile(r"@(Get|Post|Put|Patch|Delete)Mapping\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']"),  # Spring
    re.compile(r"@(Get|Post|Put|Patch|Delete)\(\s*[\"']([^\"']*)[\"']\s*\)"),                       # NestJS
    re.compile(r"\[Http(Get|Post|Put|Patch|Delete)\(\s*\"([^\"]*)\"\s*\)\]"),                       # ASP.NET
    re.compile(r"Route::(get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"']"),                     # Laravel
]
DJANGO_PATH = re.compile(r"\b(?:re_)?path\(\s*[\"']([^\"']*)[\"']")
TABLE_PATTERNS = [
    re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?(?:\w+[\"`\]]?\.[\"`\[]?)?(\w+)", re.I),
    re.compile(r"__tablename__\s*=\s*[\"'](\w+)[\"']"),
    re.compile(r"@Table\(\s*name\s*=\s*\"(\w+)\""),
    re.compile(r"Schema::create\(\s*[\"'](\w+)[\"']"),
    re.compile(r"@Entity\(\s*[\"'](\w+)[\"']\s*\)"),
    re.compile(r"\[Table\(\"(\w+)\"\)\]"),
    re.compile(r"op\.create_table\(\s*[\"'](\w+)[\"']"),
]
DJANGO_MODEL = re.compile(r"class\s+(\w+)\((?:models\.)?Model\)")
CLASS_PAT = re.compile(r"\b(?:class|interface)\s+(\w+?(Controller|Service|Repository|Repo|Model|Entity))\b")
UI_ROUTE = [re.compile(r"<Route[^>]*\bpath=[\"']([^\"']+)[\"']"),
            re.compile(r"\bpath\s*:\s*[\"']([^\"']*)[\"']\s*,\s*(?:component|element|loadComponent|loadChildren)")]


def _files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS):
            yield p


def _norm_route(method: str, path: str) -> str:
    path = "/" + path.strip().strip("/")
    path = re.sub(r"\{[^}]+\}|:\w+|<[^>]+>", "{}", path)
    return f"{method.upper()} {path.rstrip('/') or '/'}"


def scan(root: Path) -> dict:
    files, langs = [], Counter()
    routes, tables, classes, ui_routes, tests = [], {}, [], set(), 0
    manifests, frameworks = {}, set()
    for p in _files(root):
        r = p.relative_to(root).as_posix()
        files.append(r)
        langs[LANG.get(p.suffix.lower(), "")] += 1
        if re.search(r"(^|/)(tests?|__tests__|spec)/|(_test|\.test|\.spec|Test|Tests)\.\w+$|(^|/)test_", r):
            tests += 1
        if p.name in ("package.json", "requirements.txt", "pyproject.toml", "pom.xml", "build.gradle",
                      "composer.json") or p.suffix == ".csproj":
            text = p.read_text(encoding="utf-8", errors="replace")
            manifests[r] = len(text)
            for hint, fw in FRAMEWORK_HINTS.items():
                if re.search(rf"(?:^|[\"'\s<=/]){re.escape(hint)}(?:[\"'\s>=<~^@/]|$)", text, re.I | re.M):
                    frameworks.add(fw)
        if p.suffix.lower() not in (".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".cs", ".php", ".sql", ".rb", ".go", ".vue"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if p.stat().st_size > 2_000_000:
            continue
        for pat in ROUTE_PATTERNS:
            for m, path in pat.findall(text):
                routes.append({"route": _norm_route(m, path), "file": r})
        if p.name in ("urls.py",):
            routes += [{"route": _norm_route("ANY", x), "file": r} for x in DJANGO_PATH.findall(text)]
        for pat in TABLE_PATTERNS:
            for t in pat.findall(text):
                tables.setdefault(t.lower(), r)
        for m in DJANGO_MODEL.findall(text):
            tables.setdefault(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", m).lower(), r)
        classes += [{"name": n, "kind": {"repo": "repository", "entity": "model"}.get(k.lower(), k.lower()), "file": r}
                    for n, k in CLASS_PAT.findall(text)]
        for pat in UI_ROUTE:
            ui_routes.update(pat.findall(text))
    langs.pop("", None)
    return {"scanned_at": now(), "root": rel(root),
            "stack": {"languages": dict(langs.most_common()), "frameworks": sorted(frameworks), "manifests": manifests},
            "files": sorted(files),
            "routes": [{"route": rt, "file": f} for rt, f in sorted({(x["route"], x["file"]) for x in routes})],
            "tables": [{"name": t, "file": f} for t, f in sorted(tables.items())],
            "classes": [{"name": n, "kind": k, "file": f} for n, k, f in sorted({(c["name"], c["kind"], c["file"]) for c in classes})],
            "ui_routes": sorted(ui_routes), "test_files": tests}


def render_md(f: dict) -> str:
    s = f["stack"]
    md = ["# Project facts (existing application)", "", f"Scanned {f['scanned_at']} from `{f['root']}`.", "",
          "## Stack", "", "- Languages: " + ", ".join(f"{k} ({v})" for k, v in s["languages"].items()),
          "- Frameworks: " + (", ".join(s["frameworks"]) or "none detected"),
          "- Manifests: " + (", ".join(s["manifests"]) or "none"),
          f"- Files: {len(f['files'])}; test files: {f['test_files']}", "",
          f"## Routes ({len(f['routes'])})", ""]
    md += [f"- `{r['route']}` ({r['file']})" for r in f["routes"]] or ["None found."]
    md += ["", f"## Tables ({len(f['tables'])})", ""]
    md += [f"- `{t['name']}` ({t['file']})" for t in f["tables"]] or ["None found."]
    md += ["", f"## Classes ({len(f['classes'])})", ""]
    md += [f"- {c['kind']} `{c['name']}` ({c['file']})" for c in f["classes"]] or ["None found."]
    md += ["", "## Frontend routes", ""] + ([f"- `{u}`" for u in f["ui_routes"]] or ["None found."])
    return "\n".join(md) + "\n"


def write_facts(pdir: Path) -> dict:
    root = app_dir(pdir)
    if not root.exists():
        sys.exit(f"{rel(root)} does not exist — run discover.py import <path> first")
    facts = scan(root)
    out = pdir / "00-discovery"
    write_json(out / "project-facts.json", facts)
    (out / "project-facts.md").write_text(render_md(facts), encoding="utf-8")
    return facts


def cmd_import(pdir: Path, src: str):
    dest = app_dir(pdir)
    if dest.exists() and any(dest.iterdir()):
        sys.exit(f"{rel(dest)} already exists and is not empty; remove it or run discover.py scan")
    dest.parent.mkdir(parents=True, exist_ok=True)
    is_url = re.match(r"^(https?://|git@|ssh://)", src)
    path = Path(src)
    if is_url or (path / ".git").exists():
        subprocess.run(["git", "clone", "--quiet", src, str(dest)], check=True)
    elif path.is_dir():
        shutil.copytree(path, dest, ignore=shutil.ignore_patterns(*SKIP_DIRS - {"storage"}))
        subprocess.run(["git", "init", "-q", "-b", "main", str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(dest), "-c", "user.name=SDLC Platform", "-c", "user.email=sdlc-platform@localhost",
                        "commit", "-q", "-m", "chore: import existing application"], check=True)
    else:
        sys.exit(f"not a folder or git URL: {src}")
    branches = subprocess.run(["git", "-C", str(dest), "branch", "--format=%(refname:short)"],
                              capture_output=True, text=True).stdout.split()
    if "develop" not in branches:
        subprocess.run(["git", "-C", str(dest), "branch", "develop"], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "develop"], check=True)
    print(f"imported into {rel(dest)} (branch develop)")


# ---------------------------------------------------------------- SV10: do not re-create existing code
def existing_findings(ctx) -> list[tuple[str, str]]:
    """(where, message) pairs for specs that re-create something the existing app already has."""
    facts = ctx.facts
    out = []
    known_tables = {t["name"].lower() for t in facts.get("tables", [])}
    for name, d in ctx.tables.items():
        if name in known_tables and "existing" not in d["comment"].lower():
            out.append(("schema.sql", f"CREATE TABLE {name} re-creates an existing table; use ALTER TABLE for "
                                      f"changes, or mark it '-- existing (reference only)'"))
    known_routes = {r["route"] for r in facts.get("routes", [])}
    for path, item in (ctx.api.get("paths") or {}).items():
        for method, op in (item or {}).items():
            if not isinstance(op, dict):
                continue
            key = _norm_route(method, path)
            if key in known_routes and not op.get("x-existing"):
                out.append(("openapi.yaml", f"{key} already exists in the application; mark it x-existing: true "
                                            f"and specify only the change"))
    files = set(facts.get("files", []))
    classes = {c["name"] for c in facts.get("classes", [])}
    for feat in ctx.features:
        p = ctx.sdir / "features" / f"{feat['id']}.md"
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        from spec_rules import section
        for line in section(text, 12).splitlines():
            for path_ in re.findall(r"[\w./-]+/[\w.-]+\.\w+", line):
                if path_ in files and not re.search(r"(?i)modify|existing|extend|update", line):
                    out.append((f"features/{feat['id']}.md", f"section 12 lists existing file {path_} without "
                                                             f"marking it '(modify)'"))
        for line in text.splitlines():
            if re.search(r"(?i)\b(create|add|new|implement)\b", line) and not \
                    re.search(r"(?i)existing|extend|modify|reuse|update", line):
                for c in classes:
                    if re.search(rf"\b{re.escape(c)}\b", line):
                        out.append((f"features/{feat['id']}.md", f"creates {c}, which already exists: "
                                                                 f"'{line.strip()[:80]}'"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["import", "scan"])
    ap.add_argument("source", nargs="?")
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    if a.cmd == "import":
        if not a.source:
            ap.error("import needs a folder or git URL")
        cmd_import(pdir, a.source)
    f = write_facts(pdir)
    print(f"project facts: {len(f['files'])} files, {len(f['routes'])} routes, {len(f['tables'])} tables, "
          f"{len(f['classes'])} classes, frameworks {', '.join(f['stack']['frameworks']) or 'none'} -> "
          f"{rel(pdir / '00-discovery' / 'project-facts.md')}")


if __name__ == "__main__":
    main()
