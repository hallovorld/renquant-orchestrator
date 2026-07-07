"""Tests for scripts/run_concentration_cap_sweep.py (Codex review on PR #405
— the implementation diverged from the approved #403 experiment contract:
wrong grid dimensionality, unfrozen seeds, thin output contract, and a
repeat of the hardcoded-umbrella-path bug just fixed in #404). These tests
prove the CONTRACT/STRUCTURE matches #403 exactly: the 75-variant 3D grid,
the frozen {42,43,44} seed set with no ad-hoc override in gating mode, and
the unanimity verdict rule — using synthetic per-seed results rather than a
real multi-hour backtest sweep."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_concentration_cap_sweep as sweep  # noqa: E402


class TestGridDimensionality:
    def test_grid_has_exactly_75_variants(self, tmp_path):
        base_config = tmp_path / "base.json"
        base_config.write_text('{"ranking": {"kelly_sizing": {}}}')
        variants = sweep.build_grid_variants(
            base_config_path=base_config, output_dir=tmp_path, seeds=sweep.FROZEN_SEEDS,
        )
        assert len(variants) == 75

    def test_grid_matches_403_frozen_values(self):
        assert sweep.ENTRY_CAPS == (0.08, 0.10, 0.12, 0.15, 0.20)
        assert sweep.DRIFT_BUFFERS[:-1] == (0.0, 0.08, 0.13, 0.18)
        assert math.isinf(sweep.DRIFT_BUFFERS[-1])
        assert sweep.TOPUP_THRESHOLDS == (0.02, 0.03, 0.05)
        assert sweep.REQUIRED_REGIMES == ("BULL_CALM", "BEAR", "BULL_VOLATILE")

    def test_incumbent_variant_identified_in_grid(self, tmp_path):
        base_config = tmp_path / "base.json"
        base_config.write_text('{"ranking": {"kelly_sizing": {}}}')
        variants = sweep.build_grid_variants(
            base_config_path=base_config, output_dir=tmp_path, seeds=sweep.FROZEN_SEEDS,
        )
        incumbents = [v for v in variants if v.role == "incumbent"]
        assert len(incumbents) == 1
        inc = incumbents[0]
        assert inc.entry_cap == sweep.INCUMBENT_ENTRY_CAP
        assert math.isinf(inc.drift_buffer)
        assert inc.topup_threshold == sweep.INCUMBENT_TOPUP_THRESHOLD


class TestDriftBufferToTrimConfig:
    def test_inf_drift_buffer_disables_trim(self, tmp_path):
        out = tmp_path / "cfg.json"
        sweep.build_variant_config(
            {}, entry_cap=0.12, drift_buffer=float("inf"), topup_threshold=0.05,
            output_path=out,
        )
        import json
        cfg = json.loads(out.read_text())
        kelly = cfg["ranking"]["kelly_sizing"]
        assert kelly["trim_enabled"] is False
        assert "trim_threshold" not in kelly

    def test_finite_drift_buffer_enables_trim_with_that_threshold(self, tmp_path):
        out = tmp_path / "cfg.json"
        sweep.build_variant_config(
            {}, entry_cap=0.12, drift_buffer=0.13, topup_threshold=0.05,
            output_path=out,
        )
        import json
        cfg = json.loads(out.read_text())
        kelly = cfg["ranking"]["kelly_sizing"]
        assert kelly["trim_enabled"] is True
        assert kelly["trim_threshold"] == 0.13


class TestFrozenSeedEnforcement:
    def test_default_run_uses_frozen_seeds(self, tmp_path, monkeypatch):
        """Omitting --dev-seeds must use exactly {42, 43, 44} — the frozen
        set from #403 — not the old hardcoded (0, 1, 2)."""
        base_config = tmp_path / "base.json"
        base_config.write_text('{"ranking": {"kelly_sizing": {}}}')
        monkeypatch.setattr(sweep, "default_repo_root", lambda: tmp_path)
        rc = sweep.main([
            "--base-config", str(base_config), "--output-dir", str(tmp_path / "out"),
        ])
        assert rc == 0
        import json
        plan = json.loads((tmp_path / "out" / "sweep_plan.json").read_text())
        assert plan["seeds"] == [42, 43, 44]
        assert plan["seeds_frozen"] is True

    def test_dev_seeds_without_confirmation_flag_is_rejected(self, tmp_path, monkeypatch):
        base_config = tmp_path / "base.json"
        base_config.write_text('{"ranking": {"kelly_sizing": {}}}')
        monkeypatch.setattr(sweep, "default_repo_root", lambda: tmp_path)
        rc = sweep.main([
            "--base-config", str(base_config), "--output-dir", str(tmp_path / "out"),
            "--dev-seeds", "0,1,2",
        ])
        assert rc == 1

    def test_dev_seeds_with_confirmation_flag_is_allowed_but_flagged_unfrozen(
        self, tmp_path, monkeypatch,
    ):
        base_config = tmp_path / "base.json"
        base_config.write_text('{"ranking": {"kelly_sizing": {}}}')
        monkeypatch.setattr(sweep, "default_repo_root", lambda: tmp_path)
        rc = sweep.main([
            "--base-config", str(base_config), "--output-dir", str(tmp_path / "out"),
            "--dev-seeds", "0,1,2", "--i-know-this-breaks-the-frozen-contract",
        ])
        assert rc == 0
        import json
        plan = json.loads((tmp_path / "out" / "sweep_plan.json").read_text())
        assert plan["seeds"] == [0, 1, 2]
        assert plan["seeds_frozen"] is False


class TestPathAuthority:
    def test_repo_root_resolved_via_default_repo_root_not_hardcoded(self):
        """The prior implementation hard-coded UMBRELLA_REPO/STRATEGY_DIR —
        the same class of bug fixed in #374/#391/#396/#404. Confirm the
        module imports and uses the canonical resolver instead."""
        assert hasattr(sweep, "default_repo_root")
        import inspect
        source = inspect.getsource(sweep)
        assert "UMBRELLA_REPO" not in source
        assert "Path.home()" not in source


class TestTurnoverFillsCost:
    def test_turnover_and_fill_count_computed_from_trade_log(self):
        trade_log = [
            {"action": "buy", "ticker": "AAPL", "target_pct": 0.10},
            {"action": "sell", "ticker": "AAPL", "pnl_pct": 0.05},
            {"action": "buy", "ticker": "MSFT", "target_pct": 0.08},
        ]
        out = sweep.compute_turnover_fills_cost(trade_log, n_days=252)
        assert out["fill_count"] == 3
        # Only buy events carry target_pct in the real trade_events schema
        # (sells carry pnl_pct, not a weight) — 0.10 + 0.08 = 0.18.
        assert out["turnover_annualized"] == pytest.approx(0.18, abs=1e-6)

    def test_cost_delta_vs_incumbent_computed_when_incumbent_turnover_given(self):
        trade_log = [{"action": "buy", "ticker": "AAPL", "target_pct": 0.20}]
        out = sweep.compute_turnover_fills_cost(
            trade_log, n_days=252, incumbent_turnover_annualized=0.10,
        )
        assert out["cost_delta_bps_vs_incumbent"] is not None


class TestWinnerContinuation:
    def test_sell_that_drifted_above_entry_cap_is_flagged(self):
        trade_log = [
            {"action": "buy", "ticker": "AAPL", "target_pct": 0.10},
            {"action": "sell", "ticker": "AAPL", "pnl_pct": 0.50},  # implied exit = 0.15 > 0.12
        ]
        out = sweep.compute_winner_continuation(trade_log, entry_cap=0.12)
        assert out["n_drifted_above_cap"] == 1
        assert out["net_positive"] is True

    def test_sell_that_never_exceeded_cap_is_not_flagged(self):
        trade_log = [
            {"action": "buy", "ticker": "MSFT", "target_pct": 0.05},
            {"action": "sell", "ticker": "MSFT", "pnl_pct": 0.02},  # implied exit = 0.051 < 0.12
        ]
        out = sweep.compute_winner_continuation(trade_log, entry_cap=0.12)
        assert out["n_drifted_above_cap"] == 0


class TestUnanimityVerdict:
    def _seed_row(self, seed, *, sharpe, bull_calm_sharpe, bull_calm_dd, full_dd=0.10,
                  turnover=0.10, net_positive=True):
        return {
            "seed": seed, "sharpe": sharpe, "max_dd": full_dd,
            "per_regime": {
                "BULL_CALM": {"sharpe": bull_calm_sharpe, "max_dd": bull_calm_dd},
                "BEAR": {"sharpe": sharpe, "max_dd": full_dd},
                "BULL_VOLATILE": {"sharpe": sharpe, "max_dd": full_dd},
            },
            "turnover": {"turnover_annualized": turnover},
            "winner_continuation": {"net_positive": net_positive},
        }

    def test_all_seeds_passing_yields_tier3_ready(self):
        cand = {"variant": "cap15_driftinf_topup05", "per_seed": [
            self._seed_row(s, sharpe=1.2, bull_calm_sharpe=1.3, bull_calm_dd=0.09)
            for s in (42, 43, 44)
        ]}
        inc = {"variant": "incumbent", "per_seed": [
            self._seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0, bull_calm_dd=0.10)
            for s in (42, 43, 44)
        ]}
        verdict = sweep.unanimity_verdict(cand, inc, placebo_passed=True)
        assert verdict["tier3_ready"] is True

    def test_one_seed_failing_blocks_the_whole_verdict(self):
        """Unanimity, not majority: 2-of-3 passing must NOT clear the gate."""
        cand = {"variant": "cap20_driftinf_topup05", "per_seed": [
            self._seed_row(42, sharpe=1.2, bull_calm_sharpe=1.3, bull_calm_dd=0.09),
            self._seed_row(43, sharpe=1.2, bull_calm_sharpe=1.3, bull_calm_dd=0.09),
            self._seed_row(44, sharpe=0.5, bull_calm_sharpe=0.4, bull_calm_dd=0.20),  # fails
        ]}
        inc = {"variant": "incumbent", "per_seed": [
            self._seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0, bull_calm_dd=0.10)
            for s in (42, 43, 44)
        ]}
        verdict = sweep.unanimity_verdict(cand, inc, placebo_passed=True)
        assert verdict["tier3_ready"] is False

    def test_missing_placebo_blocks_verdict_as_null_not_pass(self):
        cand = {"variant": "cap15_driftinf_topup05", "per_seed": [
            self._seed_row(s, sharpe=1.2, bull_calm_sharpe=1.3, bull_calm_dd=0.09)
            for s in (42, 43, 44)
        ]}
        inc = {"variant": "incumbent", "per_seed": [
            self._seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0, bull_calm_dd=0.10)
            for s in (42, 43, 44)
        ]}
        verdict = sweep.unanimity_verdict(cand, inc, placebo_passed=None)
        assert verdict["unanimous_criteria"]["6_placebo_no_lift"] is None
        assert verdict["tier3_ready"] is False

    def test_new_tail_in_non_incumbent_worst_regime_fails_criterion_4(self):
        """#403 round-3 fix: a candidate that keeps BEAR flat but damages
        BULL_VOLATILE must fail criterion 4 even if BULL_CALM improves."""
        def row(seed):
            return {
                "seed": seed, "sharpe": 1.1, "max_dd": 0.10,
                "per_regime": {
                    "BULL_CALM": {"sharpe": 1.5, "max_dd": 0.08},  # much better
                    "BEAR": {"sharpe": 1.0, "max_dd": 0.10},  # flat
                    "BULL_VOLATILE": {"sharpe": 0.2, "max_dd": 0.30},  # damaged
                },
                "turnover": {"turnover_annualized": 0.10},
                "winner_continuation": {"net_positive": True},
            }
        cand = {"variant": "candidate", "per_seed": [row(s) for s in (42, 43, 44)]}
        inc = {"variant": "incumbent", "per_seed": [
            self._seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0, bull_calm_dd=0.10)
            for s in (42, 43, 44)
        ]}
        verdict = sweep.unanimity_verdict(cand, inc, placebo_passed=True)
        assert verdict["unanimous_criteria"]["4_per_regime_no_material_regression_all_regimes"] is False
        assert verdict["tier3_ready"] is False
