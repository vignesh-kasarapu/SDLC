"""Tests for ingestion formats, FRD intake mode, the spec content rules (seeded-bad-spec suite),
per-feature slices, resume, existing-code discovery, stack patterns, usage logging and packaging.

Shares the throw-away project fixture and helpers with test_tools.py.
Run: python -m pytest
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from test_tools import ROOT, PROJECTS, feature_recs, project, run, tech_stack, write  # noqa: F401  (fixture)

FIXTURES = Path(__file__).parent / "fixtures"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAwS2OUAAAAABJRU5ErkJggg==")


def cid_of(pdir: Path, needle: str) -> str:
    blocks = json.loads((pdir / "01-frd" / "crd-index.json").read_text(encoding="utf-8"))["blocks"]
    return next(c for c, b in blocks.items() if needle in b["text"])


# ---------------------------------------------------------------- input formats
def make_xlsx(path: Path):
    m = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{m}" xmlns:r="{r}"><sheets>'
                                      f'<sheet name="Reqs" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="ws"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{m}"><si><t>ID</t></si><si><t>Requirement</t></si>'
                                           f'<si><t>REQ-1</t></si><si><t>Login with SSO</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{m}"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                   '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c><c r="C2"><v>42.0</v></c></row>'
                   '</sheetData></worksheet>')


def make_docx_with_image(path: Path):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{w}" xmlns:a="{a}" xmlns:r="{r}"><w:body>'
                   '<w:p><w:r><w:t>The job form is shown below.</w:t></w:r></w:p>'
                   '<w:p><w:r><w:drawing><a:graphic><a:graphicData><a:blip r:embed="rId5"/></a:graphicData>'
                   '</a:graphic></w:drawing></w:r></w:p></w:body></w:document>')
        z.writestr("word/_rels/document.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId5" Target="media/image1.png" Type="image"/></Relationships>')
        z.writestr("word/media/image1.png", PNG)


def make_blank_pdf(path: Path):
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj".encode() + o + b"endobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer<</Root 1 0 R/Size {len(objs) + 1}>>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


HTML = """<html><head><title>Job form</title></head><body><h1>Create job</h1>
<form id="job-form" action="/api/v1/jobs" method="post">
<label for="t">Title</label><input id="t" name="title" required maxlength="120">
<select name="dept"><option>HR</option><option>IT</option></select>
<button type="submit">Save</button></form>
<nav><a>Home</a><a>Jobs</a></nav>
<table><tr><th>Name</th><th>Status</th></tr><tr><td>A</td><td>Open</td></tr></table>
<button>Export</button></body></html>"""


def test_parse_many_formats_and_vision_handoff(project, tmp_path):
    src = tmp_path / "input"
    src.mkdir()
    (src / "a_requirements.md").write_text("# Requirements\n\nThe system shall do X.\n", encoding="utf-8")
    (src / "b_fields.csv").write_text("Field,Type\nTitle,text\nSalary,number\n", encoding="utf-8")
    (src / "c_screen.html").write_text(HTML, encoding="utf-8")
    make_xlsx(src / "d_matrix.xlsx")
    (src / "e_wire.png").write_bytes(PNG)
    make_docx_with_image(src / "f_doc.docx")
    make_blank_pdf(src / "g_scan.pdf")
    out = run("parse_doc.py", src).stdout
    assert "parsed 7 file(s)" in out and "PENDING VISUALS: 3" in out
    idx = json.loads((project / "01-frd" / "crd-index.json").read_text(encoding="utf-8"))
    texts = "\n".join(b["text"] for b in idx["blocks"].values())
    assert "Title [text, required, maxlength=120" in texts and "options: HR/IT" in texts
    assert "Actions: Save" in texts and "UI navigation" in texts and "Home, Jobs" in texts
    assert "| Name | Status |" in texts and "UI actions on the page: Export" in texts
    assert "Sheet: Reqs" in texts and "| REQ-1 | Login with SSO | 42 |" in texts
    assert "| Salary | number |" in texts and "The job form is shown below." in texts
    assert sum(1 for b in idx["blocks"].values() if b["kind"] == "heading" and "Source file" in b["text"]) == 7
    pdf_block = next(b for b in idx["blocks"].values() if b.get("scanned"))
    assert pdf_block["page"] == 1
    assert (project / "input" / "f_doc_media" / "image1.png").exists()

    # Pending images block the pipeline until the vision agent's results are attached.
    r = run("gate.py", "crd-parsed", ok=False)
    assert "not analysed yet" in r.stdout
    pending = idx["pending_visuals"]
    vdir = project / "01-frd" / "visuals"
    write(vdir / f"{pending[0]}.json", {"id": pending[0], "source": "x", "kind": "ui_screen",
                                        "summary": "Wireframe of the job form."})          # screen missing
    assert "invalid" in run("parse_doc.py", "--attach-visuals", ok=False).stderr
    write(vdir / f"{pending[0]}.json", {"id": pending[0], "source": "x", "kind": "ui_screen",
                                        "summary": "Wireframe of the job form.",
                                        "screen": {"screen_name": "Job form", "form_fields": [
                                            {"label": "Salary band", "type": "select", "required": True}],
                                            "buttons": [{"label": "Publish", "action": "submit"}]}})
    write(vdir / f"{pending[1]}.json", {"id": pending[1], "source": "x", "kind": "diagram",
                                        "summary": "Approval flow diagram.", "mermaid": "flowchart TD\n A-->B"})
    write(vdir / f"{pending[2]}.json", {"id": pending[2], "source": "x", "kind": "text_page",
                                        "summary": "Scanned signature page.", "text": "Approved by the client."})
    run("parse_doc.py", "--attach-visuals")
    run("gate.py", "crd-parsed")
    crd = (project / "01-frd" / "crd.md").read_text(encoding="utf-8")
    assert "Salary band [select, required]" in crd and "Publish -> submit" in crd
    assert "```mermaid" in crd and "Approved by the client." in crd and "PENDING" not in crd


def test_golden_mini_frd_parse(project):
    golden = FIXTURES / "golden" / "mini_frd"
    run("parse_doc.py", golden / "input.md")
    idx = json.loads((project / "01-frd" / "crd-index.json").read_text(encoding="utf-8"))
    expected = json.loads((golden / "expected.json").read_text(encoding="utf-8"))
    assert idx["doc_type"] == expected["doc_type"]
    assert [b["kind"] for b in idx["blocks"].values()] == expected["kinds"]
    for cid, text in expected["texts"].items():
        assert idx["blocks"][cid]["text"] == text


def test_doc_type_detection_and_override(project):
    run("parse_doc.py", ROOT / "samples" / "leave_crd.md")
    assert json.loads((project / "01-frd" / "intake.json").read_text(encoding="utf-8"))["doc_type"] == "crd"
    run("parse_doc.py", ROOT / "samples" / "leave_crd.md", "--as", "frd")
    assert json.loads((project / "01-frd" / "intake.json").read_text(encoding="utf-8"))["decided_by"] == "user"
    write(project / "01-frd" / "frd.v1.json", {"requirements": [], "open_questions": []})
    assert "renumbers" in run("parse_doc.py", ROOT / "samples" / "leave_crd.md", ok=False).stderr


# ---------------------------------------------------------------- FRD intake mode
def test_frd_intake_keeps_client_wording(project):
    run("parse_doc.py", FIXTURES / "golden" / "mini_frd" / "input.md")
    assert run("frd_intake.py", "mode").stdout.strip() == "frd"
    c1 = cid_of(project, "REQ-001")
    c2 = cid_of(project, "REQ-002")
    frd = {"version": 1, "open_questions": [{"id": "Q-001", "question": "Which roles may see team leave?",
                                             "blocking": False, "related": ["FR-001"]}],
           "requirements": [
               {"id": "FR-001", "type": "functional", "title": "Submit leave", "client_ref": "REQ-001",
                "statement": "The system shall let an employee submit a leave request for a date range.",
                "priority": "must", "source": [c1], "acceptance_criteria": ["Given ..."], "status": "confirmed"},
               {"id": "FR-002", "type": "functional", "title": "Approve leave", "client_ref": "REQ-002",
                "statement": "The system shall let the team lead approve ... a pending request with a comment",
                "priority": "must", "source": [c2], "acceptance_criteria": ["Given ..."], "status": "confirmed",
                "clarification": "Rejection also requires a comment."},
               {"id": "NFR-001", "type": "non_functional", "title": "Stack", "statement": "The backend uses FastAPI.",
                "priority": "must", "source": ["USER-STACK"], "acceptance_criteria": ["Lint passes"],
                "status": "confirmed"}]}
    write(project / "01-frd" / "frd.v1.json", frd)
    write(project / "01-frd" / "tech-stack.json", tech_stack())
    write(project / "01-frd" / "feature-recommendations.json", feature_recs())
    run("frd_intake.py", "build", "--version", "1")
    md = (project / "01-frd" / "frd.v1.md").read_text(encoding="utf-8")
    assert "## Part A. Client FRD (verbatim)" in md and "REQ-004 An employee may have at most 25 days" in md
    assert "## 19. Technology stack" in md and "## 20. Architecture pattern" in md
    assert "Rejection also requires a comment." in md and "The backend uses FastAPI." in md
    run("frd_intake.py", "check", "--version", "1")

    frd["requirements"][0]["statement"] = "Employees can request time off for a period."     # paraphrase
    write(project / "01-frd" / "frd.v1.json", frd)
    assert "not the client's wording" in run("frd_intake.py", "check", "--version", "1", ok=False).stdout
    assert "not the client's wording" in run("gate.py", "frd-quality", ok=False).stdout
    frd["requirements"][0]["statement"] = "the system shall let an employee   submit a leave request"  # case/space
    write(project / "01-frd" / "frd.v1.json", frd)
    run("frd_intake.py", "build", "--version", "1")
    (project / "01-frd" / "frd.v1.md").write_text(md.replace("Part A", "Rewritten"), encoding="utf-8")
    assert "not the rendered intake document" in run("frd_intake.py", "check", "--version", "1", ok=False).stdout


# ---------------------------------------------------------------- spec rules: good set + seeded defects
CRD = """# Recruiting portal

Recruiters create job requisitions with a title of at most 120 characters.

Users log in with their company email.

Payroll processing integration is out of scope.
"""

SPEC_F1 = """# F-001: Users

| Field | Value |
|---|---|
| Feature ID | F-001 |
| Source requirements | FR-001 |

## 1. Description
Users log in and see the user list (FR-001).

## 2. Business rules
| Requirement | Rule (quoted from the FRD) | Enforcement |
|---|---|---|
| FR-001 | Users log in with their company email. | service |

## 3. Acceptance criteria
| ID | Criterion (Given/When/Then) | Requirements |
|---|---|---|
| AC-F001-01 | Given a registered user, when they log in, then they see the user list | FR-001 |

## 4. Database
Table users.

## 5. Backend
UserService.get_user(user_id) -> User

## 6. API
| operationId | Method and path | Roles | Request | Responses |
|---|---|---|---|---|
| getUser | GET /api/v1/users/{userId} | admin | - | 200, 404 |

## 7. Frontend
Screen S-001 User list.

## 8. Security
Only authenticated users.

## 9. Non-functional requirements
None

## 10. Dependencies
None

## 11. Test cases
| ID | Level | Scenario | Expected | Covers (AC) | Requirements |
|---|---|---|---|---|---|
| T-F001-01 | api | log in | 200 | AC-F001-01 | FR-001 |

## 12. Files by owner
| Agent | Files |
|---|---|
| backend-dev | backend/app/services/user_service.py |

## 13. Open items
None
"""

SPEC_F2 = SPEC_F1.replace("F-001: Users", "F-002: Jobs").replace("| Feature ID | F-001 |", "| Feature ID | F-002 |") \
    .replace("Users log in and see the user list (FR-001).", "Recruiters create job requisitions (FR-002, BR-001). Depends on F-001.") \
    .replace("| FR-001 | Users log in with their company email. | service |",
             "| BR-001 | A job title has at most 120 characters. | DB constraint + service |") \
    .replace("| AC-F001-01 | Given a registered user, when they log in, then they see the user list | FR-001 |",
             "| AC-F002-01 | Given a recruiter, when they submit a valid job, then it is created | FR-002 |\n"
             "| AC-F002-02 | Given a title longer than 120 characters, when it is submitted, then it is rejected | BR-001 |") \
    .replace("| T-F001-01 | api | log in | 200 | AC-F001-01 | FR-001 |",
             "| T-F002-01 | api | create valid job | 201 | AC-F002-01 | FR-002 |\n"
             "| T-F002-02 | api | title too long | 400 | AC-F002-02 | BR-001 |") \
    .replace("Screen S-001 User list.", "Screen S-002 Job form.") \
    .replace("| getUser | GET /api/v1/users/{userId} | admin | - | 200, 404 |", "| createJob | POST /api/v1/jobs | recruiter | JobCreate | 201, 400 |") \
    .replace("Table users.", "Table jobs.").replace("UserService.get_user(user_id) -> User", "JobService.create_job(data) -> Job") \
    .replace("user_service.py", "job_service.py").replace("| Source requirements | FR-001 |", "| Source requirements | FR-002, BR-001 |")

OPENAPI = """openapi: 3.1.0
info: {title: Recruiting, version: '1'}
paths:
  /api/v1/users/{userId}:
    get:
      operationId: getUser
      tags: [F-001]
      x-roles: [admin]
      responses:
        '200':
          content:
            application/json:
              schema: {$ref: '#/components/schemas/User'}
  /api/v1/jobs:
    post:
      operationId: createJob
      tags: [F-002]
      requestBody:
        content:
          application/json:
            schema: {$ref: '#/components/schemas/JobCreate'}
      responses:
        '201':
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Job'}
components:
  schemas:
    User:
      type: object
      properties:
        id: {type: string, format: uuid}
        email: {type: string}
    JobCreate:
      type: object
      required: [title]
      properties:
        title: {type: string, maxLength: 120}
    Job:
      type: object
      properties:
        id: {type: string}
        title: {type: string}
        createdBy: {type: string}
        applicantCount: {type: integer, x-derived: true}
"""

SCHEMA_SQL = """-- F-001 FR-001
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR(200) NOT NULL UNIQUE,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
-- F-002 FR-002 BR-001
CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  title VARCHAR(120) NOT NULL CHECK (length(title) <= 120),
  created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
"""

UI_SPEC = """# UI specification

### S-001 User list (F-001)
| Field | Type | Validation | Error message | API field |
|---|---|---|---|---|
| Email | text | required | Email is required | User.email |

### S-002 Job form (F-002)
| Field | Type | Validation | Error message | API field |
|---|---|---|---|---|
| Title | text | required, max 120 | Title is too long | JobCreate.title |
"""


def spec_project(pdir: Path) -> Path:
    crd = pdir / "input-crd.md"
    crd.write_text(CRD, encoding="utf-8")
    run("parse_doc.py", crd)
    c_job, c_login = cid_of(pdir, "job requisitions"), cid_of(pdir, "log in")

    def r(rid, rtype, title, stmt, src, prio="must"):
        return {"id": rid, "type": rtype, "title": title, "statement": stmt, "priority": prio, "source": [src],
                "acceptance_criteria": ["Given x, when y, then z"], "status": "confirmed"}
    write(pdir / "01-frd" / "frd.v1.json", {"version": 1, "open_questions": [], "requirements": [
        r("FR-001", "functional", "Login", "Users log in with their company email.", c_login),
        r("FR-002", "functional", "Create job", "Recruiters create job requisitions.", c_job),
        r("BR-001", "business_rule", "Title length", "A job title has at most 120 characters.", c_job),
        r("FR-003", "functional", "Payroll export", "Export to payroll.", c_job, prio="wont")]})
    write(pdir / "01-frd" / "tech-stack.json", tech_stack())
    write(pdir / "01-frd" / "context.json", {"overview": "x", "objectives": [], "stakeholders": [], "roles": [],
                                             "scope": {"in": ["Jobs"], "out": ["Payroll processing integration"]}})
    sdir = pdir / "02-spec"
    write(sdir / "features.json", {"features": [
        {"id": "F-001", "title": "Users", "description": "Login", "requirement_ids": ["FR-001"],
         "layers": ["backend", "api", "frontend"], "entities": ["User"], "endpoints": ["GET /api/v1/users/{id}"],
         "screens": ["User list"]},
        {"id": "F-002", "title": "Jobs", "description": "Job requisitions", "requirement_ids": ["FR-002", "BR-001"],
         "layers": ["database", "backend", "api", "frontend"], "entities": ["Job"],
         "endpoints": ["POST /api/v1/jobs"], "screens": ["Job form"]}]})
    (sdir / "openapi.yaml").write_text(OPENAPI, encoding="utf-8")
    (sdir / "schema.sql").write_text(SCHEMA_SQL, encoding="utf-8")
    (sdir / "ui-spec.md").write_text(UI_SPEC, encoding="utf-8")
    (sdir / "architecture.md").write_text("# Architecture\n\n## Project structure\nbackend/app/controllers\n\n"
                                          "## Cross-cutting concerns\nErrors use one envelope.\n\n## Risks\nNone.\n",
                                          encoding="utf-8")
    (sdir / "coding-standards.md").write_text("# Coding standards\nruff and mypy.\n", encoding="utf-8")
    (sdir / "database.md").write_text("# Database\nTables users and jobs.\n", encoding="utf-8")
    (sdir / "features" / "F-001.md").write_text(SPEC_F1, encoding="utf-8")
    (sdir / "features" / "F-002.md").write_text(SPEC_F2, encoding="utf-8")
    run("spec_docs.py", "render")
    return sdir


def test_good_spec_set_passes_all_rules(project):
    spec_project(project)
    out = run("spec_docs.py", "check").stdout
    assert "SPEC DOCS OK" in out and "WARNING" not in out
    assert run("spec_docs.py", "pending").stdout.strip() == "ALL FEATURE SPECS COMPLETE"


def _edit(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


SEEDED = [
    ("unknown requirement", "features/F-002.md", "JobService.create_job(data) -> Job", "JobService.create_job(data) per FR-099", "SV01", "unknown requirement FR-099"),
    ("unknown screen", "features/F-002.md", "Screen S-002 Job form.", "Screen S-009 Job form.", "SV01", "unknown screen S-009"),
    ("uncited rule", "features/F-002.md", "| BR-001 | A job title", "| - | A job title", "SV02", "business rule without a requirement ID"),
    ("requirement never addressed", "features.json", '"requirement_ids": ["FR-002", "BR-001"]',
     '"requirement_ids": ["FR-002", "BR-001", "FR-001"]', "SV02", "FR-001 is never addressed"),
    ("placeholder", "architecture.md", "Errors use one envelope.", "Errors use one envelope. Retry policy TBD.", "SV03", "placeholder"),
    ("forbidden tech", "architecture.md", "Errors use one envelope.", "Admin pages are built with Django.", "SV04", "'Django'"),
    ("negated tech is fine", "architecture.md", "Errors use one envelope.", "We chose FastAPI over Django.", None, "OK"),
    ("invented number", "features/F-002.md", "| BR-001 | A job title has at most 120 characters.", "| BR-001 | A job title has at most 45 characters.", "SV05", "number 45"),
    ("cites wont", "features/F-001.md", "Only authenticated users.", "Only authenticated users. See FR-003.", "SV06", "priority 'wont'"),
    ("out-of-scope obligation", "features/F-002.md", "Only authenticated users.", "The system must send payroll processing integration files.", "SV06", "out-of-scope"),
    ("AC not GWT", "features/F-002.md", "Given a recruiter, when they submit a valid job, then it is created", "A recruiter can create a job", "SV07", "Given/When/Then"),
    ("AC bad id", "features/F-002.md", "| AC-F002-01 |", "| AC-1 |", "SV07", "must look like AC-F002-01"),
    ("FR without AC", "features/F-002.md", "| AC-F002-01 | Given a recruiter, when they submit a valid job, then it is created | FR-002 |\n", "", "SV07", "FR-002 has no acceptance criterion"),
    ("AC without test", "features/F-002.md", "| T-F002-02 | api | title too long | 400 | AC-F002-02 | BR-001 |", "", "SV08", "AC-F002-02 has no test case"),
    ("test covers unknown AC", "features/F-002.md", "| T-F002-02 | api | title too long | 400 | AC-F002-02 |", "| T-F002-02 | api | title too long | 400 | AC-F002-09 |", "SV08", "unknown criterion AC-F002-09"),
    ("API field without column", "openapi.yaml", "        title: {type: string, maxLength: 120}", "        title: {type: string, maxLength: 120}\n        salary: {type: integer}", "SV09", "JobCreate.salary has no column"),
    ("UI maps unknown field", "ui-spec.md", "JobCreate.title", "JobCreate.headline", "SV09", "unknown property 'JobCreate.headline'"),
    ("missing section", "features/F-001.md", "## 8. Security\nOnly authenticated users.\n", "", None, "missing section '## 8. Security'"),
]


@pytest.mark.parametrize("name,file,old,new,code,needle", SEEDED, ids=[s[0] for s in SEEDED])
def test_seeded_bad_specs_are_caught(project, name, file, old, new, code, needle):
    sdir = spec_project(project)
    if file == "features.json":   # structured edit: assign F-001's requirement to F-002 as well
        feats = json.loads((sdir / file).read_text(encoding="utf-8"))
        feats["features"][1]["requirement_ids"] = json.loads(new.split(": ", 1)[1])
        write(sdir / file, feats)
    else:
        _edit(sdir / file, old, new)
    run("spec_docs.py", "render")
    r = run("spec_docs.py", "check", ok=None)
    out = r.stdout
    if name == "negated tech is fine":
        assert r.returncode == 0 and "SV04" not in out
        return
    if code in ("SV05",) or name == "out-of-scope obligation":
        assert r.returncode == 0 and f"WARNING {code}" in out and needle in out, out   # warnings never block
        return
    assert r.returncode != 0, out
    if code:
        assert code in out, out
    assert needle in out, out
    assert "F-001" in run("spec_docs.py", "pending").stdout or "features/F-001" not in out


def test_entity_without_table_and_existing_code(project):
    sdir = spec_project(project)
    feats = json.loads((sdir / "features.json").read_text(encoding="utf-8"))
    feats["features"][1]["entities"].append("Candidate")
    write(sdir / "features.json", feats)
    run("spec_docs.py", "render")
    assert "entity Candidate (F-002) has no table" in run("spec_docs.py", "check", ok=False).stdout
    feats["features"][1]["entities"].remove("Candidate")
    write(sdir / "features.json", feats)
    run("spec_docs.py", "render")
    write(project / "00-discovery" / "project-facts.json", {
        "tables": [{"name": "jobs", "file": "db.sql"}], "routes": [{"route": "POST /api/v1/jobs", "file": "x.py"}],
        "files": ["backend/app/services/job_service.py"], "classes": [{"name": "JobService", "kind": "service", "file": "x"}]})
    out = run("spec_docs.py", "check", ok=False).stdout
    assert "SV10" in out and "re-creates an existing table" in out and "POST /api/v1/jobs already exists" in out
    assert "existing file backend/app/services/job_service.py" in out


def test_slices_hold_only_the_features_inputs(project):
    sdir = spec_project(project)
    out = run("spec_docs.py", "slice", "all").stdout
    assert "slices/F-002.md" in out
    s2 = (sdir / "slices" / "F-002.md").read_text(encoding="utf-8")
    assert "### BR-001: Title length" in s2 and "CREATE TABLE jobs" in s2 and "createJob" in s2
    assert "JobCreate" in s2 and "S-002 Job form" in s2 and "## Project structure" in s2
    assert "with a title of at most 120 characters" in s2                    # cited client paragraph
    assert "FR-001" not in s2 and "CREATE TABLE users" not in s2 and "getUser" not in s2
    assert "## Risks" not in s2                                               # irrelevant architecture left out


def test_pending_lists_missing_and_failing_specs(project):
    sdir = spec_project(project)
    (sdir / "features" / "F-001.md").unlink()
    _edit(sdir / "features" / "F-002.md", "| AC-F002-01 |", "| AC-1 |")
    assert run("spec_docs.py", "pending").stdout.strip() == "PENDING F-001 F-002"


# ---------------------------------------------------------------- existing code
def test_discover_import_and_scan(project, tmp_path):
    src = tmp_path / "legacy"
    (src / "backend" / "app" / "controllers").mkdir(parents=True)
    (src / "backend" / "app" / "models").mkdir(parents=True)
    (src / "frontend" / "src").mkdir(parents=True)
    (src / "node_modules" / "junk").mkdir(parents=True)
    (src / "backend" / "requirements.txt").write_text("fastapi==0.110\nsqlalchemy\n", encoding="utf-8")
    (src / "frontend" / "package.json").write_text('{"dependencies": {"react": "^18"}}', encoding="utf-8")
    (src / "backend" / "app" / "controllers" / "job_controller.py").write_text(
        'router = APIRouter()\n\n@router.post("/api/v1/jobs/{job_id}/publish")\ndef publish(job_id: int): ...\n\n'
        'class JobController:\n    pass\n', encoding="utf-8")
    (src / "backend" / "app" / "models" / "job.py").write_text(
        'class Job(Base):\n    __tablename__ = "jobs"\n', encoding="utf-8")
    (src / "frontend" / "src" / "App.tsx").write_text('<Route path="/jobs" element={<Jobs/>} />', encoding="utf-8")
    (src / "node_modules" / "junk" / "x.js").write_text("app.get('/nope')", encoding="utf-8")
    out = run("discover.py", "import", src).stdout
    assert "imported into" in out and "1 routes" in out and "1 tables" in out
    facts = json.loads((project / "00-discovery" / "project-facts.json").read_text(encoding="utf-8"))
    assert facts["routes"] == [{"route": "POST /api/v1/jobs/{}/publish", "file": "backend/app/controllers/job_controller.py"}]
    assert facts["tables"][0]["name"] == "jobs" and "FastAPI" in facts["stack"]["frameworks"]
    assert "React" in facts["stack"]["frameworks"] and facts["ui_routes"] == ["/jobs"]
    assert any(c["name"] == "JobController" for c in facts["classes"])
    assert not any("node_modules" in f for f in facts["files"])
    app = ROOT.parent / "app-development" / project.name
    head = subprocess.run(["git", "-C", str(app), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    assert head.stdout.strip() == "develop"


# ---------------------------------------------------------------- stack patterns
def _py(code: str):
    return subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, 'tools')\n{code}"],
                          capture_output=True, text=True, cwd=ROOT)


def test_architecture_pattern_is_configurable(project):
    ts = tech_stack()
    ts["architecture_pattern"] = "framework-native"
    write(project / "01-frd" / "tech-stack.json", ts)
    assert "pattern_rationale" in run("validate.py", "tech-stack", project / "01-frd" / "tech-stack.json", ok=False).stdout
    ts["pattern_rationale"] = "Next.js app router conventions; the architect defines folders."
    write(project / "01-frd" / "tech-stack.json", ts)
    run("validate.py", "tech-stack", project / "01-frd" / "tech-stack.json")
    r = _py(f"from scaffold import plan_files\nfrom pathlib import Path\n"
            f"print(sorted(plan_files(Path(r'{project}'))))")
    assert "backend/app/controllers/__init__.py" not in r.stdout and "docs/STRUCTURE.md" in r.stdout, r.stderr
    assert "skipped" in run("layer_check.py").stdout


# ---------------------------------------------------------------- usage + packaging
def test_usage_logging_and_report(project):
    out_file = project / "02-spec" / "features" / "F-001.md"
    out_file.write_text("x" * 4000, encoding="utf-8")
    run("state.py", "start", "feature-spec-writer", "--key", "F-001", "--prompt-chars", "400")
    run("state.py", "log", "feature-spec-writer", "done", "--key", "F-001", "--outputs", out_file)
    entry = json.loads((project / "03-build" / "logs" / "agents.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert entry["duration_s"] >= 0 and entry["est_tokens_out"] == 1000 and entry["est_tokens_in"] == 100
    assert entry["key"] == "F-001" and entry["model"] == "sonnet"
    rep = run("usage.py").stdout
    assert "feature-spec-writer" in rep and "TOTAL" in rep
    assert json.loads(run("usage.py", "--by", "key", "--json").stdout)["F-001"]["tokens_out"] == 1000


def test_package_zip_is_clean(tmp_path):
    out = tmp_path / "platform.zip"
    run("package.py", "--out", out)
    names = zipfile.ZipFile(out).namelist()
    assert "sdlc-platform/tools/state.py" in names and "sdlc-platform/.claude/settings.json" in names
    assert not [n for n in names if "__pycache__" in n or ".pytest_cache" in n or "settings.local" in n]
