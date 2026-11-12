#!/usr/bin/env python
"""Deterministic quality / phase gates. Slash commands MUST stop when a gate exits non-zero.

Usage: gate.py <gate> [--project ID]
Gates:
  project          active project exists
  crd-parsed       01-frd/crd.md exists
  frd-exists       at least one frd.vN.md + frd.vN.json
  tech-stack       01-frd/tech-stack.json captured from the user and valid (MVC mandatory)
  frd-quality      latest FRD: schema valid, tech stack captured, sections 19-20 present, every recommended
                   feature decided and accepted ones present, revisions built only from human-approved
                   change plans, sources valid,
                   checklist passed, evaluator verdict pass, no blockers
  frd-approved     01-frd/approval.json decision=approved and locked files unchanged
  wireframes-check the generated wireframe set is complete and valid (required before /approve-wireframes)
  wireframes-ready screens are settled after FRD approval: client wireframes confirmed, generated
                   wireframes approved, or skipped with a reason (required before /generate-specs)
  specs-exist      02-spec core artifacts exist, plus the Markdown spec set: architecture, coding-standards,
                   features, database, api-spec, ui-spec, index and one complete features/F-nnn.md per
                   feature (tools/spec_docs.py check)
  plan-valid       02-spec/plan.json produced by dag.py, trace.json passed
  specs-approved   02-spec/approval.json decision=approved and locked files unchanged
  build-ready      specs approved and features loaded into state
  features-complete every feature Completed
  qa-passed        04-delivery/qa-gate.json passed
"""
from __future__ import annotations

import argparse
import sys

from common import app_dir, latest_version, project_dir, read_json, rel, sha256, ROOT

SPEC_CORE = ["commands.json", "features.json", "schema.sql",
             "openapi.yaml"]  # Markdown docs: spec_docs.check
DEFAULT_STACK = ("fastapi", "react")  # config/ownership.yaml + config/layers.yaml fit this stack only


def g_project(pdir):
    return [] if (pdir / "state.json").exists() else ["state.json missing — run /new-project"]


def g_crd_parsed(pdir):
    if not (pdir / "01-frd" / "crd.md").exists():
        return ["CRD not ingested — run /ingest-crd <file>"]
    pending = read_json(pdir / "01-frd" / "crd-index.json", default={}).get("pending_visuals", [])
    if pending:
        return [f"images/scanned pages not analysed yet: {', '.join(pending)} — run the visual-analyst step of "
                f"/ingest-crd, then python tools/parse_doc.py --attach-visuals"]
    return []


def g_frd_exists(pdir):
    fdir = pdir / "01-frd"
    v = latest_version(fdir, "frd", "json")
    if not v or not (fdir / f"frd.v{v}.md").exists():
        return ["no FRD version found — run /generate-frd"]
    return []


def g_tech_stack(pdir):
    from validate import validate
    ts = pdir / "01-frd" / "tech-stack.json"
    if not ts.exists():
        return ["technology stack not captured from the user — run /set-tech-stack"]
    return [f"tech-stack.json: {e}" for e in validate("tech-stack", ts)]


def _feature_recs(pdir, frd):
    from validate import validate
    fr = pdir / "01-frd" / "feature-recommendations.json"
    if not fr.exists():
        return ["feature recommendations not reviewed — run /recommend-features"]
    errs = [f"feature-recommendations.json: {e}" for e in validate("feature-recommendations", fr)]
    if errs:
        return errs
    recs = read_json(fr)["recommended"]
    pending = [r["id"] for r in recs if r["decision"] == "pending"]
    if pending:
        errs.append(f"recommended features without a decision: {pending} — run /recommend-features")
    live = [r for r in frd["requirements"] if r.get("priority") != "wont"]
    cited = {s for r in live for s in r.get("source", [])}
    asked = {x for q in frd.get("open_questions", []) for x in q.get("related", []) + q.get("source", [])}
    for r in recs:
        if r["decision"] == "accepted" and r["id"] not in cited:
            errs.append(f"accepted feature {r['id']} ({r['title']}) has no requirement with source {r['id']} — run /revise-frd")
        if r["decision"] == "ask_client" and r["id"] not in asked:
            errs.append(f"{r['id']} is marked 'ask client' but no open question references it — run /revise-frd")
    return errs


def _change_plan(pdir, v, frd):
    """Every revision (v>1) must come from a change plan the human reviewed, applying exactly what they approved."""
    if v <= 1:
        return []
    from validate import validate
    cp = pdir / "01-frd" / f"change-plan.v{v}.json"
    if not cp.exists():
        return [f"frd.v{v} has no reviewed change plan (01-frd/change-plan.v{v}.json) — revisions must be "
                f"proposed and approved before they are written"]
    errs = [f"change-plan.v{v}.json: {e}" for e in validate("change-plan", cp)]
    if errs:
        return errs
    plan = read_json(cp)["changes"]
    pending = [c["id"] for c in plan if c["decision"] == "pending"]
    if pending:
        errs.append(f"change-plan.v{v} has undecided changes: {pending}")
    wanted = {c["id"] for c in plan if c["decision"] in ("approved", "edited")}
    applied = {e["change_id"] for e in frd.get("change_log", []) if e.get("applied")}
    if wanted - applied:
        errs.append(f"approved changes not applied in frd.v{v}: {sorted(wanted - applied)}")
    if applied - wanted:
        errs.append(f"frd.v{v} applied changes the human did not approve: {sorted(applied - wanted)}")
    return errs


def g_frd_quality(pdir):
    errs = g_frd_exists(pdir)
    if errs:
        return errs
    from validate import validate
    from traceability import check_frd
    fdir = pdir / "01-frd"
    v = latest_version(fdir, "frd", "json")
    errs += [f"frd.v{v}.json schema: {e}" for e in validate("requirements", fdir / f"frd.v{v}.json")]
    errs += g_tech_stack(pdir)
    errs += _feature_recs(pdir, read_json(fdir / f"frd.v{v}.json"))
    errs += _change_plan(pdir, v, read_json(fdir / f"frd.v{v}.json"))
    md = (fdir / f"frd.v{v}.md").read_text(encoding="utf-8")
    for heading in ("## 19. Technology stack", "## 20. Architecture pattern and programming standards"):
        if heading not in md:
            errs.append(f"frd.v{v}.md is missing section '{heading[3:]}'")
    from frd_intake import is_intake, check as intake_check
    if is_intake(pdir):  # the client's FRD is kept verbatim; requirements quote it
        errs += intake_check(pdir, v)
    tr = check_frd(pdir, v)
    errs += tr["invalid_sources"]
    ck = fdir / f"checklist.v{v}.json"
    if not ck.exists():
        errs.append(f"checklist not run for v{v} — run tools/checklist.py")
    else:
        c = read_json(ck)
        if c["summary"]["mandatory_failed"]:
            errs.append(f"mandatory checklist failures: {c['summary']['mandatory_failed']}")
        if c["summary"]["conditional_failed"]:
            errs.append(f"applicable conditional checklist failures: {c['summary']['conditional_failed']}")
    ev = fdir / f"eval.v{v}.json"
    if not ev.exists():
        errs.append(f"evaluation missing for v{v} — run /evaluate-frd")
    else:
        e = read_json(ev)
        errs += [f"eval.v{v}.json schema: {x}" for x in validate("evaluation", ev)]
        if e.get("frd_version") != v:
            errs.append(f"eval.v{v}.json evaluates version {e.get('frd_version')}, not {v}")
        blockers = [i["id"] for i in e.get("issues", []) if i.get("severity") == "blocker"]
        low = [d for d, s in e.get("dimensions", {}).items() if s.get("score", 0) < 3]
        if blockers:
            errs.append(f"evaluator blocker issues: {blockers}")
        if low:
            errs.append(f"dimensions scored below 3: {low}")
        if e.get("verdict") != "pass" and not blockers and not low:
            errs.append("evaluator verdict is 'fail'")
    frd = read_json(fdir / f"frd.v{v}.json")
    blocking_q = [q["id"] for q in frd.get("open_questions", []) if q.get("blocking") and not q.get("resolution")]
    if blocking_q:
        errs.append(f"unresolved blocking open questions: {blocking_q} (answer them via /revise-frd)")
    return errs


def _approval_ok(pdir, sub):
    appr = read_json(pdir / sub / "approval.json", default={})
    if appr.get("decision") != "approved":
        return [f"{sub} not approved (decision={appr.get('decision', 'none')})"]
    errs = []
    st = read_json(pdir / "state.json")
    for path in appr.get("locked_files", []):
        lock = st["locks"].get(path)
        p = ROOT / path
        if not lock or not p.exists() or sha256(p) != lock["sha256"]:
            errs.append(f"locked artifact modified or missing since approval: {path}")
    return errs


def g_frd_approved(pdir):
    errs = _approval_ok(pdir, "01-frd")
    if not errs:
        appr = read_json(pdir / "01-frd" / "approval.json")
        latest = latest_version(pdir / "01-frd", "frd", "json")
        if appr.get("version") != latest:
            errs.append(f"approved version is v{appr.get('version')} but latest FRD is v{latest} — re-approve with /approve-frd")
    return errs


def g_wireframes_check(pdir):
    from wireframes import check_errors
    return check_errors(pdir)


def g_wireframes_ready(pdir):
    from wireframes import ready_errors
    return ready_errors(pdir)


def g_specs_exist(pdir):
    errs = g_wireframes_ready(pdir)
    sdir = pdir / "02-spec"
    errs += [f"missing 02-spec/{f}" for f in SPEC_CORE if not (sdir / f).exists()]
    ts = read_json(pdir / "01-frd" / "tech-stack.json", default={})
    stack = (ts.get("backend", {}).get("framework", "") + " " + ts.get("frontend", {}).get("framework", "")).lower()
    custom = ts and (not all(k in stack for k in DEFAULT_STACK) or ts.get("architecture_pattern", "MVC") != "MVC")
    if custom and not (sdir / "ownership.yaml").exists():
        errs.append("non-default stack or pattern: architect must write 02-spec/ownership.yaml (and layers.yaml "
                    "where layers apply) for the project's folders")
    if (sdir / "features.json").exists():
        for f in read_json(sdir / "features.json")["features"]:
            if not (sdir / "features" / f"{f['id']}.md").exists():
                errs.append(f"missing feature spec 02-spec/features/{f['id']}.md")
    from spec_docs import check as spec_docs_check  # Markdown docs, feature-spec structure, contract consistency
    errs += spec_docs_check(pdir)
    return errs


def g_plan_valid(pdir):
    errs = g_specs_exist(pdir)
    sdir = pdir / "02-spec"
    plan = read_json(sdir / "plan.json", default={})
    if not plan.get("valid"):
        errs.append("plan.json missing or invalid — run /plan-features (tools/dag.py)")
    tr = read_json(sdir / "trace.json", default={})
    if not tr.get("passed"):
        errs.append("requirement->feature trace missing or failing — run tools/traceability.py spec")
    return errs


def g_specs_approved(pdir):
    errs = g_frd_approved(pdir) + _approval_ok(pdir, "02-spec")
    if not errs:
        frd_v = read_json(pdir / "01-frd" / "approval.json").get("version")
        spec_v = read_json(pdir / "02-spec" / "approval.json").get("version")
        if spec_v != frd_v:
            errs.append(f"specs were approved against FRD v{spec_v}, but the approved FRD is v{frd_v} — regenerate specs")
    return errs


def g_build_ready(pdir):
    errs = g_specs_approved(pdir)
    st = read_json(pdir / "state.json")
    if not st.get("features"):
        errs.append("features not loaded into state — /approve-specs runs `state.py load-plan`")
    if not (app_dir(pdir) / ".git").exists():
        errs.append(f"{rel(app_dir(pdir))} repository missing — it is created at FRD approval; run python tools/scaffold.py init")
    return errs


def g_features_complete(pdir):
    st = read_json(pdir / "state.json")
    if not st.get("features"):
        return ["no features in state"]
    return [f"{fid} is {f['status']}" for fid, f in st["features"].items() if f["status"] != "Completed"]


def g_qa_passed(pdir):
    q = read_json(pdir / "04-delivery" / "qa-gate.json", default={})
    if not q.get("passed"):
        return ["QA gate not passed — run /qa-system"] + q.get("failures", [])
    return []


GATES = {
    "project": g_project, "crd-parsed": g_crd_parsed, "frd-exists": g_frd_exists, "tech-stack": g_tech_stack,
    "frd-quality": g_frd_quality, "frd-approved": g_frd_approved, "wireframes-check": g_wireframes_check,
    "wireframes-ready": g_wireframes_ready, "specs-exist": g_specs_exist,
    "plan-valid": g_plan_valid, "specs-approved": g_specs_approved, "build-ready": g_build_ready,
    "features-complete": g_features_complete, "qa-passed": g_qa_passed,
}


def run_gate(name, pdir):
    return GATES[name](pdir)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gate", choices=sorted(GATES))
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    errs = run_gate(a.gate, pdir)
    if errs:
        print(f"GATE FAILED: {a.gate} ({rel(pdir)})")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    print(f"GATE PASSED: {a.gate}")


if __name__ == "__main__":
    main()
