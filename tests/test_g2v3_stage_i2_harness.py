"""Frozen constants, §2-§4 arithmetic and the synthetic smoke of the GOAL-2v3 Stage I-2 harness.

scripts/experiments/g2v3_stage_i2_stack.py implements doc/design/2026-08-29-goal2v3-stage-i2-prereg.md (#1089)
on top of the imported I-1 harness. Every frozen number is read from the module and compared with the prereg
TEXT (the markdown itself is parsed for the bound identifiers, parameters and the six interpretations). The
meta-fold layout, purge, NaN meta-features, common-sample exclusion, P1/P2/P3 + every outcome-register row,
the M0 z-sum floor and the determinism guard are exercised on synthetic numbers; the end-to-end smoke runs
on a tiny synthetic bar store through the PRIVATE smoke hook and must finish in under 60 s. Nothing here
touches the real bar store or runs --dev-run.
"""
from __future__ import annotations

import gzip
import importlib.util
import inspect
import json
import pathlib
import re
import sys
import time

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/experiments/g2v3_stage_i2_stack.py"
PREREG = REPO / "doc/design/2026-08-29-goal2v3-stage-i2-prereg.md"


def _load():
    spec = importlib.util.spec_from_file_location("g2v3_stage_i2_stack", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load()
I1 = M.I1
SILENT = dict(log=lambda *a, **k: None)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


PREREG_TEXT = _norm(PREREG.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# frozen constants == the preregistration text
# --------------------------------------------------------------------------- #
def test_i1_is_imported_not_copied():
    assert M.I1.__file__ == str(REPO / "scripts/experiments/g2v3_stage_i1_bases.py")
    for name in ("build_rows", "run_bases", "fold_masks", "apply_purge", "cap_rows", "session_blocks", "episodes_of",
                 "ess_stats", "screen_base", "check_store_manifest", "load_gate_authorization", "source_state",
                 "b3_slow_state", "_synthetic_store", "_smoke_config"):
        assert callable(getattr(M.I1, name)), name
    src = SCRIPT.read_text(encoding="utf-8")
    for fn in ("def build_rows", "def run_bases", "def session_blocks", "def ess_stats", "def check_store_manifest",
               "def name_features", "def load_gate_authorization"):
        assert fn not in src, f"{fn} re-implemented in the I-2 harness instead of reused"
    assert (M.H, M.SLOTS, tuple(M.SCREEN_SLOTS)) == (13, 39, tuple(range(13, 26)))
    assert M.MIN_NAMES_PER_IC == 100 and M.MIN_PAIRS == 8 and M.LIFE_BAR_T == 1.0
    assert M.B1_STATE_LAG_SESSIONS == 1 and M.B3_SLOW_SESSIONS == 60


def test_accepted_i1_bundle_matches_the_prereg_binding_text():
    b = M.ACCEPTED_I1_BUNDLE
    assert b["run_id"] == "i1-dev-20260829T113813Z-666484a7"
    assert b["source_commit"] == "666484a7ab37dc9f88dd5692f8d9e90f3aab9332"
    assert b["run_status"] == "DEV_RUN"
    assert b["report_sha256"] == "666d9c6a9a2286af4215399aebbd07a2fda8efafc6b5440d8d39ea6b9e1e1542"
    assert b["audit_sha256"] == "d124d8f2a8766edf7d4a6f767206444467f05fa3bb8dec1818a76b01b2cd3082"
    assert b["consumed_bar_aggregate_sha256"] == "4addcbe25f164a57afc0ea9fb0fd4e8e368a17fc292e2fe62b80fff5219d3883"
    assert b["dir"] == "doc/research/data/2026-08-29-g2v3-i1/" + b["run_id"]
    for token in (b["run_id"], b["report_sha256"], b["audit_sha256"], b["consumed_bar_aggregate_sha256"],
                  "source commit 666484a7", "#1088"):
        assert token in PREREG_TEXT, token
    assert M.SURVIVING_BASES == ("B0", "B1", "B2", "B3")


def test_determinism_targets_match_the_prereg_text():
    assert M.EXPECTED_I1_BLOCK_T == {"B0": 3.5042, "B1": 3.1837, "B2": 3.5915, "B3": 3.2394}
    assert M.EXPECTED_I1_N_BLOCKS == {"B0": 622, "B1": 511, "B2": 622, "B3": 619}
    assert M.DETERMINISM_DECIMALS == 4
    assert "(B0 3.5042, B1 3.1837, B2 3.5915, B3 3.2394)" in PREREG_TEXT
    assert "`n_blocks` (622/511/622/619)" in PREREG_TEXT
    assert "reproduces the I-1 overall block-t to 4 decimals" in PREREG_TEXT
    assert (M.ACCEPTED_I1_BUNDLE["s0_block_t"], M.ACCEPTED_I1_BUNDLE["s0_n_blocks"]) == (4.1861, 622)
    assert "scores **4.1861**" in PREREG_TEXT


def test_meta_folds_match_the_prereg_table():
    assert [(m["name"], m["train_start"], m["train_end"], m["oof_start"], m["oof_end"]) for m in M.META_FOLDS] == [
        ("M1", "2022-01-01", "2022-06-30", "2022-07-01", "2022-12-31"),
        ("M2", "2022-01-01", "2022-12-31", "2023-01-01", "2023-06-30"),
        ("M3", "2022-01-01", "2023-06-30", "2023-07-01", "2023-12-31"),
        ("M4", "2022-01-01", "2023-12-31", "2024-01-01", "2024-06-30"),
    ]
    assert [m["train_base_folds"] for m in M.META_FOLDS] == [[0], [0, 1], [0, 1, 2], [0, 1, 2, 3]]
    assert [m["oof_base_fold"] for m in M.META_FOLDS] == [1, 2, 3, 4]
    assert M.META_OOF_PERIOD == ("2022-07-01", "2024-06-30")
    assert "meta-OOF period is 2022-07-01..2024-06-30" in PREREG_TEXT
    for row in ("| M1 | 2022H1 | 2022H2 |", "| M2 | 2022H1–2022H2 | 2023H1 |", "| M3 | 2022H1–2023H1 | 2023H2 |",
                "| M4 | 2022H1–2023H2 | 2024H1 |"):
        assert row in PREREG_TEXT, row
    # 2022H1 (FOLDS[0]) is never meta-scored; M1 trains on 2022H1 ONLY
    assert min(m["oof_start"] for m in M.META_FOLDS) == "2022-07-01"
    assert M.META_FOLDS[0]["train_base_folds"] == [0] and M.META_FOLDS[0]["train_end"] == M.FOLDS[0][2]
    assert M.META_PURGE_BARS == 13
    assert M.meta_fold_layout(M.FOLDS) == M.META_FOLDS


def test_meta_learner_constants_match_the_prereg_text():
    assert M.META_XGB_PARAMS == dict(objective="reg:squarederror", max_depth=2, n_estimators=200, learning_rate=0.05,
                                     subsample=0.8, colsample_bytree=1.0, min_child_weight=50, tree_method="hist",
                                     random_state=20260829, n_jobs=8)
    for k, v in M.META_XGB_PARAMS.items():
        if k == "objective":
            assert "`reg:squarederror`" in PREREG_TEXT
        else:
            literal = f'`{k}="{v}"`' if isinstance(v, str) else f"`{k}={v}`"
            assert literal in PREREG_TEXT, (k, v)
    assert M.META_ROW_CAP == 4_000_000 and "Row cap 4,000,000 per meta-fit" in PREREG_TEXT
    assert M.META_SEED_BASE == 20260829 and "seed `20260829 + 1000·meta_fold`" in PREREG_TEXT
    assert [M.meta_seed(k) for k in (1, 2, 3, 4)] == [20261829, 20262829, 20263829, 20264829]
    assert M.META_FEATURES == ("p_B0", "p_B1", "p_B2", "p_B3", "n_abstain", "regime_BEAR", "regime_BULL_CALM",
                               "regime_BULL_VOLATILE", "regime_CHOPPY", "b3_slow_sign", "slot")
    assert len(M.META_FEATURES) == 11 and "Meta-features (11)" in PREREG_TEXT
    assert "s0" not in M.META_FEATURES and not any(f.startswith("sector") for f in M.META_FEATURES)
    assert M.META_LABEL_HORIZON == 13 and tuple(M.SECONDARY_HORIZONS) == (1, 3)
    assert M.P1_LIFE_BAR_T == 1.0 and M.P1_BEAR_MIN_N_EFF_ADJ == 30.0
    assert "BEAR n_eff_adj ≥ 30 re-verified" in PREREG_TEXT
    assert M.SERIES == ("M_xgb", "M0", "B0", "B1", "B2", "B3", "s0")


def test_outcome_register_and_interpretations_are_verbatim_from_the_prereg():
    for verdict, row in M.OUTCOME_REGISTER.items():
        line = f"| {verdict} | {row['condition']} | {row['consequence']} |"
        assert _norm(line) in PREREG_TEXT, line
    assert set(M.OUTCOME_REGISTER) == {"PASS", "FAIL-A", "FAIL-B", "REFUSED"}
    assert len(M.PREREG_INTERPRETATIONS) == 6
    for i, text in enumerate(M.PREREG_INTERPRETATIONS, start=1):
        assert f"{i}. {_norm(text)}" in PREREG_TEXT, (i, text[:60])
    assert M.INTERPRETATIONS[:6] == M.PREREG_INTERPRETATIONS
    assert M.INTERPRETATIONS[6:] == M.HARNESS_INTERPRETATIONS
    for i, text in enumerate(M.HARNESS_INTERPRETATIONS, start=7):
        assert text.startswith(f"[harness {i}]"), text[:20]
    assert M.SPEC == "doc/design/2026-08-29-goal2v3-stage-i2-prereg.md"
    assert M.OUT_DIR.relative_to(M.REPO) == pathlib.Path("doc/research/data/2026-08-29-g2v3-i2")


def test_dev_run_config_takes_only_the_two_authorizations():
    assert list(inspect.signature(M.dev_run_config).parameters) == ["auth", "i1"]
    f = {x.name: x.default for x in M.dataclasses.fields(M.I2Config)}
    assert f["meta_row_cap"] == 4_000_000 and f["i1"] is None and f["expected_block_t"] is None
    with pytest.raises(M.I1NotBound, match="needs the I1Binding"):
        M.dev_run_config(object(), object())


# --------------------------------------------------------------------------- #
# §2 nested OOF: layout, purge
# --------------------------------------------------------------------------- #
def _rows(session, slot, n_bases_nan=None):
    session, slot = np.asarray(session), np.asarray(slot)
    return dict(name=np.zeros(len(session), dtype=np.int32), session=session.astype(np.int32),
                slot=slot.astype(np.int16), sessions=[f"s{i}" for i in range(int(session.max()) + 1)],
                Y=np.zeros((len(session), 3), dtype=np.float32), b1=np.zeros(len(session), dtype=np.int16))


def test_run_meta_trains_forward_chaining_and_never_scores_the_first_half(monkeypatch):
    # 3 base folds (sessions 0 | 1 | 2), one row per (session, slot 13/25)
    rows = _rows([0, 0, 1, 1, 2, 2], [13, 25, 13, 25, 13, 25])
    rows["Y"][:, 0] = np.arange(6, dtype=np.float32)
    oof_masks = [rows["session"] == k for k in range(3)]
    X = np.arange(6, dtype=np.float32)[:, None].repeat(11, axis=1)
    seen = []

    def fake_fit(X_tr, y_tr, X_te):
        seen.append((X_tr[:, 0].tolist(), X_te[:, 0].tolist()))
        return np.full(len(X_te), 0.5, dtype=np.float32)
    monkeypatch.setattr(M, "fit_meta", fake_fit)
    folds = (("a", "b", "c"),) * 3
    cfg = M.I2Config(base=I1.RunConfig(bar_store="x", census_audit="x", spy_daily="x",
                                       sector_map={}, sector_etf_map={}, out_dir="x",
                                       run_status="SMOKE", folds=folds), out_dir="x",
                     run_status="SMOKE")
    p, meta_oof, recs = M.run_meta(rows, X, oof_masks, cfg, **SILENT)
    assert seen == [([0.0, 1.0], [2.0, 3.0]), ([0.0, 1.0, 2.0, 3.0], [4.0, 5.0])]   # M1: fold0 only; M2: fold0+1
    assert np.isnan(p[:2]).all() and (p[2:] == 0.5).all()                           # first half never meta-scored
    assert meta_oof.tolist() == [False, False, True, True, True, True]
    assert [r["seed"] for r in recs] == [20261829, 20262829] and all(r["n_purged"] == 0 for r in recs)
    assert [r["n_train_used"] for r in recs] == [2, 4] and not any(r["capped"] for r in recs)


def test_meta_purge_is_the_literal_13_bar_rule_via_i1_machinery():
    rows = _rows([0, 0, 0, 1], [13, 26, 27, 13])
    train, oof = np.array([True, True, True, False]), np.array([False, False, False, True])
    kept = I1.apply_purge(rows, rows["sessions"], train, oof)
    # bar(s=0,t=27) + 13 label + 13 purge = 53 > first OOF bar 52 -> purged; t=26 is exactly at the boundary (kept)
    assert kept.tolist() == [True, True, False, False]
    assert M.META_PURGE_BARS == I1.PURGE_BARS == 13


def test_meta_row_cap_uses_the_meta_seed_without_replacement(monkeypatch):
    idx = np.arange(100)
    a, capped = I1.cap_rows(idx, 40, M.meta_seed(1))
    b, _ = I1.cap_rows(idx, 40, M.meta_seed(1))
    c, _ = I1.cap_rows(idx, 40, M.meta_seed(2))
    assert capped and len(a) == 40 and len(set(a.tolist())) == 40 and a.tolist() == b.tolist() and a.tolist() != c.tolist()


# --------------------------------------------------------------------------- #
# §3 meta-features: NaN on abstain, n_abstain, one-hot, slow sign, slot; s0 absent
# --------------------------------------------------------------------------- #
def test_meta_features_nan_on_abstain_and_counts():
    rows = _rows([0, 0, 1, 2], [13, 14, 15, 16])
    rows["b1"] = np.array([0, 1, -1, 3], dtype=np.int16)
    nan = np.nan
    preds = {"B0": np.array([0.1, 0.2, 0.3, 0.4], np.float32), "B1": np.array([nan, 0.2, nan, 0.4], np.float32),
             "B2": np.array([0.1, nan, nan, 0.4], np.float32), "B3": np.array([nan, nan, nan, 0.4], np.float32)}
    b3_slow = np.array([1.0, -1.0, nan])
    X, diag = M.meta_features(rows, preds, b3_slow)
    assert X.shape == (4, 11) and X.dtype == np.float32
    F = list(M.META_FEATURES)
    assert np.isnan(X[0, F.index("p_B1")]) and np.isnan(X[0, F.index("p_B3")]) and X[0, F.index("p_B0")] == np.float32(0.1)
    assert X[:, F.index("n_abstain")].tolist() == [2, 2, 3, 0]
    assert X[0, 5:9].tolist() == [1, 0, 0, 0] and X[1, 5:9].tolist() == [0, 1, 0, 0]
    assert X[2, 5:9].tolist() == [0, 0, 0, 0] and X[3, 5:9].tolist() == [0, 0, 0, 1]    # -1 => all zeros
    assert X[:, F.index("b3_slow_sign")][:2].tolist() == [1.0, 1.0] and X[2, F.index("b3_slow_sign")] == -1.0
    assert np.isnan(X[3, F.index("b3_slow_sign")])
    assert X[:, F.index("slot")].tolist() == [13, 14, 15, 16]
    assert diag == dict(regime_undefined_rows=1, b3_slow_missing_rows=1)


# --------------------------------------------------------------------------- #
# §3 M0: z-sum within the session×slot cross-section, floor MIN_NAMES_PER_IC
# --------------------------------------------------------------------------- #
def test_m0_zsum_needs_min_names_and_sums_available_z():
    # cross-section A: 5 names at (session 0, slot 13); cross-section B: 3 names at (session 0, slot 14)
    rows = _rows([0] * 8, [13] * 5 + [14] * 3)
    nan = np.nan
    p0 = np.array([1, 2, 3, 4, 5, 1, 2, 3], float)
    preds = {"B0": p0, "B1": p0.copy(), "B2": np.full(8, nan), "B3": np.array([7, 7, 7, 7, 7, 1, 2, 3], float)}
    mask = np.ones(8, dtype=bool)
    m0 = M.m0_zsum(rows, preds, mask, min_names=4)
    z = (p0[:5] - 3.0) / np.std(p0[:5], ddof=1)
    assert np.allclose(m0[:5], 2 * z, atol=1e-6)            # B0 + B1 available; B2 all NaN; B3 zero spread -> nothing
    assert np.isnan(m0[5:]).all()                             # 3 names < 4 => no M0 value
    assert np.isnan(M.m0_zsum(rows, preds, mask, min_names=6)).all()
    # a row whose bases are all NaN has no M0 even inside a big cross-section
    preds2 = {k: v.copy() for k, v in preds.items()}
    for k in preds2:
        preds2[k][0] = nan
    m0b = M.m0_zsum(rows, preds2, mask, min_names=4)
    assert np.isnan(m0b[0]) and np.isfinite(m0b[1:5]).all()
    assert np.isnan(M.m0_zsum(rows, preds, np.zeros(8, dtype=bool), 4)).all()
    assert M.MIN_NAMES_PER_IC == 100                          # the DEV_RUN floor (RunConfig default)


# --------------------------------------------------------------------------- #
# §4 common sample, P1/P2/P3, every outcome-register row
# --------------------------------------------------------------------------- #
def test_common_sample_exclusion_arithmetic():
    nan = np.nan
    meta_oof = np.array([True] * 8 + [False] * 2)
    p_meta = np.array([1.0] * 10)
    preds = {"B0": np.ones(10), "B1": np.array([1, nan, 1, 1, 1, 1, 1, 1, 1, 1.0]),
             "B2": np.array([1, nan, nan, 1, 1, 1, 1, 1, 1, 1.0]), "B3": np.ones(10)}
    s0 = np.ones(10)
    m0 = np.array([1, 1, 1, nan, 1, 1, 1, 1, 1, 1.0])
    common, common_m0, st = M.common_sample(meta_oof, p_meta, preds, s0, m0)
    assert common.tolist() == [True, False, False, True, True, True, True, True, False, False]
    assert common_m0.tolist() == [True, False, False, False, True, True, True, True, False, False]
    assert st["n_meta_oof_rows"] == 8 and st["n_mxgb_scored_rows"] == 8 and st["n_common"] == 6
    assert st["n_excluded"] == 2 and st["excluded_fraction"] == 0.25
    assert st["excluded_by_series"] == {"p_B0": 0, "p_B1": 1, "p_B2": 2, "p_B3": 0, "s0": 0}
    assert st["n_common_m0"] == 5 and st["m0_only_extra_excluded"] == 1 and st["m0_only_extra_excluded_fraction"] == round(1 / 6, 6)


def _series(t_m, t_bases, t_s0, bear=100.0):
    def res(t, bear_n=None):
        return dict(overall=dict(block_t=t), per_regime=dict(BEAR=dict(n_eff_adj=bear_n)))
    s = {"M_xgb": res(t_m, bear), "s0": res(t_s0), "M0": res(0.0)}
    for bb, t in zip(("B0", "B1", "B2", "B3"), t_bases):
        s[bb] = res(t)
    return s


@pytest.mark.parametrize("t_m,bases,t_s0,bear,expect", [
    (4.5, (3.5042, 3.1837, 3.5915, 3.2394), 4.1861, 45.0, ("PASS", True, True, True)),
    (4.0, (3.5042, 3.1837, 3.5915, 3.2394), 4.1861, 45.0, ("FAIL-A", True, True, False)),
    (3.0, (3.5042, 3.1837, 3.5915, 3.2394), 4.1861, 45.0, ("FAIL-B", True, False, False)),
    (0.9, (0.1, 0.2, 0.3, 0.4), 0.0, 45.0, ("FAIL-B", False, True, True)),        # life bar fails => FAIL-B even if P2,P3
    (4.5, (3.5042, 3.1837, 3.5915, 3.2394), 4.1861, 29.9, ("FAIL-B", False, True, True)),  # BEAR n_eff_adj < 30
    (4.5, (3.5042, 3.1837, 3.5915, 3.2394), 4.1861, "unestablished", ("FAIL-B", False, True, True)),
    (3.5915, (3.5042, 3.1837, 3.5915, 3.2394), 3.0, 45.0, ("FAIL-B", True, False, True)),  # equality is not > (P2)
    (4.1861, (3.0, 3.0, 3.0, 3.0), 4.1861, 45.0, ("FAIL-A", True, True, False)),           # equality is not > (P3)
    (4.5, (3.5042, None, 3.5915, 3.2394), 4.1861, 45.0, ("FAIL-B", True, False, True)),     # a base unestablished => P2 fails
    (None, (3.5042, 3.1837, 3.5915, 3.2394), 4.1861, 45.0, ("FAIL-B", False, False, False)),
])
def test_pass_bar_and_outcome_register_rows(t_m, bases, t_s0, bear, expect):
    bar = M.pass_bar(_series(t_m, bases, t_s0, bear))
    verdict, p1, p2, p3 = expect
    assert (bar["P1"]["passes"], bar["P2"]["passes"], bar["P3"]["passes"]) == (p1, p2, p3)
    assert bar["stage_i2_pass"] == (p1 and p2 and p3)
    out = M.outcome_of(bar)
    assert out["verdict"] == verdict
    assert out["condition"] == M.OUTCOME_REGISTER[verdict]["condition"]
    assert out["consequence"] == M.OUTCOME_REGISTER[verdict]["consequence"]
    assert out["register_row"] == f"| {verdict} | {out['condition']} | {out['consequence']} |"
    assert out["register"].endswith("§4.4")


def test_pass_bar_states_margins_as_numbers():
    bar = M.pass_bar(_series(4.5, (3.5042, 3.1837, 3.5915, 3.2394), 4.1861, 45.0))
    assert bar["P1"]["margin_block_t"] == 3.5 and bar["P1"]["margin_bear"] == 15.0
    assert bar["P2"]["best_base"] == "B2" and bar["P2"]["best_base_block_t"] == 3.5915 and bar["P2"]["margin"] == 0.9085
    assert bar["P3"]["s0_block_t"] == 4.1861 and bar["P3"]["margin"] == 0.3139
    assert bar["P1"]["life_bar_t"] == 1.0 and bar["P1"]["bear_min"] == 30.0
    assert "REFUSED" not in {M.outcome_of(M.pass_bar(_series(t, (1, 1, 1, 1), 1.0)))["verdict"] for t in (0.0, 2.0)}


# --------------------------------------------------------------------------- #
# §1.1 determinism guard (pure)
# --------------------------------------------------------------------------- #
def _refit(t, n):
    return {bb: dict(overall=dict(block_t=t[bb], n_blocks=n[bb])) for bb in t}


def test_determinism_guard_exact_proceeds_off_by_1e4_refuses():
    T, N = M.EXPECTED_I1_BLOCK_T, M.EXPECTED_I1_N_BLOCKS
    rec = M.determinism_guard(_refit(T, N), T, N)
    assert rec["status"] == "PASS" and all(v["match"] for v in rec["per_series"].values())
    assert set(rec["per_series"]) == {"B0", "B1", "B2", "B3"}
    # with the s0 reference attached (harness interpretation 8)
    s0 = dict(overall=dict(block_t=4.1861, n_blocks=622))
    rec = M.determinism_guard(_refit(T, N), T, N, s0, (4.1861, 622))
    assert rec["per_series"]["s0"]["match"] is True
    # a 5th-decimal drift that rounds away is tolerated; a 4th-decimal drift is REFUSED
    ok = dict(T, B2=3.59152)
    assert M.determinism_guard(_refit(ok, N), T, N)["status"] == "PASS"
    bad = dict(T, B2=3.5916)
    with pytest.raises(M.DeterminismRefused, match=r"B2: block_t 3.5916 vs 3.5915 @ 4 dp"):
        M.determinism_guard(_refit(bad, N), T, N)
    with pytest.raises(M.DeterminismRefused, match=r"B1: block_t 3.1837 vs 3.1837 @ 4 dp, n_blocks 512 vs 511"):
        M.determinism_guard(_refit(T, dict(N, B1=512)), T, N)
    with pytest.raises(M.DeterminismRefused, match=r"B0: block_t None"):
        M.determinism_guard(_refit(dict(T, B0=None), N), T, N)
    with pytest.raises(M.DeterminismRefused, match=r"s0: block_t 4.1862"):
        M.determinism_guard(_refit(T, N), T, N, dict(overall=dict(block_t=4.1862, n_blocks=622)), (4.1861, 622))
    assert issubclass(M.DeterminismRefused, M.DevRunRefused) and issubclass(M.I1NotBound, M.DevRunRefused)


# --------------------------------------------------------------------------- #
# synthetic smoke end-to-end (< 60 s)
# --------------------------------------------------------------------------- #
REPORT_KEYS = {"stage", "run_status", "run_id", "generated_at", "spec", "i1_spec", "versions", "frozen", "inputs",
               "base_refit", "meta", "common_sample", "series", "pass_bar", "outcome", "prereg_interpretations",
               "harness_interpretations", "interpretations", "provenance", "note"}


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("i2smoke")
    t0 = time.monotonic()
    report = M.run_smoke(tmp, planted=True, **SILENT)
    elapsed = time.monotonic() - t0
    audit = json.load(gzip.open(tmp / "out" / "g2v3_stage_i2_audit.json.gz"))
    return dict(tmp=tmp, report=report, audit=audit, elapsed=elapsed)


def test_smoke_runs_end_to_end_under_60s_with_the_full_schema(smoke):
    rep, aud = smoke["report"], smoke["audit"]
    assert smoke["elapsed"] < 60.0, smoke["elapsed"]
    assert REPORT_KEYS <= set(rep)
    assert rep["run_status"] == "SMOKE" and rep["stage"] == "GOAL-2v3 Stage I-2" and rep["versions"]["xgboost"]
    assert M._RUN_ID.match(rep["run_id"]) and rep["run_id"].startswith("i2-smoke-")
    # base re-fit exactly as I-1 (its folds, its seeds), guard NOT applied on synthetic data
    assert set(rep["base_refit"]["bases"]) == {"B0", "B1", "B2", "B3"}
    assert rep["base_refit"]["determinism_guard"]["status"] == "NOT_APPLIED"
    for f in aud["base_fits"]:
        assert f["seed"] == I1.fit_seed(f["fold_index"], I1.BASE_CODES[f["base"]], f["state_index"])
    assert len(rep["base_refit"]["fold_row_counts"]) == 3
    # meta: two meta-folds over three base folds; first base-OOF half never meta-scored
    folds = rep["meta"]["folds"]
    assert [m["name"] for m in folds] == ["M1", "M2"] and [m["seed"] for m in folds] == [20261829, 20262829]
    assert folds[0]["train_base_folds"] == [0] and folds[1]["train_base_folds"] == [0, 1]
    n_oof = {c["fold_index"]: c["n_oof_rows"] for c in rep["base_refit"]["fold_row_counts"]}
    assert rep["meta"]["n_meta_oof_rows"] == n_oof[1] + n_oof[2] == rep["inputs"]["n_meta_oof_observations"]
    assert rep["meta"]["features"] == list(M.META_FEATURES) and rep["meta"]["s0_is_a_feature"] is False
    assert set(rep["meta"]["feature_nan_counts_on_meta_oof"]) == set(M.META_FEATURES)
    assert rep["meta"]["b2_oof_states_by_fold"] == {"fold_0": ["OTHER"], "fold_1": ["OTHER"], "fold_2": ["OTHER"]}
    # common sample + series
    cs = rep["common_sample"]
    assert cs["n_common"] == cs["n_mxgb_scored_rows"] - cs["n_excluded"] and 0 <= cs["excluded_fraction"] <= 1
    assert set(rep["series"]) == set(M.SERIES) | {"M_xgb_full_meta_oof_DIAGNOSTIC_ONLY"}
    for name, res in rep["series"].items():
        assert set(res["per_regime"]) == set(M.K5_REGIMES)
        assert res["gating"] is (name == "M_xgb")
        assert "passes_life_bar" not in res and "life_bar" not in res
    assert set(rep["series"]["M_xgb"]["secondary_horizons_DIAGNOSTIC_ONLY"]) == {"h=1", "h=3", "h=39"}
    assert "secondary_horizons_DIAGNOSTIC_ONLY" not in rep["series"]["B0"]
    assert rep["series"]["M_xgb"]["overall"]["block_t"] > 1.0             # the planted reversal reaches the stack
    assert rep["series"]["M_xgb"]["overall"]["estimator"] == "ok"
    assert rep["series"]["s0"]["overall"]["block_t"] > 1.0
    # pass bar / outcome: computed, quoted, NOT binding on synthetic data
    assert rep["pass_bar"]["stage_i2_pass"] == (rep["pass_bar"]["P1"]["passes"] and rep["pass_bar"]["P2"]["passes"]
                                                and rep["pass_bar"]["P3"]["passes"])
    assert rep["outcome"]["verdict"] in ("PASS", "FAIL-A", "FAIL-B") and rep["outcome"]["binding"] is False
    assert rep["outcome"]["register_row"].startswith(f"| {rep['outcome']['verdict']} |")
    assert rep["interpretations"] == M.INTERPRETATIONS and rep["prereg_interpretations"] == M.PREREG_INTERPRETATIONS
    # artifacts + provenance
    out = smoke["tmp"] / "out"
    assert json.load(open(out / "report.json"))["run_id"] == rep["run_id"]
    assert set(aud) == {"base_refit", "base_fits", "fold_row_counts", "meta_folds", "series", "consumed_sha256"}
    assert set(aud["series"]) == {"M_xgb", "M_xgb_full_meta_oof", "M0", "B0", "B1", "B2", "B3", "s0"}
    assert len(aud["series"]["M_xgb"]["block_series"]) == rep["series"]["M_xgb"]["overall"]["n_blocks"]
    assert rep["provenance"]["gate_bundle"] is None and rep["provenance"]["i1_bundle"] is None
    assert rep["provenance"]["consumed_bar_manifest"]["matches_i1_bundle"] is None
    assert M.validate_i2_provenance(rep, aud, M.REPO) == []


def test_smoke_common_sample_and_m0_are_computed_on_the_same_rows(smoke):
    rep = smoke["report"]
    n = rep["series"]["M_xgb"]["n_scored_rows"]
    for bb in ("B0", "B1", "B2", "B3", "s0"):
        assert rep["series"][bb]["n_scored_rows"] == n, bb
    assert rep["series"]["M0"]["n_scored_rows"] == rep["common_sample"]["n_common_m0"] <= n


def test_cli_default_is_the_synthetic_smoke(tmp_path, capsys):
    assert M.main(["--smoke-out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    summary = json.loads(out[out.index("{"):])
    assert summary["run_status"] == "SMOKE" and summary["binding"] is False
    assert summary["determinism_guard"] == "NOT_APPLIED" and set(summary["series"]) >= set(M.SERIES)
    assert (tmp_path / "out" / "report.json").is_file()
