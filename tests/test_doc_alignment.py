"""CI staleness check for the strategy snapshot (M9).

Compares the live-generated snapshot against the committed baseline.
If this test fails, run::

    python scripts/generate_strategy_snapshot.py --update

then commit the updated ``data/strategy_snapshot.json``.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "data" / "strategy_snapshot.json"


def _generate_live() -> dict:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gen", REPO / "scripts" / "generate_strategy_snapshot.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.generate()


def test_snapshot_not_stale():
    """Committed baseline must match the live-generated snapshot."""
    assert BASELINE.exists(), (
        f"{BASELINE.relative_to(REPO)} missing — run:\n"
        "  python scripts/generate_strategy_snapshot.py --update"
    )
    baseline = json.loads(BASELINE.read_text())
    live = _generate_live()

    for key in ("cli_subcommands", "pyproject_entrypoints", "source_modules"):
        baseline_val = baseline.get(key)
        live_val = live.get(key)
        if baseline_val != live_val:
            if isinstance(live_val, list) and isinstance(baseline_val, list):
                added = sorted(set(live_val) - set(baseline_val))
                removed = sorted(set(baseline_val) - set(live_val))
                diff_msg = ""
                if added:
                    diff_msg += f"\n  added:   {added}"
                if removed:
                    diff_msg += f"\n  removed: {removed}"
            elif isinstance(live_val, dict) and isinstance(baseline_val, dict):
                added = sorted(set(live_val) - set(baseline_val))
                removed = sorted(set(baseline_val) - set(live_val))
                diff_msg = ""
                if added:
                    diff_msg += f"\n  added:   {added}"
                if removed:
                    diff_msg += f"\n  removed: {removed}"
            else:
                diff_msg = f"\n  baseline: {baseline_val}\n  live:     {live_val}"

            raise AssertionError(
                f"Snapshot stale on '{key}':{diff_msg}\n"
                "Run: python scripts/generate_strategy_snapshot.py --update"
            )


def test_design_docs_exist():
    """Every design doc referenced in the snapshot must exist on disk."""
    if not BASELINE.exists():
        return
    baseline = json.loads(BASELINE.read_text())
    design_dir = REPO / "doc" / "design"
    for doc in baseline.get("design_docs", []):
        assert (design_dir / doc).exists(), f"design doc missing: doc/design/{doc}"


def test_cli_subcommand_count_sanity():
    """Catch accidental removal of CLI subcommands."""
    if not BASELINE.exists():
        return
    baseline = json.loads(BASELINE.read_text())
    cmds = baseline.get("cli_subcommands", [])
    assert len(cmds) >= 25, (
        f"Only {len(cmds)} CLI subcommands in baseline — expected ≥25. "
        "Did someone accidentally drop subcommands?"
    )
