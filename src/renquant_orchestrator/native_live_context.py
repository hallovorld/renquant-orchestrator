"""Native live context fixture builder for offboard rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import json
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


def compute_decision_snapshot_digest(
    *,
    market_snapshot: dict[str, Any],
    model_content_sha256: str,
    calibrator_content_sha256: str | None,
    session_date: str,
) -> str:
    """The §2a decision-snapshot digest (orchestrator#443 D6 §2a, r7 point 1).

    Covers, per the frozen design: (i) as-of timestamp + (ii) candidate/
    scoring universe + (iii) prices/corporate-action snapshot — all present
    inside ``market_snapshot``'s own resolved content, so hashing it whole
    covers all three; (iv)/(v) model/calibrator artifact identity; (vi) the
    starting-state-convention RULE marker (not a per-arm value — see
    ``STARTING_STATE_CONVENTION``); (vii) the session identifier.

    Both arms must be handed the IDENTICAL digest computed from the SAME
    shared inputs before either runs; each arm's actual consumption is then
    independently re-hashed via this SAME function and compared (see
    ``build_native_live_context``'s ``decision_snapshot_digest`` argument) —
    never reimplemented at the two call sites, to avoid exactly the kind of
    hand-copied-hash drift this project has hit before with
    ``model_content_sha256``.
    """
    canonical = json.dumps(
        {
            "market_snapshot": market_snapshot,
            "model_content_sha256": model_content_sha256,
            "calibrator_content_sha256": calibrator_content_sha256,
            "starting_state_convention": STARTING_STATE_CONVENTION,
            "session_date": session_date,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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
    this independently RECOMPUTES the digest from what this call actually
    loaded (``model_content_sha256``/``calibrator_content_sha256``/
    ``session_date`` are then required too) and raises
    ``DecisionSnapshotMismatchError`` if it doesn't match the expected value
    handed in — the consumption-side half of the frozen decision-snapshot
    contract (orchestrator#443 D6 §2a, r7 point 1). Callers outside that
    path simply omit these arguments and get the unchanged pre-existing
    behavior.
    """
    metadata = _load_json_object(metadata_json) if metadata_json else {}
    market_snapshot = _load_json_object(market_snapshot_json)

    decision_snapshot_verified: bool | None = None
    actual_digest: str | None = None
    if decision_snapshot_digest is not None:
        if model_content_sha256 is None or session_date is None:
            raise ValueError(
                "decision_snapshot_digest requires model_content_sha256 and "
                "session_date to independently recompute and verify it"
            )
        actual_digest = compute_decision_snapshot_digest(
            market_snapshot=market_snapshot,
            model_content_sha256=model_content_sha256,
            calibrator_content_sha256=calibrator_content_sha256,
            session_date=session_date,
        )
        if actual_digest != decision_snapshot_digest:
            raise DecisionSnapshotMismatchError(
                "decision-snapshot digest mismatch: this arm's actually-"
                f"consumed inputs hash to {actual_digest}, expected "
                f"{decision_snapshot_digest} (frozen before either arm ran); "
                "refusing to proceed on a different-from-frozen input world"
            )
        decision_snapshot_verified = True

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
            **(
                {
                    "decision_snapshot_digest": actual_digest,
                    "decision_snapshot_verified": decision_snapshot_verified,
                }
                if decision_snapshot_digest is not None
                else {}
            ),
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
    "compute_decision_snapshot_digest",
    "build_native_live_context",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
