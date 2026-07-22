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
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

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


def _run(tmp_path, *, run_rows=None, score_rows=None, jsonl=None,
         staleness_max=28, coverage_floor=0.80, streak=2, as_of=AS_OF):
    """Run main() with all seams patched; return (rc, alerts)."""
    alerts: list[tuple[str, str]] = []
    db_path = _make_shadow_db(tmp_path, run_rows or [], score_rows or [])
    jsonl_path = tmp_path / "shadow_scorer_health.jsonl"
    if jsonl is not None:
        jsonl_path.write_text("\n".join(json.dumps(r) for r in jsonl) + "\n")

    with (
        patch.object(sentinel, "is_session_day", return_value=True),
        patch.object(sentinel, "SHADOW_DB", db_path),
        patch.object(sentinel, "SHADOW_HEALTH_JSONL", str(jsonl_path)),
        patch.object(sentinel, "STALENESS_MAX_DAYS", staleness_max),
        patch.object(sentinel, "COVERAGE_FLOOR", coverage_floor),
        patch.object(sentinel, "STREAK_N", streak),
        patch.object(sentinel, "alert", lambda t, b, **kw: alerts.append((t, b))),
    ):
        rc = sentinel.main(["--as-of", as_of])
    return rc, alerts


def _healthy_db_rows(cutoff="2026-07-14"):
    run_rows = [("r_d1", D1.isoformat(), cutoff), ("r_d0", D0.isoformat(), cutoff)]
    score_rows = [(rid, tk, SHADOW, SHADOW)
                  for rid in ("r_d1", "r_d0")
                  for tk in ("AAPL", "MSFT", "NVDA", "AMZN")]
    return run_rows, score_rows


def _record(run_date, **kw):
    """A schema-v1 health record. Defaults to a HEALTHY, loaded, actionable day."""
    base = dict(
        schema="shadow_scorer_health.v1", shadow_name=SHADOW, kind="panel",
        loaded=True, load_error=None, artifact_path="patchtst/x.pt",
        artifact_resolved=True, artifact_resolved_path="/store/patchtst/x.pt",
        effective_train_cutoff_date="2026-07-10", staleness_days=6,
        config_fingerprint="cfg123", n_candidates=80, n_scored=78,
        coverage_frac=0.975, skip_reason=None, actionable=True, reasons=[],
        run_date=run_date, run_id=f"r_{run_date}",
    )
    base.update(kw)
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
        assert rc == 1
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
        assert rc == 1
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
        assert rc == 1
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
        assert rc == 1
        assert "coverage_0.40_below_0.80" in alerts[0][1]

    def test_db_derived_stale_alarms(self, tmp_path):
        # frozen cutoff 2024-11-13 vs as-of => ~610d > 28d ceiling (no actionable
        # from the DB, so derived).
        run_rows, score_rows = _healthy_db_rows(cutoff="2024-11-13")
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == 1
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
        assert rc == 1
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
        assert rc == 1
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
        assert rc == 1
        assert "DARK" in alerts[0][1]

    def test_feed_alive_but_shadow_dead_is_load_failure_not_dark(self, tmp_path):
        run_rows = [("r_d1", D1.isoformat(), None), ("r_d0", D0.isoformat(), None)]
        score_rows = [("r_d1", "AAPL", None, "XGBoost"), ("r_d0", "AAPL", None, "XGBoost")]
        rc, alerts = _run(tmp_path, run_rows=run_rows, score_rows=score_rows)
        assert rc == 1
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
        for key in ("shadow_name", "run_date", "loaded", "actionable", "n_scored"):
            assert sentinel.is_valid_v1_record(self._drop(D0.isoformat(), key)) is False, key

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
        assert rc == 1
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
    def test_disabled_state_actionable_true_stays_quiet(self, tmp_path):
        # #211's shadow_enabled=false path: an explicit expected/disabled record
        # (loaded=false but actionable=true) is NOT a fault => quiet, for a full
        # streak of them.
        jsonl = [
            _record(D1.isoformat(), loaded=False, n_scored=0, coverage_frac=None,
                    actionable=True, skip_reason="shadow_disabled",
                    reasons=["shadow_enabled_false"]),
            _record(D0.isoformat(), loaded=False, n_scored=0, coverage_frac=None,
                    actionable=True, skip_reason="shadow_disabled",
                    reasons=["shadow_enabled_false"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 0 and not alerts

    def test_real_fault_actionable_false_alarms(self, tmp_path):
        # same loaded=false shape but actionable=false (real fault) => alarm.
        jsonl = [
            _record(D1.isoformat(), loaded=False, n_scored=0, actionable=False,
                    reasons=["artifact_load_failed"]),
            _record(D0.isoformat(), loaded=False, n_scored=0, actionable=False,
                    reasons=["artifact_load_failed"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 1
        assert "LOAD FAILURE" in alerts[0][1]

    def test_loaded_but_actionable_false_is_fault(self, tmp_path):
        # scored fine, but the producer says the output is not trustworthy.
        jsonl = [
            _record(D1.isoformat(), actionable=False, reasons=["missing_provenance"]),
            _record(D0.isoformat(), actionable=False, reasons=["missing_provenance"]),
        ]
        rc, alerts = _run(tmp_path, jsonl=jsonl)
        assert rc == 1
        body = "\n".join(b for _, b in alerts)
        assert "DEGRADED" in body and "missing_provenance" in body

    def test_disabled_day_breaks_a_fault_streak(self, tmp_path):
        # one real-fault day + one expected/disabled day => streak broken, quiet.
        jsonl = [
            _record(D1.isoformat(), loaded=False, n_scored=0, actionable=False,
                    reasons=["artifact_load_failed"]),
            _record(D0.isoformat(), loaded=False, n_scored=0, actionable=True,
                    reasons=["shadow_enabled_false"]),
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
