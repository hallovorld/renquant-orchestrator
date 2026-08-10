"""Rehearsal controls for the qp evidence runner (orch#955 §7, PR B).

The committed fixture IS the auditable control surface (the model#220
convention): a tiny synthetic corpus + scores + stamps run through the
REAL runner code path (identity assertions included — the fixture
manifest carries the fixture's own shas, so the sha logic is exercised,
not bypassed). Controls: (a) planted PASS, (b) null FAIL with CI
covering 0, (c) all-fail stamps ⇒ POWER_INSUFFICIENT via gate
starvation, (d) determinism, (e) sha-pin mismatch dies loudly.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RUNNER = (Path(__file__).resolve().parents[1]
          / "doc" / "research" / "data" / "2026-08-10-qp-evidence-runner.py")
spec = importlib.util.spec_from_file_location("qp_runner", RUNNER)
qp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qp)

N_DAYS, N_NAMES = 720, 40   # < POWER_FLOOR (700) after any starvation


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _build_fixture(tmp, planted: float, all_fail_stamps: bool = False,
                   n_days: int = N_DAYS, seed: int = 7, n_folds: int = 1,
                   drop_last_day_from_scores: bool = False,
                   mixed_regime_day: bool = False,
                   starve_middle_third: bool = False):
    rng = np.random.default_rng(seed)
    dates = [str(pd.Timestamp("2020-01-01") + pd.Timedelta(days=i))[:10]
             for i in range(n_days)]
    tickers = [f"T{i:02d}" for i in range(N_NAMES)]
    per_fold = n_days // n_folds
    fold_of = {d: 1 + min(i // per_fold, n_folds - 1) for i, d in enumerate(dates)}
    rows_s, rows_l = [], []
    for d in dates:
        score = rng.normal(size=N_NAMES)
        z = rng.normal(size=N_NAMES)
        z = (z - z.mean()) / z.std()
        lab = z + planted * (score - score.mean()) / score.std()
        lab = (lab - lab.mean()) / lab.std()
        di = dates.index(d)
        starved = starve_middle_third and n_days // 3 <= di < 2 * n_days // 3
        for j, (t, s_, l_) in enumerate(zip(tickers, score, lab)):
            regime = "STARVED" if starved else "BULL_CALM"
            if mixed_regime_day and d == dates[0] and j == 0:
                regime = "BEAR"
            rows_s.append({"fold": fold_of[d], "date": d, "ticker": t,
                           "recipe_score": float(s_), "regime": regime})
            rows_l.append({"date": d, "ticker": t, "fwd_5d_excess": float(l_)})
    sdf = pd.DataFrame(rows_s).sort_values(["fold", "date", "ticker"])
    if drop_last_day_from_scores:
        sdf = sdf[sdf.date != dates[-1]]
    scores = tmp / "scores.csv"
    sdf.to_csv(scores, index=False)
    corpus = tmp / "corpus.parquet"
    pd.DataFrame(rows_l).to_parquet(corpus, index=False)
    stamps = tmp / "stamps.json"
    stamps.write_text(json.dumps({
        f"fold_{f}": {"boundaries": {"train_end": "2019-12-31"},
                      "passed": not all_fail_stamps, "reason": "fixture",
                      "regimes": {"BULL_CALM": {"eligible": True,
                                                "passed": not all_fail_stamps},
                                  "STARVED": {"eligible": True,
                                              "passed": False}}}
        for f in range(1, n_folds + 1)}))
    schedule = {}
    for d in dates:
        schedule.setdefault(str(fold_of[d]), []).append(d)
    manifest = tmp / "manifest.json"
    manifest.write_text(json.dumps({
        "outputs": {"scores_csv": {"sha256": _sha(scores)},
                    "stamps_json": {"sha256": _sha(stamps)}},
        "inputs": {"frozen_corpus": {"sha256": _sha(corpus)}},
        "expected_schedule": schedule}))
    # mini harness: CUTS whose test intervals reproduce the fixture folds,
    # so the runner's INDEPENDENT derivation (CUTS x corpus dates) equals
    # the manifest schedule via the real code path
    cuts = []
    for f in range(1, n_folds + 1):
        ds = schedule[str(f)]
        cuts.append(("2016-01-01", "2019-12-31", ds[0], ds[-1]))
    harness = tmp / "harness.py"
    harness.write_text("CUTS = " + repr(cuts) + "\n")
    return scores, stamps, manifest, corpus, harness


def _run(tmp, *paths):
    out = tmp / "out"
    return qp.main(["runner", *map(str, paths), str(out), "--fixture-mode"])


def test_real_mode_rejects_fixture_corpus(tmp_path):
    scores, stamps, manifest, corpus, harness = _build_fixture(
        tmp_path, planted=0.3, n_days=30)
    with pytest.raises(AssertionError, match="freeze pin"):
        qp.main(["runner", str(scores), str(stamps), str(manifest),
                 str(corpus), str(harness), str(tmp_path / "o")])


def test_real_mode_rejects_nonfrozen_harness(tmp_path):
    # real mode must refuse ANY harness text that is not the frozen file
    scores, stamps, manifest, corpus, harness = _build_fixture(
        tmp_path, planted=0.3, n_days=30)
    import shutil
    real_corpus_placeholder = corpus  # corpus pin fails first unless bypassed;
    # to isolate the harness pin, monkeypatch the corpus constant to the fixture sha
    orig = qp.FROZEN_CORPUS_SHA
    try:
        qp.FROZEN_CORPUS_SHA = _sha(corpus)
        with pytest.raises(AssertionError, match="frozen harness pin"):
            qp.main(["runner", str(scores), str(stamps), str(manifest),
                     str(corpus), str(harness), str(tmp_path / "o")])
    finally:
        qp.FROZEN_CORPUS_SHA = orig


def test_tampered_schedule_aborts(tmp_path):
    # removing a day from BOTH scores and the manifest schedule must still
    # abort: the runner derives the schedule from CUTS x corpus dates
    scores, stamps, manifest, corpus, harness = _build_fixture(
        tmp_path, planted=0.3, n_days=30)
    m = json.loads(Path(manifest).read_text())
    dropped = m["expected_schedule"]["1"].pop(10)
    df = pd.read_csv(scores)
    df = df[df.date != dropped]
    df.to_csv(scores, index=False)
    m["outputs"]["scores_csv"]["sha256"] = _sha(scores)
    Path(manifest).write_text(json.dumps(m))
    with pytest.raises(AssertionError, match="runner-derived"):
        _run(tmp_path, scores, stamps, manifest, corpus, harness)


def test_planted_pass(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.6)
    s = _run(tmp_path, *fx)
    assert s["n_days_realized"] == N_DAYS
    assert s["mean_stat_sigma_per_day"] > qp.BAR
    assert s["bootstrap_ci95"][0] > 0
    assert s["verdict"] == "PASS"
    assert s["oracle_mean_plumbing_control"] > s["mean_stat_sigma_per_day"]


def test_null_fail_ci_covers_zero(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.0)
    s = _run(tmp_path, *fx)
    assert s["verdict"] == "FAIL"
    lo, hi = s["bootstrap_ci95"]
    assert lo < 0 < hi
    assert abs(s["mean_stat_sigma_per_day"]) < 0.1


def test_all_fail_stamps_power_insufficient(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.6, all_fail_stamps=True)
    s = _run(tmp_path, *fx)
    assert s["n_days_realized"] == 0
    assert s["n_days_gate_starved"] == N_DAYS
    assert s["verdict"] == "POWER_INSUFFICIENT"


def test_determinism(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.3)
    s1 = _run(tmp_path, *fx)
    s2 = _run(tmp_path, *fx)
    assert s1 == s2


def test_sha_mismatch_dies(tmp_path):
    scores, stamps, manifest, corpus, harness = _build_fixture(tmp_path, planted=0.3)
    m = json.loads(manifest.read_text())
    m["outputs"]["scores_csv"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(m))
    with pytest.raises(AssertionError, match="scores_csv.sha256"):
        _run(tmp_path, scores, stamps, manifest, corpus, harness)


def test_missing_day_refuses_to_adjudicate(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.3, n_days=30,
                        drop_last_day_from_scores=True)
    with pytest.raises(AssertionError, match="refusing to adjudicate"):
        _run(tmp_path, *fx)
    cov = pd.read_csv(tmp_path / "out_coverage.csv")
    assert (cov.skip == "missing_from_scores").sum() == 1
    assert not (tmp_path / "out_summary.json").exists()


def test_planted_with_missing_day_cannot_pass(tmp_path):
    # the r5 review's exact exploit: strong planted signal + one omitted
    # scheduled day must NOT produce a PASS -- it must refuse outright
    fx = _build_fixture(tmp_path, planted=0.6, n_days=720,
                        drop_last_day_from_scores=True)
    with pytest.raises(AssertionError, match="refusing to adjudicate"):
        _run(tmp_path, *fx)
    assert not (tmp_path / "out_summary.json").exists()


def test_mixed_regime_day_dies(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.3, n_days=20, mixed_regime_day=True)
    with pytest.raises(AssertionError, match="mixed regimes"):
        _run(tmp_path, *fx)


def test_two_folds_no_cross_boundary_turnover(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.3, n_days=40, n_folds=2)
    _run(tmp_path, *fx)
    daily = pd.read_csv(tmp_path / "out_daily.csv")
    # the first day of each fold must have turnover 0 (prev_top reset)
    firsts = daily.sort_values(["fold", "date"]).groupby("fold").first()
    assert (firsts.turnover == 0).all()


def test_two_folds_bootstrap_deterministic_and_runs(tmp_path):
    fx = _build_fixture(tmp_path, planted=0.3, n_days=40, n_folds=2)
    s1 = _run(tmp_path, *fx)
    s2 = _run(tmp_path, *fx)
    assert s1 == s2 and s1["bootstrap_ci95"][0] is not None


def test_tie_membership_deterministic(tmp_path):
    scores, stamps, manifest, corpus, harness = _build_fixture(tmp_path, planted=0.0, n_days=6)
    df = pd.read_csv(scores)
    df["recipe_score"] = 1.0   # all tied -> top-K must be first K tickers
    df.to_csv(scores, index=False)
    m = json.loads(Path(manifest).read_text())
    m["outputs"]["scores_csv"]["sha256"] = _sha(scores)
    Path(manifest).write_text(json.dumps(m))
    s = _run(tmp_path, scores, stamps, manifest, corpus, harness)
    daily = pd.read_csv(tmp_path / "out_daily.csv")
    assert len(daily) == 6   # ran; membership = lexicographically first K


def test_interleaved_starvation_splits_bootstrap_runs(tmp_path):
    # review r7 fixture: a starved middle third must split the admitted
    # days into two contiguous runs -- no block may bridge the gap
    fx = _build_fixture(tmp_path, planted=0.3, n_days=90,
                        starve_middle_third=True)
    scores, stamps, manifest, corpus, harness = fx
    s = _run(tmp_path, *fx)
    assert s["n_days_gate_starved"] == 30
    assert s["n_days_realized"] == 60
    # reconstruct the runs exactly as the runner does and assert the split
    import ast as _ast
    daily = pd.read_csv(tmp_path / "out_daily.csv")
    cuts = _ast.literal_eval(Path(harness).read_text().split("=", 1)[1])
    corpus_dates = sorted(pd.read_parquet(corpus, columns=["date"])["date"]
                          .astype(str).str[:10].unique())
    derived = {str(i + 1): [d for d in corpus_dates if ts <= d <= te]
               for i, (_, _, ts, te) in enumerate(cuts)}
    runs = qp.admitted_runs(daily, derived)
    assert len(runs) == 2 and len(runs[0]) == 30 and len(runs[1]) == 30
