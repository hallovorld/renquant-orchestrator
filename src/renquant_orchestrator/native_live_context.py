"""Native live context fixture builder for offboard rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
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
) -> dict[str, Any]:
    """Build an already-hydrated native context JSON for inference rehearsal.

    When ``decision_snapshot_digest`` is given (the §2a shadow A/B path),
    this independently RECOMPUTES the digest from BOTH files this call
    actually consumes — the sealed market snapshot AND the sealed account
    snapshot are re-read and re-hashed via ``decision_snapshot_identity``
    (``model_content_sha256``/``session_date`` are then required too) — and
    raises ``DecisionSnapshotMismatchError`` if it doesn't match the
    expected value handed in: the consumption-side half of the frozen
    decision-snapshot contract (orchestrator#443 D6 §2a; r8 dual-hash). A
    mismatch fails this arm's context step, and the two-arm runner's paired
    inclusion rule then invalidates BOTH arms. Callers outside that path
    simply omit these arguments and get the unchanged pre-existing behavior.
    """
    metadata = _load_json_object(metadata_json) if metadata_json else {}
    market_snapshot = _load_json_object(market_snapshot_json)

    decision_snapshot_meta: dict[str, Any] = {}
    if decision_snapshot_digest is not None:
        if model_content_sha256 is None or session_date is None:
            raise ValueError(
                "decision_snapshot_digest requires model_content_sha256 and "
                "session_date to independently recompute and verify it"
            )
        identity = decision_snapshot_identity(
            market_snapshot_json=market_snapshot_json,
            account_snapshot_json=account_snapshot_json,
            session_date=session_date,
            model_content_sha256=model_content_sha256,
            calibrator_content_sha256=calibrator_content_sha256,
        )
        if identity["digest"] != decision_snapshot_digest:
            raise DecisionSnapshotMismatchError(
                "decision-snapshot digest mismatch: this arm's actually-"
                f"consumed inputs (market sha {identity['market_snapshot_sha256']}, "
                f"account sha {identity['account_snapshot_sha256']}) hash to "
                f"{identity['digest']}, expected {decision_snapshot_digest} "
                "(frozen before either arm ran); refusing to proceed on a "
                "different-from-frozen input world"
            )
        decision_snapshot_meta = {
            "decision_snapshot_digest": identity["digest"],
            "decision_snapshot_verified": True,
            "market_snapshot_sha256": identity["market_snapshot_sha256"],
            "account_snapshot_sha256": identity["account_snapshot_sha256"],
        }

    payload = {
        "schema_version": 1,
        "source": "native_live_context_fixture",
        "config": _load_json_object(strategy_config_json),
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
    args = parser.parse_args(argv)

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
    )
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
    "main",
    "market_snapshot_identity",
]


if __name__ == "__main__":
    raise SystemExit(main())
