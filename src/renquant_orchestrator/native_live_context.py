"""Native live context fixture builder for offboard rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


NATIVE_CONTEXT_PRODUCER = "renquant_orchestrator.native_live_context"

#: Fixed marker for the §2a decision-snapshot's "starting portfolio-state
#: convention" component (orchestrator#443 D6 §2a, r7 point 1): the RULE is
#: frozen and shared across arms, but each arm's own prior-EOD account state
#: is deliberately NOT part of this digest (it must differ between arms by
#: design). Changing this string changes every future digest — do not touch
#: without updating the design doc.
STARTING_STATE_CONVENTION = "each_arm_reads_its_own_prior_eod_close_not_shared"


def canonical_json_sha256(payload: Any) -> str:
    """Canonical (sorted-keys, compact) JSON content hash.

    This is the ONE content-hash convention used for sealing/verifying the
    §2a shared session inputs — file formatting (indentation, key order,
    trailing newline) never changes the hash, only semantic content does.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def market_snapshot_identity(market_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract the as-of / universe / corporate-action identity components
    the §2a decision digest must cover explicitly (orchestrator#443, Codex
    r8 review): they are named digest inputs, not merely implied by hashing
    the whole snapshot, so a snapshot schema change can never silently drop
    them from coverage."""
    as_of = market_snapshot.get("as_of")
    if not as_of:
        raise ValueError(
            "market snapshot has no 'as_of'; the §2a decision digest "
            "requires the as-of identity (fail-closed)"
        )
    prices = market_snapshot.get("prices")
    universe = sorted(prices) if isinstance(prices, dict) else []
    corporate_actions = market_snapshot.get("corporate_actions")
    corporate_action_identity = (
        canonical_json_sha256(corporate_actions)
        if corporate_actions is not None
        else "none_declared"
    )
    return {
        "as_of": str(as_of),
        "universe": universe,
        "corporate_action_identity": corporate_action_identity,
    }


def compute_decision_snapshot_digest(
    *,
    market_snapshot_sha256: str,
    account_snapshot_sha256: str,
    as_of: str,
    session_date: str,
    universe: Sequence[str],
    corporate_action_identity: str,
    model_content_sha256: str,
    calibrator_content_sha256: str | None,
) -> str:
    """The §2a decision-snapshot digest (orchestrator#443 D6 §2a; r8 dual-hash).

    Covers, per the frozen design: the canonical content hashes of BOTH
    sealed session inputs (market snapshot AND account snapshot — r8: an
    account-only difference must change the digest), the as-of timestamp,
    the session identifier, the candidate universe, the corporate-action
    identity, the model/calibrator artifact identity, and the
    starting-state-convention RULE marker (``STARTING_STATE_CONVENTION``).

    Both arms must be handed the IDENTICAL digest computed from the SAME
    sealed inputs before either runs; each arm's actual consumption is then
    independently re-hashed via this SAME function and compared (see
    ``decision_snapshot_identity`` + ``build_native_live_context``) — never
    reimplemented at the call sites, to avoid exactly the kind of
    hand-copied-hash drift this project has hit before with
    ``model_content_sha256``.
    """
    canonical = json.dumps(
        {
            "digest_schema_version": 2,
            "market_snapshot_sha256": market_snapshot_sha256,
            "account_snapshot_sha256": account_snapshot_sha256,
            "as_of": as_of,
            "session_date": session_date,
            "universe": sorted(universe),
            "corporate_action_identity": corporate_action_identity,
            "model_content_sha256": model_content_sha256,
            "calibrator_content_sha256": calibrator_content_sha256,
            "starting_state_convention": STARTING_STATE_CONVENTION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def decision_snapshot_identity(
    *,
    market_snapshot_json: str | Path,
    account_snapshot_json: str | Path,
    session_date: str,
    model_content_sha256: str,
    calibrator_content_sha256: str | None,
) -> dict[str, Any]:
    """Load BOTH session-input files fresh and compute the full §2a
    decision-snapshot identity block (component hashes + digest).

    This is the single implementation used by the producing side (the
    two-arm runner, over the files it seals) AND the consuming side
    (``build_native_live_context``, over the files it actually loads) —
    the r8 "independently recompute from both sealed files" requirement is
    met by re-reading the files at each call, never by trusting a cached
    in-memory value.
    """
    market_snapshot = _load_json_object(market_snapshot_json)
    account_snapshot = _load_json_object(account_snapshot_json)
    market_sha = canonical_json_sha256(market_snapshot)
    account_sha = canonical_json_sha256(account_snapshot)
    identity = market_snapshot_identity(market_snapshot)
    digest = compute_decision_snapshot_digest(
        market_snapshot_sha256=market_sha,
        account_snapshot_sha256=account_sha,
        as_of=identity["as_of"],
        session_date=session_date,
        universe=identity["universe"],
        corporate_action_identity=identity["corporate_action_identity"],
        model_content_sha256=model_content_sha256,
        calibrator_content_sha256=calibrator_content_sha256,
    )
    return {
        "digest": digest,
        "market_snapshot_sha256": market_sha,
        "account_snapshot_sha256": account_sha,
        "as_of": identity["as_of"],
        "universe_size": len(identity["universe"]),
        "corporate_action_identity": identity["corporate_action_identity"],
        "model_content_sha256": model_content_sha256,
        "calibrator_content_sha256": calibrator_content_sha256,
        "session_date": session_date,
        "starting_state_convention": STARTING_STATE_CONVENTION,
    }


class DecisionSnapshotMismatchError(ValueError):
    """An arm's actually-consumed inputs don't match the frozen decision snapshot."""


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_model_fingerprint_from_path() -> "Callable[[str | Path], str]":
    """The project's ONE unified model/calibrator fingerprint authority.

    Never reimplement this hash locally: three independently hand-copied
    ``model_content_sha256`` implementations hashing different field sets is
    a recurring live incident (2026-05-27 / 06-22 / 07-01). This is the
    SINGLE plumbing wrapper — ``shadow_ab_runner`` (the producing side) and
    this module (the consuming side) both use it. Fails closed if the shared
    implementation is unavailable.
    """
    try:
        from renquant_common.model_fingerprint import (  # noqa: PLC0415
            model_content_sha256_from_path,
        )
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "paired-world fingerprinting requires the unified "
            "renquant_common.model_fingerprint implementation; refusing to "
            "substitute a bespoke hash (triple-impl mismatch history)"
        ) from exc

    import warnings  # noqa: PLC0415

    def _fingerprint(path: str | Path) -> str:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return model_content_sha256_from_path(path)

    return _fingerprint


def panel_artifact_refs(config: dict[str, Any]) -> tuple[str, str | None]:
    """Extract the (model ref, calibrator ref or None) a strategy config's
    active panel-scoring section declares. Single shared extraction — the
    two-arm runner's precheck and this module's consumption-side check must
    read the SAME keys or the verification proves nothing.

    Raises ``ValueError`` when the config declares no model artifact, or an
    enabled calibration without an artifact path (fail-closed).
    """
    panel = (
        (config.get("ranking") or {}).get("panel_scoring")
        or config.get("panel_ltr")
        or {}
    )
    model_ref = panel.get("artifact_path")
    if not model_ref:
        raise ValueError(
            "config has no ranking.panel_scoring.artifact_path; cannot "
            "identify the model artifact (paired-world rule needs it)"
        )
    calibrator_ref: str | None = None
    global_calibration = panel.get("global_calibration") or {}
    if global_calibration.get("enabled"):
        calibrator_ref = global_calibration.get("artifact_path")
        if not calibrator_ref:
            raise ValueError(
                "config enables global_calibration without an artifact_path; "
                "cannot identify the calibrator artifact"
            )
    return str(model_ref), calibrator_ref


def verify_config_artifact_shas(
    *,
    strategy_config_json: str | Path,
    config: dict[str, Any],
    model_content_sha256: str,
    calibrator_content_sha256: str | None,
    strategy_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    fingerprint_from_path: "Callable[[str | Path], str] | None" = None,
) -> dict[str, Any]:
    """Verify the handed-in model/calibrator shas against the artifacts this
    context ACTUALLY resolves from the strategy config it loaded.

    Resolution goes through the single artifact-resolution authority
    (:mod:`renquant_orchestrator.artifact_resolver`), anchored at the SAME
    (``strategy_dir``, ``repo_root``) pair the producing runner used — the
    two-arm runner threads its own anchors into this call precisely so both
    sides resolve identically (divergent resolution order between two call
    sites is the incident class ``artifact_resolver`` exists to kill). When
    the anchors are not handed in, they default to the config file's own
    parent directory and the default repo root. ANY inconsistency —
    unresolvable ref, sha mismatch, calibrator declared-but-not-handed-in or
    handed-in-but-not-declared — raises ``DecisionSnapshotMismatchError``
    (fail-closed; the arm's nonzero exit is what triggers the runner's
    both-arms invalidation).
    """
    from .artifact_resolver import resolve_artifact  # noqa: PLC0415
    from .runtime_paths import default_repo_root  # noqa: PLC0415

    fingerprint = fingerprint_from_path or default_model_fingerprint_from_path()
    strategy_dir = (
        Path(strategy_dir) if strategy_dir is not None
        else Path(strategy_config_json).resolve().parent
    )
    repo_root = Path(repo_root) if repo_root is not None else default_repo_root()

    try:
        model_ref, calibrator_ref = panel_artifact_refs(config)
    except ValueError as exc:
        raise DecisionSnapshotMismatchError(
            f"paired-world artifact check failed: {exc}"
        ) from exc

    def _resolved_sha(ref: str, kind: str) -> str:
        try:
            resolved = resolve_artifact(
                ref,
                strategy_dir=strategy_dir,
                repo_root=repo_root,
                verify_sha=False,
            )
        except FileNotFoundError as exc:
            raise DecisionSnapshotMismatchError(
                f"paired-world artifact check failed: {kind} artifact "
                f"unresolvable from this context's anchors: {exc}"
            ) from exc
        return fingerprint(resolved.path)

    actual_model_sha = _resolved_sha(model_ref, "model")
    if actual_model_sha != model_content_sha256:
        raise DecisionSnapshotMismatchError(
            "paired-world model sha mismatch: the config's resolved model "
            f"artifact fingerprints to {actual_model_sha}, but "
            f"{model_content_sha256} was frozen before either arm ran"
        )

    actual_calibrator_sha: str | None = None
    if calibrator_ref is None and calibrator_content_sha256 is not None:
        raise DecisionSnapshotMismatchError(
            "paired-world calibrator mismatch: a calibrator sha was frozen "
            "but this config declares no enabled calibrator"
        )
    if calibrator_ref is not None:
        if calibrator_content_sha256 is None:
            raise DecisionSnapshotMismatchError(
                "paired-world calibrator mismatch: this config declares an "
                "enabled calibrator but no calibrator sha was frozen"
            )
        actual_calibrator_sha = _resolved_sha(calibrator_ref, "calibrator")
        if actual_calibrator_sha != calibrator_content_sha256:
            raise DecisionSnapshotMismatchError(
                "paired-world calibrator sha mismatch: the config's resolved "
                f"calibrator artifact fingerprints to {actual_calibrator_sha}, "
                f"but {calibrator_content_sha256} was frozen before either "
                "arm ran"
            )

    return {
        "model_content_sha256": actual_model_sha,
        "calibrator_content_sha256": actual_calibrator_sha,
    }


def build_native_live_context(
    *,
    strategy_config_json: str | Path,
    market_snapshot_json: str | Path,
    account_snapshot_json: str | Path,
    output_json: str | Path,
    metadata_json: str | Path | None = None,
    decision_snapshot_digest: str | None = None,
    model_content_sha256: str | None = None,
    calibrator_content_sha256: str | None = None,
    session_date: str | None = None,
    strategy_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    fingerprint_from_path: Callable[[str | Path], str] | None = None,
) -> dict[str, Any]:
    """Build an already-hydrated native context JSON for inference rehearsal.

    When ``decision_snapshot_digest`` is given (the §2a shadow A/B path),
    this independently VERIFIES the paired world this arm actually consumes
    (``model_content_sha256``/``session_date`` are then required too):

    * the digest is RECOMPUTED from BOTH files this call consumes — the
      sealed market snapshot AND the sealed account snapshot are re-read
      and re-hashed via ``decision_snapshot_identity`` — and compared to
      the expected value handed in;
    * the handed-in model/calibrator shas are verified against the
      artifacts this context ACTUALLY resolves from the strategy config it
      loaded (``verify_config_artifact_shas``).

    Any mismatch raises ``DecisionSnapshotMismatchError``: the
    consumption-side half of the frozen decision-snapshot contract
    (orchestrator#443 D6 §2a; r8 dual-hash). That failure exits this arm's
    context step nonzero, and the two-arm runner's paired inclusion rule
    then invalidates BOTH arms. Callers outside that path simply omit these
    arguments and get the unchanged pre-existing behavior.
    """
    metadata = _load_json_object(metadata_json) if metadata_json else {}
    market_snapshot = _load_json_object(market_snapshot_json)
    config = _load_json_object(strategy_config_json)

    decision_snapshot_meta: dict[str, Any] = {}
    if decision_snapshot_digest is not None:
        if model_content_sha256 is None or session_date is None:
            raise ValueError(
                "decision_snapshot_digest requires model_content_sha256 and "
                "session_date to independently recompute and verify it"
            )
        try:
            identity = decision_snapshot_identity(
                market_snapshot_json=market_snapshot_json,
                account_snapshot_json=account_snapshot_json,
                session_date=session_date,
                model_content_sha256=model_content_sha256,
                calibrator_content_sha256=calibrator_content_sha256,
            )
        except DecisionSnapshotMismatchError:
            raise
        except (OSError, ValueError) as exc:
            raise DecisionSnapshotMismatchError(
                f"paired-world inputs unreadable or invalid: {exc}"
            ) from exc
        if identity["digest"] != decision_snapshot_digest:
            raise DecisionSnapshotMismatchError(
                "decision-snapshot digest mismatch: this arm's actually-"
                f"consumed inputs (market sha {identity['market_snapshot_sha256']}, "
                f"account sha {identity['account_snapshot_sha256']}) hash to "
                f"{identity['digest']}, expected {decision_snapshot_digest} "
                "(frozen before either arm ran); refusing to proceed on a "
                "different-from-frozen input world"
            )
        verify_config_artifact_shas(
            strategy_config_json=strategy_config_json,
            config=config,
            model_content_sha256=model_content_sha256,
            calibrator_content_sha256=calibrator_content_sha256,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            fingerprint_from_path=fingerprint_from_path,
        )
        decision_snapshot_meta = {
            "decision_snapshot_digest": identity["digest"],
            "decision_snapshot_verified": True,
            "market_snapshot_sha256": identity["market_snapshot_sha256"],
            "account_snapshot_sha256": identity["account_snapshot_sha256"],
            "config_artifact_shas_verified": True,
        }

    payload = {
        "schema_version": 1,
        "source": "native_live_context_fixture",
        "config": config,
        "market_snapshot": market_snapshot,
        "account_snapshot": _load_json_object(account_snapshot_json),
        "metadata": {
            **metadata,
            "native_context_producer": {
                "source": NATIVE_CONTEXT_PRODUCER,
                "strategy_config_json": str(strategy_config_json),
                "market_snapshot_json": str(market_snapshot_json),
                "account_snapshot_json": str(account_snapshot_json),
            },
            **decision_snapshot_meta,
        },
    }
    _write_json(output_json, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-context")
    parser.add_argument("--strategy-config-json", required=True)
    parser.add_argument("--market-snapshot-json", required=True)
    parser.add_argument("--account-snapshot-json", required=True)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--decision-snapshot-digest", default=None)
    parser.add_argument("--model-content-sha256", default=None)
    parser.add_argument("--calibrator-content-sha256", default=None)
    parser.add_argument("--session-date", default=None)
    parser.add_argument("--strategy-dir", default=None)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    try:
        payload = build_native_live_context(
            strategy_config_json=args.strategy_config_json,
            market_snapshot_json=args.market_snapshot_json,
            account_snapshot_json=args.account_snapshot_json,
            metadata_json=args.metadata_json,
            output_json=args.output_json,
            decision_snapshot_digest=args.decision_snapshot_digest,
            model_content_sha256=args.model_content_sha256,
            calibrator_content_sha256=args.calibrator_content_sha256,
            session_date=args.session_date,
            strategy_dir=args.strategy_dir,
            repo_root=args.repo_root,
        )
    except DecisionSnapshotMismatchError as exc:
        # Nonzero with an unambiguous marker: this exit is what triggers the
        # two-arm runner's both-arms (paired) invalidation.
        print(f"PAIRED-WORLD MISMATCH: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "NATIVE_CONTEXT_PRODUCER",
    "STARTING_STATE_CONVENTION",
    "DecisionSnapshotMismatchError",
    "build_native_live_context",
    "canonical_json_sha256",
    "compute_decision_snapshot_digest",
    "decision_snapshot_identity",
    "default_model_fingerprint_from_path",
    "main",
    "market_snapshot_identity",
    "panel_artifact_refs",
    "verify_config_artifact_shas",
]


if __name__ == "__main__":
    raise SystemExit(main())
