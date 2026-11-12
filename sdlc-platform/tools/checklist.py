#!/usr/bin/env python
"""Rule-based domain checklist evaluation (roadmap §2.3, §2.5).

Usage: checklist.py [--version N] [--project ID] [--domain SLUG]
Reads  01-frd/frd.vN.json, 01-frd/crd.md, 01-frd/domain.json
Writes 01-frd/checklist.vN.json and prints a summary.

Mandatory items that are missing or only weakly covered FAIL the quality gate,
regardless of the evaluator's scores (a high average never overrides a mandatory failure).
Exit code: 0 = no mandatory failures, 1 = mandatory failures.
"""
from __future__ import annotations

import argparse
import sys

from common import KNOWLEDGE, die, latest_version, project_dir, read_json, read_yaml, rel, write_json, now


def load_items(domain: str | None):
    items, packs = [], []
    for pack in ["_generic", domain]:
        if not pack:
            continue
        f = KNOWLEDGE / pack / "checklist.yaml"
        if f.exists():
            items.extend(read_yaml(f)["items"])
            packs.append(pack)
    return items, packs


def req_text(r) -> str:
    return " ".join([r.get("title", ""), r.get("statement", ""), " ".join(r.get("acceptance_criteria", []))]).lower()


def matches(text: str, groups) -> bool:
    return all(any(str(k).lower() in text for k in group) for group in groups)


def evaluate(frd: dict, crd_text: str, items: list) -> list:
    crd_lower = crd_text.lower()
    reqs = [r for r in frd["requirements"] if r.get("priority") != "wont"]
    results = []
    for it in items:
        res = {k: it.get(k) for k in ("id", "level", "category", "description")}
        applicable = True
        if it["level"] == "conditional":
            applicable = any(str(k).lower() in crd_lower for k in it.get("applies_if", []))
        res["applicable"] = applicable
        if not applicable:
            res.update(status="n/a", covered_by=[], tagged_without_evidence=[])
            results.append(res)
            continue
        tagged = [r for r in reqs if it["id"] in (r.get("checklist_refs") or [])]
        evidenced = [r for r in tagged if matches(req_text(r), it["match"])]
        if evidenced:
            status = "covered"
        elif tagged:
            status = "weak"  # tagged, but text does not substantiate the claim
        else:
            status = "missing"
        res.update(
            status=status,
            covered_by=[r["id"] for r in evidenced],
            tagged_without_evidence=[r["id"] for r in tagged if r not in evidenced],
            assumed_only=bool(evidenced) and all(r.get("status") == "assumed" for r in evidenced),
        )
        results.append(res)
    return results


STATUS_TEXT = {"covered": "Covered", "weak": "Weak (tagged, not substantiated)", "missing": "Missing", "n/a": "Not applicable"}


def write_markdown(path, out):
    lines = [f"# Domain checklist: FRD v{out['frd_version']}", "",
             f"Domain: **{out['domain'] or '?'}** · Packs used: {', '.join(out['packs_used'])} · "
             f"Result: **{'PASSED' if out['passed'] else 'FAILED'}** · Evaluated: {out['evaluated_at']}", ""]
    if out["domain"] and not out["domain_pack_found"]:
        lines += [f"> No domain pack exists for `{out['domain']}`: only generic checks were applied.", ""]
    lines += ["Mandatory and applicable conditional items must be **Covered** for the FRD to pass. "
              "A high evaluator score never overrides a failure here.", "",
              "| Item | Category | Level | Status | Covered by | Description |", "|---|---|---|---|---|---|"]
    order = {"mandatory": 0, "conditional": 1, "recommended": 2}
    for r in sorted(out["items"], key=lambda x: (order.get(x["level"], 9), x["id"])):
        by = ", ".join(r.get("covered_by") or r.get("tagged_without_evidence") or []) or "-"
        if r.get("assumed_only"):
            by += " (assumed only; confirm with client)"
        lines.append(f"| {r['id']} | {r['category']} | {r['level']} | {STATUS_TEXT[r['status']]} | {by} | {r['description']} |")
    s = out["summary"]
    lines += ["", "## Summary",
              f"- Mandatory failed: {', '.join(s['mandatory_failed']) or 'none'}",
              f"- Applicable conditional failed: {', '.join(s['conditional_failed']) or 'none'}",
              f"- Recommended missing: {', '.join(s['recommended_missing']) or 'none'}",
              f"- Needs client confirmation: {', '.join(s['needs_client_confirmation']) or 'none'}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def show(domain):
    items, packs = load_items(domain)
    print(f"Checklist items for domain '{domain or 'generic'}' (packs: {', '.join(packs)})")
    if domain and domain not in packs:
        print(f"  no domain pack for '{domain}': add knowledge/domains/{domain}/checklist.yaml")
    for it in items:
        cond = f"  [applies if CRD mentions: {', '.join(it['applies_if'])}]" if it.get("applies_if") else ""
        print(f"  {it['id']:<18} {it['level']:<11} {it['description']}{cond}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int)
    ap.add_argument("--project")
    ap.add_argument("--domain")
    ap.add_argument("--show", action="store_true", help="list the checklist items that apply; evaluate nothing")
    a = ap.parse_args()
    if a.show and a.domain:
        show(a.domain)
        return
    pdir = project_dir(a.project)
    fdir = pdir / "01-frd"
    if a.show:
        show(read_json(fdir / "domain.json", default={}).get("domain"))
        return
    v = a.version or latest_version(fdir, "frd", "json")
    if not v:
        die("no frd.vN.json found — run /generate-frd first")
    frd = read_json(fdir / f"frd.v{v}.json")
    crd_text = (fdir / "crd.md").read_text(encoding="utf-8")
    domain = a.domain or read_json(fdir / "domain.json", default={}).get("domain")
    items, packs = load_items(domain)
    results = evaluate(frd, crd_text, items)

    mandatory_failed = [r["id"] for r in results if r["level"] == "mandatory" and r["status"] in ("missing", "weak")]
    conditional_failed = [r["id"] for r in results if r["level"] == "conditional" and r["status"] in ("missing", "weak")]
    recommended_missing = [r["id"] for r in results if r["level"] == "recommended" and r["status"] in ("missing", "weak")]
    needs_confirmation = [r["id"] for r in results if r.get("assumed_only")]
    out = {
        "frd_version": v,
        "evaluated_at": now(),
        "domain": domain,
        "packs_used": packs,
        "domain_pack_found": domain in packs,
        "items": results,
        "summary": {
            "mandatory_failed": mandatory_failed,
            "conditional_failed": conditional_failed,
            "recommended_missing": recommended_missing,
            "needs_client_confirmation": needs_confirmation,
        },
        "passed": not mandatory_failed and not conditional_failed,
    }
    dest = fdir / f"checklist.v{v}.json"
    write_json(dest, out)
    write_markdown(fdir / f"checklist.v{v}.md", out)

    print(f"Checklist for frd.v{v} (packs: {', '.join(packs)})")
    for r in results:
        flag = {"covered": "OK  ", "weak": "WEAK", "missing": "MISS", "n/a": "n/a "}[r["status"]]
        extra = ",".join(r.get("covered_by") or r.get("tagged_without_evidence") or [])
        conf = " (assumed-only)" if r.get("assumed_only") else ""
        print(f"  [{flag}] {r['id']:<16} {r['level']:<11} {extra}{conf}")
    if domain and domain not in packs:
        print(f"WARNING: no domain pack for '{domain}' — only generic checks applied; reviewer must judge domain coverage.")
    print(f"mandatory_failed={mandatory_failed} conditional_failed={conditional_failed}")
    print(f"recommended_missing={recommended_missing} needs_client_confirmation={needs_confirmation}")
    print(f"-> {rel(dest)}  {'PASSED' if out['passed'] else 'FAILED'}")
    sys.exit(0 if out["passed"] else 1)


if __name__ == "__main__":
    main()
