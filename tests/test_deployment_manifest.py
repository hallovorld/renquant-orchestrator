"""R-PIN Stage 1 — deployment-manifest schema v1 + neutral state root.

Design: doc/design/2026-07-11-deployment-pin-authority-migration.md
(§5.1 schema, §5.2 state root, §7.1 transition predicates, §9 Stage 1
deliverable 1 tests: good/malformed schema, generation rules, portability,
inventory verification, forward-only generation record).
"""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator.deployment_manifest import (
    GENERATION_OK,
    GENERATION_STALE_OR_REPLAYED,
    GENERATION_TORN_APPLY,
    DeploymentManifestError,
    build_runtime_inventory,
    classify_generation,
    deploy_state_root,
    deployment_manifest_problems,
    emergency_apply_violations,
    ensure_state_root_layout,
    load_deployment_manifest,
    load_runtime_inventory,
    manifest_content_sha256,
    normal_apply_violations,
    portability_problems,
    read_expected_generation,
    record_expected_generation,
    steady_state_violations,
    validate_deployment_manifest,
    verify_runtime_inventory,
    write_json_canonical,
)

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
DIGEST_1 = "1" * 64
DIGEST_2 = "2" * 64


def make_manifest(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "kind": "deployment-manifest",
        "generation": 1,
        "generated_at": "2026-07-11T00:00:00Z",
        "repos": {
            "renquant-strategy-104": {
                "remote": "https://github.com/hallovorld/renquant-strategy-104",
                "branch": "main",
                "commit": SHA_A,
                "role": "active 104 strategy config",
                "status": "bootstrapped",
            },
            "renquant-artifacts": {
                "remote": "https://github.com/hallovorld/renquant-artifacts",
                "branch": "main",
                "commit": SHA_B,
                "role": "model artifacts + registry",
                "status": "bootstrapped",
            },
        },
        "artifact_store": {"repo": "renquant-artifacts", "path": ""},
        "deployment": {
            "deployed_at": "2026-07-11T00:00:00Z",
            "deployed_by": "operator",
            "verify": {
                "profile": "readonly-e2e",
                "args": {"min_admits": 1},
                "exit": 0,
                "evidence_ref": "store://records/readonly-e2e-20260711",
                "evidence_repo_commit": SHA_C,
            },
            "state": "deployed",
            "supersedes_sha256": None,
        },
    }
    payload.update(overrides)
    return payload


def problems_of(payload) -> list[str]:
    return deployment_manifest_problems(payload)


# --- schema: good ------------------------------------------------------------------


def test_valid_manifest_has_no_problems() -> None:
    assert problems_of(make_manifest()) == []


def test_load_valid_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "deployment-manifest.json"
    payload = make_manifest()
    write_json_canonical(path, payload)
    loaded = load_deployment_manifest(path)
    assert loaded == payload
    assert manifest_content_sha256(loaded) == manifest_content_sha256(payload)


def test_captured_state_permits_null_evidence_ref() -> None:
    payload = make_manifest()
    payload["deployment"]["state"] = "captured"
    payload["deployment"]["verify"]["evidence_ref"] = None
    payload["deployment"]["verify"]["evidence_repo_commit"] = None
    assert problems_of(payload) == []


# --- schema: malformed --------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda p: p.update(schema_version=2), "schema_version"),
        (lambda p: p.update(schema_version=True), "schema_version"),
        (lambda p: p.update(kind="run-manifest"), "kind"),
        (lambda p: p.update(generation=0), "generation"),
        (lambda p: p.update(generation=-3), "generation"),
        (lambda p: p.update(generation="7"), "generation"),
        (lambda p: p.update(generation=True), "generation"),
        (lambda p: p.update(generated_at="not-a-time"), "generated_at"),
        (lambda p: p.update(repos={}), "repos"),
        (lambda p: p.update(repos="nope"), "repos"),
        (lambda p: p.update(surprise=1), "unknown top-level"),
        (lambda p: p.pop("artifact_store"), "artifact_store"),
        (lambda p: p.pop("deployment"), "deployment"),
    ],
)
def test_malformed_top_level_rejected(mutate, needle) -> None:
    payload = make_manifest()
    mutate(payload)
    assert any(needle in problem for problem in problems_of(payload)), (
        problems_of(payload)
    )


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda r: r.pop("remote"), "remote"),
        (lambda r: r.pop("branch"), "branch"),
        (lambda r: r.pop("commit"), "commit"),
        (lambda r: r.pop("role"), "role"),
        (lambda r: r.pop("status"), "status"),
        (lambda r: r.update(commit="a" * 12), "40-hex"),
        (lambda r: r.update(commit="A" * 40), "40-hex"),
        (lambda r: r.update(commit="z" * 40), "40-hex"),
    ],
)
def test_malformed_repo_entry_rejected(mutate, needle) -> None:
    payload = make_manifest()
    mutate(payload["repos"]["renquant-strategy-104"])
    assert any(needle in problem for problem in problems_of(payload)), (
        problems_of(payload)
    )


def test_validate_raises_with_named_source(tmp_path: Path) -> None:
    with pytest.raises(DeploymentManifestError, match="schema validation failed"):
        validate_deployment_manifest(make_manifest(generation=0))
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DeploymentManifestError, match="unreadable"):
        load_deployment_manifest(path)


# --- schema: PORTABILITY (§5.1 — repo identity only, no host paths) -----------------


def test_repo_entry_smuggling_host_fields_rejected() -> None:
    for smuggled in ({"local_path": "/Users/x/repo"}, {"test_command": "make test"},
                     {"path": "/opt/x"}):
        payload = make_manifest()
        payload["repos"]["renquant-strategy-104"].update(smuggled)
        joined = "; ".join(problems_of(payload))
        assert "non-identity key(s)" in joined, joined


def test_absolute_path_value_anywhere_rejected() -> None:
    payload = make_manifest()
    payload["repos"]["renquant-strategy-104"]["role"] = "/Users/renhao/git/x"
    assert any("host path" in problem for problem in problems_of(payload))


def test_portability_sweep_flags_nested_host_paths() -> None:
    assert portability_problems({"a": [{"b": "/tmp/x"}]})
    assert portability_problems({"a": "~/state"})
    assert portability_problems({"a": "C:\\state"})
    assert portability_problems({"a": "https://github.com/x", "b": 3}) == []


# --- schema: artifact_store ---------------------------------------------------------


@pytest.mark.parametrize(
    "store, needle",
    [
        ("artifacts/", "bare path is not a pinned owner"),
        ({}, "bare path is not a pinned owner"),
        ({"repo": "unknown-repo", "path": ""}, "not a manifest repo"),
        ({"repo": "renquant-artifacts", "path": "/abs"}, "relative subdir"),
        ({"repo": "renquant-artifacts", "path": "../escape"}, "relative subdir"),
        ({"repo": "renquant-artifacts", "path": "", "cmd": "sh"}, "unknown key"),
    ],
)
def test_artifact_store_rejections(store, needle) -> None:
    payload = make_manifest(artifact_store=store)
    joined = "; ".join(problems_of(payload))
    assert needle in joined, joined


# --- schema: deployment.verify (allowlisted profile + structured args) --------------


def test_unknown_verify_profile_rejected() -> None:
    payload = make_manifest()
    payload["deployment"]["verify"]["profile"] = "bash -c"
    joined = "; ".join(problems_of(payload))
    assert "not in the code-owned allowlist" in joined


def test_verify_args_validated_per_profile() -> None:
    payload = make_manifest()
    payload["deployment"]["verify"]["args"] = {"min_admits": 1, "cmd": "rm -rf"}
    assert any("unknown key(s)" in p for p in problems_of(payload))
    payload["deployment"]["verify"]["args"] = {"min_admits": -1}
    assert any("min_admits" in p for p in problems_of(payload))
    payload["deployment"]["verify"]["args"] = {"min_admits": True}
    assert any("min_admits" in p for p in problems_of(payload))
    payload["deployment"]["verify"]["args"] = "not-structured"
    assert any("structured" in p for p in problems_of(payload))


def test_verify_unknown_keys_rejected() -> None:
    payload = make_manifest()
    payload["deployment"]["verify"]["command"] = "echo pwned"
    assert any("unknown key(s)" in p for p in problems_of(payload))


# --- schema: evidence_ref (store:// form, never a local path) ------------------------


@pytest.mark.parametrize(
    "ref",
    [
        "/var/log/verify.log",
        "file:///tmp/x",
        "store://",
        "store:///abs",
        "store://../escape",
        12,
    ],
)
def test_bad_evidence_ref_rejected(ref) -> None:
    payload = make_manifest()
    payload["deployment"]["verify"]["evidence_ref"] = ref
    assert any("evidence_ref" in p for p in problems_of(payload))


def test_null_evidence_ref_rejected_for_deployed_state() -> None:
    payload = make_manifest()
    payload["deployment"]["verify"]["evidence_ref"] = None
    joined = "; ".join(problems_of(payload))
    assert "required for state 'deployed'" in joined


# --- schema: evidence_repo_commit (Codex #483 checkout-identity follow-up) ----------


def test_evidence_repo_commit_required_when_evidence_ref_sealed() -> None:
    """A sealed evidence_ref without the sibling-checkout revision it was
    resolved from is exactly the checkout-identity gap Codex flagged —
    schema-invalid, not just a verify-time concern."""
    payload = make_manifest()
    payload["deployment"]["verify"]["evidence_repo_commit"] = None
    joined = "; ".join(problems_of(payload))
    assert "evidence_repo_commit must be a full 40-hex" in joined


@pytest.mark.parametrize(
    "bad_commit",
    ["", "not-a-sha", "a" * 39, "A" * 40, "z" * 40, 12, ["a" * 40]],
)
def test_evidence_repo_commit_must_be_full_lowercase_sha(bad_commit) -> None:
    payload = make_manifest()
    payload["deployment"]["verify"]["evidence_repo_commit"] = bad_commit
    joined = "; ".join(problems_of(payload))
    assert "evidence_repo_commit must be a full 40-hex" in joined


def test_evidence_repo_commit_forbidden_when_evidence_ref_null() -> None:
    """The pre-seal 'captured' state has nothing to bind yet: a non-null
    evidence_repo_commit without a sealed evidence_ref is rejected too —
    the two fields may never travel one without the other."""
    payload = make_manifest()
    payload["deployment"]["state"] = "captured"
    payload["deployment"]["verify"]["evidence_ref"] = None
    payload["deployment"]["verify"]["evidence_repo_commit"] = SHA_C
    joined = "; ".join(problems_of(payload))
    assert "evidence_repo_commit must be null when evidence_ref is null" in joined


def test_evidence_repo_commit_may_differ_from_pinned_artifacts_commit() -> None:
    """The exact pre-#21-pin-vs-post-#21-evidence case: the pinned
    renquant-artifacts commit (repos[...].commit) and the sibling-checkout
    revision the evidence was sealed from (evidence_repo_commit) are
    INDEPENDENT fields — an evidence bundle sealed by a later PR than the
    pinned commit is legitimate and must remain schema-valid."""
    payload = make_manifest()
    assert payload["repos"]["renquant-artifacts"]["commit"] == SHA_B
    payload["deployment"]["verify"]["evidence_repo_commit"] = SHA_C
    assert SHA_C != SHA_B
    assert problems_of(payload) == []


# --- schema: generation chaining (supersedes_sha256) ---------------------------------


def test_generation_one_may_have_null_supersedes() -> None:
    assert problems_of(make_manifest()) == []


def test_generation_beyond_one_requires_supersedes() -> None:
    payload = make_manifest(generation=2)
    joined = "; ".join(problems_of(payload))
    assert "supersedes_sha256 may be null only for generation 1" in joined
    payload["deployment"]["supersedes_sha256"] = DIGEST_1
    assert problems_of(payload) == []


def test_non_hex_supersedes_rejected() -> None:
    payload = make_manifest(generation=2)
    payload["deployment"]["supersedes_sha256"] = "not-a-sha"
    assert any("64-hex" in p for p in problems_of(payload))


# --- neutral state root (§5.2) --------------------------------------------------------


def test_state_root_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RENQUANT_DEPLOY_STATE_ROOT", str(tmp_path / "root"))
    assert deploy_state_root() == tmp_path / "root"
    assert deploy_state_root(tmp_path / "explicit") == tmp_path / "explicit"
    monkeypatch.delenv("RENQUANT_DEPLOY_STATE_ROOT")
    assert deploy_state_root() == Path("~/.renquant/deploy").expanduser()


def test_ensure_state_root_layout_creates_receipts(tmp_path: Path) -> None:
    root = tmp_path / "deploy"
    paths = ensure_state_root_layout(root)
    assert (root / "receipts").is_dir()
    assert paths["manifest"].name == "deployment-manifest.json"
    assert paths["inventory"].name == "runtime-inventory.json"
    assert paths["expected_generation"].name == "expected-generation.json"


# --- runtime inventory (§5.2: verified HEAD==manifest commit at read) -----------------


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc.stdout.strip()


def _make_repo(path: Path) -> str:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    (path / "f.txt").write_text("x", encoding="utf-8")
    _git(path, "add", "f.txt")
    _git(path, "commit", "-qm", "c1")
    return _git(path, "rev-parse", "HEAD")


def _manifest_and_inventory(tmp_path: Path) -> tuple[dict, dict]:
    commits = {}
    paths = {}
    for name in ("renquant-strategy-104", "renquant-artifacts"):
        repo = tmp_path / "clones" / name
        commits[name] = _make_repo(repo)
        paths[name] = repo
    manifest = make_manifest()
    for name, commit in commits.items():
        manifest["repos"][name]["commit"] = commit
    inventory = build_runtime_inventory(paths)
    return manifest, inventory


def test_inventory_verifies_head_matches_manifest(tmp_path: Path) -> None:
    manifest, inventory = _manifest_and_inventory(tmp_path)
    resolved = verify_runtime_inventory(manifest, inventory)
    assert resolved == {
        name: entry["commit"] for name, entry in manifest["repos"].items()
    }


def test_inventory_head_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest, inventory = _manifest_and_inventory(tmp_path)
    repo = Path(inventory["repos"]["renquant-artifacts"]["path"])
    (repo / "f.txt").write_text("y", encoding="utf-8")
    _git(repo, "commit", "-aqm", "drift")
    with pytest.raises(DeploymentManifestError, match="checkout HEAD"):
        verify_runtime_inventory(manifest, inventory)


def test_inventory_missing_repo_fails_closed(tmp_path: Path) -> None:
    manifest, inventory = _manifest_and_inventory(tmp_path)
    del inventory["repos"]["renquant-artifacts"]
    with pytest.raises(DeploymentManifestError, match="missing from the runtime"):
        verify_runtime_inventory(manifest, inventory)


def test_inventory_schema_rejects_relative_paths(tmp_path: Path) -> None:
    inventory = build_runtime_inventory({"x": tmp_path / "x"})
    inventory["repos"]["x"]["path"] = "relative/path"
    path = tmp_path / "runtime-inventory.json"
    write_json_canonical(path, inventory)
    with pytest.raises(DeploymentManifestError, match="absolute host path"):
        load_runtime_inventory(path)


def test_inventory_read_does_not_require_clean_tree(tmp_path: Path) -> None:
    """§5.2 read rule is HEAD==commit; a dirty clone is a pin-guard concern,
    not an inventory-read failure."""
    manifest, inventory = _manifest_and_inventory(tmp_path)
    repo = Path(inventory["repos"]["renquant-artifacts"]["path"])
    (repo / "scratch.txt").write_text("dirty", encoding="utf-8")
    resolved = verify_runtime_inventory(manifest, inventory)
    assert set(resolved) == set(manifest["repos"])


# --- forward-only expected-generation record (§5.2) -----------------------------------


def test_expected_generation_record_and_read(tmp_path: Path) -> None:
    root = tmp_path / "deploy"
    ensure_state_root_layout(root)
    assert read_expected_generation(root) is None
    record_expected_generation(root, generation=1, manifest_sha256=DIGEST_1)
    record = read_expected_generation(root)
    assert record["generation"] == 1
    assert record["manifest_sha256"] == DIGEST_1


def test_expected_generation_refuses_decrease(tmp_path: Path) -> None:
    root = tmp_path / "deploy"
    ensure_state_root_layout(root)
    record_expected_generation(root, generation=5, manifest_sha256=DIGEST_1)
    with pytest.raises(DeploymentManifestError, match="FORWARD-ONLY"):
        record_expected_generation(root, generation=4, manifest_sha256=DIGEST_2)
    # the record is untouched after the refused write
    assert read_expected_generation(root)["generation"] == 5


def test_expected_generation_refuses_same_epoch_rewrite(tmp_path: Path) -> None:
    root = tmp_path / "deploy"
    ensure_state_root_layout(root)
    record_expected_generation(root, generation=3, manifest_sha256=DIGEST_1)
    with pytest.raises(DeploymentManifestError, match="never reused"):
        record_expected_generation(root, generation=3, manifest_sha256=DIGEST_2)
    # identical re-record is an idempotent no-op
    record_expected_generation(root, generation=3, manifest_sha256=DIGEST_1)
    assert read_expected_generation(root)["generation"] == 3


def test_expected_generation_advances(tmp_path: Path) -> None:
    root = tmp_path / "deploy"
    ensure_state_root_layout(root)
    record_expected_generation(root, generation=1, manifest_sha256=DIGEST_1)
    record_expected_generation(root, generation=2, manifest_sha256=DIGEST_2)
    assert read_expected_generation(root)["generation"] == 2


def test_malformed_expected_generation_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "deploy"
    ensure_state_root_layout(root)
    (root / "expected-generation.json").write_text(
        json.dumps({"kind": "expected-generation", "generation": "x"}),
        encoding="utf-8",
    )
    with pytest.raises(DeploymentManifestError, match="malformed"):
        read_expected_generation(root)


def test_classify_generation_torn_and_stale() -> None:
    assert classify_generation(4, 4) == GENERATION_OK
    # less than the durable record = restored old manifest pair (replay)
    assert classify_generation(3, 4) == GENERATION_STALE_OR_REPLAYED
    # GREATER than the durable record = torn apply (crash between writes)
    assert classify_generation(5, 4) == GENERATION_TORN_APPLY


# --- §7.1 transition predicates --------------------------------------------------------


def test_steady_state_predicate() -> None:
    assert steady_state_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=7, main_sha256=DIGEST_1,
    ) == []
    assert steady_state_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=8, main_sha256=DIGEST_1,
    )
    assert steady_state_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=7, main_sha256=DIGEST_2,
    )


def test_normal_apply_predicate_predecessor_exactness() -> None:
    # record-first: origin/main exactly ONE ahead, superseding the machine
    assert normal_apply_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=8, main_supersedes_sha256=DIGEST_1,
    ) == []
    # generation skip — someone recorded past this machine
    skip = normal_apply_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=9, main_supersedes_sha256=DIGEST_1,
    )
    assert any("generation skip" in v for v in skip)
    # supersedes must name the machine's actual content
    mismatch = normal_apply_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=8, main_supersedes_sha256=DIGEST_2,
    )
    assert any("predecessor mismatch" in v for v in mismatch)


def test_emergency_apply_refuses_forked_epoch() -> None:
    # origin/main ahead of the machine ⇒ refuse (the §7.1 rejection drill case)
    ahead = emergency_apply_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=8, main_sha256=DIGEST_2,
        candidate_generation=8, candidate_supersedes_sha256=DIGEST_1,
    )
    assert any("forked-epoch guard" in v for v in ahead)
    # steady state + valid candidate ⇒ permitted
    assert emergency_apply_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=7, main_sha256=DIGEST_1,
        candidate_generation=8, candidate_supersedes_sha256=DIGEST_1,
    ) == []
    # candidate must extend the shared epoch by exactly one
    bad_candidate = emergency_apply_violations(
        local_generation=7, local_sha256=DIGEST_1,
        main_generation=7, main_sha256=DIGEST_1,
        candidate_generation=10, candidate_supersedes_sha256=DIGEST_1,
    )
    assert any("exactly machine generation + 1" in v for v in bad_candidate)


# --- canonical content ------------------------------------------------------------------


def test_manifest_sha256_is_content_stable() -> None:
    payload = make_manifest()
    shuffled = copy.deepcopy(payload)
    # key order must not matter (canonical form sorts keys)
    shuffled["repos"] = dict(reversed(list(shuffled["repos"].items())))
    assert manifest_content_sha256(payload) == manifest_content_sha256(shuffled)
    changed = copy.deepcopy(payload)
    changed["generation"] = 2
    assert manifest_content_sha256(payload) != manifest_content_sha256(changed)
