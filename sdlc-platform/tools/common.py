"""Shared helpers for the SDLC platform tools (stdlib + pyyaml + jsonschema)."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent          # the shareable platform folder (open Claude Code here)
# Client data and generated apps live NEXT TO the platform folder, never inside it:
#   <workspace>/sdlc-platform/   <workspace>/projects/   <workspace>/app-development/
WORKSPACE = Path(os.environ.get("SDLC_WORKSPACE") or ROOT.parent).resolve()
PROJECTS = WORKSPACE / "projects"
ACTIVE_FILE = PROJECTS / ".active"
SCHEMAS = ROOT / "schemas"
KNOWLEDGE = ROOT / "knowledge" / "domains"
AGENTS_DIR = ROOT / ".claude" / "agents"
APP_ROOT = WORKSPACE / "app-development"  # generated application repositories, one per project

PHASE_DIRS = ["input", "01-frd", "02-spec", "02-spec/features", "03-build",
              "03-build/defects", "03-build/briefs", "03-build/logs", "03-build/reports",
              "04-delivery", "04-delivery/reports", "04-delivery/defects"]


def app_dir(pdir) -> Path:
    """The project's application repository: app-development/<project-id>/ (created by scaffold.py)."""
    return APP_ROOT / Path(pdir).name


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "project"


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        die(f"missing file: {rel(path)}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def read_yaml(path: Path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    try:
        return Path(os.path.relpath(Path(path).resolve(), ROOT)).as_posix()  # e.g. ../projects/<id>/01-frd/frd.v1.md
    except ValueError:  # different drive on Windows
        return Path(path).as_posix()


def active_project_id(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("SDLC_PROJECT")
    if env:
        return env
    if ACTIVE_FILE.exists():
        pid = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        if pid:
            return pid
    die("no active project. Run /new-project <name> first (or set SDLC_PROJECT).")


def project_dir(pid: str | None = None) -> Path:
    pid = active_project_id(pid)
    d = PROJECTS / pid
    if not d.exists():
        die(f"project '{pid}' does not exist under {PROJECTS}")
    return d


def latest_version(directory: Path, prefix: str, ext: str) -> int:
    """Highest N for files named <prefix>.vN.<ext>; 0 if none."""
    best = 0
    pat = re.compile(rf"^{re.escape(prefix)}\.v(\d+)\.{re.escape(ext)}$")
    if Path(directory).exists():
        for p in Path(directory).iterdir():
            m = pat.match(p.name)
            if m:
                best = max(best, int(m.group(1)))
    return best


def agent_model(agent: str) -> str:
    """Model declared in the agent's frontmatter (for audit logs)."""
    p = AGENTS_DIR / f"{agent}.md"
    if not p.exists():
        return "unknown"
    for line in p.read_text(encoding="utf-8").splitlines()[1:40]:
        if line.strip() == "---":
            break
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return "inherit"
