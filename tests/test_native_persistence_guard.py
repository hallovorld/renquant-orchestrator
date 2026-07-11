# R5 persistence-guard unit tests (T6/D6-F3 remediation): fail-closed
# run-manifest + artifact-sha verification before native live/persistence
# mutation, with the expiring single-run operator incident token as the ONLY
# override. All external authorities (git probe, fingerprint) are injected so
# these run hermetically.
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator.native_persistence_guard import (
    CHECK_ARTIFACT_SHA,
    CHECK_DECISION_SNAPSHOT,
    CHECK_RUN_MANIFEST,
    IncidentTokenError,
    MAX_INCIDENT_TOKEN_TTL,
    PersistenceGuardError,
    validate_incident_token,
    verify_persistence_guard,
)
from renquant_orchestrator.shadow_ab_runner import EXPERIMENT_PIN_REPOS

NOW = dt.datetime(2026, 7, 10, 3, 0, 0, tzinfo=dt.timezone.utc)
RUN_ID = "native-live-20260710"


def _commit(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()


def _write_manifest(tmp_path: Path) -> Path:
    repos = {}
    for name in EXPERIMENT_PIN_REPOS:
        repo_dir = tmp_path / "repos" / name
        repo_dir.mkdir(parents=True, exist_ok=True)
        repos[name] = {"path": str(repo_dir), "commit": _commit(name)}
    manifest = tmp_path / "run_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "repos": repos, "data_revision": "rev-1"}),
        encoding="utf-8",
    )
    return manifest


def _probe(manifest_path: Path, *, drift: set[str] = frozenset(), dirty: set[str] = frozenset()):
    """Fake git probe answering rev-parse/status for the manifest's repos."""
    repos = json.loads(manifest_path.read_text(encoding="utf-8"))["repos"]
    head_by_path = {
        entry["path"]: ("f" * 40 if name in drift else entry["commit"])
        for name, entry in repos.items()
    }
    dirty_paths = {repos[name]["path"] for name in dirty}

    def probe(args):
        path = args[1]
        if list(args[2:]) == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(list(args), 0, stdout=head_by_path[path] + "\n", stderr="")
        if list(args[2:]) == ["status", "--porcelain"]:
            out = " M src/dirty.py\n" if path in dirty_paths else ""
            return subprocess.CompletedProcess(list(args), 0, stdout=out, stderr="")
        raise AssertionError(f"unexpected git probe: {args}")

    return probe


def _fake_fingerprint(path: str | Path) -> str:
    return "sha256:fp-" + Path(path).read_text(encoding="utf-8").strip()


def _write_config(tmp_path: Path) -> Path:
    model = tmp_path / "model.pt"
    model.write_text("model-1", encoding="utf-8")
    config = tmp_path / "configs" / "strategy_config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps({"ranking": {"panel_scoring": {"artifact_path": str(model)}}}),
        encoding="utf-8",
    )
    return config


MODEL_SHA = "sha256:fp-model-1"


def _token(
    *,
    run_id: str = RUN_ID,
    issued_at: str = "2026-07-10T00:00:00Z",
    expires_at: str = "2026-07-10T06:00:00Z",
    checks: list[str] | None = None,
    **overrides,
) -> dict:
    scope: dict = {"run_id": run_id}
    if checks is not None:
        scope["checks"] = checks
    token = {
        "schema_version": 1,
        "kind": "persistence_guard_incident_token",
        "incident": "INC-2026-07-10-pin-migration",
        "operator": "renhao",
        "reason": "planned pin bump mid-incident; verified manually",
        "issued_at": issued_at,
        "expires_at": expires_at,
        "scope": scope,
    }
    token.update(overrides)
    return token


def _write_token(tmp_path: Path, token: dict) -> Path:
    path = tmp_path / "incident_token.json"
    path.write_text(json.dumps(token), encoding="utf-8")
    return path


def _guard(tmp_path: Path, **overrides):
    manifest = overrides.pop("manifest", None) or _write_manifest(tmp_path)
    config = overrides.pop("config", None) or _write_config(tmp_path)
    kwargs = dict(
        run_manifest_json=manifest,
        strategy_config_json=config,
        model_content_sha256=MODEL_SHA,
        run_id=RUN_ID,
        repo_root=tmp_path,
        git_probe=_probe(manifest),
        fingerprint_from_path=_fake_fingerprint,
        now=NOW,
    )
    kwargs.update(overrides)
    return verify_persistence_guard(**kwargs)


def test_guard_verified_happy_path_stamps_identities(tmp_path: Path) -> None:
    result = _guard(tmp_path)
    assert result["verified"] is True
    assert result["armed"] is True
    assert result["override"] is None
    assert result["failures"] == []
    assert result["run_id"] == RUN_ID
    assert result["run_manifest"]["resolved_repos"] == {
        name: _commit(name) for name in EXPERIMENT_PIN_REPOS
    }
    assert result["run_manifest"]["data_revision"] == "rev-1"
    assert result["artifacts"] == {
        "model_content_sha256": MODEL_SHA,
        "calibrator_content_sha256": None,
        "verified": True,
    }
    assert result["strategy_config_sha256"].startswith("sha256:")


def test_guard_fails_closed_on_pin_drift_without_token(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    with pytest.raises(PersistenceGuardError, match="FAILED CLOSED.*renquant-pipeline"):
        _guard(
            tmp_path,
            manifest=manifest,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
        )


def test_guard_fails_closed_on_dirty_checkout(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    with pytest.raises(PersistenceGuardError, match="DIRTY"):
        _guard(
            tmp_path,
            manifest=manifest,
            git_probe=_probe(manifest, dirty={"renquant-execution"}),
        )


def test_guard_fails_closed_on_artifact_sha_mismatch(tmp_path: Path) -> None:
    with pytest.raises(PersistenceGuardError, match=CHECK_ARTIFACT_SHA):
        _guard(tmp_path, model_content_sha256="sha256:fp-STALE")


def test_guard_binds_inference_payload_to_frozen_digest(tmp_path: Path) -> None:
    # missing/unverified stamp -> blocked
    with pytest.raises(PersistenceGuardError, match=CHECK_DECISION_SNAPSHOT):
        _guard(tmp_path, decision_snapshot_digest="d1", inference_metadata={})
    with pytest.raises(PersistenceGuardError, match=CHECK_DECISION_SNAPSHOT):
        _guard(
            tmp_path,
            decision_snapshot_digest="d1",
            inference_metadata={
                "decision_snapshot_digest": "d1",
                "decision_snapshot_verified": False,
            },
        )
    # matching verified stamp -> allowed
    result = _guard(
        tmp_path,
        decision_snapshot_digest="d1",
        inference_metadata={
            "decision_snapshot_digest": "d1",
            "decision_snapshot_verified": True,
        },
    )
    assert result["verified"] is True
    assert result["decision_snapshot_digest"] == "d1"


def test_guard_readonly_soak_records_would_have_blocked(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    result = _guard(
        tmp_path,
        manifest=manifest,
        git_probe=_probe(manifest, drift={"renquant-strategy-104"}),
        enforce=False,
    )
    assert result["verified"] is False
    assert result["would_have_blocked"] is True
    assert result["failures"][0]["check"] == CHECK_RUN_MANIFEST


def test_valid_token_overrides_and_is_fully_logged(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    token_path = _write_token(tmp_path, _token())
    result = _guard(
        tmp_path,
        manifest=manifest,
        git_probe=_probe(manifest, drift={"renquant-pipeline"}),
        incident_token_json=token_path,
    )
    assert result["verified"] is False
    override = result["override"]
    assert override["incident"] == "INC-2026-07-10-pin-migration"
    assert override["operator"] == "renhao"
    assert override["expires_at"] == "2026-07-10T06:00:00Z"
    assert override["scope"]["run_id"] == RUN_ID
    assert override["overridden_checks"] == [CHECK_RUN_MANIFEST]
    assert override["token_path"] == str(token_path)


def test_expired_token_never_unblocks(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    token_path = _write_token(
        tmp_path,
        _token(issued_at="2026-07-09T20:00:00Z", expires_at="2026-07-10T02:59:00Z"),
    )
    with pytest.raises(IncidentTokenError, match="EXPIRED"):
        _guard(
            tmp_path,
            manifest=manifest,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


def test_token_lifetime_ceiling_rejects_standing_overrides(tmp_path: Path) -> None:
    token = _token(issued_at="2026-07-10T00:00:00Z", expires_at="2026-07-12T00:00:00Z")
    with pytest.raises(IncidentTokenError, match="exceeds"):
        validate_incident_token(token, run_id=RUN_ID, now=NOW)
    assert dt.timedelta(hours=48) > MAX_INCIDENT_TOKEN_TTL


def test_token_is_single_run_scoped(tmp_path: Path) -> None:
    with pytest.raises(IncidentTokenError, match="single-run"):
        validate_incident_token(_token(run_id="some-other-run"), run_id=RUN_ID, now=NOW)
    # a run without a run_id can never consume a token
    with pytest.raises(IncidentTokenError, match="single-run"):
        validate_incident_token(_token(), run_id=None, now=NOW)


def test_token_scope_checks_must_cover_every_failure(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    token_path = _write_token(tmp_path, _token(checks=[CHECK_ARTIFACT_SHA]))
    with pytest.raises(IncidentTokenError, match="does not cover"):
        _guard(
            tmp_path,
            manifest=manifest,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


def test_token_missing_fields_or_wrong_kind_rejected() -> None:
    with pytest.raises(IncidentTokenError, match="operator"):
        validate_incident_token(_token(operator=""), run_id=RUN_ID, now=NOW)
    with pytest.raises(IncidentTokenError, match="incident"):
        validate_incident_token(_token(incident="  "), run_id=RUN_ID, now=NOW)
    with pytest.raises(IncidentTokenError, match="kind"):
        validate_incident_token(_token(kind="some_other_token"), run_id=RUN_ID, now=NOW)
    with pytest.raises(IncidentTokenError, match="schema_version"):
        validate_incident_token(_token(schema_version=99), run_id=RUN_ID, now=NOW)


def test_token_not_yet_valid_rejected() -> None:
    token = _token(issued_at="2026-07-10T04:00:00Z", expires_at="2026-07-10T08:00:00Z")
    with pytest.raises(IncidentTokenError, match="not yet valid"):
        validate_incident_token(token, run_id=RUN_ID, now=NOW)


def test_token_naive_timestamps_rejected() -> None:
    token = _token(issued_at="2026-07-10T00:00:00", expires_at="2026-07-10T06:00:00Z")
    with pytest.raises(IncidentTokenError, match="explicit UTC offset"):
        validate_incident_token(token, run_id=RUN_ID, now=NOW)


def test_token_invalid_scope_checks_rejected() -> None:
    with pytest.raises(IncidentTokenError, match="scope.checks"):
        validate_incident_token(_token(checks=["everything"]), run_id=RUN_ID, now=NOW)


def test_unreadable_manifest_is_hard_error_even_with_valid_token(tmp_path: Path) -> None:
    token_path = _write_token(tmp_path, _token())
    config = _write_config(tmp_path)
    with pytest.raises(PersistenceGuardError, match="not token-overridable"):
        verify_persistence_guard(
            run_manifest_json=tmp_path / "missing_manifest.json",
            strategy_config_json=config,
            model_content_sha256=MODEL_SHA,
            run_id=RUN_ID,
            incident_token_json=token_path,
            fingerprint_from_path=_fake_fingerprint,
            now=NOW,
        )


def test_unreadable_strategy_config_is_hard_error(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    with pytest.raises(PersistenceGuardError, match="strategy config unreadable"):
        verify_persistence_guard(
            run_manifest_json=manifest,
            strategy_config_json=tmp_path / "missing_config.json",
            model_content_sha256=MODEL_SHA,
            run_id=RUN_ID,
            git_probe=_probe(manifest),
            fingerprint_from_path=_fake_fingerprint,
            now=NOW,
        )


def test_unused_token_is_noted_when_guard_verifies(tmp_path: Path) -> None:
    token_path = _write_token(tmp_path, _token())
    result = _guard(tmp_path, incident_token_json=token_path)
    assert result["verified"] is True
    assert result["override"] is None
    assert result["incident_token_unused"] == str(token_path)
