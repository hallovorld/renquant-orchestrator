"""Tests — per-epoch/per-role paired-session telemetry (v5 prereg §4.7 rule 4).

Covers: the 'no manifests → everything burned' safe default, strict
postdating of the pilot-registration commit, no-cross-epoch-pooling,
burned-manifest listings, activation (terminal) boundaries, record
deduplication across the printed payload + on-disk bundle copies, epoch
attribution (freeze fingerprint vs location fallbacks — only the former can
carry a pilot/terminal role), and the runner-side exposure on the existing
reporting surface.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator.shadow_ab_epoch_telemetry import (
    ATTRIBUTION_ARCHIVE,
    ATTRIBUTION_FREEZE,
    ATTRIBUTION_ROOT,
    EPOCH_ROLE_COUNTERS_FILENAME,
    EpochTelemetryError,
    PRE_EPOCH_ID,
    ROLE_BURNED,
    ROLE_PILOT,
    ROLE_TERMINAL,
    TELEMETRY_STATUS_COMPLETE,
    collect_session_records,
    derive_epoch_role_counters,
    enumerate_epochs,
    main as epoch_report_main,
)
from renquant_orchestrator.shadow_ab_runner import (
    BUNDLE_FILENAME,
    FREEZE_FILENAME,
    run_shadow_ab_session,
)

W1_PINS = {"renquant-strategy-104": "aaa1", "renquant-pipeline": "bbb2",
           "renquant-execution": "ccc3"}
W2_PINS = {"renquant-strategy-104": "ddd4", "renquant-pipeline": "bbb2",
           "renquant-execution": "ccc3"}
W1_ORCH = "0rch1"
W2_ORCH = "0rch2"


def _freeze(pins: dict[str, str], orch: str, frozen_at: str) -> dict:
    return {
        "schema_version": 1,
        "protocol": "D6-2a",
        "frozen_at": frozen_at,
        "config_sha256_a": "ca",
        "config_sha256_b": "cb",
        "model_content_sha256": "m",
        "calibrator_content_sha256": "c",
        "data_manifest_sha256": "d",
        "subrepo_pins": dict(pins),
        "orchestrator_commit": orch,
    }


def _session(
    date: str,
    status: str,
    *,
    pins: dict[str, str] | None = None,
    orch: str | None = None,
    as_of: str | None = None,
    marker: str = "",
) -> dict:
    def _arm(label: str) -> dict:
        return {
            "arm": label,
            "subrepo_pins": dict(pins) if pins else None,
            "orchestrator_commit": orch,
            "completed": status == "valid",
        }

    payload: dict = {
        "schema_version": 1,
        "protocol": "D6-2a",
        "session_date": date,
        "status": status,
        "void": False,
        "reasons": [marker] if marker else [],
        "arms": {"a": _arm("a"), "b": _arm("b")},
    }
    if as_of is not None:
        payload["decision_snapshot"] = {"as_of": as_of, "digest": "deadbeef"}
    return payload


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")


def _home(tmp_path: Path) -> Path:
    """epoch-1 archived (valid pair, world W1) + current epoch-2 at root
    (minted freeze, world W2, valid pair with a sealed as-of)."""
    root = tmp_path / "shadow-home"
    e1 = root / "archive" / "epoch1-freeze-20260711T072031"
    _write(e1 / FREEZE_FILENAME, _freeze(W1_PINS, W1_ORCH, "2026-07-11T08:58:18Z"))
    _write(
        e1 / "2026-07-11" / BUNDLE_FILENAME,
        _session("2026-07-11", "valid", pins=W1_PINS, orch=W1_ORCH,
                 as_of="2026-07-11T14:20:31Z"),
    )
    _write(root / FREEZE_FILENAME, _freeze(W2_PINS, W2_ORCH, "2026-07-20T21:35:00Z"))
    _write(
        root / "2026-07-21" / BUNDLE_FILENAME,
        _session("2026-07-21", "valid", pins=W2_PINS, orch=W2_ORCH,
                 as_of="2026-07-21T21:35:10Z"),
    )
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registration(
    tmp_path: Path,
    *,
    epoch_id: str = "epoch-2",
    registered_at: str = "2026-07-20T22:00:00Z",
    **extra,
) -> Path:
    path = tmp_path / "registration_manifest.json"
    _write(path, {
        "schema_version": 1,
        "epoch_id": epoch_id,
        "registered_at": registered_at,
        "pilot_registration_commit": "cafe1234",
        "source_repository": "RenQuant",
        **extra,
    })
    return path


def _activation(
    tmp_path: Path,
    registration: Path,
    *,
    epoch_id: str = "epoch-2",
    activated_at: str = "2026-07-25T00:00:00Z",
    **extra,
) -> Path:
    """An activation manifest BOUND to the registration file's content."""
    path = tmp_path / "activation_manifest.json"
    _write(path, {
        "schema_version": 1,
        "epoch_id": epoch_id,
        "activated_at": activated_at,
        "source_repository": "RenQuant",
        "source_commit": "beef5678",
        "registration_manifest_sha256": _sha256(registration),
        **extra,
    })
    return path


# --- safe default ---------------------------------------------------------------


def test_no_manifests_everything_burned(tmp_path: Path) -> None:
    report = derive_epoch_role_counters(_home(tmp_path))
    assert report["safe_default_applied"] is True
    assert report["totals"][ROLE_PILOT] == 0
    assert report["totals"][ROLE_TERMINAL] == 0
    assert report["totals"][ROLE_BURNED] == 2
    for entry in report["sessions"]:
        assert entry["role"] == ROLE_BURNED
        assert "no registration manifest" in entry["role_reason"]


# --- registration boundaries ----------------------------------------------------


def test_registration_promotes_postdating_valid_pair_to_pilot(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path, registered_at="2026-07-20T22:00:00Z")
    report = derive_epoch_role_counters(root, registration_manifest=registration)
    assert report["safe_default_applied"] is False
    assert report["totals"][ROLE_PILOT] == 1
    assert report["totals"][ROLE_BURNED] == 1  # the epoch-1 pair stays burned
    assert report["epochs"]["epoch-2"]["n_paired_sessions"][ROLE_PILOT] == 1
    assert report["epochs"]["epoch-1"]["n_paired_sessions"][ROLE_BURNED] == 1


def test_pre_registration_session_burns(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path, registered_at="2026-07-22T00:00:00Z")
    report = derive_epoch_role_counters(root, registration_manifest=registration)
    assert report["totals"][ROLE_PILOT] == 0
    assert report["totals"][ROLE_BURNED] == 2
    pilotless = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-21"
    ]
    assert "strictly postdate" in pilotless[0]["role_reason"]


def test_registration_day_session_without_as_of_burns(tmp_path: Path) -> None:
    root = _home(tmp_path)
    # Same-day valid pair with NO sealed as-of: the conservative 00:00 UTC
    # reading cannot prove strict postdating -> burned, never pilot.
    _write(
        root / "2026-07-20" / BUNDLE_FILENAME,
        _session("2026-07-20", "valid", pins=W2_PINS, orch=W2_ORCH),
    )
    registration = _registration(tmp_path, registered_at="2026-07-20T10:00:00Z")
    report = derive_epoch_role_counters(root, registration_manifest=registration)
    entry = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-20"
    ][0]
    assert entry["role"] == ROLE_BURNED


def test_epoch_mismatch_burns_no_cross_epoch_pooling(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path, epoch_id="epoch-9")
    report = derive_epoch_role_counters(root, registration_manifest=registration)
    assert report["totals"][ROLE_PILOT] == 0
    entry = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-21"
    ][0]
    assert "no cross-epoch pooling" in entry["role_reason"]


# --- burned-sessions manifest ---------------------------------------------------


def test_burned_manifest_listing_wins_over_pilot_eligibility(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(
        tmp_path,
        burned_sessions=[{"session_date": "2026-07-21", "epoch_id": "epoch-2"}],
    )
    report = derive_epoch_role_counters(root, registration_manifest=registration)
    assert report["totals"][ROLE_PILOT] == 0
    entry = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-21"
    ][0]
    assert "burned-sessions manifest" in entry["role_reason"]


def test_burned_sessions_manifest_path_resolves_relative(tmp_path: Path) -> None:
    root = _home(tmp_path)
    _write(tmp_path / "burned.json", {
        "schema_version": 1,
        "sessions": [{"session_date": "2026-07-21"}],  # epoch wildcard
    })
    registration = _registration(
        tmp_path,
        burned_sessions_manifest="burned.json",
        burned_sessions_manifest_sha256=_sha256(tmp_path / "burned.json"),
    )
    report = derive_epoch_role_counters(root, registration_manifest=registration)
    assert report["totals"][ROLE_PILOT] == 0
    assert report["totals"][ROLE_BURNED] == 2


def test_malformed_burned_manifest_fails_closed(tmp_path: Path) -> None:
    root = _home(tmp_path)
    _write(tmp_path / "burned.json", {"schema_version": 1, "sessions": [{"nope": 1}]})
    registration = _registration(
        tmp_path,
        burned_sessions_manifest="burned.json",
        burned_sessions_manifest_sha256=_sha256(tmp_path / "burned.json"),
    )
    with pytest.raises(EpochTelemetryError, match="session_date"):
        derive_epoch_role_counters(root, registration_manifest=registration)


def test_burned_manifest_without_sha256_commitment_fails_closed(
    tmp_path: Path,
) -> None:
    root = _home(tmp_path)
    _write(tmp_path / "burned.json", {
        "schema_version": 1, "sessions": [{"session_date": "2026-07-21"}],
    })
    registration = _registration(
        tmp_path, burned_sessions_manifest="burned.json",
    )
    with pytest.raises(EpochTelemetryError, match="burned_sessions_manifest_sha256"):
        derive_epoch_role_counters(root, registration_manifest=registration)


def test_burned_manifest_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    root = _home(tmp_path)
    _write(tmp_path / "burned.json", {
        "schema_version": 1, "sessions": [{"session_date": "2026-07-21"}],
    })
    registration = _registration(
        tmp_path,
        burned_sessions_manifest="burned.json",
        burned_sessions_manifest_sha256=_sha256(tmp_path / "burned.json"),
    )
    # A later edit at the same path must NOT be able to change the burn set.
    _write(tmp_path / "burned.json", {"schema_version": 1, "sessions": []})
    with pytest.raises(EpochTelemetryError, match="digest mismatch"):
        derive_epoch_role_counters(root, registration_manifest=registration)


# --- activation boundaries ------------------------------------------------------


def test_activation_splits_terminal_from_pilot(tmp_path: Path) -> None:
    root = _home(tmp_path)
    _write(
        root / "2026-07-28" / BUNDLE_FILENAME,
        _session("2026-07-28", "valid", pins=W2_PINS, orch=W2_ORCH,
                 as_of="2026-07-28T21:35:10Z"),
    )
    registration = _registration(tmp_path)
    activation = _activation(tmp_path, registration)
    report = derive_epoch_role_counters(
        root, registration_manifest=registration, activation_manifest=activation,
    )
    assert report["totals"][ROLE_PILOT] == 1     # 2026-07-21
    assert report["totals"][ROLE_TERMINAL] == 1  # 2026-07-28
    assert report["totals"][ROLE_BURNED] == 1    # epoch-1 pair


def test_activation_without_registration_rejected(tmp_path: Path) -> None:
    root = _home(tmp_path)
    activation = tmp_path / "activation_manifest.json"
    _write(activation, {
        "schema_version": 1, "epoch_id": "epoch-2",
        "activated_at": "2026-07-25T00:00:00Z",
    })
    with pytest.raises(EpochTelemetryError, match="two-stage start"):
        derive_epoch_role_counters(root, activation_manifest=activation)


def test_activation_epoch_must_match_registration_epoch(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path, epoch_id="epoch-2")
    activation = _activation(tmp_path, registration, epoch_id="epoch-3")
    with pytest.raises(EpochTelemetryError, match="SAME epoch"):
        derive_epoch_role_counters(
            root, registration_manifest=registration,
            activation_manifest=activation,
        )


# --- immutable manifest binding -------------------------------------------------


def test_report_records_manifest_bindings(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path)
    activation = _activation(tmp_path, registration)
    report = derive_epoch_role_counters(
        root, registration_manifest=registration, activation_manifest=activation,
    )
    reg = report["manifest_bindings"]["registration"]
    act = report["manifest_bindings"]["activation"]
    assert reg["sha256"] == _sha256(registration)
    assert reg["source_repository"] == "RenQuant"
    assert reg["source_commit"] == "cafe1234"  # pilot_registration_commit
    assert act["sha256"] == _sha256(activation)
    assert act["source_commit"] == "beef5678"
    assert act["registration_manifest_sha256"] == reg["sha256"]


def test_registration_without_source_provenance_fails_closed(
    tmp_path: Path,
) -> None:
    root = _home(tmp_path)
    path = tmp_path / "registration_manifest.json"
    _write(path, {
        "schema_version": 1, "epoch_id": "epoch-2",
        "registered_at": "2026-07-20T22:00:00Z",
        # no source_repository / source_commit / pilot_registration_commit
    })
    with pytest.raises(EpochTelemetryError, match="source provenance"):
        derive_epoch_role_counters(root, registration_manifest=path)


def test_registration_pinned_sha256_mismatch_fails_closed(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path)
    with pytest.raises(EpochTelemetryError, match="digest mismatch"):
        derive_epoch_role_counters(
            root, registration_manifest=registration,
            registration_manifest_sha256="0" * 64,
        )


def test_registration_pinned_sha256_match_accepts(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path)
    report = derive_epoch_role_counters(
        root, registration_manifest=registration,
        registration_manifest_sha256="sha256:" + _sha256(registration),
    )
    assert report["manifest_bindings"]["registration"]["pinned_sha256"]


def test_sha256_pin_without_manifest_path_fails_closed(tmp_path: Path) -> None:
    root = _home(tmp_path)
    with pytest.raises(EpochTelemetryError, match="cannot be verified"):
        derive_epoch_role_counters(root, registration_manifest_sha256="0" * 64)


def test_activation_without_registration_binding_fails_closed(
    tmp_path: Path,
) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path)
    activation = tmp_path / "activation_manifest.json"
    _write(activation, {
        "schema_version": 1, "epoch_id": "epoch-2",
        "activated_at": "2026-07-25T00:00:00Z",
        "source_repository": "RenQuant", "source_commit": "beef5678",
        # no registration_manifest_sha256
    })
    with pytest.raises(EpochTelemetryError, match="registration_manifest_sha256"):
        derive_epoch_role_counters(
            root, registration_manifest=registration,
            activation_manifest=activation,
        )


def test_activation_stale_registration_binding_fails_closed(
    tmp_path: Path,
) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path)
    activation = _activation(tmp_path, registration)
    # A later edit of the registration file at the SAME path must invalidate
    # the activation binding (all sessions stay burned, activation ineligible).
    _registration(tmp_path, registered_at="2026-07-19T00:00:00Z")
    with pytest.raises(EpochTelemetryError, match="not bound"):
        derive_epoch_role_counters(
            root, registration_manifest=registration,
            activation_manifest=activation,
        )


# --- telemetry_status (fail-closed activation evidence) -------------------------


def test_report_stamps_telemetry_status_complete_and_reconciled(
    tmp_path: Path,
) -> None:
    root = _home(tmp_path)
    for registration in (None, _registration(tmp_path)):
        report = derive_epoch_role_counters(
            root, registration_manifest=registration,
        )
        assert report["telemetry_status"] == TELEMETRY_STATUS_COMPLETE
        assert report["counts_reconciled"] is True


# --- record collection + dedup --------------------------------------------------


def test_printed_payload_and_bundle_copy_dedup_to_one_record(tmp_path: Path) -> None:
    root = _home(tmp_path)
    bundle = json.loads(
        (root / "2026-07-21" / BUNDLE_FILENAME).read_text(encoding="utf-8")
    )
    printed = dict(bundle)
    printed["bundle_path"] = str(root / "2026-07-21" / BUNDLE_FILENAME)
    printed["epoch_role_counters"] = {"totals": {}}
    _write(root / "session_2026-07-21.json", printed)
    records = collect_session_records(root)
    dates = [r.session_date for r in records]
    assert dates.count("2026-07-21") == 1
    record = [r for r in records if r.session_date == "2026-07-21"][0]
    assert len(record.sources) == 2


def test_distinct_attempts_on_one_date_stay_distinct(tmp_path: Path) -> None:
    root = _home(tmp_path)
    _write(
        root / "session_2026-07-21.json",
        _session("2026-07-21", "invalidated", marker="precheck_failure: x"),
    )
    records = collect_session_records(root)
    assert [r.session_date for r in records].count("2026-07-21") == 2


def test_excluded_records_counted_but_never_paired(tmp_path: Path) -> None:
    root = _home(tmp_path)
    _write(
        root / "session_2026-07-22.json",
        _session("2026-07-22", "invalidated", marker="precheck_failure: x"),
    )
    report = derive_epoch_role_counters(root)
    assert report["totals"]["records"] == 3
    assert report["totals"][ROLE_BURNED] == 2  # only the two VALID pairs
    entry = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-22"
    ][0]
    assert entry["role"] is None
    assert "not a paired session" in entry["role_reason"]


# --- epoch attribution ----------------------------------------------------------


def test_epochs_enumerate_archives_plus_current(tmp_path: Path) -> None:
    root = _home(tmp_path)
    epochs = enumerate_epochs(root)
    assert [e.epoch_id for e in epochs] == ["epoch-1", "epoch-2"]
    assert epochs[0].archived and epochs[0].minted
    assert not epochs[1].archived and epochs[1].minted


def test_freeze_fingerprint_attribution(tmp_path: Path) -> None:
    report = derive_epoch_role_counters(_home(tmp_path))
    by_date = {e["session_date"]: e for e in report["sessions"]}
    assert by_date["2026-07-11"]["epoch_id"] == "epoch-1"
    assert by_date["2026-07-11"]["attribution"] == ATTRIBUTION_FREEZE
    assert by_date["2026-07-21"]["epoch_id"] == "epoch-2"
    assert by_date["2026-07-21"]["attribution"] == ATTRIBUTION_FREEZE


def test_unproven_world_can_never_be_pilot(tmp_path: Path) -> None:
    root = _home(tmp_path)
    # A postdating VALID pair whose stamped world matches NO recorded freeze
    # (e.g. the freeze was clobbered): eligible on every other axis, but the
    # attribution is only location-based -> burned, never pilot.
    _write(
        root / "2026-07-22" / BUNDLE_FILENAME,
        _session("2026-07-22", "valid",
                 pins={"renquant-strategy-104": "zzz9"}, orch="0rch9",
                 as_of="2026-07-22T21:35:10Z"),
    )
    registration = _registration(tmp_path)
    report = derive_epoch_role_counters(root, registration_manifest=registration)
    entry = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-22"
    ][0]
    assert entry["attribution"] == ATTRIBUTION_ROOT
    assert entry["role"] == ROLE_BURNED
    assert "not proven" in entry["role_reason"]


def test_fingerprintless_archive_record_attributes_by_location(tmp_path: Path) -> None:
    root = _home(tmp_path)
    e1 = root / "archive" / "epoch1-freeze-20260711T072031"
    _write(
        e1 / "session_2026-07-10.json",
        _session("2026-07-10", "invalidated", marker="precheck_failure: y"),
    )
    report = derive_epoch_role_counters(root)
    entry = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-10"
    ][0]
    assert entry["epoch_id"] == "epoch-1"
    assert entry["attribution"] == ATTRIBUTION_ARCHIVE


def test_non_epoch_archive_record_is_pre_epoch(tmp_path: Path) -> None:
    root = _home(tmp_path)
    pre = root / "archive" / "pre-arming-attempts-20260710"
    _write(
        pre / "session_2026-07-10.json",
        _session("2026-07-10", "invalidated", marker="arm_failure: a, b"),
    )
    report = derive_epoch_role_counters(root)
    entry = [
        e for e in report["sessions"] if e["session_date"] == "2026-07-10"
    ][0]
    assert entry["epoch_id"] == PRE_EPOCH_ID


# --- runner exposure (existing reporting surface) -------------------------------
# Hermetic session harness mirroring tests/test_shadow_ab_runner.py.


PINS = {
    "renquant-strategy-104": "aaa1",
    "renquant-pipeline": "bbb2",
    "renquant-execution": "ccc3",
}
ORCH_COMMIT = "feedface"


def _fake_fingerprint(path: str | Path) -> str:
    return "sha256:fp-" + Path(path).read_text(encoding="utf-8").strip()


def _recording_runner(command, env):
    return subprocess.CompletedProcess(list(command), 0, stdout="", stderr="")


def _world(tmp_path: Path) -> dict[str, Path]:
    model = tmp_path / "model.pt"
    model.write_text("model-1", encoding="utf-8")
    calibrator = tmp_path / "calibrator.json"
    calibrator.write_text("cal-1", encoding="utf-8")
    manifest = tmp_path / "wf_manifest.json"
    manifest.write_text(json.dumps({"cuts": [1, 2, 3]}), encoding="utf-8")
    market = tmp_path / "market_snapshot.json"
    market.write_text(json.dumps({"as_of": "2026-07-21"}), encoding="utf-8")
    account = tmp_path / "account_snapshot.json"
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")

    def _config(path: Path, floor_mult: float) -> Path:
        path.write_text(json.dumps({
            "ranking": {"panel_scoring": {
                "artifact_path": str(model),
                "buy_floor_std_mult": floor_mult,
                "global_calibration": {
                    "enabled": True,
                    "artifact_path": str(calibrator),
                },
            }},
        }), encoding="utf-8")
        return path

    return {
        "config_a": _config(tmp_path / "strategy_config.shadow.json", 0.5),
        "config_b": _config(tmp_path / "strategy_config.shadow_b.json", 1.0),
        "manifest": manifest,
        "market": market,
        "account": account,
    }


def _run_session(tmp_path: Path, out_root: Path, **overrides):
    world = _world(tmp_path)
    kwargs = dict(
        config_a=world["config_a"],
        config_b=world["config_b"],
        data_manifest=world["manifest"],
        output_root=out_root,
        market_snapshot_json=world["market"],
        account_snapshot_json=world["account"],
        session_date="2026-07-21",
        repo_root=out_root.parent / "umbrella",
        strategy_dir=out_root.parent / "umbrella" / "backtesting" / "renquant_104",
        command_runner=_recording_runner,
        fingerprint_from_path=_fake_fingerprint,
        pins_resolver=lambda: dict(PINS),
        orchestrator_commit_resolver=lambda: ORCH_COMMIT,
        notifier=lambda title, body: None,
    )
    kwargs.update(overrides)
    return run_shadow_ab_session(**kwargs)


def test_runner_exposes_epoch_role_counters_on_reporting_surface(
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "sessions"
    payload = _run_session(tmp_path, out_root)
    assert payload["exit_code"] == 0
    report = payload["epoch_role_counters"]
    # No committed manifests -> the safe default: this valid pair is BURNED.
    assert report["safe_default_applied"] is True
    assert report["telemetry_status"] == TELEMETRY_STATUS_COMPLETE
    assert report["counts_reconciled"] is True
    assert report["totals"][ROLE_BURNED] == 1
    assert report["totals"][ROLE_PILOT] == 0
    # Self-minted current epoch, proven by its own freeze fingerprint.
    assert report["epochs"]["epoch-1"]["n_paired_sessions"][ROLE_BURNED] == 1
    assert report["sessions"][0]["attribution"] == ATTRIBUTION_FREEZE
    sidecar = json.loads(
        (out_root / EPOCH_ROLE_COUNTERS_FILENAME).read_text(encoding="utf-8")
    )
    assert sidecar["totals"] == report["totals"]
    # The on-disk bundle stays free of the derived report (dedup contract).
    bundle = json.loads(
        (out_root / "2026-07-21" / BUNDLE_FILENAME).read_text(encoding="utf-8")
    )
    assert "epoch_role_counters" not in bundle


def test_runner_records_derivation_failure_without_raising(tmp_path: Path) -> None:
    out_root = tmp_path / "sessions"
    payload = _run_session(
        tmp_path, out_root,
        registration_manifest=tmp_path / "missing_registration.json",
    )
    assert payload["exit_code"] == 0  # telemetry never changes the verdict
    assert "error" in payload["epoch_role_counters"]
    assert payload["epoch_role_counters"]["safe_default_applied"] is True
    # Fail-closed evidence stamp: the activation validator requires
    # "complete", so this payload can never support the >=40 condition.
    assert payload["epoch_role_counters"]["telemetry_status"] == "unavailable"


# --- CLI ------------------------------------------------------------------------


def test_cli_epoch_report_prints_and_writes(tmp_path: Path, capsys) -> None:
    root = _home(tmp_path)
    out_json = tmp_path / "report.json"
    rc = epoch_report_main([
        "--output-root", str(root), "--output-json", str(out_json),
    ])
    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["totals"][ROLE_BURNED] == 2
    assert json.loads(out_json.read_text(encoding="utf-8")) == printed


def test_cli_epoch_report_rejects_malformed_manifest(tmp_path: Path) -> None:
    root = _home(tmp_path)
    bad = tmp_path / "registration_manifest.json"
    _write(bad, {"schema_version": 1})  # missing epoch_id + registered_at
    with pytest.raises(SystemExit):
        epoch_report_main([
            "--output-root", str(root), "--registration-manifest", str(bad),
        ])


def test_cli_epoch_report_rejects_pinned_digest_mismatch(tmp_path: Path) -> None:
    root = _home(tmp_path)
    registration = _registration(tmp_path)
    with pytest.raises(SystemExit):
        epoch_report_main([
            "--output-root", str(root),
            "--registration-manifest", str(registration),
            "--registration-manifest-sha256", "0" * 64,
        ])
