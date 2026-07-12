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
    SignalSnapshot,
    TickResult,
    build_session_bundle,
    check_triple_gate,
    current_session_date,
    evaluate_tick,
    validate_digest,
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


# ── Watermark validation (review item 1) ─────────────────────────────────────


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

    def test_future_watermark_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
            universe_hash="h", model_content_sha256="m",
            calibrator_content_sha256="c",
        )
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
        )
        assert not result.entries_allowed
        assert "future bars" in result.reason


# ── Digest verification (review item 2) ──────────────────────────────────────


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

    def test_missing_expected_digest_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=None,
            stop_coverage_ok=True,
        )
        assert not result.entries_allowed
        assert "fail-closed" in result.reason

    def test_digest_mismatch_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest="tampered_digest",
            stop_coverage_ok=True,
        )
        assert not result.entries_allowed
        assert "mismatch" in result.reason


# ── Shadow mode blocks entries (review item 3) ───────────────────────────────


class TestShadowModeNonAdmission:
    def test_shadow_mode_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="shadow")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "shadow" in result.reason

    def test_paper_mode_allows_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
        )
        assert result.entries_allowed


# ── Configured quiet interval (review item 4) ────────────────────────────────


class TestConfiguredQuietInterval:
    def test_configured_quiet_interval_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = CryptoSessionConfig(
            enabled=True, mode="live",
            kill_switch_path=tmp_path / "no_kill",
            quiet_interval_minutes=30,
        )
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 0, 20, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
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
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 0, 12, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
        )
        assert result.entries_allowed


# ── Stop coverage (review item 5) ────────────────────────────────────────────


class TestStopCoverage:
    def test_missing_stop_coverage_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=None,
        )
        assert not result.entries_allowed
        assert "stop_coverage" in result.reason

    def test_false_stop_coverage_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=False,
        )
        assert not result.entries_allowed
        assert "stop-coverage" in result.reason


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
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 0, 5, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
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
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
        )
        assert not result.entries_allowed
        assert "mismatch" in result.reason

    def test_valid_tick_allows_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
        )
        assert result.entries_allowed
        assert result.exits_allowed
        assert result.signal_snapshot_digest == snap.digest()

    def test_weekend_entries_allowed(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        saturday = dt.date(2026, 7, 11)
        snap = _make_snapshot(saturday)
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 11, 14, 30, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
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
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_digest=snap.digest(),
            stop_coverage_ok=True,
        )
        j = result.to_jsonable()
        assert json.dumps(j)
        assert j["entries_allowed"] is True
        assert j["session_date"] == "2026-07-12"


# ── Session bundle ───────────────────────────────────────────────────────────


class TestSessionBundle:
    def test_bundle_structure(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ticks = [
            evaluate_tick(
                config=cfg,
                now_utc=dt.datetime(2026, 7, 12, h, 0, tzinfo=UTC),
                signal_snapshot=snap,
                expected_digest=snap.digest(),
                stop_coverage_ok=True,
            )
            for h in range(1, 4)
        ]
        bundle = build_session_bundle(
            config=cfg,
            session_date=dt.date(2026, 7, 12),
            tick_results=ticks,
            signal_snapshot=snap,
        )
        assert bundle["schema_version"] == 1
        assert bundle["source"] == "crypto_session"
        assert bundle["session_date"] == "2026-07-12"
        assert bundle["n_ticks"] == 3
        assert bundle["n_entries_allowed"] == 3
        assert bundle["signal_snapshot_digest"] == snap.digest()
        assert json.dumps(bundle)


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
