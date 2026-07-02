"""Tests for ops/renquant105/export_batch_scores.py + batch_scores_bundle.py
(Codex #236 round 2 — the exporter previously picked the lexicographically
largest run_id off `candidate_scores` alone, with no `pipeline_runs`
completion/fingerprint check, no atomic write, and an undocumented coverage
floor that silently accepted a ~50% score collapse. This file proves: (1) SQL
selection rejects a run with no pipeline_runs row / wrong run_type / missing
fingerprint, and correctly picks the canonical (created_at-latest) run when
multiple exist for a date; (2) an atomic-write crash never exposes a
half-written file; (3) coverage is measured against the run's own persisted
candidate roster and a shortfall is refused with the missing tickers named;
(4) the replay-side verifier detects a stale session_date and a content-hash
mismatch."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OPS_DIR = REPO / "ops" / "renquant105"
sys.path.insert(0, str(OPS_DIR))

import export_batch_scores as exporter  # noqa: E402
import batch_scores_bundle as bundle  # noqa: E402


# ─────────────────────────── fixture DB builder ───────────────────────────

_SCHEMA = """
CREATE TABLE pipeline_runs (
    run_id           TEXT PRIMARY KEY,
    run_date         DATE NOT NULL,
    run_type         TEXT NOT NULL,
    strategy         TEXT,
    run_bundle_json  TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE candidate_scores (
    run_id      TEXT,
    ticker      TEXT,
    role        TEXT,
    panel_score REAL,
    PRIMARY KEY (run_id, ticker, role)
);
"""

_GOOD_BUNDLE = {
    "config_hash": "sha256:cfg",
    "artifact_hashes": {"panel": "sha256:art1", "gate_b": "sha256:art2"},
    "watchlist_hash": "sha256:wl",
    "watchlist_size": 3,
}


def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "runs.alpaca.db")
    con = sqlite3.connect(db_path)
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    return db_path


def _insert_run(
    db_path,
    run_id,
    *,
    run_date="2026-07-01",
    run_type="live",
    strategy="patchtst",
    run_bundle=_GOOD_BUNDLE,
    created_at="2026-07-01T13:55:00",
    scores=None,  # dict ticker -> score-or-None; defaults to a full 3/3 roster
):
    if scores is None:
        scores = {"AAA": 0.1, "BBB": 0.2, "CCC": 0.3}
    con = sqlite3.connect(db_path)
    con.execute(
        "insert into pipeline_runs (run_id, run_date, run_type, strategy, "
        "run_bundle_json, created_at) values (?,?,?,?,?,?)",
        (run_id, run_date, run_type, strategy,
         json.dumps(run_bundle) if run_bundle is not None else None,
         created_at),
    )
    for ticker, score in scores.items():
        con.execute(
            "insert into candidate_scores (run_id, ticker, role, panel_score) "
            "values (?,?,?,?)",
            (run_id, ticker, "candidate", score),
        )
    con.commit()
    con.close()


# We only need >= MIN_ROWS(=80) scored names to clear the initial SQL filter
# in production, but for unit tests we monkeypatch MIN_ROWS down so fixtures
# stay small and readable.
@pytest.fixture(autouse=True)
def _small_min_rows(monkeypatch):
    monkeypatch.setattr(exporter, "MIN_ROWS", 2)


# ─────────────────────────── selection logic ───────────────────────────

def test_selects_completed_live_run_with_fingerprint(tmp_path):
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-live-aaaa1111")
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 0
    meta = json.loads((tmp_path / "out" / "batch_scores_2026-07-02.meta.json").read_text())
    assert meta["run_id"] == "2026-07-01-live-aaaa1111"


def test_rejects_run_with_no_pipeline_runs_row(tmp_path):
    """candidate_scores rows with no matching pipeline_runs row (e.g. a
    partial write that crashed before record_pipeline_run committed) must
    never be selectable — the join requires a real completed run row."""
    db = _make_db(tmp_path)
    con = sqlite3.connect(db)
    con.execute(
        "insert into candidate_scores (run_id, ticker, role, panel_score) "
        "values (?,?,?,?)", ("2026-07-01-live-orphan", "AAA", "candidate", 0.1),
    )
    con.execute(
        "insert into candidate_scores (run_id, ticker, role, panel_score) "
        "values (?,?,?,?)", ("2026-07-01-live-orphan", "BBB", "candidate", 0.2),
    )
    con.commit()
    con.close()
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1
    assert not (tmp_path / "out").exists()


def test_rejects_non_live_run_type(tmp_path):
    """A run_type='sim' or 'lean' row must never be selected even if its
    run_id happens to contain the substring 'live' somewhere."""
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-sim-live-lookalike", run_type="sim")
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1


def test_rejects_run_with_empty_strategy(tmp_path):
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-live-nostrategy", strategy="")
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1


@pytest.mark.parametrize("missing_field", ["config_hash", "artifact_hashes", "watchlist_hash"])
def test_rejects_run_with_missing_fingerprint_field(tmp_path, missing_field):
    db = _make_db(tmp_path)
    bad_bundle = dict(_GOOD_BUNDLE)
    bad_bundle.pop(missing_field)
    _insert_run(db, "2026-07-01-live-nofp", run_bundle=bad_bundle)
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1
    assert not (tmp_path / "out").exists()


def test_rejects_run_with_empty_artifact_hash_value(tmp_path):
    """A present-but-empty artifact_hashes entry (e.g. one artifact failed to
    hash) must be treated the same as a missing fingerprint, not accepted
    because the dict key technically exists."""
    db = _make_db(tmp_path)
    bad_bundle = dict(_GOOD_BUNDLE)
    bad_bundle["artifact_hashes"] = {"panel": "sha256:art1", "gate_b": None}
    _insert_run(db, "2026-07-01-live-partialfp", run_bundle=bad_bundle)
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1


def test_picks_canonical_latest_run_by_created_at_not_run_id_string(tmp_path):
    """Two live runs on the same date: run_id string order is DELIBERATELY
    the opposite of created_at order, proving selection uses created_at (the
    real completion timestamp) and not a lexicographic string comparison."""
    db = _make_db(tmp_path)
    _insert_run(
        db, "2026-07-01-live-zzzz-earlier", created_at="2026-07-01T09:00:00",
        scores={"AAA": 0.1, "BBB": 0.2},
    )
    _insert_run(
        db, "2026-07-01-live-aaaa-later", created_at="2026-07-01T13:55:00",
        scores={"CCC": 0.3, "DDD": 0.4},
    )
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 0
    meta = json.loads((tmp_path / "out" / "batch_scores_2026-07-02.meta.json").read_text())
    assert meta["run_id"] == "2026-07-01-live-aaaa-later"


def test_no_qualifying_run_before_today_is_refused(tmp_path):
    db = _make_db(tmp_path)
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1
    assert not (tmp_path / "out").exists()


# ─────────────── source-freshness: exact-prior-session requirement ─────────
# Codex #236 round 3: round 2 accepted the latest qualifying run from ANY
# date strictly before today, so a multi-day pipeline outage would silently
# republish however-old a vector was last produced, re-stamped as today's.
# These tests prove the fix requires an EXACT match on the immediately
# preceding NYSE session (holiday/weekend aware), with no fallback.

def test_old_run_is_rejected_not_silently_accepted(tmp_path):
    """The most recent available run is 3 days stale (not the immediately
    preceding session) — must be refused, never silently republished as
    today's fresh vector."""
    db = _make_db(tmp_path)
    _insert_run(db, "2026-06-29-live-stale", run_date="2026-06-29",
                created_at="2026-06-29T13:55:00")
    # today=2026-07-02 (Thu); expected prior session=2026-07-01 (Wed) — the
    # only available run is 2026-06-29, 3 sessions earlier.
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1
    assert not (tmp_path / "out").exists()


def test_missing_exact_prior_session_run_is_refused_no_fallback(tmp_path):
    """Only an OLDER qualifying run exists (no run at all for the exact
    expected prior session) — must fail/refuse, never fall back to the older
    run."""
    db = _make_db(tmp_path)
    _insert_run(db, "2026-06-30-live-older", run_date="2026-06-30",
                created_at="2026-06-30T13:55:00")
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1
    assert not (tmp_path / "out").exists()


def test_weekend_and_holiday_aware_prior_session(tmp_path):
    """2026-07-03 (Fri) is the observed July 4th holiday (July 4 falls on a
    Saturday) and 2026-07-04/05 are the weekend, so the correct 'immediately
    preceding session' before 2026-07-06 (Mon) is 2026-07-02 (Thu) — a 4
    calendar-day gap that naive weekday-only arithmetic would get wrong
    (it would land on Friday 07-03, a holiday with no real session)."""
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-02-live-correct", run_date="2026-07-02",
                created_at="2026-07-02T13:55:00")
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-06")
    assert rc == 0
    meta = json.loads((tmp_path / "out" / "batch_scores_2026-07-06.meta.json").read_text())
    assert meta["source_run_date"] == "2026-07-02"


def test_holiday_date_run_never_selected_even_if_present(tmp_path):
    """A (synthetic, DB-only) run dated on the market-holiday Friday 2026-07-03
    must never be selected for a Monday 2026-07-06 export — the real prior
    session is Thursday 2026-07-02, not the naive "Friday before" guess."""
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-03-live-holidayrun", run_date="2026-07-03",
                created_at="2026-07-03T13:55:00")
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-06")
    assert rc == 1
    assert not (tmp_path / "out").exists()


def test_source_run_date_persisted_in_meta(tmp_path):
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-live-dated", run_date="2026-07-01")
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 0
    meta = json.loads((tmp_path / "out" / "batch_scores_2026-07-02.meta.json").read_text())
    assert meta["source_run_date"] == "2026-07-01"


def test_verify_bundle_rejects_missing_source_run_date(tmp_path):
    """A bundle predating this fix (no source_run_date in meta) must be
    refused, not silently trusted."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        score_path = os.path.join(d, "s.json")
        meta_path = os.path.join(d, "m.json")
        scores = {"AAA": 0.1}
        with open(score_path, "w") as f:
            json.dump(scores, f)
        with open(meta_path, "w") as f:
            json.dump({
                "session_date": "2026-07-02",
                "score_content_sha256": bundle.canonical_hash(scores),
            }, f)  # no source_run_date field
        ok, reason = bundle.verify_bundle(score_path, meta_path, today="2026-07-02")
        assert not ok
        assert "source_run_date" in reason.lower()


def test_verify_bundle_rejects_stale_source_run_date(tmp_path):
    """meta.session_date is correctly today, but meta.source_run_date points
    at a stale run (not the immediately preceding session) — must be
    refused, catching a bundle that was correctly stamped session_date=today
    but sourced from an old run (the exact failure mode this round fixes on
    the export side; this is the replay-side defense-in-depth check)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        score_path = os.path.join(d, "s.json")
        meta_path = os.path.join(d, "m.json")
        scores = {"AAA": 0.1}
        with open(score_path, "w") as f:
            json.dump(scores, f)
        with open(meta_path, "w") as f:
            json.dump({
                "session_date": "2026-07-02",
                "source_run_date": "2026-06-29",  # 3 sessions stale
                "score_content_sha256": bundle.canonical_hash(scores),
            }, f)
        ok, reason = bundle.verify_bundle(score_path, meta_path, today="2026-07-02")
        assert not ok
        assert "stale source" in reason.lower()


# ─────────────────────────── coverage + missing tickers ───────────────────

def test_coverage_below_floor_is_refused_with_missing_tickers_named(tmp_path, capsys):
    db = _make_db(tmp_path)
    # 5-name roster, only 2 scored (40% coverage) — well below the 90% floor.
    _insert_run(
        db, "2026-07-01-live-lowcov",
        scores={"AAA": 0.1, "BBB": 0.2, "CCC": None, "DDD": None, "EEE": None},
    )
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 1
    assert not (tmp_path / "out").exists()
    err = capsys.readouterr().err
    assert "CCC" in err and "DDD" in err and "EEE" in err


def test_coverage_at_floor_is_accepted(tmp_path):
    db = _make_db(tmp_path)
    # 10-name roster, 9 scored = exactly 90% — must pass (floor is inclusive).
    scores = {f"T{i}": 0.1 * i for i in range(9)}
    scores["T9"] = None
    _insert_run(db, "2026-07-01-live-atfloor", scores=scores)
    rc = exporter.main(db_path=db, out_dir=str(tmp_path / "out"), today="2026-07-02")
    assert rc == 0
    meta = json.loads((tmp_path / "out" / "batch_scores_2026-07-02.meta.json").read_text())
    assert meta["missing_tickers"] == ["T9"]
    assert meta["universe_n"] == 10
    assert meta["n"] == 9


# ─────────────────────────── atomic write + hashing ───────────────────────

def test_export_is_atomic_no_partial_file_survives_a_write_crash(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-live-crashtest")
    out_dir = tmp_path / "out"

    # Simulate a crash mid-write: os.rename never runs, only the .tmp file
    # would exist. A correctly atomic writer never lets a reader see a
    # renamed-but-incomplete final path.
    real_rename = os.rename
    calls = {"n": 0}

    def _boom_on_first_rename(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated crash before rename completes")
        return real_rename(src, dst)

    monkeypatch.setattr(exporter.os, "rename", _boom_on_first_rename)
    with pytest.raises(OSError):
        exporter.main(db_path=db, out_dir=str(out_dir), today="2026-07-02")

    score_path = out_dir / "batch_scores_2026-07-02.json"
    # The crash happened on the FIRST rename (the score file) — no final
    # score path should exist, only its .tmp sibling (or nothing at all if
    # makedirs itself is what's being raced — either way, never a corrupt
    # "final" file).
    assert not score_path.exists()


def test_score_content_hash_is_deterministic_regardless_of_db_row_order(tmp_path):
    """Two runs with the identical logical score set, inserted in different
    orders, must hash identically — proves the canonical hash sorts keys
    rather than depending on dict/DB iteration order."""
    db1 = str(tmp_path / "db1.sqlite")
    con = sqlite3.connect(db1)
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    _insert_run(db1, "2026-07-01-live-orderA", scores={"AAA": 0.1, "BBB": 0.2, "CCC": 0.3})

    db2 = str(tmp_path / "db2.sqlite")
    con = sqlite3.connect(db2)
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    _insert_run(db2, "2026-07-01-live-orderB", scores={"CCC": 0.3, "AAA": 0.1, "BBB": 0.2})

    exporter.main(db_path=db1, out_dir=str(tmp_path / "out1"), today="2026-07-02")
    exporter.main(db_path=db2, out_dir=str(tmp_path / "out2"), today="2026-07-02")
    meta1 = json.loads((tmp_path / "out1" / "batch_scores_2026-07-02.meta.json").read_text())
    meta2 = json.loads((tmp_path / "out2" / "batch_scores_2026-07-02.meta.json").read_text())
    assert meta1["score_content_sha256"] == meta2["score_content_sha256"]


# ─────────────────────── expected_previous_session ─────────────────────────

def test_expected_previous_session_regular_weekday():
    assert bundle.expected_previous_session("2026-07-02") == "2026-07-01"


def test_expected_previous_session_skips_weekend():
    # Monday 2026-06-29 -> prior session is Friday 2026-06-26, not Sunday.
    assert bundle.expected_previous_session("2026-06-29") == "2026-06-26"


def test_expected_previous_session_skips_holiday():
    # Monday 2026-07-06 -> prior session is Thursday 2026-07-02: Friday
    # 2026-07-03 is the observed July 4th holiday, then the weekend.
    assert bundle.expected_previous_session("2026-07-06") == "2026-07-02"


# ─────────────────────────── replay-side verification ─────────────────────

def test_verify_bundle_accepts_freshly_exported_bundle(tmp_path):
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-live-verifyok")
    out_dir = tmp_path / "out"
    exporter.main(db_path=db, out_dir=str(out_dir), today="2026-07-02")
    ok, reason = bundle.verify_bundle(
        str(out_dir / "batch_scores_2026-07-02.json"),
        str(out_dir / "batch_scores_2026-07-02.meta.json"),
        today="2026-07-02",
    )
    assert ok, reason


def test_verify_bundle_rejects_stale_session_date(tmp_path):
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-live-stale")
    out_dir = tmp_path / "out"
    exporter.main(db_path=db, out_dir=str(out_dir), today="2026-07-02")
    # Replay runs a day later against yesterday's leftover bundle.
    ok, reason = bundle.verify_bundle(
        str(out_dir / "batch_scores_2026-07-02.json"),
        str(out_dir / "batch_scores_2026-07-02.meta.json"),
        today="2026-07-03",
    )
    assert not ok
    assert "stale" in reason.lower()


def test_verify_bundle_rejects_content_hash_mismatch(tmp_path):
    db = _make_db(tmp_path)
    _insert_run(db, "2026-07-01-live-tamper")
    out_dir = tmp_path / "out"
    exporter.main(db_path=db, out_dir=str(out_dir), today="2026-07-02")
    score_path = out_dir / "batch_scores_2026-07-02.json"
    # Tamper with the score file after export, meta still names the old hash.
    payload = json.loads(score_path.read_text())
    payload["AAA"] = 999.0
    score_path.write_text(json.dumps(payload))
    ok, reason = bundle.verify_bundle(
        str(score_path),
        str(out_dir / "batch_scores_2026-07-02.meta.json"),
        today="2026-07-02",
    )
    assert not ok
    assert "mismatch" in reason.lower()


def test_verify_bundle_rejects_missing_meta_hash_field():
    """A bundle exported before this fix (no score_content_sha256 in meta)
    must be refused, not silently trusted. source_run_date is present and
    correct so this test isolates the hash-field check specifically (a
    separate test below covers a missing source_run_date)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        score_path = os.path.join(d, "s.json")
        meta_path = os.path.join(d, "m.json")
        with open(score_path, "w") as f:
            json.dump({"AAA": 0.1}, f)
        with open(meta_path, "w") as f:
            json.dump(
                {"session_date": "2026-07-02", "source_run_date": "2026-07-01"}, f
            )  # no hash field
        ok, reason = bundle.verify_bundle(score_path, meta_path, today="2026-07-02")
        assert not ok
        assert "sha256" in reason.lower() or "hash" in reason.lower()
