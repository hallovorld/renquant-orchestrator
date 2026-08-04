"""Positive-control fixtures for the S2 readout (mandatory per the frozen
prereg's measurement-mechanics clause; these are the ONLY runs allowed
before session 20). Everything here is synthetic — no real record surface
is touched."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))

import pytest as _pytest
_pytest.importorskip(
    "renquant_model_momentum",
    reason="the momentum arm now loads through the pipeline provider "
           "boundary (pipeline#262), which needs the model distro; hosted "
           "CI skips, the operator machine runs")
_pytest.importorskip("renquant_pipeline.kernel.panel_pipeline.momentum_residual_scorer")

import s2_readout as s2  # noqa: E402
from renquant_model_momentum.ledger import row_sha256_of  # noqa: E402
import renquant_model_momentum as mm  # noqa: E402

SESSIONS = [f"2026-09-{d:02d}" for d in range(1, 21)]  # 20 synthetic sessions
CUTOFFS = {s: f"{s}T20:00:00+00:00" for s in SESSIONS}


def _mk_runs_db(path: Path, per_session_scores: dict[str, dict[str, float]],
                *, decoy_runs: int = 0,
                decoy_scores: "dict[str, float] | None" = None) -> None:
    """decoy_runs adds same-day runs: holding-role-only decoys (the live
    intraday pattern, 21-35/session measured 2026-08-04) plus — when
    decoy_scores is set — a candidate-carrying decoy with a LOWER run_id
    than the canonical run, which the lexicographically-last rule must
    ignore."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT)")
    con.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT, rank_score REAL)")
    for i, (session, scores) in enumerate(per_session_scores.items()):
        rid = f"{session}-live-zz{i}"
        con.execute("INSERT INTO pipeline_runs VALUES (?,?)", (rid, session))
        for t, sc in scores.items():
            con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (rid, t, "candidate", sc))
        con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (rid, "HOLD1", "holding", 99.0))
        for d in range(decoy_runs):
            drid = f"{session}-live-aa{d}"
            con.execute("INSERT INTO pipeline_runs VALUES (?,?)", (drid, session))
            con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (drid, "HOLD1", "holding", 42.0))
        if decoy_scores:
            drid = f"{session}-live-mm0"   # sorts BELOW zz -> must be ignored
            con.execute("INSERT INTO pipeline_runs VALUES (?,?)", (drid, session))
            for t, sc in decoy_scores.items():
                con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (drid, t, "candidate", sc))
    con.commit(); con.close()


def _mk_fwd_db(path: Path, per_session_returns: dict[str, dict[str, float]]) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE ticker_forward_returns (as_of_date TEXT, ticker TEXT, fwd_1d REAL)")
    for session, rets in per_session_returns.items():
        for t, r in rets.items():
            con.execute("INSERT INTO ticker_forward_returns VALUES (?,?,?)", (session, t, r))
    con.commit(); con.close()


def _mk_momentum(root: Path, entries: list[tuple[str, str, dict[str, float]]]) -> Path:
    """entries: (cutoff_date, appended_at_utc, scores) — built with the REAL
    model package (train on synthetic readers is overkill here, so artifacts
    are packaged via the package's own content sha + ledger append, then
    appended_at is resealed with ledger.row_sha256_of)."""
    import numpy as np
    import pandas as pd

    class _Readers:
        def __init__(self, universe, asof, seed):
            idx = pd.bdate_range(end=pd.Timestamp(asof), periods=90)
            rng = np.random.default_rng(seed)
            self._r = {t: pd.Series(rng.normal(0.001, 0.02, 90), index=idx)
                       for t in [*universe, "SPY"]}
            self._v = {t: pd.Series(rng.integers(1000, 9999, 90).astype(float), index=idx)
                       for t in universe}
            self._s = {t: ("TECH" if i % 2 else "ENER") for i, t in enumerate(universe)}
        def tr_returns(self, t): return self._r.get(t)
        def volume(self, t): return self._v.get(t)
        def market_tr_returns(self): return self._r["SPY"]
        def sector_of(self): return dict(self._s)
        def read_digests(self): return {"synthetic": "0" * 64}

    params = {"params_version": "v0", "window": 60, "skip": 5, "min_obs": 30,
              "min_features": 2, "names_per_date_floor": 3, "min_side_obs": 5}
    universe = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    root.mkdir(parents=True, exist_ok=True)
    ledger = root / "momentum_artifact_ledger.jsonl"
    for i, (cutoff, _appended, _scores) in enumerate(entries):
        artifact = mm.train_momentum_artifact(
            cutoff, universe, params, readers=_Readers(universe, cutoff, seed=7 + i))
        dated = root / cutoff / "momentum_residual_v0.json"
        dated.parent.mkdir(parents=True, exist_ok=True)
        dated.write_text(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n",
                         encoding="utf-8")
        mm.append_to_artifact_ledger(artifact, ledger)
    # reseal appended_at to the requested timeline
    rows = [json.loads(l) for l in ledger.read_text().strip().splitlines()]
    prev = None
    for r, (_c, appended, _s2) in zip(rows, entries):
        r["appended_at_utc"] = appended
        r["prev_row_sha"] = prev
        r["row_sha"] = row_sha256_of(r)
        prev = r["row_sha"]
    ledger.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
                      encoding="utf-8")
    return ledger


def _mom_scores(ledger: Path, cutoff: str) -> dict:
    dated = ledger.parent / cutoff / "momentum_residual_v0.json"
    art = json.loads(dated.read_text())
    return {t: float(v) for t, v in art["scores"].items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


UNIVERSE = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


def _standard_world(tmp_path: Path, *, blend_beats_prod: bool = True,
                    mom_entries=None, decoy_runs: int = 0,
                    decoy_scores=None):
    """A fully-covered synthetic world over the momentum trainer's universe.
    Winners DDD/EEE (+1%), losers AAA/BBB (-1%), CCC/FFF flat."""
    prod_scores, blend_scores, fwd = {}, {}, {}
    for sess in SESSIONS:
        fwd[sess] = {"AAA": -0.01, "BBB": -0.01, "CCC": 0.0,
                     "DDD": 0.01, "EEE": 0.01, "FFF": 0.0}
        prod_scores[sess] = {"AAA": 6.0, "BBB": 5.0, "CCC": 4.0,
                             "DDD": 3.0, "EEE": 2.0, "FFF": 1.0}
        blend_scores[sess] = ({"DDD": 6.0, "EEE": 5.0, "CCC": 4.0,
                               "AAA": 3.0, "BBB": 2.0, "FFF": 1.0}
                              if blend_beats_prod else dict(prod_scores[sess]))
    prod_db = tmp_path / "prod.db"
    _mk_runs_db(prod_db, prod_scores, decoy_runs=decoy_runs, decoy_scores=decoy_scores)
    blend_db = tmp_path / "blend.db"; _mk_runs_db(blend_db, blend_scores)
    fwd_db = tmp_path / "fwd.db"; _mk_fwd_db(fwd_db, fwd)
    entries = mom_entries or [("2026-08-28", "2026-08-28T12:00:00+00:00", {})]
    ledger = _mk_momentum(tmp_path / "momentum", entries)
    return prod_db, blend_db, ledger, fwd_db


def _expected_mom_basket(ledger: Path, cutoff: str) -> list[str]:
    scores = {t: v for t, v in _mom_scores(ledger, cutoff).items() if t in set(UNIVERSE)}
    return [t for t, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]


def test_positive_control_promote_interest(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    assert rep["coverage_ok"] is True
    assert rep["matched_pairs"]["blend_vs_prod"]["n"] == 20
    assert rep["matched_pairs"]["blend_vs_prod"]["mean_diff"] > 0
    assert rep["verdict"] == "PROMOTE-INTEREST"
    expected = _expected_mom_basket(ledger, "2026-08-28")
    for rec in rep["per_session"]:
        ident = rec["momentum_serving_identity"]
        assert {"row_index", "row_sha", "artifact_content_sha256"} <= set(ident)
        assert rec["momentum_basket"] == expected


def test_canonical_run_selection_ignores_decoys(tmp_path):
    """[codex on orch#783 item 3] holding-only decoy runs AND a
    candidate-carrying decoy with a LOWER run_id must not perturb the
    canonical selection (lexicographically-last candidate-carrying run)."""
    decoy = {"FFF": 99.0, "CCC": 98.0, "AAA": 97.0}   # would flip the basket
    prod_db, blend_db, ledger, fwd_db = _standard_world(
        tmp_path, decoy_runs=3, decoy_scores=decoy)
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    first = rep["per_session"][0]
    assert first["prod_basket"] == ["AAA", "BBB", "CCC"]   # canonical run only
    assert rep["verdict"] == "PROMOTE-INTEREST"


def test_first_coverage_miss_extends_second_closes(tmp_path):
    """[codex on orch#783 item 1] the frozen two-phase rule: first
    20-session coverage miss -> EXTEND; with the extension already used ->
    INSUFFICIENT RECORD."""
    prod_db, blend_db, _l, fwd_db = _standard_world(tmp_path)
    # momentum ledger appended AFTER every session cutoff -> zero coverage
    late = _mk_momentum(tmp_path / "mom-late",
                        [("2026-09-25", "2026-09-25T12:00:00+00:00", {})])
    rep1 = s2.run_readout(SESSIONS, prod_db, blend_db, late, fwd_db, CUTOFFS)
    assert rep1["coverage_ok"] is False
    assert rep1["verdict"] == "EXTEND"
    rep2 = s2.run_readout(SESSIONS, prod_db, blend_db, late, fwd_db, CUTOFFS,
                          extension_used=True)
    assert rep2["verdict"] == "INSUFFICIENT RECORD — no promotion interest"
    # and a winning blend NEVER promotes through a coverage miss in either phase
    assert rep1["matched_pairs"]["blend_vs_prod"]["mean_diff"] > 0


def test_time_safe_selection_ignores_late_appended_rows(tmp_path):
    """AMENDMENT 1 hardened rule, now THROUGH the pipeline loader: a row
    appended after a session's cutoff must not serve that session."""
    prod_db, blend_db, _l, fwd_db = _standard_world(tmp_path)
    ledger = _mk_momentum(tmp_path / "mom2", [
        ("2026-08-28", "2026-08-28T12:00:00+00:00", {}),
        ("2026-08-29", "2026-09-10T12:00:00+00:00", {}),   # appended mid-window
    ])
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    first = next(r for r in rep["per_session"] if r["session"] == "2026-09-01")
    later = next(r for r in rep["per_session"] if r["session"] == "2026-09-15")
    assert first["momentum_serving_identity"]["row_index"] == 0
    assert first["momentum_basket"] == _expected_mom_basket(ledger, "2026-08-28")
    assert later["momentum_serving_identity"]["row_index"] == 1
    assert later["momentum_basket"] == _expected_mom_basket(ledger, "2026-08-29")


def test_broken_chain_counts_as_coverage_miss(tmp_path):
    """The provider loader's None mapping: a corrupted ledger chain makes
    every session a momentum miss -> two-phase coverage handling."""
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    rows = [json.loads(l) for l in ledger.read_text().strip().splitlines()]
    rows[0]["cutoff_date"] = "2099-01-01"   # edited without resealing
    ledger.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
                      encoding="utf-8")
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    assert rep["missing"]["momentum"] == 20
    assert rep["verdict"] == "EXTEND"


def test_placebo_is_deterministic_and_seeded(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    r1 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    r2 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    b1 = [rec["placebo_basket"] for rec in r1["per_session"]]
    assert b1 == [rec["placebo_basket"] for rec in r2["per_session"]]
    assert len({tuple(b) for b in b1}) > 1


def test_window_size_is_enforced(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    import pytest
    with pytest.raises(SystemExit, match="exactly 20"):
        s2.run_readout(SESSIONS[:5], prod_db, blend_db, ledger, fwd_db, CUTOFFS)
