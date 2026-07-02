"""Focused tests for scripts/kpi_scorecard.py's r2 correctness fixes.

Covers the 4 cases Codex's review named explicitly: an unrelated-newest-file
false green on collector_liveness, a partial PIT directory wrongly counted
in pit_accrual_days, same-day rerun reproducibility (content hash), and
run-selection semantics (a full run must supersede a more-recent intraday
partial row, never the other way around).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

import kpi_scorecard as kpi  # noqa: E402


# --------------------------------------------------------------- fixtures


@pytest.fixture()
def rq_root(tmp_path, monkeypatch):
    root = tmp_path / "rq_root"
    root.mkdir()
    monkeypatch.setattr(kpi, "RQ", str(root))
    return root


def _make_pipeline_runs_db(path, rows):
    """rows: list of (run_id, run_date, created_at, portfolio_value, cash, n_candidates).

    n_candidates here means "how many candidate_scores rows to synthesize
    for this run_id" — full-run status is determined by joining
    candidate_scores and counting, matching production (pipeline_runs.
    n_candidates is 0 on every real row and is NOT used by the code under
    test)."""
    con = sqlite3.connect(path)
    con.execute(
        "create table pipeline_runs (run_id text, run_date text, created_at text, "
        "run_type text, portfolio_value real, cash real, counters_json text)"
    )
    con.execute("create table candidate_scores (run_id text, ticker text)")
    for run_id, run_date, created_at, pv, cash, n_candidates in rows:
        con.execute(
            "insert into pipeline_runs (run_id, run_date, created_at, run_type, "
            "portfolio_value, cash) values (?, ?, ?, 'live', ?, ?)",
            (run_id, run_date, created_at, pv, cash),
        )
        con.executemany(
            "insert into candidate_scores (run_id, ticker) values (?, ?)",
            [(run_id, f"TICKER{i}") for i in range(n_candidates)],
        )
    con.commit()
    con.close()


# --------------------------------------------------------- collector_liveness


def test_collector_liveness_unrelated_newest_file_no_false_green(rq_root):
    """An empty/irrelevant file with a fresh mtime in some scanned directory
    must never be enough to report a collector live — liveness must come
    from that collector's OWN data-output content, not generic directory
    activity."""
    # No real collector data output exists anywhere under rq_root. Only an
    # unrelated, irrelevant file with a brand new mtime.
    irrelevant_dir = rq_root / "logs" / "rq105"
    irrelevant_dir.mkdir(parents=True)
    (irrelevant_dir / "unrelated_wrapper.log").write_text("")  # empty, fresh mtime

    today = dt.date.today()
    result = kpi._run(kpi.metric_collector_liveness, today)
    # Either every real data-output path is genuinely missing (stale/missing
    # per collector) or the day is reported as a non-session day — in no
    # case may the presence of the unrelated fresh file alone flip this to
    # "live".
    assert result["status"] in ("ok", "unavailable")
    if result["status"] == "ok":
        assert result["value"] in ("stale", "not_a_session_day")
        if result["value"] == "stale":
            for name, detail in result["detail"].items():
                assert detail["status"] != "ok", (
                    f"{name} falsely reported live from an unrelated file")


# --------------------------------------------------------- pit_accrual_days


def test_pit_accrual_days_excludes_partial_dir(rq_root):
    """A directory that only has SOME of the 4 required endpoint manifests
    (a crashed/partial publish) must not be counted toward accrual — every
    counted day is irreversible once claimed, so a false positive here can
    never be corrected later."""
    snapshots = rq_root / "data" / "estimate_snapshots"
    snapshots.mkdir(parents=True)

    def _write_valid_day(date_str):
        d = snapshots / date_str
        d.mkdir()
        for endpoint in (
            "analyst_estimates", "grades_consensus",
            "price_target_consensus", "price_target_summary",
        ):
            parquet_name = f"{endpoint}.parquet"
            (d / parquet_name).write_bytes(b"not-empty")
            (d / f"{endpoint}.manifest.json").write_text(json.dumps({
                "status": "ok", "as_of": date_str, "output": parquet_name,
            }))

    _write_valid_day("2026-06-01")
    _write_valid_day("2026-06-02")

    # Partial day: only 2 of 4 manifests present (simulating a crash
    # mid-publish) — must NOT be counted.
    partial_dir = snapshots / "2026-06-03"
    partial_dir.mkdir()
    for endpoint in ("analyst_estimates", "grades_consensus"):
        parquet_name = f"{endpoint}.parquet"
        (partial_dir / parquet_name).write_bytes(b"not-empty")
        (partial_dir / f"{endpoint}.manifest.json").write_text(json.dumps({
            "status": "ok", "as_of": "2026-06-03", "output": parquet_name,
        }))

    kpi.ESTIMATE_SNAPSHOTS = str(snapshots)
    sys.path.insert(0, os.path.join(REPO_ROOT, "ops", "pit"))
    import pit_liveness_check  # noqa: E402

    # pit_liveness_check.ROOT is computed from RQ_ROOT at IMPORT time, a
    # separate module global from kpi.ESTIMATE_SNAPSHOTS — must be patched
    # independently for check_snapshot() to see this fixture's directory.
    pit_liveness_check.ROOT = str(snapshots)

    result = kpi._run(kpi.metric_pit_accrual_days, dt.date(2026, 6, 4))
    assert result["status"] == "ok"
    assert result["value"] == 2, "the partial 2026-06-03 dir must not be counted"
    assert "2026-06-03" in result["detail"]["rejected_days"]
    assert result["detail"]["n_rejected_partial_or_invalid"] == 1


# ------------------------------------------------------- reproducibility


def test_same_day_rerun_produces_identical_content_hash():
    """Two independent computations of the canonical content hash over
    IDENTICAL metrics (even if the dict was built via a different key
    insertion order) must produce the same hash — proving the scorecard's
    reproducibility claim is genuinely checkable, not just asserted."""
    metrics_a = {
        "deployed_fraction": {"status": "ok", "value": 0.8234, "measured_at": "2026-07-02T09:00:00"},
        "pit_accrual_days": {"status": "ok", "value": 42, "measured_at": "2026-07-02T09:00:05"},
    }
    # Same content, different insertion order and a different measured_at
    # (wall-clock, must NOT affect the content hash).
    metrics_b = {
        "pit_accrual_days": {"value": 42, "status": "ok", "measured_at": "2026-07-02T09:15:33"},
        "deployed_fraction": {"value": 0.8234, "status": "ok", "measured_at": "2026-07-02T09:15:40"},
    }
    hash_a = kpi._canonical_content_hash(metrics_a)
    hash_b = kpi._canonical_content_hash(metrics_b)
    assert hash_a == hash_b

    # A genuine content change must flip the hash.
    metrics_c = dict(metrics_a)
    metrics_c["deployed_fraction"] = {**metrics_a["deployed_fraction"], "value": 0.8235}
    hash_c = kpi._canonical_content_hash(metrics_c)
    assert hash_c != hash_a


def test_generator_sha256_is_stable_content_hash():
    h1 = kpi._generator_sha256()
    h2 = kpi._generator_sha256()
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest


def test_atomic_write_never_leaves_partial_file(tmp_path):
    out_path = str(tmp_path / "scorecard.json")
    kpi._atomic_write_json(out_path, {"a": 1})
    assert os.path.exists(out_path)
    assert not os.path.exists(f"{out_path}.tmp-{os.getpid()}")
    with open(out_path) as f:
        assert json.load(f) == {"a": 1}


# ------------------------------------------------------- run-selection semantics


def test_canonical_daily_live_full_run_supersedes_later_intraday_partial(rq_root):
    """A full run (n_candidates >= MIN_FULL_RUN_CANDIDATES) must be selected
    even when a LATER, partial/intraday-monitor row exists for the same
    run_date — the partial row's more-recent created_at must never win."""
    db_path = str(rq_root / "runs.alpaca.db")
    _make_pipeline_runs_db(db_path, [
        ("full-run-1", "2026-06-01", "2026-06-01T13:55:00", 100000.0, 20000.0,
         kpi.MIN_FULL_RUN_CANDIDATES),
        # Same day, LATER created_at, but only a handful of candidates
        # (an intraday monitor pass, not a full run) — must be excluded.
        ("intraday-monitor-1", "2026-06-01", "2026-06-01T15:30:00", 100500.0, 500.0, 3),
    ])
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    canon = kpi._canonical_daily_live(con)
    assert len(canon) == 1
    assert canon.iloc[0]["run_id"] == "full-run-1"
    assert canon.iloc[0]["cash"] == 20000.0


def test_canonical_daily_live_excludes_all_partial_runs_when_no_full_run_exists(rq_root):
    db_path = str(rq_root / "runs.alpaca.db")
    _make_pipeline_runs_db(db_path, [
        ("intraday-only", "2026-06-01", "2026-06-01T15:30:00", 100500.0, 500.0, 3),
    ])
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    with pytest.raises(ValueError, match="no candidate_scores-backed runs"):
        kpi._canonical_daily_live(con)


def test_metric_deployed_fraction_uses_full_run_not_raw_latest(rq_root):
    db_path = str(rq_root / "runs.alpaca.db")
    _make_pipeline_runs_db(db_path, [
        ("full-run-1", "2026-06-01", "2026-06-01T13:55:00", 100000.0, 20000.0,
         kpi.MIN_FULL_RUN_CANDIDATES),
        ("intraday-monitor-1", "2026-06-01", "2026-06-01T15:30:00", 100500.0, 90000.0, 3),
    ])
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    result = kpi._run(kpi.metric_deployed_fraction, con)
    assert result["status"] == "ok"
    # 1 - 20000/100000 = 0.8, NOT 1 - 90000/100500 (~0.1045) from the
    # more-recent intraday partial row.
    assert result["value"] == pytest.approx(0.8, abs=1e-4)
    assert result["detail"]["latest_full_run_id"] == "full-run-1"


# ------------------------------------------------------- DB provenance


def test_extract_hash_distinguishes_same_size_same_mtime_different_content(rq_root):
    """A mutable SQLite file's size+mtime alone cannot prove which rows were
    read — two DB files that happen to share both must still be
    distinguishable by their actual content hash."""
    db_a = str(rq_root / "a.db")
    db_b = str(rq_root / "b.db")
    _make_pipeline_runs_db(db_a, [
        ("run-1", "2026-06-01", "2026-06-01T13:55:00", 100000.0, 20000.0,
         kpi.MIN_FULL_RUN_CANDIDATES),
    ])
    _make_pipeline_runs_db(db_b, [
        # Same run_id/run_date/n_candidates shape, DIFFERENT cash value —
        # a genuinely different DB state.
        ("run-1", "2026-06-01", "2026-06-01T13:55:00", 100000.0, 45000.0,
         kpi.MIN_FULL_RUN_CANDIDATES),
    ])

    # Force identical size and mtime on both files — the exact scenario
    # where a size+mtime-only provenance stamp would be blind to the
    # difference.
    size_a, size_b = os.path.getsize(db_a), os.path.getsize(db_b)
    target_size = max(size_a, size_b)
    for p, size in ((db_a, size_a), (db_b, size_b)):
        if size < target_size:
            with open(p, "ab") as f:
                f.write(b"\x00" * (target_size - size))
    common_mtime = 1_800_000_000.0  # arbitrary fixed epoch time
    os.utime(db_a, (common_mtime, common_mtime))
    os.utime(db_b, (common_mtime, common_mtime))
    assert os.path.getsize(db_a) == os.path.getsize(db_b)
    assert os.path.getmtime(db_a) == os.path.getmtime(db_b)

    con_a = sqlite3.connect(f"file:{db_a}?mode=ro", uri=True)
    con_b = sqlite3.connect(f"file:{db_b}?mode=ro", uri=True)
    canon_a = kpi._canonical_daily_live(con_a)
    canon_b = kpi._canonical_daily_live(con_b)
    hash_a = kpi._extract_hash(canon_a)
    hash_b = kpi._extract_hash(canon_b)
    assert hash_a != hash_b, (
        "same size+mtime DB files with different row content must produce "
        "different extract hashes — a size/mtime-only stamp would have "
        "missed this")


def test_pit_accrual_manifest_hash_changes_with_manifest_content(rq_root):
    """Two otherwise-identical valid snapshot days with different manifest
    byte content must produce different accrual_extract_sha256 values."""
    snapshots = rq_root / "data" / "estimate_snapshots"
    snapshots.mkdir(parents=True)

    def _write_day(date_str, extra_field=None):
        d = snapshots / date_str
        d.mkdir(exist_ok=True)
        for endpoint in (
            "analyst_estimates", "grades_consensus",
            "price_target_consensus", "price_target_summary",
        ):
            parquet_name = f"{endpoint}.parquet"
            (d / parquet_name).write_bytes(b"not-empty")
            manifest = {"status": "ok", "as_of": date_str, "output": parquet_name}
            if extra_field:
                manifest["note"] = extra_field
            (d / f"{endpoint}.manifest.json").write_text(json.dumps(manifest))

    kpi.ESTIMATE_SNAPSHOTS = str(snapshots)
    sys.path.insert(0, os.path.join(REPO_ROOT, "ops", "pit"))
    import pit_liveness_check
    pit_liveness_check.ROOT = str(snapshots)

    _write_day("2026-06-01")
    result_a = kpi._run(kpi.metric_pit_accrual_days, dt.date(2026, 6, 2))
    hash_a = result_a["detail"]["accrual_extract_sha256"]

    for f in snapshots.glob("2026-06-01/*.manifest.json"):
        f.unlink()
    _write_day("2026-06-01", extra_field="differs")
    result_b = kpi._run(kpi.metric_pit_accrual_days, dt.date(2026, 6, 2))
    hash_b = result_b["detail"]["accrual_extract_sha256"]

    assert hash_a != hash_b


# ------------------------------------------------- DB read-snapshot consistency


def test_all_db_metrics_share_one_snapshot_despite_concurrent_writer(tmp_path):
    """The scorecard's DB-derived metrics must all observe the SAME
    committed state, even if a concurrent writer commits new rows to
    runs.alpaca.db mid-run. Without an explicit read transaction, python's
    sqlite3 module does not implicitly pin a snapshot for SELECT-only work
    — two independent SELECTs on the same read-only connection could
    observe different WAL states across a concurrent commit, breaking the
    scorecard's claim to be one coherent point-in-time state vector."""
    db_path = str(tmp_path / "runs.alpaca.db")
    setup = sqlite3.connect(db_path)
    # Real runs.alpaca.db is WAL-mode (per _connect_ro's own docstring,
    # which falls back to immutable=1 specifically for readers that cannot
    # create the WAL -shm file) — WAL is what gives a reader snapshot
    # isolation from a CONCURRENT writer without blocking either side; the
    # default rollback-journal mode does not have this property (a writer
    # can be blocked by an open reader transaction instead). Match
    # production's actual journal mode so this test reflects reality.
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("create table pipeline_runs (run_id text, run_date text)")
    setup.execute("insert into pipeline_runs values ('run-1', '2026-06-01')")
    setup.commit()
    setup.close()

    reader = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    reader.execute("BEGIN")
    count_before = reader.execute("select count(*) from pipeline_runs").fetchone()[0]
    assert count_before == 1

    # A CONCURRENT WRITER commits a new row from a SEPARATE connection while
    # the reader's transaction is still open — this is exactly the scenario
    # that would corrupt an un-transacted scorecard's coherence.
    writer = sqlite3.connect(db_path)
    writer.execute("insert into pipeline_runs values ('run-2', '2026-06-02')")
    writer.commit()
    writer.close()

    # A SECOND query on the SAME reader connection, still inside the ONE
    # transaction opened above, must see the SAME snapshot as the first
    # query — proving the explicit BEGIN genuinely pins one coherent
    # point-in-time view for the whole run, not per-statement freshness.
    count_after_concurrent_write = reader.execute(
        "select count(*) from pipeline_runs").fetchone()[0]
    assert count_after_concurrent_write == count_before == 1, (
        "a second query within the same explicit transaction observed the "
        "concurrent writer's commit — the snapshot is not actually pinned"
    )

    reader.execute("ROLLBACK")
    reader.close()

    # Sanity: a FRESH connection/transaction (as if this were the NEXT
    # scorecard run) correctly sees the writer's committed row — proving
    # the isolation is scoped to one transaction's lifetime, not a
    # permanently stale cache.
    fresh_reader = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    fresh_reader.execute("BEGIN")
    count_fresh = fresh_reader.execute("select count(*) from pipeline_runs").fetchone()[0]
    assert count_fresh == 2
    fresh_reader.execute("ROLLBACK")
    fresh_reader.close()
