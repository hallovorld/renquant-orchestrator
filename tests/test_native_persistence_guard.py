# R5 persistence-guard unit tests (T6/D6-F3 remediation, shadow-soak stage):
# fail-closed run-manifest + artifact-sha verification before native
# live/persistence mutation, with a SIGNED, expiring, single-run,
# identity-bound operator incident token as the ONLY override. Signatures are
# real OpenSSH detached signatures (ssh-keygen -Y) made with the committed
# PLACEHOLDER test key and verified against the committed
# security/persistence_guard_allowed_signers registry, so the exact
# production verification path is exercised. Git probe / fingerprint
# authorities are injected so everything else runs hermetically.
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator.native_live_context import canonical_json_sha256
from renquant_orchestrator.native_persistence_guard import (
    CHECK_ARTIFACT_SHA,
    CHECK_DECISION_SNAPSHOT,
    CHECK_RUN_MANIFEST,
    IncidentTokenError,
    MAX_INCIDENT_TOKEN_TTL,
    PersistenceGuardError,
    SIGNATURE_NAMESPACE,
    default_allowed_signers_path,
    validate_incident_token,
    verify_persistence_guard,
)
from renquant_orchestrator.shadow_ab_runner import EXPERIMENT_PIN_REPOS

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SIGNERS = REPO_ROOT / "security" / "persistence_guard_allowed_signers"
FIXTURE_KEY = Path(__file__).resolve().parent / "fixtures" / "persistence_guard_test_key"
TEST_PRINCIPAL = "persistence-guard-test-operator"

NOW = dt.datetime(2026, 7, 10, 3, 0, 0, tzinfo=dt.timezone.utc)
RUN_ID = "native-live-20260710"
MODEL_SHA = "sha256:fp-model-1"
# Fixed expected config sha for DIRECT validate_incident_token tests (the
# guard-level tests compute the real canonical sha of the tmp config).
DIRECT_CFG_SHA = "sha256:cfg-direct-1"

ALL_CHECKS = [CHECK_ARTIFACT_SHA, CHECK_DECISION_SNAPSHOT, CHECK_RUN_MANIFEST]


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


def _config_sha(config: Path) -> str:
    return canonical_json_sha256(json.loads(config.read_text(encoding="utf-8")))


def _token(
    *,
    run_id: str = RUN_ID,
    issued_at: str = "2026-07-10T00:00:00Z",
    expires_at: str = "2026-07-10T06:00:00Z",
    checks: list[str] | None = None,
    model_sha: str = MODEL_SHA,
    config_sha: str = DIRECT_CFG_SHA,
    operator: str = TEST_PRINCIPAL,
    **overrides,
) -> dict:
    scope: dict = {
        "run_id": run_id,
        "checks": list(checks) if checks is not None else list(ALL_CHECKS),
        "model_content_sha256": model_sha,
        "strategy_config_sha256": config_sha,
    }
    token = {
        "schema_version": 1,
        "kind": "persistence_guard_incident_token",
        "incident": "INC-2026-07-10-pin-migration",
        "operator": operator,
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


def _sign_token(tmp_path: Path, token_path: Path, *, key: Path | None = None) -> Path:
    """Detached-sign the token file with the (placeholder) test key."""
    key_src = key or FIXTURE_KEY
    key_copy = tmp_path / f"signing_{key_src.name}"
    if not key_copy.exists():
        key_copy.write_bytes(key_src.read_bytes())
        key_copy.chmod(0o600)
    subprocess.run(
        [
            "ssh-keygen", "-Y", "sign",
            "-f", str(key_copy),
            "-n", SIGNATURE_NAMESPACE,
            str(token_path),
        ],
        check=True,
        capture_output=True,
    )
    return token_path.with_name(token_path.name + ".sig")


def _signed_token(tmp_path: Path, token: dict) -> Path:
    path = _write_token(tmp_path, token)
    _sign_token(tmp_path, path)
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
        allowed_signers=ALLOWED_SIGNERS,
        git_probe=_probe(manifest),
        fingerprint_from_path=_fake_fingerprint,
        now=NOW,
    )
    kwargs.update(overrides)
    return verify_persistence_guard(**kwargs)


# --- verification checks ---------------------------------------------------------


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


# --- signed incident-token override ----------------------------------------------


def test_signed_token_overrides_and_is_fully_logged(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    config = _write_config(tmp_path)
    token_path = _signed_token(
        tmp_path, _token(checks=[CHECK_RUN_MANIFEST], config_sha=_config_sha(config))
    )
    result = _guard(
        tmp_path,
        manifest=manifest,
        config=config,
        git_probe=_probe(manifest, drift={"renquant-pipeline"}),
        incident_token_json=token_path,
    )
    assert result["verified"] is False
    override = result["override"]
    assert override["incident"] == "INC-2026-07-10-pin-migration"
    assert override["operator"] == TEST_PRINCIPAL
    assert override["expires_at"] == "2026-07-10T06:00:00Z"
    assert override["scope"]["run_id"] == RUN_ID
    assert override["scope"]["model_content_sha256"] == MODEL_SHA
    assert override["overridden_checks"] == [CHECK_RUN_MANIFEST]
    assert override["token_path"] == str(token_path)
    assert override["signature"]["verified"] is True
    assert override["signature"]["principal"] == TEST_PRINCIPAL
    assert override["signature"]["namespace"] == SIGNATURE_NAMESPACE
    assert override["signature"]["allowed_signers"] == str(ALLOWED_SIGNERS)


def test_unsigned_token_fails_closed(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    config = _write_config(tmp_path)
    token_path = _write_token(tmp_path, _token(config_sha=_config_sha(config)))
    # deliberately NOT signed
    with pytest.raises(IncidentTokenError, match="NO detached signature"):
        _guard(
            tmp_path,
            manifest=manifest,
            config=config,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


def test_forged_token_fails_closed(tmp_path: Path) -> None:
    """Any caller-side edit after signing (e.g. extending expiry) is a forgery."""
    manifest = _write_manifest(tmp_path)
    config = _write_config(tmp_path)
    token = _token(config_sha=_config_sha(config))
    token_path = _signed_token(tmp_path, token)
    token["expires_at"] = "2026-07-10T23:59:59Z"  # tamper AFTER signing
    token_path.write_text(json.dumps(token), encoding="utf-8")
    with pytest.raises(IncidentTokenError, match="signature verification FAILED"):
        _guard(
            tmp_path,
            manifest=manifest,
            config=config,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


def test_wrong_key_token_fails_closed(tmp_path: Path) -> None:
    """A syntactically perfect token signed by a key OUTSIDE the committed
    allowed_signers registry never unblocks."""
    manifest = _write_manifest(tmp_path)
    config = _write_config(tmp_path)
    rogue_key = tmp_path / "rogue_key"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", str(rogue_key)],
        check=True,
        capture_output=True,
    )
    token_path = _write_token(tmp_path, _token(config_sha=_config_sha(config)))
    _sign_token(tmp_path, token_path, key=rogue_key)
    with pytest.raises(IncidentTokenError, match="signature verification FAILED"):
        _guard(
            tmp_path,
            manifest=manifest,
            config=config,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


def test_wrong_principal_fails_closed(tmp_path: Path) -> None:
    """Claiming a different operator than the allowed_signers principal fails
    even when the signature bytes are made with a registered key."""
    manifest = _write_manifest(tmp_path)
    config = _write_config(tmp_path)
    token_path = _signed_token(
        tmp_path, _token(operator="mallory", config_sha=_config_sha(config))
    )
    with pytest.raises(IncidentTokenError, match="signature verification FAILED"):
        _guard(
            tmp_path,
            manifest=manifest,
            config=config,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


def test_expired_token_never_unblocks_even_when_signed(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    config = _write_config(tmp_path)
    token_path = _signed_token(
        tmp_path,
        _token(
            issued_at="2026-07-09T20:00:00Z",
            expires_at="2026-07-10T02:59:00Z",
            config_sha=_config_sha(config),
        ),
    )
    with pytest.raises(IncidentTokenError, match="EXPIRED"):
        _guard(
            tmp_path,
            manifest=manifest,
            config=config,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


def test_token_scope_checks_must_cover_every_failure(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    config = _write_config(tmp_path)
    token_path = _signed_token(
        tmp_path, _token(checks=[CHECK_ARTIFACT_SHA], config_sha=_config_sha(config))
    )
    with pytest.raises(IncidentTokenError, match="does not cover"):
        _guard(
            tmp_path,
            manifest=manifest,
            config=config,
            git_probe=_probe(manifest, drift={"renquant-pipeline"}),
            incident_token_json=token_path,
        )


# --- token payload contract (post-signature validation) ---------------------------


def _validate(token: dict, **overrides):
    kwargs = dict(
        run_id=RUN_ID,
        model_content_sha256=MODEL_SHA,
        strategy_config_sha256=DIRECT_CFG_SHA,
        now=NOW,
    )
    kwargs.update(overrides)
    return validate_incident_token(token, **kwargs)


def test_token_lifetime_ceiling_rejects_standing_overrides() -> None:
    token = _token(issued_at="2026-07-10T00:00:00Z", expires_at="2026-07-12T00:00:00Z")
    with pytest.raises(IncidentTokenError, match="exceeds"):
        _validate(token)
    assert dt.timedelta(hours=48) > MAX_INCIDENT_TOKEN_TTL


def test_token_is_single_run_scoped() -> None:
    with pytest.raises(IncidentTokenError, match="single-run"):
        _validate(_token(run_id="some-other-run"))
    # a run without a run_id can never consume a token
    with pytest.raises(IncidentTokenError, match="single-run"):
        _validate(_token(), run_id=None)


def test_token_identity_binding_is_required_and_exact() -> None:
    with pytest.raises(IncidentTokenError, match="different model"):
        _validate(_token(model_sha="sha256:fp-other-model"))
    with pytest.raises(IncidentTokenError, match="different config"):
        _validate(_token(config_sha="sha256:cfg-other"))
    stripped = _token()
    del stripped["scope"]["model_content_sha256"]
    with pytest.raises(IncidentTokenError, match="model_content_sha256 is REQUIRED"):
        _validate(stripped)
    stripped = _token()
    del stripped["scope"]["strategy_config_sha256"]
    with pytest.raises(IncidentTokenError, match="strategy_config_sha256 is REQUIRED"):
        _validate(stripped)


def test_token_missing_fields_or_wrong_kind_rejected() -> None:
    with pytest.raises(IncidentTokenError, match="operator"):
        _validate(_token(operator=""))
    with pytest.raises(IncidentTokenError, match="incident"):
        _validate(_token(incident="  "))
    with pytest.raises(IncidentTokenError, match="kind"):
        _validate(_token(kind="some_other_token"))
    with pytest.raises(IncidentTokenError, match="schema_version"):
        _validate(_token(schema_version=99))


def test_token_not_yet_valid_rejected() -> None:
    token = _token(issued_at="2026-07-10T04:00:00Z", expires_at="2026-07-10T08:00:00Z")
    with pytest.raises(IncidentTokenError, match="not yet valid"):
        _validate(token)


def test_token_naive_timestamps_rejected() -> None:
    token = _token(issued_at="2026-07-10T00:00:00", expires_at="2026-07-10T06:00:00Z")
    with pytest.raises(IncidentTokenError, match="explicit UTC offset"):
        _validate(token)


def test_token_checks_are_required_and_vocabulary_checked() -> None:
    with pytest.raises(IncidentTokenError, match="scope.checks is REQUIRED"):
        _validate(_token(checks=["everything"]))
    missing = _token()
    del missing["scope"]["checks"]
    with pytest.raises(IncidentTokenError, match="scope.checks is REQUIRED"):
        _validate(missing)


# --- hard (non-overridable) guard-input errors ------------------------------------


def test_unreadable_manifest_is_hard_error_even_with_valid_token(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    token_path = _signed_token(tmp_path, _token(config_sha=_config_sha(config)))
    with pytest.raises(PersistenceGuardError, match="not token-overridable"):
        verify_persistence_guard(
            run_manifest_json=tmp_path / "missing_manifest.json",
            strategy_config_json=config,
            model_content_sha256=MODEL_SHA,
            run_id=RUN_ID,
            incident_token_json=token_path,
            allowed_signers=ALLOWED_SIGNERS,
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


# --- committed registry meta-contract ----------------------------------------------


def test_committed_allowed_signers_is_the_placeholder_and_is_default() -> None:
    """The committed registry entry is a clearly labeled TEST-ONLY placeholder
    (the operator must replace it before the enforcement flip) and IS the
    guard's default verification target."""
    assert default_allowed_signers_path() == ALLOWED_SIGNERS
    content = ALLOWED_SIGNERS.read_text(encoding="utf-8")
    assert "PLACEHOLDER" in content
    assert f'namespaces="{SIGNATURE_NAMESPACE}"' in content
    entries = [
        line for line in content.splitlines() if line.strip() and not line.startswith("#")
    ]
    assert len(entries) == 1
    assert entries[0].startswith(TEST_PRINCIPAL + " ")
    # and the committed private test key must still match the registry entry
    pub_key_material = (
        FIXTURE_KEY.with_name(FIXTURE_KEY.name + ".pub")
        .read_text(encoding="utf-8")
        .split()[1]
    )
    assert pub_key_material in entries[0]
