"""Tests for ops/renquant104/rq104_shadow_scorer_sentinel.py (GOAL-5 AC1).

Each silent-degradation state of the shadow scorer is injected via a fixture
(the structured `shadow_scorer_health.v1` JSONL and/or the shadow runs DB) and
must alarm; each healthy state must stay silent. Session-day gating is mocked so
weekends/holidays never depend on the real calendar. Both reader paths are
exercised: the pipeline health record (primary, authoritative `actionable`) and
the shadow-DB fallback (derived staleness/coverage).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))

import rq104_shadow_scorer_sentinel as sentinel  # noqa: E402

AS_OF = "2026-07-16"
D0 = dt.date(2026, 7, 16)
D1 = dt.date(2026, 7, 15)
SHADOW = "hf_patchtst"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _make_shadow_db(tmp_path, run_rows, score_rows):
    """run_rows:   list of (run_id, run_date, training_cutoff)
    score_rows: list of (run_id, ticker, active_scorer, model_type)"""
    db = tmp_path / "shadow.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE pipeline_runs (run_id TEXT, run_date DATE, run_type TEXT,"
        " training_cutoff TEXT)"
    )
    conn.execute(
        "CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT,"
        " active_scorer TEXT, model_type TEXT, panel_score REAL)"
    )
    for run_id, run_date, cutoff in run_rows:
        conn.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?)",
                     (run_id, run_date, "live", cutoff))
    for run_id, ticker, scorer, mtype in score_rows:
        conn.execute("INSERT INTO candidate_scores VALUES (?,?,?,?,?)",
                     (run_id, ticker, scorer, mtype, 0.1))
    conn.commit()
    conn.close()
    return str(db)


def _make_prod_runs_db(tmp_path, live_dates: list[str]) -> str:
    """A minimal PRODUCTION runs DB (data/runs.alpaca.db shape): only what
    `_had_live_run` needs — one row per live session date."""
    db = tmp_path / "prod.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE pipeline_runs (run_id TEXT, run_date DATE, run_type TEXT,"
        " training_cutoff TEXT)"
    )
    for i, d in enumerate(live_dates):
        conn.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?)",
                     (f"r{i}", d, "live", None))
    conn.commit()
    conn.close()
    return str(db)


def _write_comparison_json(mlruns_root: Path, exp_id: str, run_id: str,
                          rows: list, *, mtime_date: str) -> Path:
    """An MLflow comparison.json artifact in the REAL production shape: no
    run_date/shadow_name columns (verified against the actual artifacts under
    mlruns/**/comparison.json), so the locator's date match falls back to
    file mtime — exactly like production."""
    art_dir = mlruns_root / exp_id / run_id / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    p = art_dir / "comparison.json"
    payload = {
        "columns": ["ticker", "primary_score", "shadow_score", "diff",
                    "primary_rank", "shadow_rank", "rank_diff"],
        "data": rows,
    }
    p.write_text(json.dumps(payload))
    ts = dt.datetime.fromisoformat(mtime_date).timestamp()
    os.utime(p, (ts, ts))
    return p


def _write_tagged_comparison_json(mlruns_root: Path, exp_id: str, run_id: str,
                                  rows: list, *, as_of_date: str,
                                  shadow_name: str, mtime_date: str) -> Path:
    """An MLflow comparison.json artifact WITH the run tags the real producer
    (`_log_shadow_run` in renquant-pipeline) writes via `mlflow.set_tags` —
    `<run_dir>/tags/as_of_date` and `<run_dir>/tags/shadow_name` — the
    content-based record the locator's primary match now reads instead of
    trusting file mtime or an artifact payload column."""
    p = _write_comparison_json(mlruns_root, exp_id, run_id, rows,
                               mtime_date=mtime_date)
    tags_dir = p.parent.parent / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    (tags_dir / "as_of_date").write_text(as_of_date)
    (tags_dir / "shadow_name").write_text(shadow_name)
    return p


def _run(tmp_path, *, run_rows=None, score_rows=None, jsonl=None,
         staleness_max=28, coverage_floor=0.80, streak=2, as_of=AS_OF,
         lanes=None):
    """Run main() with all seams patched; return (rc, alerts).

    `lanes` is the patrol registry. The default is ONE legacy-shaped mechanics
    lane (name=SHADOW, runs_db=the fixture DB) — the exact shape this suite's
    fixtures were written against, kept explicit here since #758 removed the
    retired PatchTST lane from the PRODUCTION registry. These tests pin the
    detection MECHANICS (streaks, classify, primary-vs-fallback merge, strict
    schema); the production registry (clf + momentum) is pinned by its own
    tests below, so a future registry change cannot silently change what the
    mechanics tests measure.

    `--config ""` is passed so the config drift check takes its NOT-REQUESTED
    path: none of these tests may depend on the operator's sibling strategy-104
    checkout (the tests-measure-the-operator's-disk class).
    """
    alerts: list[tuple[str, str]] = []
    db_path = _make_shadow_db(tmp_path, run_rows or [], score_rows or [])
    jsonl_path = tmp_path / "shadow_scorer_health.jsonl"
    if jsonl is not None:
        jsonl_path.write_text("\n".join(json.dumps(r) for r in jsonl) + "\n")
    if lanes is None:
        lanes = (sentinel.WatchedLane(name=SHADOW, runs_db=db_path),)

    with (
        patch.object(sentinel, "is_session_day", return_value=True),
        patch.object(sentinel, "SHADOW_DB", db_path),
        patch.object(sentinel, "SHADOW_HEALTH_JSONL", str(jsonl_path)),
        patch.object(sentinel, "STALENESS_MAX_DAYS", staleness_max),
        patch.object(sentinel, "COVERAGE_FLOOR", coverage_floor),
        patch.object(sentinel, "STREAK_N", streak),
        patch.object(sentinel, "alert", lambda t, b, **kw: alerts.append((t, b))),
        patch.object(sentinel, "watched_lanes", lambda: tuple(lanes)),
        # A missing dir/db keeps any MLflow-fallback lane a no-op here
        # (`_read_from_mlflow` early-returns {}) so main()-driving tests never
        # touch the real production mlruns tree / runs DB.
        patch.object(sentinel, "MLRUNS_DIR", str(tmp_path / "no_mlruns_here")),
        patch.object(sentinel, "PROD_RUNS_DB", str(tmp_path / "no_prod_db_here")),
    ):
        rc = sentinel.main(["--as-of", as_of, "--config", ""])
    return rc, alerts


def _healthy_db_rows(cutoff="2026-07-14"):
    run_rows = [("r_d1", D1.isoformat(), cutoff), ("r_d0", D0.isoformat(), cutoff)]
    score_rows = [(rid, tk, SHADOW, SHADOW)
                  for rid in ("r_d1", "r_d0")
                  for tk in ("AAPL", "MSFT", "NVDA", "AMZN")]
    return run_rows, score_rows


def _record(run_date, **kw):
    """A canonical schema-v1 health record. Defaults to a HEALTHY (status=ok)
    day. Tests may pass `status=`/`state=` explicitly, or just `actionable=`
    (legacy convenience) — status is then derived. The producer invariant
    `actionable == (status != "fault")` is always re-enforced so every record
    this helper returns is internally consistent and passes strict validation.
    """
    base = dict(
        schema="shadow_scorer_health.v1", shadow_name=SHADOW, kind="panel",
        status="ok", state="ok",
        loaded=True, load_error=None, artifact_path="patchtst/x.pt",
        artifact_resolved=True, artifact_resolved_path="/store/patchtst/x.pt",
        effective_train_cutoff_date="2026-07-10", staleness_days=6,
        config_fingerprint="cfg123", content_sha256="sha256:abc", n_candidates=80,
        n_scored=78, coverage_frac=0.975, skip_reason=None, reasons=[],
        run_date=run_date, run_id=f"r_{run_date}",
    )
    base.update(kw)
    # if only actionable was supplied, derive status from it
    if "status" not in kw and "actionable" in kw:
        base["status"] = "ok" if kw["actionable"] else "fault"
    # always re-enforce the canonical invariant
    base["actionable"] = (base["status"] != "fault")
    return base


# ---------------------------------------------------------------------------
# a. LOAD FAILURE streak (the incident) — DB fallback + structured record
# ---------------------------------------------------------------------------

class TestLoadFailureStreak:
    def test_db_two_days_no_shadow_scores_alarm(self, tmp_path):
        # both days: live runs + scores collected, but NONE from the shadow
        # (only legacy tournament model types) => the 2026-07-16 incident.
        run_rows = [("r_d1", D1.isoformat(), None), ("r_d0", D0.isoformat(), None)]
        score_rows = [(rid, tk, None, "XGBoost")
                      for rid in ("r_d1", "r_d0") for tk in ("AAPL", "MSFT")]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == sentinel.EXIT_ALARM
        assert "LOAD FAILURE" in alerts[0][1]

    def test_structured_two_days_not_loaded_alarm(self, tmp_path):
        jsonl = [
            _record(D1.isoformat(), loaded=False, n_scored=0, coverage_frac=0.0,
                    artifact_resolved=False, load_error="artifact_not_found",
                    actionable=False, reasons=["artifact_unresolved"]),
            _record(D0.isoformat(), loaded=False, n_scored=0, coverage_frac=0.0,
                    artifact_resolved=False, load_error="artifact_not_found",
                    actionable=False, reasons=["artifact_unresolved"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == sentinel.EXIT_ALARM
        assert "LOAD FAILURE" in alerts[0][1]
        assert "artifact_unresolved" in alerts[0][1]

    def test_healthy_days_silent(self, tmp_path):
        run_rows, score_rows = _healthy_db_rows()
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == 0 and not alerts

    def test_single_bad_day_silent(self, tmp_path):
        run_rows = [("r_d1", D1.isoformat(), "2026-07-14"), ("r_d0", D0.isoformat(), None)]
        score_rows = [("r_d1", "AAPL", SHADOW, SHADOW), ("r_d1", "MSFT", SHADOW, SHADOW),
                      ("r_d0", "AAPL", None, "XGBoost")]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == 0

    def test_missing_day_is_not_our_alarm(self, tmp_path):
        # D1 has no runs at all (liveness's domain) => streak cannot be claimed.
        run_rows = [("r_d0", D0.isoformat(), None)]
        score_rows = [("r_d0", "AAPL", None, "XGBoost")]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == 0

    def test_model_type_marks_shadow_when_active_scorer_null(self, tmp_path):
        run_rows, _ = _healthy_db_rows()
        score_rows = [(rid, tk, None, SHADOW)
                      for rid in ("r_d1", "r_d0") for tk in ("AAPL", "MSFT")]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == 0


# ---------------------------------------------------------------------------
# b. NOT ACTIONABLE / DEGRADED streak (stale / coverage / provenance)
# ---------------------------------------------------------------------------

class TestDegradedStreak:
    def test_structured_stale_actionable_false_alarms(self, tmp_path):
        jsonl = [
            _record(D1.isoformat(), staleness_days=120, actionable=False,
                    reasons=["stale_cutoff_120d"]),
            _record(D0.isoformat(), staleness_days=121, actionable=False,
                    reasons=["stale_cutoff_121d"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == sentinel.EXIT_ALARM
        assert "NOT ACTIONABLE" in alerts[0][1] or "DEGRADED" in alerts[0][1]
        assert "stale_cutoff_120d" in alerts[0][1]

    def test_structured_low_coverage_actionable_false_alarms(self, tmp_path):
        jsonl = [
            _record(D1.isoformat(), coverage_frac=0.4, actionable=False,
                    reasons=["coverage_0.40_below_0.80"]),
            _record(D0.isoformat(), coverage_frac=0.3, actionable=False,
                    reasons=["coverage_0.30_below_0.80"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == sentinel.EXIT_ALARM
        assert "coverage_0.40_below_0.80" in alerts[0][1]

    def test_db_derived_stale_alarms(self, tmp_path):
        # frozen cutoff 2024-11-13 vs as-of => ~610d > 28d ceiling (no actionable
        # from the DB, so derived).
        run_rows, score_rows = _healthy_db_rows(cutoff="2024-11-13")
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == sentinel.EXIT_ALARM
        assert "stale train-cutoff" in "\n".join(b for _, b in alerts)

    def test_db_derived_thin_coverage_alarms(self, tmp_path):
        # 1 shadow ticker of 4 candidates = 25% < 80% floor, both days.
        run_rows = [("r_d1", D1.isoformat(), "2026-07-14"),
                    ("r_d0", D0.isoformat(), "2026-07-14")]
        score_rows = []
        for rid in ("r_d1", "r_d0"):
            score_rows.append((rid, "AAPL", SHADOW, SHADOW))
            for tk in ("MSFT", "NVDA", "AMZN"):
                score_rows.append((rid, tk, None, "XGBoost"))
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == sentinel.EXIT_ALARM
        assert "coverage" in "\n".join(b for _, b in alerts).lower()

    def test_mixed_degradation_window_alarms(self, tmp_path):
        # day1 load fail, day0 stale => neither pure-load nor pure-dark, but all
        # non-healthy => the DEGRADED catch-all fires (no silent gap).
        jsonl = [
            _record(D1.isoformat(), loaded=False, n_scored=0, actionable=False,
                    reasons=["artifact_unresolved"]),
            _record(D0.isoformat(), staleness_days=90, actionable=False,
                    reasons=["stale_cutoff_90d"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == sentinel.EXIT_ALARM
        body = "\n".join(b for _, b in alerts)
        assert "DEGRADED" in body

    def test_raised_threshold_suppresses_known_frozen(self, tmp_path):
        run_rows, score_rows = _healthy_db_rows(cutoff="2024-11-13")
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows,
                          staleness_max=1000)
        assert rc == 0

    def test_single_degraded_day_silent(self, tmp_path):
        jsonl = [_record(D1.isoformat()),  # healthy
                 _record(D0.isoformat(), actionable=False, reasons=["stale"])]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 0


# ---------------------------------------------------------------------------
# c. FEED DARK streak (bootstrap-safe: only when BOTH feeds silent)
# ---------------------------------------------------------------------------

class TestFeedDarkStreak:
    def test_two_days_no_scores_collected_alarm(self, tmp_path):
        # runs exist, but no candidate scores AND no JSONL => truly dark.
        run_rows = [("r_d1", D1.isoformat(), None), ("r_d0", D0.isoformat(), None)]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=[])
        assert rc == sentinel.EXIT_ALARM
        assert "DARK" in alerts[0][1]

    def test_feed_alive_but_shadow_dead_is_load_failure_not_dark(self, tmp_path):
        run_rows = [("r_d1", D1.isoformat(), None), ("r_d0", D0.isoformat(), None)]
        score_rows = [("r_d1", "AAPL", None, "XGBoost"), ("r_d0", "AAPL", None, "XGBoost")]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == sentinel.EXIT_ALARM
        body = "\n".join(b for _, b in alerts)
        assert "LOAD FAILURE" in body and "DARK" not in body

    def test_jsonl_absent_but_db_alive_is_not_dark(self, tmp_path):
        # bootstrap window: the pipeline sink is not deployed yet (no JSONL), but
        # the DB score feed is healthy => must stay silent.
        run_rows, score_rows = _healthy_db_rows()
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows, jsonl=None)
        assert rc == 0 and not alerts


# ---------------------------------------------------------------------------
# actionable false-positive guard + primary/fallback merge
# ---------------------------------------------------------------------------

class TestActionableGuard:
    def test_by_design_nonload_actionable_true_stays_silent(self, tmp_path):
        # shadow scored 0 but the PIPELINE marked it actionable (a by-design
        # skip, e.g. config-fingerprint rotation) => must NOT alarm.
        jsonl = [
            _record(D1.isoformat(), loaded=False, n_scored=0, coverage_frac=0.0,
                    actionable=True, skip_reason="config_fingerprint_rotation",
                    reasons=["config_fingerprint_rotation_by_design"]),
            _record(D0.isoformat(), loaded=False, n_scored=0, coverage_frac=0.0,
                    actionable=True, skip_reason="config_fingerprint_rotation",
                    reasons=["config_fingerprint_rotation_by_design"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 0 and not alerts

    def test_structured_healthy_silent(self, tmp_path):
        jsonl = [_record(D1.isoformat()), _record(D0.isoformat())]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 0 and not alerts

    def test_primary_wins_fallback_fills_gaps(self, tmp_path):
        # D0 covered by structured record (healthy); D1 only in DB (healthy) =>
        # merged, silent.
        jsonl = [_record(D0.isoformat())]
        run_rows = [("r_d1", D1.isoformat(), "2026-07-14")]
        score_rows = [("r_d1", "AAPL", SHADOW, SHADOW), ("r_d1", "MSFT", SHADOW, SHADOW)]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows, jsonl=jsonl)
        assert rc == 0

    def test_wrong_schema_line_ignored(self, tmp_path):
        # a non-shadow-health JSONL line (e.g. admission sidecar) must be skipped;
        # the DB fallback then drives (healthy).
        run_rows, score_rows = _healthy_db_rows()
        jsonl = [{"schema": "admission_shadow.v1", "date": D0.isoformat(),
                  "added": ["AAPL"]}]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows, jsonl=jsonl)
        assert rc == 0 and not alerts


# ---------------------------------------------------------------------------
# strict schema validation — unknown/invalid records are IGNORED, DB fallback
# stays authoritative until an explicit migration parser is added.
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def _bad(self, run_date, **overrides):
        rec = _record(run_date)
        rec.update(overrides)
        return rec

    def _drop(self, run_date, key):
        rec = _record(run_date)
        rec.pop(key, None)
        return rec

    def test_unit_accepts_exact_v1(self):
        assert sentinel.is_valid_v1_record(_record(D0.isoformat())) is True

    def test_unit_missing_schema_rejected(self):
        assert sentinel.is_valid_v1_record(self._drop(D0.isoformat(), "schema")) is False

    def test_unit_future_version_rejected(self):
        for ver in ("shadow_scorer_health.v2", "shadow_scorer_health.v10",
                    "shadow_scorer_health", "Shadow_Scorer_Health.v1"):
            assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), schema=ver)) is False

    def test_unit_malformed_boolean_rejected(self):
        assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), loaded="false")) is False
        assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), actionable=1)) is False

    def test_unit_int_field_rejects_bool_and_string(self):
        assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), n_scored=True)) is False
        assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), n_scored="7")) is False

    def test_unit_missing_core_field_rejected(self):
        for key in ("shadow_name", "run_date", "loaded", "actionable", "n_scored", "status"):
            assert sentinel.is_valid_v1_record(self._drop(D0.isoformat(), key)) is False, key

    def test_unit_invalid_status_rejected(self):
        for bad in ("degraded", "OK", "faulted", "", None, 1):
            assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), status=bad)) is False, bad

    def test_unit_actionable_status_invariant_enforced(self):
        # status=fault must carry actionable=false; status=ok must carry
        # actionable=true. A record violating the producer invariant is corrupt
        # -> rejected (falls through to the DB fallback).
        assert sentinel.is_valid_v1_record(
            self._bad(D0.isoformat(), status="fault", actionable=True)) is False
        assert sentinel.is_valid_v1_record(
            self._bad(D0.isoformat(), status="ok", actionable=False)) is False
        # the consistent forms are accepted
        assert sentinel.is_valid_v1_record(
            self._bad(D0.isoformat(), status="fault", actionable=False)) is True
        assert sentinel.is_valid_v1_record(
            self._bad(D0.isoformat(), status="expected_skip", actionable=True)) is True

    def test_unit_unparseable_run_date_rejected(self):
        rec = _record(D0.isoformat())
        rec["run_date"] = "2026-13-99"
        assert sentinel.is_valid_v1_record(rec) is False

    def test_unit_bad_nullable_types_rejected(self):
        assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), staleness_days="3")) is False
        assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), coverage_frac="0.9")) is False
        assert sentinel.is_valid_v1_record(self._bad(D0.isoformat(), reasons="stale")) is False

    def test_unit_nullable_absent_or_none_ok(self):
        rec = self._bad(D0.isoformat(), staleness_days=None, coverage_frac=None)
        assert sentinel.is_valid_v1_record(rec) is True

    def test_invalid_records_ignored_db_fallback_authoritative(self, tmp_path):
        # Both days' JSONL records are malformed (unknown schema + bad bool). They
        # must be IGNORED, so the DB fallback — which shows the real 07-16-style
        # shadow death — drives the verdict and ALARMS. A producer emitting an
        # unrecognised shape can never silently mask a real fault.
        jsonl = [
            {"schema": "shadow_scorer_health.v99", "shadow_name": SHADOW,
             "run_date": D1.isoformat(), "loaded": True, "actionable": True,
             "n_scored": 50},
            self._bad(D0.isoformat(), loaded="nope"),  # malformed bool
        ]
        run_rows = [("r_d1", D1.isoformat(), None), ("r_d0", D0.isoformat(), None)]
        score_rows = [(rid, tk, None, "XGBoost")
                      for rid in ("r_d1", "r_d0") for tk in ("AAPL", "MSFT")]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows, jsonl=jsonl)
        assert rc == sentinel.EXIT_ALARM
        assert "LOAD FAILURE" in alerts[0][1]
        assert "shadow_runs_db_fallback" in alerts[0][1]

    def test_valid_record_supersedes_db_fallback(self, tmp_path):
        # a VALID v1 record (healthy) for a day the DB would call dead must win:
        # primary supersedes fallback per-day.
        jsonl = [_record(D1.isoformat()), _record(D0.isoformat())]
        run_rows = [("r_d1", D1.isoformat(), None), ("r_d0", D0.isoformat(), None)]
        score_rows = [(rid, tk, None, "XGBoost")
                      for rid in ("r_d1", "r_d0") for tk in ("AAPL",)]  # DB = shadow dead
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows, jsonl=jsonl)
        assert rc == 0 and not alerts


# ---------------------------------------------------------------------------
# producer/consumer expected-skip contract (renquant-pipeline#211)
# ---------------------------------------------------------------------------

class TestExpectedSkipContract:
    def test_expected_skip_status_stays_quiet(self, tmp_path):
        # #211's expected_skip states (disabled / no_shadow_models / no_candidates):
        # loaded=false but status=expected_skip (actionable=true) is NOT a fault
        # => quiet, for a full streak of them.
        jsonl = [
            _record(D1.isoformat(), status="expected_skip", state="disabled",
                    loaded=False, n_scored=0, coverage_frac=None,
                    skip_reason="shadow_disabled", reasons=["shadow_enabled_false"]),
            _record(D0.isoformat(), status="expected_skip", state="no_candidates",
                    loaded=False, n_scored=0, coverage_frac=None,
                    reasons=["no_candidates"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 0 and not alerts

    def test_fault_status_load_states_alarm(self, tmp_path):
        # status=fault with a load-type state (unresolved_artifact / load_failed /
        # not_scored) => LOAD FAILURE.
        jsonl = [
            _record(D1.isoformat(), status="fault", state="load_failed",
                    loaded=False, n_scored=0, reasons=["artifact_load_failed"]),
            _record(D0.isoformat(), status="fault", state="unresolved_artifact",
                    loaded=False, n_scored=0, reasons=["artifact_unresolved"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == sentinel.EXIT_ALARM
        assert "LOAD FAILURE" in alerts[0][1]

    def test_fault_status_degraded_state_is_degraded(self, tmp_path):
        # status=fault + state=degraded (scored but untrusted) => DEGRADED.
        jsonl = [
            _record(D1.isoformat(), status="fault", state="degraded",
                    reasons=["missing_provenance"]),
            _record(D0.isoformat(), status="fault", state="degraded",
                    reasons=["missing_provenance"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == sentinel.EXIT_ALARM
        body = "\n".join(b for _, b in alerts)
        assert "DEGRADED" in body and "missing_provenance" in body

    def test_expected_skip_day_breaks_a_fault_streak(self, tmp_path):
        # one real-fault day + one expected_skip day => streak broken, quiet.
        jsonl = [
            _record(D1.isoformat(), status="fault", state="load_failed",
                    loaded=False, n_scored=0, reasons=["artifact_load_failed"]),
            _record(D0.isoformat(), status="expected_skip", state="disabled",
                    loaded=False, n_scored=0, reasons=["shadow_enabled_false"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 0 and not alerts


# ---------------------------------------------------------------------------
# gating + reader/classify units
# ---------------------------------------------------------------------------

class TestGating:
    def test_non_session_day_skips(self, tmp_path):
        run_rows = [("r_d1", D1.isoformat(), None), ("r_d0", D0.isoformat(), None)]
        db = _make_shadow_db(tmp_path, run_rows, [])
        with (
            patch.object(sentinel, "is_session_day", return_value=False),
            patch.object(sentinel, "SHADOW_DB", db),
        ):
            rc = sentinel.main(["--as-of", AS_OF])
        assert rc == 0

    def test_no_runs_in_window_is_liveness_domain(self, tmp_path):
        rc, alerts = _run(tmp_path)  # empty DB, no JSONL => all None => quiet
        assert rc == 0 and not alerts

    def test_last_session_days_oldest_first(self):
        with patch.object(sentinel, "is_session_day",
                          side_effect=lambda d: d.weekday() < 5):
            days = sentinel.last_session_days(dt.date(2026, 7, 13), 2)  # Monday
        assert days == [dt.date(2026, 7, 10), dt.date(2026, 7, 13)]  # Fri, Mon

    def test_from_dict_maps_v1_schema(self):
        rec = sentinel.ShadowHealthRecord.from_dict(
            _record("2026-07-16", n_scored=7, coverage_frac=0.9, staleness_days=4),
            source="pipeline_health_record",
        )
        assert rec.run_date == D0 and rec.n_scored == 7 and rec.loaded is True
        assert rec.actionable is True and rec.source == "pipeline_health_record"

    def test_classify_actionable_false_is_degraded(self):
        rec = sentinel.ShadowHealthRecord.from_dict(
            _record("2026-07-16", actionable=False, reasons=["stale"]),
            source="pipeline_health_record",
        )
        cls, reasons = sentinel.classify(rec)
        assert cls == sentinel.DEGRADED and "stale" in reasons

    def test_classify_fallback_none_actionable_uses_derived(self):
        rec = sentinel.ShadowHealthRecord(
            run_date=D0, loaded=True, n_scored=50, coverage_frac=0.5,
            staleness_days=3, actionable=None, source="shadow_runs_db_fallback",
        )
        cls, reasons = sentinel.classify(rec)  # coverage 0.5 < 0.80 default
        assert cls == sentinel.DEGRADED

    def test_classify_expected_skip_status_is_healthy(self):
        rec = sentinel.ShadowHealthRecord.from_dict(
            _record("2026-07-16", status="expected_skip", state="disabled",
                    loaded=False, n_scored=0),
            source="pipeline_health_record")
        assert sentinel.classify(rec)[0] == sentinel.HEALTHY

    def test_classify_fault_status_drives_over_loaded(self):
        # even loaded=true + scores, status=fault => the alarm axis (DEGRADED).
        rec = sentinel.ShadowHealthRecord.from_dict(
            _record("2026-07-16", status="fault", state="degraded"),
            source="pipeline_health_record")
        assert sentinel.classify(rec)[0] == sentinel.DEGRADED


# ---------------------------------------------------------------------------
# canonical-contract constants: imported from the PRODUCER (#211), with an
# asserted-equal local fallback so the writer and reader cannot drift.
# ---------------------------------------------------------------------------

def _pinned_producer():
    """The producer PRODUCTION serves: shadow_health from the umbrella's
    pin-materialised pipeline clone, when this machine has one. The dev
    sibling that pyproject's pythonpath resolves can lag the lock pin
    (measured 2026-08-02: sibling a14dad11 vs pin 60871e24, missing
    not_yet_published), and this test's estimand is 'fallback == the PINNED
    producer', so the pin wins when present. Elsewhere (CI provisions the
    sibling at the pin; umbrella-less machines) the normal import is the
    best available producer."""
    import importlib
    pinned_src = (Path(__file__).resolve().parents[2]
                  / "RenQuant" / ".subrepo_runtime" / "repos"
                  / "renquant-pipeline" / "src")
    if (pinned_src / "renquant_pipeline" / "kernel" / "panel_pipeline"
            / "shadow_health.py").is_file():
        # Import with the pinned src at the FRONT of sys.path and a clean
        # renquant_pipeline module cache (a lone spec_from_file_location load
        # breaks the module's package context), then restore both so every
        # other test keeps its usual resolution.
        saved_mods = {k: v for k, v in sys.modules.items()
                      if k.split(".")[0] == "renquant_pipeline"}
        for k in saved_mods:
            del sys.modules[k]
        sys.path.insert(0, str(pinned_src))
        try:
            return importlib.import_module(
                "renquant_pipeline.kernel.panel_pipeline.shadow_health")
        finally:
            sys.path.remove(str(pinned_src))
            for k in [k for k in sys.modules
                      if k.split(".")[0] == "renquant_pipeline"]:
                del sys.modules[k]
            sys.modules.update(saved_mods)
    return pytest.importorskip(
        "renquant_pipeline.kernel.panel_pipeline.shadow_health")


class TestContractConstants:
    def test_fallback_literals_match_producer(self):
        sh = _pinned_producer()
        fb = sentinel._FALLBACK_CONTRACT
        assert fb["SHADOW_HEALTH_SCHEMA"] == sh.SHADOW_HEALTH_SCHEMA
        assert fb["STATUS_OK"] == sh.STATUS_OK
        assert fb["STATUS_EXPECTED_SKIP"] == sh.STATUS_EXPECTED_SKIP
        assert fb["STATUS_FAULT"] == sh.STATUS_FAULT
        assert fb["FAULT_STATES"] == frozenset(sh.FAULT_STATES)
        assert fb["EXPECTED_SKIP_STATES"] == frozenset(sh.EXPECTED_SKIP_STATES)

    def test_module_imports_producer_when_available(self):
        pytest.importorskip("renquant_pipeline.kernel.panel_pipeline.shadow_health")
        # in an env where the producer is importable (e.g. `make test`), the
        # module must have used it — not silently fallen back to the literals.
        assert sentinel.CONTRACT_SOURCE == "renquant_pipeline"
        assert sentinel.SHADOW_HEALTH_SCHEMA == "shadow_scorer_health.v1"
        assert "load_failed" in sentinel.FAULT_STATES
        assert "disabled" in sentinel.EXPECTED_SKIP_STATES


# ---------------------------------------------------------------------------
# decorated config-lane names — the 2026-07 clf promotion renamed the lane to
# 'hf_patchtst_pt07_strict_seed44_previous_primary'; the primary sink must
# still claim those records (the observed miss silently demoted the sentinel
# to the DB fallback), while a differently-keyed lane never matches.
# ---------------------------------------------------------------------------

DECORATED = "hf_patchtst_pt07_strict_seed44_previous_primary"


class TestDecoratedLaneName:
    def _dark_db(self):
        # live runs happened, zero shadow scores collected — DB alone would
        # alarm FEED DARK; only OUR healthy structured records may silence it.
        return [("r_d1", D1.isoformat(), "2026-07-14"),
                ("r_d0", D0.isoformat(), "2026-07-14")]

    def test_decorated_name_matches_primary_sink(self, tmp_path):
        jsonl = [_record(D1.isoformat(), shadow_name=DECORATED),
                 _record(D0.isoformat(), shadow_name=DECORATED)]
        rc, alerts = _run(tmp_path, run_rows=self._dark_db(), jsonl=jsonl)
        assert rc == 0 and not alerts

    def test_foreign_lane_name_not_matched(self, tmp_path):
        jsonl = [_record(D1.isoformat(), shadow_name="topdecile_clf_blend_leg"),
                 _record(D0.isoformat(), shadow_name="topdecile_clf_blend_leg")]
        rc, alerts = _run(tmp_path, run_rows=self._dark_db(), jsonl=jsonl)
        assert rc != 0 and alerts

    def test_prefix_requires_separator(self):
        # 'hf_patchtstX' is a different key, not a decoration
        assert not sentinel._matches_shadow_lane("hf_patchtstX")
        assert sentinel._matches_shadow_lane("hf_patchtst")
        assert sentinel._matches_shadow_lane(DECORATED)


# ---------------------------------------------------------------------------
# Multi-lane patrol. Until 2026-07-29 the sentinel watched ONE lane
# ('hf_patchtst'), so the certified top-decile classifier — the only line with
# a confirmed effect, and the one accruing the 120-session forward ledger —
# ran unwatched. These pin the second lane and, critically, the reason its
# evidence source differs.
# ---------------------------------------------------------------------------

class TestMultiLane:
    def test_registry_watches_clf_and_momentum_not_the_retired_patchtst(self):
        # #758: the retired PatchTST lane is REMOVED and the GOAL-7 momentum
        # lane (strategy-104#77, config kind 'momentum_residual') is ADDED in
        # the same change.
        names = {l.name for l in sentinel.watched_lanes()}
        assert names == {"topdecile_clf_blend_leg", "momentum_residual_v0_shadow"}
        assert sentinel.SHADOW_NAME not in names

    def test_no_registry_lane_uses_the_retired_shadow_experiment_db(self):
        # Both lanes log to MLflow + the health JSONL, not the patchtst
        # shadow-experiment runs DB (retired with its lane). A DB fallback here
        # would derive "no scores collected" every single day and manufacture a
        # permanent FEED DARK alarm out of a healthy lane.
        for lane in sentinel.watched_lanes():
            assert lane.runs_db is None, lane.name
            assert lane.mlruns_dir, lane.name

    def test_momentum_lane_matching_accepts_decorated_names_only(self):
        mom = next(l for l in sentinel.watched_lanes()
                   if l.name == "momentum_residual_v0_shadow")
        assert mom.matches("momentum_residual_v0_shadow")
        assert mom.matches("momentum_residual_v0_shadow_retuned")
        assert not mom.matches("momentum_residual_v0_shadowX")
        assert not mom.matches("topdecile_clf_blend_leg")

    def test_no_db_lane_never_reads_the_db(self, tmp_path, monkeypatch):
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None)
        called: list = []
        monkeypatch.setattr(sentinel, "_read_from_shadow_db",
                            lambda *a, **k: called.append(1) or {})
        monkeypatch.setattr(sentinel, "SHADOW_HEALTH_JSONL",
                            str(tmp_path / "absent.jsonl"))
        out = sentinel.read_health_records([D0, D1], clf)
        assert called == [], "a lane with runs_db=None must not touch the DB"
        assert all(v is None for v in out.values())

    def test_lane_matching_accepts_decorated_names_per_lane(self):
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg")
        assert clf.matches("topdecile_clf_blend_leg")
        assert clf.matches("topdecile_clf_blend_leg_seed7_prev")
        assert not clf.matches("hf_patchtst")
        assert not clf.matches("topdecile_clf_blend_legX")

    def test_each_lane_reads_only_its_own_records(self, tmp_path, monkeypatch):
        jsonl = tmp_path / "health.jsonl"
        recs = [_record(D1.isoformat(), shadow_name="hf_patchtst"),
                _record(D0.isoformat(), shadow_name="hf_patchtst"),
                _record(D1.isoformat(), shadow_name="topdecile_clf_blend_leg",
                        status="fault"),
                _record(D0.isoformat(), shadow_name="topdecile_clf_blend_leg",
                        status="fault")]
        jsonl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        monkeypatch.setattr(sentinel, "SHADOW_HEALTH_JSONL", str(jsonl))
        pt = sentinel.WatchedLane(name="hf_patchtst", runs_db=None)
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None)
        pt_recs = sentinel.read_health_records([D1, D0], pt)
        clf_recs = sentinel.read_health_records([D1, D0], clf)
        assert all(r.status == "ok" for r in pt_recs.values() if r)
        assert all(r.status == "fault" for r in clf_recs.values() if r)

    def test_a_degraded_clf_lane_alarms_and_names_itself(self, tmp_path, monkeypatch):
        jsonl = tmp_path / "health.jsonl"
        recs = [_record(D1.isoformat(), shadow_name="topdecile_clf_blend_leg",
                        status="fault"),
                _record(D0.isoformat(), shadow_name="topdecile_clf_blend_leg",
                        status="fault")]
        jsonl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        monkeypatch.setattr(sentinel, "SHADOW_HEALTH_JSONL", str(jsonl))
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   purpose="the certified line")
        sent: list = []
        monkeypatch.setattr(sentinel, "alert",
                            lambda t, b, **kw: sent.append((t, b)))
        out: list = []
        rc = sentinel._patrol_lane(clf, [D1, D0], D0, out)
        assert rc == sentinel.EXIT_ALARM and out
        assert "topdecile_clf_blend_leg" in sent[0][0]
        assert "the certified line" in sent[0][1]

    def test_load_failure_body_names_the_failing_lane_not_the_default(
        self, tmp_path, monkeypatch
    ):
        # Regression: check_{feed_dark,load_failure,degraded}_streak used to
        # interpolate the module-global SHADOW_NAME into the alert BODY
        # regardless of which lane was patrolling, so a clf-lane failure
        # would page with a title naming the clf lane but a body claiming
        # 'hf_patchtst' (the default lane) died — misidentifying the broken
        # feed to the operator.
        jsonl = tmp_path / "health.jsonl"
        recs = [_record(D1.isoformat(), shadow_name="topdecile_clf_blend_leg",
                        loaded=False, n_scored=0, coverage_frac=0.0,
                        artifact_resolved=False, load_error="artifact_not_found",
                        actionable=False, reasons=["artifact_unresolved"]),
                _record(D0.isoformat(), shadow_name="topdecile_clf_blend_leg",
                        loaded=False, n_scored=0, coverage_frac=0.0,
                        artifact_resolved=False, load_error="artifact_not_found",
                        actionable=False, reasons=["artifact_unresolved"])]
        jsonl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        monkeypatch.setattr(sentinel, "SHADOW_HEALTH_JSONL", str(jsonl))
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None)
        sent: list = []
        monkeypatch.setattr(sentinel, "alert",
                            lambda t, b, **kw: sent.append((t, b)))
        out: list = []
        rc = sentinel._patrol_lane(clf, [D1, D0], D0, out)
        assert rc == sentinel.EXIT_ALARM and out
        title, body = sent[0]
        assert "LOAD FAILURE" in body
        assert "'topdecile_clf_blend_leg'" in body
        assert f"'{sentinel.SHADOW_NAME}'" not in body


# ---------------------------------------------------------------------------
# MLflow fallback for the clf lane (codex HIGH, 2026-07-29): a lane with
# runs_db=None and no producer writing shadow_scorer_health.v1 records for it
# had NO observable health signal at all — read_health_records() returned all
# None and _patrol_lane() printed "liveness domain, skip" forever, silently.
# This wires the SAME comparison.json locator rq104_blend_readout.py already
# proves works daily, against the real emitted artifact shape (no
# run_date/shadow_name columns — mtime-date fallback), so the lane is
# actually observed instead of registered-but-blind.
# ---------------------------------------------------------------------------

class TestMlflowFallback:
    def test_no_mlruns_dir_returns_empty(self, tmp_path):
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(tmp_path / "absent"))
        assert sentinel._read_from_mlflow([D0, D1], clf) == {}

    def test_day_with_no_live_run_is_liveness_domain(self, tmp_path, monkeypatch):
        prod_db = _make_prod_runs_db(tmp_path, [])  # no live runs at all
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        mlruns = tmp_path / "mlruns"
        mlruns.mkdir()
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns))
        assert sentinel._read_from_mlflow([D0], clf) == {}

    def test_live_day_with_recorded_comparison_is_healthy(self, tmp_path, monkeypatch):
        prod_db = _make_prod_runs_db(tmp_path, [D0.isoformat()])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        mlruns = tmp_path / "mlruns"
        rows = [["AAPL", 0.1, 0.2, 0.1, 5, 3, 2],
                ["MSFT", 0.05, 0.01, -0.04, 10, 20, -10]]
        _write_comparison_json(mlruns, "exp1", "run1", rows, mtime_date=D0.isoformat())
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns))
        rec = sentinel._read_from_mlflow([D0], clf)[D0]
        assert rec.loaded is True
        assert rec.feed_present is True
        assert rec.n_scored == 2
        assert rec.source == "mlflow_comparison_fallback"
        cls, _ = sentinel.classify(rec)
        assert cls == sentinel.HEALTHY

    def test_live_day_with_no_matching_comparison_is_feed_dark(self, tmp_path, monkeypatch):
        prod_db = _make_prod_runs_db(tmp_path, [D0.isoformat()])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        mlruns = tmp_path / "mlruns"
        # a comparison.json exists, but its mtime tags a DIFFERENT date
        rows = [["AAPL", 0.1, 0.2, 0.1, 5, 3, 2]]
        _write_comparison_json(mlruns, "exp1", "run1", rows, mtime_date=D1.isoformat())
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns))
        rec = sentinel._read_from_mlflow([D0], clf)[D0]
        assert rec.loaded is False
        assert rec.feed_present is False
        cls, _ = sentinel.classify(rec)
        assert cls == sentinel.FEED_DARK

    def test_end_to_end_patrol_alarms_when_lane_silently_dark(self, tmp_path, monkeypatch):
        """The exact HIGH-finding scenario: live runs happened, the JSONL
        primary sink has nothing for this lane, and MLflow has no comparison
        table for it either -> the sentinel must now alarm, not silently
        print 'liveness domain, skip' over a genuinely dark feed."""
        streak_days = [D1, D0]
        prod_db = _make_prod_runs_db(tmp_path, [d.isoformat() for d in streak_days])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        monkeypatch.setattr(sentinel, "SHADOW_HEALTH_JSONL", str(tmp_path / "absent.jsonl"))
        mlruns = tmp_path / "mlruns"
        mlruns.mkdir()
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns), purpose="the certified line")
        sent: list = []
        monkeypatch.setattr(sentinel, "alert", lambda t, b, **kw: sent.append((t, b)))
        out: list = []
        rc = sentinel._patrol_lane(clf, streak_days, D0, out)
        assert rc == sentinel.EXIT_ALARM and out
        assert "topdecile_clf_blend_leg" in sent[0][0]

    def test_end_to_end_patrol_stays_quiet_when_recorded_daily(self, tmp_path, monkeypatch):
        streak_days = [D1, D0]
        prod_db = _make_prod_runs_db(tmp_path, [d.isoformat() for d in streak_days])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        monkeypatch.setattr(sentinel, "SHADOW_HEALTH_JSONL", str(tmp_path / "absent.jsonl"))
        mlruns = tmp_path / "mlruns"
        for i, d in enumerate(streak_days):
            rows = [["AAPL", 0.1, 0.2, 0.1, 5, 3, 2]]
            _write_comparison_json(mlruns, "exp1", f"run{i}", rows,
                                   mtime_date=d.isoformat())
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns))
        sent: list = []
        monkeypatch.setattr(sentinel, "alert", lambda t, b, **kw: sent.append((t, b)))
        out: list = []
        rc = sentinel._patrol_lane(clf, streak_days, D0, out)
        assert rc == 0 and not out and not sent

    def test_tagged_record_found_even_when_not_among_newest_20_untagged(
        self, tmp_path, monkeypatch
    ):
        """codex HIGH (2026-07-29): the locator scanned only the 20
        most-recently-modified comparison.json files, so a valid older record
        could be silently missed. The correctly TAGGED run has the OLDEST
        mtime here, with 20 unrelated untagged files modified more recently —
        it must still be found because the tag-based primary match scans
        every candidate, not just the newest 20."""
        prod_db = _make_prod_runs_db(tmp_path, [D0.isoformat()])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        mlruns = tmp_path / "mlruns"
        rows = [["AAPL", 0.1, 0.2, 0.1, 5, 3, 2]]
        _write_tagged_comparison_json(
            mlruns, "exp1", "run_target", rows,
            as_of_date=D0.isoformat(), shadow_name="topdecile_clf_blend_leg",
            mtime_date="2020-01-01",  # oldest by far
        )
        for i in range(20):
            _write_comparison_json(
                mlruns, "exp1", f"run_noise{i}", rows,
                mtime_date=D1.isoformat(),  # newer, and for a different date
            )
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns))
        rec = sentinel._read_from_mlflow([D0], clf)[D0]
        assert rec.loaded is True
        assert rec.n_scored == 1
        cls, _ = sentinel.classify(rec)
        assert cls == sentinel.HEALTHY

    def test_unrelated_tagged_comparison_for_other_lane_is_not_falsely_matched(
        self, tmp_path, monkeypatch
    ):
        """codex HIGH (2026-07-29): the locator never verified `shadow_name`
        against the actual run (production comparison.json has neither
        `run_date` nor `shadow_name` as payload columns), so a differently
        tagged lane's record could pass as a match. A comparison.json tagged
        for the OTHER lane (`hf_patchtst`), same date, newest mtime, must not
        satisfy the clf lane's health check — it should read as FEED DARK,
        not silently borrow the other lane's record."""
        prod_db = _make_prod_runs_db(tmp_path, [D0.isoformat()])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        mlruns = tmp_path / "mlruns"
        rows = [["AAPL", 0.1, 0.2, 0.1, 5, 3, 2]]
        _write_tagged_comparison_json(
            mlruns, "exp1", "run_other_lane", rows,
            as_of_date=D0.isoformat(), shadow_name="hf_patchtst",
            mtime_date=D0.isoformat(),
        )
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns))
        rec = sentinel._read_from_mlflow([D0], clf)[D0]
        assert rec.loaded is False
        assert rec.feed_present is False
        cls, _ = sentinel.classify(rec)
        assert cls == sentinel.FEED_DARK

    def test_tagged_match_wins_over_touched_untagged_file_with_matching_mtime(
        self, tmp_path, monkeypatch
    ):
        """codex HIGH (2026-07-29): file mtime is not immutable — a
        touch/copy/retry can make an unrelated file's mtime match `run_date`
        by coincidence. An untagged decoy with the right mtime-date must lose
        to the correctly tagged record for a DIFFERENT date once any tagged
        candidates exist in the tree at all (tags are authoritative)."""
        prod_db = _make_prod_runs_db(tmp_path, [D0.isoformat()])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        mlruns = tmp_path / "mlruns"
        decoy_rows = [["ZZZZ", 9.9, 9.9, 0.0, 1, 1, 0],
                      ["YYYY", 9.9, 9.9, 0.0, 2, 2, 0],
                      ["XXXX", 9.9, 9.9, 0.0, 3, 3, 0]]
        # untagged decoy whose mtime happens to fall on D0 (the touch/retry case)
        _write_comparison_json(mlruns, "exp1", "run_decoy", decoy_rows,
                               mtime_date=D0.isoformat())
        real_rows = [["AAPL", 0.1, 0.2, 0.1, 5, 3, 2]]
        _write_tagged_comparison_json(
            mlruns, "exp1", "run_real", real_rows,
            as_of_date=D0.isoformat(), shadow_name="topdecile_clf_blend_leg",
            mtime_date="2020-01-01",
        )
        clf = sentinel.WatchedLane(name="topdecile_clf_blend_leg", runs_db=None,
                                   mlruns_dir=str(mlruns))
        rec = sentinel._read_from_mlflow([D0], clf)[D0]
        assert rec.loaded is True
        # 1 row (the tagged "run_real"), not 3 (the untagged same-mtime-date decoy)
        assert rec.n_scored == 1
        assert rec.n_candidates == 1


# --- 2026-07-30: the DB fallback matched the lane differently from the JSONL path --
# The served lane is `hf_patchtst_pt07_strict_seed44_previous_primary`. The JSONL
# branch used `_matches_shadow_lane` (prefix); this branch used SQL `=` (exact). So
# whenever the JSONL sink did not cover a date, the fallback found ZERO rows and the
# sentinel reported "LOAD FAILURE ... ZERO shadow scores" while the pipeline's own
# record for the same date said loaded=True, n_scored=77 and 85, stale_622d.
# Wrong, and MORE alarming than the truth.

import sqlite3 as _sqlite3


def _mini_db(path, scorer_name, n=5):
    c = _sqlite3.connect(path)
    c.executescript(
        # Schema transcribed from the real query at _derive_day_record: it selects
        # run_id + training_cutoff and filters WHERE run_type='live'. My first
        # fixture omitted run_type and the tests failed on the FIXTURE, not the fix.
        "CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, run_type TEXT,"
        " training_cutoff TEXT);"
        "CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, active_scorer TEXT,"
        " model_type TEXT);")
    c.execute("INSERT INTO pipeline_runs VALUES ('r1','2026-07-28','live','2024-11-14')")  # run_type='live'

    for i in range(n):
        c.execute("INSERT INTO candidate_scores VALUES ('r1',?,?,NULL)",
                  (f"T{i}", scorer_name))
    c.commit(); c.close()


def test_the_DECORATED_lane_name_is_counted_by_the_db_fallback(tmp_path):
    """THE DEFECT. The real served name carries a suffix; SQL `=` rejected it."""
    db = tmp_path / "runs.db"
    _mini_db(db, "hf_patchtst_pt07_strict_seed44_previous_primary", n=5)
    conn = sentinel._open_db_readonly(str(db))
    rec = sentinel._derive_day_record(conn, dt.date(2026, 7, 28))
    conn.close()
    assert rec is not None
    assert rec.n_scored == 5, rec
    assert rec.loaded is True


def test_the_bare_lane_name_still_counts(tmp_path):
    """Anti-regression: the exact form must keep working, or the fix trades one
    blind spot for another."""
    db = tmp_path / "runs.db"
    _mini_db(db, sentinel.SHADOW_NAME, n=3)
    conn = sentinel._open_db_readonly(str(db))
    rec = sentinel._derive_day_record(conn, dt.date(2026, 7, 28))
    conn.close()
    assert rec.n_scored == 3 and rec.loaded is True


def test_an_UNRELATED_scorer_is_NOT_counted(tmp_path):
    """The matcher must still discriminate. A prefix rule that accepted everything
    would make the sentinel report a healthy shadow lane forever."""
    db = tmp_path / "runs.db"
    _mini_db(db, "xgb_prod_panel", n=7)
    conn = sentinel._open_db_readonly(str(db))
    rec = sentinel._derive_day_record(conn, dt.date(2026, 7, 28))
    conn.close()
    assert rec.n_scored == 0 and rec.loaded is False


def test_a_lookalike_prefix_is_NOT_counted(tmp_path):
    """`hf_patchtstXX` shares the prefix but is a different lane; the matcher
    requires the exact name or an underscore-delimited suffix."""
    db = tmp_path / "runs.db"
    _mini_db(db, sentinel.SHADOW_NAME + "XX", n=4)
    conn = sentinel._open_db_readonly(str(db))
    rec = sentinel._derive_day_record(conn, dt.date(2026, 7, 28))
    conn.close()
    assert rec.n_scored == 0, "prefix matching must not swallow a neighbouring lane"


def test_the_two_paths_share_ONE_matcher():
    """The durable half. If a second matcher is ever expressed in SQL, the copy that
    runs will not be the copy a reader finds first — the twin-implementation class
    this programme keeps hitting."""
    src = (Path(sentinel.__file__)).read_text()
    assert "active_scorer = ? OR model_type = ?" not in src
    assert src.count("_matches_shadow_lane") >= 3


def test_an_ALL_NULL_scorer_column_yields_loaded_None_not_False(tmp_path):
    """"The DB does not record it" is not "the shadow scored nothing".

    Measured 2026-07-30: since 2026-07-22 every candidate_scores row in
    runs.alpaca_shadow.db carries active_scorer = NULL — 88/85/85/95/360/98 rows on
    six live dates, ZERO identifiable under ANY matcher, while the pipeline's own
    JSONL for the same dates says loaded=True, n_scored=77/85. Reporting False there
    asserts a fact the store cannot support."""
    db = tmp_path / "runs.db"
    c = _sqlite3.connect(db)
    c.executescript(
        "CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, run_type TEXT,"
        " training_cutoff TEXT);"
        "CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, active_scorer TEXT,"
        " model_type TEXT);")
    c.execute("INSERT INTO pipeline_runs VALUES ('r1','2026-07-28','live','2024-11-14')")
    for i in range(9):
        c.execute("INSERT INTO candidate_scores VALUES ('r1',?,NULL,NULL)", (f"T{i}",))
    c.commit(); c.close()
    conn = sentinel._open_db_readonly(str(db))
    rec = sentinel._derive_day_record(conn, dt.date(2026, 7, 28))
    conn.close()
    assert rec.loaded is None, rec
    assert rec.n_scored == 0


def test_a_populated_scorer_column_still_yields_a_BOOLEAN(tmp_path):
    """Anti-vacuity: the None must be reserved for the uninformative case, or every
    reading becomes 'unknown' and the sentinel says nothing at all."""
    db = tmp_path / "runs.db"
    _mini_db(db, "xgb_prod_panel", n=4)
    conn = sentinel._open_db_readonly(str(db))
    rec = sentinel._derive_day_record(conn, dt.date(2026, 7, 28))
    conn.close()
    assert rec.loaded is False and rec.n_scored == 0


class TestAlarmIsDistinguishableFromCrash:
    """GOAL-1 #622: a crashed watchdog and an alarming watchdog must not look the same.

    `sys.exit(main())` means an uncaught exception exits **1**. While the alarm also
    returned 1, `launchctl list` showed `exit=1` for both "did its job, found a problem"
    and "crashed, found nothing" — and nothing else in the record disambiguated them.
    Measured 2026-07-31: this job's live last exit IS 1, and it was not possible to say
    which of the two had happened.
    """

    def test_the_alarm_code_is_not_the_crash_code(self):
        """The whole of the change, in one assertion."""
        assert sentinel.EXIT_ALARM != 1, "an alarm must not collide with an exception exit"
        assert sentinel.EXIT_ALARM != 0, "an alarm must not look like success"
        assert sentinel.EXIT_ALARM != 2, "2 is argparse's usage error"

    def test_the_codes_stay_a_partition_under_bitwise_OR(self):
        """`main()` aggregates lanes with `rc |= _patrol_lane(...)`.

        OR-ing must not manufacture a value that means something else: clean lanes
        contribute 0, alarming lanes contribute EXIT_ALARM, so any mix is either 0 or
        EXIT_ALARM and never 1.
        """
        for combo in ([0], [0, 0], [sentinel.EXIT_ALARM], [0, sentinel.EXIT_ALARM],
                      [sentinel.EXIT_ALARM, sentinel.EXIT_ALARM, 0]):
            rc = 0
            for c in combo:
                rc |= c
            assert rc in (0, sentinel.EXIT_ALARM), (combo, rc)
            assert rc != 1


# ---------------------------------------------------------------------------
# #758: the momentum lane (`momentum_residual_v0_shadow`, config kind
# `momentum_residual`) — watched BEFORE its config entry (strategy-104#77)
# merges. These drive main() over the REAL production registry and pin BOTH
# sides of the transition the issue names:
#   before the merge (no momentum entry in the served config) the sentinel must
#   not false-alarm — without the pre-activation gate, the MLflow fallback
#   fabricates FEED DARK records out of every live-run day for a lane that
#   cannot have evidence yet;
#   after the merge, a feed-dark or load-failed momentum lane must page, and
#   the designed pre-first-publish state (`not_yet_published`, an expected
#   skip per pipeline#253) must not.
# ---------------------------------------------------------------------------

MOMENTUM = "momentum_residual_v0_shadow"
CLF = "topdecile_clf_blend_leg"
CLF_DECL = {"name": CLF, "kind": "xgb"}
MOM_DECL = {"name": MOMENTUM, "kind": "momentum_residual"}


def _clf_healthy_jsonl():
    """Healthy clf records for the window, so every verdict in these tests is
    about the MOMENTUM lane, never clf noise."""
    return [_record(D1.isoformat(), shadow_name=CLF),
            _record(D0.isoformat(), shadow_name=CLF)]


def _run_production(tmp_path, *, shadows, jsonl=None, prod_live=(),
                    momentum_mlflow_dates=(), as_of=AS_OF, cfg_mtime=None):
    """Drive main() over the REAL `watched_lanes()` registry (unpatched),
    against a config declaring `shadows`, a production runs DB with live rows
    on `prod_live`, and an mlruns tree carrying TAGGED momentum comparisons for
    `momentum_mlflow_dates`. Returns (rc, alerts)."""
    alerts: list[tuple[str, str]] = []
    cfg = {"ranking": {"panel_scoring": {"kind": "xgb", "shadow_models": shadows}}}
    cfg_path = tmp_path / "strategy_config.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    if cfg_mtime is not None:
        # backdate the arming instant (the config file's mtime) for
        # arming-window tests
        t = dt.datetime.combine(cfg_mtime, dt.time(12, 0)).timestamp()
        os.utime(cfg_path, (t, t))
    jsonl_path = tmp_path / "shadow_scorer_health.jsonl"
    if jsonl is not None:
        jsonl_path.write_text("\n".join(json.dumps(r) for r in jsonl) + "\n")
    prod_db = _make_prod_runs_db(tmp_path, [d.isoformat() for d in prod_live])
    mlruns = tmp_path / "mlruns"
    mlruns.mkdir(exist_ok=True)
    for i, d in enumerate(momentum_mlflow_dates):
        _write_tagged_comparison_json(
            mlruns, "exp1", f"mom_run{i}", [["AAPL", 0.1, 0.2, 0.1, 5, 3, 2]],
            as_of_date=d.isoformat(), shadow_name=MOMENTUM,
            mtime_date=d.isoformat())
    with (
        patch.object(sentinel, "is_session_day", return_value=True),
        patch.object(sentinel, "SHADOW_DB", str(tmp_path / "no_shadow_db_here")),
        patch.object(sentinel, "SHADOW_HEALTH_JSONL", str(jsonl_path)),
        patch.object(sentinel, "STREAK_N", 2),
        patch.object(sentinel, "MLRUNS_DIR", str(mlruns)),
        patch.object(sentinel, "PROD_RUNS_DB", prod_db),
        patch.object(sentinel, "alert", lambda t, b, **kw: alerts.append((t, b))),
    ):
        rc = sentinel.main(["--as-of", as_of, "--config", str(cfg_path)])
    return rc, alerts


class TestMomentumTransition:
    def test_BEFORE_the_config_merge_the_undeclared_lane_stays_quiet(self, tmp_path):
        """The pre-#77 state: live runs happen, the config does not declare the
        momentum lane, and no momentum evidence exists anywhere. Without the
        pre-activation gate this pages FEED DARK forever (the MLflow fallback
        fabricates dark records for every live-run day); the anti-vacuity twin
        below proves the SAME evidence alarms once the config declares the
        lane, so this quiet is the gate's doing, not a dead detector's."""
        rc, alerts = _run_production(
            tmp_path, shadows=[CLF_DECL], jsonl=_clf_healthy_jsonl(),
            prod_live=(D1, D0))
        assert rc == 0 and not alerts

    def test_AFTER_the_merge_a_never_reported_lane_arms_then_alarms(self, tmp_path, capsys):
        """The anti-vacuity twin, revised 2026-08-02 (measured on the machine
        the day the momentum pin landed): a DECLARED lane with no record EVER
        is in its ARMING window — the patrol's look-back predates the
        declaration, so paging FEED DARK off those sessions manufactures an
        alarm from days the lane could not have reported on. With fewer than
        ARMING_DARK_SESSIONS live-run sessions it reports ARMED (printed,
        rc 0, no page). The anti-vacuity BOUND stays: once that many
        consecutive live-run sessions show still no record ever, the lane
        falls through and FEED DARK pages naming it — a miswired lane cannot
        idle as INFO forever."""
        # (a) two live-run sessions, no momentum record ever: ARMED, no page.
        rc, alerts = _run_production(
            tmp_path, shadows=[CLF_DECL, MOM_DECL], jsonl=_clf_healthy_jsonl(),
            prod_live=(D1, D0))
        assert rc == 0 and not alerts
        assert "ARMED" in capsys.readouterr().out
        # (b) grace exhausted: ARMING_DARK_SESSIONS live-run sessions and
        # still no record ever -> the full patrol fires FEED DARK.
        d2, d3, d4 = (dt.date(2026, 7, 14), dt.date(2026, 7, 13),
                      dt.date(2026, 7, 12))
        sub = tmp_path / "grace_exhausted"
        sub.mkdir()
        rc, alerts = _run_production(
            sub, shadows=[CLF_DECL, MOM_DECL], jsonl=_clf_healthy_jsonl(),
            prod_live=(d4, d3, d2, D1, D0), cfg_mtime=dt.date(2026, 7, 11))
        assert rc == sentinel.EXIT_ALARM
        assert len(alerts) == 1, alerts  # clf stayed quiet; only momentum paged
        title, body = alerts[0]
        assert MOMENTUM in title
        assert "DARK" in body

    def test_AFTER_the_merge_not_yet_published_is_quiet(self, tmp_path):
        """The designed pre-first-publish window (pipeline#253's
        `not_yet_published`, an expected skip): the entry is merged but the
        weekly train job has not published its first artifact. status drives
        classification, so this must be as quiet as any expected_skip."""
        jsonl = _clf_healthy_jsonl() + [
            _record(d.isoformat(), shadow_name=MOMENTUM, kind="momentum_residual",
                    status="expected_skip", state="not_yet_published",
                    loaded=False, n_scored=0, coverage_frac=None,
                    reasons=["ledger_has_no_published_rows"])
            for d in (D1, D0)]
        rc, alerts = _run_production(
            tmp_path, shadows=[CLF_DECL, MOM_DECL], jsonl=jsonl,
            prod_live=(D1, D0))
        assert rc == 0 and not alerts

    def test_AFTER_the_merge_a_load_failed_momentum_lane_alarms(self, tmp_path):
        jsonl = _clf_healthy_jsonl() + [
            _record(d.isoformat(), shadow_name=MOMENTUM, kind="momentum_residual",
                    status="fault", state="load_failed", loaded=False,
                    n_scored=0, coverage_frac=None,
                    reasons=["ledger_tail_verification_failed"])
            for d in (D1, D0)]
        rc, alerts = _run_production(
            tmp_path, shadows=[CLF_DECL, MOM_DECL], jsonl=jsonl,
            prod_live=(D1, D0))
        assert rc == sentinel.EXIT_ALARM
        assert len(alerts) == 1, alerts
        title, body = alerts[0]
        assert MOMENTUM in title
        assert "LOAD FAILURE" in body
        assert f"'{MOMENTUM}'" in body
        assert "ledger_tail_verification_failed" in body

    def test_a_single_fault_day_does_not_page(self, tmp_path):
        """Streak discipline holds for the new lane: one bad day is a hiccup,
        not a page — including the merge-straddling day itself."""
        jsonl = _clf_healthy_jsonl() + [
            _record(D1.isoformat(), shadow_name=MOMENTUM, kind="momentum_residual",
                    status="expected_skip", state="not_yet_published",
                    loaded=False, n_scored=0, coverage_frac=None),
            _record(D0.isoformat(), shadow_name=MOMENTUM, kind="momentum_residual",
                    status="fault", state="load_failed", loaded=False,
                    n_scored=0, coverage_frac=None),
        ]
        rc, alerts = _run_production(
            tmp_path, shadows=[CLF_DECL, MOM_DECL], jsonl=jsonl,
            prod_live=(D1, D0))
        assert rc == 0 and not alerts

    def test_a_healthy_momentum_mlflow_feed_covers_a_jsonl_gap(self, tmp_path):
        """The bootstrap analog the clf lane already has: JSONL carries nothing
        for the lane but MLflow has its tagged comparisons -> quiet."""
        rc, alerts = _run_production(
            tmp_path, shadows=[CLF_DECL, MOM_DECL], jsonl=_clf_healthy_jsonl(),
            prod_live=(D1, D0), momentum_mlflow_dates=(D1, D0))
        assert rc == 0 and not alerts

    def test_a_lane_REMOVED_after_reporting_still_alarms_absent_from_config(
        self, tmp_path
    ):
        """The gate must not be a derivation in disguise (orch#702): a lane the
        config no longer declares but which HAS reported here falls through to
        the full patrol, and the orch#689 ABSENT FROM CONFIG alarm still fires."""
        jsonl = _clf_healthy_jsonl() + [
            _record("2026-07-10", shadow_name=MOMENTUM, kind="momentum_residual")]
        rc, alerts = _run_production(
            tmp_path, shadows=[CLF_DECL], jsonl=jsonl, prod_live=())
        assert rc == sentinel.EXIT_ALARM
        assert any(MOMENTUM in t and "ABSENT FROM CONFIG" in t for t, _ in alerts), alerts

    def test_an_unreadable_config_never_arms_the_gate(self, tmp_path):
        """'Could not read the config' must not impersonate 'not declared': with
        a broken config the gate stays off and the patrol runs — here the dark
        momentum lane still pages (plus the UNAVAILABLE config finding)."""
        alerts: list = []
        jsonl_path = tmp_path / "health.jsonl"
        jsonl_path.write_text(
            "\n".join(json.dumps(r) for r in _clf_healthy_jsonl()) + "\n")
        prod_db = _make_prod_runs_db(tmp_path, [D1.isoformat(), D0.isoformat()])
        mlruns = tmp_path / "mlruns"
        mlruns.mkdir()
        bad_cfg = tmp_path / "broken.json"
        bad_cfg.write_text("{not json", encoding="utf-8")
        with (
            patch.object(sentinel, "is_session_day", return_value=True),
            patch.object(sentinel, "SHADOW_HEALTH_JSONL", str(jsonl_path)),
            patch.object(sentinel, "STREAK_N", 2),
            patch.object(sentinel, "MLRUNS_DIR", str(mlruns)),
            patch.object(sentinel, "PROD_RUNS_DB", prod_db),
            patch.object(sentinel, "alert", lambda t, b, **kw: alerts.append((t, b))),
        ):
            rc = sentinel.main(["--as-of", AS_OF, "--config", str(bad_cfg)])
        assert rc == sentinel.EXIT_ALARM
        assert any(MOMENTUM in t for t, _ in alerts), alerts

    def test_gate_unit_none_means_ungated(self, tmp_path, monkeypatch):
        """Direct _patrol_lane callers (and a config-less machine) keep today's
        behavior: declared_lanes=None never gates."""
        prod_db = _make_prod_runs_db(tmp_path, [D1.isoformat(), D0.isoformat()])
        monkeypatch.setattr(sentinel, "PROD_RUNS_DB", prod_db)
        monkeypatch.setattr(sentinel, "SHADOW_HEALTH_JSONL",
                            str(tmp_path / "absent.jsonl"))
        mlruns = tmp_path / "mlruns"
        mlruns.mkdir()
        lane = sentinel.WatchedLane(name=MOMENTUM, runs_db=None,
                                    mlruns_dir=str(mlruns))
        sent: list = []
        monkeypatch.setattr(sentinel, "alert", lambda t, b, **kw: sent.append((t, b)))
        out: list = []
        assert sentinel._patrol_lane(lane, [D1, D0], D0, out) == sentinel.EXIT_ALARM
        out2: list = []
        rc = sentinel._patrol_lane(lane, [D1, D0], D0, out2,
                                   declared_lanes=[CLF])
        assert rc == 0 and not out2


# ---------------------------------------------------------------------------
# #758 acknowledgement trail: a momentum alarm must be DISPOSITIONABLE in the
# sentinel ack ledger without also swallowing a crash. The ledger machinery is
# the degradation sentinel's (job-level, keyed by launchd label + exit code);
# these bind this sentinel's EXIT_ALARM to it.
# ---------------------------------------------------------------------------

class TestMomentumAckTrail:
    JOB = "com.renquant.rq104-shadow-scorer-sentinel"

    @staticmethod
    def _ack_mod():
        import importlib.util
        root = Path(__file__).resolve().parent.parent
        mod_path = root / "ops" / "renquant104" / "rq104_degradation_sentinel.py"
        d = str(mod_path.parent)
        if d not in sys.path:
            sys.path.insert(0, d)
        spec = importlib.util.spec_from_file_location("rq104_ack_for_shadow", mod_path)
        m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        return m

    def test_the_job_label_is_the_real_installed_one(self):
        """The ack ledger is keyed by launchd label; an ack written under a
        guessed key covers nothing. Bind the key these tests use to the plist."""
        plist = (Path(__file__).resolve().parent.parent / "ops" / "renquant104"
                 / f"{self.JOB}.plist").read_text(encoding="utf-8")
        assert f"<string>{self.JOB}</string>" in plist

    def test_an_ack_of_EXIT_ALARM_covers_an_alarm_and_never_a_crash(self):
        A = self._ack_mod()
        row = {"acked_exit_codes": [sentinel.EXIT_ALARM]}
        assert A.ack_covers_exit(
            row, f"{self.JOB} (last exit {sentinel.EXIT_ALARM})") is True
        assert A.ack_covers_exit(row, f"{self.JOB} (last exit 1)") is False
        assert A.ack_covers_exit(row, f"{self.JOB} (last exit 3)") is False

    def test_no_standing_ack_pre_dispositions_the_momentum_alarm(self):
        """The first momentum-lane page must SURFACE: the checked-in ledger must
        not already silence this job's EXIT_ALARM before any human has seen one."""
        ledger_path = (Path(__file__).resolve().parent.parent / "ops"
                       / "renquant104" / "sentinel_acks.json")
        row = json.loads(ledger_path.read_text(encoding="utf-8")).get(self.JOB)
        if row is not None:
            assert sentinel.EXIT_ALARM not in row.get("acked_exit_codes", []), (
                "sentinel_acks.json already covers EXIT_ALARM for the shadow "
                "scorer sentinel — a momentum alarm would be born silenced")


# ---------------------------------------------------------------------------
# default_strategy_config: the pin-materialised clone must outrank the dev
# sibling (2026-08-02; the wrong-object class of RenQuant#553). Measured on
# the machine: the sibling sat behind the lock and the patrol reported a
# retired lane as declared and the momentum lane as undeclared, while the
# PINNED config said the opposite.
# ---------------------------------------------------------------------------

def _fake_tree(tmp_path, *, pinned: bool, sibling: bool):
    """github-root layout with the sentinel file 3 levels deep, mirroring
    <github>/renquant-orchestrator-run/ops/renquant104/<file>."""
    gh = tmp_path / "github"
    sent_dir = gh / "renquant-orchestrator-run" / "ops" / "renquant104"
    sent_dir.mkdir(parents=True)
    if pinned:
        p = (gh / "RenQuant" / ".subrepo_runtime" / "repos"
             / "renquant-strategy-104" / "configs")
        p.mkdir(parents=True)
        (p / "strategy_config.json").write_text("{}")
    if sibling:
        s = gh / "renquant-strategy-104" / "configs"
        s.mkdir(parents=True)
        (s / "strategy_config.json").write_text("{}")
    return sent_dir / "rq104_shadow_scorer_sentinel.py"


def _resolve_with_file_at(monkeypatch, fake_file):
    monkeypatch.delenv("RQ104_STRATEGY_CONFIG", raising=False)
    monkeypatch.setattr(sentinel.os.path, "abspath", lambda _: str(fake_file))
    return sentinel.default_strategy_config()


def test_default_config_prefers_the_pinned_clone(tmp_path, monkeypatch):
    fake = _fake_tree(tmp_path, pinned=True, sibling=True)
    got = _resolve_with_file_at(monkeypatch, fake)
    assert ".subrepo_runtime" in got, got


def test_default_config_falls_back_to_the_sibling(tmp_path, monkeypatch):
    fake = _fake_tree(tmp_path, pinned=False, sibling=True)
    got = _resolve_with_file_at(monkeypatch, fake)
    assert got.endswith("renquant-strategy-104/configs/strategy_config.json")
    assert ".subrepo_runtime" not in got


def test_default_config_env_override_wins(tmp_path, monkeypatch):
    fake = _fake_tree(tmp_path, pinned=True, sibling=True)
    monkeypatch.setenv("RQ104_STRATEGY_CONFIG", "/explicit/path.json")
    monkeypatch.setattr(sentinel.os.path, "abspath", lambda _: str(fake))
    assert sentinel.default_strategy_config() == "/explicit/path.json"
