"""Tests for scripts/m4b_floor_replay.py (M4-b floor-replay harness).

All fixtures are synthetic — no production DB, no live calibrator artifact.
Covers: the pure-python calibrator head, recentering + pairing detection,
the four floor rules, the matched-breadth solver, the exact small-n block
bootstrap (against an independent brute force) + degeneracy guard, the five
frozen criteria wiring, the S-REL controls (positive plant detection proof +
true-null false-fire), the run gate, and the baseline-report / replay modes
on a synthetic sqlite DB.
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "m4b_floor_replay.py"
_spec = importlib.util.spec_from_file_location("m4b_floor_replay", _SCRIPT)
m4b = importlib.util.module_from_spec(_spec)
sys.modules["m4b_floor_replay"] = m4b  # dataclass needs the module registered
_spec.loader.exec_module(m4b)


# ------------------------------------------------------------------ helpers
def toy_calibrator(y_scale: float = 0.1, lookahead: int = 60) -> "m4b.Calibrator":
    """Linear ER head er(raw) = y_scale * raw on [-1, 1]; neutral_raw = 0."""
    doc = {
        "trained_date": "2026-07-03",
        "expected_return": {"x": [-1.0, 1.0], "y": [-y_scale, y_scale]},
        "metadata": {"lookahead_days": lookahead, "er_clip_bound": 0.2},
    }
    return m4b.Calibrator(doc, path="<toy>", sha256="toy")


def make_bar(date: str, raws, cal, *, mu_offset: float = 0.0,
             eligible=None, regime: str = "BULL_CALM", era: str = "panel",
             horizon: int = 60) -> "m4b.Bar":
    raws = np.asarray(raws, dtype=float)
    mu_stored = cal.mu_at_horizon(raws, horizon) + mu_offset
    if eligible is None:
        eligible = np.ones(len(raws), dtype=bool)
    return m4b.Bar(
        run_id=f"run-{date}", date=date, regime=regime, era=era,
        tickers=[f"T{i:03d}" for i in range(len(raws))],
        raw=raws, mu_stored=np.asarray(mu_stored, dtype=float),
        eligible=np.asarray(eligible, dtype=bool),
        mu_horizon_days=horizon,
    )


def replayed_bars(bar_specs, cal):
    bars = [make_bar(*spec[:2], cal, **spec[2]) if len(spec) > 2
            else make_bar(*spec, cal) for spec in bar_specs]
    m4b.replay_bars(bars, cal, [])
    return bars


def fixture_bars(n_bars=10, n_names=30, seed=7, cal=None, drift_scale=0.15):
    """Bars whose raw centers drift bar to bar (so an absolute floor's
    breadth varies while relative floors stay stable — the M4-b setting)."""
    cal = cal or toy_calibrator()
    rng = np.random.default_rng(seed)
    bars = []
    for i in range(n_bars):
        drift = drift_scale * math.sin(i)  # deterministic per-bar center
        raws = rng.normal(drift, 0.45, size=n_names)
        bars.append(make_bar(f"2026-06-{i + 1:02d}", raws, cal))
    m4b.replay_bars(bars, cal, [])
    return bars


def attach_synthetic_outcomes(bars, horizon="fwd_20d", seed=11, sigma=0.05,
                              shift_fn=None):
    rng = np.random.default_rng(seed)
    for b in bars:
        ex = rng.normal(0.0, sigma, size=len(b.tickers))
        if shift_fn is not None:
            ex = ex + shift_fn(b)
        b.excess[horizon] = ex


# --------------------------------------------------------------- calibrator
class TestCalibrator:
    def test_neutral_raw_zero_crossing(self):
        cal = toy_calibrator()
        assert cal.neutral_raw == pytest.approx(0.0)

    def test_neutral_raw_interpolated(self):
        doc = {"expected_return": {"x": [0.0, 1.0], "y": [-0.02, 0.06]},
               "metadata": {}}
        cal = m4b.Calibrator(doc)
        assert cal.neutral_raw == pytest.approx(0.25)

    def test_neutral_raw_none_when_no_crossing(self):
        doc = {"expected_return": {"x": [0.0, 1.0], "y": [0.01, 0.06]},
               "metadata": {}}
        assert m4b.Calibrator(doc).neutral_raw is None

    def test_er_interp_and_clamp(self):
        cal = toy_calibrator()
        assert cal.er_native(np.array([0.5]))[0] == pytest.approx(0.05)
        # clamped beyond knot range
        assert cal.er_native(np.array([5.0]))[0] == pytest.approx(0.1)
        assert cal.er_native(np.array([-5.0]))[0] == pytest.approx(-0.1)

    def test_load_time_clip(self):
        doc = {"expected_return": {"x": [-1.0, 1.0], "y": [-0.5, 0.5]},
               "metadata": {"er_clip_bound": 0.2}}
        cal = m4b.Calibrator(doc)
        assert float(cal.er_y.max()) == pytest.approx(0.2)
        assert float(cal.er_y.min()) == pytest.approx(-0.2)

    def test_horizon_scaling_and_reclip(self):
        cal = toy_calibrator()  # native 60d
        raws = np.array([0.5])
        assert cal.mu_at_horizon(raws, 60)[0] == pytest.approx(0.05)
        assert cal.mu_at_horizon(raws, 120)[0] == pytest.approx(0.10)
        # scaling re-clips at the bound
        assert cal.mu_at_horizon(np.array([1.0]), 300)[0] == pytest.approx(0.2)


# ------------------------------------------------- recentering and pairing
class TestReplayBars:
    def test_recentering_removes_center(self):
        cal = toy_calibrator()
        bars = replayed_bars([("2026-07-06", [0.1, 0.3, 0.5, 0.7, 0.9])], cal)
        b = bars[0]
        assert b.center == pytest.approx(0.5)
        # mu_rec = er(raw - center + neutral) = 0.1 * (raw - 0.5)
        np.testing.assert_allclose(
            b.mu_rec, 0.1 * (b.raw - 0.5), atol=1e-12)
        assert float(np.median(b.mu_rec)) == pytest.approx(0.0, abs=1e-12)

    def test_pairing_detection(self):
        cal = toy_calibrator()
        raws = list(np.linspace(-0.6, 0.6, 41))
        paired = replayed_bars([("2026-07-06", raws)], cal)[0]
        assert paired.is_current_pairing and paired.fidelity <= 1e-12
        # +2% intercept (the retired-pairing artifact) => NOT current pairing
        off = replayed_bars(
            [("2026-06-30", raws, {"mu_offset": 0.02})], cal)[0]
        assert not off.is_current_pairing
        assert off.fidelity == pytest.approx(0.02, abs=1e-9)

    def test_mad_matches_hand_computation(self):
        cal = toy_calibrator()
        b = replayed_bars([("2026-07-06", [0.0, 0.2, 0.4, 0.6, 1.0])], cal)[0]
        mu = b.mu_rec
        assert b.mad == pytest.approx(
            float(np.median(np.abs(mu - np.median(mu)))))


# -------------------------------------------------------------- floor rules
class TestFloorRules:
    def _bar(self):
        cal = toy_calibrator()
        # raw: center (median) = 0.3 -> mu_rec = 0.1*(raw-0.3)
        return replayed_bars(
            [("2026-07-06", [-0.5, -0.1, 0.1, 0.3, 0.5, 0.7, 0.9])], cal)[0]

    def test_baseline_uses_stored_mu(self):
        b = self._bar()  # mu_stored = 0.1*raw -> >=0.03 iff raw >= 0.3
        got = m4b.floor_clearing(b, "baseline", None)
        np.testing.assert_array_equal(got, b.mu_stored >= 0.03)
        assert int(got.sum()) == 4

    def test_quantile_rule_with_mu_pos_side_condition(self):
        b = self._bar()  # mu_rec ranks = raw ranks; 3 names have mu_rec > 0
        got = m4b.floor_clearing(b, "quantile", 5.5 / 7.0)
        # top-5.5/7 quantile admits >= 6 ranks, but mu_rec > 0 caps at 3
        assert int(got.sum()) == 3
        assert set(np.flatnonzero(got)) == {4, 5, 6}

    def test_dispersion_rule(self):
        b = self._bar()
        # admit iff mu_rec >= k * MAD and mu_rec > 0
        k = float(b.mu_rec[5] / b.mad)  # threshold exactly at name 5
        got = m4b.floor_clearing(b, "dispersion", k)
        assert set(np.flatnonzero(got)) == {5, 6}

    def test_absolute_rule_no_mu_pos_condition(self):
        b = self._bar()
        got = m4b.floor_clearing(b, "absolute", -0.01)
        # admits mu_rec >= -0.01 (raw >= 0.2): names 3..6 — negative floor OK
        assert set(np.flatnonzero(got)) == {3, 4, 5, 6}

    def test_eligibility_masks_admission_not_the_quantile(self):
        cal = toy_calibrator()
        raws = [-0.5, -0.1, 0.1, 0.3, 0.5, 0.7, 0.9]
        elig = np.array([True] * 6 + [False])  # top name upstream-vetoed
        b = replayed_bars(
            [("2026-07-06", raws, {"eligible": elig})], cal)[0]
        got = m4b.floor_clearing(b, "quantile", 2.0 / 7.0)
        # per-bar quantile still computed on the FULL cross-section (#147):
        # top-2 threshold sits at name 5; name 6 excluded by eligibility only
        assert set(np.flatnonzero(got)) == {5}

    def test_bl4_masks(self):
        b = self._bar()
        np.testing.assert_array_equal(
            m4b.bl4_mask(b, "quantile", "prod-raw"), b.raw > 0.0)
        np.testing.assert_array_equal(
            m4b.bl4_mask(b, "baseline", "arm"), b.raw > 0.0)
        np.testing.assert_array_equal(
            m4b.bl4_mask(b, "quantile", "arm"), b.raw > b.center)
        assert m4b.bl4_mask(b, "quantile", "off").all()


# ---------------------------------------------------- matched-breadth solve
class TestMatchedBreadth:
    def test_solver_matches_baseline_breadth_all_arms(self):
        bars = fixture_bars(n_bars=10, n_names=40)
        B = m4b.mean_count(bars, "baseline", None)
        assert B > 1.0  # fixture sanity: baseline admits something
        for arm, lo, hi, inc in (("quantile", 1e-6, 1.0, True),
                                 ("dispersion", 0.0, 50.0, False),
                                 ("absolute", -0.05, 0.2, False)):
            s = m4b.solve_matched_param(bars, arm, B, lo=lo, hi=hi,
                                        increasing=inc)
            assert s["matched"], f"{arm}: {s}"
            assert abs(s["achieved_mean"] - B) <= m4b.BREADTH_TOL

    def test_solver_flags_unachievable_target(self):
        bars = fixture_bars(n_bars=6, n_names=20)
        # mu>0 side-condition caps quantile breadth well below 19.5
        s = m4b.solve_matched_param(bars, "quantile", 19.5,
                                    lo=1e-6, hi=1.0, increasing=True)
        assert not s["matched"]
        assert s["achieved_mean"] < 19.5

    def test_param_is_global_not_per_bar(self):
        bars = fixture_bars(n_bars=8, n_names=30)
        B = m4b.mean_count(bars, "baseline", None)
        s = m4b.solve_matched_param(bars, "quantile", B, lo=1e-6, hi=1.0,
                                    increasing=True)
        counts = [int(m4b.floor_clearing(b, "quantile", s["param"]).sum())
                  for b in bars]
        # single K, per-bar counts may differ; only the mean is matched
        assert abs(float(np.mean(counts)) - s["achieved_mean"]) < 1e-9


# --------------------------------------------------------------- statistics
class TestExactBlockBootstrap:
    @staticmethod
    def _brute_force(A, block_len):
        """Independent reimplementation: all block-start tuples, trimmed
        circular blocks, delta of pooled means."""
        n = len(A)
        n_blocks = math.ceil(n / block_len)
        lens = [block_len] * n_blocks
        lens[-1] = n - block_len * (n_blocks - 1)
        out = []
        for starts in itertools.product(range(n), repeat=n_blocks):
            rows = []
            for bi, s in enumerate(starts):
                rows += [A[(s + o) % n] for o in range(lens[bi])]
            rows = np.asarray(rows)
            sA, nA, sK, nK = rows.sum(axis=0)
            if nA and nK:
                out.append(sK / nK - sA / nA)
        return np.sort(np.asarray(out))

    def test_matches_independent_brute_force(self):
        rng = np.random.default_rng(3)
        n = 5
        A = np.column_stack([
            rng.normal(0, 1, n), rng.integers(2, 9, n).astype(float),
            rng.normal(0, 1, n), rng.integers(2, 9, n).astype(float)])
        dates = [f"d{i}" for i in range(n)]
        res = m4b.exact_block_bootstrap(dates, A, 2)
        assert res["exact"] and res["n_tuples"] == 5 ** 3
        brute = self._brute_force(A, 2)
        got = np.sort(np.array(
            [res["delta_min"], res["delta_max"]]))
        assert got[0] == pytest.approx(brute[0])
        assert got[1] == pytest.approx(brute[-1])
        assert res["n_atoms"] == len(brute)
        # tail masses agree with the brute-force distribution
        assert res["p_le_0"] == pytest.approx(float(np.mean(brute <= 0)))
        assert res["p_ge_0"] == pytest.approx(float(np.mean(brute >= 0)))

    def test_degenerate_when_block_covers_sample(self):
        A = np.array([[0.0, 3.0, 0.3, 3.0]] * 4)
        res = m4b.exact_block_bootstrap([f"d{i}" for i in range(4)], A, 5)
        assert res["exact"] and res["degenerate"]
        assert res["delta_min"] == pytest.approx(res["delta_max"])

    def test_infeasible_enumeration_returns_exact_false(self):
        n = 20
        A = np.ones((n, 4))
        res = m4b.exact_block_bootstrap([f"d{i}" for i in range(n)], A, 1)
        assert not res.get("exact")
        assert res["n_tuples"] == 20 ** 20


class TestSmallNDispatch:
    def _A(self, n, seed=5):
        rng = np.random.default_rng(seed)
        return ([f"d{i}" for i in range(n)],
                np.column_stack([rng.normal(0, 1, n),
                                 rng.integers(2, 9, n).astype(float),
                                 rng.normal(0, 1, n),
                                 rng.integers(2, 9, n).astype(float)]))

    def test_small_n_uses_exact_branch(self):
        dates, A = self._A(8)
        res = m4b.delta_significance(dates, A, m4b.BLOCK_PRIMARY)
        assert res["branch"] == "exact_small_n"

    def test_small_n_mc_fallback_records_deviation_on_primary_only(self):
        dates, A = self._A(12)  # 12^12 tuples for block-1: infeasible
        dev: list[str] = []
        res = m4b.delta_significance(dates, A, 1, dev, primary=True)
        assert res["branch"] == "mc_fallback_small_n"
        assert len(dev) == 1 and "recorded deviation" in dev[0]
        dev2: list[str] = []
        m4b.delta_significance(dates, A, 1, dev2, primary=False)
        assert dev2 == []

    def test_large_n_uses_mc_with_exact_alongside(self):
        dates, A = self._A(16)  # >= SMALL_N_DATES; 16^4 = 65536 enumerable
        res = m4b.delta_significance(dates, A, m4b.BLOCK_PRIMARY)
        assert res["branch"] == "mc"
        assert res["exact_alongside"]["exact"]

    def test_mc_is_seeded_and_reproducible(self):
        dates, A = self._A(16)
        r1 = m4b.mc_block_bootstrap(dates, A, 5)
        r2 = m4b.mc_block_bootstrap(dates, A, 5)
        assert r1["ci95"] == r2["ci95"]


class TestCriterion1:
    def test_exact_branch(self):
        assert m4b.criterion1_pass(
            {"exact": True, "p_le_0": 0.02}, 0.01)
        assert not m4b.criterion1_pass(
            {"exact": True, "p_le_0": 0.03}, 0.01)
        assert not m4b.criterion1_pass(
            {"exact": True, "p_le_0": 0.0}, -0.01)

    def test_degenerate_never_fires(self):
        assert not m4b.criterion1_pass(
            {"exact": True, "p_le_0": 0.0, "degenerate": True}, 0.05)
        assert not m4b.criterion1_pass(
            {"ci95": [0.01, 0.02], "degenerate": True}, 0.05)

    def test_mc_branch(self):
        assert m4b.criterion1_pass({"ci95": [0.001, 0.02]}, 0.01)
        assert not m4b.criterion1_pass({"ci95": [-0.001, 0.02]}, 0.01)
        assert not m4b.criterion1_pass({"ci95": None}, 0.01)


# ------------------------------------------------------- criteria 2..5 wiring
class TestEvaluateCandidate:
    def _bars_with_plant(self, favor: str):
        """12 drifting bars; candidate-only names planted as winners
        (favor='candidate') or losers (favor='baseline')."""
        bars = fixture_bars(n_bars=12, n_names=30, seed=9)
        B = m4b.mean_count(bars, "baseline", None)
        s = m4b.solve_matched_param(bars, "quantile", B, lo=1e-6, hi=1.0,
                                    increasing=True)
        param = s["param"]
        sign = 1.0 if favor == "candidate" else -1.0

        def shift(b):
            base = m4b.floor_clearing(b, "baseline", None)
            cand = m4b.floor_clearing(b, "quantile", param)
            return sign * (0.08 * (cand & ~base) - 0.08 * (base & ~cand))

        attach_synthetic_outcomes(bars, shift_fn=shift, sigma=0.02)
        return bars, param

    def test_candidate_wins_when_planted_better(self):
        bars, param = self._bars_with_plant("candidate")
        ev = m4b.evaluate_candidate(bars, "quantile", param, "fwd_20d", "off")
        cr = ev["criteria"]
        assert ev["expectancy_delta"] > 0
        assert cr["1_delta_ci_excludes_0"]
        assert cr["3_winners_removed_le_losers_removed"]
        assert cr["4_zero_admission_le_baseline"]
        assert ev["block5"]["branch"] == "exact_small_n"

    def test_candidate_loses_when_planted_worse(self):
        bars, param = self._bars_with_plant("baseline")
        ev = m4b.evaluate_candidate(bars, "quantile", param, "fwd_20d", "off")
        cr = ev["criteria"]
        assert ev["expectancy_delta"] < 0
        assert not cr["1_delta_ci_excludes_0"]
        assert not cr["3_winners_removed_le_losers_removed"]
        assert not ev["stage1_all_criteria_pass"]

    def test_criterion2_cut_requires_min_dates(self):
        bars, param = self._bars_with_plant("candidate")
        for b in bars[:2]:
            b.regime = "BEAR"  # 2-date cut: reported but not counted
        ev = m4b.evaluate_candidate(bars, "quantile", param, "fwd_20d", "off")
        bear = ev["cuts"]["regime:BEAR"]
        assert bear["n_resolved_dates"] == 2 and not bear["counted"]

    def test_criterion5_admission_match_and_divergence(self):
        bars, param = self._bars_with_plant("candidate")
        ev = m4b.evaluate_candidate(bars, "quantile", param, "fwd_20d", "off")
        det = ev["criteria"]["5_detail"]
        assert set(det) == {"topn_saturation", "p90", "p95", "qp_spill",
                            "zero_streak"}
        # identical arm must trivially match the distribution criteria
        ev_self = m4b.evaluate_candidate(
            bars, "baseline", None, "fwd_20d", "off")
        assert ev_self["criteria"]["5_admission_distribution_match"]

    def test_dispersion_monotone_sanity_wired(self):
        bars = fixture_bars(n_bars=12, n_names=30, seed=9)
        attach_synthetic_outcomes(bars)
        B = m4b.mean_count(bars, "baseline", None)
        s = m4b.solve_matched_param(bars, "dispersion", B, lo=0.0, hi=50.0,
                                    increasing=False)
        ev = m4b.evaluate_candidate(
            bars, "dispersion", s["param"], "fwd_20d", "off")
        assert ev["monotone_in_dispersion_rho"] is not None


# ------------------------------------------------------ admission metrics
class TestAdmissionMetrics:
    def test_max_zero_streak(self):
        assert m4b.max_zero_streak([]) == 0
        assert m4b.max_zero_streak([1, 2, 3]) == 0
        assert m4b.max_zero_streak([0, 0, 1, 0, 0, 0, 2]) == 3

    def test_metrics_hand_check(self):
        bars = fixture_bars(n_bars=6, n_names=20, seed=13)
        met = m4b.admission_metrics(bars, "baseline", None)
        counts = [int(m4b.floor_clearing(b, "baseline", None).sum())
                  for b in bars]
        assert list(met["counts_by_date"].values()) == counts
        arr = np.asarray(counts, dtype=float)
        assert met["mean"] == pytest.approx(float(arr.mean()))
        assert met["topn_saturation_freq"] == pytest.approx(
            float(np.mean(arr >= m4b.TOP_N)))
        assert met["qp_spill_freq"] == pytest.approx(
            float(np.mean(arr > m4b.TOP_N)))

    def test_spearman(self):
        assert m4b.spearman([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
        assert m4b.spearman([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
        assert m4b.spearman([1, 1, 1], [1, 2, 3]) is None
        assert m4b.spearman([1, 2], [1, 2]) is None


# ----------------------------------------------------------------- controls
class TestControls:
    def test_positive_plant_detected_and_null_calibrated(self):
        bars = fixture_bars(n_bars=10, n_names=30, seed=21)
        attach_synthetic_outcomes(bars, sigma=0.05, seed=22)
        B = m4b.mean_count(bars, "baseline", None)
        s = m4b.solve_matched_param(bars, "quantile", B, lo=1e-6, hi=1.0,
                                    increasing=True)
        ctl = m4b.run_controls(bars, {"quantile": s["param"]}, "fwd_20d",
                               "off", n_reps=60, gaps=(0.08,), seed=5)
        arm = ctl["arms"]["quantile"]
        power = arm["positive_control_power"]["gap_0.08"]
        null_iid = arm["true_null_false_fire_rate_iid"]
        null_perm = arm["true_null_false_fire_rate_perm"]
        # detection proof: the planted effect is found far above the null
        assert power >= 0.5
        assert power >= null_iid + 0.3
        # true-null false-fire stays near nominal on the exact branch
        assert null_iid <= 0.15
        assert null_perm is not None and null_perm <= 0.15
        # the small-n exact-tail branch is what the controls exercised
        assert any(b.startswith("exact_small_n")
                   for b in ctl["sig_branch_used"])

    def test_perm_null_none_without_real_outcomes(self):
        bars = fixture_bars(n_bars=8, n_names=20, seed=3)  # no outcomes
        B = m4b.mean_count(bars, "baseline", None)
        s = m4b.solve_matched_param(bars, "quantile", B, lo=1e-6, hi=1.0,
                                    increasing=True)
        ctl = m4b.run_controls(bars, {"quantile": s["param"]}, "fwd_20d",
                               "off", n_reps=10, gaps=(0.08,), seed=5)
        assert ctl["arms"]["quantile"]["true_null_false_fire_rate_perm"] is None


# ----------------------------------------------------------------- run gate
class TestRunGate:
    def test_gate_counts_pairing_sessions_with_outcomes(self):
        cal = toy_calibrator()
        bars = fixture_bars(n_bars=12, n_names=20, seed=2, cal=cal)
        attach_synthetic_outcomes(bars)
        for b in bars[:3]:
            b.is_current_pairing = False  # retired-pairing bars don't count
        g = m4b.gate_status(bars, "fwd_20d")
        assert g["current_pairing_sessions_with_resolved_outcomes"] == 9
        assert not g["gate_met"]
        assert g["verdict_eligibility"] == "PRE-GATE EXPLORATORY"
        for b in bars[:3]:
            b.is_current_pairing = True
        g2 = m4b.gate_status(bars, "fwd_20d")
        assert g2["gate_met"]
        assert g2["verdict_eligibility"] == "STAGE-1 ELIGIBLE"


# ------------------------------------------------------- sqlite fixture DB
def build_fixture_db(path: Path, cal, *, n_pairing=3, n_retired=2,
                     n_names=45, seed=17) -> None:
    """Synthetic runs DB with the production schema subset the harness reads.

    Retired-pairing runs carry a +0.02 mu intercept (the pre-restore
    artifact); pairing runs store mu == current-calibrator replay exactly.
    """
    rng = np.random.default_rng(seed)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY, run_date TEXT, run_type TEXT,
            regime TEXT, created_at TEXT, counters_json TEXT);
        CREATE TABLE score_distribution (
            run_id TEXT, date TEXT, ticker TEXT, raw_panel REAL, mu REAL,
            is_holding INTEGER DEFAULT 0, blocked_by TEXT,
            active_scorer TEXT, model_type TEXT, mu_horizon_days INTEGER);
        CREATE TABLE ticker_forward_returns (
            as_of_date TEXT, ticker TEXT, fwd_1d REAL, fwd_5d REAL,
            fwd_10d REAL, fwd_20d REAL, fwd_60d REAL,
            PRIMARY KEY (as_of_date, ticker));
    """)
    day = 0
    for kind, n_runs, offset in (("retired", n_retired, 0.02),
                                 ("pairing", n_pairing, 0.0)):
        for _ in range(n_runs):
            day += 1
            date = f"2026-07-{day:02d}"
            run_id = f"{date}-live-{kind}"
            raws = rng.normal(-0.1 if kind == "pairing" else -0.05,
                              0.4, size=n_names)
            mus = cal.mu_at_horizon(raws, 60) + offset
            laundered = int(np.sum((raws < 0) & (mus > 0)))
            con.execute(
                "INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
                (run_id, date, "live", "BULL_CALM", f"{date} 21:00:00",
                 json.dumps({"calibrator_sign_laundered": laundered})))
            # a superseded thin run earlier the same date (dedup check)
            con.execute(
                "INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
                (f"{run_id}-early", date, "live", "BULL_CALM",
                 f"{date} 14:00:00", "{}"))
            for i in range(n_names):
                t = f"T{i:03d}"
                blocked = "veto:rank_score_below_floor" if i == 0 else None
                con.execute(
                    "INSERT INTO score_distribution "
                    "(run_id, date, ticker, raw_panel, mu, is_holding, "
                    "blocked_by, active_scorer, model_type, mu_horizon_days) "
                    "VALUES (?,?,?,?,?,0,?,?,?,60)",
                    (run_id, date, t, float(raws[i]), float(mus[i]),
                     blocked, "panel_ltr_xgboost", None))
                con.execute(
                    "INSERT OR IGNORE INTO ticker_forward_returns "
                    "(as_of_date, ticker, fwd_5d, fwd_10d, fwd_20d) "
                    "VALUES (?,?,?,?,?)",
                    (date, t, rng.normal(0, 0.02), rng.normal(0, 0.03),
                     rng.normal(0, 0.05)))
            con.execute(
                "INSERT OR IGNORE INTO ticker_forward_returns "
                "(as_of_date, ticker, fwd_5d, fwd_10d, fwd_20d) "
                "VALUES (?,?,0.0,0.0,0.0)", (date, "SPY"))
    con.commit()
    con.close()


class TestDBModes:
    @pytest.fixture()
    def db(self, tmp_path):
        cal = toy_calibrator()
        p = tmp_path / "runs.fixture.db"
        build_fixture_db(p, cal)
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        yield con, cal
        con.close()

    def test_canonical_runs_dedup_latest_full(self, db):
        con, _ = db
        runs = m4b.canonical_runs(con, min_candidates=5)
        assert len(runs) == 5  # one per date, the "-early" rows superseded
        assert all(not r["run_id"].endswith("-early") for r in runs)

    def test_baseline_report_pairing_and_laundering(self, db):
        con, cal = db
        rep = m4b.baseline_report(con, cal, n_runs=5, min_candidates=5)
        rows = rep["runs"]
        assert len(rows) == 5
        retired = [r for r in rows if "retired" in r["run_id"]]
        pairing = [r for r in rows if "pairing" in r["run_id"]]
        assert len(retired) == 2 and len(pairing) == 3
        assert all(not r["is_current_pairing"] for r in retired)
        assert all(r["is_current_pairing"] for r in pairing)
        for r in pairing:
            assert r["current_cal_fidelity_max_abs_diff"] <= 1e-12
        for r in rows:  # stored laundering must equal the prod BL-2 counter
            assert (r["sign_laundered_stored"]
                    == r["sign_laundered_prod_counter"])
            assert r["sign_laundered_reverse_stored"] == 0

    def test_replay_pairing_window_and_premeasure(self, db):
        con, cal = db
        res = m4b.run_replay(con, cal, "off", "fwd_20d", min_candidates=5,
                             window="pairing")
        assert res["window"] == "pairing"
        assert res["substrate"]["n_bars"] == 3  # pairing bars only
        pm = res["baseline_premeasure"]
        assert pm["mean_floor_clearing_B"] == res["matched_breadth"]["target_B"]
        assert all(r["is_current_pairing"] for r in pm["per_bar"])
        for arm in ("quantile", "dispersion", "absolute"):
            assert arm in res["evaluations"]
        assert res["ngboost_sigma_band"]["status"] == "SKIPPED"
        # 3 sessions < 10: never verdict-eligible
        assert res["verdict_eligibility"] == "PRE-GATE EXPLORATORY"
        # evidence JSON must serialize
        json.dumps(res, default=m4b._json_default)

    def test_replay_window_all_records_deviation(self, db):
        con, cal = db
        res = m4b.run_replay(con, cal, "off", "fwd_20d", min_candidates=5,
                             window="all")
        assert res["substrate"]["n_bars"] == 5
        assert any("--window all" in d for d in res["deviations"])

    def test_replay_empty_pairing_window_graceful(self, db, tmp_path):
        cal = toy_calibrator()
        p = tmp_path / "runs.retired-only.db"
        build_fixture_db(p, cal, n_pairing=0, n_retired=3)
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            res = m4b.run_replay(con, cal, "off", "fwd_20d",
                                 min_candidates=5, window="pairing")
        finally:
            con.close()
        assert "evaluations" not in res
        assert "no bars in the current-pairing window" in res["note"]
        assert res["run_gate"]["current_pairing_sessions"] == 0

    def test_read_only_enforced(self, db):
        con, _ = db
        with pytest.raises(sqlite3.OperationalError):
            con.execute("INSERT INTO pipeline_runs VALUES "
                        "('x','2026-07-09','live','B','t','{}')")


# ---------------------------------------------------------- pre-registered
class TestPreRegisteredConstants:
    def test_frozen_protocol_constants(self):
        """Design §4 anchors — a drive-by edit of any of these is a protocol
        deviation and must fail loudly here."""
        assert m4b.FLOOR == 0.03
        assert m4b.COST_PROXY == 0.0011
        assert m4b.TOP_N == 3
        assert m4b.BLOCK_PRIMARY == 5 and m4b.BLOCK_SENS == 1
        assert m4b.BREADTH_TOL == 0.5
        assert m4b.MIN_CUT_DATES == 5
        assert m4b.MIN_STAGE1_SESSIONS == 10
        assert m4b.PRIMARY_HORIZON == "fwd_20d"
        assert "fwd_60d" in m4b.HORIZONS

    def test_ngboost_skip_note_present(self):
        assert "sigma-wire" in m4b.NGBOOST_SKIP_NOTE
        assert "2026-05-17" in m4b.NGBOOST_SKIP_NOTE
