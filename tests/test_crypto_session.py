"""Tests for the 24/7 crypto session scheduler (D-C11)."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from renquant_orchestrator.crypto_session import (
    CRYPTO_ENV_FLAG,
    CRYPTO_KILL_SWITCH_RELPATH,
    CRYPTO_LIVE_MODE,
    CRYPTO_PAPER_MODE,
    CryptoSessionConfig,
    SessionWindow,
    SignalSnapshot,
    TickResult,
    build_session_bundle,
    check_triple_gate,
    current_session_date,
    default_crypto_kill_switch_path,
    evaluate_tick,
    watermark_for_session,
)

UTC = dt.timezone.utc


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

    def test_is_active(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12))
        assert w.is_active(dt.datetime(2026, 7, 12, 12, 0, tzinfo=UTC))
        assert not w.is_active(dt.datetime(2026, 7, 13, 0, 0, tzinfo=UTC))

    def test_weekend_active(self):
        """Crypto sessions are active on weekends (always-open)."""
        saturday = dt.date(2026, 7, 11)  # Saturday
        w = SessionWindow.for_date(saturday)
        assert w.is_active(dt.datetime(2026, 7, 11, 15, 0, tzinfo=UTC))


# ── SignalSnapshot ───────────────────────────────────────────────────────────


class TestSignalSnapshot:
    def test_digest_deterministic(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 12, 0, 0, tzinfo=UTC),
            universe_hash="abc123",
            model_content_sha256="model_hash",
            calibrator_content_sha256="cal_hash",
        )
        d1 = snap.digest()
        d2 = snap.digest()
        assert d1 == d2
        assert len(d1) == 64  # sha256 hex

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


# ── evaluate_tick ────────────────────────────────────────────────────────────


def _enabled_config(
    tmp_path: Path,
    *,
    mode: str = CRYPTO_LIVE_MODE,
    quiet_interval_minutes: int = 15,
) -> CryptoSessionConfig:
    """Config with the triple gate clear.

    Defaults to ``mode="live"`` so entries CAN be allowed once the other
    gates (watermark/digest/stop-coverage) are also satisfied by the
    caller — tests that specifically exercise the mode gate override this.
    """
    return CryptoSessionConfig(
        enabled=True,
        mode=mode,
        kill_switch_path=tmp_path / "nonexistent_kill_switch",
        quiet_interval_minutes=quiet_interval_minutes,
    )


def _make_snapshot(session_date: dt.date) -> SignalSnapshot:
    return SignalSnapshot(
        session_date=session_date,
        bar_watermark_utc=watermark_for_session(session_date),
        universe_hash="test_hash",
        model_content_sha256="model_sha",
        calibrator_content_sha256="cal_sha",
    )


class TestEvaluateTick:
    def test_gate_failed_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.delenv(CRYPTO_ENV_FLAG, raising=False)
        cfg = _enabled_config(tmp_path)
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        )
        assert not result.entries_allowed
        assert result.exits_allowed  # exits always allowed

    def test_quiet_interval_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 0, 5, tzinfo=UTC),
            signal_snapshot=snap,
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
        snap = _make_snapshot(dt.date(2026, 7, 11))  # yesterday
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
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
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert result.entries_allowed
        assert result.exits_allowed
        assert result.signal_snapshot_digest == snap.digest()
        assert result.mode == CRYPTO_LIVE_MODE

    def test_weekend_entries_allowed(self, tmp_path, monkeypatch):
        """24/7: entries work on Saturday."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        saturday = dt.date(2026, 7, 11)
        snap = _make_snapshot(saturday)
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 11, 14, 30, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert result.entries_allowed

    def test_exits_always_allowed_even_kill_switched(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        kill_file = tmp_path / "kill"
        kill_file.touch()
        cfg = CryptoSessionConfig(enabled=True, kill_switch_path=kill_file)
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
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        j = result.to_jsonable()
        assert json.dumps(j)  # serializable
        assert j["entries_allowed"] is True
        assert j["session_date"] == "2026-07-12"
        assert j["mode"] == CRYPTO_LIVE_MODE


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
                expected_signal_snapshot_digest=snap.digest(),
                crypto_stop_coverage_violations=[],
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
        assert json.dumps(bundle)  # fully serializable


# ── Watermark ────────────────────────────────────────────────────────────────


class TestWatermark:
    def test_watermark_is_session_midnight(self):
        wm = watermark_for_session(dt.date(2026, 7, 12))
        assert wm == dt.datetime(2026, 7, 12, 0, 0, tzinfo=UTC)

    def test_watermark_excludes_current_day_bars(self):
        """Session D's watermark = D 00:00 UTC = end of D-1."""
        wm = watermark_for_session(dt.date(2026, 7, 12))
        d_minus_1_close = dt.datetime(2026, 7, 12, 0, 0, tzinfo=UTC)
        assert wm == d_minus_1_close


# ── Config from dict ─────────────────────────────────────────────────────────


class TestConfigFromDict:
    def test_defaults(self):
        cfg = CryptoSessionConfig.from_dict({})
        assert not cfg.enabled
        assert cfg.tick_cadence_seconds == 900
        assert cfg.mode == "shadow"

    def test_full_config(self):
        cfg = CryptoSessionConfig.from_dict({
            "crypto_trading": {
                "enabled": True,
                "tick_cadence_seconds": 300,
                "mode": "paper",
                "ntfy_topic": "test-crypto",
                "sleeve_budget_usd": 1500.0,
                "max_drawdown_pct": 8.0,
            }
        })
        assert cfg.enabled
        assert cfg.tick_cadence_seconds == 300
        assert cfg.mode == "paper"
        assert cfg.sleeve_budget_usd == 1500.0
        assert cfg.max_drawdown_pct == 8.0


# ── current_session_date ─────────────────────────────────────────────────────


class TestCurrentSessionDate:
    def test_utc_midnight_boundary(self):
        just_before = dt.datetime(2026, 7, 11, 23, 59, 59, tzinfo=UTC)
        just_after = dt.datetime(2026, 7, 12, 0, 0, 0, tzinfo=UTC)
        assert current_session_date(just_before) == dt.date(2026, 7, 11)
        assert current_session_date(just_after) == dt.date(2026, 7, 12)


# ── Fix 1: watermark enforcement ─────────────────────────────────────────────


class TestWatermarkEnforcement:
    def test_future_watermark_blocks_entries(self, tmp_path, monkeypatch):
        """A snapshot whose bars reach into the current session must fail
        closed, even though its session_date matches."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        session_date = dt.date(2026, 7, 12)
        future_snap = SignalSnapshot(
            session_date=session_date,
            bar_watermark_utc=dt.datetime(2026, 7, 12, 6, 0, tzinfo=UTC),
            universe_hash="test_hash",
            model_content_sha256="model_sha",
            calibrator_content_sha256="cal_sha",
        )
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 8, 0, tzinfo=UTC),
            signal_snapshot=future_snap,
            expected_signal_snapshot_digest=future_snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "watermark mismatch" in result.reason
        expected_wm = watermark_for_session(session_date)
        assert expected_wm.isoformat() in result.reason
        assert future_snap.bar_watermark_utc.isoformat() in result.reason
        # still a full record: digest is populated even on failure
        assert result.signal_snapshot_digest == future_snap.digest()

    def test_matching_watermark_passes_this_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))  # correct watermark
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert "watermark mismatch" not in result.reason
        assert result.entries_allowed


# ── Fix 2: externally-supplied expected digest ───────────────────────────────


class TestExpectedDigestVerification:
    def test_digest_mismatch_blocks_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        bogus_expected = "0" * 64
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=bogus_expected,
            crypto_stop_coverage_violations=[],
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "digest mismatch" in result.reason
        assert bogus_expected in result.reason
        assert snap.digest() in result.reason

    def test_no_expected_digest_supplied_blocks_entries(self, tmp_path, monkeypatch):
        """expected_signal_snapshot_digest=None must fail closed distinctly
        from a mismatch — the caller never supplied one at all."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=None,
            crypto_stop_coverage_violations=[],
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "no expected" in result.reason.lower()
        assert "mismatch" not in result.reason


# ── Fix 3: crypto_trading.mode entry gate ────────────────────────────────────


class TestModeGate:
    def test_shadow_mode_blocks_entries_but_full_record(self, tmp_path, monkeypatch):
        """Shadow mode must block entries but still produce a complete,
        richly-populated decision record (not an empty/degraded one)."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="shadow")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert result.mode == "shadow"
        assert "mode=shadow" in result.reason
        # decision record is FULL, not degraded:
        assert result.signal_snapshot_digest == snap.digest()
        assert result.is_quiet is False
        assert result.is_kill_switched is False

    def test_live_mode_with_all_gates_clear_allows_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode=CRYPTO_LIVE_MODE)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert result.entries_allowed
        assert result.mode == CRYPTO_LIVE_MODE

    def test_paper_mode_with_all_gates_clear_allows_entries(self, tmp_path, monkeypatch):
        """Reconciling #497/#499 (2026-07-12): "paper" trades against
        Alpaca's paper endpoint -- the same account this codebase's Stage-0
        paper battery exercises -- so it is a genuinely authorized,
        no-real-capital-at-risk state, not a record-only one like "shadow".
        Restricting entries to "live" alone would make it impossible to
        ever validate this scheduler end-to-end before flipping to real
        capital."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode=CRYPTO_PAPER_MODE)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert result.entries_allowed
        assert result.mode == CRYPTO_PAPER_MODE

    def test_unknown_mode_blocks_entries_but_full_record(self, tmp_path, monkeypatch):
        """A mode value outside CRYPTO_ENTRY_ELIGIBLE_MODES (typo, unrecognized
        config value, ...) fails closed exactly like "shadow" -- entries
        require explicit membership in the eligible set, not merely
        "not shadow"."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="not-a-real-mode")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert not result.entries_allowed
        assert result.signal_snapshot_digest == snap.digest()


# ── Fix 4: configured quiet interval + config validation ────────────────────


class TestConfiguredQuietInterval:
    def test_non_default_quiet_interval_honored_by_session_window(self):
        w = SessionWindow.for_date(dt.date(2026, 7, 12), quiet_interval_minutes=30)
        assert w.quiet_end_utc == dt.datetime(2026, 7, 12, 0, 30, tzinfo=UTC)

    def test_non_default_quiet_interval_honored_by_evaluate_tick(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, quiet_interval_minutes=30)
        snap = _make_snapshot(dt.date(2026, 7, 12))

        # 20 min past midnight: inside the CONFIGURED 30-min quiet window,
        # which would NOT be quiet under the old hard-coded 15-min default.
        still_quiet = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 0, 20, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert still_quiet.is_quiet
        assert not still_quiet.entries_allowed

        # 30 min past midnight: the configured quiet window has ended.
        past_quiet = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 0, 30, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert not past_quiet.is_quiet
        assert past_quiet.entries_allowed


class TestConfigValidation:
    def test_negative_quiet_interval_raises(self):
        with pytest.raises(ValueError):
            CryptoSessionConfig(enabled=True, quiet_interval_minutes=-1)

    def test_quiet_interval_at_or_above_one_day_raises(self):
        with pytest.raises(ValueError):
            CryptoSessionConfig(enabled=True, quiet_interval_minutes=24 * 60)

    def test_zero_tick_cadence_raises(self):
        with pytest.raises(ValueError):
            CryptoSessionConfig(enabled=True, tick_cadence_seconds=0)

    def test_negative_tick_cadence_raises(self):
        with pytest.raises(ValueError):
            CryptoSessionConfig(enabled=True, tick_cadence_seconds=-300)

    def test_excessive_tick_cadence_raises(self):
        with pytest.raises(ValueError):
            CryptoSessionConfig(enabled=True, tick_cadence_seconds=3601)

    def test_from_dict_also_validates(self):
        with pytest.raises(ValueError):
            CryptoSessionConfig.from_dict(
                {"crypto_trading": {"quiet_interval_minutes": -5}}
            )


# ── Fix 4b: kill-switch default path resolved from the audited data root ────


class TestDefaultKillSwitchPath:
    def test_resolved_from_data_root_not_cwd(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RENQUANT_DATA_ROOT", str(tmp_path))
        resolved = default_crypto_kill_switch_path()
        assert resolved == tmp_path / CRYPTO_KILL_SWITCH_RELPATH

    def test_explicit_data_root_argument_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RENQUANT_DATA_ROOT", str(tmp_path / "other"))
        explicit_root = tmp_path / "explicit"
        resolved = default_crypto_kill_switch_path(explicit_root)
        assert resolved == explicit_root / CRYPTO_KILL_SWITCH_RELPATH


# ── Fix 5: execution-side stop-coverage precondition ─────────────────────────


class TestStopCoveragePrecondition:
    def test_none_fails_closed_unproven_safe(self, tmp_path, monkeypatch):
        """None means the caller never checked — an unproven-safe state
        must fail closed exactly like a confirmed violation."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=None,
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "not evaluated" in result.reason

    def test_empty_list_proven_covered_allows_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[],
        )
        assert result.entries_allowed

    def test_violations_block_and_name_symbols(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[
                {"symbol": "BTC/USD", "reason": "no protective stop found"},
            ],
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "BTC/USD" in result.reason

    def test_multiple_violations_name_all_symbols(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
            signal_snapshot=snap,
            expected_signal_snapshot_digest=snap.digest(),
            crypto_stop_coverage_violations=[
                {"symbol": "BTC/USD", "reason": "no protective stop found"},
                {"symbol": "ETH/USD", "reason": "stop order rejected"},
            ],
        )
        assert not result.entries_allowed
        assert "BTC/USD" in result.reason
        assert "ETH/USD" in result.reason
