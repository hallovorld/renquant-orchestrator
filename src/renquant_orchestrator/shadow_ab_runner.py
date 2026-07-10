"""Two-arm shadow A/B session runner — D6-§2a prerequisite P-2 (UNINVOKED).

Runs the §2a breadth-lever admission A/B: two isolated shadow arms, identical
except the treatment key, once per session, sequentially, on the SAME session
inputs. This module is pure orchestration code + contract enforcement; it is
NOT scheduled anywhere (no launchd entry, no daily_104 wiring) — arming is a
later, separately-gated step after the D6 protocol PR (#443) merges.

Frozen review contract (doc/design/2026-07-09-governor-prereg-replay-protocol.md
§2a, P-2 build item) enforced here:

  (i)   both arms run the IDENTICAL pinned code path with ARM-SYMMETRIC
        preflight policy — the shadow (non-strict) preflight relaxation is
        owned by this entrypoint and applied to BOTH arms from one shared
        template; a tag-keyed asymmetry is structurally impossible and is
        additionally rejected by :func:`assert_preflight_symmetry`;
  (ii)  arms run SEQUENTIALLY, never concurrently, against the same session's
        inputs (the shared market/account snapshots are resolved once and both
        arms consume the same files);
  (iii) a per-session run bundle is stamped for BOTH arms with the full §2a
        fingerprint list: config sha, model sha, calibrator sha, broker-state
        tag, strategy/pipeline/execution pin shas, data/feature manifest sha,
        this orchestrator repo's own commit, and the shared decision-snapshot
        digest (both arms verified to have consumed the SAME input world);
  (iv)  symmetric labeling/notification for both arms on a DEDICATED shadow
        ntfy topic (the live topic is rejected);
  (v)   fail-closed: any wiring or contract failure invalidates the
        session-pair in BOTH arms (paired inclusion — a clean arm paired with
        a failed arm is excluded entirely) and the runner never touches prod
        state (output root must live outside the umbrella runtime tree);
  (vi)  no umbrella runner import and no umbrella modification anywhere on
        the runner path — arms are assembled from the orchestrator's native,
        pipeline-owned chain (native-live-context → native-live-inference →
        native-live-run), which never imports umbrella ``live.runner``.

Same-world rule: both arms must resolve IDENTICAL model / calibrator /
data-manifest shas before anything runs; a mismatch aborts the session with
neither arm invoked. Config-hash drift against the experiment's
frozen-at-start hashes VOIDS the session (``SHADOW-AB VOID``) — a config
change never reinterprets the experiment, it terminates it. Any other
fingerprint drift against the freeze invalidates the session-pair (bounded
missingness, not VOID).

Broker-state tags are FROZEN by the protocol: ``alpaca_shadow_a`` (S-0.5
treatment) / ``alpaca_shadow_b`` (S-1.0 control). The legacy ``alpaca_shadow``
tag belongs to the untouched daily_104 Step-4 ops shadow and is never an
experiment arm. Until the pipeline ``ALLOWED_BROKERS`` allowlist and the
execution readonly-broker parameterization (P-1) merge, downstream state-path
resolution fails closed by design — this runner is a prerequisite, not an
armed experiment.

All external authorities (command execution, model/calibrator fingerprinting,
pin resolution, orchestrator-commit resolution, notification) are injectable
so unit tests run hermetically — the model fingerprint default delegates to
the project's ONE unified implementation in ``renquant_common`` (never a
bespoke re-hash; see the calibrator/scorer triple-impl incident history).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .native_live_context import compute_decision_snapshot_digest
from .runtime_paths import default_github_root, default_repo_root

# --- frozen protocol constants (§2a) -----------------------------------------

PROTOCOL = "D6-2a"
BUNDLE_SCHEMA_VERSION = 1

FROZEN_TAG_A = "alpaca_shadow_a"
FROZEN_TAG_B = "alpaca_shadow_b"
LEGACY_SHADOW_TAG = "alpaca_shadow"

#: the production/ops topic used by daily_104.sh — never a shadow A/B target.
LIVE_NTFY_TOPIC = "renquant"

#: §2a bundle field (v): the three pins stamped per session, per arm.
EXPERIMENT_PIN_REPOS = (
    "renquant-strategy-104",
    "renquant-pipeline",
    "renquant-execution",
)

#: Arm-symmetric preflight policy (§2a P-2 property (i)). ONE shared mapping
#: applied identically to both arms — whatever relaxation arm A gets, arm B
#: gets byte-for-byte. Never key this on the broker-state tag.
SHADOW_PREFLIGHT_ENV: dict[str, str] = {
    "RENQUANT_SUPPRESS_PREFLIGHT_NTFY": "1",
    "RENQUANT_SHADOW_PREFLIGHT_STRICT": "0",
}

FREEZE_FILENAME = "shadow_ab_freeze.json"
COUNTERS_FILENAME = "shadow_ab_counters.json"
BUNDLE_FILENAME = "shadow_ab_session_bundle.json"

VOID_MARKER = "SHADOW-AB VOID"

EXIT_VALID = 0
EXIT_PRECHECK_ABORT = 3
EXIT_SESSION_INVALIDATED = 4
EXIT_VOID = 5

#: §2a per-session bundle manifest — every arm entry must carry all of these.
SPEC_2A_ARM_FIELDS = (
    "config_sha256",              # (i)  resolved config content hash
    "model_content_sha256",       # (ii) unified model fingerprint
    "calibrator_content_sha256",  # (iii) unified calibrator fingerprint
    "broker_state_tag",           # (iv) frozen arm identity tag
    "subrepo_pins",               # (v)  strategy/pipeline/execution pin shas
    "data_manifest_sha256",       # (vi) frozen data/feature manifest sha
    "orchestrator_commit",        # (vii) invoking runner's own commit
    "decision_snapshot_digest",   # (viii) r7 point 1: shared frozen input-world digest
)

CommandRunner = Callable[[Sequence[str], Mapping[str, str]], "subprocess.CompletedProcess[str]"]
Notifier = Callable[[str, str], None]


class ShadowABContractError(RuntimeError):
    """A frozen §2a contract was violated (fail-closed, never best-effort)."""


# --- small pure helpers -------------------------------------------------------


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: str | Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _tail(text: str, *, lines: int = 40) -> list[str]:
    return (text or "").splitlines()[-lines:]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{int(time.time() * 1000)}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- validation ----------------------------------------------------------------


def validate_tags(tag_a: str, tag_b: str) -> None:
    """Enforce the FROZEN §2a broker-state tag assignment.

    The protocol froze S-0.5 → ``alpaca_shadow_a`` and S-1.0 →
    ``alpaca_shadow_b``; anything else (legacy ``alpaca_shadow``, swapped,
    equal, or novel tags) is rejected so experiment state can never collide
    with the untouched Step-4 ops shadow or mislabel an arm.
    """
    if tag_a == FROZEN_TAG_A and tag_b == FROZEN_TAG_B:
        return
    raise ValueError(
        f"frozen §2a broker-state tags are --tag-a={FROZEN_TAG_A} "
        f"--tag-b={FROZEN_TAG_B} (got --tag-a={tag_a!r} --tag-b={tag_b!r}); "
        f"the legacy {LEGACY_SHADOW_TAG!r} tag belongs to the untouched "
        "daily_104 Step-4 ops shadow and is never an experiment arm"
    )


def validate_ntfy_topic(topic: str | None) -> None:
    if topic is None:
        return
    if topic.strip().lower() == LIVE_NTFY_TOPIC:
        raise ValueError(
            "shadow A/B notifications require a DEDICATED shadow topic; the "
            f"live topic {LIVE_NTFY_TOPIC!r} is never a shadow A/B target "
            "(§2a P-2 property (iv))"
        )


def validate_output_root(output_root: Path, *, repo_root: Path) -> None:
    """The runner can never touch prod state (§2a P-2 property (v))."""
    out = Path(output_root).expanduser().resolve()
    repo = Path(repo_root).expanduser().resolve()
    if out == repo or repo in out.parents:
        raise ValueError(
            f"--output-root {out} lives inside the umbrella runtime tree "
            f"{repo}; experiment session state must live outside prod paths"
        )


def default_experiment_strategy_dir(*, github_root: str | Path | None = None) -> Path:
    """Resolve the PINNED renquant-strategy-104 config dir — NO umbrella fallback.

    Unlike :func:`renquant_orchestrator.runtime_paths.default_strategy_config_path`
    (a general migration helper that falls back to the umbrella-layout path
    while other call sites still transition), the §2a experiment path may
    NEVER depend on the umbrella checkout — that is a frozen protocol rule
    (doc/design/2026-07-09-governor-prereg-replay-protocol.md §2a: "no
    umbrella runner or call-site change is permitted for this experiment —
    not as a prerequisite, not as a separately-gated follow-up, not as a
    fallback"). Fail closed instead of silently falling back to
    ``repo_root / "backtesting" / "renquant_104"``.
    """
    github = Path(github_root) if github_root is not None else default_github_root()
    strategy_dir = github / "renquant-strategy-104" / "configs"
    if not strategy_dir.is_dir():
        raise ShadowABContractError(
            f"pinned renquant-strategy-104 configs dir not found at "
            f"{strategy_dir}; the §2a experiment path resolves strategy_dir "
            "from the pinned subrepo checkout ONLY — it never falls back to "
            "an umbrella-layout path (RFC frozen rule: umbrella is not on "
            "the experiment path)"
        )
    return strategy_dir


# --- arm model -----------------------------------------------------------------


@dataclass(frozen=True)
class ArmSpec:
    label: str  # "a" | "b"
    tag: str
    config_path: Path


@dataclass(frozen=True)
class ArmFingerprints:
    config_sha256: str
    model_content_sha256: str
    calibrator_content_sha256: str | None
    data_manifest_sha256: str


def _default_fingerprint_from_path() -> Callable[[str | Path], str]:
    """The project's ONE unified model/calibrator fingerprint authority.

    Never reimplement this hash locally: three independently hand-copied
    ``model_content_sha256`` implementations hashing different field sets is
    a recurring live incident (2026-05-27 / 06-22 / 07-01). Fail closed if
    the shared implementation is unavailable.
    """
    try:
        from renquant_common.model_fingerprint import (  # noqa: PLC0415
            model_content_sha256_from_path,
        )
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ShadowABContractError(
            "shadow A/B fingerprinting requires the unified "
            "renquant_common.model_fingerprint implementation; refusing to "
            "substitute a bespoke hash (triple-impl mismatch history)"
        ) from exc

    def _fingerprint(path: str | Path) -> str:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return model_content_sha256_from_path(path)

    return _fingerprint


def resolve_arm_fingerprints(
    config_path: str | Path,
    *,
    strategy_dir: str | Path,
    repo_root: str | Path,
    data_manifest_path: str | Path,
    fingerprint_from_path: Callable[[str | Path], str] | None = None,
) -> ArmFingerprints:
    """Resolve the §2a fingerprint set for one arm (fail-closed).

    Model/calibrator refs resolve through the single artifact-resolution
    authority (:mod:`renquant_orchestrator.artifact_resolver`) so both arms
    use the same strategy_dir-then-repo_root contract — divergent resolution
    order between two call sites is a known incident class.
    """
    from .artifact_resolver import resolve_artifact  # noqa: PLC0415

    fingerprint = fingerprint_from_path or _default_fingerprint_from_path()

    config_file = Path(config_path)
    raw = config_file.read_bytes()
    config = json.loads(raw)
    config_sha = _sha256_bytes(raw)

    panel = (
        (config.get("ranking") or {}).get("panel_scoring")
        or config.get("panel_ltr")
        or {}
    )
    model_ref = panel.get("artifact_path")
    if not model_ref:
        raise ShadowABContractError(
            f"{config_file}: no ranking.panel_scoring.artifact_path; cannot "
            "fingerprint the arm's model (same-world rule needs it)"
        )
    model = resolve_artifact(
        model_ref,
        strategy_dir=strategy_dir,
        repo_root=repo_root,
        verify_sha=False,
    )
    model_sha = fingerprint(model.path)

    calibrator_sha: str | None = None
    global_calibration = panel.get("global_calibration") or {}
    if global_calibration.get("enabled"):
        calibrator_ref = global_calibration.get("artifact_path")
        if not calibrator_ref:
            raise ShadowABContractError(
                f"{config_file}: global_calibration.enabled without an "
                "artifact_path; cannot fingerprint the arm's calibrator"
            )
        calibrator = resolve_artifact(
            calibrator_ref,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            verify_sha=False,
        )
        calibrator_sha = fingerprint(calibrator.path)

    return ArmFingerprints(
        config_sha256=config_sha,
        model_content_sha256=model_sha,
        calibrator_content_sha256=calibrator_sha,
        data_manifest_sha256=_sha256_file(data_manifest_path),
    )


def same_world_violations(fp_a: ArmFingerprints, fp_b: ArmFingerprints) -> list[str]:
    """§2a same-world rule: the arms must have scored the same world."""
    violations: list[str] = []
    if fp_a.model_content_sha256 != fp_b.model_content_sha256:
        violations.append(
            "model_content_sha256 differs across arms: "
            f"{fp_a.model_content_sha256} != {fp_b.model_content_sha256}"
        )
    if fp_a.calibrator_content_sha256 != fp_b.calibrator_content_sha256:
        violations.append(
            "calibrator_content_sha256 differs across arms: "
            f"{fp_a.calibrator_content_sha256} != {fp_b.calibrator_content_sha256}"
        )
    if fp_a.data_manifest_sha256 != fp_b.data_manifest_sha256:
        violations.append(
            "data_manifest_sha256 differs across arms: "
            f"{fp_a.data_manifest_sha256} != {fp_b.data_manifest_sha256}"
        )
    return violations


#: §2a frozen treatment key (orchestrator#443 D6 §2a, r7 point 3): the ONLY
#: functional key the two arms' configs may differ in. Distinct config file
#: PATHS are not sufficient evidence of this — the actual JSON content must
#: be diffed and the diff set asserted to be exactly this one dotted path.
FROZEN_TREATMENT_KEY = "ranking.panel_scoring.buy_floor_std_mult"

_MISSING = object()


def _flatten_config(config: Mapping[str, Any], *, prefix: str = "") -> dict[str, Any]:
    """Flatten a nested config dict to {dotted.path: leaf_value}.

    Keys (at any depth) ending in ``_reason`` are dropped — the protocol
    explicitly permits inert annotation-string deltas alongside the one
    frozen treatment key (doc/design/2026-07-09-governor-prereg-replay-
    protocol.md §2a: "a clone ... differing in exactly ONE functional key
    (plus inert `_reason` annotation strings)").
    """
    flat: dict[str, Any] = {}
    for key, value in config.items():
        if key.endswith("_reason"):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            flat.update(_flatten_config(value, prefix=path))
        else:
            flat[path] = value
    return flat


def treatment_key_violations(
    config_a: Mapping[str, Any], config_b: Mapping[str, Any]
) -> list[str]:
    """§2a treatment-isolation rule: the ONLY functional config delta allowed
    between the two arms is :data:`FROZEN_TREATMENT_KEY`.

    Mechanically diffs the two (flattened, ``_reason``-stripped) configs and
    asserts the diff set is exactly ``{FROZEN_TREATMENT_KEY}`` — catching
    both an accidental additional delta (returns a violation) and a missing
    treatment delta (arms would otherwise be identical, also a violation:
    this is not a valid A/B pair).
    """
    flat_a = _flatten_config(config_a)
    flat_b = _flatten_config(config_b)
    all_keys = set(flat_a) | set(flat_b)
    diff_keys = {k for k in all_keys if flat_a.get(k, _MISSING) != flat_b.get(k, _MISSING)}

    violations: list[str] = []
    unexpected = diff_keys - {FROZEN_TREATMENT_KEY}
    if unexpected:
        violations.append(
            "config diff includes key(s) beyond the frozen treatment key "
            f"{FROZEN_TREATMENT_KEY!r}: {sorted(unexpected)} — a later config "
            "edit introduced an untracked behavior delta"
        )
    if FROZEN_TREATMENT_KEY not in diff_keys:
        violations.append(
            "config diff does NOT include the frozen treatment key "
            f"{FROZEN_TREATMENT_KEY!r} — arms are not a valid treatment/"
            "control pair without it"
        )
    return violations


# --- pins / commit resolution ---------------------------------------------------


def resolve_experiment_pins(lock_path: str | Path) -> dict[str, str]:
    """Read the strategy/pipeline/execution pin shas from the subrepo lock."""
    lock_file = Path(lock_path)
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    by_name = {
        entry.get("name"): entry.get("commit")
        for entry in (lock.get("subrepos") or [])
        if isinstance(entry, dict)
    }
    pins: dict[str, str] = {}
    for name in EXPERIMENT_PIN_REPOS:
        commit = by_name.get(name)
        if not commit:
            raise ShadowABContractError(
                f"pin sha for {name!r} not found in {lock_file}; the §2a "
                "bundle cannot be stamped without it"
            )
        pins[name] = str(commit)
    return pins


def _default_orchestrator_commit() -> str:
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise ShadowABContractError(
            "cannot resolve the invoking orchestrator commit sha "
            f"(git rev-parse failed: {proc.stderr.strip()}); the §2a bundle "
            "cannot be stamped without it"
        )
    return proc.stdout.strip()


# --- arm plan assembly -----------------------------------------------------------


def build_arm_plan(
    *,
    tag: str,
    config_path: Path,
    arm_dir: Path,
    market_snapshot_json: Path,
    account_snapshot_json: Path,
    strategy_dir: Path,
    session_date: str,
    decision_snapshot_digest: str,
    model_content_sha256: str,
    calibrator_content_sha256: str | None,
) -> list[list[str]]:
    """Build one arm's command sequence from the SHARED template.

    The assembly is the orchestrator-native, pipeline-owned chain (no umbrella
    ``live.runner`` anywhere): hydrate a context from the arm's config plus the
    session-shared snapshots, run native inference, then build the readonly
    native run bundle with the arm's broker-state tag threaded into the
    live-state contract and the arm-isolated runs DB.

    ``decision_snapshot_digest``/``model_content_sha256``/
    ``calibrator_content_sha256`` are IDENTICAL for both arms (frozen once,
    before either arm runs — r7 point 1) and threaded into
    ``native-live-context`` so it can independently recompute and verify the
    digest against what it actually loaded, failing closed on a mismatch.
    """
    context_json = arm_dir / "native_context.json"
    inference_json = arm_dir / "native_inference.json"
    execution_json = arm_dir / "native_execution.json"
    native_bundle_json = arm_dir / "native_bundle.json"
    live_state_contract_json = arm_dir / "live_state_contract.json"
    runs_db = arm_dir / f"runs.{tag}.db"
    context_command = [
        "renquant-orchestrator", "native-live-context",
        "--strategy-config-json", str(config_path),
        "--market-snapshot-json", str(market_snapshot_json),
        "--account-snapshot-json", str(account_snapshot_json),
        "--output-json", str(context_json),
        "--decision-snapshot-digest", decision_snapshot_digest,
        "--model-content-sha256", model_content_sha256,
        "--session-date", session_date,
    ]
    if calibrator_content_sha256 is not None:
        context_command += ["--calibrator-content-sha256", calibrator_content_sha256]
    return [
        context_command,
        [
            "renquant-orchestrator", "native-live-inference",
            "--context-json", str(context_json),
            "--output-json", str(inference_json),
        ],
        [
            "renquant-orchestrator", "native-live-run",
            "--inference-json", str(inference_json),
            "--execution-output-json", str(execution_json),
            "--output-json", str(native_bundle_json),
            "--broker-name", tag,
            "--run-id", f"shadow-ab-{session_date}-{tag}",
            "--strategy-dir", str(strategy_dir),
            "--runs-db", str(runs_db),
            "--live-state-broker-name", tag,
            "--live-state-contract-output-json", str(live_state_contract_json),
        ],
    ]


def _canonical_plan(
    plan: Sequence[Sequence[str]],
    *,
    tag: str,
    config_path: Path,
    arm_dir: Path,
) -> list[list[str]]:
    """Erase the (config, tag, arm-dir) identity so arm plans can be compared."""
    canonical: list[list[str]] = []
    for command in plan:
        canonical.append([
            token
            .replace(str(arm_dir), "<ARM_DIR>")
            .replace(str(config_path), "<CONFIG>")
            .replace(tag, "<TAG>")
            for token in command
        ])
    return canonical


def assert_preflight_symmetry(
    *,
    plan_a: Sequence[Sequence[str]],
    plan_b: Sequence[Sequence[str]],
    arm_a: ArmSpec,
    arm_b: ArmSpec,
    arm_dir_a: Path,
    arm_dir_b: Path,
    env_a: Mapping[str, str],
    env_b: Mapping[str, str],
) -> None:
    """§2a P-2 property (i): arm B's invocation must equal arm A's modulo
    exactly (config, tag, arm output dir). Any other delta — an extra flag,
    a tag-keyed preflight relaxation, a differing env — is a contract
    violation and fails closed before anything runs."""
    if dict(env_a) != dict(env_b):
        raise ShadowABContractError(
            "preflight env asymmetry between arms: whatever preflight "
            "relaxation arm A gets, arm B must get identically"
        )
    canonical_a = _canonical_plan(
        plan_a, tag=arm_a.tag, config_path=arm_a.config_path, arm_dir=arm_dir_a,
    )
    canonical_b = _canonical_plan(
        plan_b, tag=arm_b.tag, config_path=arm_b.config_path, arm_dir=arm_dir_b,
    )
    if canonical_a != canonical_b:
        raise ShadowABContractError(
            "arm command asymmetry beyond (config, tag): "
            f"{canonical_a!r} != {canonical_b!r}"
        )


# --- default boundaries -----------------------------------------------------------


def _python_orchestrator_command(command: Sequence[str]) -> list[str]:
    if not command or command[0] != "renquant-orchestrator":
        raise ValueError(f"unsupported shadow A/B command: {command!r}")
    return [sys.executable, "-m", "renquant_orchestrator", *command[1:]]


def _default_command_runner(
    command: Sequence[str],
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _python_orchestrator_command(command),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(env),
    )


def _default_notifier(topic: str | None) -> Notifier:
    def _notify(title: str, body: str) -> None:
        if not topic:
            return
        try:
            from .daily_trading_health import post_ntfy  # noqa: PLC0415

            post_ntfy(title, body, topic)
        except Exception:  # noqa: BLE001 - notification is never load-bearing
            pass

    return _notify


# --- freeze / counters -----------------------------------------------------------


def _freeze_payload(
    *,
    arm_a: ArmSpec,
    arm_b: ArmSpec,
    fp_a: ArmFingerprints,
    fp_b: ArmFingerprints,
    pins: Mapping[str, str],
    orchestrator_commit: str,
) -> dict[str, Any]:
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "frozen_at": _utc_now_iso(),
        "tag_a": arm_a.tag,
        "tag_b": arm_b.tag,
        "config_sha256_a": fp_a.config_sha256,
        "config_sha256_b": fp_b.config_sha256,
        "model_content_sha256": fp_a.model_content_sha256,
        "calibrator_content_sha256": fp_a.calibrator_content_sha256,
        "data_manifest_sha256": fp_a.data_manifest_sha256,
        # Codex review on #451: a code/pin change mid-experiment must not
        # silently change the decision path while passing the other
        # frozen-world checks — freeze both identities alongside the rest.
        "subrepo_pins": dict(pins),
        "orchestrator_commit": orchestrator_commit,
    }


def _config_drift(
    freeze: Mapping[str, Any],
    fp_a: ArmFingerprints,
    fp_b: ArmFingerprints,
) -> list[str]:
    """Treatment-fingerprint drift — VOIDS the experiment immediately."""
    drift: list[str] = []
    if freeze.get("config_sha256_a") != fp_a.config_sha256:
        drift.append(
            "arm A config hash drifted from frozen-at-start: "
            f"{freeze.get('config_sha256_a')} -> {fp_a.config_sha256}"
        )
    if freeze.get("config_sha256_b") != fp_b.config_sha256:
        drift.append(
            "arm B config hash drifted from frozen-at-start: "
            f"{freeze.get('config_sha256_b')} -> {fp_b.config_sha256}"
        )
    return drift


def _frozen_world_mismatches(
    freeze: Mapping[str, Any],
    fp: ArmFingerprints,
    *,
    pins: Mapping[str, str] | None = None,
    orchestrator_commit: str | None = None,
) -> list[str]:
    """Non-config drift vs the freeze — excludes the pair (bounded missingness).

    Includes the strategy/pipeline/execution pin shas and the invoking
    orchestrator commit (Codex review on #451): these are part of the same
    "every fingerprint in both bundles matches the values frozen at
    experiment start" condition as model/calibrator/manifest — a pin or
    code change mid-experiment must not silently pass by only checking the
    config/model/calibrator/manifest subset.
    """
    mismatches: list[str] = []
    checks: list[tuple[str, Any]] = [
        ("model_content_sha256", fp.model_content_sha256),
        ("calibrator_content_sha256", fp.calibrator_content_sha256),
        ("data_manifest_sha256", fp.data_manifest_sha256),
    ]
    if pins is not None:
        checks.append(("subrepo_pins", dict(pins)))
    if orchestrator_commit is not None:
        checks.append(("orchestrator_commit", orchestrator_commit))
    for key, current in checks:
        if freeze.get(key) != current:
            mismatches.append(
                f"{key} does not match frozen-at-start value: "
                f"{freeze.get(key)} -> {current}"
            )
    return mismatches


def _update_counters(output_root: Path, *, excluded: bool) -> dict[str, int]:
    counters_path = output_root / COUNTERS_FILENAME
    counters = {"attempted_pairs": 0, "excluded_pairs": 0}
    if counters_path.exists():
        loaded = json.loads(counters_path.read_text(encoding="utf-8"))
        counters["attempted_pairs"] = int(loaded.get("attempted_pairs", 0))
        counters["excluded_pairs"] = int(loaded.get("excluded_pairs", 0))
    counters["attempted_pairs"] += 1
    if excluded:
        counters["excluded_pairs"] += 1
    _write_json_atomic(counters_path, counters)
    return counters


# --- session runner ---------------------------------------------------------------


def _arm_entry(
    arm: ArmSpec,
    fp: ArmFingerprints | None,
    *,
    pins: Mapping[str, str] | None,
    orchestrator_commit: str | None,
    decision_snapshot_digest: str | None = None,
) -> dict[str, Any]:
    return {
        "arm": arm.label,
        "broker_state_tag": arm.tag,
        "config_path": str(arm.config_path),
        "config_sha256": fp.config_sha256 if fp else None,
        "model_content_sha256": fp.model_content_sha256 if fp else None,
        "calibrator_content_sha256": fp.calibrator_content_sha256 if fp else None,
        "subrepo_pins": dict(pins) if pins else None,
        "data_manifest_sha256": fp.data_manifest_sha256 if fp else None,
        "orchestrator_commit": orchestrator_commit,
        "decision_snapshot_digest": decision_snapshot_digest,
        "completed": False,
        "invalidated": True,
        "invalidation_reasons": [],
        "steps": [],
    }


def _run_steps(
    plan: Sequence[Sequence[str]],
    *,
    run: CommandRunner,
    env: Mapping[str, str],
) -> tuple[list[dict[str, Any]], bool]:
    steps: list[dict[str, Any]] = []
    ok = True
    for command in plan:
        started = time.time()
        proc = run(command, env)
        steps.append({
            "command": list(command),
            "returncode": proc.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "stdout_tail": _tail(proc.stdout or ""),
            "stderr_tail": _tail(proc.stderr or ""),
            "ok": proc.returncode == 0,
        })
        if proc.returncode != 0:
            ok = False
            break
    return steps, ok


def run_shadow_ab_session(
    *,
    config_a: str | Path,
    config_b: str | Path,
    tag_a: str = FROZEN_TAG_A,
    tag_b: str = FROZEN_TAG_B,
    data_manifest: str | Path,
    output_root: str | Path,
    market_snapshot_json: str | Path,
    account_snapshot_json: str | Path | None = None,
    session_date: str | None = None,
    repo_root: str | Path | None = None,
    strategy_dir: str | Path | None = None,
    snapshot_broker_name: str = "readonly-alpaca",
    ntfy_topic: str | None = None,
    plan_only: bool = False,
    command_runner: CommandRunner | None = None,
    fingerprint_from_path: Callable[[str | Path], str] | None = None,
    pins_resolver: Callable[[], Mapping[str, str]] | None = None,
    orchestrator_commit_resolver: Callable[[], str] | None = None,
    notifier: Notifier | None = None,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run (or plan) one paired two-arm shadow session; returns the payload.

    The returned payload always carries ``exit_code`` (see the EXIT_*
    constants) and, for non-plan runs, ``bundle_path``.
    """
    repo_root = Path(repo_root or default_repo_root())
    strategy_dir = Path(strategy_dir) if strategy_dir else default_experiment_strategy_dir()
    output_root = Path(output_root)
    session_date = session_date or dt.date.today().isoformat()

    validate_tags(tag_a, tag_b)
    validate_ntfy_topic(ntfy_topic)
    validate_output_root(output_root, repo_root=repo_root)

    config_a = Path(config_a)
    config_b = Path(config_b)
    if config_a.resolve() == config_b.resolve():
        raise ValueError(
            "arms must resolve DISTINCT configs (one frozen treatment key "
            f"apart); both arms got {config_a}"
        )

    arm_a = ArmSpec(label="a", tag=tag_a, config_path=config_a)
    arm_b = ArmSpec(label="b", tag=tag_b, config_path=config_b)
    session_dir = output_root / session_date
    bundle_path = session_dir / BUNDLE_FILENAME
    notify = notifier or _default_notifier(ntfy_topic)
    run = command_runner or _default_command_runner
    resolve_pins = pins_resolver or (
        lambda: resolve_experiment_pins(repo_root / "subrepos.lock.json")
    )
    resolve_commit = orchestrator_commit_resolver or _default_orchestrator_commit

    # One shared env template for BOTH arms (property (i)).
    env: dict[str, str] = dict(base_env if base_env is not None else os.environ)
    env.update(SHADOW_PREFLIGHT_ENV)

    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "session_date": session_date,
        "status": "invalidated",
        "void": False,
        "reasons": [],
        "preflight_env": dict(SHADOW_PREFLIGHT_ENV),
        "freeze_path": str(output_root / FREEZE_FILENAME),
        "freeze_created": False,
        "shared_steps": [],
        "arms": {
            "a": _arm_entry(
                arm_a, None, pins=None, orchestrator_commit=None,
                decision_snapshot_digest=None,
            ),
            "b": _arm_entry(
                arm_b, None, pins=None, orchestrator_commit=None,
                decision_snapshot_digest=None,
            ),
        },
    }

    def _finish(exit_code: int, status: str) -> dict[str, Any]:
        bundle["status"] = status
        bundle["exit_code"] = exit_code
        if not plan_only:
            excluded = status != "valid"
            bundle["counters"] = _update_counters(output_root, excluded=excluded)
            attempted = bundle["counters"]["attempted_pairs"]
            bundle["counters"]["excluded_fraction"] = (
                round(bundle["counters"]["excluded_pairs"] / attempted, 4)
                if attempted else 0.0
            )
            _write_json_atomic(bundle_path, bundle)
            bundle["bundle_path"] = str(bundle_path)
            for label, arm in (("a", arm_a), ("b", arm_b)):
                notify(
                    f"[SHADOW-AB {label}:{arm.tag}] {session_date} {status}",
                    "; ".join(bundle["reasons"]) or status,
                )
        return bundle

    # -- prechecks: resolve every §2a bundle field BEFORE anything runs -------
    try:
        fp_a = resolve_arm_fingerprints(
            config_a,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            data_manifest_path=data_manifest,
            fingerprint_from_path=fingerprint_from_path,
        )
        fp_b = resolve_arm_fingerprints(
            config_b,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            data_manifest_path=data_manifest,
            fingerprint_from_path=fingerprint_from_path,
        )
        pins = dict(resolve_pins())
        missing_pins = [name for name in EXPERIMENT_PIN_REPOS if not pins.get(name)]
        if missing_pins:
            raise ShadowABContractError(
                f"pin resolver returned no sha for: {', '.join(missing_pins)}"
            )
        orchestrator_commit = resolve_commit()
    except (ShadowABContractError, OSError, ValueError, KeyError) as exc:
        bundle["reasons"].append(f"precheck_failure: {exc}")
        for entry in bundle["arms"].values():
            entry["invalidation_reasons"].append("paired_invalidation: precheck failed")
        return _finish(EXIT_PRECHECK_ABORT, "invalidated")

    bundle["arms"]["a"] = _arm_entry(
        arm_a, fp_a, pins=pins, orchestrator_commit=orchestrator_commit,
    )
    bundle["arms"]["b"] = _arm_entry(
        arm_b, fp_b, pins=pins, orchestrator_commit=orchestrator_commit,
    )

    # -- same-world rule (across arms, before running) -------------------------
    violations = same_world_violations(fp_a, fp_b)
    if violations:
        bundle["reasons"].extend(f"same_world_violation: {v}" for v in violations)
        for entry in bundle["arms"].values():
            entry["invalidation_reasons"].append(
                "paired_invalidation: same-world rule violated; neither arm ran"
            )
        return _finish(EXIT_PRECHECK_ABORT, "invalidated")

    # -- treatment-key isolation (the ONLY functional config delta allowed) -----
    treatment_violations = treatment_key_violations(
        json.loads(config_a.read_bytes()), json.loads(config_b.read_bytes()),
    )
    if treatment_violations:
        bundle["reasons"].extend(
            f"treatment_key_violation: {v}" for v in treatment_violations
        )
        for entry in bundle["arms"].values():
            entry["invalidation_reasons"].append(
                "paired_invalidation: treatment-key isolation violated; "
                "neither arm ran"
            )
        return _finish(EXIT_PRECHECK_ABORT, "invalidated")

    # -- frozen-at-start fingerprints: drift => VOID, mismatch => excluded ------
    freeze_path = output_root / FREEZE_FILENAME
    if freeze_path.exists():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        drift = _config_drift(freeze, fp_a, fp_b)
        if drift:
            bundle["void"] = True
            bundle["void_marker"] = VOID_MARKER
            bundle["reasons"].extend(f"config_hash_drift: {d}" for d in drift)
            for entry in bundle["arms"].values():
                entry["invalidation_reasons"].append(
                    "paired_invalidation: treatment config hash drifted; "
                    "experiment VOID under this protocol version"
                )
            return _finish(EXIT_VOID, "void")
        world_mismatches = _frozen_world_mismatches(
            freeze, fp_a, pins=pins, orchestrator_commit=orchestrator_commit,
        )
        if world_mismatches:
            bundle["reasons"].extend(
                f"frozen_fingerprint_mismatch: {m}" for m in world_mismatches
            )
            for entry in bundle["arms"].values():
                entry["invalidation_reasons"].append(
                    "paired_invalidation: session world does not match the "
                    "experiment's frozen-at-start fingerprints"
                )
            return _finish(EXIT_PRECHECK_ABORT, "invalidated")
    elif not plan_only:
        _write_json_atomic(
            freeze_path,
            _freeze_payload(
                arm_a=arm_a, arm_b=arm_b, fp_a=fp_a, fp_b=fp_b,
                pins=pins, orchestrator_commit=orchestrator_commit,
            ),
        )
        bundle["freeze_created"] = True

    # -- shared session inputs (both arms consume the SAME files) ---------------
    session_dir_a = session_dir / f"arm_{arm_a.tag}"
    session_dir_b = session_dir / f"arm_{arm_b.tag}"
    shared_steps: list[list[str]] = []
    if account_snapshot_json is None:
        account_snapshot_json = session_dir / "account_snapshot.json"
        shared_steps.append([
            "renquant-orchestrator", "native-live-account-snapshot",
            "--broker-name", snapshot_broker_name,
            "--output-json", str(account_snapshot_json),
        ])
    account_snapshot_json = Path(account_snapshot_json)
    market_snapshot_json = Path(market_snapshot_json)

    # -- the shared decision snapshot (r7 point 1): ONE digest, computed once
    # before either arm runs, handed to BOTH — never independently resolved
    # by each arm at its own invocation time. ------------------------------
    decision_snapshot_digest = compute_decision_snapshot_digest(
        market_snapshot=json.loads(market_snapshot_json.read_bytes()),
        model_content_sha256=fp_a.model_content_sha256,
        calibrator_content_sha256=fp_a.calibrator_content_sha256,
        session_date=session_date,
    )
    bundle["arms"]["a"]["decision_snapshot_digest"] = decision_snapshot_digest
    bundle["arms"]["b"]["decision_snapshot_digest"] = decision_snapshot_digest

    plan_a = build_arm_plan(
        tag=arm_a.tag,
        config_path=arm_a.config_path,
        arm_dir=session_dir_a,
        market_snapshot_json=market_snapshot_json,
        account_snapshot_json=account_snapshot_json,
        strategy_dir=strategy_dir,
        session_date=session_date,
        decision_snapshot_digest=decision_snapshot_digest,
        model_content_sha256=fp_a.model_content_sha256,
        calibrator_content_sha256=fp_a.calibrator_content_sha256,
    )
    plan_b = build_arm_plan(
        tag=arm_b.tag,
        config_path=arm_b.config_path,
        arm_dir=session_dir_b,
        market_snapshot_json=market_snapshot_json,
        account_snapshot_json=account_snapshot_json,
        strategy_dir=strategy_dir,
        session_date=session_date,
        decision_snapshot_digest=decision_snapshot_digest,
        model_content_sha256=fp_a.model_content_sha256,
        calibrator_content_sha256=fp_a.calibrator_content_sha256,
    )
    try:
        assert_preflight_symmetry(
            plan_a=plan_a,
            plan_b=plan_b,
            arm_a=arm_a,
            arm_b=arm_b,
            arm_dir_a=session_dir_a,
            arm_dir_b=session_dir_b,
            env_a=env,
            env_b=env,
        )
    except ShadowABContractError as exc:
        bundle["reasons"].append(f"preflight_symmetry_violation: {exc}")
        for entry in bundle["arms"].values():
            entry["invalidation_reasons"].append(
                "paired_invalidation: preflight symmetry violated; neither arm ran"
            )
        return _finish(EXIT_PRECHECK_ABORT, "invalidated")

    bundle["arms"]["a"]["planned_commands"] = [list(c) for c in plan_a]
    bundle["arms"]["b"]["planned_commands"] = [list(c) for c in plan_b]
    bundle["shared_planned_commands"] = [list(c) for c in shared_steps]

    if plan_only:
        bundle["status"] = "plan_only"
        bundle["exit_code"] = EXIT_VALID
        return bundle

    session_dir_a.mkdir(parents=True, exist_ok=True)
    session_dir_b.mkdir(parents=True, exist_ok=True)

    # -- shared inputs, then arms SEQUENTIALLY (never concurrently) --------------
    shared_ok = True
    if shared_steps:
        steps, shared_ok = _run_steps(shared_steps, run=run, env=env)
        bundle["shared_steps"] = steps
        if not shared_ok:
            bundle["reasons"].append("shared_input_failure: session input step failed")
            for entry in bundle["arms"].values():
                entry["invalidation_reasons"].append(
                    "paired_invalidation: shared session inputs failed; neither arm ran"
                )
            return _finish(EXIT_SESSION_INVALIDATED, "invalidated")

    arm_ok: dict[str, bool] = {}
    for label, plan in (("a", plan_a), ("b", plan_b)):
        steps, ok = _run_steps(plan, run=run, env=env)
        bundle["arms"][label]["steps"] = steps
        bundle["arms"][label]["completed"] = ok
        arm_ok[label] = ok

    failed = sorted(label for label, ok in arm_ok.items() if not ok)
    if failed:
        # Either-arm failure invalidates the session-pair in BOTH arms.
        bundle["reasons"].append(
            f"arm_failure: arm(s) {', '.join(failed)} failed; paired inclusion "
            "excludes this session in BOTH arms"
        )
        for label in ("a", "b"):
            bundle["arms"][label]["invalidated"] = True
            bundle["arms"][label]["invalidation_reasons"].append(
                f"paired_invalidation: arm(s) {', '.join(failed)} failed this session"
            )
        return _finish(EXIT_SESSION_INVALIDATED, "invalidated")

    for label in ("a", "b"):
        bundle["arms"][label]["invalidated"] = False
    return _finish(EXIT_VALID, "valid")


# --- CLI --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="renquant-orchestrator shadow-ab",
        description=(
            "two-arm shadow A/B session runner (D6-§2a P-2). UNINVOKED "
            "prerequisite: no schedule installs this; arming is a later "
            "gated step."
        ),
    )
    parser.add_argument("--config-a", required=True, help="arm A (S-0.5 treatment) strategy config path")
    parser.add_argument("--config-b", required=True, help="arm B (S-1.0 control) strategy config path")
    parser.add_argument("--tag-a", default=FROZEN_TAG_A, help=f"frozen broker-state tag for arm A ({FROZEN_TAG_A})")
    parser.add_argument("--tag-b", default=FROZEN_TAG_B, help=f"frozen broker-state tag for arm B ({FROZEN_TAG_B})")
    parser.add_argument(
        "--data-manifest", required=True,
        help="frozen data/feature manifest used by this session's scoring pass",
    )
    parser.add_argument(
        "--output-root", required=True,
        help="experiment session root (freeze, counters, per-session bundles); must be outside the umbrella tree",
    )
    parser.add_argument(
        "--market-snapshot-json", required=True,
        help="session-shared market snapshot consumed by BOTH arms",
    )
    parser.add_argument(
        "--account-snapshot-json", default=None,
        help="session-shared account snapshot; when omitted a single shared readonly fetch step is planned",
    )
    parser.add_argument("--session-date", default=None, help="ISO session date (default: today)")
    parser.add_argument("--repo-root", default=None, help="umbrella runtime root (pins lock; default: resolver)")
    parser.add_argument(
        "--strategy-dir", default=None,
        help=(
            "strategy dir for artifact/state resolution; default resolves "
            "the PINNED renquant-strategy-104/configs dir ONLY, never an "
            "umbrella-layout fallback (RFC frozen rule)"
        ),
    )
    parser.add_argument("--snapshot-broker-name", default="readonly-alpaca")
    parser.add_argument(
        "--ntfy-topic", default=None,
        help="DEDICATED shadow topic for symmetric arm notifications (live topic rejected)",
    )
    parser.add_argument(
        "--plan-only", action="store_true",
        help="resolve fingerprints + prechecks and print the symmetric plan without invoking anything",
    )
    args = parser.parse_args(argv)

    try:
        payload = run_shadow_ab_session(
            config_a=args.config_a,
            config_b=args.config_b,
            tag_a=args.tag_a,
            tag_b=args.tag_b,
            data_manifest=args.data_manifest,
            output_root=args.output_root,
            market_snapshot_json=args.market_snapshot_json,
            account_snapshot_json=args.account_snapshot_json,
            session_date=args.session_date,
            repo_root=args.repo_root,
            strategy_dir=args.strategy_dir,
            snapshot_broker_name=args.snapshot_broker_name,
            ntfy_topic=args.ntfy_topic,
            plan_only=args.plan_only,
        )
    except (ValueError, ShadowABContractError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2, sort_keys=True))
    if payload.get("void"):
        print(f"{VOID_MARKER}: {'; '.join(payload.get('reasons') or [])}", file=sys.stderr)
    return int(payload["exit_code"])


__all__ = [
    "EXIT_PRECHECK_ABORT",
    "EXIT_SESSION_INVALIDATED",
    "EXIT_VALID",
    "EXIT_VOID",
    "EXPERIMENT_PIN_REPOS",
    "FROZEN_TAG_A",
    "FROZEN_TAG_B",
    "FROZEN_TREATMENT_KEY",
    "LEGACY_SHADOW_TAG",
    "SHADOW_PREFLIGHT_ENV",
    "SPEC_2A_ARM_FIELDS",
    "VOID_MARKER",
    "ArmFingerprints",
    "ArmSpec",
    "ShadowABContractError",
    "assert_preflight_symmetry",
    "build_arm_plan",
    "default_experiment_strategy_dir",
    "main",
    "resolve_arm_fingerprints",
    "resolve_experiment_pins",
    "run_shadow_ab_session",
    "same_world_violations",
    "treatment_key_violations",
    "validate_ntfy_topic",
    "validate_output_root",
    "validate_tags",
]


if __name__ == "__main__":
    raise SystemExit(main())
