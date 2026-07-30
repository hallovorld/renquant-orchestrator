"""Behavioural tests for the scorer attribution probes.

These train a real tiny booster where the ground truth is KNOWN by
construction, then assert the probes recover it. Source-grep tests would pass
on a probe that reports the wrong feature, which is the failure mode that
matters here: the probe's whole purpose is to name which feature drives the
score, so a test that cannot detect a wrong name tests nothing.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

xgb = pytest.importorskip("xgboost")

SPEC = importlib.util.spec_from_file_location(
    "scorer_attribution_probe",
    Path(__file__).resolve().parent.parent / "scripts" / "scorer_attribution_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

N_FEATURES = 6
DRIVER = 1          # the only feature the label depends on
UNUSED = (4, 5)     # pure noise, present in the matrix but not in the label


@pytest.fixture(scope="module")
def artifact() -> dict:
    """A booster whose driver is feature 1 and whose features 4,5 are noise."""
    rng = np.random.default_rng(7)
    x = rng.normal(size=(3000, N_FEATURES))
    y = 3.0 * x[:, DRIVER]          # monotone increasing in the driver only
    # gamma prunes splits whose gain does not clear it, so the noise features
    # are genuinely never split on -- which is what makes the bloat probe's
    # `never_split_on` count testable rather than vacuous.
    booster = xgb.train({"max_depth": 3, "eta": 0.3, "gamma": 50.0, "verbosity": 0},
                        xgb.DMatrix(x, label=y,
                                    feature_names=[f"f{i}" for i in range(N_FEATURES)]),
                        num_boost_round=25)
    return {
        "feature_cols": [f"feat{i}" for i in range(N_FEATURES)],
        "booster_raw_json": booster.save_raw(raw_format="json").decode(),
    }


def test_bloat_counts_the_unused_features(artifact):
    bloat = probe.probe_bloat(probe.load_booster(artifact), artifact["feature_cols"])
    assert bloat["declared"] == N_FEATURES
    # Nothing in the label depends on feat4/feat5 and gamma prunes worthless
    # splits, so at least one of them is never split on. The probe must COUNT
    # that, not silently report 0.
    assert bloat["ever_split_on"] < N_FEATURES
    assert bloat["never_split_on"] == N_FEATURES - bloat["ever_split_on"]
    assert bloat["never_split_on"] >= 1
    # The driver must be in the top of the gain ranking, not merely present.
    assert bloat["top"][0][0] == f"feat{DRIVER}"


def test_bloat_counts_features_declared_but_absent_from_the_booster(artifact):
    """The live case: the artifact declares 172 feature_cols, the booster has
    gain for 106. The difference must be reported, not dropped."""
    padded = artifact["feature_cols"] + ["ghost0", "ghost1", "ghost2", "ghost3"]
    bloat = probe.probe_bloat(probe.load_booster(artifact), padded)
    assert bloat["declared"] == N_FEATURES + 4
    assert bloat["never_split_on"] >= 4
    assert not any(f.startswith("ghost") for f, _, _ in bloat["top"])


def test_marginal_effect_names_the_true_driver(artifact):
    booster = probe.load_booster(artifact)
    rows = probe.probe_marginal(booster, artifact["feature_cols"],
                                artifact["feature_cols"], n_baselines=200, seed=0)
    assert rows[0]["feature"] == f"feat{DRIVER}", (
        f"probe ranked {rows[0]['feature']} above the constructed driver")
    assert rows[0]["mean"] > 0            # label increases in the driver
    assert rows[0]["frac_positive"] > 0.9
    # And the noise features must NOT be credited with a comparable effect.
    driver = abs(rows[0]["mean"])
    for row in rows:
        if row["feature"] in {f"feat{i}" for i in UNUSED}:
            assert abs(row["mean"]) < 0.1 * driver


def test_marginal_effect_is_deterministic_under_a_fixed_seed(artifact):
    booster = probe.load_booster(artifact)
    kwargs = dict(n_baselines=64, seed=11)
    a = probe.probe_marginal(booster, artifact["feature_cols"],
                             artifact["feature_cols"], **kwargs)
    b = probe.probe_marginal(booster, artifact["feature_cols"],
                             artifact["feature_cols"], **kwargs)
    assert [r["mean"] for r in a] == [r["mean"] for r in b]


def test_price_ratio_classification_matches_the_alpha158_families():
    # The families whose definition divides by the current close. Getting this
    # list wrong would mislabel which features a rally mechanically depresses.
    for feat in ("MA20", "MA60", "QTLU30", "QTLD30", "MIN60", "MAX60", "ROC60", "RSV20"):
        assert feat.startswith(probe.PRICE_RATIO_PREFIXES), feat
    for feat in ("STD60", "KLEN", "CORD60", "BETA60", "book_to_price",
                 "gross_profitability", "days_since_earnings"):
        assert not feat.startswith(probe.PRICE_RATIO_PREFIXES), feat


def test_truncation_probe_reports_the_ratio_when_the_gate_bites(tmp_path):
    """A synthetic OHLCV tree where high-vol names really do carry high STD60."""
    pd = pytest.importorskip("pandas")
    rng = np.random.default_rng(3)
    dates = pd.date_range("2026-01-01", periods=80, freq="B")
    watchlist = []
    for i in range(20):
        calm = i < 10
        ticker = f"T{i}"
        watchlist.append(ticker)
        rets = rng.normal(0, 0.004 if calm else 0.05, size=len(dates))
        close = 100 * np.exp(np.cumsum(rets))
        out = tmp_path / ticker
        out.mkdir()
        pd.DataFrame({"close": close}, index=dates).to_parquet(out / "1d.parquet")
    res = probe.probe_truncation(str(tmp_path), watchlist, vol_cap_pct=60.0)
    assert res["n"] == 20
    assert res["n_dropped"] > 0 and res["n_kept"] > 0
    assert res["ratio"] > 1.0, "high-vol names must carry the larger STD60"
    assert res["spearman"] > 0.5


def test_truncation_probe_survives_a_missing_ticker_directory(tmp_path):
    res = probe.probe_truncation(str(tmp_path), ["NOPE"], vol_cap_pct=60.0)
    assert res == {"n": 0}


def test_main_runs_end_to_end_and_writes_json(artifact, tmp_path):
    art = tmp_path / "art.json"
    art.write_text(json.dumps(artifact))
    out = tmp_path / "out.json"
    assert probe.main(["--artifact", str(art), "--n-baselines", "32",
                       "--json-out", str(out)]) == 0
    payload = json.loads(out.read_text())
    assert payload["bloat"]["declared"] == N_FEATURES
    assert payload["marginal"][0]["feature"] == f"feat{DRIVER}"
