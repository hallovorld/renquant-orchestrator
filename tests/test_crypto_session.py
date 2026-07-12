"""Tests for the 24/7 crypto session scheduler (D-C11)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from renquant_orchestrator.crypto_session import (
    CRYPTO_ENV_FLAG,
    CryptoSessionConfig,
    SessionWindow,
    SignalArtifactRef,
    SignalSnapshot,
    StopCoverageReport,
    TickResult,
    build_session_bundle,
    check_triple_gate,
    current_session_date,
    evaluate_tick,
    validate_digest,
    validate_signal_contract,
    validate_watermark,
    watermark_for_session,
)

UTC = dt.timezone.utc


def _enabled_config(tmp_path: Path, *, mode: str = "live") -> CryptoSessionConfig:
    return CryptoSessionConfig(
        enabled=True,
        mode=mode,
        kill_switch_path=tmp_path / "nonexistent_kill_switch",
    )


def _make_snapshot(session_date: dt.date) -> SignalSnapshot:
    return SignalSnapshot(
        session_date=session_date,
        bar_watermark_utc=watermark_for_session(session_date),
        universe_hash="test_hash",
        model_content_sha256="model_sha",
        calibrator_content_sha256="cal_sha",
    )


def _make_artifact_ref(snap: SignalSnapshot, tmp_path: Path) -> SignalArtifactRef:
    p = tmp_path / "signal_artifact.json"
    if not p.exists():
        p.write_text("{}")
    return SignalArtifactRef(
        expected_digest=snap.digest(),
        artifact_path=str(p),
        schema_version=1,
        producer_run_id="test-run-001",
    )


def _make_stop_coverage(
    now_utc: dt.datetime, *, mode: str = "live", violations: int = 0
) -> StopCoverageReport:
    return StopCoverageReport(
        timestamp_utc=now_utc,
        environment=mode,
        account_id="test-account-123",
        positions_covered=5,
        violations=violations,
        source_version="test-v1",
    )


# ── SessionWindow ────────────────────────────────────────────────────────────


class TestSessionWindow:
    def test_for_date(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12))
        assert w.open_utc == dt.datetime(2026, 7, 12, 0, 0, tzinfo=UTC)
        assert w.close_utc == dt.datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
        assert w.quiet_end_utc == dt.datetime(2026, 7, 12, 0, 15, tzinfo=UTC)

    def test_quiet_interval_start(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12))
        assert w.in_quiet_interval(dt.datetime(2026, 7, 12, 0, 0, tzinfo=UTC))

    def test_quiet_interval_inside(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12))
        assert w.in_quiet_interval(dt.datetime(2026, 7, 12, 0, 10, tzinfo=UTC))

    def test_quiet_interval_end_exclusive(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12))
        assert not w.in_quiet_interval(dt.datetime(2026, 7, 12, 0, 15, tzinfo=UTC))

    def test_configured_quiet_interval(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12), quiet_minutes=30)
        assert w.quiet_end_utc == dt.datetime(2026, 7, 12, 0, 30, tzinfo=UTC)
        assert w.in_quiet_interval(dt.datetime(2026, 7, 12, 0, 25, tzinfo=UTC))
        assert not w.in_quiet_interval(dt.datetime(2026, 7, 12, 0, 30, tzinfo=UTC))

    def test_is_active(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12))
        assert w.is_active(dt.datetime(2026, 7, 12, 12, 0, tzinfo=UTC))
        assert not w.is_active(dt.datetime(2026, 7, 13, 0, 0, tzinfo=UTC))

    def test_weekend_active(self):
        saturday = dt.date(2026, 7, 11)
        w = SessionWindow.for_date(saturday)
        assert w.is_active(dt.datetime(2026, 7, 11, 15, 0, tzinfo=UTC))


# ── SignalSnapshot ───────────────────────────────────────────────────────────


class TestSignalSnapshot:
    def test_digest_deterministic(self):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        d1 = snap.digest()
        d2 = snap.digest()
        assert d1 == d2
        assert len(d1) == 64

    def test_digest_changes_with_inputs(self):
        base = dict(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 12, 0, 0, tzinfo=UTC),
            universe_hash="abc123",
            model_content_sha256="model_hash",
            calibrator_content_sha256="cal_hash",
        )
        d1 = SignalSnapshot(**base).digest()
        d2 = SignalSnapshot(**{**base, "universe_hash": "xyz789"}).digest()
        assert d1 != d2


# ── Triple gate ──────────────────────────────────────────────────────────────


class TestTripleGate:
    def test_disabled_config(self, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "true")
        cfg = CryptoSessionConfig(enabled=False)
        ok, reason = check_triple_gate(cfg)
        assert not ok
        assert "enabled=false" in reason

    def test_missing_env_flag(self, monkeypatch):
        monkeypatch.delenv(CRYPTO_ENV_FLAG, raising=False)
        cfg = CryptoSessionConfig(enabled=True)
        ok, reason = check_triple_gate(cfg)
        assert not ok
        assert CRYPTO_ENV_FLAG in reason

    def test_kill_switch_present(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        kill_file = tmp_path / "kill"
        kill_file.touch()
        cfg = CryptoSessionConfig(enabled=True, kill_switch_path=kill_file)
        ok, reason = check_triple_gate(cfg)
        assert not ok
        assert "kill switch" in reason

    def test_all_gates_pass(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "true")
        kill_file = tmp_path / "kill"
        assert not kill_file.exists()
        cfg = CryptoSessionConfig(enabled=True, kill_switch_path=kill_file)
        ok, reason = check_triple_gate(cfg)
        assert ok


# ── Watermark validation ────────────────────────────────────────────────────


class TestWatermarkValidation:
    def test_watermark_is_session_midnight(self):
        wm = watermark_for_session(dt.date(2026, 7, 12))
        assert wm == dt.datetime(2026, 7, 12, 0, 0, tzinfo=UTC)

    def test_valid_watermark(self):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ok, reason = validate_watermark(snap, dt.date(2026, 7, 12))
        assert ok

    def test_future_watermark_rejected(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 12, 6, 0, tzinfo=UTC),
            universe_hash="h", model_content_sha256="m",
            calibrator_content_sha256="c",
        )
        ok, reason = validate_watermark(snap, dt.date(2026, 7, 12))
        assert not ok
        assert "future bars" in reason

    def test_stale_watermark_rejected(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
            universe_hash="h", model_content_sha256="m",
            calibrator_content_sha256="c",
        )
        ok, reason = validate_watermark(snap, dt.date(2026, 7, 12))
        assert not ok
        assert "stale" in reason

    def test_future_watermark_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
            universe_hash="h", model_content_sha256="m",
            calibrator_content_sha256="c",
        )
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert "future bars" in result.reason


# ── Digest verification ─────────────────────────────────────────────────────


class TestDigestVerification:
    def test_digest_match(self):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ok, reason = validate_digest(snap, snap.digest())
        assert ok

    def test_digest_mismatch_rejected(self):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ok, reason = validate_digest(snap, "wrong_digest_value")
        assert not ok
        assert "mismatch" in reason

    def test_missing_artifact_ref_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=None,
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert "fail-closed" in result.reason

    def test_digest_mismatch_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        af = tmp_path / "bad.json"
        af.write_text("{}")
        bad_ref = SignalArtifactRef(
            expected_digest="tampered_digest",
            artifact_path=str(af),
            schema_version=1,
            producer_run_id="test-run-001",
        )
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=bad_ref,
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert "mismatch" in result.reason


# ── Shadow mode blocks entries ──────────────────────────────────────────────


class TestShadowModeNonAdmission:
    def test_shadow_mode_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="shadow")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now, mode="shadow"),
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "shadow" in result.reason

    def test_paper_mode_allows_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now, mode="paper"),
        )
        assert result.entries_allowed


# ── Configured quiet interval ───────────────────────────────────────────────


class TestConfiguredQuietInterval:
    def test_configured_quiet_interval_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = CryptoSessionConfig(
            enabled=True, mode="live",
            kill_switch_path=tmp_path / "no_kill",
            quiet_interval_minutes=30,
        )
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 0, 20, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert result.is_quiet

    def test_after_configured_quiet_allows_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = CryptoSessionConfig(
            enabled=True, mode="live",
            kill_switch_path=tmp_path / "no_kill",
            quiet_interval_minutes=10,
        )
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 0, 12, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert result.entries_allowed


# ── Stop coverage ───────────────────────────────────────────────────────────


class TestStopCoverage:
    def test_missing_stop_coverage_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=None,
        )
        assert not result.entries_allowed
        assert "stop_coverage" in result.reason

    def test_violations_block_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now, violations=3),
        )
        assert not result.entries_allowed
        assert "violation" in result.reason

    def test_environment_mismatch_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now, mode="paper"),
        )
        assert not result.entries_allowed
        assert "environment mismatch" in result.reason

    def test_stale_report_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        stale_time = now - dt.timedelta(seconds=600)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(stale_time),
        )
        assert not result.entries_allowed
        assert "stale" in result.reason


# ── Signal contract validation ──────────────────────────────────────────────


class TestSignalContract:
    def test_valid(self):
        ok, _ = validate_signal_contract(_make_snapshot(dt.date(2026, 7, 12)))
        assert ok

    def test_empty_universe_hash(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=watermark_for_session(dt.date(2026, 7, 12)),
            universe_hash="", model_content_sha256="m",
            calibrator_content_sha256="c",
        )
        ok, reason = validate_signal_contract(snap)
        assert not ok
        assert "universe_hash" in reason

    def test_empty_model_hash(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=watermark_for_session(dt.date(2026, 7, 12)),
            universe_hash="h", model_content_sha256="",
            calibrator_content_sha256="c",
        )
        ok, reason = validate_signal_contract(snap)
        assert not ok
        assert "model_content_sha256" in reason

    def test_empty_calibrator_hash(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=watermark_for_session(dt.date(2026, 7, 12)),
            universe_hash="h", model_content_sha256="m",
            calibrator_content_sha256="",
        )
        ok, reason = validate_signal_contract(snap)
        assert not ok
        assert "calibrator_content_sha256" in reason

    def test_naive_watermark(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 12, 0, 0),
            universe_hash="h", model_content_sha256="m",
            calibrator_content_sha256="c",
        )
        ok, reason = validate_signal_contract(snap)
        assert not ok
        assert "timezone-aware" in reason

    def test_empty_fingerprint_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=watermark_for_session(dt.date(2026, 7, 12)),
            universe_hash="h", model_content_sha256="",
            calibrator_content_sha256="c",
        )
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert "model_content_sha256" in result.reason


# ── Artifact ref validation ─────────────────────────────────────────────────


class TestArtifactRefValidation:
    def test_valid_ref(self, tmp_path):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ref = _make_artifact_ref(snap, tmp_path)
        ok, _ = ref.validate()
        assert ok

    def test_nonexistent_path(self):
        ref = SignalArtifactRef(
            expected_digest="abc123",
            artifact_path="/nonexistent/path.json",
            schema_version=1,
            producer_run_id="run-1",
        )
        ok, reason = ref.validate()
        assert not ok
        assert "does not exist" in reason

    def test_wrong_schema_version(self, tmp_path):
        af = tmp_path / "art.json"
        af.write_text("{}")
        ref = SignalArtifactRef(
            expected_digest="abc123",
            artifact_path=str(af),
            schema_version=99,
            producer_run_id="run-1",
        )
        ok, reason = ref.validate()
        assert not ok
        assert "schema_version" in reason

    def test_invalid_ref_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        bad_ref = SignalArtifactRef(
            expected_digest=snap.digest(),
            artifact_path="/nonexistent/a.json",
            schema_version=1,
            producer_run_id="run-1",
        )
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=bad_ref,
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert "does not exist" in result.reason


# ── Stop coverage validation ────────────────────────────────────────────────


class TestStopCoverageValidation:
    def test_valid(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ok, _ = _make_stop_coverage(now).validate()
        assert ok

    def test_invalid_environment(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        r = StopCoverageReport(
            timestamp_utc=now, environment="shadow", account_id="acct",
            positions_covered=5, violations=0, source_version="v1",
        )
        ok, reason = r.validate()
        assert not ok
        assert "environment" in reason

    def test_naive_timestamp(self):
        now = dt.datetime(2026, 7, 12, 1, 0)
        r = StopCoverageReport(
            timestamp_utc=now, environment="live", account_id="acct",
            positions_covered=5, violations=0, source_version="v1",
        )
        ok, reason = r.validate()
        assert not ok
        assert "timezone-aware" in reason


# ── evaluate_tick ────────────────────────────────────────────────────────────


class TestEvaluateTick:
    def test_gate_failed_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.delenv(CRYPTO_ENV_FLAG, raising=False)
        cfg = _enabled_config(tmp_path)
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        )
        assert not result.entries_allowed
        assert result.exits_allowed

    def test_quiet_interval_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 0, 5, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert result.is_quiet

    def test_no_snapshot_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=None,
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "fail-closed" in result.reason

    def test_wrong_session_date_blocks(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 11))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert "mismatch" in result.reason

    def test_valid_tick_allows_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert result.entries_allowed
        assert result.exits_allowed
        assert result.signal_snapshot_digest == snap.digest()

    def test_weekend_entries_allowed(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        saturday = dt.date(2026, 7, 11)
        snap = _make_snapshot(saturday)
        now = dt.datetime(2026, 7, 11, 14, 30, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        assert result.entries_allowed

    def test_exits_always_allowed_even_kill_switched(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        kill_file = tmp_path / "kill"
        kill_file.touch()
        cfg = CryptoSessionConfig(enabled=True, mode="live", kill_switch_path=kill_file)
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert result.is_kill_switched


# ── TickResult serialization ─────────────────────────────────────────────────


class TestTickResultSerialization:
    def test_to_jsonable_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now),
        )
        j = result.to_jsonable()
        assert json.dumps(j)
        assert j["entries_allowed"] is True
        assert j["session_date"] == "2026-07-12"


# ── Session bundle ───────────────────────────────────────────────────────────


class TestSessionBundle:
    def test_bundle_v2(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ref = _make_artifact_ref(snap, tmp_path)
        ticks = [
            evaluate_tick(
                config=cfg,
                now_utc=dt.datetime(2026, 7, 12, h, 0, tzinfo=UTC),
                signal_snapshot=snap,
                artifact_ref=ref,
                stop_coverage=_make_stop_coverage(
                    dt.datetime(2026, 7, 12, h, 0, tzinfo=UTC)
                ),
            )
            for h in range(1, 4)
        ]
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        cov = _make_stop_coverage(now)
        bundle = build_session_bundle(
            config=cfg,
            session_date=dt.date(2026, 7, 12),
            tick_results=ticks,
            signal_snapshot=snap,
            artifact_ref=ref,
            stop_coverage=cov,
        )
        assert bundle["schema_version"] == 2
        assert bundle["environment"] == "live"
        assert bundle["quiet_interval_minutes"] == 15
        assert bundle["n_ticks"] == 3
        assert bundle["n_entries_allowed"] == 3
        assert bundle["signal_snapshot_digest"] == snap.digest()
        assert bundle["artifact_ref"]["producer_run_id"] == "test-run-001"
        assert bundle["stop_coverage"]["account_id"] == "test-account-123"
        assert json.dumps(bundle)

    def test_bundle_without_provenance(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        bundle = build_session_bundle(
            config=cfg,
            session_date=dt.date(2026, 7, 12),
            tick_results=[],
        )
        assert bundle["artifact_ref"] is None
        assert bundle["stop_coverage"] is None


# ── Config from dict ─────────────────────────────────────────────────────────


class TestConfigFromDict:
    def test_defaults(self):
        cfg = CryptoSessionConfig.from_dict({})
        assert not cfg.enabled
        assert cfg.tick_cadence_seconds == 900
        assert cfg.mode == "shadow"
        assert cfg.quiet_interval_minutes == 15

    def test_full_config(self):
        cfg = CryptoSessionConfig.from_dict({
            "crypto_trading": {
                "enabled": True,
                "tick_cadence_seconds": 300,
                "mode": "paper",
                "ntfy_topic": "test-crypto",
                "sleeve_budget_usd": 1500.0,
                "max_drawdown_pct": 8.0,
                "quiet_interval_minutes": 30,
            }
        })
        assert cfg.enabled
        assert cfg.tick_cadence_seconds == 300
        assert cfg.mode == "paper"
        assert cfg.sleeve_budget_usd == 1500.0
        assert cfg.max_drawdown_pct == 8.0
        assert cfg.quiet_interval_minutes == 30


# ── current_session_date ─────────────────────────────────────────────────────


class TestCurrentSessionDate:
    def test_utc_midnight_boundary(self):
        just_before = dt.datetime(2026, 7, 11, 23, 59, 59, tzinfo=UTC)
        just_after = dt.datetime(2026, 7, 12, 0, 0, 0, tzinfo=UTC)
        assert current_session_date(just_before) == dt.date(2026, 7, 11)
        assert current_session_date(just_after) == dt.date(2026, 7, 12)


# ── Adversarial construction tests ──────────────────────────────────────────


class TestAdversarialArtifactRef:
    def test_empty_digest_raises(self):
        with pytest.raises(ValueError, match="expected_digest"):
            SignalArtifactRef(
                expected_digest="", artifact_path="a.json",
                schema_version=1, producer_run_id="run-001",
            )

    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="artifact_path"):
            SignalArtifactRef(
                expected_digest="abc123", artifact_path="",
                schema_version=1, producer_run_id="run-001",
            )

    def test_zero_schema_version_raises(self):
        with pytest.raises(ValueError, match="schema_version"):
            SignalArtifactRef(
                expected_digest="abc123", artifact_path="a.json",
                schema_version=0, producer_run_id="run-001",
            )

    def test_empty_run_id_raises(self):
        with pytest.raises(ValueError, match="producer_run_id"):
            SignalArtifactRef(
                expected_digest="abc123", artifact_path="a.json",
                schema_version=1, producer_run_id="",
            )

    def test_whitespace_only_digest_raises(self):
        with pytest.raises(ValueError, match="expected_digest"):
            SignalArtifactRef(
                expected_digest="   ", artifact_path="a.json",
                schema_version=1, producer_run_id="run-001",
            )


class TestAdversarialStopCoverage:
    def test_negative_violations_raises(self):
        with pytest.raises(ValueError, match="violations"):
            StopCoverageReport(
                timestamp_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
                environment="live", account_id="acct",
                positions_covered=5, violations=-1, source_version="v1",
            )

    def test_negative_positions_raises(self):
        with pytest.raises(ValueError, match="positions_covered"):
            StopCoverageReport(
                timestamp_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
                environment="live", account_id="acct",
                positions_covered=-1, violations=0, source_version="v1",
            )

    def test_empty_environment_raises(self):
        with pytest.raises(ValueError, match="environment"):
            StopCoverageReport(
                timestamp_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
                environment="", account_id="acct",
                positions_covered=5, violations=0, source_version="v1",
            )

    def test_empty_source_version_raises(self):
        with pytest.raises(ValueError, match="source_version"):
            StopCoverageReport(
                timestamp_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
                environment="live", account_id="acct",
                positions_covered=5, violations=0, source_version="",
            )

    def test_empty_account_id_raises(self):
        with pytest.raises(ValueError, match="account_id"):
            StopCoverageReport(
                timestamp_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
                environment="live", account_id="",
                positions_covered=5, violations=0, source_version="v1",
            )


class TestAdversarialEvaluateTick:
    def test_forged_digest_ref_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        af = tmp_path / "forged.json"
        af.write_text("{}")
        forged_ref = SignalArtifactRef(
            expected_digest="forged_but_wrong_digest_value_abc",
            artifact_path=str(af),
            schema_version=1,
            producer_run_id="forged-run",
        )
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=forged_ref,
            stop_coverage=_make_stop_coverage(now),
        )
        assert not result.entries_allowed
        assert "mismatch" in result.reason

    def test_wrong_env_report_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="live")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref=_make_artifact_ref(snap, tmp_path),
            stop_coverage=_make_stop_coverage(now, mode="paper"),
        )
        assert not result.entries_allowed
        assert "environment mismatch" in result.reason
