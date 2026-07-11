"""R-PIN Stage 1 — ``deploy-pin capture`` (design §9 Stage 1 deliverable 3).

Fixtures build a synthetic umbrella tree (an on-disk lock + real
``.subrepo_runtime/repos/<name>`` git clones) so agreement/disagreement is
exercised against real git state, never mocks. The capture must:

* FAIL CLOSED on ANY lock↔clone disagreement (all disagreements listed);
* emit a PORTABLE manifest (identity only — no host path anywhere) plus the
  host runtime inventory;
* default to DRY-RUN (writes nothing); ``--write`` persists to the neutral
  state root and re-verifies read-only;
* keep the expected-generation record FORWARD-ONLY across captures.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator.deploy_pin import (
    DeployPinError,
    capture_deployed_state,
    main as deploy_pin_main,
    read_lock_subrepo_identity,
    resolve_evidence_bundle_path,
    run_capture,
    verify_deployment_manifest,
)
from renquant_orchestrator.deployment_manifest import (
    load_deployment_manifest,
    read_expected_generation,
    repo_identity_digest,
    sha256_of_bytes,
)

REPO_NAMES = ("renquant-strategy-104", "renquant-pipeline", "renquant-artifacts")


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc.stdout.strip()


def _make_repo(path: Path, marker: str) -> str:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    (path / "f.txt").write_text(marker, encoding="utf-8")
    _git(path, "add", "f.txt")
    _git(path, "commit", "-qm", f"c1-{marker}")
    return _git(path, "rev-parse", "HEAD")


def make_umbrella(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    """A synthetic umbrella: lock + matching .subrepo_runtime clones."""
    umbrella = tmp_path / "umbrella"
    clones_root = umbrella / ".subrepo_runtime" / "repos"
    clones: dict[str, Path] = {}
    subrepos = []
    for name in REPO_NAMES:
        clone = clones_root / name
        head = _make_repo(clone, name)
        clones[name] = clone
        subrepos.append({
            "name": name,
            "role": f"{name} role",
            "local_path": str(tmp_path / "siblings" / name),  # host detail —
            # must NEVER surface in the portable manifest
            "remote": f"https://github.com/hallovorld/{name}",
            "branch": "main",
            "commit": head,
            "test_command": "make test",  # legacy field — must never surface
            "status": "bootstrapped",
        })
    lock = umbrella / "subrepos.lock.json"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({
            "schema_version": 1,
            "source_repo": {"name": "RenQuant"},
            "subrepos": subrepos,
        }, indent=2),
        encoding="utf-8",
    )
    return lock, clones


def _capture_argv(lock: Path, state_root: Path, *extra: str) -> list[str]:
    return [
        "capture",
        "--lock", str(lock),
        "--state-root", str(state_root),
        "--artifact-store-repo", "renquant-artifacts",
        *extra,
    ]


def _run_json(argv: list[str], capsys) -> tuple[int, dict]:
    rc = deploy_pin_main(argv)
    captured = capsys.readouterr()
    return rc, (json.loads(captured.out) if captured.out.strip() else {})


# --- agreement: portable manifest + inventory --------------------------------------


def test_capture_agreement_emits_portable_manifest(tmp_path: Path, capsys) -> None:
    lock, clones = make_umbrella(tmp_path)
    state_root = tmp_path / "deploy-root"
    rc, report = _run_json(_capture_argv(lock, state_root), capsys)
    assert rc == 0
    assert report["mode"] == "dry-run"
    manifest = report["manifest"]
    lock_payload = json.loads(lock.read_text(encoding="utf-8"))
    for entry in lock_payload["subrepos"]:
        recorded = manifest["repos"][entry["name"]]
        assert recorded == {
            "remote": entry["remote"],
            "branch": entry["branch"],
            "commit": entry["commit"],
            "role": entry["role"],
            "status": entry["status"],
        }
    # first record: generation 1, chains to nothing, pre-seal state
    assert manifest["generation"] == 1
    assert manifest["deployment"]["supersedes_sha256"] is None
    assert manifest["deployment"]["state"] == "captured"
    assert manifest["deployment"]["verify"]["profile"] == "readonly-e2e"
    assert manifest["deployment"]["verify"]["args"] == {"min_admits": 1}
    # PORTABLE: no host location and no legacy lock field anywhere
    manifest_text = json.dumps(manifest)
    assert "local_path" not in manifest_text
    assert "test_command" not in manifest_text
    assert str(tmp_path) not in manifest_text
    # the inventory carries the host truth instead
    inventory = report["runtime_inventory"]
    for name, clone in clones.items():
        assert inventory["repos"][name]["path"] == str(clone.resolve())


def test_capture_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    lock, _ = make_umbrella(tmp_path)
    state_root = tmp_path / "deploy-root"
    rc, report = _run_json(_capture_argv(lock, state_root), capsys)
    assert rc == 0
    assert report["written"] == []
    assert "would_write" in report
    assert not state_root.exists()


def test_capture_write_persists_and_reverifies(tmp_path: Path, capsys) -> None:
    lock, _ = make_umbrella(tmp_path)
    state_root = tmp_path / "deploy-root"
    rc, report = _run_json(
        _capture_argv(
            lock, state_root, "--write",
            "--evidence-ref", "store://records/readonly-e2e-20260711",
        ),
        capsys,
    )
    assert rc == 0
    manifest_path = state_root / "deployment-manifest.json"
    inventory_path = state_root / "runtime-inventory.json"
    record_path = state_root / "expected-generation.json"
    assert manifest_path.exists() and inventory_path.exists() and record_path.exists()
    assert (state_root / "receipts").is_dir()
    # sealed evidence ⇒ durable 'deployed' state; loader accepts the file
    loaded = load_deployment_manifest(manifest_path)
    assert loaded["deployment"]["state"] == "deployed"
    # epoch record matches the file bytes exactly
    record = read_expected_generation(state_root)
    assert record["generation"] == 1
    assert record["manifest_sha256"] == sha256_of_bytes(manifest_path.read_bytes())
    # the read-only re-verification ran and resolved every repo
    assert set(report["reverified"]["repos"]) == set(REPO_NAMES)


def test_second_capture_advances_the_epoch(tmp_path: Path, capsys) -> None:
    lock, _ = make_umbrella(tmp_path)
    state_root = tmp_path / "deploy-root"
    rc, _ = _run_json(_capture_argv(lock, state_root, "--write"), capsys)
    assert rc == 0
    first_sha = sha256_of_bytes((state_root / "deployment-manifest.json").read_bytes())
    rc, report = _run_json(_capture_argv(lock, state_root, "--write"), capsys)
    assert rc == 0
    manifest = report["manifest"]
    # a re-capture is a NEW generation chaining to the prior record — never
    # a reuse (§5.1: every mutation advances the epoch)
    assert manifest["generation"] == 2
    assert manifest["deployment"]["supersedes_sha256"] == first_sha
    assert read_expected_generation(state_root)["generation"] == 2


def test_capture_refuses_torn_state_root(tmp_path: Path, capsys) -> None:
    lock, _ = make_umbrella(tmp_path)
    state_root = tmp_path / "deploy-root"
    rc, _ = _run_json(_capture_argv(lock, state_root, "--write"), capsys)
    assert rc == 0
    # simulate the torn case: epoch record lost, manifest kept
    (state_root / "expected-generation.json").unlink()
    rc = deploy_pin_main(_capture_argv(lock, state_root, "--write"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "TORN" in err


# --- disagreement: fail closed --------------------------------------------------------


def test_clone_head_drift_fails_closed(tmp_path: Path, capsys) -> None:
    lock, clones = make_umbrella(tmp_path)
    drifted = clones["renquant-pipeline"]
    (drifted / "f.txt").write_text("drift", encoding="utf-8")
    _git(drifted, "commit", "-aqm", "drift")
    state_root = tmp_path / "deploy-root"
    rc = deploy_pin_main(_capture_argv(lock, state_root, "--write"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "DISAGREES" in err
    assert "renquant-pipeline" in err
    assert "on-disk lock commit" in err
    # fail-closed means NOTHING was written
    assert not state_root.exists()


def test_missing_clone_fails_closed(tmp_path: Path, capsys) -> None:
    lock, clones = make_umbrella(tmp_path)
    import shutil

    shutil.rmtree(clones["renquant-artifacts"])
    rc = deploy_pin_main(_capture_argv(lock, tmp_path / "deploy-root"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "renquant-artifacts" in err and "does not exist" in err


def test_all_disagreements_are_listed(tmp_path: Path) -> None:
    lock, clones = make_umbrella(tmp_path)
    for name in ("renquant-strategy-104", "renquant-pipeline"):
        (clones[name] / "f.txt").write_text("drift", encoding="utf-8")
        _git(clones[name], "commit", "-aqm", "drift")
    with pytest.raises(DeployPinError) as excinfo:
        capture_deployed_state(lock_path=lock)
    message = str(excinfo.value)
    assert "renquant-strategy-104" in message
    assert "renquant-pipeline" in message
    assert "2 problem(s)" in message


def test_short_lock_commit_is_a_disagreement(tmp_path: Path) -> None:
    """A >=12-hex PREFIX satisfies the checkout check, but the deployed
    truth must agree on the FULL sha — the authority record can never be
    anchored to a prefix."""
    lock, _ = make_umbrella(tmp_path)
    payload = json.loads(lock.read_text(encoding="utf-8"))
    payload["subrepos"][0]["commit"] = payload["subrepos"][0]["commit"][:16]
    lock.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DeployPinError, match="not the full clone HEAD"):
        capture_deployed_state(lock_path=lock)


def test_lock_missing_identity_field_fails_closed(tmp_path: Path) -> None:
    lock, _ = make_umbrella(tmp_path)
    payload = json.loads(lock.read_text(encoding="utf-8"))
    del payload["subrepos"][1]["role"]
    payload["subrepos"][2]["status"] = ""
    lock.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DeployPinError) as excinfo:
        read_lock_subrepo_identity(lock)
    message = str(excinfo.value)
    assert "renquant-pipeline" in message and "role" in message
    assert "renquant-artifacts" in message and "status" in message


def test_unreadable_lock_fails_closed(tmp_path: Path) -> None:
    lock = tmp_path / "subrepos.lock.json"
    lock.write_text("{broken", encoding="utf-8")
    with pytest.raises(DeployPinError, match="unreadable"):
        read_lock_subrepo_identity(lock)


# --- CLI surface -----------------------------------------------------------------------


def test_bad_evidence_ref_is_a_usage_error(tmp_path: Path) -> None:
    lock, _ = make_umbrella(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        deploy_pin_main(
            _capture_argv(lock, tmp_path / "root", "--evidence-ref", "/tmp/x.log")
        )
    assert excinfo.value.code == 2


def test_cli_dispatch_via_orchestrator_entrypoint(tmp_path: Path, capsys) -> None:
    from renquant_orchestrator.cli import main as cli_main

    lock, _ = make_umbrella(tmp_path)
    rc = cli_main([
        "deploy-pin", "capture",
        "--lock", str(lock),
        "--state-root", str(tmp_path / "deploy-root"),
    ])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "dry-run"
    assert report["manifest"]["kind"] == "deployment-manifest"


def test_run_capture_stdout_injectable(tmp_path: Path) -> None:
    lock, _ = make_umbrella(tmp_path)
    buffer = io.StringIO()
    rc = run_capture(
        lock_path=lock,
        runtime_root=None,
        state_root=tmp_path / "deploy-root",
        write=False,
        deployed_by="operator",
        deployed_at=None,
        evidence_ref=None,
        artifact_store_repo="renquant-artifacts",
        artifact_store_path="",
        stdout=buffer,
    )
    assert rc == 0
    assert json.loads(buffer.getvalue())["mode"] == "dry-run"


# --- deploy-pin verify: evidence_ref cross-check (Codex #483 follow-up) -----------


def _seal_evidence_bundle(
    github_root: Path,
    *,
    repo: str = "renquant-artifacts",
    store_subdir: str = "store",
    rel: str = "experiments/verify-test/RUN-LOCK.json",
    lock_identity_digest: str,
    inventory_identity_digest: str,
) -> None:
    """Materialize a synthetic sibling checkout with a sealed evidence
    bundle at ``<github_root>/<repo>/<store_subdir>/<rel>`` plus its
    STORE-MANIFEST.json content-hash entry (the renquant-artifacts #13/#14
    convention) — never touches any real checkout."""
    store_root = github_root / repo / store_subdir
    bundle_path = store_root / rel
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(
            {
                "lock_identity_digest": lock_identity_digest,
                "inventory_identity_digest": inventory_identity_digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    bundle_path.write_text(data, encoding="utf-8")
    store_manifest_path = store_root / "STORE-MANIFEST.json"
    store_manifest = (
        json.loads(store_manifest_path.read_text(encoding="utf-8"))
        if store_manifest_path.exists()
        else {}
    )
    store_manifest[rel] = sha256_of_bytes(data.encode("utf-8"))
    store_manifest_path.write_text(
        json.dumps(store_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


_VERIFY_EVIDENCE_REF = "store://experiments/verify-test/RUN-LOCK.json"


def test_verify_accepts_matching_evidence_bundle(tmp_path: Path, capsys) -> None:
    lock, _ = make_umbrella(tmp_path)
    digest = repo_identity_digest(read_lock_subrepo_identity(lock))
    github_root = tmp_path / "siblings"
    _seal_evidence_bundle(
        github_root, lock_identity_digest=digest, inventory_identity_digest=digest
    )

    rc, report = _run_json(
        _capture_argv(
            lock, tmp_path / "deploy-root", "--write",
            "--evidence-ref", _VERIFY_EVIDENCE_REF,
            "--artifact-store-path", "store",
        ),
        capsys,
    )
    assert rc == 0
    assert report["manifest"]["deployment"]["state"] == "deployed"
    manifest_path = tmp_path / "committed-manifest.json"
    manifest_path.write_text(json.dumps(report["manifest"]), encoding="utf-8")

    verify_report = verify_deployment_manifest(manifest_path, github_root=github_root)
    assert verify_report["state"] == "deployed"
    assert verify_report["lock_identity_digest"] == digest
    assert verify_report["inventory_identity_digest"] == digest
    assert verify_report["expected_repo_identity_digest"] == digest

    # CLI surface, too.
    rc, cli_report = _run_json(
        [
            "verify",
            "--manifest", str(manifest_path),
            "--github-root", str(github_root),
        ],
        capsys,
    )
    assert rc == 0
    assert cli_report["state"] == "deployed"


def test_verify_rejects_lock_inventory_digest_mismatch(tmp_path: Path, capsys) -> None:
    """A sealed bundle that attests to a DIFFERENT lock/clone set than the
    manifest's own recorded commits must be rejected — the exact Codex
    #483 concern: a list of commit hashes can be edited without proving it
    was the lock and clone set actually observed on the production host."""
    lock, _ = make_umbrella(tmp_path)
    github_root = tmp_path / "siblings"
    wrong_digest = "0" * 64
    _seal_evidence_bundle(
        github_root,
        lock_identity_digest=wrong_digest,
        inventory_identity_digest=wrong_digest,
    )

    rc, report = _run_json(
        _capture_argv(
            lock, tmp_path / "deploy-root", "--write",
            "--evidence-ref", _VERIFY_EVIDENCE_REF,
            "--artifact-store-path", "store",
        ),
        capsys,
    )
    assert rc == 0
    manifest_path = tmp_path / "committed-manifest.json"
    manifest_path.write_text(json.dumps(report["manifest"]), encoding="utf-8")

    with pytest.raises(DeployPinError, match="identity digest mismatch"):
        verify_deployment_manifest(manifest_path, github_root=github_root)

    rc = deploy_pin_main(
        ["verify", "--manifest", str(manifest_path), "--github-root", str(github_root)]
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "identity digest mismatch" in err
    assert "source-lock" in err
    assert "materialized-runtime-inventory" in err


def test_verify_rejects_null_evidence_ref(tmp_path: Path, capsys) -> None:
    lock, _ = make_umbrella(tmp_path)
    state_root = tmp_path / "deploy-root"
    rc, report = _run_json(_capture_argv(lock, state_root, "--write"), capsys)
    assert rc == 0
    assert report["manifest"]["deployment"]["state"] == "captured"
    manifest_path = state_root / "deployment-manifest.json"
    with pytest.raises(DeployPinError, match="evidence_ref is null"):
        verify_deployment_manifest(manifest_path, github_root=tmp_path / "siblings")


def test_verify_rejects_missing_artifact_store_sibling(tmp_path: Path, capsys) -> None:
    lock, _ = make_umbrella(tmp_path)
    rc, report = _run_json(
        _capture_argv(
            lock, tmp_path / "deploy-root", "--write",
            "--evidence-ref", _VERIFY_EVIDENCE_REF,
            "--artifact-store-path", "store",
        ),
        capsys,
    )
    assert rc == 0
    manifest_path = tmp_path / "committed-manifest.json"
    manifest_path.write_text(json.dumps(report["manifest"]), encoding="utf-8")

    with pytest.raises(DeployPinError, match="sibling checkout not found"):
        verify_deployment_manifest(manifest_path, github_root=tmp_path / "no-such-siblings")


def test_verify_rejects_store_manifest_content_tamper(tmp_path: Path, capsys) -> None:
    """The sealed bundle's own bytes must match the store's
    STORE-MANIFEST.json content hash — catches tampering with the bundle
    file itself, distinct from the identity-digest cross-check."""
    lock, _ = make_umbrella(tmp_path)
    digest = repo_identity_digest(read_lock_subrepo_identity(lock))
    github_root = tmp_path / "siblings"
    _seal_evidence_bundle(
        github_root, lock_identity_digest=digest, inventory_identity_digest=digest
    )

    rc, report = _run_json(
        _capture_argv(
            lock, tmp_path / "deploy-root", "--write",
            "--evidence-ref", _VERIFY_EVIDENCE_REF,
            "--artifact-store-path", "store",
        ),
        capsys,
    )
    assert rc == 0
    manifest_path = tmp_path / "committed-manifest.json"
    manifest_path.write_text(json.dumps(report["manifest"]), encoding="utf-8")

    # tamper the bundle bytes AFTER STORE-MANIFEST.json was hashed
    bundle_path = github_root / "renquant-artifacts" / "store" / "experiments" / "verify-test" / "RUN-LOCK.json"
    bundle_path.write_text(
        json.dumps({"lock_identity_digest": "x", "inventory_identity_digest": "x"}),
        encoding="utf-8",
    )

    with pytest.raises(DeployPinError, match="possible tamper"):
        resolve_evidence_bundle_path(report["manifest"], github_root=github_root)
