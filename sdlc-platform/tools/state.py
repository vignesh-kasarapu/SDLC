#!/usr/bin/env python
"""Deterministic project + feature state machine (roadmap §4.5, §9.1).

Usage:
  state.py init <name> [--domain D] [--force]   create projects/<id>/ and make it active
  state.py use <project-id>                       switch active project
  state.py show [--json]                          human-readable status
  state.py phase <frd|wireframes|spec|build|qa|release> <status>
  state.py start <agent> [--key K] [--prompt-chars N]          mark an agent run's start
  state.py log <agent> <event> [--detail TEXT] [--key K] [--inputs a,b] [--outputs c,d]
                                                  audit + usage log: model, duration (from start),
                                                  prompt/input/output size, estimated tokens
  state.py lock <path>...                         record sha256 locks (enforced by lock_guard hook)
  state.py load-plan                              import features from 02-spec/plan.json
  state.py refresh                                promote Pending -> Ready when deps are Completed
  state.py next [--claim]                         print next Ready feature (claim => InProgress)
  state.py transition <F-ID> <State> [--note T]   guarded lifecycle transition
  state.py complete <F-ID> --evidence <path>      Testing -> Completed with evidence
  state.py features                               list features
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (PHASE_DIRS, PROJECTS, ACTIVE_FILE, ROOT, agent_model, die, now,
                    project_dir, read_json, rel, sha256, slug, write_json)

MAX_RETRIES = 3

TRANSITIONS = {
    "Pending": {"Ready", "Blocked"},
    "Ready": {"InProgress", "Blocked"},
    "InProgress": {"Integrating", "Blocked"},
    "Integrating": {"Testing", "FixRequired", "Blocked"},
    "Testing": {"FixRequired", "Completed", "Blocked"},
    "FixRequired": {"InProgress", "Blocked"},
    "Blocked": {"Ready", "Pending"},
    "Completed": set(),
}

PHASES = ["frd", "wireframes", "spec", "build", "qa", "release"]
PHASE_STATUSES = {"not_started", "in_progress", "evaluated", "passed", "approved",
                  "rejected", "completed", "blocked", "skipped"}


def state_path(pdir):
    return pdir / "state.json"


def load(pdir):
    st = read_json(state_path(pdir))
    for p in PHASES:  # projects created before a phase existed
        st.setdefault("phases", {}).setdefault(p, "not_started")
    return st


def save(pdir, st):
    st["updated_at"] = now()
    write_json(state_path(pdir), st)


def append_history(st, event, **kw):
    st.setdefault("history", []).append({"at": now(), "event": event, **kw})


def cmd_init(a):
    pid = slug(a.name)
    pdir = PROJECTS / pid
    if pdir.exists() and not a.force:
        die(f"project '{pid}' already exists (use --force to re-init state)")
    for d in PHASE_DIRS:
        (pdir / d).mkdir(parents=True, exist_ok=True)
    st = {
        "project_id": pid,
        "name": a.name,
        "domain": a.domain,
        "created_at": now(),
        "phases": {p: "not_started" for p in PHASES},
        "locks": {},
        "features": {},
        "history": [],
    }
    append_history(st, "project_created")
    save(pdir, st)
    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(pid, encoding="utf-8")
    print(f"created {rel(pdir)} (active project = {pid})")


def cmd_use(a):
    project_dir(a.project)
    ACTIVE_FILE.write_text(a.project, encoding="utf-8")
    print(f"active project = {a.project}")


def cmd_show(a):
    pdir = project_dir()
    st = load(pdir)
    if a.json:
        print(json.dumps(st, indent=2))
        return
    print(f"Project : {st['name']} ({st['project_id']})  domain={st.get('domain') or '?'}")
    print("Phases  : " + "  ".join(f"{p}={st['phases'][p]}" for p in PHASES))
    print(f"Locks   : {len(st['locks'])} file(s)")
    feats = st.get("features", {})
    if feats:
        counts = {}
        for f in feats.values():
            counts[f["status"]] = counts.get(f["status"], 0) + 1
        print("Features: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        for fid, f in sorted(feats.items()):
            deps = ",".join(f.get("depends_on", [])) or "-"
            print(f"  {fid:<8} {f['status']:<12} retries={f.get('retries', 0)} deps={deps}  {f.get('title', '')}")
    print("Recent  :")
    for h in st.get("history", [])[-8:]:
        extra = {k: v for k, v in h.items() if k not in ("at", "event")}
        print(f"  {h['at']}  {h['event']}  {json.dumps(extra) if extra else ''}")


def cmd_phase(a):
    if a.phase not in PHASES:
        die(f"phase must be one of {PHASES}")
    if a.status not in PHASE_STATUSES:
        die(f"status must be one of {sorted(PHASE_STATUSES)}")
    pdir = project_dir()
    st = load(pdir)
    old = st["phases"][a.phase]
    st["phases"][a.phase] = a.status
    append_history(st, "phase_status", phase=a.phase, old=old, new=a.status)
    save(pdir, st)
    print(f"phase {a.phase}: {old} -> {a.status}")


def _files_bytes(pdir, csv_paths):
    total = 0
    for p in filter(None, (csv_paths or "").split(",")):
        path = Path(p.strip())
        for cand in (path, ROOT / path, pdir / path):
            if cand.exists():
                total += sum(f.stat().st_size for f in ([cand] if cand.is_file() else cand.rglob("*")) if f.is_file())
                break
    return total


def cmd_start(a):
    """Mark the start of an agent run; `log` with the same agent and --key computes its duration."""
    pdir = project_dir()
    runs_file = pdir / "03-build" / "logs" / "open-runs.json"
    runs = json.loads(runs_file.read_text(encoding="utf-8")) if runs_file.exists() else {}
    runs[f"{a.agent}|{a.key or ''}"] = {"started": now(), "prompt_chars": a.prompt_chars or 0}
    runs_file.parent.mkdir(parents=True, exist_ok=True)
    runs_file.write_text(json.dumps(runs, indent=1), encoding="utf-8")
    print(f"started {a.agent}{' ' + a.key if a.key else ''}")


def cmd_log(a):
    import datetime as dt
    pdir = project_dir()
    st = load(pdir)
    phase = next((ph for ph, s in st.get("phases", {}).items() if s == "in_progress"), None)
    entry = {"at": now(), "agent": a.agent, "model": agent_model(a.agent), "event": a.event,
             "detail": a.detail, "phase": phase, "key": a.key}
    runs_file = pdir / "03-build" / "logs" / "open-runs.json"
    runs = json.loads(runs_file.read_text(encoding="utf-8")) if runs_file.exists() else {}
    run = runs.pop(f"{a.agent}|{a.key or ''}", None)
    if run:
        started = dt.datetime.fromisoformat(run["started"])
        entry["duration_s"] = round((dt.datetime.fromisoformat(entry["at"]) - started).total_seconds())
        runs_file.write_text(json.dumps(runs, indent=1), encoding="utf-8")
    prompt = a.prompt_chars or (run or {}).get("prompt_chars", 0)
    in_bytes, out_bytes = _files_bytes(pdir, a.inputs), _files_bytes(pdir, a.outputs)
    if prompt or in_bytes or out_bytes:
        entry.update({"prompt_chars": prompt, "input_bytes": in_bytes, "output_bytes": out_bytes,
                      "est_tokens_in": (prompt + in_bytes) // 4, "est_tokens_out": out_bytes // 4})
    entry = {k: v for k, v in entry.items() if v not in (None, "")}
    log = pdir / "03-build" / "logs" / "agents.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    extra = f" {entry['duration_s']}s" if "duration_s" in entry else ""
    print(f"logged {a.agent} [{entry['model']}] {a.event}{extra}")


def cmd_lock(a):
    pdir = project_dir()
    st = load(pdir)
    from pathlib import Path
    keys = []
    for p in a.paths:
        path = Path(p) if Path(p).is_absolute() else ROOT / p
        if not path.exists():
            die(f"cannot lock missing file {p}")
        key = rel(path)
        st["locks"][key] = {"sha256": sha256(path), "locked_at": now()}
        keys.append(key)
        print(f"locked {key}")
    append_history(st, "locked", paths=keys)
    save(pdir, st)


def cmd_load_plan(a):
    pdir = project_dir()
    st = load(pdir)
    plan = read_json(pdir / "02-spec" / "plan.json")
    feats = {}
    for f in plan["features"]:
        prev = st.get("features", {}).get(f["id"], {})
        feats[f["id"]] = {
            "title": f.get("title", ""),
            "depends_on": f.get("depends_on", []),
            "group": f.get("group"),
            "status": prev.get("status", "Pending"),
            "retries": prev.get("retries", 0),
            "evidence": prev.get("evidence"),
            "history": prev.get("history", []),
        }
    st["features"] = feats
    st["execution_order"] = plan.get("order", [])
    append_history(st, "plan_loaded", features=len(feats))
    _refresh(st)
    save(pdir, st)
    print(f"loaded {len(feats)} features")


def _set_status(st, fid, new, note=None):
    f = st["features"][fid]
    old = f["status"]
    if new not in TRANSITIONS.get(old, set()):
        die(f"illegal transition {fid}: {old} -> {new} (allowed: {sorted(TRANSITIONS[old]) or 'none'})")
    if new == "FixRequired":
        if f.get("retries", 0) >= MAX_RETRIES:
            die(f"{fid} reached the retry limit ({MAX_RETRIES}); transition it to Blocked and escalate to a human")
        f["retries"] = f.get("retries", 0) + 1
    if new == "Ready":
        unmet = [d for d in f.get("depends_on", []) if st["features"].get(d, {}).get("status") != "Completed"]
        if unmet:
            die(f"{fid} cannot be Ready; incomplete dependencies: {unmet}")
    if new == "InProgress" and old == "Ready":
        f["retries"] = 0
    f["status"] = new
    f.setdefault("history", []).append({"at": now(), "from": old, "to": new, "note": note})
    append_history(st, "feature_transition", feature=fid, old=old, new=new)


def _refresh(st):
    promoted = []
    for fid, f in st["features"].items():
        if f["status"] == "Pending":
            if all(st["features"].get(d, {}).get("status") == "Completed" for d in f.get("depends_on", [])):
                _set_status(st, fid, "Ready", "dependencies satisfied")
                promoted.append(fid)
    return promoted


def cmd_refresh(a):
    pdir = project_dir()
    st = load(pdir)
    promoted = _refresh(st)
    save(pdir, st)
    print("promoted to Ready: " + (", ".join(promoted) or "none"))


def _ordered_ids(st):
    order = [x for x in st.get("execution_order", []) if x in st["features"]]
    return order + sorted(x for x in st["features"] if x not in order)


def cmd_next(a):
    pdir = project_dir()
    st = load(pdir)
    _refresh(st)
    # Resume an interrupted feature first.
    for fid in _ordered_ids(st):
        if st["features"][fid]["status"] in ("InProgress", "Integrating", "Testing", "FixRequired"):
            save(pdir, st)
            print(f"{fid} RESUME {st['features'][fid]['status']}")
            return
    for fid in _ordered_ids(st):
        if st["features"][fid]["status"] == "Ready":
            if a.claim:
                _set_status(st, fid, "InProgress", "claimed by orchestrator")
            save(pdir, st)
            print(f"{fid} {'CLAIMED' if a.claim else 'READY'}")
            return
    save(pdir, st)
    statuses = {f["status"] for f in st["features"].values()}
    if st["features"] and statuses == {"Completed"}:
        print("ALL_COMPLETE")
        sys.exit(0)
    print("NONE_READY " + json.dumps({k: v["status"] for k, v in st["features"].items()}))
    sys.exit(3)


def cmd_transition(a):
    pdir = project_dir()
    st = load(pdir)
    if a.feature not in st["features"]:
        die(f"unknown feature {a.feature}")
    if a.state == "Completed":
        die("use `state.py complete <F> --evidence <file>` to complete a feature")
    _set_status(st, a.feature, a.state, a.note)
    save(pdir, st)
    f = st["features"][a.feature]
    print(f"{a.feature} -> {a.state} (retries={f.get('retries', 0)}/{MAX_RETRIES})")


def cmd_complete(a):
    from pathlib import Path
    pdir = project_dir()
    st = load(pdir)
    ev = Path(a.evidence)
    if not ev.is_absolute():
        ev = ROOT / ev
    if not ev.exists():
        die(f"evidence file not found: {a.evidence}")
    report = read_json(ev) if ev.suffix == ".json" else None
    if report is not None and report.get("verdict") != "pass":
        die(f"evidence report verdict is '{report.get('verdict')}', not 'pass'")
    _set_status(st, a.feature, "Completed", f"evidence: {rel(ev)}")
    st["features"][a.feature]["evidence"] = rel(ev)
    promoted = _refresh(st)
    save(pdir, st)
    print(f"{a.feature} Completed. Newly ready: {', '.join(promoted) or 'none'}")


def cmd_features(a):
    pdir = project_dir()
    st = load(pdir)
    for fid in _ordered_ids(st):
        f = st["features"][fid]
        print(f"{fid}\t{f['status']}\t{','.join(f.get('depends_on', []))}\t{f.get('title', '')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("name"); p.add_argument("--domain"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("use"); p.add_argument("project"); p.set_defaults(fn=cmd_use)
    p = sub.add_parser("show"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("phase"); p.add_argument("phase"); p.add_argument("status"); p.set_defaults(fn=cmd_phase)
    p = sub.add_parser("start"); p.add_argument("agent"); p.add_argument("--key", help="feature or batch id")
    p.add_argument("--prompt-chars", type=int); p.set_defaults(fn=cmd_start)
    p = sub.add_parser("log"); p.add_argument("agent"); p.add_argument("event"); p.add_argument("--detail", default="")
    p.add_argument("--key", help="same key as `start` (e.g. F-003)"); p.add_argument("--prompt-chars", type=int)
    p.add_argument("--inputs", help="comma-separated files/folders the agent was told to read")
    p.add_argument("--outputs", help="comma-separated files/folders the agent wrote"); p.set_defaults(fn=cmd_log)
    p = sub.add_parser("lock"); p.add_argument("paths", nargs="+"); p.set_defaults(fn=cmd_lock)
    p = sub.add_parser("load-plan"); p.set_defaults(fn=cmd_load_plan)
    p = sub.add_parser("refresh"); p.set_defaults(fn=cmd_refresh)
    p = sub.add_parser("next"); p.add_argument("--claim", action="store_true"); p.set_defaults(fn=cmd_next)
    p = sub.add_parser("transition"); p.add_argument("feature"); p.add_argument("state"); p.add_argument("--note"); p.set_defaults(fn=cmd_transition)
    p = sub.add_parser("complete"); p.add_argument("feature"); p.add_argument("--evidence", required=True); p.set_defaults(fn=cmd_complete)
    p = sub.add_parser("features"); p.set_defaults(fn=cmd_features)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
