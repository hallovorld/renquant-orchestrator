"""Tests for the read-only renquant105 trend-signal DIAGNOSTIC (synthetic ledger, no network).

The study reads ONLY the decision ledger (candidate_scores + ticker_forward_returns +
pipeline_runs) — it trains no model and never writes to a canonical path. These tests build a
tiny synthetic SQLite ledger and assert that:
  * the rank-IC reads a planted monotone signal,
  * the data-INSUFFICIENCY gate forces ``bottleneck_verdict == UNDETERMINED`` and emits NO
    lever ranking (the central review fix),
  * sufficiency is measured in EFFECTIVE NON-OVERLAPPING BLOCKS, not raw dates,
  * the killed-winner split is reported across a sensitivity grid and labelled non-causal,
  * an immutable input manifest (DB sha256, resolved runs, scorer mix, deterministic tie
    rejection) is emitted,
  * the on-cohort shuffled-label placebo runs,
  * the missing-DB path is a clean CI skip (exit 0).
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sqlite3
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rtsb", Path(__file__).resolve().parent.parent / "scripts" / "research_trend_signal_baseline.py")
rtsb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rtsb)


def _sessions_after(start: _dt.date, n: int):
    out, d = [], start
    while len(out) < n:
        d = d + _dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def _mk_ledger(path: Path, *, n_dates: int, n_names: int = 20, run_type: str = "live",
               start: _dt.date = _dt.date(2024, 1, 1), trailing_sessions: int = 80,
               signal: bool = True):
    """A ledger where, on each date, mu is monotone in the realized fwd_20d (planted signal)
    when ``signal`` is True. ``trailing_sessions`` extra forward-return rows extend the session
    calendar so the 20-session horizon ages.
    """
    con = sqlite3.connect(str(path))
    con.execute("create table pipeline_runs (run_id text, run_date date, run_type text)")
    con.execute(
        "create table candidate_scores (run_id text, ticker text, raw_score real, mu real, "
        "selected integer, blocked_by text, model_type text, active_scorer text)")
    con.execute(
        "create table ticker_forward_returns (as_of_date date, ticker text, "
        "fwd_5d real, fwd_10d real, fwd_20d real, fwd_60d real)")
    dates = [d for d in _sessions_after(start, n_dates)]
    last = dates[-1]
    for i, d in enumerate(dates):
        rid = f"{run_type}-{d.isoformat()}"
        con.execute("insert into pipeline_runs values (?,?,?)", (rid, d.isoformat(), run_type))
        for j in range(n_names):
            mu = (j - n_names / 2) / (n_names * 5.0)  # spread around 0
            fwd = (j / n_names - 0.5) * 0.2 if signal else ((n_names - j) / n_names - 0.5) * 0.2
            # name the top few as "selected" so the deployed-selection summary has signal
            selected = 1 if j >= n_names - 3 else 0
            con.execute(
                "insert into candidate_scores values (?,?,?,?,?,?,?,?)",
                (rid, f"T{j}", mu * 10, mu, selected, None, "hf_patchtst", "hf_patchtst"))
            con.execute(
                "insert into ticker_forward_returns values (?,?,?,?,?,?)",
                (d.isoformat(), f"T{j}", fwd, fwd, fwd, fwd))
    for s in _sessions_after(last, trailing_sessions):
        con.execute("insert into ticker_forward_returns values (?,?,?,?,?,?)",
                    (s.isoformat(), "FILLER", 0.0, 0.0, 0.0, 0.0))
    con.commit()
    con.close()


def test_rank_ic_reads_planted_signal(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=160, signal=True)  # ~8 effective fwd_20d blocks
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_eff_blocks=6, min_xsec=10,
                        as_of="2025-06-30")
    ic = res["live"]["ic"]["fwd_20d"]["mu"]
    assert ic["n_dates"] >= 30
    assert ic["mean_ic"] > 0.5  # strong planted monotone signal


def test_inverted_signal_negative_ic(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=False)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_eff_blocks=6, min_xsec=10,
                        as_of="2024-12-31")
    ic = res["live"]["ic"]["fwd_20d"]["mu"]
    assert ic["mean_ic"] < 0  # inverted ranking -> negative IC


def test_insufficiency_forces_undetermined_and_no_lever_ranking(tmp_path):
    """The central review fix: when the LIVE primary horizon is below the effective-block bar,
    the verdict MUST be UNDETERMINED and NO lever ranking may be emitted."""
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=12, signal=True)  # ~0.6 effective fwd_20d blocks << 6
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_eff_blocks=6, min_xsec=10,
                        as_of="2024-12-31")
    assert res["data_sufficiency"]["verdict"] == "INSUFFICIENT_LIVE_HISTORY"
    assert res["bottleneck_verdict"] == "UNDETERMINED"
    assert res["lever_ranking"] is None  # gate must suppress any ranking
    assert res["live"]["sufficient"] is False
    assert res["live"]["primary_eff_blocks"] < 6


def test_sufficiency_uses_effective_blocks_not_raw_dates(tmp_path):
    """30 raw overlapping dates ~ 1.5 effective blocks -> still INSUFFICIENT/UNDETERMINED."""
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=50, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_eff_blocks=6, min_xsec=10,
                        as_of="2024-12-31")
    # ~30 aged dates but only ~1.5 effective fwd_20d blocks -> not sufficient
    assert res["live"]["primary_aged_dates"] >= 20
    assert res["live"]["primary_eff_blocks"] < 6
    assert res["bottleneck_verdict"] == "UNDETERMINED"


def test_killed_winner_sensitivity_and_noncausal_label(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_eff_blocks=6, min_xsec=10,
                        as_of="2024-12-31")
    sens = res["live"]["killed_sensitivity"]
    assert len(sens["grid"]) >= 1
    assert "k-dependent" in sens["note"].lower()
    # descriptive recall/precision plus naive baselines are present
    t = res["live"]["trend"]["fwd_20d"]
    assert t["recall_topk"] is not None and t["recall_random"] is not None
    assert t["prec_topk_pos"] is not None and t["prec_market_sign"] is not None


def test_manifest_is_immutable_and_complete(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_eff_blocks=6, min_xsec=10,
                        as_of="2024-12-31")
    man = res["manifest"]
    assert len(man["db_sha256"]) == 64
    assert man["schema_version"] >= 0
    assert man["resolved_runs"]  # per-date run ids persisted
    assert "live_scorer_mix" in man
    assert "ambiguous_dates_rejected" in man  # deterministic tie handling recorded
    assert man["cli_args"]["min_eff_blocks"] == 6


def test_placebo_runs_on_cohort(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_eff_blocks=6, min_xsec=10,
                        as_of="2024-12-31", placebo_shuffles=50)
    pb = res["live"]["placebo"]["fwd_20d"]
    assert pb["n_shuffles"] > 0
    # planted strong signal -> observed IC should beat the shuffled-label placebo
    assert pb["p_value"] is not None and pb["p_value"] < 0.1


def test_missing_db_is_clean_skip(capsys):
    rc = rtsb.main(["--runs-db", "/tmp/__rtsb_does_not_exist__.db"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out
