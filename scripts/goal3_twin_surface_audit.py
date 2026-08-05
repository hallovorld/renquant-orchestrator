#!/usr/bin/env python3
"""GOAL-3: what can the twin-implementation guard actually SEE?

renquant-pipeline's `tools/twin_pairs.py` scans the names in `__all__` and pins
a digest for each side of every public/kernel pair. That guard exists in ONE
repo. The obvious next question — "should the other repos have it too?" — has a
prior question this script answers: **would it see anything there?**

The guard's SUBJECT is `__all__`. Measured 2026-08-05, `__all__` covers 3 of
renquant-orchestrator's 949 module-level public definitions. A guard installed
on that surface would report clean forever — not because the repo is clean, but
because its subject is nearly empty. That is the same defect class the twin
registry itself records (a check whose subject is not the object you assume),
one level up.

WHAT THIS MEASURES, precisely, and nothing more:
  * `__all__` size vs the count of module-level public definitions;
  * names defined at module level in MORE THAN ONE file ("duplicate-definition
    sites"), split by whether they are exported;
  * for each duplicate, whether the bodies are IDENTICAL (a copy) or DIFFER
    (the twin shape).

WHAT IT DOES NOT CLAIM: that every duplicate is a twin. Same-name-in-two-files
is a candidate, not a verdict — confirming one means reading both bodies and
deciding which the callers reach. This script produces the work list; it does
not do the reading.

Read-only. Usage:  python scripts/goal3_twin_surface_audit.py <package> [--json]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import pathlib
import sys


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def audit(package: str) -> dict:
    module = importlib.import_module(package)
    exported = set(getattr(module, "__all__", []) or [])
    root = pathlib.Path(module.__file__).parent

    sites: dict[str, list[dict]] = {}
    public_defs: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in tree.body:                       # MODULE level only
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            public_defs.add(node.name)
            segment = ast.get_source_segment(text, node) or ""
            sites.setdefault(node.name, []).append({
                "file": str(path.relative_to(root)),
                "body_sha256": _digest(segment),
                "n_lines": len(segment.splitlines()),
            })

    duplicates = {}
    for name, where in sites.items():
        if len(where) < 2:
            continue
        digests = {w["body_sha256"] for w in where}
        duplicates[name] = {
            "exported": name in exported,
            # IDENTICAL bodies are a copy (divergence risk); DIFFERENT bodies
            # are the twin shape (which copy runs?).
            "shape": "identical-copy" if len(digests) == 1 else "differing-bodies",
            "sites": sorted(where, key=lambda w: w["file"]),
        }

    visible = sorted(n for n, d in duplicates.items() if d["exported"])
    invisible = sorted(n for n, d in duplicates.items() if not d["exported"])
    return {
        "package": package,
        "all_size": len(exported),
        "public_module_level_defs": len(public_defs),
        "guard_subject_coverage": (round(len(exported) / len(public_defs), 4)
                                   if public_defs else None),
        "n_duplicate_names": len(duplicates),
        "visible_to_an_all_scoped_guard": visible,
        "INVISIBLE_to_an_all_scoped_guard": invisible,
        "duplicates": duplicates,
    }


def render(result: dict) -> str:
    cov = result["guard_subject_coverage"]
    lines = [
        f"GOAL-3 twin-guard subject audit — {result['package']}",
        "",
        f"  __all__ ...................... {result['all_size']}",
        f"  module-level public defs ..... {result['public_module_level_defs']}",
        f"  guard subject coverage ....... "
        f"{'n/a' if cov is None else f'{cov:.1%}'}",
        f"  duplicate-definition names ... {result['n_duplicate_names']}",
        f"    visible to an __all__ guard  {len(result['visible_to_an_all_scoped_guard'])}",
        f"    INVISIBLE to it ............ {len(result['INVISIBLE_to_an_all_scoped_guard'])}",
        "",
    ]
    for name in result["INVISIBLE_to_an_all_scoped_guard"][:12]:
        d = result["duplicates"][name]
        where = ", ".join(f"{s['file']}({s['n_lines']}L)" for s in d["sites"])
        lines.append(f"  [{d['shape']}] {name}: {where}")
    if len(result["INVISIBLE_to_an_all_scoped_guard"]) > 12:
        lines.append(f"  … and {len(result['INVISIBLE_to_an_all_scoped_guard']) - 12} more")
    lines.append("")
    lines.append("  A duplicate is a CANDIDATE, not a verdict: confirming one means "
                 "reading both\n  bodies and deciding which the callers reach. This is "
                 "the work list, not the audit.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = audit(args.package)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
