"""Tests for ops/renquant105/rq105_liveness_check.py's NO-ADMIT-AWARE staleness
exemption for the admit-contingent post-close collector (intraday_pairing_logger).

Root cause fixed: intraday_pairing_logger writes ONE row per daily-ADMITTED name
(``pair_records``: "one raw-observation record per admitted name"). On a day
renquant105 admits 0 names — the current norm (no bull edge + most watchlist names
have no panel score, orch#799) — the collector legitimately writes 0 rows, so its
last complete row keeps YESTERDAY's date and the ``date != today`` check false-fires
"stale". The fix consults the AUTHORITATIVE session manifest
(``intraday_session_scheduler.default_manifest_path``): a completed session with
``counters.entries_count == 0`` makes the stale-dated paired_is EXPECTED, not a
failure. It still flags stale when the session admitted >=1 name (a real pairing-
logger failure) or when no completed session exists.

entry_timing_shadow is deliberately NOT admit-contingent (in production it evaluates
every ticker in the #216 tick feed, not the batch admits), so it is unaffected —
these tests assert the exemption is scoped to the admit-contingent collector only.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant105"))

import rq105_liveness_check as liveness  # noqa: E402
from rq105_liveness_check import (  # noqa: E402
    _completed_session_zero_admits,
    _data_output_fresh,
    _row_timestamp_pairing,
    check_collector_data_outputs,
)


def _write_paired_row(tmp_path: Path, date_iso: str, ticker: str = "ANET") -> Path:
    """A paired_is-style JSONL whose last complete row is dated ``date_iso``.
    Matches the required schema (``date`` + ``ticker`` non-empty strings); the
    pairing collector's rows carry no top-level event timestamp (file_mtime basis),
    so no timestamp field is needed."""
    path = tmp_path / "paired_is.jsonl"
    row = {
        "date": date_iso,
        "ticker": ticker,
        "record_kind": "observe_only_paired_arrival_obs",
        "admitted": True,
    }
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_manifest(
    tmp_path: Path, session_date: str, *, status: str, entries_count, mode="shadow"
) -> Path:
    """Write a session manifest at the exact location
    ``intraday_session_scheduler.default_manifest_path`` resolves under a data
    root, so ``_completed_session_zero_admits(as_of, tmp_path)`` reads it."""
    mdir = tmp_path / "logs" / "renquant105_pilot"
    mdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": "intraday_session_manifest",
        "session_date": session_date,
        "status": status,
        "mode_effective": mode,
        "tick_count": 32,
        "counters": {
            "entries_count": entries_count,
            "deployed_notional": 0.0,
            "turnover_notional": 0.0,
        },
    }
    (mdir / f"intraday_session_manifest_{session_date}.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    return tmp_path


class TestNoAdmitExemptionOnDataOutputFresh:
    """The core exemption at the ``date != today`` gate in ``_data_output_fresh``,
    exercised directly with the AUTHORITATIVE signal injected (decoupled from
    manifest I/O — the signal derivation is tested separately below)."""

    def test_a_completed_zero_admit_exempts_stale_dated_paired_is(self, tmp_path):
        """(a) Session completed + 0 admits + stale-dated paired_is -> OK, not a
        failure. The last row is yesterday's date and the file mtime is old on a
        real 0-admit day; the authoritative (True, ...) signal must exempt it."""
        today = dt.date(2026, 8, 13).isoformat()
        yesterday = dt.date(2026, 8, 12).isoformat()
        path = _write_paired_row(tmp_path, yesterday)

        ok, reason, row = _data_output_fresh(
            str(path), today, _row_timestamp_pairing, liveness._FILE_MTIME,
            no_admit_exempt=(True, "session manifest ...: status='completed', "
                                   "counters.entries_count=0"),
        )
        assert ok is True, reason
        assert "0 admitted names" in reason
        assert "legitimately wrote no rows" in reason
        assert row is not None and row["date"] == yesterday

    def test_b_admitted_ge1_stale_dated_paired_is_still_stale(self, tmp_path):
        """(b) Session admitted >=1 name + stale-dated paired_is -> STILL stale.
        The signal is (False, ...) (>=1 admit), so a yesterday-dated last row is a
        REAL pairing-logger failure and must keep flagging."""
        today = dt.date(2026, 8, 13).isoformat()
        yesterday = dt.date(2026, 8, 12).isoformat()
        path = _write_paired_row(tmp_path, yesterday)

        ok, reason, _ = _data_output_fresh(
            str(path), today, _row_timestamp_pairing, liveness._FILE_MTIME,
            no_admit_exempt=(False, "session counters.entries_count=3 (not a 0-admit day)"),
        )
        assert ok is False
        assert "(stale)" in reason
        assert "!= today" in reason

    def test_c_fresh_paired_is_ok_unchanged(self, tmp_path):
        """(c) A normally-fresh paired_is (row dated today, fresh mtime) -> OK via
        the UNCHANGED normal path, even when the exemption signal is present. It
        must NOT take the exemption branch (the row is not stale)."""
        today = dt.date.today().isoformat()  # fresh mtime file + today's row date
        path = _write_paired_row(tmp_path, today)

        # Present exemption signal — must be irrelevant because the row is fresh.
        ok, reason, _ = _data_output_fresh(
            str(path), today, _row_timestamp_pairing, liveness._FILE_MTIME,
            no_admit_exempt=(True, "would-exempt-but-not-needed"),
        )
        assert ok is True, reason
        assert "wrote no rows" not in reason  # took the normal fresh path

        # And with no signal at all (None) it is still OK — behavior unchanged.
        ok_none, reason_none, _ = _data_output_fresh(
            str(path), today, _row_timestamp_pairing, liveness._FILE_MTIME,
            no_admit_exempt=None,
        )
        assert ok_none is True, reason_none

    def test_stale_with_no_signal_is_unchanged_stale(self, tmp_path):
        """Guard: without any exemption signal (the pre-fix call shape), a stale-
        dated file still fails exactly as before."""
        today = dt.date(2026, 8, 13).isoformat()
        path = _write_paired_row(tmp_path, dt.date(2026, 8, 12).isoformat())
        ok, reason, _ = _data_output_fresh(
            str(path), today, _row_timestamp_pairing, liveness._FILE_MTIME,
        )
        assert ok is False
        assert "(stale)" in reason


class TestAuthoritativeZeroAdmitSignal:
    """``_completed_session_zero_admits`` reads the AUTHORITATIVE session manifest
    and fails toward alarming on any uncertainty."""

    def test_completed_zero_admit_is_true(self, tmp_path):
        as_of = dt.date(2026, 8, 13)
        _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
        ok, evidence = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is True, evidence
        assert "entries_count=0" in evidence
        assert "completed" in evidence

    def test_completed_with_admits_is_false(self, tmp_path):
        as_of = dt.date(2026, 8, 13)
        _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=3)
        ok, reason = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is False
        assert "entries_count=3" in reason

    def test_halted_session_zero_admits_is_false(self, tmp_path):
        """A halted/aborted session that happens to show 0 entries is NOT a
        legitimate 0-admit completion — the 'session didn't finish' signal must
        not be weakened."""
        as_of = dt.date(2026, 8, 13)
        _write_manifest(
            tmp_path, as_of.isoformat(), status="halted_tick_error", entries_count=0
        )
        ok, reason = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is False
        assert "not 'completed'" in reason

    def test_missing_manifest_is_false(self, tmp_path):
        """No completed session for today -> not exempt (existing 'session didn't
        run' behavior stands)."""
        ok, reason = _completed_session_zero_admits(dt.date(2026, 8, 13), tmp_path)
        assert ok is False
        assert "no session manifest" in reason

    def test_missing_counters_is_false(self, tmp_path):
        """A completed manifest whose entries_count is absent/None -> not exempt
        (fail toward alarming — never suppress on a missing count)."""
        as_of = dt.date(2026, 8, 13)
        _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=None)
        ok, reason = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is False
        assert "not a 0-admit day" in reason


class TestCheckCollectorDataOutputsIntegration:
    """End-to-end through the STABLE public interface: the exemption is scoped to
    the admit-contingent collector and driven by the authoritative signal."""

    def _patch_env(self, monkeypatch, tmp_path, *, admit_contingent, zero_admit):
        # Avoid the NYSE calendar import: bounds -> None so session_close_utc None.
        class _FakeCal:
            def session_bounds(self, day):
                return None

        monkeypatch.setattr(liveness, "_session_calendar", lambda: _FakeCal())
        monkeypatch.setattr(
            liveness, "_completed_session_zero_admits",
            lambda as_of, data_root: zero_admit,
        )
        path = _write_paired_row(tmp_path, dt.date(2026, 8, 12).isoformat())
        monkeypatch.setattr(
            liveness, "_data_outputs",
            lambda data_root: [
                ("intraday_pairing_logger", path, _row_timestamp_pairing,
                 liveness._FILE_MTIME, admit_contingent),
            ],
        )
        return path

    def test_admit_contingent_stale_is_ok_on_zero_admit_day(self, monkeypatch, tmp_path):
        self._patch_env(
            monkeypatch, tmp_path,
            admit_contingent=True, zero_admit=(True, "manifest: completed, entries_count=0"),
        )
        out = check_collector_data_outputs(Path(tmp_path), dt.date(2026, 8, 13))
        assert out["intraday_pairing_logger"]["status"] == "ok", out

    def test_admit_contingent_stale_still_flags_when_admits_ge1(self, monkeypatch, tmp_path):
        self._patch_env(
            monkeypatch, tmp_path,
            admit_contingent=True, zero_admit=(False, "entries_count=5"),
        )
        out = check_collector_data_outputs(Path(tmp_path), dt.date(2026, 8, 13))
        assert out["intraday_pairing_logger"]["status"] == "stale_or_missing", out

    def test_non_admit_contingent_ignores_zero_admit_signal(self, monkeypatch, tmp_path):
        """Even if today were 0-admit, a NON-admit-contingent collector's stale
        file still flags — the exemption must not leak to it."""
        self._patch_env(
            monkeypatch, tmp_path,
            admit_contingent=False, zero_admit=(True, "manifest: completed, entries_count=0"),
        )
        out = check_collector_data_outputs(Path(tmp_path), dt.date(2026, 8, 13))
        assert out["intraday_pairing_logger"]["status"] == "stale_or_missing", out
