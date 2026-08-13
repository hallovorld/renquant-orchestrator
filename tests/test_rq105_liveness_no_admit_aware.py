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
    """``_completed_session_zero_admits`` requires BOTH a completed session
    manifest AND a zero admission set from the collector's own query, and fails
    toward alarming on any uncertainty.

    These originally asserted on ``counters.entries_count``. That was the wrong
    object (review BLOCKER): the manifest counts intraday tick intents, while the
    collector pairs batch admissions from the runs DB. They now assert the
    corrected contract; the entries_count-only cases live in the module-level
    regressions below.
    """

    def test_completed_zero_admit_is_true(self, tmp_path, monkeypatch):
        as_of = dt.date(2026, 8, 13)
        _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
        _patch_admissions(monkeypatch, legacy=(), submitted=())
        ok, evidence = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is True, evidence
        assert "completed" in evidence
        assert "admissions" in evidence

    def test_completed_with_admits_is_false(self, tmp_path, monkeypatch):
        """Admits are counted from the COLLECTOR's query, not the manifest: a
        manifest saying 0 entries does not exempt a day with batch admissions."""
        as_of = dt.date(2026, 8, 13)
        _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
        _patch_admissions(monkeypatch, submitted=[_Name("ANET"), _Name("NVDA"), _Name("MU")])
        ok, reason = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is False
        assert "3" in reason and "names to pair" in reason

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

    def test_manifest_counters_no_longer_decide(self, tmp_path, monkeypatch):
        """The manifest's counters are no longer consulted for the admit signal.

        A completed manifest with NO counters at all is exempt when the
        collector's admission set is empty, and NOT exempt when it is not —
        proving the decision moved to the right object rather than merely being
        supplemented by it."""
        as_of = dt.date(2026, 8, 13)
        _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=None)

        _patch_admissions(monkeypatch, legacy=(), submitted=())
        ok, evidence = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is True, evidence

        _patch_admissions(monkeypatch, submitted=[_Name("ANET")])
        ok, reason = _completed_session_zero_admits(as_of, tmp_path)
        assert ok is False and "names to pair" in reason


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


# ---------------------------------------------------------------------------
# The admit signal must come from the collector's OWN admission query.
#
# Regression for the review BLOCKER: an earlier revision read
# `counters.entries_count` from the session manifest. That counts intraday tick
# intents; `collect_pairs()` pairs batch admissions resolved from the runs DB as
# load_admitted(T) UNION load_submitted_entries(resolve_admitting_run_date(T)).
# A session can COMPLETE with zero intraday entries while the batch admitted
# names that require pairing rows -- exempting on the manifest count would mark a
# stale paired_is OK and suppress a real collector failure.
# ---------------------------------------------------------------------------


class _Name:
    """Minimal stand-in for the collector's admitted-name record."""

    def __init__(self, ticker: str, signal_version: str = "v1") -> None:
        self.ticker = ticker
        self.signal_version = signal_version


def _patch_admissions(monkeypatch, *, legacy=(), submitted=(), admit_date="2026-08-12"):
    """Patch the exact functions `_pairing_admit_count` calls."""
    import types

    fake = types.ModuleType("renquant_orchestrator.intraday_pairing_logger")
    fake.DEFAULT_RUNS_DB = __file__  # any existing path; connect() is patched too
    fake.connect = lambda db: types.SimpleNamespace(close=lambda: None)
    fake.load_admitted = lambda conn, date, run_type="live": list(legacy)
    fake.resolve_admitting_run_date = lambda conn, date, run_type="live": admit_date
    fake.load_submitted_entries = (
        lambda conn, d, session_date=None, run_type="live": list(submitted)
    )
    monkeypatch.setitem(
        sys.modules, "renquant_orchestrator.intraday_pairing_logger", fake
    )


def test_zero_intraday_entries_but_nonempty_batch_admits_is_NOT_exempt(
    tmp_path: Path, monkeypatch
):
    """THE regression: completed session, manifest entries_count=0, but the batch
    admitted two names -> the collector owed pairing rows, so a stale row-date is
    a REAL failure and must not be exempted."""
    as_of = dt.date(2026, 8, 13)
    _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
    _patch_admissions(monkeypatch, submitted=[_Name("ANET"), _Name("NVDA")])

    ok, evidence = _completed_session_zero_admits(as_of, tmp_path)
    assert ok is False, f"exempted a day the collector owed rows for: {evidence}"
    assert "2" in evidence and "names to pair" in evidence


def test_zero_batch_admits_is_exempt(tmp_path: Path, monkeypatch):
    """The legitimate case is unchanged: completed session AND the collector's own
    admission query returns zero names."""
    as_of = dt.date(2026, 8, 13)
    _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
    _patch_admissions(monkeypatch, legacy=(), submitted=())

    ok, evidence = _completed_session_zero_admits(as_of, tmp_path)
    assert ok is True, evidence
    assert "0" in evidence


def test_legacy_selected_rows_alone_block_the_exemption(tmp_path: Path, monkeypatch):
    """`load_admitted` (the legacy same-session path) counts too -- the union is
    the admission set, not just the submitted-entries leg."""
    as_of = dt.date(2026, 8, 13)
    _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
    _patch_admissions(monkeypatch, legacy=[_Name("MSFT")], submitted=())

    ok, _ = _completed_session_zero_admits(as_of, tmp_path)
    assert ok is False


def test_dedupe_matches_the_collector(tmp_path: Path, monkeypatch):
    """Same (signal_version, ticker) in both legs is ONE admission, as the
    collector dedupes -- so the count cannot be inflated into a false alarm."""
    as_of = dt.date(2026, 8, 13)
    _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
    _patch_admissions(
        monkeypatch, legacy=[_Name("ANET")], submitted=[_Name("ANET")]
    )
    count, evidence = liveness._pairing_admit_count(as_of)
    assert count == 1, evidence


def test_unavailable_admission_source_fails_closed(tmp_path: Path, monkeypatch):
    """If the admission query cannot run, the staleness STANDS -- no exemption."""
    import types

    as_of = dt.date(2026, 8, 13)
    _write_manifest(tmp_path, as_of.isoformat(), status="completed", entries_count=0)
    fake = types.ModuleType("renquant_orchestrator.intraday_pairing_logger")
    fake.DEFAULT_RUNS_DB = str(tmp_path / "definitely-absent.db")
    monkeypatch.setitem(
        sys.modules, "renquant_orchestrator.intraday_pairing_logger", fake
    )
    ok, evidence = _completed_session_zero_admits(as_of, tmp_path)
    assert ok is False
    assert "staleness stands" in evidence
