"""S3-b: wire the PINNED production blend scorer into the observe-only collector.

``shadow_realtime_serving.main`` deliberately refuses to fabricate a scorer
("no scorer wired", rc=2). This module is the real wiring it names: it loads
the SAME composite the production ranking uses — ``load_blend_scorer`` from
the pinned renquant-pipeline, which pin-verifies every component fail-closed
(content sha, config fingerprint, momentum ledger chain) — and adapts it to
the :class:`~renquant_orchestrator.shadow_realtime_serving.ShadowScorer`
protocol. One shared definition: the pin checks live in the pipeline and are
NOT re-implemented here; a refusal there propagates untouched.

Matrix semantics (the replay-vs-served lesson, orch#703/#1032): the feature
snapshot is bridged from ``logs/served_matrix`` — the exact ``ctx._panel_matrix``
values production scored, post-preprocessing. So the matrix handed to the
blend is those values verbatim, reindexed to the artifact's ``feature_cols``;
no re-normalization, no feature construction here. A missing column raises
inside the scorer (fail-closed), never imputes.

OBSERVE-ONLY: loads read-only, logs rows, renders no verdict, places no
order, mutates no state. Everything import-heavy is lazy so unit tests can
inject fakes without touching model/artifact code.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from renquant_orchestrator.realtime_data_plane import FeatureSnapshot, MarketSnapshot
from renquant_orchestrator.shadow_realtime_serving import ProvenanceError
from renquant_orchestrator import shadow_realtime_serving as _serving

SCORER_NAME = "pinned-blend-scorer"


def build_feature_matrix(snapshot: MarketSnapshot, feature_cols: list[str]) -> Any:
    """The scoring matrix for ``snapshot``'s fresh rows, columns = ``feature_cols``.

    Values come verbatim from each row's ``daily_feature_ref["values"]`` (the
    served-matrix bridge). A fresh row with no feature ref is REFUSED rather
    than skipped — a name that is priceable but unscoreable means the snapshot
    and the watchlist disagree, and silently dropping it would understate
    coverage. Missing columns are left to the scorer's own KeyError.
    """
    import pandas as pd  # noqa: PLC0415 — lazy; tests fake the scorer, not pandas

    rows = snapshot.fresh_rows()
    values: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        ref = row.daily_feature_ref
        if not isinstance(ref, Mapping) or not isinstance(ref.get("values"), Mapping):
            raise ProvenanceError(
                f"fresh row {row.ticker!r} carries no daily_feature_ref.values — "
                "the snapshot bridge and the tick watchlist disagree; refusing "
                "to score a partial cross-section silently"
            )
        values[str(row.ticker).strip().upper()] = ref["values"]
    if not values:
        raise ProvenanceError(
            "zero fresh rows in the snapshot (every quote censored as "
            "stale/missing) — refusing to hand the scorer an empty "
            "cross-section; check as_of vs the tick feed and staleness_sec"
        )
    matrix = pd.DataFrame.from_dict(values, orient="index")
    # Column order is the artifact's; extra snapshot columns are dropped.
    # A column the artifact requires but the snapshot lacks is a REFUSAL here
    # (named, at the seam that knows both sides) rather than a KeyError deep
    # in the scorer.
    missing = [c for c in feature_cols if c not in matrix.columns]
    if missing:
        raise ProvenanceError(
            f"feature snapshot lacks {len(missing)} of the artifact's "
            f"feature_cols (first: {missing[:5]}) — the snapshot bridge and "
            "the pinned artifact disagree; refusing to score"
        )
    return matrix[list(feature_cols)]


class _PinnedBlendShadowScorer:
    """Adapt ``BlendPanelScorer`` to the ShadowScorer protocol (#221 provenance)."""

    def __init__(self, blend: Any, *, artifact_digest: str, feature_digest: str) -> None:
        if not str(artifact_digest or "").strip():
            raise ProvenanceError(
                "pinned blend scorer has no composite config_fingerprint — an "
                "unidentifiable artifact must not serve (Codex #221)"
            )
        self.name = SCORER_NAME
        self.artifact_digest = str(artifact_digest).strip()
        self.feature_digest = str(feature_digest or "").strip()
        self._blend = blend

    def score(self, snapshot: MarketSnapshot) -> Mapping[str, float]:
        matrix = build_feature_matrix(snapshot, list(self._blend.feature_cols))
        series = self._blend.score(matrix)
        out: dict[str, float] = {}
        for ticker, value in dict(series).items():
            fv = float(value)
            if fv == fv:  # NaN-free contract: the blend NaNs the non-intersection
                out[str(ticker).strip().upper()] = fv
        return out


def load_pinned_blend_shadow_scorer(
    *,
    strategy_config_path: str | Path,
    strategy_dir: str | Path,
    feature_digest: str = "",
) -> _PinnedBlendShadowScorer:
    """Load the production blend from the PINNED strategy config, fail-closed.

    ``strategy_config_path`` must be the pin-verified config path (the wrapper
    resolves it via ``rq105_pinned_common.py --verify-file``, the same
    lock+HEAD+bytes verification the session scheduler uses — orch#1041).
    ``strategy_dir`` anchors the components' relative ``artifact_path``s
    (production: ``<RQ_ROOT>/backtesting/renquant_104``).
    """
    from renquant_pipeline.kernel.panel_pipeline.blend_scorer import (  # noqa: PLC0415
        load_blend_scorer,
    )

    config = json.loads(Path(strategy_config_path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ProvenanceError(f"strategy config is not an object: {strategy_config_path}")
    config["_strategy_dir"] = str(strategy_dir)
    blend = load_blend_scorer(config)  # pin mismatch/missing key raises here
    composite = str((getattr(blend, "metadata", {}) or {}).get("config_fingerprint") or "")
    return _PinnedBlendShadowScorer(
        blend, artifact_digest=composite, feature_digest=feature_digest
    )


def main(argv: Any | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shadow-serving-pinned",
        description=(
            "S3-b wiring: load the pinned production blend scorer (read-only, "
            "pin-verified in renquant-pipeline) and run the observe-only "
            "shadow serving collector with it."
        ),
    )
    parser.add_argument(
        "--pinned-strategy-config",
        required=True,
        help="pin-verified strategy config path (rq105_pinned_common --verify-file)",
    )
    parser.add_argument(
        "--strategy-dir",
        required=True,
        help="strategy dir anchoring component artifact_paths (backtesting/renquant_104)",
    )
    parser.add_argument(
        "--feature-snapshot-json",
        required=True,
        help="forwarded to the collector; also digested here to bind scorer↔snapshot",
    )
    args, rest = parser.parse_known_args(argv)

    # Digest the SAME file the collector will serve, through the SAME contract
    # (FeatureSnapshot.from_mapping), so _resolve_provenance cross-checks
    # scorer.feature_digest == served digest and refuses a swapped file.
    snapshot_payload = json.loads(Path(args.feature_snapshot_json).read_text(encoding="utf-8"))
    feature_digest = FeatureSnapshot.from_mapping(snapshot_payload).digest

    scorer = load_pinned_blend_shadow_scorer(
        strategy_config_path=args.pinned_strategy_config,
        strategy_dir=args.strategy_dir,
        feature_digest=feature_digest,
    )
    forwarded = ["--feature-snapshot-json", args.feature_snapshot_json, *rest]
    return _serving.main(forwarded, scorer=scorer)


__all__ = [
    "SCORER_NAME",
    "build_feature_matrix",
    "load_pinned_blend_shadow_scorer",
    "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
