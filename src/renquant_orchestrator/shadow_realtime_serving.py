"""renquant105 Stage-1 OBSERVE-ONLY shadow real-time model SERVING (design §4
piece 3, §9 converged r11).

Given a real-time market snapshot (:mod:`realtime_data_plane`) and the daily
panel model (a dependency-injected scorer; the real one loads the pinned artifact
READ-ONLY), compute a SHADOW real-time score/ranking and LOG it — as an
append-only JSONL under ``default_data_root()/logs/renquant105_pilot/`` — PAIRED
with the frozen batch score, for later comparison.

STRICTLY A COLLECTOR. This module records "what the model would score in
real-time vs what the batch scored" and nothing else. It renders NO PASS/FAIL,
places NO orders, sets NO pins, evaluates NO gates, promotes nothing, and mutates
NO live state. A logged row is a datum for the future, separate experiment
(design §9.4) — never a decision.

Note on the model contract: in Stage 1 the model signal is FROZEN daily (§6
class A); scoring the live snapshot here is an OBSERVE-ONLY counterfactual (a
Stage-3 preview of intraday re-scoring), deliberately decoupled from every
decision path so it can be measured before it is ever trusted.

The scorer is dependency-injected (a ``Protocol``). Tests inject a deterministic
fake; the real seam :func:`load_pinned_panel_scorer` lazily loads the pinned
panel scorer via ``renquant_common.load_scorer`` (read-only) and is never
constructed in tests.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from .realtime_data_plane import (
    FeatureSnapshot,
    JsonlTickFeedSource,
    MarketSnapshot,
    build_realtime_snapshot,
    default_tick_feed_path,
)
from .runtime_paths import default_data_root

log = logging.getLogger("renquant-orchestrator.shadow-realtime-serving")

STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "shadow_realtime_score"
SCHEMA_VERSION = "2"

# Primary experiment endpoint declaration (Codex #221 wrap-up). Stage 1 defers the
# statistical pre-registration to a SEPARATE, simplified experiment-prereg PR
# finalized against REAL pilot variance (design §9.4), so no paper threshold is
# fabricated here — but the endpoint, the common universe, the censoring
# mechanism, and the minimum-session gate are NAMED so a logged corpus is never
# silently treated as an experiment without them.
EXPERIMENT_ENDPOINT = {
    "primary_endpoint": (
        "paired-intersection shadow-vs-batch rank_delta_paired (and score_delta)"
    ),
    "common_universe": (
        "names with BOTH a frozen batch score AND a fresh (non-censored) shadow score"
    ),
    "censoring_mechanism": (
        "same-session + causality (source_ts<=as_of) + staleness censoring (data plane §6)"
    ),
    "minimum_session_count": (
        "deferred to the simplified experiment-prereg PR (§9.4), sized from REAL "
        "pilot variance — NOT fabricated on paper"
    ),
}


# ---------------------------------------------------------------------------
# Run provenance — every row bound to immutable artifact + feature + batch identity
# ---------------------------------------------------------------------------
class ProvenanceError(ValueError):
    """A shadow row/run could not be bound to complete, consistent provenance —
    fail-closed rather than log a non-reproducible datum (Codex #221)."""


@dataclass(frozen=True)
class RunProvenance:
    """Immutable identity every logged shadow row is bound to, so a corpus can
    never silently mix different models / features / batches (Codex #221).

    All fields are REQUIRED — a missing one is rejected, never defaulted:

      * ``artifact_digest`` — class-A scorer artifact / config fingerprint
        (the ``signal_version`` hash); the exact frozen model that scored.
      * ``feature_builder_version`` — feature-builder identity.
      * ``feature_cutoff`` — the T-1 EOD as-of the daily features were frozen.
      * ``feature_snapshot_digest`` — digest over the materialized T-1 feature
        snapshot the scorer consumed (binds the row to immutable feature state).
      * ``tick_policy_version`` — the data-plane point-in-time censoring policy.
      * ``batch_run_id`` — identity of the batch run whose frozen scores are the
        comparison baseline.
    """

    artifact_digest: str
    feature_builder_version: str
    feature_cutoff: str
    feature_snapshot_digest: str
    tick_policy_version: str
    batch_run_id: str

    _REQUIRED = (
        "artifact_digest",
        "feature_builder_version",
        "feature_cutoff",
        "feature_snapshot_digest",
        "tick_policy_version",
        "batch_run_id",
    )

    def validate(self) -> "RunProvenance":
        missing = [f for f in self._REQUIRED if not str(getattr(self, f, "")).strip()]
        if missing:
            raise ProvenanceError(
                "shadow run rejected — missing provenance fingerprints: "
                + ", ".join(missing)
                + " (Codex #221: every row must bind to immutable artifact + "
                "feature + batch identity)"
            )
        return self

    def to_record(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in self._REQUIRED}


def default_shadow_log_path(data_root: Path | None = None) -> Path:
    """The accumulating shadow-vs-batch score log, under the operator data root.

    Rooted at :func:`default_data_root` (honoring ``RENQUANT_DATA_ROOT``), NEVER
    the umbrella git tree — the same pilot directory the #216 tick feed uses."""
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "shadow_realtime_serving.jsonl"


# ---------------------------------------------------------------------------
# Scorer interface (dependency-injected)
# ---------------------------------------------------------------------------
class ShadowScorer(Protocol):
    """Pluggable read-only scorer. Given a :class:`MarketSnapshot` it returns
    ``ticker -> score``; a well-behaved scorer omits names whose quote was
    censored (stale / missing) rather than imputing a price. The real impl loads
    the pinned panel artifact read-only; tests inject a deterministic fake.

    Provenance (Codex #221): the scorer MUST expose ``artifact_digest`` — the
    immutable class-A artifact / config fingerprint that identifies the exact
    frozen model. It MAY expose ``feature_digest`` — the digest of the feature
    snapshot the artifact was built against; when set, a run whose served
    snapshot digest differs is REJECTED (mismatched feature fingerprint)."""

    name: str
    artifact_digest: str

    def score(self, snapshot: MarketSnapshot) -> Mapping[str, float]:
        ...


# ---------------------------------------------------------------------------
# Ranking + normalization helpers (pure)
# ---------------------------------------------------------------------------
def _normalize_scores(scores: Mapping[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ticker, value in scores.items():
        if value is None:
            continue
        try:
            out[str(ticker).strip().upper()] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _dense_rank(scores: Mapping[str, float]) -> dict[str, int]:
    """Dense rank, 1 = highest score; ties share a rank, the next distinct value
    gets the next integer. Empty in → empty out."""
    distinct = sorted(set(scores.values()), reverse=True)
    rank_of_value = {value: idx + 1 for idx, value in enumerate(distinct)}
    return {ticker: rank_of_value[value] for ticker, value in scores.items()}


# ---------------------------------------------------------------------------
# Idempotent append writer (mirrors the #216 tick-feed writer)
# ---------------------------------------------------------------------------
def _row_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Durable idempotency key: ``(as_of, ticker)`` PLUS the immutable
    :class:`RunProvenance` identity every row is already bound to (Codex #221
    round 2).

    ``(as_of, ticker)`` ALONE is too coarse for the provenance model this module
    enforces: it would silently treat a corrected/replayed run for the SAME
    session as a duplicate of an earlier one even when the artifact digest,
    feature-snapshot digest, or batch/run identity differs — hiding a real
    provenance conflict and leaving the ledger pointing at OBSOLETE ranks (e.g. a
    later re-run with a corrected model producing different scores would be
    wrongly dropped as "already seen"). Binding the key to the full provenance
    identity means an EXACT retry (identical ``(as_of, ticker)`` AND identical
    provenance) is still a true no-op, while a provenance-CHANGED re-run of the
    same ``(as_of, ticker)`` gets its own key and is appended as a new, distinct,
    fully-provenanced record — never silently dropped. See
    :meth:`_ShadowLogWriter.append` for the loud conflict diagnostic logged when
    that happens."""
    return (str(record.get("as_of")), str(record.get("ticker"))) + tuple(
        str(record.get(field, "")) for field in RunProvenance._REQUIRED
    )


def _session_key(record: Mapping[str, Any]) -> tuple[str, str]:
    """The coarser ``(as_of, ticker)`` session identity — used ONLY to detect and
    surface a provenance CONFLICT (same session, different full key); never used
    to dedupe on its own (Codex #221 round 2)."""
    return (str(record.get("as_of")), str(record.get("ticker")))


class _ShadowLogWriter:
    """Append shadow rows to the accumulating JSONL, skipping any whose full
    ``(as_of, ticker, *provenance)`` key is already present.

    Codex #221: idempotency is enforced under a single-writer advisory lock
    (``flock`` on a sidecar ``.lock`` file). Each append (i) takes the exclusive
    lock, (ii) RE-READS the durable unique keys from the file *inside* the lock —
    so keys another collector appended after this writer was constructed are
    seen — then (iii) appends only unseen rows. Read-then-append is therefore
    atomic across concurrent collectors and can no longer duplicate rows.

    Codex #221 round 2: the key is provenance-bound (see :func:`_row_key`), so a
    same-session row whose provenance DIFFERS from one already on disk is never
    silently deduped away as if it were an exact retry — it is appended as a new
    record and the conflict is logged loudly (never silently skipped, never
    silently overwritten) so the ledger carries both provenanced rows for
    reconciliation rather than pointing at an obsolete rank."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    def _load_keys(
        self,
    ) -> tuple[set[tuple[str, ...]], dict[tuple[str, str], set[tuple[str, ...]]]]:
        keys: set[tuple[str, ...]] = set()
        by_session: dict[tuple[str, str], set[tuple[str, ...]]] = {}
        if not self.path.exists():
            return keys, by_session
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    key = _row_key(record)
                except (json.JSONDecodeError, AttributeError):
                    continue
                keys.add(key)
                by_session.setdefault(_session_key(record), set()).add(key)
        return keys, by_session

    def append(self, records: Iterable[Mapping[str, Any]]) -> int:
        records = list(records)
        if not records:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with self._lock_path.open("w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)  # single-writer; blocks concurrent collectors
            try:
                # durable unique keys + per-session key index, re-read INSIDE the lock
                seen, by_session = self._load_keys()
                with self.path.open("a", encoding="utf-8") as fh:
                    for record in records:
                        key = _row_key(record)
                        if key in seen:
                            continue  # exact retry: identical provenance → true no-op
                        session = _session_key(record)
                        prior_for_session = by_session.get(session)
                        if prior_for_session:
                            # Same (as_of, ticker) already logged under DIFFERENT
                            # provenance — a real conflict, not a duplicate. Surface
                            # it loudly and append anyway: never silently skip the
                            # new (possibly corrected) record, never silently
                            # overwrite the earlier one.
                            log.warning(
                                "shadow-realtime-serving: provenance conflict for "
                                "as_of=%s ticker=%s — %d row(s) already logged with "
                                "different artifact/feature/batch identity; "
                                "appending this record as a NEW, distinct row "
                                "rather than silently deduping it (Codex #221 "
                                "round 2 — reconcile manually)",
                                session[0],
                                session[1],
                                len(prior_for_session),
                            )
                        fh.write(json.dumps(record, sort_keys=True) + "\n")
                        fh.flush()
                        seen.add(key)
                        by_session.setdefault(session, set()).add(key)
                        written += 1
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
        return written


# ---------------------------------------------------------------------------
# The collector — pair shadow real-time scores with frozen batch scores + LOG
# ---------------------------------------------------------------------------
def _pair_records(
    *,
    snapshot: MarketSnapshot,
    scorer_name: str,
    provenance: RunProvenance,
    batch: Mapping[str, float],
    shadow: Mapping[str, float],
    paired: set[str],
    batch_rank_paired: Mapping[str, int],
    shadow_rank_paired: Mapping[str, int],
    batch_rank_full: Mapping[str, int],
    shadow_rank_full: Mapping[str, int],
    run_id: str,
    logged_at: str,
) -> list[dict[str, Any]]:
    by_ticker = snapshot.by_ticker()
    universe = sorted(set(batch) | set(shadow) | set(by_ticker))
    prov = provenance.to_record()
    records: list[dict[str, Any]] = []
    for ticker in universe:
        row = by_ticker.get(ticker)
        batch_score = batch.get(ticker)
        shadow_score = shadow.get(ticker)
        in_paired = ticker in paired
        score_delta = (
            shadow_score - batch_score
            if shadow_score is not None and batch_score is not None
            else None
        )
        # Paired ranks (COMPARABLE): recomputed within the batch∩shadow
        # intersection, so a rank delta is not distorted by quote censoring
        # changing the shadow universe. rank_delta is defined ONLY here.
        b_rank_paired = batch_rank_paired.get(ticker) if in_paired else None
        s_rank_paired = shadow_rank_paired.get(ticker) if in_paired else None
        rank_delta_paired = (
            s_rank_paired - b_rank_paired
            if s_rank_paired is not None and b_rank_paired is not None
            else None
        )
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "stage": STAGE,
                "record_kind": RECORD_KIND,
                "observe_only": True,
                "run_id": run_id,
                "logged_at": logged_at,
                "as_of": snapshot.as_of,
                "session_date": snapshot.session_date,
                "ticker": ticker,
                "scorer": scorer_name,
                # provenance — every row bound to immutable artifact+feature+batch id
                **prov,
                "batch_score": batch_score,
                "shadow_score": shadow_score,
                "score_delta": score_delta,
                # comparable, paired-intersection ranks (the primary endpoint)
                "in_paired_universe": in_paired,
                "batch_rank_paired": b_rank_paired,
                "shadow_rank_paired": s_rank_paired,
                "rank_delta_paired": rank_delta_paired,
                # full-universe ranks: NON-comparable diagnostics only (no delta)
                "batch_rank_full": batch_rank_full.get(ticker),
                "shadow_rank_full": shadow_rank_full.get(ticker),
                "rank_comparability": "paired" if in_paired else "full-only",
                "intraday_mid": row.intraday_mid if row is not None else None,
                "quote_status": row.quote_status if row is not None else None,
                "daily_feature_ref": row.daily_feature_ref if row is not None else None,
            }
        )
    return records


def _resolve_provenance(
    *, snapshot: MarketSnapshot, scorer: ShadowScorer, batch_run_id: str
) -> RunProvenance:
    """Bind the run to complete, consistent provenance or fail-closed (Codex #221).

    Pulls the feature cutoff / builder / snapshot-digest and tick-policy version
    from the (materialized-feature-snapshot-backed) :class:`MarketSnapshot`
    metadata, the artifact digest from the scorer, and the batch run identity from
    the caller. Rejects if any fingerprint is missing, or if the scorer declares a
    ``feature_digest`` that differs from the served snapshot digest (a scorer
    built against a different feature snapshot than the one being served)."""
    meta = dict(snapshot.metadata)
    provenance = RunProvenance(
        artifact_digest=str(getattr(scorer, "artifact_digest", "") or "").strip(),
        feature_builder_version=str(meta.get("feature_builder_version") or "").strip(),
        feature_cutoff=str(meta.get("feature_cutoff") or "").strip(),
        feature_snapshot_digest=str(meta.get("feature_snapshot_digest") or "").strip(),
        tick_policy_version=str(meta.get("tick_policy_version") or "").strip(),
        batch_run_id=str(batch_run_id or "").strip(),
    ).validate()
    scorer_feature_digest = str(getattr(scorer, "feature_digest", "") or "").strip()
    if scorer_feature_digest and scorer_feature_digest != provenance.feature_snapshot_digest:
        raise ProvenanceError(
            "shadow run rejected — scorer.feature_digest "
            f"{scorer_feature_digest!r} != served feature_snapshot_digest "
            f"{provenance.feature_snapshot_digest!r} "
            "(Codex #221: mismatched feature fingerprint — do not mix)"
        )
    return provenance


def run_shadow_serving(
    *,
    snapshot: MarketSnapshot,
    scorer: ShadowScorer,
    batch_scores: Mapping[str, Any],
    batch_run_id: str,
    out_path: str | Path | None = None,
    data_root: Path | None = None,
    clock: Callable[[], datetime] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Score ``snapshot`` in real-time via the injected ``scorer``, pair each name
    with its frozen ``batch_scores``, and APPEND the paired rows to the shadow log.

    Every row is bound to complete :class:`RunProvenance` (immutable artifact +
    feature + batch identity); a missing or mismatched fingerprint fails the run
    closed (Codex #221) — nothing is logged. ``batch_run_id`` names the batch run
    whose frozen scores are the baseline.

    OBSERVE-ONLY: returns operational counts + coverage and logs a datum per name.
    It renders no verdict and mutates nothing but the append-only log file.
    Idempotent on EXACT retry — re-running the same ``(as_of, ticker)`` with
    identical provenance writes zero new rows. A re-run of the same
    ``(as_of, ticker)`` whose provenance differs (a corrected artifact, feature
    snapshot, or batch run) is a distinct, fully-provenanced row, never a
    silently-dropped duplicate (Codex #221 round 2; see :func:`_row_key`).
    """
    out = Path(out_path) if out_path else default_shadow_log_path(data_root)
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    logged_at = now.isoformat()
    resolved_run_id = run_id or f"shadow-{snapshot.as_of}"
    scorer_name = getattr(scorer, "name", "unknown")

    # Fail-closed provenance BEFORE any scoring / logging.
    provenance = _resolve_provenance(
        snapshot=snapshot, scorer=scorer, batch_run_id=batch_run_id
    )

    batch = _normalize_scores(batch_scores)
    shadow = _normalize_scores(scorer.score(snapshot))

    # Full-universe ranks: diagnostic + NON-comparable (each set ranked on its own).
    batch_rank_full = _dense_rank(batch)
    shadow_rank_full = _dense_rank(shadow)

    # Paired universe = the intersection actually comparable (a batch score AND a
    # shadow score). Ranks recomputed WITHIN it so a rank delta is not distorted
    # by quote censoring changing the shadow universe (Codex #221).
    paired = set(batch) & set(shadow)
    batch_rank_paired = _dense_rank({t: batch[t] for t in paired})
    shadow_rank_paired = _dense_rank({t: shadow[t] for t in paired})

    records = _pair_records(
        snapshot=snapshot,
        scorer_name=scorer_name,
        provenance=provenance,
        batch=batch,
        shadow=shadow,
        paired=paired,
        batch_rank_paired=batch_rank_paired,
        shadow_rank_paired=shadow_rank_paired,
        batch_rank_full=batch_rank_full,
        shadow_rank_full=shadow_rank_full,
        run_id=resolved_run_id,
        logged_at=logged_at,
    )

    writer = _ShadowLogWriter(out)
    written = writer.append(records)

    n_paired = len(paired)
    # Coverage / selection effects reported SEPARATELY (not folded into the rank
    # metric): which batch names dropped out (censored / no shadow) and which
    # shadow names had no batch baseline.
    batch_only = sorted(set(batch) - paired)
    shadow_only = sorted(set(shadow) - paired)
    coverage = (n_paired / len(batch)) if batch else 0.0
    return {
        "observe_only": True,
        "out": str(out),
        "as_of": snapshot.as_of,
        "session_date": snapshot.session_date,
        "run_id": resolved_run_id,
        "logged_at": logged_at,
        "scorer": scorer_name,
        "provenance": provenance.to_record(),
        "primary_endpoint": EXPERIMENT_ENDPOINT["primary_endpoint"],
        "n_rows": len(records),
        "n_written": written,
        "n_batch": len(batch),
        "n_shadow": len(shadow),
        "n_paired": n_paired,
        "coverage": coverage,
        "n_batch_only": len(batch_only),
        "n_shadow_only": len(shadow_only),
        "batch_only": batch_only,
        "shadow_only": shadow_only,
    }


# ---------------------------------------------------------------------------
# Real scorer seam — lazy, read-only; never constructed in tests
# ---------------------------------------------------------------------------
def load_pinned_panel_scorer(
    manifest: Any,
    *,
    feature_matrix_fn: Callable[[MarketSnapshot], Any],
    artifact_digest: str,
    feature_digest: str = "",
    name: str = "pinned-panel-scorer",
) -> ShadowScorer:
    """Adapt the pinned panel scorer (loaded READ-ONLY via
    ``renquant_common.load_scorer``) into a :class:`ShadowScorer`.

    ``feature_matrix_fn`` turns a snapshot into the model's input matrix — that
    real-time feature construction is Stage-3 wiring supplied by the caller, not
    fabricated here; this seam only loads the artifact and calls
    ``scorer.score(matrix) -> Series``. Lazily imported so tests (which inject a
    fake scorer) never touch model/artifact code. The load is read-only: no
    artifact is written, no pin is set, no order is placed.

    ``artifact_digest`` is the class-A artifact / config fingerprint the caller
    resolves from the pinned manifest — REQUIRED, so every logged row binds to the
    exact frozen model (Codex #221). ``feature_digest`` (optional) is the digest
    of the feature snapshot the artifact was built against; when supplied, a run
    that serves a different snapshot is rejected as a mismatch.
    """
    from renquant_common import load_scorer  # noqa: PLC0415 — lazy, real-run only

    if not str(artifact_digest or "").strip():
        raise ProvenanceError(
            "load_pinned_panel_scorer requires a non-empty artifact_digest "
            "(Codex #221: bind the row to the immutable artifact)"
        )
    artifact_scorer = load_scorer(manifest)

    class _PinnedPanelShadowScorer:
        def __init__(self) -> None:
            self.name = name
            self.artifact_digest = str(artifact_digest).strip()
            self.feature_digest = str(feature_digest or "").strip()
            self._scorer = artifact_scorer

        def score(self, snapshot: MarketSnapshot) -> Mapping[str, float]:
            matrix = feature_matrix_fn(snapshot)
            series = self._scorer.score(matrix)
            return {str(k).strip().upper(): float(v) for k, v in dict(series).items()}

    return _PinnedPanelShadowScorer()


# ---------------------------------------------------------------------------
# CLI — OBSERVE-ONLY; requires an injected scorer (real scorer wired separately)
# ---------------------------------------------------------------------------
def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def main(argv: Any | None = None, *, scorer: ShadowScorer | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shadow-realtime-serving",
        description=(
            "renquant105 Stage-1 OBSERVE-ONLY shadow model serving. Scores a "
            "real-time snapshot and logs it paired with the frozen batch score. "
            "Renders no verdict, places no orders, mutates no state."
        ),
    )
    parser.add_argument("--as-of", required=True, help="decision point-in-time (ISO-8601)")
    parser.add_argument("--tick-feed", default=None, help="intraday_ticks.jsonl (default under data root)")
    parser.add_argument(
        "--feature-snapshot-json",
        required=True,
        help=(
            "materialized, cutoff-stamped T-1 feature snapshot "
            "({feature_cutoff, feature_builder_version, features}); its digest binds "
            "every logged row to immutable feature state (Codex #221)"
        ),
    )
    parser.add_argument("--batch-scores-json", required=True, help="JSON object ticker->frozen batch score")
    parser.add_argument(
        "--batch-run-id", required=True, help="identity of the batch run whose scores are the baseline"
    )
    parser.add_argument("--staleness-sec", type=float, default=None, help="stale-quote censor bound")
    parser.add_argument("--data-root", default=None, help="operator data root for defaults")
    parser.add_argument("--out", default=None, help="shadow log JSONL (append; default under data root)")
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON")
    args = parser.parse_args(argv)

    if scorer is None:
        # The real panel scorer + its Stage-3 feature construction are wired by the
        # operator/caller (load_pinned_panel_scorer); the observe-only CLI does not
        # fabricate one. Mirrors the #216 logger's fail-clear-on-missing-dep stance.
        print(
            "[shadow-realtime-serving] no scorer wired. This OBSERVE-ONLY collector "
            "needs an injected ShadowScorer (real run: load_pinned_panel_scorer with "
            "the pinned artifact + a snapshot->matrix builder). Nothing logged.",
            flush=True,
        )
        return 2

    data_root = Path(args.data_root).expanduser().resolve() if args.data_root else None
    feed_path = Path(args.tick_feed) if args.tick_feed else default_tick_feed_path(data_root)
    feature_snapshot = FeatureSnapshot.from_mapping(_load_json_object(args.feature_snapshot_json))
    batch_scores = _load_json_object(args.batch_scores_json)

    build_kwargs: dict[str, Any] = {}
    if args.staleness_sec is not None:
        build_kwargs["staleness_sec"] = args.staleness_sec
    snapshot = build_realtime_snapshot(
        as_of=args.as_of,
        feature_snapshot=feature_snapshot,
        feed_source=JsonlTickFeedSource(feed_path),
        **build_kwargs,
    )
    summary = run_shadow_serving(
        snapshot=snapshot,
        scorer=scorer,
        batch_scores=batch_scores,
        batch_run_id=args.batch_run_id,
        out_path=args.out,
        data_root=data_root,
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print("[OBSERVE-ONLY] renquant105 Stage-1 shadow real-time serving")
        for key in (
            "as_of", "out", "n_rows", "n_written", "n_batch", "n_shadow",
            "n_paired", "coverage",
        ):
            print(f"  {key:<12} : {summary[key]}")
    return 0


__all__ = [
    "EXPERIMENT_ENDPOINT",
    "ProvenanceError",
    "RECORD_KIND",
    "RunProvenance",
    "SCHEMA_VERSION",
    "STAGE",
    "ShadowScorer",
    "default_shadow_log_path",
    "load_pinned_panel_scorer",
    "main",
    "run_shadow_serving",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
