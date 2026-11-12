#!/usr/bin/env python
"""Validate an agent output file against a JSON schema in schemas/.

Usage: validate.py <schema-name> <file.json>
  e.g. validate.py requirements projects/leave-demo/01-frd/frd.v1.json
Exit 0 = valid, 1 = invalid (errors printed so the producing agent can fix them).
"""
from __future__ import annotations

import sys
from pathlib import Path

from common import ROOT, SCHEMAS, read_json, rel


def validate(schema_name: str, file: Path) -> list[str]:
    import jsonschema
    schema = read_json(SCHEMAS / f"{schema_name}.schema.json")
    try:
        data = read_json(file)
    except Exception as e:  # malformed JSON
        return [f"invalid JSON: {e}"]
    v = jsonschema.Draft202012Validator(schema)
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in sorted(v.iter_errors(data), key=lambda e: list(e.absolute_path))]
    # Semantic checks shared by several artifacts.
    if schema_name == "requirements":
        seen = set()
        for r in data.get("requirements", []):
            if r.get("id") in seen:
                errors.append(f"duplicate requirement id {r['id']}")
            seen.add(r.get("id"))
            if any(s.startswith("CHECKLIST-") for s in r.get("source", [])) and r.get("status") != "assumed":
                errors.append(f"{r.get('id')}: checklist-derived requirement must have status 'assumed'")
            if r.get("priority") == "must" and not r.get("acceptance_criteria"):
                errors.append(f"{r.get('id')}: 'must' requirement has no acceptance criteria")
    if schema_name == "features":
        ids = [f["id"] for f in data.get("features", [])]
        dups = {i for i in ids if ids.count(i) > 1}
        if dups:
            errors.append(f"duplicate feature ids {sorted(dups)}")
    return errors


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    f = Path(sys.argv[2])
    if not f.is_absolute():
        f = ROOT / f
    errs = validate(sys.argv[1], f)
    if errs:
        print(f"INVALID {rel(f)} against {sys.argv[1]}:")
        for e in errs[:50]:
            print(f"  - {e}")
        sys.exit(1)
    print(f"VALID {rel(f)} ({sys.argv[1]})")


if __name__ == "__main__":
    main()
