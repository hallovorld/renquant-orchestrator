"""Tests for the read-only renquant105 trend-signal DIAGNOSTIC (synthetic ledger, no network).

The study reads ONLY the decision ledger (candidate_scores + ticker_forward_returns +
pipeline_runs) — it trains no model and never writes to a canonical path. These tests build a
tiny synthetic SQLite ledger and assert that:
  * the rank-IC reads a planted monotone signal,
  * ``bottleneck_verdict`` is ``UNDETERMINED`` UNCONDITIONALLY and ``lever_ranking`` is ALWAYS
    null — even with a large, "sufficient" overlap-ratio (the round-2 central fix),
  * sufficiency is described by a conservative OVERLAP-RATIO (not power/N_eff) that can at most
    unlock IC descriptives, never a model-vs-gate ranking,
  * the killed-winner split is reported across a sensitivity grid and labelled non-causal,
  * an immutable input manifest (DB sha256, resolved runs, scorer mix, deterministic tie
    rejection, as-of run filter) is emitted,
  * the dependence-preserving on-cohort placebo runs only on the faithful LIVE cohort and its
    p-value is in (0, 1] — never 0,
  * baselines are IMPLEMENTED (analytic random k/n + current-selected-book) and follow-ups are
    distinguished from implemented,
  * the as-of filter excludes later-dated runs from provenance surfaces,
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
    when ``signal`` is True. To exercise the DEPENDENCE-PRESERVING placebo, the per-name
    score/return mapping is ROTATED by a per-date offset so the cross-section varies across
    dates (a circular date-shift mis-pairs them) while the within-date monotone link holds.
    ``trailing_sessions`` extra forward-return rows extend the session calendar so the
    20-session horizon ages.
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
            rank = (j + i) % n_names  # per-date rotation -> cross-section varies across dates
            mu = (rank - n_names / 2) / (n_names * 5.0)  # spread around 0
            fwd = ((rank / n_names - 0.5) * 0.2 if signal
                   else ((n_names - rank) / n_names - 0.5) * 0.2)
            # name the top-ranked few as "selected" so the deployed-selection summary has signal
            selected = 1 if rank >= n_names - 3 else 0
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
    _mk_ledger(db, n_dates=160, signal=True)  # large overlap-ratio
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2025-06-30")
    ic = res["live"]["ic"]["fwd_20d"]["mu"]
    assert ic["n_dates"] >= 30
    assert ic["mean_ic"] > 0.5  # strong planted monotone signal
    assert "overlap_ratio" in ic  # renamed from eff_blocks


def test_inverted_signal_negative_ic(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=False)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2024-12-31")
    ic = res["live"]["ic"]["fwd_20d"]["mu"]
    assert ic["mean_ic"] < 0  # inverted ranking -> negative IC


def test_verdict_undetermined_unconditional_and_never_a_lever_ranking(tmp_path):
    """Round-2 central fix: the verdict is UNDETERMINED UNCONDITIONALLY and ``lever_ranking``
    is ALWAYS null — even when the overlap-ratio is large enough to 'unlock' IC descriptives.
    There is NO code path that flips the verdict or emits a model-vs-gate ranking."""
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=200, signal=True)  # very large overlap-ratio, well past the bar
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2025-09-30")
    # the overlap-ratio clears the bar (IC descriptives unlocked) ...
    assert res["live"]["primary_overlap_ratio"] >= 6
    assert res["live"]["ic_descriptives_unlocked"] is True
    # ... yet the verdict is STILL UNDETERMINED and NO lever ranking is produced.
    assert res["bottleneck_verdict"] == "UNDETERMINED"
    assert res["data_sufficiency"]["verdict"] == "UNDETERMINED_UNCONDITIONAL"
    assert res["lever_ranking"] is None
    # the script no longer exposes a lever-ranking builder at all
    assert not hasattr(rtsb, "_lever_ranking")


def test_insufficiency_also_undetermined_no_lever_ranking(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=12, signal=True)  # tiny overlap-ratio
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2024-12-31")
    assert res["bottleneck_verdict"] == "UNDETERMINED"
    assert res["lever_ranking"] is None
    assert res["live"]["ic_descriptives_unlocked"] is False
    assert res["live"]["primary_overlap_ratio"] < 6


def test_overlap_ratio_is_descriptor_not_power(tmp_path):
    """The sufficiency descriptor is a conservative OVERLAP-RATIO (n_dates/horizon), renamed
    away from 'eff_blocks'/'power'/'N_eff'; #201 must consume the same criterion."""
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=50, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2024-12-31")
    assert "primary_overlap_ratio" in res["live"]
    assert "eff_blocks" not in res["live"]
    note = res["overlap_ratio_unblock_note"].lower()
    assert "overlap-ratio" in note and "#201" in note and "no calendar date" in note
    assert "power" in note or "min" in note  # references the real pre-registered unblock


def test_killed_winner_sensitivity_and_baselines(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2024-12-31")
    sens = res["live"]["killed_sensitivity"]
    assert len(sens["grid"]) >= 1
    assert "k-dependent" in sens["note"].lower()
    # IMPLEMENTED baselines: analytic random k/n + current-selected-book + market-sign
    t = res["live"]["trend"]["fwd_20d"]
    assert t["recall_topk"] is not None and t["recall_random"] is not None
    assert t["recall_selected_book"] is not None  # current-selected-book baseline implemented
    assert t["prec_topk_pos"] is not None and t["prec_market_sign"] is not None
    # report distinguishes implemented baselines from required follow-ups
    assert any("random" in b for b in t["baselines_implemented"])
    assert any("simple-momentum" in b for b in t["baselines_followups_NOT_implemented"])


def test_random_recall_is_analytic_kn(tmp_path):
    """The random-recall baseline is the analytic k/n expectation (no Monte-Carlo noise):
    two runs are identical, and the value matches book_size / mean_names."""
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, n_names=20, signal=True)
    r1 = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                       as_of="2024-12-31")["live"]["trend"]["fwd_20d"]
    r2 = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                       as_of="2024-12-31")["live"]["trend"]["fwd_20d"]
    assert r1["recall_random"] == r2["recall_random"]  # deterministic, no seed noise
    assert abs(r1["recall_random"] - (8 / r1["mean_names"])) < 1e-9


def test_manifest_is_immutable_and_complete(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2024-12-31")
    man = res["manifest"]
    assert len(man["db_sha256"]) == 64
    assert man["schema_version"] >= 0
    assert man["resolved_runs"]  # per-date run ids persisted
    assert "live_scorer_mix" in man
    assert "ambiguous_dates_rejected" in man  # deterministic tie handling recorded
    assert man["cli_args"]["min_overlap_ratio"] == 6
    assert man["runs_filtered_to_run_date_le_as_of"] is True


def test_as_of_excludes_later_dated_runs_from_provenance(tmp_path):
    """An as-of rerun must NOT surface later-dated runs in provenance/summary surfaces."""
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=60, signal=True, start=_dt.date(2024, 1, 1))
    early = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                          as_of="2024-02-15")
    full = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                         as_of="2025-12-31")
    # every resolved run in the early as-of must be <= the as-of date
    assert all(rr["date"] <= "2024-02-15" for rr in early["manifest"]["resolved_runs"])
    # the later run resolves strictly more runs -> the as-of filter is doing real work
    assert len(early["manifest"]["resolved_runs"]) < len(full["manifest"]["resolved_runs"])


def test_placebo_preserves_dependence_pvalue_never_zero_live_only(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=120, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_overlap_ratio=6, min_xsec=10,
                        as_of="2025-06-30", placebo_shuffles=50)
    pb = res["live"]["placebo"]["fwd_20d"]
    assert pb["n_shuffles"] > 0
    # finite-MC p = (exceedances+1)/(B+1) is strictly in (0, 1] -> NEVER 0
    assert pb["p_value"] is not None and 0 < pb["p_value"] <= 1
    # strong planted signal -> observed IC beats the dependence-preserving placebo
    assert pb["p_value"] < 0.2
    # placebo is NOT run on the unfaithful SIM cohort
    sim_pb = res["sim_reference_NOT_validation_grade"]["placebo"]["fwd_20d"]
    assert sim_pb["n_shuffles"] == 0
    assert sim_pb["p_value"] is None


def test_missing_db_is_clean_skip(capsys):
    rc = rtsb.main(["--runs-db", "/tmp/__rtsb_does_not_exist__.db"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out
