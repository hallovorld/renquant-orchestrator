#!/usr/bin/env python3
"""GOAL-3: an internal duplicate-definition CENSUS, and the guard's missing root.

TWO SEPARATE THINGS, kept separate on purpose [codex on orch#814].

**(a) The census this script computes.** For one package: which module-level
public names are defined in MORE THAN ONE file, and whether the bodies are
identical (a copy — divergence risk) or differ (the twin shape — which one does
a caller reach?). It also reports how many of those names are in `__all__`.

**(b) What it deliberately does NOT compute.** renquant-pipeline's guard
(`tools/twin_pairs.py`) does not use this relation. It resolves each `__all__`
export to its source object and looks for a same-named definition under one
CONFIGURED counterpart root, `kernel/`. This script's all-files, same-name scan
is broader and is NOT a stand-in for it: a collision found here is not a pair
the guard would have found, and the two counts must not be compared. An earlier
version of this file did compare them and reported a "guard subject coverage"
percentage — that number was measuring the documented API against unrelated
internal names, and it is gone.

The separately measurable fact about the guard, which needs no new machinery
`[VERIFIED — 2026-08-05]`: `renquant-pipeline` is the only repo with a `kernel/`
root at all. In every other repo the guard's relation is UNDEFINED — not
"passes", not "clean", undefined — so "install it there" is not yet a
well-formed proposal.

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

    return {
        "package": package,
        "all_size": len(exported),
        # UNIQUE NAMES, not sites [codex on orch#814]: `public_defs` is a
        # set, and `__all__` is also a name set, so a name-to-name
        # comparison is the coherent one — but the field must SAY name.
        "unique_public_def_names": len(public_defs),
        "n_duplicate_names": len(duplicates),
        # Whether a duplicate name is also EXPORTED is worth recording, but it
        # is NOT "visible to the guard": the guard's relation is a same-named
        # definition under `kernel/`, which this scan does not compute.
        "duplicates_that_are_exported": sorted(
            n for n, d in duplicates.items() if d["exported"]),
        "duplicates_not_exported": sorted(
            n for n, d in duplicates.items() if not d["exported"]),
        "has_kernel_counterpart_root": (root / "kernel").is_dir(),
        "duplicates": duplicates,
    }


def _root_note(result: dict) -> str:
    if result["has_kernel_counterpart_root"]:
        return "present"
    return ("ABSENT — the pipeline guard's relation (export ↔ same-named def "
            "under kernel/) is UNDEFINED here, not 'clean'")


def render(result: dict) -> str:
    lines = [
        f"GOAL-3 duplicate-definition census — {result['package']}",
        "",
        f"  __all__ ...................... {result['all_size']}",
        f"  unique public def NAMES ...... {result['unique_public_def_names']}",
        f"  duplicate-definition names ... {result['n_duplicate_names']}",
        f"    also exported ............ {len(result['duplicates_that_are_exported'])}",
        f"    not exported ............. {len(result['duplicates_not_exported'])}",
        f"  kernel/ counterpart root ..... {_root_note(result)}",
        "",
    ]
    for name in result["duplicates_not_exported"][:12]:
        d = result["duplicates"][name]
        where = ", ".join(f"{s['file']}({s['n_lines']}L)" for s in d["sites"])
        lines.append(f"  [{d['shape']}] {name}: {where}")
    if len(result["duplicates_not_exported"]) > 12:
        lines.append(f"  … and {len(result['duplicates_not_exported']) - 12} more")
    lines.append("")
    lines.append("  A duplicate is a CANDIDATE, not a verdict: confirming one means "
                 "reading both\n  bodies and deciding which the callers reach. This is "
                 "the work list, not the audit.\n  This census is NOT the pipeline "
                 "guard's relation and must not be compared to its counts.")
    return "\n".join(lines)


# The exact packages the record's table lists. A claim about "every repo" has to
# name them and be measurable over them, or it is a claim about the two I ran.
# [codex on orch#814]
SURVEYED_PACKAGES = (
    "renquant_pipeline", "renquant_orchestrator", "renquant_backtesting",
    "renquant_common", "renquant_execution", "renquant_base_data",
    "renquant_strategy_104",
)


def kernel_root_map(packages=SURVEYED_PACKAGES) -> dict:
    """{package: True | False | None} — has a `kernel/` counterpart root.

    `None` means NOT MEASURED (the package could not be imported here), never
    False: an unimportable package is not evidence of an absent root.
    """
    out = {}
    for name in packages:
        try:
            module = importlib.import_module(name)
        except Exception:                        # noqa: BLE001
            out[name] = None
            continue
        out[name] = (pathlib.Path(module.__file__).parent / "kernel").is_dir()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package", nargs="?", default="renquant_orchestrator")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kernel-root-map", action="store_true",
                    help="print the has-a-kernel-root map over the surveyed "
                         "packages and exit")
    args = ap.parse_args(argv)
    if args.kernel_root_map:
        print(json.dumps(kernel_root_map(), indent=2))
        return 0
    result = audit(args.package)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
