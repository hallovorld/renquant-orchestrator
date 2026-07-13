"""Tests for the 24/7 crypto session scheduler (D-C11)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from renquant_orchestrator import crypto_session as crypto_session_module
from renquant_orchestrator.crypto_session import (
    ARTIFACT_REF_SCHEMA_VERSION,
    CRYPTO_ENV_FLAG,
    LIVE_AUTHORIZATION_SCHEMA_VERSION,
    STOP_COVERAGE_SCHEMA_VERSION,
    ArtifactRefError,
    CryptoSessionConfig,
    SessionWindow,
    SignalArtifactRef,
    SignalSnapshot,
    StopCoverageError,
    StopCoverageReport,
    TickResult,
    build_session_bundle,
    check_live_authorization,
    check_triple_gate,
    current_session_date,
    evaluate_tick,
    load_signal_artifact_ref,
    load_stop_coverage_report,
    validate_digest,
    validate_signal_contract,
    validate_watermark,
    watermark_for_session,
)

UTC = dt.timezone.utc


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _assume_trust_anchor_ready(monkeypatch) -> None:
    """Tests that verify the OTHER gates' pass-through logic (mode, quiet
    interval, live authorization, watermark, digest, stop coverage) need to
    lift the always-on TrustAnchorGateJob (see its module-level docstring)
    so a fully-passing tick can still reach entries_allowed=True -- proving
    the rest of the pipeline is correct independent of the current
    "no real trust anchor yet" restriction. Production code is untouched;
    this only patches the module flag for the duration of one test.
    """
    monkeypatch.setattr(
        crypto_session_module, "ENTRY_AUTHORIZATION_TRUST_ANCHOR_READY", True
    )


def _enabled_config(
    tmp_path: Path,
    *,
    mode: str = "paper",
    live_authorization_path: Path | None = None,
) -> CryptoSessionConfig:
    return CryptoSessionConfig(
        enabled=True,
        mode=mode,
        kill_switch_path=tmp_path / "nonexistent_kill_switch",
        live_authorization_path=live_authorization_path,
    )


def _make_snapshot(session_date: dt.date) -> SignalSnapshot:
    return SignalSnapshot(
        session_date=session_date,
        bar_watermark_utc=watermark_for_session(session_date),
        universe_hash="test_hash",
        model_content_sha256="model_sha",
        calibrator_content_sha256="cal_sha",
    )


def _write_artifact_ref(
    tmp_path: Path,
    snap: SignalSnapshot,
    *,
    filename: str = "artifact_ref.json",
    schema_version: int = ARTIFACT_REF_SCHEMA_VERSION,
    producer_run_id: str = "test-run-001",
    expected_digest: str | None = None,
    artifact_path: str | None = "__self__",
) -> Path:
    """Write a WELL-FORMED signal-artifact-ref sidecar file to disk.

    This is real file I/O for tests to exercise ``load_signal_artifact_ref``
    against — it does NOT construct a ``SignalArtifactRef`` in-memory and
    hand it straight to the function under test, which is exactly the
    tautological pattern (comparing a snapshot's digest to itself) that the
    round-3 self-fix closes.

    ``artifact_path`` defaults to the sentinel ``"__self__"``, meaning "point
    at the sidecar file itself" (SignalArtifactRef.validate() requires this
    referenced path to actually exist on disk — the sidecar's own path
    trivially satisfies that). Pass an explicit path to test a real,
    different-but-existing artifact path, or an obviously-nonexistent one to
    test the dangling-reference rejection; pass ``None`` to omit the field
    entirely (loader then defaults it to the sidecar's own path too).
    """
    path = tmp_path / filename
    resolved_artifact_path = str(path) if artifact_path == "__self__" else artifact_path
    body = {
        "schema_version": schema_version,
        "producer_run_id": producer_run_id,
        "expected_digest": expected_digest if expected_digest is not None else snap.digest(),
    }
    if resolved_artifact_path is not None:
        body["artifact_path"] = resolved_artifact_path
    _write_json(path, body)
    return path


def _write_stop_coverage(
    tmp_path: Path,
    now_utc: dt.datetime,
    *,
    filename: str = "stop_coverage.json",
    mode: str = "paper",
    violations: int = 0,
    schema_version: int = STOP_COVERAGE_SCHEMA_VERSION,
    source_version: str = "test-v1",
    account_id: str = "test-account-123",
    positions_covered: int = 5,
) -> Path:
    """Write a WELL-FORMED stop-coverage sidecar file to disk (real file I/O)."""
    path = tmp_path / filename
    _write_json(path, {
        "schema_version": schema_version,
        "timestamp_utc": now_utc.isoformat(),
        "environment": mode,
        "account_id": account_id,
        "positions_covered": positions_covered,
        "violations": violations,
        "source_version": source_version,
    })
    return path


def _write_live_authorization(
    tmp_path: Path,
    now_utc: dt.datetime,
    *,
    filename: str = "live_authorization.json",
    authorized: bool = True,
    schema_version: int = LIVE_AUTHORIZATION_SCHEMA_VERSION,
    authorized_at: dt.datetime | None = None,
    expires_at: dt.datetime | None = None,
) -> Path:
    """Write a WELL-FORMED live-authorization marker file to disk (real file I/O)."""
    path = tmp_path / filename
    _write_json(path, {
        "schema_version": schema_version,
        "authorized": authorized,
        "authorized_at": (authorized_at or (now_utc - dt.timedelta(hours=1))).isoformat(),
        "expires_at": (expires_at or (now_utc + dt.timedelta(hours=1))).isoformat(),
    })
    return path


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

    def test_naive_watermark_rejected(self):
        # A naive (non-timezone-aware) bar_watermark_utc must fail closed
        # with a clear reason rather than raising a bare TypeError when
        # compared against the (always tz-aware) session watermark.
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=dt.datetime(2026, 7, 12, 0, 0),  # no tzinfo
            universe_hash="h", model_content_sha256="m",
            calibrator_content_sha256="c",
        )
        ok, reason = validate_watermark(snap, dt.date(2026, 7, 12))
        assert not ok
        assert "timezone-aware" in reason

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
        )
        assert not result.entries_allowed
        assert "future bars" in result.reason


# ── Signal contract (fingerprint) validation ────────────────────────────────


class TestSignalContract:
    def test_valid_fingerprints(self):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ok, reason = validate_signal_contract(snap)
        assert ok

    def test_legitimate_hash_not_mistaken_for_placeholder(self):
        # "test_hash" must NOT be rejected by substring matching against "test".
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ok, reason = validate_signal_contract(snap)
        assert ok

    @pytest.mark.parametrize(
        "placeholder", ["", "   ", "MISSING", "unknown", "TODO", "n/a", "TBD", "NULL"]
    )
    def test_placeholder_fingerprint_rejected(self, placeholder):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=watermark_for_session(dt.date(2026, 7, 12)),
            universe_hash=placeholder,
            model_content_sha256="model_sha",
            calibrator_content_sha256="cal_sha",
        )
        ok, reason = validate_signal_contract(snap)
        assert not ok
        assert "universe_hash" in reason

    def test_placeholder_in_model_or_calibrator_field_rejected(self):
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=watermark_for_session(dt.date(2026, 7, 12)),
            universe_hash="real_hash",
            model_content_sha256="UNKNOWN",
            calibrator_content_sha256="cal_sha",
        )
        ok, reason = validate_signal_contract(snap)
        assert not ok
        assert "model_content_sha256" in reason

    def test_invalid_fingerprint_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = SignalSnapshot(
            session_date=dt.date(2026, 7, 12),
            bar_watermark_utc=watermark_for_session(dt.date(2026, 7, 12)),
            universe_hash="MISSING",
            model_content_sha256="model_sha",
            calibrator_content_sha256="cal_sha",
        )
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
        )
        assert not result.entries_allowed
        assert "invalid fingerprint" in result.reason


# ── Signal artifact ref loader (real file I/O) ───────────────────────────────


class TestArtifactRefLoader:
    def test_valid_ref_loads(self, tmp_path):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        path = _write_artifact_ref(tmp_path, snap)
        ref = load_signal_artifact_ref(path)
        assert isinstance(ref, SignalArtifactRef)
        assert ref.expected_digest == snap.digest()
        assert ref.producer_run_id == "test-run-001"
        assert ref.schema_version == ARTIFACT_REF_SCHEMA_VERSION

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ArtifactRefError, match="not found"):
            load_signal_artifact_ref(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ArtifactRefError, match="malformed JSON"):
            load_signal_artifact_ref(path)

    def test_non_dict_body_raises(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ArtifactRefError, match="not a JSON object"):
            load_signal_artifact_ref(path)

    def test_schema_version_mismatch_raises(self, tmp_path):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        path = _write_artifact_ref(tmp_path, snap, schema_version=99)
        with pytest.raises(ArtifactRefError, match="schema_version mismatch"):
            load_signal_artifact_ref(path)

    @pytest.mark.parametrize("placeholder", ["", "MISSING", "unknown", "  "])
    def test_placeholder_producer_run_id_raises(self, tmp_path, placeholder):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        path = _write_artifact_ref(tmp_path, snap, producer_run_id=placeholder)
        with pytest.raises(ArtifactRefError, match="producer_run_id"):
            load_signal_artifact_ref(path)

    def test_malformed_digest_raises(self, tmp_path):
        snap = _make_snapshot(dt.date(2026, 7, 12))
        path = _write_artifact_ref(tmp_path, snap, expected_digest="not-a-real-digest")
        with pytest.raises(ArtifactRefError, match="expected_digest"):
            load_signal_artifact_ref(path)

    def test_dangling_artifact_path_raises(self, tmp_path):
        # The sidecar file itself is well-formed, but the informational
        # artifact_path it points at (a DIFFERENT file) doesn't exist —
        # SignalArtifactRef.validate() must catch this dangling reference.
        snap = _make_snapshot(dt.date(2026, 7, 12))
        path = _write_artifact_ref(
            tmp_path, snap, artifact_path=str(tmp_path / "does_not_exist_signal.json")
        )
        with pytest.raises(ArtifactRefError, match="does not exist"):
            load_signal_artifact_ref(path)

    def test_omitted_artifact_path_defaults_to_sidecar_and_passes(self, tmp_path):
        # artifact_path omitted entirely from the JSON body — the loader
        # defaults it to the sidecar's own path, which trivially exists.
        snap = _make_snapshot(dt.date(2026, 7, 12))
        path = _write_artifact_ref(tmp_path, snap, artifact_path=None)
        ref = load_signal_artifact_ref(path)
        assert ref.artifact_path == str(path)


class TestSignalArtifactRefConstruction:
    """Adversarial construction tests for __post_init__/validate() — these
    run whether or not a caller goes through load_signal_artifact_ref."""

    def test_valid_construction(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text("{}", encoding="utf-8")
        ref = SignalArtifactRef(
            expected_digest="a" * 64,
            artifact_path=str(p),
            schema_version=1,
            producer_run_id="run-1",
        )
        ok, _ = ref.validate()
        assert ok

    def test_empty_expected_digest_raises(self):
        with pytest.raises(ValueError, match="expected_digest"):
            SignalArtifactRef(
                expected_digest="",
                artifact_path="/tmp/x.json",
                schema_version=1,
                producer_run_id="run-1",
            )

    def test_empty_artifact_path_raises(self):
        with pytest.raises(ValueError, match="artifact_path"):
            SignalArtifactRef(
                expected_digest="a" * 64,
                artifact_path="",
                schema_version=1,
                producer_run_id="run-1",
            )

    def test_empty_producer_run_id_raises(self):
        with pytest.raises(ValueError, match="producer_run_id"):
            SignalArtifactRef(
                expected_digest="a" * 64,
                artifact_path="/tmp/x.json",
                schema_version=1,
                producer_run_id="",
            )

    def test_schema_version_below_one_raises(self):
        with pytest.raises(ValueError, match="schema_version"):
            SignalArtifactRef(
                expected_digest="a" * 64,
                artifact_path="/tmp/x.json",
                schema_version=0,
                producer_run_id="run-1",
            )

    def test_validate_nonexistent_path(self):
        ref = SignalArtifactRef(
            expected_digest="a" * 64,
            artifact_path="/nonexistent/path.json",
            schema_version=1,
            producer_run_id="run-1",
        )
        ok, reason = ref.validate()
        assert not ok
        assert "does not exist" in reason

    def test_validate_wrong_schema_version(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text("{}", encoding="utf-8")
        ref = SignalArtifactRef(
            expected_digest="a" * 64,
            artifact_path=str(p),
            schema_version=99,
            producer_run_id="run-1",
        )
        ok, reason = ref.validate()
        assert not ok
        assert "schema_version" in reason


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

    def test_missing_artifact_ref_path_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=None,
        )
        assert not result.entries_allowed
        assert "fail-closed" in result.reason

    def test_artifact_ref_file_missing_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=tmp_path / "does_not_exist.json",
        )
        assert not result.entries_allowed
        assert "artifact ref invalid" in result.reason

    def test_malformed_artifact_ref_file_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        bad_path = tmp_path / "bad_ref.json"
        bad_path.write_text("not json at all", encoding="utf-8")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=bad_path,
        )
        assert not result.entries_allowed
        assert "artifact ref invalid" in result.reason

    def test_digest_mismatch_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        # A REAL, well-formed file — but with an expected_digest that does not
        # match this snapshot's actual digest (simulates a tampered/stale ref).
        tampered_digest = "0" * 64
        ref_path = _write_artifact_ref(tmp_path, snap, expected_digest=tampered_digest)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
        )
        assert not result.entries_allowed
        assert "mismatch" in result.reason


# ── Stop coverage loader (real file I/O) ─────────────────────────────────────


class TestStopCoverageLoader:
    def test_valid_report_loads(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_stop_coverage(tmp_path, now, mode="paper")
        report = load_stop_coverage_report(path)
        assert isinstance(report, StopCoverageReport)
        assert report.environment == "paper"
        assert report.violations == 0
        assert report.is_fresh(now)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(StopCoverageError, match="not found"):
            load_stop_coverage_report(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{broken", encoding="utf-8")
        with pytest.raises(StopCoverageError, match="malformed JSON"):
            load_stop_coverage_report(path)

    def test_non_dict_body_raises(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(StopCoverageError, match="not a JSON object"):
            load_stop_coverage_report(path)

    def test_schema_mismatch_raises(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_stop_coverage(tmp_path, now, schema_version=2)
        with pytest.raises(StopCoverageError, match="schema_version mismatch"):
            load_stop_coverage_report(path)

    def test_unknown_environment_raises(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = tmp_path / "cov.json"
        _write_json(path, {
            "schema_version": STOP_COVERAGE_SCHEMA_VERSION,
            "timestamp_utc": now.isoformat(),
            "environment": "sandbox",
            "account_id": "acct-1",
            "positions_covered": 1,
            "violations": 0,
            "source_version": "v1",
        })
        with pytest.raises(StopCoverageError, match="environment"):
            load_stop_coverage_report(path)

    def test_placeholder_source_version_raises(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_stop_coverage(tmp_path, now, source_version="UNKNOWN")
        with pytest.raises(StopCoverageError, match="source_version"):
            load_stop_coverage_report(path)

    @pytest.mark.parametrize("placeholder", ["", "MISSING", "unknown", "  "])
    def test_placeholder_account_id_raises(self, tmp_path, placeholder):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_stop_coverage(tmp_path, now, account_id=placeholder)
        with pytest.raises(StopCoverageError, match="account_id"):
            load_stop_coverage_report(path)

    def test_negative_violations_raises(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = tmp_path / "cov.json"
        _write_json(path, {
            "schema_version": STOP_COVERAGE_SCHEMA_VERSION,
            "timestamp_utc": now.isoformat(),
            "environment": "paper",
            "account_id": "acct-1",
            "positions_covered": 1,
            "violations": -1,
            "source_version": "v1",
        })
        with pytest.raises(StopCoverageError, match="violations"):
            load_stop_coverage_report(path)

    def test_unparseable_timestamp_raises(self, tmp_path):
        path = tmp_path / "cov.json"
        _write_json(path, {
            "schema_version": STOP_COVERAGE_SCHEMA_VERSION,
            "timestamp_utc": "not-a-timestamp",
            "environment": "paper",
            "account_id": "acct-1",
            "positions_covered": 1,
            "violations": 0,
            "source_version": "v1",
        })
        with pytest.raises(StopCoverageError, match="timestamp_utc"):
            load_stop_coverage_report(path)

    def test_naive_timestamp_raises(self, tmp_path):
        # A timezone-naive timestamp is ambiguous untrusted input — fail
        # closed rather than silently assuming UTC (StopCoverageReport.validate()).
        path = tmp_path / "cov.json"
        _write_json(path, {
            "schema_version": STOP_COVERAGE_SCHEMA_VERSION,
            "timestamp_utc": "2026-07-12T01:00:00",  # no UTC offset
            "environment": "paper",
            "account_id": "acct-1",
            "positions_covered": 1,
            "violations": 0,
            "source_version": "v1",
        })
        with pytest.raises(StopCoverageError, match="timezone-aware"):
            load_stop_coverage_report(path)


class TestStopCoverageReportConstruction:
    """Adversarial construction tests for __post_init__/validate() — these
    run whether or not a caller goes through load_stop_coverage_report."""

    def test_valid_construction(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        report = StopCoverageReport(
            timestamp_utc=now, environment="live", account_id="acct-1",
            positions_covered=5, violations=0, source_version="v1",
        )
        ok, _ = report.validate()
        assert ok

    def test_empty_environment_raises(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="environment"):
            StopCoverageReport(
                timestamp_utc=now, environment="", account_id="acct-1",
                positions_covered=5, violations=0, source_version="v1",
            )

    def test_empty_account_id_raises(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="account_id"):
            StopCoverageReport(
                timestamp_utc=now, environment="live", account_id="",
                positions_covered=5, violations=0, source_version="v1",
            )

    def test_negative_positions_covered_raises(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="positions_covered"):
            StopCoverageReport(
                timestamp_utc=now, environment="live", account_id="acct-1",
                positions_covered=-1, violations=0, source_version="v1",
            )

    def test_negative_violations_raises(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="violations"):
            StopCoverageReport(
                timestamp_utc=now, environment="live", account_id="acct-1",
                positions_covered=5, violations=-1, source_version="v1",
            )

    def test_empty_source_version_raises(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="source_version"):
            StopCoverageReport(
                timestamp_utc=now, environment="live", account_id="acct-1",
                positions_covered=5, violations=0, source_version="",
            )

    def test_validate_invalid_environment(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        report = StopCoverageReport(
            timestamp_utc=now, environment="shadow", account_id="acct-1",
            positions_covered=5, violations=0, source_version="v1",
        )
        ok, reason = report.validate()
        assert not ok
        assert "environment" in reason

    def test_validate_naive_timestamp(self):
        now = dt.datetime(2026, 7, 12, 1, 0)  # no tzinfo
        report = StopCoverageReport(
            timestamp_utc=now, environment="live", account_id="acct-1",
            positions_covered=5, violations=0, source_version="v1",
        )
        ok, reason = report.validate()
        assert not ok
        assert "timezone-aware" in reason


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
        )
        assert not result.entries_allowed
        assert result.exits_allowed
        assert "shadow" in result.reason

    def test_paper_mode_allows_entries(self, tmp_path, monkeypatch):
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed


# ── Live-mode authorization (separate evidence chain) ───────────────────────


class TestLiveAuthorizationDirect:
    def test_valid_authorization_passes(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_live_authorization(tmp_path, now)
        ok, reason = check_live_authorization(path, now)
        assert ok

    def test_none_path_blocks(self):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ok, reason = check_live_authorization(None, now)
        assert not ok
        assert "live_authorization_path" in reason

    def test_missing_file_blocks(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ok, reason = check_live_authorization(tmp_path / "nope.json", now)
        assert not ok
        assert "not found" in reason

    def test_malformed_json_blocks(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = tmp_path / "bad.json"
        path.write_text("{broken", encoding="utf-8")
        ok, reason = check_live_authorization(path, now)
        assert not ok
        assert "malformed JSON" in reason

    def test_authorized_false_blocks(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_live_authorization(tmp_path, now, authorized=False)
        ok, reason = check_live_authorization(path, now)
        assert not ok
        assert "not granted" in reason

    def test_expired_authorization_blocks(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_live_authorization(
            tmp_path, now,
            authorized_at=now - dt.timedelta(days=2),
            expires_at=now - dt.timedelta(hours=1),
        )
        ok, reason = check_live_authorization(path, now)
        assert not ok
        assert "expired" in reason

    def test_not_yet_active_blocks(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_live_authorization(
            tmp_path, now,
            authorized_at=now + dt.timedelta(hours=1),
            expires_at=now + dt.timedelta(hours=2),
        )
        ok, reason = check_live_authorization(path, now)
        assert not ok
        assert "not yet active" in reason

    def test_schema_mismatch_blocks(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = _write_live_authorization(tmp_path, now, schema_version=2)
        ok, reason = check_live_authorization(path, now)
        assert not ok
        assert "schema_version mismatch" in reason

    def test_missing_expires_at_blocks(self, tmp_path):
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        path = tmp_path / "auth.json"
        _write_json(path, {
            "schema_version": LIVE_AUTHORIZATION_SCHEMA_VERSION,
            "authorized": True,
            "authorized_at": (now - dt.timedelta(hours=1)).isoformat(),
        })
        ok, reason = check_live_authorization(path, now)
        assert not ok
        assert "expires_at" in reason


class TestLiveModeGateIntegration:
    def test_live_mode_without_authorization_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="live", live_authorization_path=None)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
        )
        assert not result.entries_allowed
        assert "live mode blocked" in result.reason

    def test_live_mode_with_valid_authorization_allows_entry(self, tmp_path, monkeypatch):
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        auth_path = _write_live_authorization(tmp_path, now)
        cfg = _enabled_config(tmp_path, mode="live", live_authorization_path=auth_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="live")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed

    def test_live_mode_with_expired_authorization_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        auth_path = _write_live_authorization(
            tmp_path, now,
            authorized_at=now - dt.timedelta(days=2),
            expires_at=now - dt.timedelta(hours=1),
        )
        cfg = _enabled_config(tmp_path, mode="live", live_authorization_path=auth_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
        )
        assert not result.entries_allowed
        assert "expired" in result.reason

    def test_paper_mode_does_not_require_authorization_file(self, tmp_path, monkeypatch):
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper", live_authorization_path=None)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed


# ── Configured quiet interval ───────────────────────────────────────────────


class TestConfiguredQuietInterval:
    def test_configured_quiet_interval_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = CryptoSessionConfig(
            enabled=True, mode="paper",
            kill_switch_path=tmp_path / "no_kill",
            quiet_interval_minutes=30,
        )
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 0, 20, tzinfo=UTC)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
        )
        assert not result.entries_allowed
        assert result.is_quiet

    def test_after_configured_quiet_allows_entry(self, tmp_path, monkeypatch):
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = CryptoSessionConfig(
            enabled=True, mode="paper",
            kill_switch_path=tmp_path / "no_kill",
            quiet_interval_minutes=10,
        )
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 0, 12, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed


# ── Stop coverage gate (evaluate_tick integration) ──────────────────────────


class TestStopCoverage:
    def test_missing_stop_coverage_path_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=None,
        )
        assert not result.entries_allowed
        assert "stop_coverage" in result.reason

    def test_stop_coverage_file_missing_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=tmp_path / "does_not_exist.json",
        )
        assert not result.entries_allowed
        assert "stop coverage report invalid" in result.reason

    def test_violations_block_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper", violations=3)
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert not result.entries_allowed
        assert "violation" in result.reason

    def test_environment_mismatch_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="live")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert not result.entries_allowed
        assert "environment mismatch" in result.reason

    def test_stale_report_blocks_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        stale_time = now - dt.timedelta(seconds=600)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, stale_time, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert not result.entries_allowed
        assert "stale" in result.reason


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
        )
        assert not result.entries_allowed
        assert "mismatch" in result.reason

    def test_valid_tick_allows_entries(self, tmp_path, monkeypatch):
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed
        assert result.exits_allowed
        assert result.signal_snapshot_digest == snap.digest()

    def test_weekend_entries_allowed(self, tmp_path, monkeypatch):
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        saturday = dt.date(2026, 7, 11)
        snap = _make_snapshot(saturday)
        now = dt.datetime(2026, 7, 11, 14, 30, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed

    def test_exits_always_allowed_even_kill_switched(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        kill_file = tmp_path / "kill"
        kill_file.touch()
        cfg = CryptoSessionConfig(enabled=True, mode="paper", kill_switch_path=kill_file)
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
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        j = result.to_jsonable()
        assert json.dumps(j)
        assert j["entries_allowed"] is True
        assert j["session_date"] == "2026-07-12"
        assert isinstance(j["pipeline_steps"], list)
        assert len(j["pipeline_steps"]) == 10  # one PipelineStepRecord per gate
        assert all(not step["skipped"] for step in j["pipeline_steps"])

    def test_blocked_tick_shows_skipped_later_gates(self, tmp_path, monkeypatch):
        monkeypatch.delenv(CRYPTO_ENV_FLAG, raising=False)
        cfg = _enabled_config(tmp_path)
        result = evaluate_tick(
            config=cfg,
            now_utc=dt.datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        )
        steps = result.pipeline_steps
        assert steps[0]["job_name"] == "TripleGateJob"
        assert steps[0]["skipped"] is False
        assert all(step["skipped"] for step in steps[1:])


# ── Trust-anchor gate (2026-07-13, operator + Codex review of PR #501) ─────


class TestTrustAnchorGate:
    """File-based SignalArtifactRef/StopCoverageReport loading (round 5)
    closes the in-memory-tautology gap but not the deeper one: neither is
    tied to a genuinely tamper-evident, execution/model-owned trust anchor.
    Until model#52 (signal provenance) and execution#37 (execution-owned
    coverage report) land and this gate wires to them,
    ENTRY_AUTHORIZATION_TRUST_ANCHOR_READY stays False and entries must be
    structurally impossible in every mode, while every other gate still
    runs (exercising the bundle/report plumbing)."""

    def test_default_blocks_entries_even_when_every_other_gate_passes(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed is False
        assert "trust anchor not yet implemented" in result.reason
        assert result.exits_allowed is True  # exits always allowed regardless

    def test_default_blocks_entries_in_live_mode_too(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        auth_path = _write_live_authorization(tmp_path, now)
        cfg = _enabled_config(tmp_path, mode="live", live_authorization_path=auth_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="live")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed is False
        assert "trust anchor not yet implemented" in result.reason

    def test_other_gates_still_run_and_are_recorded_when_only_blocked_by_trust_anchor(
        self, tmp_path, monkeypatch
    ):
        """The plumbing-exercise property Codex asked for: every gate up to
        and including TrustAnchorGateJob must show skipped=False (they all
        genuinely ran), proving this restriction doesn't hide the rest of
        the pipeline -- only the final admit decision is forced closed."""
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        steps = result.pipeline_steps
        assert len(steps) == 10
        assert all(not step["skipped"] for step in steps)
        assert steps[-1]["job_name"] == "TrustAnchorGateJob"

    def test_lifting_the_flag_restores_entries_allowed(self, tmp_path, monkeypatch):
        """Sanity check for the monkeypatch helper itself: proves the flag
        genuinely gates the outcome, not just that other tests happen to
        pass for unrelated reasons."""
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path, mode="paper")
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        result = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        assert result.entries_allowed is True


# ── Session bundle ───────────────────────────────────────────────────────────


class TestSessionBundle:
    def test_bundle_structure(self, tmp_path, monkeypatch):
        _assume_trust_anchor_ready(monkeypatch)
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        ref_path = _write_artifact_ref(tmp_path, snap)
        ticks = [
            evaluate_tick(
                config=cfg,
                now_utc=dt.datetime(2026, 7, 12, h, 0, tzinfo=UTC),
                signal_snapshot=snap,
                artifact_ref_path=ref_path,
                stop_coverage_path=_write_stop_coverage(
                    tmp_path,
                    dt.datetime(2026, 7, 12, h, 0, tzinfo=UTC),
                    mode="paper",
                    filename=f"cov_{h}.json",
                ),
            )
            for h in range(1, 4)
        ]
        bundle = build_session_bundle(
            config=cfg,
            session_date=dt.date(2026, 7, 12),
            tick_results=ticks,
            signal_snapshot=snap,
        )
        assert bundle["schema_version"] == 2
        assert bundle["source"] == "crypto_session"
        assert bundle["session_date"] == "2026-07-12"
        assert bundle["environment"] == "paper"
        assert bundle["quiet_interval_minutes"] == 15
        assert bundle["n_ticks"] == 3
        assert bundle["n_entries_allowed"] == 3
        assert bundle["signal_snapshot_digest"] == snap.digest()
        assert "gate_audit" in bundle
        assert bundle["gate_audit"]["TripleGateJob"] == {"ran": 3, "skipped": 0}
        assert bundle["gate_audit"]["StopCoverageGateJob"] == {"ran": 3, "skipped": 0}
        # No artifact_ref/stop_coverage objects were passed to build_session_bundle
        # itself in this test (only paths were passed to evaluate_tick per-tick).
        assert bundle["artifact_ref"] is None
        assert bundle["stop_coverage"] is None
        assert json.dumps(bundle)

    def test_bundle_with_provenance_objects(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CRYPTO_ENV_FLAG, "1")
        cfg = _enabled_config(tmp_path)
        snap = _make_snapshot(dt.date(2026, 7, 12))
        now = dt.datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
        ref_path = _write_artifact_ref(tmp_path, snap)
        cov_path = _write_stop_coverage(tmp_path, now, mode="paper")
        # Simulate a caller that already loaded+trusted these via the real
        # loaders elsewhere, and now wants them captured in the persisted
        # bundle record purely as informational provenance.
        loaded_ref = load_signal_artifact_ref(ref_path)
        loaded_cov = load_stop_coverage_report(cov_path)
        tick = evaluate_tick(
            config=cfg,
            now_utc=now,
            signal_snapshot=snap,
            artifact_ref_path=ref_path,
            stop_coverage_path=cov_path,
        )
        bundle = build_session_bundle(
            config=cfg,
            session_date=dt.date(2026, 7, 12),
            tick_results=[tick],
            signal_snapshot=snap,
            artifact_ref=loaded_ref,
            stop_coverage=loaded_cov,
        )
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
        assert bundle["n_ticks"] == 0


# ── Config from dict ─────────────────────────────────────────────────────────


class TestConfigFromDict:
    def test_defaults(self):
        cfg = CryptoSessionConfig.from_dict({})
        assert not cfg.enabled
        assert cfg.tick_cadence_seconds == 900
        assert cfg.mode == "shadow"
        assert cfg.quiet_interval_minutes == 15
        assert cfg.live_authorization_path is None

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
                "live_authorization_path": "/tmp/live_auth.json",
            }
        })
        assert cfg.enabled
        assert cfg.tick_cadence_seconds == 300
        assert cfg.mode == "paper"
        assert cfg.sleeve_budget_usd == 1500.0
        assert cfg.max_drawdown_pct == 8.0
        assert cfg.quiet_interval_minutes == 30
        assert cfg.live_authorization_path == Path("/tmp/live_auth.json")


# ── current_session_date ─────────────────────────────────────────────────────


class TestCurrentSessionDate:
    def test_utc_midnight_boundary(self):
        just_before = dt.datetime(2026, 7, 11, 23, 59, 59, tzinfo=UTC)
        just_after = dt.datetime(2026, 7, 12, 0, 0, 0, tzinfo=UTC)
        assert current_session_date(just_before) == dt.date(2026, 7, 11)
        assert current_session_date(just_after) == dt.date(2026, 7, 12)
