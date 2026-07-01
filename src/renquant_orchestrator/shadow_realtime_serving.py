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
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from .realtime_data_plane import (
    JsonlTickFeedSource,
    MarketSnapshot,
    build_realtime_snapshot,
    default_tick_feed_path,
)
from .runtime_paths import default_data_root

STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "shadow_realtime_score"
SCHEMA_VERSION = "1"


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
    the pinned panel artifact read-only; tests inject a deterministic fake."""

    name: str

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
def _row_key(record: Mapping[str, Any]) -> tuple[str, str]:
    """One shadow row per ``(as_of, ticker)`` — re-running the same snapshot is a
    no-op, never a duplicate (idempotent append)."""
    return (str(record.get("as_of")), str(record.get("ticker")))


class _ShadowLogWriter:
    """Append shadow rows to the accumulating JSONL, skipping any whose
    ``(as_of, ticker)`` key is already present. Loads existing keys once at
    construction so idempotency survives process restarts."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._seen: set[tuple[str, str]] = self._load_keys()

    def _load_keys(self) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        if not self.path.exists():
            return keys
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    keys.add(_row_key(json.loads(line)))
                except (json.JSONDecodeError, AttributeError):
                    continue
        return keys

    def append(self, records: Iterable[Mapping[str, Any]]) -> int:
        records = list(records)
        if not records:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with self.path.open("a", encoding="utf-8") as fh:
            for record in records:
                key = _row_key(record)
                if key in self._seen:
                    continue
                fh.write(json.dumps(record, sort_keys=True) + "\n")
                self._seen.add(key)
                written += 1
        return written


# ---------------------------------------------------------------------------
# The collector — pair shadow real-time scores with frozen batch scores + LOG
# ---------------------------------------------------------------------------
def _pair_records(
    *,
    snapshot: MarketSnapshot,
    scorer_name: str,
    batch: Mapping[str, float],
    batch_ranks: Mapping[str, int],
    shadow: Mapping[str, float],
    shadow_ranks: Mapping[str, int],
    run_id: str,
    logged_at: str,
) -> list[dict[str, Any]]:
    by_ticker = snapshot.by_ticker()
    universe = sorted(set(batch) | set(shadow) | set(by_ticker))
    records: list[dict[str, Any]] = []
    for ticker in universe:
        row = by_ticker.get(ticker)
        batch_score = batch.get(ticker)
        shadow_score = shadow.get(ticker)
        batch_rank = batch_ranks.get(ticker)
        shadow_rank = shadow_ranks.get(ticker)
        score_delta = (
            shadow_score - batch_score
            if shadow_score is not None and batch_score is not None
            else None
        )
        rank_delta = (
            shadow_rank - batch_rank
            if shadow_rank is not None and batch_rank is not None
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
                "batch_score": batch_score,
                "batch_rank": batch_rank,
                "shadow_score": shadow_score,
                "shadow_rank": shadow_rank,
                "score_delta": score_delta,
                "rank_delta": rank_delta,
                "intraday_mid": row.intraday_mid if row is not None else None,
                "quote_status": row.quote_status if row is not None else None,
                "daily_feature_ref": row.daily_feature_ref if row is not None else None,
            }
        )
    return records


def run_shadow_serving(
    *,
    snapshot: MarketSnapshot,
    scorer: ShadowScorer,
    batch_scores: Mapping[str, Any],
    out_path: str | Path | None = None,
    data_root: Path | None = None,
    clock: Callable[[], datetime] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Score ``snapshot`` in real-time via the injected ``scorer``, pair each name
    with its frozen ``batch_scores``, and APPEND the paired rows to the shadow log.

    OBSERVE-ONLY: returns operational counts and logs a datum per name. It renders
    no verdict and mutates nothing but the append-only log file. Idempotent —
    re-running the same ``(as_of, ticker)`` writes zero new rows.
    """
    out = Path(out_path) if out_path else default_shadow_log_path(data_root)
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    logged_at = now.isoformat()
    resolved_run_id = run_id or f"shadow-{snapshot.as_of}"
    scorer_name = getattr(scorer, "name", "unknown")

    batch = _normalize_scores(batch_scores)
    batch_ranks = _dense_rank(batch)

    shadow = _normalize_scores(scorer.score(snapshot))
    shadow_ranks = _dense_rank(shadow)

    records = _pair_records(
        snapshot=snapshot,
        scorer_name=scorer_name,
        batch=batch,
        batch_ranks=batch_ranks,
        shadow=shadow,
        shadow_ranks=shadow_ranks,
        run_id=resolved_run_id,
        logged_at=logged_at,
    )

    writer = _ShadowLogWriter(out)
    written = writer.append(records)

    n_paired = sum(
        1 for r in records if r["batch_score"] is not None and r["shadow_score"] is not None
    )
    return {
        "observe_only": True,
        "out": str(out),
        "as_of": snapshot.as_of,
        "session_date": snapshot.session_date,
        "run_id": resolved_run_id,
        "logged_at": logged_at,
        "scorer": scorer_name,
        "n_rows": len(records),
        "n_written": written,
        "n_batch": len(batch),
        "n_shadow": len(shadow),
        "n_paired": n_paired,
    }


# ---------------------------------------------------------------------------
# Real scorer seam — lazy, read-only; never constructed in tests
# ---------------------------------------------------------------------------
def load_pinned_panel_scorer(
    manifest: Any,
    *,
    feature_matrix_fn: Callable[[MarketSnapshot], Any],
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
    """
    from renquant_common import load_scorer  # noqa: PLC0415 — lazy, real-run only

    artifact_scorer = load_scorer(manifest)

    class _PinnedPanelShadowScorer:
        def __init__(self) -> None:
            self.name = name
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
    parser.add_argument("--daily-features-json", required=True, help="JSON object ticker->daily_feature_ref")
    parser.add_argument("--batch-scores-json", required=True, help="JSON object ticker->frozen batch score")
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
    daily_features = {
        str(t).strip().upper(): ref
        for t, ref in _load_json_object(args.daily_features_json).items()
    }
    batch_scores = _load_json_object(args.batch_scores_json)

    build_kwargs: dict[str, Any] = {}
    if args.staleness_sec is not None:
        build_kwargs["staleness_sec"] = args.staleness_sec
    snapshot = build_realtime_snapshot(
        as_of=args.as_of,
        daily_features=daily_features,
        feed_source=JsonlTickFeedSource(feed_path),
        **build_kwargs,
    )
    summary = run_shadow_serving(
        snapshot=snapshot,
        scorer=scorer,
        batch_scores=batch_scores,
        out_path=args.out,
        data_root=data_root,
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print("[OBSERVE-ONLY] renquant105 Stage-1 shadow real-time serving")
        for key in ("as_of", "out", "n_rows", "n_written", "n_batch", "n_shadow", "n_paired"):
            print(f"  {key:<12} : {summary[key]}")
    return 0


__all__ = [
    "RECORD_KIND",
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
