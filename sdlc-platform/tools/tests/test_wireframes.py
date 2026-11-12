"""Wireframe stage between FRD approval and spec generation."""
from __future__ import annotations

import json

from test_tools import ROOT, good_eval, project, run, setup_frd, write  # noqa: F401  (fixture)

PAGE = """<!doctype html><html><head><title>{id}: {name}</title><style>body{{font:14px sans-serif}}</style></head>
<body data-screen="{id}"><h1>{name}</h1><p class="note">{reqs}</p>{extra}<a href="index.html">All screens</a></body></html>"""

SCREENS = [
    ("W-001", "Login", ["FR-001", "FR-002"], "Employee"),
    ("W-002", "Apply for leave", ["FR-007", "FR-009", "FR-010", "FR-011"], "Employee"),
    ("W-003", "Approval queue", ["FR-008"], "Manager"),
    ("W-004", "HR administration", ["FR-004", "FR-005", "FR-006"], "HR"),
]


def approve_frd(pdir):
    setup_frd(pdir)
    run("checklist.py")
    write(pdir / "01-frd" / "eval.v1.json", good_eval())
    run("approve.py", "frd", "--by", "Tester", "--decision", "approved")


def write_set(vdir, screens=SCREENS, extra=""):
    entries = []
    for sid, name, reqs, role in screens:
        f = f"{sid}-{name.lower().replace(' ', '-')}.html"
        (vdir / f).write_text(PAGE.format(id=sid, name=name, reqs=", ".join(reqs), extra=extra), encoding="utf-8")
        entries.append({"id": sid, "name": name, "file": f, "roles": [role], "requirement_ids": reqs,
                        "purpose": name, "navigates_to": ["W-001"]})
    write(vdir / "screens.json", {"version": int(vdir.name[1:]), "screens": entries,
                                  "no_ui_requirements": [{"id": "FR-003", "reason": "email notification"}]})
    (vdir / "index.html").write_text("".join(f'<a href="{e["file"]}">{e["name"]}</a>' for e in entries), encoding="utf-8")
    (vdir / "wireframes.md").write_text("# Wireframes\n", encoding="utf-8")


def test_wireframes_generate_review_approve_and_lock(project):
    approve_frd(project)
    st = run("wireframes.py", "status").stdout
    assert "client wireframes in the approved input: 0" in st and "create wireframes" in st
    assert "no wireframes exist yet" in run("gate.py", "wireframes-ready", ok=False).stdout
    assert "no wireframes" in run("gate.py", "specs-exist", ok=False).stdout          # specs wait for screens
    assert "contains no wireframes" in run("wireframes.py", "decide", "provided", "--by", "T", ok=False).stderr
    assert "--reason" in run("wireframes.py", "decide", "skip", "--by", "T", ok=False).stderr

    run("wireframes.py", "decide", "generate", "--by", "Tester")
    run("wireframes.py", "new-version")
    v1 = project / "01b-wireframes" / "v1"
    write_set(v1, SCREENS[:3])                                               # HR screen missing
    out = run("gate.py", "wireframes-check", ok=False).stdout
    assert "FR-004 (Leave report) has no screen" in out
    assert "REFUSED" in run("approve.py", "wireframes", "--by", "T", "--decision", "approved", ok=False).stdout
    write_set(v1, extra='<script src="https://cdn.example/x.js"></script>')
    assert "self-contained" in run("wireframes.py", "check", ok=False).stdout
    write_set(v1)
    (v1 / "W-003-approval-queue.html").write_text(
        PAGE.format(id="W-003", name="Approval queue", reqs="", extra=""), encoding="utf-8")
    assert "requirement FR-008 is not annotated" in run("wireframes.py", "check", ok=False).stdout
    write_set(v1)
    run("gate.py", "wireframes-check")

    # review rounds are bounded
    for i in range(3):
        run("wireframes.py", "feedback", f"round {i}", "--by", "Client")
    assert "ESCALATE" in run("wireframes.py", "feedback", "round 4", "--by", "Client", ok=False).stderr

    run("approve.py", "wireframes", "--by", "Client", "--decision", "approved")
    run("gate.py", "wireframes-ready")
    assert "wireframes=approved" in run("state.py", "show").stdout
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(v1 / "W-001-login.html")}})
    assert run("lock_guard.py", ok=None, stdin=payload).returncode == 2                # approved screens are locked

    # Phase 2 uses the approved screen names
    write(project / "02-spec" / "features.json", {"features": [
        {"id": "F-001", "title": "Access", "description": "d", "requirement_ids": ["FR-001"], "layers": ["frontend"],
         "screens": ["Login", "Dashboard"]}]})
    out = run("spec_rules.py", ok=None).stdout
    assert "WARNING SV11" in out and "'Dashboard'" in out and "'Login'" not in out
    slice_ = run("spec_docs.py", "slice", "F-001").stdout
    assert "F-001" in slice_
    assert "W-001-login.html" in (project / "02-spec" / "slices" / "F-001.md").read_text(encoding="utf-8")

    # changes after approval need a new version and a new approval
    run("wireframes.py", "new-version")
    assert "v1 are approved but v2 is the latest" in run("gate.py", "wireframes-ready", ok=False).stdout
    assert json.loads((project / "01b-wireframes" / "v2" / "screens.json").read_text(encoding="utf-8"))["version"] == 2


def test_wireframes_skip_and_client_provided(project):
    approve_frd(project)
    run("wireframes.py", "decide", "skip", "--by", "Tester", "--reason", "API-only integration service")
    run("gate.py", "wireframes-ready")
    assert "wireframes=skipped" in run("state.py", "show").stdout


def test_client_wireframes_are_detected(project, tmp_path):
    setup_frd(project)
    html = tmp_path / "apply.html"
    html.write_text('<form aria-label="Apply"><input name="from" type="date" required></form>', encoding="utf-8")
    run("parse_doc.py", ROOT / "samples" / "leave_crd.md", html, "--force")
    run("checklist.py")
    write(project / "01-frd" / "eval.v1.json", good_eval())
    run("approve.py", "frd", "--by", "Tester", "--decision", "approved")
    assert "client wireframes in the approved input: 1" in run("wireframes.py", "status").stdout
    assert "client supplied 1 wireframe" in run("gate.py", "wireframes-ready", ok=False).stdout
    run("wireframes.py", "decide", "provided", "--by", "Tester")
    run("gate.py", "wireframes-ready")
