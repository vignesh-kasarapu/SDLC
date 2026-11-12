#!/usr/bin/env python
"""Human approval records (roadmap §9.2). Only the human-invoked /approve-* and /reject-* commands call this.

Usage:
  approve.py frd     --by NAME --decision approved|rejected [--comment TEXT]
  approve.py wireframes --by NAME --decision approved|rejected [--comment TEXT]
  approve.py specs   --by NAME --decision approved|rejected [--comment TEXT]
  approve.py release --by NAME --decision approved|rejected [--comment TEXT]

On approval: the gate must pass, the artifacts are sha256-locked in state.json
(the lock_guard hook then blocks edits), and the phase status advances.
FRD approval also creates the application repository app-development/<id>/ (tools/scaffold.py).
"""
from __future__ import annotations

import argparse
import sys

from common import latest_version, project_dir, read_json, rel, write_json, now, ROOT
from gate import run_gate
import state as S


def frd_files(pdir):
    fdir = pdir / "01-frd"
    v = latest_version(fdir, "frd", "json")
    files = [fdir / f"frd.v{v}.md", fdir / f"frd.v{v}.json", fdir / f"eval.v{v}.json",
             fdir / f"checklist.v{v}.json", fdir / "crd.md", fdir / "crd-index.json",
             fdir / "tech-stack.json", fdir / "feature-recommendations.json",
             fdir / f"checklist.v{v}.md"]
    return v, [f for f in files if f.exists()]


def spec_files(pdir):
    sdir = pdir / "02-spec"
    files = [p for p in sorted(sdir.rglob("*")) if p.is_file() and p.name != "approval.json"]
    frd_version = read_json(pdir / "01-frd" / "approval.json", default={}).get("version")
    return frd_version, files  # specs are versioned by the FRD version they were built from


def wireframe_files(pdir):
    from wireframes import latest, wdir
    v = latest(pdir)
    files = [p for p in sorted((wdir(pdir) / f"v{v}").rglob("*")) if p.is_file()] if v else []
    return v, files + [f for f in [wdir(pdir) / "decision.json"] if f.exists()]


def release_files(pdir):
    ddir = pdir / "04-delivery"
    return None, [p for p in sorted(ddir.rglob("*")) if p.is_file() and p.name != "release-approval.json"]


TARGETS = {
    "frd": ("01-frd/approval.json", "frd-quality", frd_files, "frd"),
    "wireframes": ("01b-wireframes/approval.json", "wireframes-check", wireframe_files, "wireframes"),
    "specs": ("02-spec/approval.json", "plan-valid", spec_files, "spec"),
    "release": ("04-delivery/release-approval.json", "qa-passed", release_files, "release"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=TARGETS)
    ap.add_argument("--by", required=True)
    ap.add_argument("--decision", required=True, choices=["approved", "rejected"])
    ap.add_argument("--comment", default="")
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    out_rel, gate, files_fn, phase = TARGETS[a.target]
    version, files = files_fn(pdir)

    if a.decision == "approved":
        errs = run_gate(gate, pdir)
        if errs:
            print(f"REFUSED: cannot approve {a.target}; gate '{gate}' failed:")
            for e in errs:
                print(f"  - {e}")
            sys.exit(1)

    st = S.load(pdir)
    record = {"target": a.target, "decision": a.decision, "by": a.by, "at": now(),
              "comment": a.comment, "version": version,
              "locked_files": [rel(f) for f in files] if a.decision == "approved" else []}
    if a.decision == "approved":
        from common import sha256
        for f in files:
            st["locks"][rel(f)] = {"sha256": sha256(f), "locked_at": now()}
        st["phases"][phase] = "approved"
    else:
        st["phases"][phase] = "rejected"
        if a.target == "wireframes" and a.comment:
            from wireframes import wdir
            fb = wdir(pdir) / "feedback.md"
            n = (fb.read_text(encoding="utf-8").count("## WF-REVIEW-") + 1) if fb.exists() else 1
            with open(fb, "a", encoding="utf-8") as fh:
                fh.write(f"\n## WF-REVIEW-{n} ({now()}, {a.by}, rejected v{version})\n{a.comment}\n")
        if a.target == "frd" and a.comment:
            fb = pdir / "01-frd" / "reviewer-feedback.md"
            with open(fb, "a", encoding="utf-8") as fh:
                n = sum(1 for line in fb.read_text(encoding="utf-8").splitlines() if line.startswith("## REVIEW-")) + 1 if fb.exists() else 1
                fh.write(f"\n## REVIEW-{n} ({now()}, {a.by}, on v{version})\n{a.comment}\n")
    S.append_history(st, f"{a.target}_{a.decision}", by=a.by, version=version)
    S.save(pdir, st)
    write_json(ROOT / rel(pdir) / out_rel, record)
    print(f"{a.target.upper()} {a.decision.upper()} by {a.by}"
          + (f" (version {version})" if version else "")
          + (f"; locked {len(files)} file(s)" if a.decision == "approved" else ""))
    if a.target == "frd" and a.decision == "approved":
        if (pdir / "00-discovery" / "project-facts.json").exists():
            print("APP REPOSITORY: existing application (imported with discover.py) - not scaffolded")
        else:
            from scaffold import create  # every new project gets its app repository at FRD approval
            app, created, git_msg = create(pdir)
            print(f"APP REPOSITORY {rel(app)}: {len(created)} file(s) created; {git_msg}")


if __name__ == "__main__":
    main()
