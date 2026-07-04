#!/usr/bin/env python3
"""C1 mirror-drift inventory: classify every kernel/ .py file across the
pipeline (authority) and umbrella (compatibility mirror) trees.

Campaign decision: pipeline = single authority for kernel/; umbrella kernel
becomes a frozen compatibility mirror.  This script produces the baseline
inventory that the no-new-drift CI freeze-line (check_mirror_drift.py) compares
against.

Output: structured JSON to stdout (--json) or a human-readable table (default).
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Sibling-repo layout convention (per RENQUANT_REPOS.md): every subrepo is
# checked out as a sibling of this repo under a common parent directory.
# Derive from __file__ rather than hard-coding a workstation-specific home
# directory, so the baseline this script produces is portable across
# machines/CI runners instead of baking in one operator's local layout.
_SIBLINGS_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_DEFAULT = str(_SIBLINGS_ROOT / "renquant-pipeline" / "src" / "renquant_pipeline" / "kernel")
UMBRELLA_DEFAULT = str(_SIBLINGS_ROOT / "RenQuant" / "backtesting" / "renquant_104" / "kernel")


def _collect_py_files(root: Path) -> set[str]:
    result: set[str] = set()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".py") and "__pycache__" not in dirpath:
                rel = os.path.relpath(os.path.join(dirpath, f), root)
                result.add(rel)
    return result


def _is_import_only_diff(pipeline_lines: list[str], umbrella_lines: list[str]) -> bool:
    """True when every changed line is an import/from statement or blank."""
    diff = list(difflib.unified_diff(pipeline_lines, umbrella_lines, lineterm=""))
    changed = [
        ln for ln in diff
        if ln.startswith(("+", "-"))
        and not ln.startswith(("+++", "---"))
    ]
    for ln in changed:
        content = ln[1:].strip()
        if not content:
            continue
        if not re.match(r"^(from|import)\s", content):
            return False
    return len(changed) > 0


def _diff_summary(pipeline_lines: list[str], umbrella_lines: list[str]) -> str:
    """One-line summary of what changed between the two versions."""
    added_funcs: list[str] = []
    removed_funcs: list[str] = []
    added_lines = 0
    removed_lines = 0

    diff = list(difflib.unified_diff(pipeline_lines, umbrella_lines, lineterm=""))
    for ln in diff:
        if ln.startswith("+") and not ln.startswith("+++"):
            added_lines += 1
            m = re.match(r"^\+\s*(def|class)\s+(\w+)", ln)
            if m:
                added_funcs.append(m.group(2))
        elif ln.startswith("-") and not ln.startswith("---"):
            removed_lines += 1
            m = re.match(r"^-\s*(def|class)\s+(\w+)", ln)
            if m:
                removed_funcs.append(m.group(2))

    parts: list[str] = []
    if added_funcs:
        parts.append(f"+{','.join(added_funcs[:3])}")
    if removed_funcs:
        parts.append(f"-{','.join(removed_funcs[:3])}")
    parts.append(f"+{added_lines}/-{removed_lines} lines")
    return "; ".join(parts)


def _guess_umbrella_only_disposition(rel: str, root: Path) -> str:
    """Heuristic for umbrella-only files: LIFT (useful feature) or RETIRE."""
    full = root / rel
    try:
        text = full.read_text(errors="replace")
    except OSError:
        return "UNKNOWN"
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) < 5:
        return "RETIRE"
    if any(kw in text for kw in ("DEPRECATED", "legacy", "REMOVE")):
        return "RETIRE"
    return "LIFT"


def build_inventory(
    pipeline_root: Path,
    umbrella_root: Path,
) -> dict[str, Any]:
    pipeline_files = _collect_py_files(pipeline_root)
    umbrella_files = _collect_py_files(umbrella_root)
    shared = sorted(pipeline_files & umbrella_files)
    pipeline_only = sorted(pipeline_files - umbrella_files)
    umbrella_only = sorted(umbrella_files - pipeline_files)

    identical: list[str] = []
    trivial_drift: list[str] = []
    material_drift: list[dict[str, str]] = []

    for rel in shared:
        p_lines = (pipeline_root / rel).read_text(errors="replace").splitlines()
        u_lines = (umbrella_root / rel).read_text(errors="replace").splitlines()
        if p_lines == u_lines:
            identical.append(rel)
        elif _is_import_only_diff(p_lines, u_lines):
            trivial_drift.append(rel)
        else:
            summary = _diff_summary(p_lines, u_lines)
            material_drift.append({"file": rel, "summary": summary})

    umbrella_dispositions = [
        {"file": rel, "disposition": _guess_umbrella_only_disposition(rel, umbrella_root)}
        for rel in umbrella_only
    ]

    return {
        "pipeline_root": str(pipeline_root),
        "umbrella_root": str(umbrella_root),
        "counts": {
            "pipeline_total": len(pipeline_files),
            "umbrella_total": len(umbrella_files),
            "shared": len(shared),
            "pipeline_only": len(pipeline_only),
            "umbrella_only": len(umbrella_only),
            "identical": len(identical),
            "trivial_drift": len(trivial_drift),
            "material_drift": len(material_drift),
        },
        "identical": identical,
        "trivial_drift": trivial_drift,
        "material_drift": material_drift,
        "pipeline_only": pipeline_only,
        "umbrella_only": umbrella_dispositions,
    }


def _print_table(inventory: dict[str, Any]) -> None:
    c = inventory["counts"]
    print("=" * 72)
    print("C1 MIRROR-DRIFT INVENTORY")
    print(f"  Pipeline: {inventory['pipeline_root']}")
    print(f"  Umbrella: {inventory['umbrella_root']}")
    print("=" * 72)
    print(f"\n  Pipeline total:  {c['pipeline_total']}")
    print(f"  Umbrella total:  {c['umbrella_total']}")
    print(f"  Shared:          {c['shared']}")
    print(f"    Identical:     {c['identical']}")
    print(f"    Trivial drift: {c['trivial_drift']}")
    print(f"    Material drift:{c['material_drift']}")
    print(f"  Pipeline-only:   {c['pipeline_only']}")
    print(f"  Umbrella-only:   {c['umbrella_only']}")

    if inventory["material_drift"]:
        print(f"\n{'─' * 72}")
        print("MATERIAL DRIFT (reconciliation needed)")
        print(f"{'─' * 72}")
        for entry in inventory["material_drift"]:
            print(f"  {entry['file']}")
            print(f"    {entry['summary']}")

    if inventory["umbrella_only"]:
        print(f"\n{'─' * 72}")
        print("UMBRELLA-ONLY (disposition)")
        print(f"{'─' * 72}")
        for entry in inventory["umbrella_only"]:
            print(f"  [{entry['disposition']}] {entry['file']}")

    if inventory["pipeline_only"]:
        print(f"\n{'─' * 72}")
        print("PIPELINE-ONLY (authority-native)")
        print(f"{'─' * 72}")
        for f in inventory["pipeline_only"]:
            print(f"  {f}")

    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", default=PIPELINE_DEFAULT, help="Pipeline kernel root")
    parser.add_argument("--umbrella", default=UMBRELLA_DEFAULT, help="Umbrella kernel root")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args(argv)

    pipeline_root = Path(args.pipeline)
    umbrella_root = Path(args.umbrella)

    if not pipeline_root.is_dir():
        print(f"ERROR: pipeline root not found: {pipeline_root}", file=sys.stderr)
        return 1
    if not umbrella_root.is_dir():
        print(f"ERROR: umbrella root not found: {umbrella_root}", file=sys.stderr)
        return 1

    inventory = build_inventory(pipeline_root, umbrella_root)

    if args.json:
        json.dump(inventory, sys.stdout, indent=2)
        print()
    else:
        _print_table(inventory)

    return 0


if __name__ == "__main__":
    sys.exit(main())
