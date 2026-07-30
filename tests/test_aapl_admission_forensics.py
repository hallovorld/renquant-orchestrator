"""Behavioural tests for scripts/aapl_admission_forensics.py.

Written for the PR #614 follow-up correction. The merged note claimed AAPL was
above the cross-sectional median on "12 of 13" sessions and that the recomputed
floor matched the logged floor "15/15"; re-running the extraction gives 11/13
and 13/13. The root cause was that the note's §0 aggregate window (2026-07-06
onward) and its §2 funnel table (2026-07-08 onward) were different windows, so
the two sessions where AAPL was BELOW the median (07-06, 07-07) were counted in
the denominator but missing from the table.

These tests drive the extraction on synthetic fixtures whose answers are known
by construction, so they fail if the aggregation logic over- or under-counts.
They deliberately do not grep the script's source text: an off-by-one in
``summarize`` would pass a text check and fail here.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import aapl_admission_forensics as forensics  # noqa: E402

FLOOR_LINE = (
    "2026-07-28 10:54:27,086 [INFO] kernel.panel_pipeline.scoring: VetoWeakBuysTask: "
    "dropped {dropped} candidate(s) below rank_score floor=max(min=0.20, "
    "mean+1.00*std={floor}) = {floor}  (n={n})"
)
MU_LINE = (
    "2026-07-28 10:54:28,000 [INFO] kernel.panel_pipeline.scoring: ConvictionGateTask: "
    "dropped {dropped} candidate(s) (mu_floor={mu_floor})"
)


def _make_db(path: Path, runs: dict[str, tuple[str, list[tuple[str, float, float]]]]) -> None:
    """runs: run_id -> (run_date, [(ticker, rank_score, mu), ...])."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, run_date DATE NOT NULL)")
    conn.execute(
        "CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT, "
        "rank_score REAL, mu REAL)"
    )
    for run_id, (run_date, rows) in runs.items():
        conn.execute("INSERT INTO pipeline_runs VALUES (?,?)", (run_id, run_date))
        for ticker, rs, mu in rows:
            conn.execute(
                "INSERT INTO candidate_scores VALUES (?,?,?,?,?)", (run_id, ticker, "candidate", rs, mu)
            )
    conn.commit()
    conn.close()


def test_recompute_floor_is_mean_plus_k_sigma_with_a_minimum():
    # mean of 0.1..0.5 = 0.30, sample stdev = 0.1581139 -> floor 0.4581139
    scores = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert forensics.recompute_floor(scores, min_floor=0.20, std_mult=1.0) == pytest.approx(0.4581139, abs=1e-7)
    # the min_floor clamps when mean+kσ falls below it
    assert forensics.recompute_floor([0.01, 0.02, 0.03], min_floor=0.20, std_mult=1.0) == 0.20
    # std_mult scales the band
    assert forensics.recompute_floor(scores, 0.0, 2.0) > forensics.recompute_floor(scores, 0.0, 1.0)


def test_parse_log_takes_the_last_gate_lines_when_a_date_has_several_runs(tmp_path):
    """2026-07-28 really had three live runs; the day's decision is the last one."""
    log = tmp_path / "2026-07-28.log"
    log.write_text(
        "\n".join(
            [
                FLOOR_LINE.format(dropped=59, floor="0.528", n=77),
                MU_LINE.format(dropped=18, mu_floor="0.03"),
                FLOOR_LINE.format(dropped=64, floor="0.532", n=78),
                MU_LINE.format(dropped=12, mu_floor="0.03"),
            ]
        )
    )
    facts = forensics.parse_log(log)
    assert facts is not None
    assert facts.floor == 0.532, "must take the LAST floor line, not the first"
    assert facts.n == 78
    assert facts.min_floor == 0.20
    assert facts.std_mult == 1.0
    assert facts.mu_floor == 0.03


def test_parse_log_returns_none_when_the_run_never_gated_buys(tmp_path):
    log = tmp_path / "2026-07-17.log"
    log.write_text("=== daily_104 started ===\nFATAL: on 'feat/x' (expected main) — aborting\n")
    assert forensics.parse_log(log) is None


def test_pin_run_selects_the_run_whose_candidate_count_matches_the_logged_n(tmp_path):
    """The logged n is the runtime evidence that pins WHICH run gated that day."""
    db = tmp_path / "runs.alpaca.db"
    _make_db(
        db,
        {
            # 77 rows -- the earlier run of the day
            "2026-07-28-live-be8ee266": ("2026-07-28", [(f"T{i}", 0.4 + i / 1000, 0.01) for i in range(77)]),
            # 78 rows -- the run the last log line reports
            "2026-07-28-live-5b859fff": ("2026-07-28", [(f"T{i}", 0.4 + i / 1000, 0.01) for i in range(78)]),
            # a sim run on the same date must never be picked
            "2026-07-28-sim-deadbeef": ("2026-07-28", [(f"T{i}", 0.4 + i / 1000, 0.01) for i in range(78)]),
        },
    )
    conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    try:
        assert forensics.pin_run(conn, "2026-07-28", 78) == "2026-07-28-live-5b859fff"
        assert forensics.pin_run(conn, "2026-07-28", 77) == "2026-07-28-live-be8ee266"
        assert forensics.pin_run(conn, "2026-07-28", 99) is None
    finally:
        conn.close()


def _one_session(tmp_path, date, rows, floor, mu_floor="0.03"):
    db = tmp_path / f"runs-{date}.db"
    _make_db(db, {f"{date}-live-abc": (date, rows)})
    log = tmp_path / f"{date}.log"
    log.write_text(
        FLOOR_LINE.format(dropped=0, floor=floor, n=len(rows))
        + "\n"
        + MU_LINE.format(dropped=0, mu_floor=mu_floor)
    )
    conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    try:
        facts = forensics.parse_log(log)
        return forensics.session_metrics(conn, facts, f"{date}-live-abc", "AAPL")
    finally:
        conn.close()


def test_session_metrics_flags_a_below_median_session_as_below(tmp_path):
    """The exact defect being corrected: 07-06/07-07 were BELOW the median.

    AAPL at 0.30 against a five-name cross-section whose median is 0.40.
    """
    rows = [("AAPL", 0.30, 0.009), ("B", 0.10, 0.0), ("C", 0.40, 0.0), ("D", 0.50, 0.05), ("E", 0.60, 0.05)]
    m = _one_session(tmp_path, "2026-07-06", rows, floor="0.550")
    assert m.above_median is False
    assert m.median_rank_score == 0.40
    assert m.ticker_rank == 4  # descending 0.60, 0.50, 0.40, 0.30 -> AAPL is 4th of 5
    assert m.ticker_percentile == 20.0  # exactly one of five names scores below AAPL


def test_session_metrics_counts_admitted_and_both_gate_survivors(tmp_path):
    rows = [
        ("AAPL", 0.30, 0.009),  # below floor, below mu
        ("B", 0.60, 0.01),  # above floor, below mu
        ("C", 0.70, 0.05),  # above floor, above mu -> both
        ("D", 0.80, None),  # above floor, mu missing -> not both
    ]
    m = _one_session(tmp_path, "2026-07-20", rows, floor="0.550")
    assert m.admitted == 3
    assert m.admitted_and_mu == 1
    assert m.above_median is False


def test_summarize_does_not_over_count_above_median_sessions(tmp_path):
    """Regression guard for the merged note's 12-of-13.

    Thirteen sessions, of which exactly two are below the median, must summarize
    as 11 -- not 12, and not 13.
    """
    below = [("AAPL", 0.30, 0.009), ("B", 0.10, 0.0), ("C", 0.40, 0.0), ("D", 0.50, 0.05), ("E", 0.60, 0.05)]
    above = [("AAPL", 0.55, 0.009), ("B", 0.10, 0.0), ("C", 0.40, 0.0), ("D", 0.50, 0.05), ("E", 0.60, 0.05)]
    sessions = [_one_session(tmp_path, f"2026-07-{d:02d}", below, "0.900") for d in (6, 7)]
    sessions += [_one_session(tmp_path, f"2026-07-{d:02d}", above, "0.900") for d in range(10, 21)]
    assert len(sessions) == 13
    r = forensics.summarize(sessions)
    assert r["scored_sessions"] == 13
    assert r["above_median"] == 11
    assert r["floor_match"] == 0  # logged 0.900 is deliberately not the recomputed value
    assert r["mu_floors"] == [0.03]


def test_sitting_exactly_on_the_median_does_not_count_as_above_it(tmp_path):
    """"Above the median" must be strict: a name AT the median is not above it.

    Without this, a tie inflates the above-median tally -- the same direction of
    error as the merged note's 12-of-13.
    """
    rows = [("AAPL", 0.40, 0.009), ("B", 0.10, 0.0), ("C", 0.40, 0.0), ("D", 0.50, 0.05), ("E", 0.60, 0.05)]
    m = _one_session(tmp_path, "2026-07-22", rows, floor="0.900")
    assert m.median_rank_score == 0.40
    assert m.above_median is False


def test_summarize_ignores_sessions_where_the_ticker_was_not_scored(tmp_path):
    """A session AAPL never reached must not inflate either side of the ratio."""
    scored = [("AAPL", 0.55, 0.05), ("B", 0.10, 0.0), ("C", 0.40, 0.0)]
    unscored = [("B", 0.10, 0.0), ("C", 0.40, 0.0), ("D", 0.50, 0.0)]
    sessions = [
        _one_session(tmp_path, "2026-07-20", scored, "0.900"),
        _one_session(tmp_path, "2026-07-21", unscored, "0.900"),
    ]
    r = forensics.summarize(sessions)
    assert r["scored_sessions"] == 1
    assert r["above_median"] == 1


def test_pin_run_FAILS_CLOSED_when_two_runs_share_the_logged_n(tmp_path):
    """The regression codex caught.

    `matches[-1]` with no ORDER BY picked an arbitrary run when two live runs
    on one date shared a candidate count — SQLite does not guarantee GROUP BY
    order — while the note claimed the session was pinned by runtime evidence.
    Not theoretical: 2026-07-28 has three live runs carrying candidate scores
    on the real DB, with differing AAPL values.
    """
    db = tmp_path / "runs.alpaca.db"
    _make_db(
        db,
        {
            "2026-07-28-live-aaaaaaaa": ("2026-07-28", [(f"T{i}", 0.4 + i / 1000, 0.01) for i in range(78)]),
            "2026-07-28-live-bbbbbbbb": ("2026-07-28", [(f"T{i}", 0.5 + i / 1000, 0.02) for i in range(78)]),
        },
    )
    conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    try:
        with pytest.raises(forensics.AmbiguousRunError) as ei:
            forensics.pin_run(conn, "2026-07-28", 78)
        msg = str(ei.value)
        assert "2 live runs" in msg
        # both candidates named, so the reader can disambiguate by hand
        assert "aaaaaaaa" in msg and "bbbbbbbb" in msg
    finally:
        conn.close()


def test_pin_run_is_deterministic_across_row_order(tmp_path):
    """A unique match must resolve identically regardless of insertion order."""
    def build(order):
        db = tmp_path / f"runs_{order[0][-4:]}.alpaca.db"
        _make_db(db, {rid: ("2026-07-28", [(f"T{i}", 0.4 + i / 1000, 0.01) for i in range(n)])
                      for rid, n in order})
        return db
    a = build([("2026-07-28-live-be8ee266", 77), ("2026-07-28-live-5b859fff", 78)])
    b = build([("2026-07-28-live-5b859fff", 78), ("2026-07-28-live-be8ee266", 77)])
    for db in (a, b):
        conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
        try:
            assert forensics.pin_run(conn, "2026-07-28", 78) == "2026-07-28-live-5b859fff"
        finally:
            conn.close()
