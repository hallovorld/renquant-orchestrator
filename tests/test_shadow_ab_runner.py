"""Tests for the D6-§2a two-arm shadow runner (P-2).

The pipeline invocation boundary (CommandRunner) and every external authority
(fingerprint, pins, orchestrator commit, notifier) are injected so these tests
run hermetically — no subprocess, no broker, no strategy venv.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator import shadow_ab_runner as sab
from renquant_orchestrator.native_live_context import (
    DecisionSnapshotMismatchError,
    build_native_live_context,
    canonical_json_sha256,
    compute_decision_snapshot_digest,
    decision_snapshot_identity,
)
from renquant_orchestrator.shadow_ab_runner import (
    EXIT_PRECHECK_ABORT,
    EXIT_SESSION_INVALIDATED,
    EXIT_VALID,
    EXIT_VOID,
    EXPERIMENT_PIN_REPOS,
    FROZEN_TAG_A,
    FROZEN_TAG_B,
    FROZEN_TREATMENT_KEY,
    LEGACY_SHADOW_TAG,
    PAIRED_WORLD_VERIFICATION_STAGES,
    SEALED_ACCOUNT_FILENAME,
    SEALED_DIRNAME,
    SEALED_MARKET_FILENAME,
    SHADOW_PREFLIGHT_ENV,
    SPEC_2A_ARM_FIELDS,
    VOID_MARKER,
    ArmSpec,
    ShadowABContractError,
    assert_preflight_symmetry,
    build_arm_plan,
    default_experiment_strategy_dir,
    load_run_manifest,
    resolve_arm_fingerprints,
    run_shadow_ab_session,
    seal_snapshot,
    treatment_key_violations,
    validate_ntfy_topic,
    validate_output_root,
    validate_tags,
    verify_decision_snapshot,
)


PINS = {
    "renquant-strategy-104": "aaa1",
    "renquant-pipeline": "bbb2",
    "renquant-execution": "ccc3",
}
ORCH_COMMIT = "feedface"


def _fake_fingerprint(path: str | Path) -> str:
    return "sha256:fp-" + Path(path).read_text(encoding="utf-8").strip()


class RecordingRunner:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.fail_on = fail_on

    def __call__(self, command, env) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(command), dict(env)))
        rc = 0
        if self.fail_on and any(self.fail_on in token for token in command):
            rc = 1
        return subprocess.CompletedProcess(list(command), rc, stdout="", stderr="")


class MutatingRunner(RecordingRunner):
    """Fires ``side_effect`` once, right after the first command containing
    ``trigger`` executes — simulates a producer/interloper mutating a session
    input file mid-run, between the runner's verification points."""

    def __init__(self, *, trigger: str, side_effect) -> None:
        super().__init__()
        self.trigger = trigger
        self.side_effect = side_effect
        self.fired = False

    def __call__(self, command, env) -> subprocess.CompletedProcess[str]:
        result = super().__call__(command, env)
        if not self.fired and any(self.trigger in token for token in command):
            self.fired = True
            self.side_effect()
        return result


def _write_world(tmp_path: Path, *, model_b: str | None = None) -> dict[str, Path]:
    """Build a two-config world; arm B may point at a different model."""
    model_a = tmp_path / "model_a.pt"
    model_a.write_text("model-1", encoding="utf-8")
    model_b_path = model_a
    if model_b is not None:
        model_b_path = tmp_path / "model_b.pt"
        model_b_path.write_text(model_b, encoding="utf-8")
    calibrator = tmp_path / "calibrator.json"
    calibrator.write_text("cal-1", encoding="utf-8")
    manifest = tmp_path / "wf_manifest.json"
    manifest.write_text(json.dumps({"cuts": [1, 2, 3]}), encoding="utf-8")
    market = tmp_path / "market_snapshot.json"
    market.write_text(json.dumps({"as_of": "2026-07-10"}), encoding="utf-8")
    account = tmp_path / "account_snapshot.json"
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")

    def _config(path: Path, model_path: Path, floor_mult: float) -> Path:
        path.write_text(json.dumps({
            "ranking": {"panel_scoring": {
                "artifact_path": str(model_path),
                "buy_floor_std_mult": floor_mult,
                "global_calibration": {
                    "enabled": True,
                    "artifact_path": str(calibrator),
                },
            }},
        }), encoding="utf-8")
        return path

    return {
        "config_a": _config(tmp_path / "strategy_config.shadow.json", model_a, 0.5),
        "config_b": _config(tmp_path / "strategy_config.shadow_b.json", model_b_path, 1.0),
        "manifest": manifest,
        "market": market,
        "account": account,
        "model_a": model_a,
        "model_b": model_b_path,
        "calibrator": calibrator,
    }


def _run(world: dict[str, Path], out_root: Path, **overrides):
    kwargs = dict(
        config_a=world["config_a"],
        config_b=world["config_b"],
        data_manifest=world["manifest"],
        output_root=out_root,
        market_snapshot_json=world["market"],
        account_snapshot_json=world["account"],
        session_date="2026-07-10",
        repo_root=out_root.parent / "umbrella",
        strategy_dir=out_root.parent / "umbrella" / "backtesting" / "renquant_104",
        command_runner=RecordingRunner(),
        fingerprint_from_path=_fake_fingerprint,
        pins_resolver=lambda: dict(PINS),
        orchestrator_commit_resolver=lambda: ORCH_COMMIT,
        notifier=lambda title, body: None,
    )
    kwargs.update(overrides)
    return run_shadow_ab_session(**kwargs)


def _git_pinned_repos(tmp_path: Path) -> tuple[Path, dict[str, dict[str, str]]]:
    """Real tiny git checkouts + a run manifest capturing their HEADs."""
    import subprocess as sp

    repos: dict[str, dict[str, str]] = {}
    for name in EXPERIMENT_PIN_REPOS:
        rd = tmp_path / "pins" / name
        (rd / "configs").mkdir(parents=True)
        (rd / "configs" / "marker.txt").write_text(name, encoding="utf-8")
        sp.run(["git", "init", "-q", str(rd)], check=True)
        sp.run(["git", "-C", str(rd), "add", "."], check=True)
        sp.run(
            ["git", "-C", str(rd), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-qm", "init"],
            check=True,
        )
        head = sp.run(
            ["git", "-C", str(rd), "rev-parse", "HEAD"],
            check=True, text=True, stdout=sp.PIPE,
        ).stdout.strip()
        repos[name] = {"path": str(rd), "commit": head}
    manifest = tmp_path / "run_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "repos": repos,
        "data_revision": "ohlcv-refresh-2026-07-10",
    }), encoding="utf-8")
    return manifest, repos


# --- bundle completeness (§2a manifest list) -----------------------------------


def test_valid_session_writes_complete_bundle(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    payload = _run(world, out_root)

    assert payload["exit_code"] == EXIT_VALID
    assert payload["status"] == "valid"
    bundle_path = Path(payload["bundle_path"])
    assert bundle_path.exists()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["protocol"] == "D6-2a"

    for label, tag in (("a", FROZEN_TAG_A), ("b", FROZEN_TAG_B)):
        arm = bundle["arms"][label]
        # every §2a manifest field present and populated, per arm
        for field in SPEC_2A_ARM_FIELDS:
            assert field in arm, f"arm {label} missing §2a field {field}"
            assert arm[field], f"arm {label} has empty §2a field {field}"
        assert arm["broker_state_tag"] == tag
        assert arm["model_content_sha256"] == "sha256:fp-model-1"
        assert arm["calibrator_content_sha256"] == "sha256:fp-cal-1"
        assert arm["orchestrator_commit"] == ORCH_COMMIT
        assert set(arm["subrepo_pins"]) == set(EXPERIMENT_PIN_REPOS)
        assert arm["data_manifest_sha256"].startswith("sha256:")
        assert arm["config_sha256"].startswith("sha256:")
        assert arm["invalidated"] is False
        assert arm["completed"] is True
    # arms differ in config hash (one-key treatment delta) but share the world
    assert bundle["arms"]["a"]["config_sha256"] != bundle["arms"]["b"]["config_sha256"]
    # freeze written on first session
    freeze = json.loads((out_root / "shadow_ab_freeze.json").read_text(encoding="utf-8"))
    assert freeze["config_sha256_a"] == bundle["arms"]["a"]["config_sha256"]
    assert freeze["config_sha256_b"] == bundle["arms"]["b"]["config_sha256"]
    counters = bundle["counters"]
    assert counters["attempted_pairs"] == 1
    assert counters["excluded_pairs"] == 0
    # the decision snapshot is sealed and dual-hashed (r8): both immutable
    # copies exist in the run bundle, both content hashes + the identity
    # components are recorded, and every consumption-point verification ran
    snapshot = bundle["decision_snapshot"]
    assert snapshot["sealed"] is True
    sealed_market = Path(snapshot["sealed_market_snapshot"])
    sealed_account = Path(snapshot["sealed_account_snapshot"])
    assert sealed_market.exists() and sealed_account.exists()
    assert snapshot["market_snapshot_sha256"].startswith("sha256:")
    assert snapshot["account_snapshot_sha256"].startswith("sha256:")
    assert snapshot["as_of"] == "2026-07-10"
    assert snapshot["starting_state_convention"]
    assert snapshot["digest"] == bundle["arms"]["a"]["decision_snapshot_digest"]
    stages = [v["stage"] for v in bundle["paired_world_verifications"]]
    assert stages == list(PAIRED_WORLD_VERIFICATION_STAGES)
    assert all(v["ok"] for v in bundle["paired_world_verifications"])


def test_arms_run_sequentially_and_consume_same_inputs(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    runner = RecordingRunner()
    payload = _run(world, tmp_path / "sessions", command_runner=runner)
    assert payload["exit_code"] == EXIT_VALID

    commands = [call[0] for call in runner.calls]
    # arm A's chain completes before any arm B command (sequential, never concurrent)
    a_indexes = [i for i, c in enumerate(commands) if any(FROZEN_TAG_A in t for t in c)]
    b_indexes = [i for i, c in enumerate(commands) if any(FROZEN_TAG_B in t for t in c)]
    assert a_indexes and b_indexes
    assert max(a_indexes) < min(b_indexes)
    # both arms consume the SAME sealed immutable copies from the run
    # bundle — NEVER the caller-supplied paths (r8)
    sealed_dir = tmp_path / "sessions" / "2026-07-10" / SEALED_DIRNAME
    context_cmds = [c for c in commands if "native-live-context" in c]
    assert len(context_cmds) == 2
    for cmd in context_cmds:
        assert str(sealed_dir / SEALED_MARKET_FILENAME) in cmd
        assert str(sealed_dir / SEALED_ACCOUNT_FILENAME) in cmd
    for cmd in commands:
        assert str(world["market"]) not in cmd
        assert str(world["account"]) not in cmd


# --- same-world rule -------------------------------------------------------------


def test_same_world_abort_when_model_sha_differs(tmp_path: Path) -> None:
    world = _write_world(tmp_path, model_b="model-2")
    runner = RecordingRunner()
    payload = _run(world, tmp_path / "sessions", command_runner=runner)

    assert payload["exit_code"] == EXIT_PRECHECK_ABORT
    assert payload["status"] == "invalidated"
    assert any("same_world_violation" in r for r in payload["reasons"])
    # neither arm ran
    assert runner.calls == []
    for label in ("a", "b"):
        assert payload["arms"][label]["invalidated"] is True
    # no freeze is written for an aborted first session
    assert not (tmp_path / "sessions" / "shadow_ab_freeze.json").exists()
    # exclusion is tracked against attempts
    assert payload["counters"]["attempted_pairs"] == 1
    assert payload["counters"]["excluded_pairs"] == 1


# --- either-arm failure => both arms invalidated -----------------------------------


def test_either_arm_failure_invalidates_both_arms(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    # fail arm B's inference step only; arm A completes cleanly
    runner = RecordingRunner(fail_on=f"arm_{FROZEN_TAG_B}/native_inference.json")
    payload = _run(world, tmp_path / "sessions", command_runner=runner)

    assert payload["exit_code"] == EXIT_SESSION_INVALIDATED
    assert payload["status"] == "invalidated"
    assert payload["arms"]["a"]["completed"] is True
    assert payload["arms"]["b"]["completed"] is False
    # paired inclusion: the CLEAN arm is excluded too
    for label in ("a", "b"):
        arm = payload["arms"][label]
        assert arm["invalidated"] is True
        assert any("paired_invalidation" in r for r in arm["invalidation_reasons"])
    assert payload["counters"]["excluded_pairs"] == 1


# --- config-hash drift => VOID ------------------------------------------------------


def test_config_hash_drift_voids_session(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    first = _run(world, out_root)
    assert first["exit_code"] == EXIT_VALID

    # a later config PR flips a key in arm B's config: drift against the freeze
    config_b = json.loads(world["config_b"].read_text(encoding="utf-8"))
    config_b["ranking"]["panel_scoring"]["buy_floor_std_mult"] = 2.0
    world["config_b"].write_text(json.dumps(config_b), encoding="utf-8")

    runner = RecordingRunner()
    second = _run(world, out_root, command_runner=runner, session_date="2026-07-13")
    assert second["exit_code"] == EXIT_VOID
    assert second["status"] == "void"
    assert second["void"] is True
    assert second["void_marker"] == VOID_MARKER
    assert any("config_hash_drift" in r for r in second["reasons"])
    # a VOID session never invokes an arm
    assert runner.calls == []


def test_frozen_world_mismatch_invalidates_but_does_not_void(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    first = _run(world, out_root)
    assert first["exit_code"] == EXIT_VALID

    # the model artifact changes under BOTH arms (same-world still holds,
    # but the frozen-at-start fingerprint no longer matches)
    world["model_a"].write_text("model-9", encoding="utf-8")

    runner = RecordingRunner()
    second = _run(world, out_root, command_runner=runner, session_date="2026-07-13")
    assert second["exit_code"] == EXIT_PRECHECK_ABORT
    assert second["status"] == "invalidated"
    assert second["void"] is False
    assert any("frozen_fingerprint_mismatch" in r for r in second["reasons"])
    assert runner.calls == []


# --- preflight symmetry ---------------------------------------------------------------


def test_arm_invocations_are_symmetric_modulo_config_and_tag(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    runner = RecordingRunner()
    payload = _run(world, tmp_path / "sessions", command_runner=runner)
    assert payload["exit_code"] == EXIT_VALID

    # every invocation (both arms + shared) received the IDENTICAL env,
    # including the shadow preflight relaxation
    envs = [env for _, env in runner.calls]
    assert envs, "no invocations recorded"
    for env in envs:
        assert env == envs[0]
        for key, value in SHADOW_PREFLIGHT_ENV.items():
            assert env[key] == value

    # canonicalized command plans are identical modulo (config, tag, arm dir)
    plan_a = payload["arms"]["a"]["planned_commands"]
    plan_b = payload["arms"]["b"]["planned_commands"]

    def canonical(plan, tag, config):
        return [
            [
                t.replace(f"arm_{tag}", "<ARM_DIR>")
                 .replace(str(config), "<CONFIG>")
                 .replace(tag, "<TAG>")
                for t in cmd
            ]
            for cmd in plan
        ]

    assert canonical(plan_a, FROZEN_TAG_A, world["config_a"]) == canonical(
        plan_b, FROZEN_TAG_B, world["config_b"]
    )


def test_assert_preflight_symmetry_rejects_tag_keyed_asymmetry(tmp_path: Path) -> None:
    arm_a = ArmSpec(label="a", tag=FROZEN_TAG_A, config_path=tmp_path / "a.json")
    arm_b = ArmSpec(label="b", tag=FROZEN_TAG_B, config_path=tmp_path / "b.json")
    dir_a = tmp_path / f"arm_{FROZEN_TAG_A}"
    dir_b = tmp_path / f"arm_{FROZEN_TAG_B}"
    common = dict(
        market_snapshot_json=tmp_path / "market.json",
        account_snapshot_json=tmp_path / "account.json",
        strategy_dir=tmp_path / "strategy",
        session_date="2026-07-10",
        decision_snapshot_digest="deadbeef",
        model_content_sha256="sha256:model",
        calibrator_content_sha256="sha256:cal",
    )
    plan_a = build_arm_plan(tag=arm_a.tag, config_path=arm_a.config_path, arm_dir=dir_a, **common)
    plan_b = build_arm_plan(tag=arm_b.tag, config_path=arm_b.config_path, arm_dir=dir_b, **common)

    # symmetric plans pass
    assert_preflight_symmetry(
        plan_a=plan_a, plan_b=plan_b, arm_a=arm_a, arm_b=arm_b,
        arm_dir_a=dir_a, arm_dir_b=dir_b,
        env_a=SHADOW_PREFLIGHT_ENV, env_b=SHADOW_PREFLIGHT_ENV,
    )

    # a tag-keyed preflight relaxation on ONE arm is a contract violation
    asymmetric = [list(cmd) for cmd in plan_b]
    asymmetric[0] = asymmetric[0] + ["--preflight-strict", "false"]
    with pytest.raises(ShadowABContractError):
        assert_preflight_symmetry(
            plan_a=plan_a, plan_b=asymmetric, arm_a=arm_a, arm_b=arm_b,
            arm_dir_a=dir_a, arm_dir_b=dir_b,
            env_a=SHADOW_PREFLIGHT_ENV, env_b=SHADOW_PREFLIGHT_ENV,
        )

    # an env delta between arms is a contract violation
    with pytest.raises(ShadowABContractError):
        assert_preflight_symmetry(
            plan_a=plan_a, plan_b=plan_b, arm_a=arm_a, arm_b=arm_b,
            arm_dir_a=dir_a, arm_dir_b=dir_b,
            env_a=SHADOW_PREFLIGHT_ENV,
            env_b={**SHADOW_PREFLIGHT_ENV, "RENQUANT_SHADOW_PREFLIGHT_STRICT": "1"},
        )


# --- tag validation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag_a", "tag_b"),
    [
        (LEGACY_SHADOW_TAG, FROZEN_TAG_B),   # legacy ops-shadow tag
        (FROZEN_TAG_A, LEGACY_SHADOW_TAG),
        (FROZEN_TAG_B, FROZEN_TAG_A),        # swapped arm identity
        (FROZEN_TAG_A, FROZEN_TAG_A),        # equal tags = state collision
        ("alpaca_shadow_c", FROZEN_TAG_B),   # novel tag
    ],
)
def test_tag_validation_rejects_non_frozen_tags(tag_a: str, tag_b: str) -> None:
    with pytest.raises(ValueError):
        validate_tags(tag_a, tag_b)


def test_tag_validation_accepts_frozen_pair() -> None:
    validate_tags(FROZEN_TAG_A, FROZEN_TAG_B)


def test_run_rejects_bad_tags_before_anything_else(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    with pytest.raises(ValueError):
        _run(world, tmp_path / "sessions", tag_a=LEGACY_SHADOW_TAG)


def test_run_rejects_identical_configs(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    with pytest.raises(ValueError):
        _run(world, tmp_path / "sessions", config_b=world["config_a"])


# --- safety rails ------------------------------------------------------------------------


def test_ntfy_topic_rejects_live_topic() -> None:
    with pytest.raises(ValueError):
        validate_ntfy_topic("renquant")
    validate_ntfy_topic(None)
    validate_ntfy_topic("renquant-shadow-ab")


def test_output_root_inside_umbrella_tree_rejected(tmp_path: Path) -> None:
    repo_root = tmp_path / "umbrella"
    repo_root.mkdir()
    with pytest.raises(ValueError):
        validate_output_root(repo_root / "data" / "shadow_ab", repo_root=repo_root)
    validate_output_root(tmp_path / "elsewhere", repo_root=repo_root)


def test_notifications_are_symmetric_across_arms(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    sent: list[tuple[str, str]] = []
    payload = _run(
        world, tmp_path / "sessions",
        notifier=lambda title, body: sent.append((title, body)),
    )
    assert payload["exit_code"] == EXIT_VALID
    assert len(sent) == 2
    titles = [title for title, _ in sent]
    assert titles == [
        f"[SHADOW-AB a:{FROZEN_TAG_A}] 2026-07-10 valid",
        f"[SHADOW-AB b:{FROZEN_TAG_B}] 2026-07-10 valid",
    ]
    # one shared template: identical modulo (label, tag)
    normalized = {
        t.replace(FROZEN_TAG_A, "<TAG>").replace(FROZEN_TAG_B, "<TAG>")
         .replace("AB a:", "AB <ARM>:").replace("AB b:", "AB <ARM>:")
        for t in titles
    }
    assert len(normalized) == 1


# --- plan-only + CLI wiring -----------------------------------------------------------------


def test_plan_only_invokes_nothing_and_writes_nothing(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    runner = RecordingRunner()
    sent: list[tuple[str, str]] = []
    payload = _run(
        world, out_root,
        plan_only=True,
        command_runner=runner,
        notifier=lambda title, body: sent.append((title, body)),
    )
    assert payload["exit_code"] == EXIT_VALID
    assert payload["status"] == "plan_only"
    assert runner.calls == []
    assert sent == []
    assert not out_root.exists()  # no freeze, no counters, no bundle
    # the plan is still fully stamped for review
    for label in ("a", "b"):
        assert payload["arms"][label]["planned_commands"]
        for field in SPEC_2A_ARM_FIELDS:
            assert payload["arms"][label][field]


def test_cli_shadow_ab_plan_only(tmp_path: Path, capsys, monkeypatch) -> None:
    world = _write_world(tmp_path)
    monkeypatch.setattr(
        sab, "_default_fingerprint_from_path", lambda: _fake_fingerprint,
    )
    monkeypatch.setattr(sab, "_default_orchestrator_commit", lambda: ORCH_COMMIT)
    lock = tmp_path / "umbrella" / "subrepos.lock.json"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({
        "subrepos": [{"name": name, "commit": sha} for name, sha in PINS.items()],
    }), encoding="utf-8")

    from renquant_orchestrator.cli import main as cli_main

    run_manifest, _ = _git_pinned_repos(tmp_path)
    rc = cli_main([
        "shadow-ab",
        "--config-a", str(world["config_a"]),
        "--config-b", str(world["config_b"]),
        "--data-manifest", str(world["manifest"]),
        "--output-root", str(tmp_path / "sessions"),
        "--market-snapshot-json", str(world["market"]),
        "--account-snapshot-json", str(world["account"]),
        "--session-date", "2026-07-10",
        "--repo-root", str(tmp_path / "umbrella"),
        "--strategy-dir", str(tmp_path / "umbrella" / "backtesting" / "renquant_104"),
        "--run-manifest", str(run_manifest),
        "--plan-only",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "plan_only"
    assert payload["arms"]["a"]["broker_state_tag"] == FROZEN_TAG_A
    assert payload["arms"]["b"]["broker_state_tag"] == FROZEN_TAG_B


def test_cli_rejects_live_ntfy_topic(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    from renquant_orchestrator.cli import main as cli_main

    run_manifest, _ = _git_pinned_repos(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        cli_main([
            "shadow-ab",
            "--config-a", str(world["config_a"]),
            "--config-b", str(world["config_b"]),
            "--data-manifest", str(world["manifest"]),
            "--output-root", str(tmp_path / "sessions"),
            "--market-snapshot-json", str(world["market"]),
            "--run-manifest", str(run_manifest),
            "--ntfy-topic", "renquant",
            "--plan-only",
        ])
    assert excinfo.value.code == 2


# --- counters accumulate across sessions ------------------------------------------------------


def test_excluded_pair_counter_accumulates(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    first = _run(world, out_root)
    assert first["counters"] == {
        "attempted_pairs": 1, "excluded_pairs": 0, "excluded_fraction": 0.0,
    }
    runner = RecordingRunner(fail_on="native-live-inference")
    second = _run(world, out_root, command_runner=runner, session_date="2026-07-13")
    assert second["counters"]["attempted_pairs"] == 2
    assert second["counters"]["excluded_pairs"] == 1
    assert second["counters"]["excluded_fraction"] == 0.5


# --- treatment-key isolation (Codex review on #451, point 3) --------------------------------


def test_treatment_key_violations_accepts_only_the_frozen_key() -> None:
    config_a = {"ranking": {"panel_scoring": {"buy_floor_std_mult": 0.5, "artifact_path": "m"}}}
    config_b = {"ranking": {"panel_scoring": {"buy_floor_std_mult": 1.0, "artifact_path": "m"}}}
    assert treatment_key_violations(config_a, config_b) == []


def test_treatment_key_violations_tolerates_reason_annotation_keys() -> None:
    config_a = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 0.5, "artifact_path": "m",
        "buy_floor_std_mult_reason": "treatment arm",
    }}}
    config_b = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 1.0, "artifact_path": "m",
        "buy_floor_std_mult_reason": "control arm",
    }}}
    assert treatment_key_violations(config_a, config_b) == []


def test_treatment_key_violations_tolerates_underscore_annotation_keys() -> None:
    """House convention: every ``_``-prefixed key is an inert annotation (the
    active==golden semantic-match rule; the merged strategy-104 #53 arm
    configs carry a documented ``_arm`` annotation). The validator must not
    count them as behavior deltas — caught live on the first plan-only run
    2026-07-10, where the real pinned arm configs were invalidated solely by
    their ``_arm`` strings."""
    config_a = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 0.5, "artifact_path": "m",
        "_arm": "S-0.5 TREATMENT",
    }}}
    config_b = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 1.0, "artifact_path": "m",
        "_arm": "S-1.0 CONTROL",
    }}}
    assert treatment_key_violations(config_a, config_b) == []


def test_underscore_keys_cannot_hide_a_functional_delta() -> None:
    """The annotation exemption must not become a laundering channel: a
    functional key nested UNDER an underscore-prefixed mapping is still
    stripped with its parent, so the only way to differ functionally remains
    a non-underscore path — assert a plain functional delta is still caught
    when an ``_arm`` annotation also differs."""
    config_a = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 0.5, "artifact_path": "m",
        "_arm": "a", "max_concentration": 0.35,
    }}}
    config_b = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 1.0, "artifact_path": "m",
        "_arm": "b", "max_concentration": 0.40,
    }}}
    violations = treatment_key_violations(config_a, config_b)
    assert violations
    assert any("max_concentration" in v for v in violations)
    assert not any("_arm" in v for v in violations)


def test_treatment_key_violations_rejects_an_extra_delta() -> None:
    """Negative test (explicitly requested by Codex review on #451): a later
    config edit that changes an UNRELATED key alongside the frozen treatment
    key must be caught, not waved through because the two config paths are
    merely distinct files."""
    config_a = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 0.5, "artifact_path": "m", "max_concentration": 0.35,
    }}}
    config_b = {"ranking": {"panel_scoring": {
        "buy_floor_std_mult": 1.0, "artifact_path": "m", "max_concentration": 0.40,
    }}}
    violations = treatment_key_violations(config_a, config_b)
    assert violations
    assert any("max_concentration" in v for v in violations)


def test_treatment_key_violations_rejects_no_delta_at_all() -> None:
    config = {"ranking": {"panel_scoring": {"buy_floor_std_mult": 1.0, "artifact_path": "m"}}}
    violations = treatment_key_violations(config, dict(config))
    assert violations
    assert any(FROZEN_TREATMENT_KEY in v for v in violations)


def test_run_aborts_when_config_diff_has_an_extra_delta(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    # sneak an unrelated additional delta into arm B's config
    config_b = json.loads(world["config_b"].read_text(encoding="utf-8"))
    config_b["ranking"]["panel_scoring"]["max_concentration"] = 0.40
    world["config_b"].write_text(json.dumps(config_b), encoding="utf-8")

    runner = RecordingRunner()
    payload = _run(world, tmp_path / "sessions", command_runner=runner)
    assert payload["exit_code"] == EXIT_PRECHECK_ABORT
    assert payload["status"] == "invalidated"
    assert any("treatment_key_violation" in r for r in payload["reasons"])
    assert runner.calls == []  # neither arm ran
    for label in ("a", "b"):
        assert any(
            "treatment-key isolation" in r
            for r in payload["arms"][label]["invalidation_reasons"]
        )


# --- decision-snapshot digest (Codex review on #451, point 1) -------------------------------


def test_decision_snapshot_digest_is_deterministic_and_dual_hash(tmp_path: Path) -> None:
    kwargs = dict(
        market_snapshot_sha256="sha256:m",
        account_snapshot_sha256="sha256:a",
        as_of="2026-07-10T15:55:00Z",
        session_date="2026-07-10",
        universe=["MSFT", "AAPL"],
        corporate_action_identity="none_declared",
        model_content_sha256="m1",
        calibrator_content_sha256="c1",
    )
    d1 = compute_decision_snapshot_digest(**kwargs)
    d2 = compute_decision_snapshot_digest(**{**kwargs, "universe": ["AAPL", "MSFT"]})
    assert d1 == d2  # deterministic; universe order-independent

    # EVERY identity component moves the digest — market hash, ACCOUNT hash
    # (r8: not market-only), as-of, session, universe, corporate actions
    for delta in (
        {"market_snapshot_sha256": "sha256:m2"},
        {"account_snapshot_sha256": "sha256:a2"},
        {"as_of": "2026-07-09T15:55:00Z"},
        {"session_date": "2026-07-09"},
        {"universe": ["AAPL"]},
        {"corporate_action_identity": "sha256:split"},
        {"model_content_sha256": "m2"},
        {"calibrator_content_sha256": None},
    ):
        assert compute_decision_snapshot_digest(**{**kwargs, **delta}) != d1, delta


def test_decision_snapshot_identity_requires_as_of(tmp_path: Path) -> None:
    market = tmp_path / "market.json"
    market.write_text(json.dumps({"prices": {"AAPL": 200.0}}), encoding="utf-8")
    account = tmp_path / "account.json"
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="as_of"):
        decision_snapshot_identity(
            market_snapshot_json=market,
            account_snapshot_json=account,
            session_date="2026-07-10",
            model_content_sha256="m1",
            calibrator_content_sha256="c1",
        )


def test_native_live_context_verifies_matching_digest(tmp_path: Path) -> None:
    market = tmp_path / "market.json"
    market.write_text(json.dumps({"as_of": "2026-07-10"}), encoding="utf-8")
    account = tmp_path / "account.json"
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")
    model = tmp_path / "model.pt"
    model.write_text("m-content", encoding="utf-8")
    calibrator = tmp_path / "calibrator.json"
    calibrator.write_text("c-content", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"ranking": {"panel_scoring": {
        "artifact_path": str(model),
        "global_calibration": {"enabled": True, "artifact_path": str(calibrator)},
    }}}), encoding="utf-8")
    model_sha = _fake_fingerprint(model)
    calibrator_sha = _fake_fingerprint(calibrator)

    expected = decision_snapshot_identity(
        market_snapshot_json=market,
        account_snapshot_json=account,
        session_date="2026-07-10",
        model_content_sha256=model_sha,
        calibrator_content_sha256=calibrator_sha,
    )["digest"]
    payload = build_native_live_context(
        strategy_config_json=config,
        market_snapshot_json=market,
        account_snapshot_json=account,
        output_json=tmp_path / "out.json",
        decision_snapshot_digest=expected,
        model_content_sha256=model_sha,
        calibrator_content_sha256=calibrator_sha,
        session_date="2026-07-10",
        fingerprint_from_path=_fake_fingerprint,
    )
    assert payload["metadata"]["decision_snapshot_digest"] == expected
    assert payload["metadata"]["decision_snapshot_verified"] is True
    assert payload["metadata"]["config_artifact_shas_verified"] is True
    assert payload["metadata"]["market_snapshot_sha256"].startswith("sha256:")
    assert payload["metadata"]["account_snapshot_sha256"].startswith("sha256:")


def test_native_live_context_rejects_account_substitution(tmp_path: Path) -> None:
    """r8: the consumption side recomputes from BOTH files — swapping in a
    different ACCOUNT snapshot while keeping the market snapshot identical
    must fail the arm, not pass a market-only digest check."""
    market = tmp_path / "market.json"
    market.write_text(json.dumps({"as_of": "2026-07-10"}), encoding="utf-8")
    account = tmp_path / "account.json"
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"k": "v"}), encoding="utf-8")

    expected = decision_snapshot_identity(
        market_snapshot_json=market,
        account_snapshot_json=account,
        session_date="2026-07-10",
        model_content_sha256="m1",
        calibrator_content_sha256="c1",
    )["digest"]
    # the account file is mutated after the digest was frozen
    account.write_text(json.dumps({"positions": {"AAPL": 10}}), encoding="utf-8")
    with pytest.raises(DecisionSnapshotMismatchError, match="account sha"):
        build_native_live_context(
            strategy_config_json=config,
            market_snapshot_json=market,
            account_snapshot_json=account,
            output_json=tmp_path / "out.json",
            decision_snapshot_digest=expected,
            model_content_sha256="m1",
            calibrator_content_sha256="c1",
            session_date="2026-07-10",
        )
    assert not (tmp_path / "out.json").exists()


def test_native_live_context_rejects_a_mismatched_digest(tmp_path: Path) -> None:
    """Consumption-side verification (r7 point 1): if this arm's actually-
    resolved inputs hash to something other than what was frozen before
    either arm ran, refuse to proceed rather than silently continue on a
    different-from-frozen input world."""
    market = tmp_path / "market.json"
    market.write_text(json.dumps({"as_of": "2026-07-10"}), encoding="utf-8")
    account = tmp_path / "account.json"
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"k": "v"}), encoding="utf-8")

    with pytest.raises(DecisionSnapshotMismatchError):
        build_native_live_context(
            strategy_config_json=config,
            market_snapshot_json=market,
            account_snapshot_json=account,
            output_json=tmp_path / "out.json",
            decision_snapshot_digest="not-the-real-digest",
            model_content_sha256="m1",
            calibrator_content_sha256="c1",
            session_date="2026-07-10",
        )
    # a failed verification must not have written a stale/misleading output
    assert not (tmp_path / "out.json").exists()


def test_run_shadow_ab_session_hands_both_arms_the_identical_digest(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    payload = _run(world, tmp_path / "sessions")
    assert payload["exit_code"] == EXIT_VALID

    digest_a = payload["arms"]["a"]["decision_snapshot_digest"]
    digest_b = payload["arms"]["b"]["decision_snapshot_digest"]
    assert digest_a and digest_a == digest_b

    def extract_digest(commands: list[list[str]]) -> str:
        for cmd in commands:
            if "native-live-context" in cmd:
                return cmd[cmd.index("--decision-snapshot-digest") + 1]
        raise AssertionError("no native-live-context command found")

    plan_a_digest = extract_digest(payload["arms"]["a"]["planned_commands"])
    plan_b_digest = extract_digest(payload["arms"]["b"]["planned_commands"])
    assert plan_a_digest == plan_b_digest == digest_a


# --- sealed paired world (Codex r8 review on #451) -------------------------------------------


def test_seal_snapshot_is_atomic_canonical_and_readonly(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    # non-canonical formatting on purpose: odd key order + extra whitespace
    source.write_text('{\n  "b": 2,   "a": 1\n}\n', encoding="utf-8")
    dest = tmp_path / "sealed" / "snapshot.json"

    sha = seal_snapshot(source, dest)
    assert dest.exists()
    # hash is over CANONICAL content, so it matches the parsed payload
    assert sha == canonical_json_sha256({"a": 1, "b": 2})
    # the sealed copy parses back to the same semantic content
    assert json.loads(dest.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    # no temp files leak from the atomic write
    assert [p.name for p in dest.parent.iterdir()] == [dest.name]
    # best-effort immutability
    assert not (dest.stat().st_mode & 0o222)


def test_verify_decision_snapshot_detects_sealed_mutation(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    payload = _run(world, out_root)
    assert payload["exit_code"] == EXIT_VALID
    snapshot = payload["decision_snapshot"]

    assert verify_decision_snapshot(snapshot) == []

    sealed_account = Path(snapshot["sealed_account_snapshot"])
    sealed_account.chmod(0o644)
    sealed_account.write_text(json.dumps({"positions": {"TAMPERED": 1}}), encoding="utf-8")
    problems = verify_decision_snapshot(snapshot)
    assert any("sealed account snapshot mutated" in p for p in problems)
    assert any("decision_snapshot_digest recompute mismatch" in p for p in problems)


def test_source_account_mutation_after_precheck_fails_both_arms(tmp_path: Path) -> None:
    """Negative test (a), Codex r8: the caller mutates the ACCOUNT file after
    the precheck sealed/digested it -> the paired-world verification between
    the arms catches it and BOTH arms fail; arm B is never invoked."""
    world = _write_world(tmp_path)
    runner = MutatingRunner(
        trigger=f"arm_{FROZEN_TAG_A}",
        side_effect=lambda: world["account"].write_text(
            json.dumps({"positions": {"MUTATED-MID-RUN": 1}}), encoding="utf-8",
        ),
    )
    payload = _run(world, tmp_path / "sessions", command_runner=runner)

    assert payload["exit_code"] == EXIT_SESSION_INVALIDATED
    assert payload["status"] == "invalidated"
    assert any(
        "paired_world_violation[pre_arm_b]" in r and "account snapshot source mutated" in r
        for r in payload["reasons"]
    )
    for label in ("a", "b"):
        assert payload["arms"][label]["invalidated"] is True
    # arm B never ran: no recorded invocation touches its arm dir/tag
    assert not any(
        any(FROZEN_TAG_B in token for token in cmd) for cmd, _ in runner.calls
    )
    # ... and the arms only ever consumed the SEALED copy, which is intact:
    # the failure is the SOURCE destabilizing mid-session (torn-world signal),
    # detected without ever handing arms the caller path
    snapshot = payload["decision_snapshot"]
    sealed_account_sha = canonical_json_sha256(
        json.loads(Path(snapshot["sealed_account_snapshot"]).read_text(encoding="utf-8"))
    )
    assert sealed_account_sha == snapshot["account_snapshot_sha256"]


def test_account_only_difference_changes_digest_and_aborts_rerun(tmp_path: Path) -> None:
    """Negative test (b), Codex r8: two invocations of the SAME session with
    an IDENTICAL market snapshot but DIFFERENT account snapshots must produce
    different decision digests -> same-world abort, neither arm runs."""
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    first = _run(world, out_root)
    assert first["exit_code"] == EXIT_VALID
    first_digest = first["decision_snapshot"]["digest"]

    # identical market, different account
    world["account"].write_text(
        json.dumps({"positions": {"NEW-POSITION": 5}}), encoding="utf-8",
    )
    runner = RecordingRunner()
    second = _run(world, out_root, command_runner=runner)  # same session_date

    assert second["exit_code"] == EXIT_PRECHECK_ABORT
    assert second["status"] == "invalidated"
    assert second["decision_snapshot"]["digest"] != first_digest
    assert second["decision_snapshot"]["market_snapshot_sha256"] == (
        first["decision_snapshot"]["market_snapshot_sha256"]
    )
    assert any(
        "same_world_violation" in r and "decision_snapshot_digest" in r
        for r in second["reasons"]
    )
    assert runner.calls == []  # neither arm ran
    for label in ("a", "b"):
        assert second["arms"][label]["invalidated"] is True


def test_mid_run_mutation_of_sealed_bundle_file_detected(tmp_path: Path) -> None:
    """Negative test (c), Codex r8: a sealed run-bundle file mutated MID-RUN
    (here during arm B, after pre_arm_b passed) is caught by the post-arms
    verification and the session-pair fails in BOTH arms."""
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    sealed_account = out_root / "2026-07-10" / SEALED_DIRNAME / SEALED_ACCOUNT_FILENAME

    def tamper_sealed() -> None:
        sealed_account.chmod(0o644)
        sealed_account.write_text(
            json.dumps({"positions": {"TAMPERED": 1}}), encoding="utf-8",
        )

    runner = MutatingRunner(trigger=f"arm_{FROZEN_TAG_B}", side_effect=tamper_sealed)
    payload = _run(world, out_root, command_runner=runner)

    assert payload["exit_code"] == EXIT_SESSION_INVALIDATED
    assert payload["status"] == "invalidated"
    assert any(
        "paired_world_violation[post_arms]" in r and "sealed account snapshot mutated" in r
        for r in payload["reasons"]
    )
    for label in ("a", "b"):
        assert payload["arms"][label]["invalidated"] is True
    # the verification trail shows exactly where it was caught
    stages = {v["stage"]: v["ok"] for v in payload["paired_world_verifications"]}
    assert stages["pre_arm_a"] is True
    assert stages["pre_arm_b"] is True
    assert stages["post_arms"] is False


# --- pin/commit drift (Codex review on #451, point 2) ---------------------------------------


def test_pin_drift_invalidates_pair_without_voiding(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    first = _run(world, out_root)
    assert first["exit_code"] == EXIT_VALID

    drifted_pins = dict(PINS)
    drifted_pins["renquant-execution"] = "changed-mid-experiment"
    runner = RecordingRunner()
    second = _run(
        world, out_root, command_runner=runner, session_date="2026-07-13",
        pins_resolver=lambda: drifted_pins,
    )
    assert second["exit_code"] == EXIT_PRECHECK_ABORT
    assert second["status"] == "invalidated"
    assert second["void"] is False
    assert any("subrepo_pins" in r for r in second["reasons"])
    assert runner.calls == []


def test_orchestrator_commit_drift_invalidates_pair_without_voiding(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    first = _run(world, out_root)
    assert first["exit_code"] == EXIT_VALID

    runner = RecordingRunner()
    second = _run(
        world, out_root, command_runner=runner, session_date="2026-07-13",
        orchestrator_commit_resolver=lambda: "a-different-commit",
    )
    assert second["exit_code"] == EXIT_PRECHECK_ABORT
    assert second["status"] == "invalidated"
    assert second["void"] is False
    assert any("orchestrator_commit" in r for r in second["reasons"])
    assert runner.calls == []


def test_freeze_payload_records_pins_and_orchestrator_commit(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    out_root = tmp_path / "sessions"
    payload = _run(world, out_root)
    assert payload["exit_code"] == EXIT_VALID

    freeze = json.loads((out_root / "shadow_ab_freeze.json").read_text(encoding="utf-8"))
    assert freeze["subrepo_pins"] == PINS
    assert freeze["orchestrator_commit"] == ORCH_COMMIT


# --- no umbrella-layout fallback (Codex review on #451, point 4) ----------------------------


def test_default_experiment_strategy_dir_fails_closed_without_pinned_checkout(
    tmp_path: Path,
) -> None:
    """The §2a experiment path may never fall back to an umbrella-layout
    path (RFC frozen rule) -- if the pinned renquant-strategy-104 checkout
    isn't there, fail loudly instead of silently resolving somewhere else."""
    empty_github_root = tmp_path / "no-repos-here"
    empty_github_root.mkdir()
    with pytest.raises(ShadowABContractError, match="renquant-strategy-104"):
        default_experiment_strategy_dir(github_root=empty_github_root)


def test_default_experiment_strategy_dir_resolves_the_pinned_checkout(
    tmp_path: Path,
) -> None:
    github_root = tmp_path / "github"
    pinned = github_root / "renquant-strategy-104" / "configs"
    pinned.mkdir(parents=True)
    assert default_experiment_strategy_dir(github_root=github_root) == pinned


def test_run_shadow_ab_session_never_defaults_to_umbrella_layout_path(
    tmp_path: Path, monkeypatch,
) -> None:
    """No umbrella checkout is required to construct/validate the runner:
    when strategy_dir is omitted, resolution must go through
    default_experiment_strategy_dir(), never repo_root / "backtesting" /
    "renquant_104" directly. Hermetic: the resolver itself is monkeypatched
    to a sentinel so this doesn't depend on real sibling checkouts existing
    on the machine running the tests."""
    world = _write_world(tmp_path)
    sentinel = tmp_path / "pinned-strategy-104-configs"
    sentinel.mkdir()
    monkeypatch.setattr(sab, "default_experiment_strategy_dir", lambda: sentinel)

    payload = _run(world, tmp_path / "sessions", strategy_dir=None)
    assert payload["exit_code"] == EXIT_VALID
    for label in ("a", "b"):
        assert any(
            str(sentinel) in cmd
            for cmd in payload["arms"][label]["planned_commands"]
        )
    umbrella_layout_fragment = str(Path("backtesting") / "renquant_104")
    for label in ("a", "b"):
        assert not any(
            umbrella_layout_fragment in " ".join(cmd)
            for cmd in payload["arms"][label]["planned_commands"]
        )


def test_no_umbrella_module_imported_by_a_hermetic_session(tmp_path: Path) -> None:
    """Static/runtime guard: this module's own import graph and a full
    hermetic session (RecordingRunner -- no real subprocess) must never
    reach anything importable from the umbrella package tree. This does
    NOT prove a real subprocess invocation stays umbrella-free (that
    requires the actual native-live-run integration, out of this module's
    scope) -- it proves shadow_ab_runner + native_live_context themselves
    never import umbrella code to do their own orchestration."""
    import sys as _sys

    world = _write_world(tmp_path)
    before = {name for name in _sys.modules if "RenQuant" in name or "renquant_104" in name}
    assert before == set()
    payload = _run(world, tmp_path / "sessions", command_runner=RecordingRunner())
    assert payload["exit_code"] == EXIT_VALID
    after = {name for name in _sys.modules if "RenQuant" in name or "renquant_104" in name}
    assert after == set()


# --- CLI surface contract (2026-07-10 first-real-session incident) ---------------------------


def test_every_runner_emitted_command_parses_and_dispatches_through_cli(
    tmp_path: Path, monkeypatch,
) -> None:
    """The first REAL two-arm session (2026-07-10 bundle) failed because
    build_arm_plan emitted paired-world flags the TOP-LEVEL cli.py subparser
    never declared ("unrecognized arguments: --decision-snapshot-digest ...")
    and the native-live-run subcommand did not exist at all — the module
    main()s accepted the args, but the runner invokes `python -m
    renquant_orchestrator <subcommand>`, which goes through cli.py. Pin:
    EVERY command the runner emits parses through cli.main and reaches its
    dispatch target, with the paired-world flags threaded through."""
    import renquant_orchestrator.native_live_context as nlc
    import renquant_orchestrator.native_live_inference as nli
    import renquant_orchestrator.native_live_run as nlr
    import renquant_orchestrator.native_live_snapshots as nls
    from renquant_orchestrator.cli import main as cli_main

    received: dict[str, list[str]] = {}

    def _stub(name: str):
        def _main(argv=None):
            received[name] = list(argv or [])
            return 0
        return _main

    monkeypatch.setattr(nlc, "main", _stub("native-live-context"))
    monkeypatch.setattr(nli, "main", _stub("native-live-inference"))
    monkeypatch.setattr(nlr, "main", _stub("native-live-run"))
    monkeypatch.setattr(nls, "account_main", _stub("native-live-account-snapshot"))

    plan = build_arm_plan(
        tag=FROZEN_TAG_A,
        config_path=tmp_path / "strategy_config.shadow.json",
        arm_dir=tmp_path / f"arm_{FROZEN_TAG_A}",
        market_snapshot_json=tmp_path / "sealed" / "market_snapshot.json",
        account_snapshot_json=tmp_path / "sealed" / "account_snapshot.json",
        strategy_dir=tmp_path / "configs",
        session_date="2026-07-10",
        decision_snapshot_digest="d" * 64,
        model_content_sha256="sha256:m",
        calibrator_content_sha256="sha256:c",
        repo_root=tmp_path / "runtime-root",
    )
    shared_fetch = [
        "renquant-orchestrator", "native-live-account-snapshot",
        "--broker-name", "readonly-alpaca",
        "--output-json", str(tmp_path / "account_snapshot.fetched.json"),
    ]

    for command in [shared_fetch, *plan]:
        assert command[0] == "renquant-orchestrator"
        rc = cli_main(list(command[1:]))
        assert rc == 0, f"cli rejected runner-emitted command: {command}"

    assert set(received) == {
        "native-live-account-snapshot",
        "native-live-context",
        "native-live-inference",
        "native-live-run",
    }
    # the paired-world flags AND the runner's own resolution anchors reach
    # the context module intact (the context must resolve artifacts through
    # EXACTLY the anchors the runner's precheck used)
    context_argv = received["native-live-context"]
    for flag, value in (
        ("--decision-snapshot-digest", "d" * 64),
        ("--model-content-sha256", "sha256:m"),
        ("--calibrator-content-sha256", "sha256:c"),
        ("--session-date", "2026-07-10"),
        ("--strategy-dir", str(tmp_path / "configs")),
        ("--repo-root", str(tmp_path / "runtime-root")),
    ):
        assert value == context_argv[context_argv.index(flag) + 1]
    # the arm-isolation args reach the native run module intact
    run_argv = received["native-live-run"]
    assert FROZEN_TAG_A == run_argv[run_argv.index("--broker-name") + 1]
    assert FROZEN_TAG_A == run_argv[run_argv.index("--live-state-broker-name") + 1]
    # the pipeline-context hydration args reach the inference module intact
    # (GOAL-1: without them the pinned pipeline gets a bare namespace and
    # dies on ctx.today)
    inference_argv = received["native-live-inference"]
    assert "--hydrate-pipeline-context" in inference_argv
    for flag, value in (
        ("--session-date", "2026-07-10"),
        ("--broker-name", FROZEN_TAG_A),
        ("--strategy-dir", str(tmp_path / "configs")),
        ("--repo-root", str(tmp_path / "runtime-root")),
    ):
        assert value == inference_argv[inference_argv.index(flag) + 1]


# --- immutable run manifest (Codex r2 on #460) ------------------------------------------------


def test_e2e_unpinned_sibling_rejected(tmp_path: Path) -> None:
    """Named e2e (r2): a checkout that merely EXISTS is not a pinned repo.
    A manifest-commit mismatch (an 'unpinned sibling') and a dirty working
    tree must both abort the session-pair BEFORE either arm runs."""
    import subprocess as sp

    world = _write_world(tmp_path)
    run_manifest, repos = _git_pinned_repos(tmp_path)

    # (a) unpinned: rewrite the manifest to expect a different commit
    payload = json.loads(run_manifest.read_text(encoding="utf-8"))
    payload["repos"]["renquant-pipeline"]["commit"] = "f" * 40
    unpinned = tmp_path / "run_manifest_unpinned.json"
    unpinned.write_text(json.dumps(payload), encoding="utf-8")

    runner = RecordingRunner()
    result = _run(
        world, tmp_path / "sessions",
        run_manifest=unpinned, command_runner=runner, pins_resolver=None,
    )
    assert result["exit_code"] == EXIT_PRECHECK_ABORT
    assert result["status"] == "invalidated"
    assert any(
        "run manifest verification failed" in r and "checkout HEAD" in r
        for r in result["reasons"]
    )
    assert runner.calls == []  # neither arm ran

    # (b) dirty tree at the RIGHT commit is still rejected (tracked modification)
    dirty_repo = Path(repos["renquant-execution"]["path"])
    (dirty_repo / "configs" / "marker.txt").write_text("modified", encoding="utf-8")
    runner = RecordingRunner()
    result = _run(
        world, tmp_path / "sessions",
        run_manifest=run_manifest, command_runner=runner, pins_resolver=None,
    )
    assert result["exit_code"] == EXIT_PRECHECK_ABORT
    assert any("DIRTY" in r for r in result["reasons"])
    assert runner.calls == []
    sp.run(["git", "-C", str(dirty_repo), "checkout", "--", "configs/marker.txt"],
           capture_output=True, check=True)


def test_run_manifest_verified_session_records_commits_and_data_revision(
    tmp_path: Path,
) -> None:
    world = _write_world(tmp_path)
    run_manifest, repos = _git_pinned_repos(tmp_path)
    payload = _run(
        world, tmp_path / "sessions",
        run_manifest=run_manifest, pins_resolver=None,
    )
    assert payload["exit_code"] == EXIT_VALID
    record = payload["run_manifest"]
    assert record["verified"] is True
    assert record["data_revision"] == "ohlcv-refresh-2026-07-10"
    for name in EXPERIMENT_PIN_REPOS:
        assert record["repos"][name]["commit"] == repos[name]["commit"]
        # the pins in every arm entry come FROM the manifest
        assert payload["arms"]["a"]["subrepo_pins"][name] == repos[name]["commit"]
    # ... and the SEALED decision snapshot carries the same record
    sealed = json.loads(
        (tmp_path / "sessions" / "2026-07-10" / SEALED_DIRNAME /
         "decision_snapshot.json").read_text(encoding="utf-8")
    )
    assert sealed["run_manifest"]["repos"] == record["repos"]
    assert sealed["run_manifest"]["data_revision"] == "ohlcv-refresh-2026-07-10"
    # the inference step is handed the manifest's data revision
    plan_a = payload["arms"]["a"]["planned_commands"]
    inference_cmd = next(c for c in plan_a if "native-live-inference" in c)
    assert "ohlcv-refresh-2026-07-10" == (
        inference_cmd[inference_cmd.index("--data-revision") + 1]
    )


def test_run_manifest_missing_required_repo_is_a_usage_error(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    bad = tmp_path / "bad_manifest.json"
    bad.write_text(json.dumps({
        "schema_version": 1,
        "repos": {"renquant-pipeline": {"path": str(tmp_path), "commit": "a" * 40}},
    }), encoding="utf-8")
    with pytest.raises(ShadowABContractError, match="missing required repo"):
        _run(world, tmp_path / "sessions", run_manifest=bad, pins_resolver=None)


# --- manifest-declared artifact store (store-addressed refs, Codex on #464) ----


def _store_world(tmp_path: Path) -> tuple[dict[str, Path], Path]:
    """A world whose configs use PROD-STYLE store-addressed refs
    ("../../artifacts/<...>") that only the declared store can satisfy —
    the pinned-checkout layout of the first real session, no umbrella
    geometry anywhere."""
    world = _write_world(tmp_path)
    store = tmp_path / "declared-store"
    (store / "panel").mkdir(parents=True)
    (store / "panel" / "model.pt").write_text("model-1", encoding="utf-8")
    (store / "panel" / "calibrator.json").write_text("cal-1", encoding="utf-8")
    for key in ("config_a", "config_b"):
        world[key].write_text(json.dumps({
            "ranking": {"panel_scoring": {
                "artifact_path": "../../artifacts/panel/model.pt",
                "buy_floor_std_mult": 0.5 if key == "config_a" else 1.0,
                "global_calibration": {
                    "enabled": True,
                    "artifact_path": "../../artifacts/panel/calibrator.json",
                },
            }},
        }), encoding="utf-8")
    return world, store


def test_resolve_arm_fingerprints_uses_declared_store(tmp_path: Path) -> None:
    world, store = _store_world(tmp_path)
    fp = resolve_arm_fingerprints(
        world["config_a"],
        strategy_dir=tmp_path / "runtime" / "repos" / "renquant-strategy-104",
        repo_root=tmp_path / "runtime",
        data_manifest_path=world["manifest"],
        artifact_store=store,
        fingerprint_from_path=_fake_fingerprint,
    )
    assert fp.model_content_sha256 == _fake_fingerprint(store / "panel" / "model.pt")
    assert fp.calibrator_content_sha256 == _fake_fingerprint(
        store / "panel" / "calibrator.json"
    )


def test_resolve_arm_fingerprints_without_store_fails_closed(tmp_path: Path) -> None:
    world, _store = _store_world(tmp_path)
    with pytest.raises(FileNotFoundError):
        resolve_arm_fingerprints(
            world["config_a"],
            strategy_dir=tmp_path / "runtime" / "repos" / "renquant-strategy-104",
            repo_root=tmp_path / "runtime",
            data_manifest_path=world["manifest"],
            fingerprint_from_path=_fake_fingerprint,
        )


def _pinned_store_repo(tmp_path: Path, store: Path, run_manifest: Path) -> Path:
    """Commit the store dir as its own tiny git repo and register it as a
    NAMED manifest repo — the r3 binding: the store lives inside a
    commit-verified, clean checkout, never behind a free path."""
    import subprocess as sp

    repo = tmp_path / "pins" / "renquant-artifacts"
    (repo / "store").mkdir(parents=True)
    for f in store.rglob("*"):
        if f.is_file():
            dest = repo / "store" / f.relative_to(store)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "add", "."], check=True)
    sp.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "store"],
        check=True,
    )
    head = sp.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, text=True, stdout=sp.PIPE,
    ).stdout.strip()
    payload = json.loads(run_manifest.read_text(encoding="utf-8"))
    payload["repos"]["renquant-artifacts"] = {"path": str(repo), "commit": head}
    payload["artifact_store"] = {"repo": "renquant-artifacts", "path": "store"}
    run_manifest.write_text(json.dumps(payload), encoding="utf-8")
    return repo / "store"


def test_manifest_artifact_store_recorded_and_threaded_into_arm_plans(
    tmp_path: Path,
) -> None:
    world, store = _store_world(tmp_path)
    run_manifest, _repos = _git_pinned_repos(tmp_path)
    pinned_store = _pinned_store_repo(tmp_path, store, run_manifest)

    result = _run(
        world, tmp_path / "sessions",
        run_manifest=run_manifest, pins_resolver=None,
    )
    assert result["exit_code"] == EXIT_VALID
    record = result["run_manifest"]["artifact_store"]
    assert record["repo"] == "renquant-artifacts"
    assert record["path"] == "store"
    assert record["root"] == str(pinned_store)
    assert record["commit"]  # the verified pin, not a free path
    for arm in ("a", "b"):
        plan = result["arms"][arm]["planned_commands"]
        context_cmd = next(c for c in plan if "native-live-context" in c)
        inference_cmd = next(c for c in plan if "native-live-inference" in c)
        for cmd in (context_cmd, inference_cmd):
            assert cmd[cmd.index("--artifact-store") + 1] == str(pinned_store)


def test_store_repo_with_dirty_tree_aborts_before_either_arm(tmp_path: Path) -> None:
    world, store = _store_world(tmp_path)
    run_manifest, _repos = _git_pinned_repos(tmp_path)
    pinned_store = _pinned_store_repo(tmp_path, store, run_manifest)
    (pinned_store / "panel" / "model.pt").write_text("tampered", encoding="utf-8")

    result = _run(
        world, tmp_path / "sessions",
        run_manifest=run_manifest, pins_resolver=None,
    )
    assert result["exit_code"] == EXIT_PRECHECK_ABORT
    assert any("DIRTY" in r for r in result["reasons"])


def test_manifest_artifact_store_missing_dir_aborts_precheck(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    run_manifest, _repos = _git_pinned_repos(tmp_path)
    payload = json.loads(run_manifest.read_text(encoding="utf-8"))
    # names a verified repo, but the subdir does not exist inside it
    payload["artifact_store"] = {
        "repo": "renquant-strategy-104", "path": "no-such-store",
    }
    run_manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(
        world, tmp_path / "sessions",
        run_manifest=run_manifest, pins_resolver=None,
    )
    assert result["exit_code"] == EXIT_PRECHECK_ABORT
    assert any("artifact_store" in r for r in result["reasons"])


def test_manifest_artifact_store_rejects_untyped_and_unpinned_forms(
    tmp_path: Path,
) -> None:
    run_manifest, _repos = _git_pinned_repos(tmp_path)
    payload = json.loads(run_manifest.read_text(encoding="utf-8"))

    # a bare path is not a pinned owner (the r2 rejection: it can point
    # straight back at the deprecated umbrella tree)
    payload["artifact_store"] = {"path": "/Users/anyone/RenQuant/artifacts"}
    run_manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ShadowABContractError, match="pinned owner"):
        load_run_manifest(run_manifest)

    # naming a repo outside the manifest is rejected
    payload["artifact_store"] = {"repo": "not-a-manifest-repo", "path": "store"}
    run_manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ShadowABContractError, match="not a manifest repo"):
        load_run_manifest(run_manifest)

    # escaping the repo with ".." or an absolute subdir is rejected
    for bad in ("../outside", "/abs/store"):
        payload["artifact_store"] = {"repo": "renquant-strategy-104", "path": bad}
        run_manifest.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ShadowABContractError, match="relative subdir"):
            load_run_manifest(run_manifest)


def test_store_root_symlink_escaping_repo_aborts_precheck(tmp_path: Path) -> None:
    # r4 resolve-and-contain: a committed symlink AT the store subdir that
    # points outside the named clean checkout must precheck-abort.
    import subprocess as sp

    world, store = _store_world(tmp_path)
    run_manifest, _repos = _git_pinned_repos(tmp_path)

    outside = tmp_path / "outside-store"
    (outside / "panel").mkdir(parents=True)
    (outside / "panel" / "model.pt").write_text("model-1", encoding="utf-8")
    (outside / "panel" / "calibrator.json").write_text("cal-1", encoding="utf-8")

    repo = tmp_path / "pins" / "renquant-artifacts"
    repo.mkdir(parents=True)
    (repo / "store").symlink_to(outside)
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "add", "."], check=True)
    sp.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "symlinked store"],
        check=True,
    )
    head = sp.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, text=True, stdout=sp.PIPE,
    ).stdout.strip()
    payload = json.loads(run_manifest.read_text(encoding="utf-8"))
    payload["repos"]["renquant-artifacts"] = {"path": str(repo), "commit": head}
    payload["artifact_store"] = {"repo": "renquant-artifacts", "path": "store"}
    run_manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(
        world, tmp_path / "sessions",
        run_manifest=run_manifest, pins_resolver=None,
    )
    assert result["exit_code"] == EXIT_PRECHECK_ABORT
    assert any("escapes its named repo" in r for r in result["reasons"])


def test_artifact_symlink_escaping_store_aborts_precheck(tmp_path: Path) -> None:
    # r4: a symlinked FILE below the store targeting an external directory
    # must also precheck-abort (containment enforced per resolved artifact).
    import subprocess as sp

    world, store = _store_world(tmp_path)
    run_manifest, _repos = _git_pinned_repos(tmp_path)
    pinned_store = _pinned_store_repo(tmp_path, store, run_manifest)

    outside = tmp_path / "outside-blob"
    outside.mkdir()
    (outside / "evil.pt").write_text("model-1", encoding="utf-8")
    repo = pinned_store.parent
    victim = pinned_store / "panel" / "model.pt"
    victim.unlink()
    victim.symlink_to(outside / "evil.pt")
    sp.run(["git", "-C", str(repo), "add", "."], check=True)
    sp.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "symlinked blob"],
        check=True,
    )
    head = sp.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, text=True, stdout=sp.PIPE,
    ).stdout.strip()
    payload = json.loads(run_manifest.read_text(encoding="utf-8"))
    payload["repos"]["renquant-artifacts"]["commit"] = head
    run_manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(
        world, tmp_path / "sessions",
        run_manifest=run_manifest, pins_resolver=None,
    )
    assert result["exit_code"] == EXIT_PRECHECK_ABORT
    assert any("escapes the declared artifact store" in r for r in result["reasons"])


# --- write containment + post-arm quarantine (2026-07-11 self-poisoning) -------


def test_arm_inference_commands_carry_log_containment_dir(tmp_path: Path) -> None:
    world = _write_world(tmp_path)
    result = _run(world, tmp_path / "sessions")
    for arm in ("a", "b"):
        plan = result["arms"][arm]["planned_commands"]
        inference_cmd = next(c for c in plan if "native-live-inference" in c)
        contained = inference_cmd[inference_cmd.index("--log-containment-dir") + 1]
        # the arm's OWN directory — never the pinned strategy checkout
        assert f"arm_" in contained and str(tmp_path / "sessions") in contained


def test_post_arm_quarantine_moves_stray_logs_and_warns(tmp_path: Path) -> None:
    from renquant_orchestrator.shadow_ab_runner import (
        quarantine_stray_arm_byproducts,
    )
    import subprocess as sp

    repo = tmp_path / "pins" / "renquant-strategy-104"
    (repo / "configs").mkdir(parents=True)
    (repo / "configs" / "m.txt").write_text("x", encoding="utf-8")
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "add", "."], check=True)
    sp.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", "init"], check=True)
    # a session byproduct (the incident shape) + an unrelated dirty file
    (repo / "logs").mkdir()
    (repo / "logs" / "admission_shadow.jsonl").write_text("{}", encoding="utf-8")
    (repo / "configs" / "m.txt").write_text("hand-edit", encoding="utf-8")

    manifest = {"repos": {"renquant-strategy-104": {"path": str(repo), "commit": "x"}}}
    notes = quarantine_stray_arm_byproducts(
        manifest, quarantine_root=tmp_path / "q",
    )
    # logs/ quarantined with evidence preserved (destination is a claimed
    # unique-attempt dir, not a fixed path — see the retry-safety test below)
    assert not (repo / "logs").exists()
    quarantined = list((tmp_path / "q").glob("renquant-strategy-104-logs-*"))
    assert len(quarantined) == 1
    assert (quarantined[0] / "admission_shadow.jsonl").exists()
    assert any("post_arm_quarantine" in n for n in notes)
    # the unrelated dirty file is REPORTED but left in place (fail-closed next
    # session, by design)
    assert (repo / "configs" / "m.txt").read_text() == "hand-edit"
    assert any("post_arm_tree_dirty" in n for n in notes)


def test_post_arm_quarantine_is_retry_safe_across_repeated_calls(tmp_path: Path) -> None:
    """2026-07-11 r1 review: a retried or repeated same-session quarantine
    after an earlier successful move must not find its destination already
    present. Simulates a retry by calling quarantine_stray_arm_byproducts
    TWICE in one session, re-creating a stray logs/ byproduct between calls
    (as a second arm run would) — both calls must succeed and leave the
    pinned checkout clean, never raising and never leaving logs/ behind."""
    from renquant_orchestrator.shadow_ab_runner import (
        quarantine_stray_arm_byproducts,
    )
    import subprocess as sp

    repo = tmp_path / "pins" / "renquant-strategy-104"
    (repo / "configs").mkdir(parents=True)
    (repo / "configs" / "m.txt").write_text("x", encoding="utf-8")
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "add", "."], check=True)
    sp.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", "init"], check=True)

    manifest = {"repos": {"renquant-strategy-104": {"path": str(repo), "commit": "x"}}}
    quarantine_root = tmp_path / "q"

    for attempt_content in ('{"attempt": 1}', '{"attempt": 2}'):
        (repo / "logs").mkdir()
        (repo / "logs" / "admission_shadow.jsonl").write_text(
            attempt_content, encoding="utf-8"
        )
        notes = quarantine_stray_arm_byproducts(
            manifest, quarantine_root=quarantine_root,
        )
        # the checkout is clean after EVERY attempt, not just the first
        assert not (repo / "logs").exists(), "logs/ left behind after a retry"
        assert not any(
            "post_arm_quarantine_error" in n for n in notes
        ), f"quarantine raised/errored on retry: {notes}"
        assert any("post_arm_quarantine:" in n for n in notes)

    # both attempts' evidence survives distinctly — nothing was overwritten
    quarantined_dirs = sorted((tmp_path / "q").glob("renquant-strategy-104-logs-*"))
    assert len(quarantined_dirs) == 2
    contents = sorted(
        (d / "admission_shadow.jsonl").read_text() for d in quarantined_dirs
    )
    assert contents == ['{"attempt": 1}', '{"attempt": 2}']

    # the append-only bundle record has one line per attempt
    index_path = quarantine_root / "index.jsonl"
    assert index_path.exists()
    lines = index_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert record["status"] == "quarantined"
        assert record["repo"] == "renquant-strategy-104"
