"""End-to-end tests for the deterministic platform tools.

Each test runs the real CLI tools against a throw-away project under projects/zz-test-*,
then restores projects/.active and deletes the project.
Run: python -m pytest tools/tests -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
PROJECTS = ROOT.parent / "projects"  # data lives next to the platform folder
ACTIVE = PROJECTS / ".active"


def run(*args, ok=True, stdin=None):
    r = subprocess.run([sys.executable, str(TOOLS / args[0]), *map(str, args[1:])],
                       capture_output=True, text=True, cwd=ROOT, input=stdin)
    if ok is True:
        assert r.returncode == 0, f"{args} failed:\n{r.stdout}\n{r.stderr}"
    elif ok is False:
        assert r.returncode != 0, f"{args} unexpectedly succeeded:\n{r.stdout}"
    return r


@pytest.fixture
def project():
    prev = ACTIVE.read_text(encoding="utf-8") if ACTIVE.exists() else None
    name = f"zz-test-{uuid.uuid4().hex[:8]}"
    run("state.py", "init", name)
    pdir = PROJECTS / name
    try:
        yield pdir
    finally:
        # Restore the user's active project FIRST, whatever happens during cleanup.
        if prev is None:
            ACTIVE.unlink(missing_ok=True)
        else:
            ACTIVE.write_text(prev, encoding="utf-8")
        _remove_tree(pdir)
        _remove_tree(ROOT.parent / "app-development" / name)


def _remove_tree(path: Path):
    """Best-effort delete. Git objects are read-only on Windows, and IDE git watchers may
    briefly hold the nested repository open, so retry a few times."""
    import time

    def _force(func, p, *_):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass

    for _ in range(10):
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_force)
        else:
            shutil.rmtree(path, onerror=_force)
        if not path.exists():
            return
        time.sleep(0.5)


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) if not isinstance(data, str) else data, encoding="utf-8")


# ---------------------------------------------------------------- fixtures

def req(rid, title, statement, refs, src=("C-005",), status="confirmed", prio="must"):
    rtype = {"FR": "functional", "NFR": "non_functional", "BR": "business_rule", "SR": "security",
             "IR": "integration", "DR": "data"}[rid.split("-")[0]]
    return {"id": rid, "type": rtype, "title": title, "statement": statement, "priority": prio,
            "source": list(src), "acceptance_criteria": [f"Given a user, when {title.lower()}, then it works"],
            "status": status, "checklist_refs": list(refs)}


def full_frd():
    return {"version": 1, "open_questions": [], "requirements": [
        req("FR-001", "Login", "Users log in with company email and password to authenticate.", ["GEN-AUTH"]),
        req("SR-001", "Role permissions", "Role-based permission checks restrict functions per role.", ["GEN-RBAC"]),
        req("FR-002", "Input validation", "Invalid input is rejected with a clear error message.", ["GEN-VALIDATION"]),
        req("SR-002", "Personal data privacy", "Personal data is visible only to HR and the manager.", ["GEN-PRIVACY"]),
        req("FR-003", "Leave email notification", "An email notification is sent when leave is applied, approved or rejected.", ["GEN-NOTIFY"]),
        req("IR-001", "Payroll integration", "Unpaid leave days are exported to payroll monthly via an integration file.", ["GEN-INTEGRATION", "LMS-PAYROLL"]),
        req("FR-004", "Leave report", "HR can view a leave report and export it.", ["GEN-REPORTING", "LMS-REPORTS"]),
        req("FR-005", "Employee records", "HR maintains the employee record with department and reporting manager.", ["LMS-EMP"]),
        req("FR-006", "Leave type configuration", "HR admin can configure each leave type and its policy.", ["LMS-HR-ADMIN", "LMS-LEAVE-TYPES"]),
        req("FR-007", "Apply for leave", "An employee submits a leave application for a date range.", ["LMS-APPLY"]),
        req("FR-008", "Approve leave", "The manager can approve or reject a request with a comment.", ["LMS-APPROVAL"]),
        req("FR-009", "Leave balance", "The leave balance is reduced when leave is approved.", ["LMS-BALANCE"]),
        req("FR-010", "Cancel leave", "An employee can cancel a pending request.", ["LMS-CANCEL"]),
        req("BR-001", "Overlap and balance check", "Overlapping requests or requests that exceed the available balance are rejected.", ["LMS-OVERLAP"]),
        req("FR-011", "Medical certificate", "Employees upload a medical certificate for long sick leave.", ["LMS-ATTACH"]),
    ]}


FRD_MD = "# FRD v1\n## 19. Technology stack\n## 20. Architecture pattern and programming standards\n"


def tech_stack():
    return {"source": "user", "confirmed_by": "Tester", "confirmed_at": "2026-11-10T00:00:00Z",
            "frontend": {"language": "TypeScript", "framework": "React"},
            "backend": {"language": "Python", "framework": "FastAPI"},
            "database": {"engine": "PostgreSQL", "orm": "SQLAlchemy", "migrations": "Alembic"},
            "architecture_pattern": "MVC",
            "coding_standards": ["knowledge/standards/mvc-coding-standards.md", "ruff", "eslint"]}


def feature_recs(decision="rejected"):
    return {"domain": "leave-management", "based_on": ["requirements.json"], "covered": [],
            "recommended": [{"id": "SUG-001", "title": "Team calendar", "description": "Who is on leave",
                             "importance": "recommended", "rationale": "managers", "basis": "domain_checklist",
                             "checklist_refs": ["LMS-TEAM-CAL"], "decision": decision}]}


def good_eval(v=1):
    dims = ["completeness", "clarity", "consistency", "testability", "traceability", "domain_coverage",
            "feasibility", "nfr_coverage"]
    return {"frd_version": v, "dimensions": {d: {"score": 4, "rationale": "ok"} for d in dims},
            "issues": [], "verdict": "pass", "summary": "fine"}


def setup_frd(pdir, frd=None):
    run("parse_doc.py", ROOT / "samples" / "leave_crd.md")
    write(pdir / "01-frd" / "domain.json", {"domain": "leave-management", "subdomain": "corporate-leave",
                                            "confidence": 0.9, "known_domain_pack": True,
                                            "evidence": [{"source": "C-001", "quote": "Leave"}]})
    write(pdir / "01-frd" / "frd.v1.json", frd or full_frd())
    write(pdir / "01-frd" / "frd.v1.md", FRD_MD)
    write(pdir / "01-frd" / "tech-stack.json", tech_stack())
    write(pdir / "01-frd" / "feature-recommendations.json", feature_recs())


# ---------------------------------------------------------------- tests

def test_parse_markdown_assigns_stable_ids(project):
    run("parse_doc.py", ROOT / "samples" / "leave_crd.md")
    idx = json.loads((project / "01-frd" / "crd-index.json").read_text(encoding="utf-8"))["blocks"]
    assert "C-001" in idx and idx["C-001"]["kind"] == "heading"
    assert any(b["kind"] == "list" for b in idx.values())
    assert "[C-001]" in (project / "01-frd" / "crd.md").read_text(encoding="utf-8")


def test_parse_docx_with_stdlib(project, tmp_path):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = (f'<w:document {W}><w:body>'
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Leave System</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Employees apply for leave.</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Type</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Days</w:t></w:r></w:p></w:tc></w:tr>'
            '<w:tr><w:tc><w:p><w:r><w:t>Casual</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>12</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '</w:body></w:document>')
    docx = tmp_path / "crd.docx"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", body)
    run("parse_doc.py", docx)
    idx = json.loads((project / "01-frd" / "crd-index.json").read_text(encoding="utf-8"))["blocks"]
    kinds = [b["kind"] for b in idx.values()]
    assert kinds == ["heading", "para", "table"]
    assert "| Casual | 12 |" in idx["C-003"]["text"]


def test_checklist_passes_with_full_coverage(project):
    setup_frd(project)
    r = run("checklist.py")
    assert "PASSED" in r.stdout
    res = json.loads((project / "01-frd" / "checklist.v1.json").read_text(encoding="utf-8"))
    statutory = next(i for i in res["items"] if i["id"] == "LMS-STATUTORY")
    assert statutory["status"] == "n/a"  # sample CRD never mentions statutory leave


def test_checklist_mandatory_missing_and_weak_fail(project):
    frd = full_frd()
    frd["requirements"] = [r for r in frd["requirements"] if r["id"] != "FR-010"]  # drop cancellation
    frd["requirements"][0]["statement"] = "Users can use the system."               # GEN-AUTH tag w/o evidence
    frd["requirements"][0]["title"] = "Access"
    frd["requirements"][0]["acceptance_criteria"] = ["it works"]
    setup_frd(project, frd)
    r = run("checklist.py", ok=False)
    res = json.loads((project / "01-frd" / "checklist.v1.json").read_text(encoding="utf-8"))
    status = {i["id"]: i["status"] for i in res["items"]}
    assert status["LMS-CANCEL"] == "missing"
    assert status["GEN-AUTH"] == "weak"
    assert "LMS-CANCEL" in res["summary"]["mandatory_failed"]


def test_validate_rejects_confirmed_checklist_assumption(project):
    frd = full_frd()
    frd["requirements"].append(req("FR-012", "Holiday calendar", "Holidays are excluded from the leave count.",
                                   ["LMS-HOLIDAY"], src=("CHECKLIST-LMS-HOLIDAY",), status="confirmed"))
    setup_frd(project, frd)
    r = run("validate.py", "requirements", project / "01-frd" / "frd.v1.json", ok=False)
    assert "must have status 'assumed'" in r.stdout


def test_frd_gate_approval_and_lock_guard(project):
    setup_frd(project)
    run("checklist.py")
    # No evaluation yet -> gate and approval refused.
    run("gate.py", "frd-quality", ok=False)
    r = run("approve.py", "frd", "--by", "Tester", "--decision", "approved", ok=False)
    assert "REFUSED" in r.stdout
    # A blocker issue fails the gate even with good scores.
    ev = good_eval()
    ev["issues"] = [{"id": "E-001", "severity": "blocker", "dimension": "consistency", "description": "x",
                     "evidence": "C-005", "suggested_fix": "y"}]
    write(project / "01-frd" / "eval.v1.json", ev)
    run("gate.py", "frd-quality", ok=False)
    write(project / "01-frd" / "eval.v1.json", good_eval())
    run("gate.py", "frd-quality")
    run("approve.py", "frd", "--by", "Tester", "--decision", "approved")
    run("gate.py", "frd-approved")

    frd_md = project / "01-frd" / "frd.v1.md"
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(frd_md)}, "cwd": str(ROOT)})
    r = run("lock_guard.py", ok=None, stdin=payload)
    assert r.returncode == 2 and "locked" in r.stderr
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(project / "state.json")}})
    assert run("lock_guard.py", ok=None, stdin=payload).returncode == 2
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(project / "01-frd" / "notes.md")}})
    assert run("lock_guard.py", ok=None, stdin=payload).returncode == 0

    # Tampering with a locked file breaks the approval gate.
    frd_md.write_text("# tampered\n", encoding="utf-8")
    run("gate.py", "frd-approved", ok=False)
    frd_md.write_text(FRD_MD, encoding="utf-8")
    # A newer, unapproved version invalidates approval.
    write(project / "01-frd" / "frd.v2.json", full_frd())
    write(project / "01-frd" / "frd.v2.md", FRD_MD)
    r = run("gate.py", "frd-approved", ok=False)
    assert "re-approve" in r.stdout


def test_dag_detects_cycles_and_builds_waves(project):
    feats = {"features": [{"id": f"F-00{i}", "title": t, "description": "d", "requirement_ids": ["FR-001"],
                           "layers": ["backend"]} for i, t in enumerate(["Users", "Employees", "Roles", "Apply"], 1)]}
    write(project / "02-spec" / "features.json", feats)
    edges = [{"from": "F-001", "to": "F-002", "type": "hard", "reason": "fk"},
             {"from": "F-001", "to": "F-003", "type": "hard", "reason": "auth"},
             {"from": "F-002", "to": "F-004", "type": "hard", "reason": "fk"},
             {"from": "F-003", "to": "F-004", "type": "soft", "reason": "ui"}]
    write(project / "02-spec" / "dependencies.json", {"edges": edges})
    r = run("dag.py", "build")
    plan = json.loads((project / "02-spec" / "plan.json").read_text(encoding="utf-8"))
    assert plan["groups"] == [["F-001"], ["F-002", "F-003"], ["F-004"]]
    assert next(f for f in plan["features"] if f["id"] == "F-004")["depends_on"] == ["F-002"]

    edges.append({"from": "F-004", "to": "F-001", "type": "hard", "reason": "cycle"})
    write(project / "02-spec" / "dependencies.json", {"edges": edges})
    r = run("dag.py", "build", ok=False)
    assert "circular" in r.stdout


def test_feature_state_machine(project):
    plan = {"valid": True, "order": ["F-001", "F-002"], "groups": [["F-001"], ["F-002"]],
            "features": [{"id": "F-001", "title": "Users", "depends_on": []},
                         {"id": "F-002", "title": "Leave", "depends_on": ["F-001"]}]}
    write(project / "02-spec" / "plan.json", plan)
    run("state.py", "load-plan")
    st = json.loads((project / "state.json").read_text(encoding="utf-8"))
    assert st["features"]["F-001"]["status"] == "Ready" and st["features"]["F-002"]["status"] == "Pending"

    run("state.py", "transition", "F-002", "Ready", ok=False)          # dependency incomplete
    run("state.py", "transition", "F-001", "Testing", ok=False)        # illegal jump
    assert "F-001 CLAIMED" in run("state.py", "next", "--claim").stdout
    run("state.py", "transition", "F-001", "Integrating")
    run("state.py", "transition", "F-001", "Testing")
    run("state.py", "transition", "F-001", "Completed", ok=False)      # must use complete + evidence

    for _ in range(3):                                                  # 3 fix rounds allowed
        run("state.py", "transition", "F-001", "FixRequired")
        run("state.py", "transition", "F-001", "InProgress")
        run("state.py", "transition", "F-001", "Integrating")
        run("state.py", "transition", "F-001", "Testing")
    r = run("state.py", "transition", "F-001", "FixRequired", ok=False)  # 4th refused
    assert "retry limit" in r.stderr

    bad = project / "03-build" / "reports" / "F-001.test.json"
    write(bad, {"verdict": "fail"})
    run("state.py", "complete", "F-001", "--evidence", bad, ok=False)
    write(bad, {"verdict": "pass"})
    r = run("state.py", "complete", "F-001", "--evidence", bad)
    assert "F-002" in r.stdout                                          # dependent promoted to Ready
    assert "F-002 CLAIMED" in run("state.py", "next", "--claim").stdout


def test_ownership_check(project):
    app = ROOT.parent / "app-development" / project.name
    app.mkdir()
    subprocess.run(["git", "init", "-q", str(app)], check=True)
    (app / "backend" / "app" / "services").mkdir(parents=True)
    (app / "backend" / "app" / "services" / "leave.py").write_text("x = 1\n")
    run("ownership.py", "check", "backend-dev")
    run("ownership.py", "check", "api-dev", ok=False)
    (app / "backend" / "app" / "controllers").mkdir(parents=True)
    (app / "backend" / "app" / "controllers" / "leave_controller.py").write_text("y = 1\n")
    run("ownership.py", "check", "backend-dev", ok=False)
    run("ownership.py", "check", "backend-dev,api-dev")


def test_agent_models_match_config():
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))["agents"]
    agents_dir = ROOT / ".claude" / "agents"
    files = {p.stem for p in agents_dir.glob("*.md")}
    assert files == set(cfg), f"agent files and config differ: {files ^ set(cfg)}"
    for name, m in cfg.items():
        text = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        assert f"name: {name}" in front
        assert f"model: {m['primary']}" in front, f"{name} model differs from config primary"


def test_tech_stack_and_frd_sections_required(project):
    setup_frd(project)
    run("checklist.py")
    write(project / "01-frd" / "eval.v1.json", good_eval())
    run("gate.py", "frd-quality")
    ts = tech_stack()
    ts["architecture_pattern"] = "Layered"                     # MVC is mandatory
    write(project / "01-frd" / "tech-stack.json", ts)
    r = run("gate.py", "frd-quality", ok=False)
    assert "tech-stack.json" in r.stdout
    (project / "01-frd" / "tech-stack.json").unlink()            # never asked the user
    r = run("gate.py", "frd-quality", ok=False)
    assert "/set-tech-stack" in r.stdout
    write(project / "01-frd" / "tech-stack.json", tech_stack())
    write(project / "01-frd" / "frd.v1.md", "# FRD without stack sections\n")
    r = run("gate.py", "frd-quality", ok=False)
    assert "Technology stack" in r.stdout


def test_mvc_layer_check(project):
    app = ROOT.parent / "app-development" / project.name
    files = {
        "backend/app/models/leave.py": "from app.core.db import Base\nclass Leave(Base): pass\n",
        "backend/app/repositories/leave_repository.py": "from app.models.leave import Leave\n",
        "backend/app/services/leave_service.py":
            "from app.repositories.leave_repository import x\nfrom ..schemas import leave_schemas\n",
        "backend/app/controllers/leave_controller.py":
            "from fastapi import APIRouter\nfrom app.services.leave_service import LeaveService\n",
        "backend/app/core/db.py": "import sqlalchemy\n",
        "frontend/src/views/LeaveView.tsx":
            "import { LeaveForm } from '../components/LeaveForm'\nimport { useLeaves } from '../controllers/useLeaves'\n",
        "frontend/src/controllers/useLeaves.ts": "import { getLeaves } from '../services/leaveService'\n",
        "frontend/src/services/leaveService.ts": "import { client } from '../api/client'\n",
    }
    for rel, body in files.items():
        (app / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / rel).write_text(body, encoding="utf-8")
    run("layer_check.py", "--all")
    # Controller reaching into the repository layer + view calling a service directly = violations.
    (app / "backend/app/controllers/leave_controller.py").write_text(
        "from app.repositories.leave_repository import LeaveRepository\n", encoding="utf-8")
    (app / "frontend/src/views/LeaveView.tsx").write_text(
        "import { getLeaves } from '../services/leaveService'\n", encoding="utf-8")
    (app / "backend/app/services/leave_service.py").write_text(
        "from ..controllers import leave_controller\n", encoding="utf-8")
    r = run("layer_check.py", "--all", ok=False)
    assert "[controllers] imports [repositories]" in r.stdout
    assert "[fe-views] imports [fe-services]" in r.stdout
    assert "[services] imports [controllers]" in r.stdout


def test_feature_recommendations_gate(project):
    setup_frd(project)
    run("checklist.py")
    assert (project / "01-frd" / "checklist.v1.md").exists()
    write(project / "01-frd" / "eval.v1.json", good_eval())
    run("gate.py", "frd-quality")                                   # SUG-001 rejected -> fine
    write(project / "01-frd" / "feature-recommendations.json", feature_recs("pending"))
    assert "without a decision" in run("gate.py", "frd-quality", ok=False).stdout
    write(project / "01-frd" / "feature-recommendations.json", feature_recs("accepted"))
    assert "has no requirement with source SUG-001" in run("gate.py", "frd-quality", ok=False).stdout
    frd = full_frd()
    frd["requirements"].append(req("FR-012", "Team calendar", "Managers see a team leave calendar.",
                                   ["LMS-TEAM-CAL"], src=("SUG-001",)))
    write(project / "01-frd" / "frd.v1.json", frd)
    run("checklist.py")
    run("gate.py", "frd-quality")
    (project / "01-frd" / "feature-recommendations.json").unlink()
    assert "/recommend-features" in run("gate.py", "frd-quality", ok=False).stdout


def test_checklist_show_lists_domain_items():
    r = run("checklist.py", "--show", "--domain", "recruitment")
    assert "RCT-OFFER" in r.stdout and "GEN-AUTH" in r.stdout


def change_plan():
    def ch(i, sev, **kw):
        return {"id": f"CH-00{i}", "action": "modify", "requirement_ids": ["FR-007"], "summary": f"change {i}",
                "before": "old", "after": "new", "reason": "r", "triggered_by": ["E-001"], "severity": sev,
                "decision": "pending", **kw}
    return {"from_version": 1, "target_version": 2,
            "changes": [ch(1, "blocker"), ch(2, "minor"), ch(3, "major", options=["5 days", "10 days"]), ch(4, "minor")]}


def test_revision_requires_human_approved_change_plan(project):
    setup_frd(project)
    frd2 = full_frd()
    frd2["version"] = 2
    write(project / "01-frd" / "frd.v2.json", frd2)
    write(project / "01-frd" / "frd.v2.md", FRD_MD)
    run("checklist.py")
    write(project / "01-frd" / "eval.v2.json", good_eval(2))
    assert "no reviewed change plan" in run("gate.py", "frd-quality", ok=False).stdout

    write(project / "01-frd" / "change-plan.v2.json", change_plan())
    assert "CH-003" in run("changes.py", "show").stdout
    run("changes.py", "status", ok=False)                                   # all pending
    assert "undecided" in run("gate.py", "frd-quality", ok=False).stdout

    run("changes.py", "decide", "--by", "Tester", "--approve", "CH-001", "--reject", "CH-002",
        "--option", "CH-003=10 days", "--edit", "CH-004=use plain wording")
    run("changes.py", "status")
    plan = json.loads((project / "01-frd" / "change-plan.v2.json").read_text(encoding="utf-8"))
    d = {c["id"]: c for c in plan["changes"]}
    assert d["CH-003"]["chosen_option"] == "10 days" and d["CH-004"]["decision"] == "edited"

    frd2["change_log"] = [{"change_id": "CH-001", "applied": True}, {"change_id": "CH-003", "applied": True}]
    write(project / "01-frd" / "frd.v2.json", frd2)
    assert "not applied in frd.v2: ['CH-004']" in run("gate.py", "frd-quality", ok=False).stdout
    frd2["change_log"] += [{"change_id": "CH-004", "applied": True}, {"change_id": "CH-002", "applied": True}]
    write(project / "01-frd" / "frd.v2.json", frd2)
    assert "did not approve: ['CH-002']" in run("gate.py", "frd-quality", ok=False).stdout
    frd2["change_log"].pop()
    write(project / "01-frd" / "frd.v2.json", frd2)
    run("gate.py", "frd-quality")


def test_frd_approval_scaffolds_app_repository(project):
    import subprocess as sp
    setup_frd(project)
    run("checklist.py")
    write(project / "01-frd" / "eval.v1.json", good_eval())
    r = run("scaffold.py", "init", ok=False)               # refused before approval
    assert "REFUSED" in r.stdout
    r = run("approve.py", "frd", "--by", "Tester", "--decision", "approved")
    assert "APP REPOSITORY" in r.stdout
    app = ROOT.parent / "app-development" / project.name
    for f in ["README.md", "CONTRIBUTING.md", ".gitignore", ".env.example", "docker-compose.yml",
              ".github/workflows/ci.yml", ".github/pull_request_template.md", "docs/STRUCTURE.md",
              "backend/Dockerfile", "backend/app/controllers/__init__.py", "backend/app/services/__init__.py",
              "backend/app/repositories/__init__.py", "backend/tests/unit/.gitkeep",
              "frontend/Dockerfile", "frontend/src/views/.gitkeep", "e2e/.gitkeep"]:
        assert (app / f).exists(), f
    import yaml
    assert "jobs" in yaml.safe_load((app / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert "db" in yaml.safe_load((app / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    branches = sp.run(["git", "-C", str(app), "branch", "--format=%(refname:short)"], capture_output=True, text=True).stdout.split()
    assert sorted(branches) == ["develop", "main"]
    head = sp.run(["git", "-C", str(app), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert head == "develop"
    # Idempotent: user changes survive a re-run.
    (app / "README.md").write_text("custom\n", encoding="utf-8")
    run("scaffold.py", "init")
    assert (app / "README.md").read_text(encoding="utf-8") == "custom\n"
