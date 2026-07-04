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


COMPARED_KEYS = (
    "cli_subcommands",
    "pyproject_entrypoints",
    "scheduled_jobs",
    "design_docs",
    "source_modules",
)


def _assert_snapshot_matches(baseline: dict, live: dict) -> None:
    for key in COMPARED_KEYS:
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


def test_snapshot_not_stale():
    """Committed baseline must match the live-generated snapshot."""
    assert BASELINE.exists(), (
        f"{BASELINE.relative_to(REPO)} missing — run:\n"
        "  python scripts/generate_strategy_snapshot.py --update"
    )
    baseline = json.loads(BASELINE.read_text())
    live = _generate_live()
    _assert_snapshot_matches(baseline, live)


def test_snapshot_catches_scheduled_jobs_drift():
    """A job registry drift not reflected in the baseline must fail staleness."""
    baseline = json.loads(BASELINE.read_text())
    live = dict(baseline)
    live["scheduled_jobs"] = [*baseline["scheduled_jobs"], "a_new_job_nobody_updated_the_baseline_for"]

    try:
        _assert_snapshot_matches(baseline, live)
    except AssertionError as exc:
        assert "scheduled_jobs" in str(exc)
    else:
        raise AssertionError("expected staleness check to catch the injected scheduled_jobs drift")


def test_snapshot_catches_design_docs_drift():
    """A design doc drift not reflected in the baseline must fail staleness."""
    baseline = json.loads(BASELINE.read_text())
    live = dict(baseline)
    live["design_docs"] = [*baseline["design_docs"], "2099-01-01-a-new-design-doc-nobody-committed.md"]

    try:
        _assert_snapshot_matches(baseline, live)
    except AssertionError as exc:
        assert "design_docs" in str(exc)
    else:
        raise AssertionError("expected staleness check to catch the injected design_docs drift")


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
