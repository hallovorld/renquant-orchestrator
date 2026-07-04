"""expkit.runner — the end-to-end pipeline: freeze check -> controls gate ->
evaluation -> stats -> verdict -> evidence bundle."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator.expkit.controls import plant_mean_shift, sign_flip_null
from renquant_orchestrator.expkit.prereg import Criterion, FrozenSpec, SpecNotFrozenError
from renquant_orchestrator.expkit.runner import (
    ExperimentPlugin,
    gate_per_date,
    run_experiment,
)
from renquant_orchestrator.expkit.verdict import Outcome

BOUNDARY = {
    "window": "synthetic 700 dates",
    "cells": "one",
    "outcome_era": "synthetic",
    "cost_model": "none",
    "substrate": "synthetic (declared)",
    "multiplicity": "k=1",
    "not_covered": "anything real",
}


def make_spec(**overrides) -> FrozenSpec:
    kwargs = dict(
        experiment_id="toy_experiment",
        hypothesis="the synthetic mean clears the bar",
        criteria=(Criterion(name="bar", threshold=0.015),),
        family_size_k=1,
        seeds=(42, 43, 44),
        evidence_boundary=BOUNDARY,
        reopening_conditions=("never — synthetic",),
        block=5,
        n_boot=400,
        min_decision_dates=600,
    )
    kwargs.update(overrides)
    return FrozenSpec(**kwargs)


def synth_per_date(mean: float, n: int = 700, sd: float = 0.05, seed: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    clean = rng.standard_normal(n) * sd + mean
    return pd.DataFrame(
        {"real_ic": clean + 0.04, "placebo_ic": np.full(n, 0.04), "clean_ic": clean},
        index=dates,
    )


def make_plugin(spec: FrozenSpec, per_date: pd.DataFrame, **overrides) -> ExperimentPlugin:
    clean = per_date["clean_ic"]
    kwargs = dict(
        spec=spec,
        load_substrate=lambda: per_date,
        evaluate=lambda sub: sub,
        positive_control=lambda sub: plant_mean_shift(clean, 0.10),
        null_control=lambda sub: sign_flip_null(clean, seed=142),
        declared_plant_effect=0.10,
    )
    kwargs.update(overrides)
    return ExperimentPlugin(**kwargs)


# ---------------------------------------------------------------------------
# gate_per_date
# ---------------------------------------------------------------------------
def test_gate_per_date_detects_planted_positive():
    spec = make_spec()
    summary, decision = gate_per_date(synth_per_date(0.05), spec, controls_ok=True)
    assert decision.mechanical_outcome is Outcome.GO
    assert summary["n_dates"] == 700
    assert summary["mean_placebo_ic"] == pytest.approx(0.04)


def test_gate_per_date_without_controls_is_non_voting():
    spec = make_spec()
    _, decision = gate_per_date(synth_per_date(0.05), spec, controls_ok=None)
    assert decision.outcome is Outcome.NON_VOTING
    assert decision.mechanical_outcome is Outcome.GO


def test_gate_per_date_small_n_flows_to_exact():
    spec = make_spec(block=60, min_decision_dates=600)
    _, decision = gate_per_date(synth_per_date(0.2, n=10), spec, controls_ok=True)
    assert decision.method == "exact"
    assert decision.requires_null_control


def test_gate_per_date_series_input_and_missing_clean_column():
    spec = make_spec()
    s = synth_per_date(0.05)["clean_ic"]
    _, decision = gate_per_date(s, spec, controls_ok=True)
    assert decision.mechanical_outcome is Outcome.GO
    with pytest.raises(ValueError, match="clean_ic"):
        gate_per_date(pd.DataFrame({"x": [1.0]}), spec, controls_ok=True)


# ---------------------------------------------------------------------------
# run_experiment end to end
# ---------------------------------------------------------------------------
def test_run_experiment_go_with_passing_controls(tmp_path: Path):
    spec = make_spec()
    plugin = make_plugin(spec, synth_per_date(0.05))
    result = run_experiment(plugin, out_dir=tmp_path, repo_root=tmp_path)
    assert result.outcome == "GO"
    assert result.controls.all_passed
    assert result.spec is spec
    # evidence bundle round-trips with the spec hash stamped
    payload = json.loads(result.evidence_path.read_text())
    assert payload["spec_sha256"] == spec.sha256()
    assert payload["decision"]["outcome"] == "GO"
    assert payload["controls"]["all_passed"] is True
    assert payload["manifest"]["seeds"] == [42, 43, 44]
    assert result.per_date_path.exists()


def test_run_experiment_failing_positive_control_blocks_verdict(tmp_path: Path):
    spec = make_spec()
    per_date = synth_per_date(0.05)
    # a broken plant: does nothing -> the harness cannot demonstrate detection
    plugin = make_plugin(
        spec,
        per_date,
        positive_control=lambda sub: sign_flip_null(per_date["clean_ic"], seed=1),
    )
    result = run_experiment(plugin, repo_root=tmp_path)
    assert result.outcome == "NON-VOTING"
    assert not result.controls.positive.passed
    assert any("controls_failed" in r for r in result.decision.non_voting_reasons)
    assert result.decision.mechanical_outcome is Outcome.GO  # still recorded


def test_run_experiment_failing_null_control_blocks_verdict(tmp_path: Path):
    spec = make_spec()
    per_date = synth_per_date(0.05)
    # a broken null: still carries the signal -> gate fires on the "null"
    plugin = make_plugin(
        spec, per_date, null_control=lambda sub: per_date["clean_ic"]
    )
    result = run_experiment(plugin, repo_root=tmp_path)
    assert result.outcome == "NON-VOTING"
    assert not result.controls.null.passed


def test_declared_non_voting_reasons_survive_passing_controls(tmp_path: Path):
    spec = make_spec()
    plugin = make_plugin(
        spec,
        synth_per_date(0.05),
        non_voting_reasons=("survivorship substrate (declared)",),
    )
    result = run_experiment(plugin, repo_root=tmp_path)
    assert result.controls.all_passed
    assert result.outcome == "NON-VOTING"
    assert result.decision.mechanical_outcome is Outcome.GO


def test_negative_branch_waiver_requires_reason():
    spec = make_spec()
    per_date = synth_per_date(0.05)
    with pytest.raises(ValueError, match="waiver"):
        make_plugin(spec, per_date, require_negative_branch=False)
    plugin = make_plugin(
        spec,
        per_date,
        require_negative_branch=False,
        negative_branch_waiver="under-powered to KILL at the bar (documented)",
    )
    result = run_experiment(plugin, repo_root=Path("."), freeze_check=False)
    assert result.controls.null.detail["negative_branch_waiver"].startswith("under-powered")


# ---------------------------------------------------------------------------
# dry run
# ---------------------------------------------------------------------------
def test_dry_run_loads_nothing_and_writes_nothing(tmp_path: Path):
    spec = make_spec()

    def _explode():
        raise AssertionError("substrate must not be loaded on --dry-run")

    plugin = make_plugin(spec, synth_per_date(0.05), load_substrate=_explode)
    result = run_experiment(plugin, out_dir=tmp_path / "out", dry_run=True)
    assert result.dry_run
    assert result.outcome is None and result.decision is None
    assert result.dry_run_plan["experiment_id"] == "toy_experiment"
    assert result.dry_run_plan["gate_criterion"]["threshold"] == 0.015
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# freeze-first integration
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def test_run_experiment_enforces_freeze_first(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    results = tmp_path / "results.json"
    results.write_text("{}")
    _git(tmp_path, "add", "results.json")
    _git(tmp_path, "commit", "-q", "-m", "results FIRST (violation)")
    spec_file = tmp_path / "spec.json"
    spec_file.write_text("{}")
    _git(tmp_path, "add", "spec.json")
    _git(tmp_path, "commit", "-q", "-m", "spec second")

    spec = make_spec()
    plugin = make_plugin(
        spec,
        synth_per_date(0.05),
        spec_path=spec_file,
        results_paths=(results,),
    )
    with pytest.raises(SpecNotFrozenError):
        run_experiment(plugin, repo_root=tmp_path)
    # dry run reports the violation without raising
    result = run_experiment(plugin, repo_root=tmp_path, dry_run=True)
    assert result.freeze_check is not None and not result.freeze_check.ok
    # freeze check demands a repo_root
    with pytest.raises(ValueError, match="repo_root"):
        run_experiment(plugin)


def test_verdicts_md_row_uses_spec_reopening_conditions(tmp_path: Path):
    spec = make_spec(reopening_conditions=("substrate X lands", "gate Y repaired"))
    plugin = make_plugin(spec, synth_per_date(0.05))
    result = run_experiment(plugin, repo_root=tmp_path)
    row = result.verdicts_md_row(date="2026-07-03", rationale="toy")
    assert "substrate X lands; gate Y repaired" in row
    assert "**GO**" in row
    assert "synthetic 700 dates" in row  # boundary travels with the verdict
