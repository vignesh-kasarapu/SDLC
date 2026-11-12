#!/usr/bin/env python
"""Create the application repository for a project right after its FRD is approved.

Location: app-development/<project-id>/  (workspace root; git-ignored by the platform, its own git repo)

The layout follows the user's stack (01-frd/tech-stack.json) and the mandatory MVC structure
(knowledge/standards/mvc-coding-standards.md §2):

  .github/workflows/ci.yml          CI: lint + test backend and frontend, build Docker images (no deploy)
  .github/pull_request_template.md  PR checklist (feature ID, requirements, tests, layer/ownership checks)
  .github/ISSUE_TEMPLATE/           feature + defect templates
  backend/                          MVC backend (controllers/services/repositories/models/dto) + Dockerfile
  backend/tests/ unit api integration
  frontend/                         MVC frontend (views/components/controllers/services/api/types) + Dockerfile
  e2e/ perf/                        end-to-end and performance tests
  docs/ deploy/ scripts/            documentation, deployment guide, helper scripts
  docker-compose.yml .env.example   local stack (database + backend + frontend), placeholder secrets only
  README.md CONTRIBUTING.md CHANGELOG.md .gitignore .gitattributes .editorconfig

Git workflow: `main` (released, tagged vX.Y.Z) <- `release/vX.Y.Z` <- `develop` (integration)
<- `feature/F-nnn-<slug>` and `fix/D-nnn-<slug>`. The scaffold is committed on main, then
`develop` is created and checked out.

Existing files are never overwritten, so re-running is safe.

Usage: scaffold.py init [--project ID]      (requires the frd-approved gate)
       scaffold.py show [--project ID]      print the target path and detected stack
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import app_dir, project_dir, read_json, rel


# ---------- stack detection ----------
def detect(ts: dict) -> dict:
    be = (ts.get("backend", {}).get("framework", "") + " " + ts.get("backend", {}).get("language", "")).lower()
    fe = (ts.get("frontend", {}).get("framework", "") + " " + ts.get("frontend", {}).get("language", "")).lower()
    db = ts.get("database", {}).get("engine", "").lower()
    if any(k in be for k in ("fastapi", "flask", "django", "python")):
        backend = "fastapi" if "fastapi" in be else "python"
    elif any(k in be for k in ("spring", "java", "kotlin")):
        backend = "spring"
    elif any(k in be for k in (".net", "asp", "c#", "dotnet")):
        backend = "dotnet"
    else:
        backend = "node"
    frontend = "angular" if "angular" in fe else ("none" if not fe.strip() else "vite")
    database = next((k for k in ("postgres", "mysql", "mariadb", "sql server", "mssql", "mongo", "sqlite") if k in db), "")
    return {"backend": backend, "frontend": frontend, "database": database}


BACKEND_DIRS = {
    "fastapi": ["backend/app/controllers", "backend/app/services", "backend/app/repositories", "backend/app/models",
                "backend/app/schemas", "backend/app/core", "backend/migrations",
                "backend/tests/unit", "backend/tests/api", "backend/tests/integration"],
    "python": ["backend/app/controllers", "backend/app/services", "backend/app/repositories", "backend/app/models",
               "backend/app/schemas", "backend/app/core", "backend/migrations",
               "backend/tests/unit", "backend/tests/api", "backend/tests/integration"],
    "node": ["backend/src/controllers", "backend/src/services", "backend/src/repositories", "backend/src/models",
             "backend/src/dto", "backend/src/config", "backend/migrations",
             "backend/tests/unit", "backend/tests/api", "backend/tests/integration"],
    "spring": [f"backend/src/main/java/app/{d}" for d in ("controller", "service", "repository", "model", "dto", "config")]
              + ["backend/src/main/resources/db/migration",
                 "backend/src/test/java/app/unit", "backend/src/test/java/app/api", "backend/src/test/java/app/integration"],
    "dotnet": [f"backend/src/{d}" for d in ("Controllers", "Services", "Repositories", "Models", "DTOs", "Config")]
              + ["backend/src/Migrations", "backend/tests/Unit", "backend/tests/Api", "backend/tests/Integration"],
}
FRONTEND_DIRS = {
    "vite": [f"frontend/src/{d}" for d in ("views", "components", "controllers", "services", "api", "types", "utils")]
            + ["frontend/public"],
    "angular": [f"frontend/src/app/{d}" for d in ("views", "components", "services", "models")] + ["frontend/src/assets"],
    "none": [],
}
COMMON_DIRS = ["e2e", "perf", "docs", "deploy", "scripts"]

BACKEND_DOCKERFILE = {
    "fastapi": """FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    "python": """FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app.main:app"]
""",
    "node": """FROM node:20-alpine
WORKDIR /srv
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
USER node
EXPOSE 3000
CMD ["node", "dist/main.js"]
""",
    "spring": """FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY . .
RUN ./mvnw -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /srv
COPY --from=build /src/target/*.jar app.jar
RUN useradd appuser
USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
""",
    "dotnet": """FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish src -c Release -o /out

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /srv
COPY --from=build /out .
USER app
EXPOSE 8080
ENTRYPOINT ["dotnet", "App.dll"]
""",
}
BACKEND_PORT = {"fastapi": 8000, "python": 8000, "node": 3000, "spring": 8080, "dotnet": 8080}

FRONTEND_DOCKERFILE = """FROM node:20-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from={dist} /usr/share/nginx/html
EXPOSE 80
"""

DB_SERVICE = {
    "postgres": ("postgres:16", 5432, {"POSTGRES_DB": "${DB_NAME}", "POSTGRES_USER": "${DB_USER}",
                                        "POSTGRES_PASSWORD": "${DB_PASSWORD}"}, "/var/lib/postgresql/data"),
    "mysql": ("mysql:8.4", 3306, {"MYSQL_DATABASE": "${DB_NAME}", "MYSQL_USER": "${DB_USER}",
                                  "MYSQL_PASSWORD": "${DB_PASSWORD}", "MYSQL_ROOT_PASSWORD": "${DB_PASSWORD}"}, "/var/lib/mysql"),
    "mariadb": ("mariadb:11", 3306, {"MARIADB_DATABASE": "${DB_NAME}", "MARIADB_USER": "${DB_USER}",
                                     "MARIADB_PASSWORD": "${DB_PASSWORD}", "MARIADB_ROOT_PASSWORD": "${DB_PASSWORD}"}, "/var/lib/mysql"),
    "sql server": ("mcr.microsoft.com/mssql/server:2022-latest", 1433, {"ACCEPT_EULA": "Y", "MSSQL_SA_PASSWORD": "${DB_PASSWORD}"},
                   "/var/opt/mssql"),
    "mongo": ("mongo:7", 27017, {"MONGO_INITDB_DATABASE": "${DB_NAME}"}, "/data/db"),
}
DB_SERVICE["mssql"] = DB_SERVICE["sql server"]


# ---------- file contents ----------
def compose(stack) -> str:
    be, fe, db = stack["backend"], stack["frontend"], stack["database"]
    lines = ["# Local development stack. Secrets come from .env (copy .env.example); never commit .env.", "services:"]
    if db in DB_SERVICE:
        image, port, env, vol = DB_SERVICE[db]
        lines += ["  db:", f"    image: {image}", "    environment:"]
        lines += [f"      {k}: {v}" for k, v in env.items()]
        lines += ["    ports:", f"      - \"{port}:{port}\"", "    volumes:", f"      - db-data:{vol}"]
    p = BACKEND_PORT[be]
    lines += ["  backend:", "    build: ./backend", "    env_file: .env", "    ports:", f"      - \"{p}:{p}\""]
    if db in DB_SERVICE:
        lines += ["    depends_on:", "      - db"]
    if fe != "none":
        lines += ["  frontend:", "    build: ./frontend", "    ports:", "      - \"5173:80\"", "    depends_on:", "      - backend"]
    if db in DB_SERVICE:
        lines += ["volumes:", "  db-data: {}"]
    return "\n".join(lines) + "\n"


def env_example(stack) -> str:
    return "\n".join([
        "# Copy to .env for local development. Placeholder values only - never put real secrets in git.",
        "APP_ENV=development",
        "LOG_LEVEL=info",
        "DB_HOST=db",
        "DB_NAME=app",
        "DB_USER=app",
        "DB_PASSWORD=change-me",
        "AUTH_SECRET=change-me",
        "CORS_ORIGINS=http://localhost:5173",
    ]) + "\n"


def ci_workflow(stack) -> str:
    be, fe = stack["backend"], stack["frontend"]
    jobs = []
    if be in ("fastapi", "python"):
        jobs.append("""  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Lint
        run: ruff check app && mypy app
      - name: Test
        run: pytest -q --cov=app/services --cov-fail-under=80""")
    elif be == "node":
        jobs.append("""  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run lint
      - run: npm test""")
    elif be == "spring":
        jobs.append("""  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./mvnw -q verify""")
    else:
        jobs.append("""  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.0.x"
      - run: dotnet format --verify-no-changes
      - run: dotnet test""")
    if fe != "none":
        jobs.append("""  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run lint
      - run: npm test -- --run
      - run: npm run build""")
    needs = "[backend, frontend]" if fe != "none" else "[backend]"
    jobs.append(f"""  docker:
    runs-on: ubuntu-latest
    needs: {needs}
    steps:
      - uses: actions/checkout@v4
      - name: Build images (no push, no deploy)
        run: docker compose build""")
    return ("# CI for every push and pull request. Builds and tests only - this pipeline never deploys\n"
            "# or pushes images. The deployer agent finalises it in Phase 4.\n"
            "name: CI\n\non:\n  push:\n    branches: [main, develop, \"feature/**\", \"fix/**\", \"release/**\"]\n"
            "  pull_request:\n    branches: [main, develop]\n\njobs:\n" + "\n\n".join(jobs) + "\n")


GITIGNORE = """# Secrets
.env
*.pem

# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Node
node_modules/
dist/
coverage/

# Java / .NET
target/
bin/
obj/

# Test output
playwright-report/
test-results/

# OS / editor
.DS_Store
Thumbs.db
.idea/
.vscode/
"""

GITATTRIBUTES = """* text=auto eol=lf
*.bat text eol=crlf
*.ps1 text eol=crlf
*.png binary
*.jpg binary
"""

EDITORCONFIG = """root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 2

[*.{py,java,cs}]
indent_size = 4
"""

CONTRIBUTING = """# Contributing: git workflow

## Branches
| Branch | Purpose | Created from | Merges into |
|---|---|---|---|
| `main` | Released code only. Every merge is tagged `vX.Y.Z`. | - | - |
| `develop` | Integration branch. Always green. | `main` | `release/*` |
| `feature/F-nnn-<slug>` | One feature from `02-spec/features/F-nnn.md`. | `develop` | `develop` |
| `fix/D-nnn-<slug>` | One defect found in system QA. | `develop` | `develop` |
| `release/vX.Y.Z` | Release docs, version bump, final QA. | `develop` | `main` and back into `develop` |
| `hotfix/<slug>` | Urgent fix to a released version. | `main` | `main` and `develop` |

Never commit directly to `main` or `develop`.

## Commits (Conventional Commits)
`<type>(<scope>): <summary>`, where the scope is the feature or defect ID:
- `feat(F-003): add job requisition approval service`
- `fix(D-012): reject offer withdrawal after acceptance`
- `test(F-003): API tests for requisition approval`
- Other types: `refactor`, `docs`, `chore`, `ci`, `build`.

## Pull requests
- One feature or defect per PR, into `develop`. Use the PR template.
- Merge only when CI is green: lint, unit, API and integration tests, frontend build, and Docker build.
- The MVC layer check and the file ownership check must pass (see `docs/STRUCTURE.md`).
- Merge with `--no-ff`, so each feature stays visible in history.

## Releases
1. `git checkout -b release/vX.Y.Z develop`, then update `CHANGELOG.md` and the docs.
2. Merge into `main` with `--no-ff` and tag `vX.Y.Z`.
3. Merge `main` back into `develop`.
"""

PR_TEMPLATE = """## Feature / defect
- ID: F-nnn / D-nnn
- Spec: `02-spec/features/F-nnn.md`
- Requirements: FR-..., NFR-...

## What changed
<!-- one line per MVC layer touched -->

## Checklist
- [ ] Follows the MVC dependency rule: Controller -> Service -> Repository -> Model
- [ ] Lint and type checks pass with zero errors
- [ ] Unit tests for services, API tests for controllers; all acceptance criteria covered
- [ ] Migrations reviewed (no destructive change without a migration plan)
- [ ] No secrets, credentials or `.env` committed
- [ ] `CHANGELOG.md` updated (for releases)
"""

ISSUE_FEATURE = """---
name: Feature
about: A feature from the approved specification
labels: feature
---
**Feature ID:** F-nnn
**Spec:** `02-spec/features/F-nnn.md`
**Requirements:** FR-...

### Acceptance criteria
- [ ] ...
"""

ISSUE_DEFECT = """---
name: Defect
about: A reproducible defect
labels: bug
---
**Defect ID:** D-nnn   **Feature:** F-nnn   **Severity:** critical / high / medium / low

### Steps to reproduce
1. ...

### Expected
### Actual
### Evidence (logs, test output)
"""


def structure_doc(stack) -> str:
    be = stack["backend"]
    layer_root = {"fastapi": "backend/app", "python": "backend/app", "node": "backend/src",
                  "spring": "backend/src/main/java/app", "dotnet": "backend/src"}[be]
    return f"""# Project structure (MVC)

Every request flows **View -> Controller -> Service -> Repository -> Model**. A layer may only call the
layer below it. This is enforced by the MVC layer check, lint and code review.

| Folder | Layer | Rule |
|---|---|---|
| `{layer_root}/` controllers | Controller | HTTP only: validate input DTOs, call one service, map the result. No business logic, no data access. |
| `{layer_root}/` services | Service | Business rules, authorization decisions, transactions. Calls repositories. |
| `{layer_root}/` repositories | Repository | Data access only. Returns models. |
| `{layer_root}/` models | Model | ORM entities and constraints. |
| `{layer_root}/` schemas / dto | DTO | Request and response shapes. No logic. |
| `{layer_root}/` core / config | Cross-cutting | Configuration, security, DB session, error envelope `{{code, message, details}}`, logging. |
| `backend/tests/` | Tests | `unit/` (services), `api/` (controllers), `integration/`. |
| `frontend/src/views/` | View | Screens. Use controllers and components only. |
| `frontend/src/components/` | View | Presentational, reusable. |
| `frontend/src/controllers/` | Controller (UI) | Hooks or state connecting views to services. |
| `frontend/src/services/`, `api/` | Service (UI) | API calls on top of the shared client. |
| `e2e/`, `perf/` | Tests | End-to-end (one per main user flow) and load checks. |
| `docs/`, `deploy/` | Docs | Documentation and the deployment guide. |

The architecture and detailed standards are in the project's specification (`02-spec/architecture.md`,
`02-spec/coding-standards.md`).
"""


def readme(name, ts, stack) -> str:
    def s(part):
        d = ts.get(part, {})
        return " / ".join(x for x in (d.get("language"), d.get("framework") or d.get("engine")) if x) or "-"
    return f"""# {name}

Generated by the Agentic SDLC Platform from the approved FRD. Built feature by feature in Phase 3.

| Part | Stack |
|---|---|
| Frontend | {s('frontend')} |
| Backend | {s('backend')} |
| Database | {s('database')} |
| Architecture | MVC (Controller -> Service -> Repository -> Model) |

## Layout
```
.github/        CI workflow, PR and issue templates
backend/        MVC backend + Dockerfile + tests/
frontend/       MVC frontend + Dockerfile
e2e/  perf/     end-to-end and performance tests
docs/           documentation (STRUCTURE.md explains the layers)
deploy/         deployment guide
docker-compose.yml, .env.example
```

## Run locally
```
cp .env.example .env      # placeholder values; never commit .env
docker compose up --build
```

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for the git workflow (main / develop / feature/F-nnn).
"""


def plan_files(pdir) -> dict[str, str]:
    ts = read_json(pdir / "01-frd" / "tech-stack.json")
    stack = detect(ts)
    files: dict[str, str] = {
        "README.md": readme(pdir.name, ts, stack),
        "CONTRIBUTING.md": CONTRIBUTING,
        "CHANGELOG.md": "# Changelog\n\nAll notable changes, newest first (Keep a Changelog format).\n\n## [Unreleased]\n",
        ".gitignore": GITIGNORE,
        ".gitattributes": GITATTRIBUTES,
        ".editorconfig": EDITORCONFIG,
        ".env.example": env_example(stack),
        "docker-compose.yml": compose(stack),
        ".github/workflows/ci.yml": ci_workflow(stack),
        ".github/pull_request_template.md": PR_TEMPLATE,
        ".github/ISSUE_TEMPLATE/feature.md": ISSUE_FEATURE,
        ".github/ISSUE_TEMPLATE/defect.md": ISSUE_DEFECT,
        "docs/STRUCTURE.md": structure_doc(stack),
        "backend/Dockerfile": BACKEND_DOCKERFILE[stack["backend"]],
        "backend/.dockerignore": ".venv\n__pycache__\nnode_modules\ntests\n.env\n",
    }
    if stack["frontend"] != "none":
        dist = "build /src/dist/browser" if stack["frontend"] == "angular" else "build /src/dist"
        files["frontend/Dockerfile"] = FRONTEND_DOCKERFILE.format(dist=dist)
        files["frontend/.dockerignore"] = "node_modules\ndist\ncoverage\n.env\n"
    if ts.get("architecture_pattern", "MVC") == "MVC":
        dirs = BACKEND_DIRS[stack["backend"]] + FRONTEND_DIRS[stack["frontend"]] + COMMON_DIRS
    else:  # framework convention: the architect defines the folders in 02-spec/architecture.md + ownership.yaml
        dirs = ["backend", "backend/tests"] + (["frontend"] if stack["frontend"] != "none" else []) + COMMON_DIRS
        files["docs/STRUCTURE.md"] = (f"# Project structure ({ts['architecture_pattern']})\n\n"
                                      f"{ts.get('pattern_rationale', '')}\n\nThe folder convention is defined in "
                                      f"Phase 2 (02-spec/architecture.md and 02-spec/ownership.yaml).\n")
    for d in dirs:
        if stack["backend"] in ("fastapi", "python") and d.startswith("backend/app/"):
            files.setdefault(f"{d}/__init__.py", "")
        else:
            files.setdefault(f"{d}/.gitkeep", "")
    if stack["backend"] in ("fastapi", "python") and ts.get("architecture_pattern", "MVC") == "MVC":
        files["backend/app/__init__.py"] = ""
    return files


# ---------- git ----------
def _git(app: Path, *args, check=True):
    return subprocess.run(["git", "-C", str(app), *args], capture_output=True, text=True, check=check)


def init_repo(app: Path) -> str:
    if (app / ".git").exists():
        return "git repository already present (left unchanged)"
    subprocess.run(["git", "init", "-q", str(app)], check=True, capture_output=True)
    _git(app, "symbolic-ref", "HEAD", "refs/heads/main")
    if not _git(app, "config", "user.email", check=False).stdout.strip():
        _git(app, "config", "user.name", "SDLC Platform")
        _git(app, "config", "user.email", "sdlc-platform@localhost")
    _git(app, "add", "-A")
    _git(app, "commit", "-q", "-m", "chore: scaffold application repository (MVC, git workflow, CI, Docker)")
    _git(app, "branch", "develop")
    _git(app, "checkout", "-q", "develop")
    return "git repository initialised: main (scaffold commit) + develop (checked out)"


def create(pdir) -> tuple[Path, list[str], str]:
    app = app_dir(pdir)
    created = []
    for relpath, content in plan_files(pdir).items():
        p = app / relpath
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        created.append(relpath)
    try:
        git_msg = init_repo(app)
    except (OSError, subprocess.CalledProcessError) as e:
        git_msg = f"WARNING: git setup failed ({e}); run `python tools/scaffold.py init` again once git works"
    return app, created, git_msg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "show"])
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    if a.cmd == "show":
        print(f"{rel(app_dir(pdir))}  stack={detect(read_json(pdir / '01-frd' / 'tech-stack.json'))}")
        return
    from gate import run_gate
    errs = run_gate("frd-approved", pdir)
    if errs:
        print("REFUSED: the app repository is created only after FRD approval:")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    app, created, git_msg = create(pdir)
    print(f"SCAFFOLD {rel(app)}: {len(created)} file(s) created")
    print(f"  {git_msg}")


if __name__ == "__main__":
    main()
