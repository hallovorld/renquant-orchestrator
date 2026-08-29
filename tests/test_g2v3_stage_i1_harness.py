"""Synthetic smoke + frozen-constant checks for the GOAL-2v3 Stage I-1 harness.

Runs scripts/experiments/g2v3_stage_i1_bases.py end-to-end on a tiny synthetic
bar store (30 names x 40 sessions x 39 slots) through the PRIVATE smoke hook
(tiny folds, 20-name IC floor). Never touches the real bar store, the census
artifact or the development window. The frozen constants are read from the
module and compared with the preregistration text literally.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/experiments/g2v3_stage_i1_bases.py"


def _load():
    spec = importlib.util.spec_from_file_location("g2v3_stage_i1_bases", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses + postponed annotations need the module registered
    spec.loader.exec_module(mod)
    return mod


M = _load()


# --------------------------------------------------------------------------
# frozen constants == the preregistration (doc/design/2026-08-27-goal2v3-intraday-granularity.md, Stage I-1)
# --------------------------------------------------------------------------
def test_frozen_constants_match_the_preregistration():
    assert M.H == 13
    assert M.SLOTS == 39 and tuple(M.SCREEN_SLOTS) == tuple(range(13, 26))
    assert (M.DEV_START, M.DEV_END) == ("2020-08-01", "2024-06-30")
    assert M.SEED_BASE == 20260828
    assert M.XGB_PARAMS == dict(objective="reg:squarederror", max_depth=3, n_estimators=300, learning_rate=0.05,
                                subsample=0.8, colsample_bytree=0.8, min_child_weight=20, tree_method="hist",
                                random_state=20260828, n_jobs=8)
    assert M.ROW_CAP == 4_000_000
    assert M.BASE_CODES == {"B0": 0, "B1": 1, "B2": 2, "B3": 3}
    assert M.MIN_SECTOR_ROWS == 50_000
    assert M.B3_SLOW_SESSIONS == 60 and M.B3_FAST_LAG_SLOTS == 39
    assert tuple(M.FOLDS) == (
        ("2021-12-31", "2022-01-01", "2022-06-30"),
        ("2022-06-30", "2022-07-01", "2022-12-31"),
        ("2022-12-31", "2023-01-01", "2023-06-30"),
        ("2023-06-30", "2023-07-01", "2023-12-31"),
        ("2023-12-31", "2024-01-01", "2024-06-30"),
    )
    assert M.PURGE_BARS == 13
    assert M.MIN_NAMES_PER_IC == 100 and M.MIN_PAIRS == 8 and M.LIFE_BAR_T == 1.0
    assert tuple(M.SECONDARY_HORIZONS) == (1, 3, 39)
    assert tuple(M.FEATURE_NAMES) == ("r1", "r3", "r13", "rv13", "rng13", "vz", "gap", "slot", "m13", "sec13", "rel13")
    # seed formula: 20260828 + 1000*fold + 100*base_code + state_index
    assert M.fit_seed(0, 0, 0) == 20260828
    assert M.fit_seed(4, 3, 2) == 20260828 + 4000 + 300 + 2
    # the --dev-run configuration uses ONLY the frozen folds / floor / window (dataclass defaults)
    f = {x.name: x.default for x in M.dataclasses.fields(M.RunConfig)}
    assert f["folds"] is M.FOLDS and f["min_names"] == 100 and f["row_cap"] == 4_000_000
    assert (f["dev_start"], f["dev_end"]) == ("2020-08-01", "2024-06-30")


def test_dev_run_config_never_takes_overrides():
    import inspect
    assert list(inspect.signature(M.dev_run_config).parameters) == []
    assert M.CENSUS_AUDIT.name == "g2v3_stage_i0_audit.json.gz"
    assert M.OUT_DIR.relative_to(M.REPO) == pathlib.Path("doc/research/data/2026-08-29-g2v3-i1")


# --------------------------------------------------------------------------
# unit checks of the literal rules
# --------------------------------------------------------------------------
def test_b3_state_rules_zero_is_up_and_missing_abstains():
    idx = pd.bdate_range("2023-01-02", periods=70)
    close = pd.Series(np.linspace(100, 110, 70), index=idx)          # rising
    sessions = [d.strftime("%Y-%m-%d") for d in idx[[60, 61, 69]]]
    slow = M.b3_slow_state(close, sessions)
    assert np.isnan(slow[0])            # only 60 closes strictly before -> fewer than 61 -> MISSING
    assert slow[1] == 1.0 and slow[2] == 1.0
    flat = pd.Series(np.full(70, 100.0), index=idx)
    assert M.b3_slow_state(flat, sessions)[2] == 1.0                   # zero return => +1
    grid = np.array([[100.0, np.nan, 100.0], [100.0, 100.0, 90.0]])
    fast = M.b3_fast_state(grid)
    assert np.isnan(fast[0]).all()                                     # first session has no prior session
    assert fast[1, 0] == 1.0 and np.isnan(fast[1, 1]) and fast[1, 2] == -1.0


def test_purge_is_literal_and_inert_on_the_a1_grid():
    sessions = ["s0", "s1", "s2"]
    rows = dict(session=np.array([0, 1, 1, 2, 2]), slot=np.array([13, 13, 25, 13, 20]))
    train = np.array([True, True, True, False, False])
    oof = np.array([False, False, False, True, True])
    purged = M.apply_purge(rows, sessions, train, oof)
    assert purged.tolist() == train.tolist()                          # label ends at bar 38 of s1; first OOF row s2 slot 13
    rows2 = dict(session=np.array([1, 2]), slot=np.array([25, 0]))     # a hypothetical OOF row at slot 0 would purge
    assert M.apply_purge(rows2, sessions, np.array([True, False]), np.array([False, True])).tolist() == [False, False]


def test_row_cap_is_global_without_replacement_and_seeded():
    idx = np.arange(10_000)
    a, capped = M.cap_rows(idx, 4_000, 123)
    b, _ = M.cap_rows(idx, 4_000, 123)
    c, _ = M.cap_rows(idx, 4_000, 124)
    assert capped and len(a) == 4_000 and len(np.unique(a)) == 4_000 and (a == b).all() and not (a == c).all()
    assert M.cap_rows(idx, 20_000, 1)[1] is False


def test_ess_fails_closed_below_eight_pairs():
    blocks = {f"s{i}": 0.1 for i in range(6)}
    eps = [("BEAR", list(blocks))]
    st = M.ess_stats(blocks, eps)
    assert st["n_eff_adj"] == "unestablished" and st["block_t"] is None and st["estimator"].startswith("FAIL_CLOSED")


# --------------------------------------------------------------------------
# end-to-end synthetic smoke
# --------------------------------------------------------------------------
REPORT_KEYS = {"stage", "run_status", "generated_at", "spec", "versions", "frozen", "inputs", "fold_row_counts",
               "bases", "s0_reference", "base_vs_b0", "stage_i2_trigger", "interpretations"}


def _smoke(tmp_path, planted, drop=None):
    syn = M._synthetic_store(tmp_path / "syn", planted=planted, drop_eligibility=drop)
    cfg = M._smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                          syn["sector_etf_map"], tmp_path / "out", M._smoke_folds(syn["sessions"]), min_names=20,
                          dev_start=syn["sessions"][0], dev_end=syn["sessions"][-1])
    return syn, M.run_stage_i1(cfg, log=lambda *a, **k: None)


def test_smoke_planted_signal_is_detected_and_schema_holds(tmp_path):
    syn, rep = _smoke(tmp_path, planted=True)
    assert REPORT_KEYS <= set(rep)
    assert rep["run_status"] == "SMOKE" and "note" in rep
    assert rep["versions"]["xgboost"]
    assert set(rep["bases"]) == {"B0", "B1", "B2", "B3"}
    for b, r in rep["bases"].items():
        assert r["horizon"] == 13
        assert set(r["per_regime"]) == set(M.K5_REGIMES)
        assert set(r["secondary_horizons_DIAGNOSTIC_ONLY"]) == {"h=1", "h=3", "h=39"}
        assert r["secondary_horizons_DIAGNOSTIC_ONLY"]["h=39"].startswith("not computed")
    b0 = rep["bases"]["B0"]["overall"]
    assert b0["estimator"] == "ok" and b0["pairs"] >= 8
    assert b0["block_t"] > 1.0, b0                                     # the planted reversal is found
    assert rep["bases"]["B0"]["passes_life_bar"] is True
    assert rep["s0_reference"]["overall"]["block_t"] > 1.0             # the naive reference sees it too
    assert set(rep["base_vs_b0"]) == {"B1", "B2", "B3"}
    assert isinstance(rep["stage_i2_trigger"]["fired"], bool)
    # artifacts on disk
    out = tmp_path / "out"
    assert json.load(open(out / "report.json"))["run_status"] == "SMOKE"
    aud = json.load(gzip.open(out / "g2v3_stage_i1_audit.json.gz"))
    assert set(aud) == {"bases", "fits", "fold_row_counts", "consumed_sha256"}
    assert set(aud["bases"]) == {"B0", "B1", "B2", "B3", "s0_reference"}
    assert len(aud["bases"]["B0"]["block_series"]) == b0["n_blocks"]
    # seeds recorded per fit follow the frozen formula
    for f in aud["fits"]:
        assert f["seed"] == M.fit_seed(f["fold_index"], M.BASE_CODES[f["base"]], f["state_index"])
        assert f["capped"] is False and f["n_train_used"] == f["n_train_raw"]
    # sec13: the healthcare ETF (XLV) is absent from the store -> recorded, not fatal
    assert rep["inputs"]["sec13_etf_available_by_sector"] == {"tech": True, "finance": True, "healthcare": False}
    assert rep["inputs"]["missing_store_files"] == ["XLV"]
    assert rep["frozen"]["folds"] != [list(f) for f in M.FOLDS]        # the smoke used the private tiny folds


def test_smoke_null_store_gives_small_block_t(tmp_path):
    _, rep = _smoke(tmp_path, planted=False)
    for b in ("B0", "B1", "B2", "B3"):
        t = rep["bases"][b]["overall"]["block_t"]
        assert t is not None and abs(t) < 3.0, (b, rep["bases"][b]["overall"])
    assert abs(rep["s0_reference"]["overall"]["block_t"]) < 3.0


def test_smoke_honours_census_eligibility_and_refuses_a_changed_store(tmp_path):
    syn0 = M._synthetic_store(tmp_path / "probe", planted=True)
    s = syn0["sessions"]
    drop = {"SYN000": [s[25], s[26]], "SYN001": [s[25]]}
    syn, rep = _smoke(tmp_path, planted=True, drop=drop)
    aud = json.load(gzip.open(tmp_path / "out" / "g2v3_stage_i1_audit.json.gz"))
    n = aud["bases"]["B0"]["per_session_n_names"]
    assert n[s[25]] == 28 and n[s[26]] == 29 and n[s[27]] == 30
    # a bar file that differs from the census's audited hash is refused (fail closed)
    p = syn["bar_store"] / "SYN005.parquet"
    df = pd.read_parquet(p)
    df.loc[0, "close"] *= 1.001
    df.to_parquet(p)
    cfg = M._smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                          syn["sector_etf_map"], tmp_path / "out2", M._smoke_folds(s), min_names=20,
                          dev_start=s[0], dev_end=s[-1])
    with pytest.raises(SystemExit, match="unaudited store"):
        M.run_stage_i1(cfg, log=lambda *a, **k: None)
