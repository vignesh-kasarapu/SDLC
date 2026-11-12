#!/usr/bin/env python
"""Phase 2 specification documents: one Markdown file per spec area, plus one per feature.

Agent-written docs (checked here, not generated):
  02-spec/architecture.md       architect
  02-spec/coding-standards.md   architect
  02-spec/database.md           db-spec        (with schema.sql)
  02-spec/ui-spec.md            ui-spec
  02-spec/features/F-nnn.md     feature-spec-writer (one per feature, templates/feature-spec.md)

Rendered deterministically from the machine-readable sources (never hand-edited):
  02-spec/features.md           from features.json (+ approved FRD for requirement titles)
  02-spec/api-spec.md           from openapi.yaml
  02-spec/index.md              table of contents of the whole spec set, per-feature status

Usage:
  spec_docs.py render [--project ID]     (re)write features.md, api-spec.md, index.md
  spec_docs.py check  [--project ID]     verify the spec set: structure + content rules SV01-SV10
                                         (tools/spec_rules.py); exit 1 on blockers, warnings printed
  spec_docs.py pending                   features whose spec is missing or has blockers (resume list)
  spec_docs.py slice F-nnn|all           write 02-spec/slices/F-nnn.md: only what that feature's
                                         spec writer needs (tools/spec_slice.py)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import project_dir, read_json, rel

AGENT_DOCS = {
    "architecture.md": ("architect", "System context, MVC layers, project structure, cross-cutting concerns, NFR mapping, ADRs"),
    "coding-standards.md": ("architect", "Lint/format/type tools, naming, Definition of Done for this stack"),
    "database.md": ("db-spec", "ER diagram, entities, rule enforcement, migration plan, retention (DDL in schema.sql)"),
    "ui-spec.md": ("ui-spec", "Navigation map, screens S-nnn, forms, states, accessibility"),
}
RENDERED_DOCS = {
    "features.md": ("spec_docs.py", "Feature breakdown and requirement-to-feature coverage (from features.json)"),
    "api-spec.md": ("spec_docs.py", "API contract per feature, readable form of openapi.yaml"),
}
FEATURE_SECTIONS = ["1. Description", "2. Business rules", "3. Acceptance criteria", "4. Database", "5. Backend",
                    "6. API", "7. Frontend", "8. Security", "9. Non-functional requirements", "10. Dependencies",
                    "11. Test cases", "12. Files by owner", "13. Open items"]
HTTP = ("get", "post", "put", "patch", "delete")


# ---------- helpers ----------
def _cell(v) -> str:
    if v is None or v == "" or v == []:
        return "—"
    if isinstance(v, (list, tuple)):
        v = ", ".join(map(str, v))
    return str(v).replace("|", "\\|").replace("\n", " ")


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out


def _load_yaml(path: Path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _frd_requirements(pdir):
    v = read_json(pdir / "01-frd" / "approval.json", default={}).get("version")
    frd = read_json(pdir / "01-frd" / f"frd.v{v}.json", default={}) if v else {}
    return v, {r["id"]: r for r in frd.get("requirements", [])}


def _features(pdir):
    return read_json(pdir / "02-spec" / "features.json", default={}).get("features", [])


def _operations(api):
    for path, item in (api.get("paths") or {}).items():
        for method in HTTP:
            if isinstance(item, dict) and method in item:
                yield method.upper(), path, item[method] or {}


def _ref_name(schema):
    if not isinstance(schema, dict):
        return ""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        inner = _ref_name(schema.get("items", {}))
        return f"{inner}[]" if inner else "array"
    return schema.get("type", "")


def _body_schema(content):
    for media in (content or {}).values():
        return _ref_name(media.get("schema", {}))
    return ""


def _norm_endpoint(text: str) -> str:
    """'GET /api/v1/jobs/{id}' and 'get /api/v1/jobs/{jobId}' compare equal."""
    parts = text.strip().split(None, 1)
    if len(parts) != 2:
        return text.strip().lower()
    return parts[0].upper() + " " + re.sub(r"\{[^}]+\}", "{}", parts[1].strip().rstrip("/"))


def open_count(spec: Path) -> int:
    return len(re.findall(r"\bOPEN:", spec.read_text(encoding="utf-8"))) if spec.exists() else 0


# ---------- renderers ----------
def render_features(pdir) -> str:
    feats = _features(pdir)
    frd_v, reqs = _frd_requirements(pdir)
    md = ["# Feature breakdown", "",
          f"Rendered from `02-spec/features.json` by `tools/spec_docs.py`; do not edit by hand. "
          f"Source FRD: v{frd_v}.", "", "## Features", ""]
    md += _table(["ID", "Title", "Layers", "Requirements", "Entities", "Screens", "Spec"],
                 [[f["id"], f["title"], f.get("layers"), len(f["requirement_ids"]), f.get("entities"),
                   f.get("screens"), f"[{f['id']}.md](features/{f['id']}.md)"] for f in feats])
    for f in feats:
        md += ["", f"## {f['id']}: {f['title']}", "", f.get("description", ""), ""]
        md += _table(["Requirement", "Type", "Priority", "Title"],
                     [[r, reqs.get(r, {}).get("type"), reqs.get(r, {}).get("priority"), reqs.get(r, {}).get("title")]
                      for r in f["requirement_ids"]])
        if f.get("endpoints"):
            md += ["", "Endpoints: " + ", ".join(f"`{e}`" for e in f["endpoints"])]
    covered = {}
    for f in feats:
        for r in f["requirement_ids"]:
            covered.setdefault(r, []).append(f["id"])
    md += ["", "## Requirement coverage", ""]
    rows = [[rid, r.get("priority"), covered.get(rid) or ("not required (wont)" if r.get("priority") == "wont" else "**UNMAPPED**")]
            for rid, r in sorted(reqs.items())]
    md += _table(["Requirement", "Priority", "Features"], rows) if rows else ["(approved FRD not found)"]
    return "\n".join(md) + "\n"


def render_api(pdir) -> str:
    api = _load_yaml(pdir / "02-spec" / "openapi.yaml")
    feats = {f["id"]: f["title"] for f in _features(pdir)}
    info = api.get("info", {})
    md = ["# API specification", "",
          f"Rendered from `02-spec/openapi.yaml` by `tools/spec_docs.py`; do not edit by hand. "
          f"The YAML is the binding contract.", "",
          f"- Title: {info.get('title', '—')}  ", f"- Version: {info.get('version', '—')}  ",
          f"- OpenAPI: {api.get('openapi', '—')}"]
    schemes = (api.get("components") or {}).get("securitySchemes") or {}
    if schemes:
        md += ["", "## Security schemes", ""]
        md += _table(["Name", "Type", "Scheme", "Format"],
                     [[n, s.get("type"), s.get("scheme"), s.get("bearerFormat")] for n, s in schemes.items()])
    by_feat = {}
    for method, path, op in _operations(api):
        tag = next((t for t in op.get("tags", []) if re.fullmatch(r"F-\d{3}", str(t))), "untagged")
        by_feat.setdefault(tag, []).append((method, path, op))
    for fid in sorted(by_feat):
        md += ["", f"## {fid}: {feats.get(fid, 'unknown feature')}", ""]
        rows = []
        for method, path, op in by_feat[fid]:
            req = _body_schema((op.get("requestBody") or {}).get("content"))
            ok = next((_body_schema(r.get("content")) for c, r in (op.get("responses") or {}).items()
                       if str(c).startswith("2") and isinstance(r, dict)), "")
            rows.append([op.get("operationId"), f"`{method} {path}`", op.get("x-roles"), op.get("x-requirements"),
                         req, ok, ", ".join(map(str, (op.get("responses") or {}).keys()))])
        md += _table(["operationId", "Endpoint", "Roles", "Requirements", "Request", "Success body", "Responses"], rows)
    schemas = (api.get("components") or {}).get("schemas") or {}
    if schemas:
        md += ["", "## Schemas"]
        for name, s in schemas.items():
            md += ["", f"### {name}", ""]
            req = set(s.get("required", []))
            props = s.get("properties") or {}
            if not props:
                md.append(f"Type: `{_ref_name(s) or s.get('type', 'object')}`")
                continue
            md += _table(["Field", "Type", "Required", "Constraints"],
                         [[p, _ref_name(d) or d.get("type"), "yes" if p in req else "",
                           ", ".join(f"{k}={d[k]}" for k in ("format", "enum", "minLength", "maxLength",
                                                              "minimum", "maximum", "pattern") if k in d)]
                          for p, d in props.items()])
    return "\n".join(md) + "\n"


def render_index(pdir) -> str:
    sdir = pdir / "02-spec"
    frd_v, _ = _frd_requirements(pdir)
    plan = read_json(sdir / "plan.json", default={})
    wave = {fid: i for i, g in enumerate(plan.get("groups", []), 1) for fid in g}
    deps = {f["id"]: f.get("depends_on", []) for f in plan.get("features", [])}
    md = [f"# Specification index: {pdir.name}", "",
          f"Generated by `tools/spec_docs.py render`. Built from approved FRD v{frd_v}.", "",
          "## Specification documents", ""]
    rows = []
    for name, (owner, purpose) in {**AGENT_DOCS, **RENDERED_DOCS}.items():
        rows.append([f"[{name}]({name})", owner, purpose, "present" if (sdir / name).exists() else "**missing**"])
    for name, owner, purpose in [("schema.sql", "db-spec", "Reference DDL (Model layer)"),
                                 ("openapi.yaml", "api-spec", "Binding API contract"),
                                 ("commands.json", "architect", "Setup/test/lint/run commands"),
                                 ("dag.md", "dag.py", "Dependency graph and execution waves (after /plan-features)")]:
        rows.append([f"[{name}]({name})", owner, purpose, "present" if (sdir / name).exists() else "pending"])
    md += _table(["Document", "Owner", "Contents", "Status"], rows)
    md += ["", "## Feature specifications", ""]
    rows = []
    for f in _features(pdir):
        spec = sdir / "features" / f"{f['id']}.md"
        rows.append([f["id"], f["title"], f"[features/{f['id']}.md](features/{f['id']}.md)" if spec.exists() else "**missing**",
                     len(f["requirement_ids"]), open_count(spec), wave.get(f["id"], "—"), deps.get(f["id"]) or "—"])
    md += _table(["ID", "Title", "Spec", "Requirements", "OPEN items", "Wave", "Depends on"], rows)
    return "\n".join(md) + "\n"


def render(pdir) -> list[Path]:
    sdir = pdir / "02-spec"
    written = []
    if (sdir / "features.json").exists():
        (sdir / "features.md").write_text(render_features(pdir), encoding="utf-8")
        written.append(sdir / "features.md")
    if (sdir / "openapi.yaml").exists():
        (sdir / "api-spec.md").write_text(render_api(pdir), encoding="utf-8")
        written.append(sdir / "api-spec.md")
    (sdir / "index.md").write_text(render_index(pdir), encoding="utf-8")
    written.append(sdir / "index.md")
    return written


# ---------- checks ----------
def check_feature_spec(path: Path, fid: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errs = []
    first = next((l for l in text.splitlines() if l.strip()), "")
    if not first.startswith(f"# {fid}"):
        errs.append(f"{rel(path)}: first heading must be '# {fid}: <title>'")
    for s in FEATURE_SECTIONS:
        m = re.search(rf"^##\s+{re.escape(s)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        if not m:
            errs.append(f"{rel(path)}: missing section '## {s}'")
        elif not m.group(1).strip():
            errs.append(f"{rel(path)}: section '## {s}' is empty (write 'None' if nothing applies)")
    if "{{" in text:
        errs.append(f"{rel(path)}: unfilled template placeholders '{{{{…}}}}'")
    return errs


def check(pdir) -> list[str]:
    sdir = pdir / "02-spec"
    errs = [f"missing 02-spec/{n} (written by {o})" for n, (o, _) in AGENT_DOCS.items() if not (sdir / n).exists()]
    feats = _features(pdir)
    ids = {f["id"] for f in feats}
    for f in feats:
        spec = sdir / "features" / f"{f['id']}.md"
        if spec.exists():
            errs += check_feature_spec(spec, f["id"])
    for extra in sorted((sdir / "features").glob("F-*.md")) if (sdir / "features").exists() else []:
        if extra.stem not in ids:
            errs.append(f"{rel(extra)}: feature not in features.json (stale spec — remove it or add the feature)")
    # contracts agree with the breakdown
    if (sdir / "openapi.yaml").exists() and feats:
        api = _load_yaml(sdir / "openapi.yaml")
        ops = {_norm_endpoint(f"{m} {p}") for m, p, _ in _operations(api)}
        for m, p, op in _operations(api):
            tags = [t for t in op.get("tags", []) if re.fullmatch(r"F-\d{3}", str(t))]
            if not tags:
                errs.append(f"openapi.yaml: {m} {p} has no F-nnn tag")
            errs += [f"openapi.yaml: {m} {p} tagged with unknown feature {t}" for t in tags if t not in ids]
        for f in feats:
            errs += [f"{f['id']}: endpoint '{e}' from features.json is not in openapi.yaml"
                     for e in f.get("endpoints", []) if _norm_endpoint(e) not in ops]
    if (sdir / "ui-spec.md").exists():
        ui = (sdir / "ui-spec.md").read_text(encoding="utf-8").lower()
        for f in feats:
            errs += [f"{f['id']}: screen '{s}' from features.json is not described in ui-spec.md"
                     for s in f.get("screens", []) if s.lower() not in ui]
    # rendered docs must exist and be current
    expected = {"features.md": render_features if (sdir / "features.json").exists() else None,
                "api-spec.md": render_api if (sdir / "openapi.yaml").exists() else None,
                "index.md": render_index}
    for name, fn in expected.items():
        if fn is None:
            continue
        p = sdir / name
        if not p.exists():
            errs.append(f"missing 02-spec/{name} — run python tools/spec_docs.py render")
        elif p.read_text(encoding="utf-8") != fn(pdir):
            errs.append(f"02-spec/{name} is out of date — run python tools/spec_docs.py render")
    from spec_rules import run as run_rules  # SV01-SV10 content rules
    errs += run_rules(pdir).blockers
    return errs


def pending(pdir) -> list[str]:
    """Features whose spec is missing or still has blockers: the ones to (re)write on resume."""
    from spec_rules import run as run_rules
    sdir = pdir / "02-spec"
    bad = " ".join(run_rules(pdir).blockers) if (sdir / "features.json").exists() else ""
    out = []
    for f in _features(pdir):
        spec = sdir / "features" / f"{f['id']}.md"
        if not spec.exists() or check_feature_spec(spec, f["id"]) or f"features/{f['id']}.md" in bad:
            out.append(f["id"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "check", "pending", "slice"])
    ap.add_argument("feature", nargs="?", help="slice: F-nnn or 'all'")
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    if a.cmd == "render":
        for p in render(pdir):
            print(f"wrote {rel(p)}")
        return
    if a.cmd == "pending":
        todo = pending(pdir)
        print("PENDING " + " ".join(todo) if todo else "ALL FEATURE SPECS COMPLETE")
        return
    if a.cmd == "slice":
        from spec_slice import write_slice
        ids = [f["id"] for f in _features(pdir)] if a.feature in (None, "all") else [a.feature]
        for fid in ids:
            out, size = write_slice(pdir, fid)
            print(f"wrote {rel(out)} ({size // 1024} KB)")
        return
    errs = check(pdir)
    from spec_rules import run as run_rules
    warns = run_rules(pdir).warnings if (pdir / "02-spec" / "features.json").exists() else []
    for w in warns:
        print(f"  WARNING {w}")
    if errs:
        print(f"SPEC DOCS INCOMPLETE ({len(errs)}):")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    print(f"SPEC DOCS OK: {len(_features(pdir))} feature specs, all spec documents present and current"
          + (f"; {len(warns)} warning(s) to review" if warns else ""))


if __name__ == "__main__":
    main()
