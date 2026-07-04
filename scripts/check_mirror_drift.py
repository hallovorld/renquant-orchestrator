#!/usr/bin/env python3
"""C1 no-new-drift CI freeze-line: report any kernel files that drifted
since the last inventory baseline.

Compares the current pipeline/umbrella kernel state against the committed
baseline inventory (data/c1_drift_baseline.json).  New drift (files that
were IDENTICAL or TRIVIAL in the baseline but are now MATERIAL) is reported.
Files already classified as MATERIAL in the baseline are expected and skipped.

Exit codes:
  0  no new drift (or --report-only mode, always 0)
  1  new drift detected (strict mode only, not yet enabled)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mirror_drift_inventory import build_inventory, PIPELINE_DEFAULT, UMBRELLA_DEFAULT

BASELINE_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "c1_drift_baseline.json"


def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as fh:
        return json.load(fh)


def _baseline_known_material(baseline: dict) -> set[str]:
    return {e["file"] for e in baseline.get("material_drift", [])}


def _baseline_known_files(baseline: dict) -> set[str]:
    """All files the baseline knows about, in any category."""
    known: set[str] = set()
    known.update(baseline.get("identical", []))
    known.update(baseline.get("trivial_drift", []))
    known.update(_baseline_known_material(baseline))
    known.update(baseline.get("pipeline_only", []))
    known.update(e["file"] for e in baseline.get("umbrella_only", []))
    return known


def check_drift(
    pipeline_root: Path,
    umbrella_root: Path,
    baseline_path: Path,
    *,
    report_only: bool = True,
) -> int:
    baseline = load_baseline(baseline_path)
    if not baseline:
        print("WARNING: no baseline found — run mirror_drift_inventory.py --json > data/c1_drift_baseline.json first")
        return 0

    current = build_inventory(pipeline_root, umbrella_root)
    baseline_material = _baseline_known_material(baseline)
    baseline_all = _baseline_known_files(baseline)

    new_drift: list[dict] = []
    for entry in current["material_drift"]:
        if entry["file"] not in baseline_material:
            new_drift.append(entry)

    new_files: list[str] = []
    current_all_files: set[str] = set()
    current_all_files.update(current["identical"])
    current_all_files.update(current["trivial_drift"])
    current_all_files.update(e["file"] for e in current["material_drift"])
    current_all_files.update(current["pipeline_only"])
    current_all_files.update(e["file"] for e in current["umbrella_only"])
    for f in sorted(current_all_files - baseline_all):
        new_files.append(f)

    if not new_drift and not new_files:
        print(f"C1 freeze-line OK: no new drift (baseline has {len(baseline_material)} known material files)")
        return 0

    if new_drift:
        print(f"NEW DRIFT: {len(new_drift)} file(s) drifted since baseline:")
        for entry in new_drift:
            print(f"  {entry['file']}: {entry['summary']}")

    if new_files:
        print(f"NEW FILES: {len(new_files)} file(s) not in baseline:")
        for f in new_files:
            print(f"  {f}")

    if report_only:
        print("(report-only mode — exit 0)")
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", default=PIPELINE_DEFAULT)
    parser.add_argument("--umbrella", default=UMBRELLA_DEFAULT)
    parser.add_argument("--baseline", default=str(BASELINE_DEFAULT))
    parser.add_argument("--strict", action="store_true", help="Exit 1 on new drift (not yet enabled in CI)")
    args = parser.parse_args(argv)

    return check_drift(
        Path(args.pipeline),
        Path(args.umbrella),
        Path(args.baseline),
        report_only=not args.strict,
    )


if __name__ == "__main__":
    sys.exit(main())
