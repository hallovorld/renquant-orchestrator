"""Derive the weekly PatchTST retrain cutoff from the training-corpus frontier.

S12 §4-B3 (``doc/research/2026-07-02-s12-panel-refresh-diagnosis.md``): the
umbrella ``weekly_retrain_patchtst.sh`` WEEKLY mode pinned ``LATEST_CUT`` to the
STATIC source manifest's frozen tail (``walkforward_manifest_v2_20260602.json``,
latest cutoff 2026-03-09). After a corpus refresh the retrain would advance
exactly once, then re-train the same cutoff forever, ``cutoffs_advance``
correctly refuses, and the served pin re-freezes.

This module makes the cutoff DERIVE from the corpus itself:

- **source** — the refreshed training corpus parquet's max LABELED date (rows
  whose forward-label column is non-null): the achievable train frontier;
- **quantization** — snapped DOWN to the Monday of its ISO week, the grid every
  cutoff of the static WF manifests sits on (39/39 measured Mondays), so
  intra-week reruns are idempotent instead of spawning off-grid cutoffs;
- **fail-closed staleness** — the frontier's implied bar frontier
  (``frontier + lookahead_days`` business days, mirroring
  ``model_freshness_monitor``'s horizon-adjusted ``label_observation_cutoff``
  semantics) must be within ``--max-staleness-days`` of today, so a frozen
  corpus ABORTS the retrain instead of silently re-training stale data;
- **the static manifest is ONLY a lower-bound sanity** — the derived cutoff
  must not regress behind the manifest tail, but the manifest date is NEVER
  the cutoff source and a manifest alone can never produce a cutoff.

Cutoffs stay date-based end to end (the ``val_tail_pct`` lesson: percentage
tails silently freeze the effective train cutoff). Everything downstream —
seeds, embargo, trainer/calibrator argv — is untouched:
``build_patchtst_wf_manifest`` still consumes an effective source manifest.

Usage (stdout carries ONLY the derived ISO cutoff; diagnostics go to stderr)::

  python -m renquant_orchestrator.patchtst_weekly_cutoff \\
      --corpus /.../data/transformer_v4_wl200_clean.parquet \\
      --lower-bound-manifest /.../sim/walkforward_manifest_v2_20260602.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import pandas as pd

from .build_patchtst_wf_manifest import (
    DEFAULT_LABEL,
    extract_cutoffs,
    infer_label_lookahead_days,
)

#: Max calendar-day age of the corpus's IMPLIED BAR FRONTIER (labeled frontier
#: + lookahead business days). A weekly-refreshed corpus scores ~1-7d; the
#: frozen 2026-02-10 corpus scores ~55d and must fail closed.
DEFAULT_MAX_STALENESS_DAYS = 28


class CutoffDerivationError(RuntimeError):
    """Fail-closed derivation failure — the weekly retrain must NOT proceed."""


def corpus_labeled_frontier(corpus_path: Path, *, label: str = DEFAULT_LABEL) -> _dt.date:
    """Max fully-labeled date in the training corpus (the achievable frontier).

    Reads only the ``date`` (+ label, when present) columns. The served corpus
    is label-dropna'd at build so ``max(date)`` already IS the labeled
    frontier; when a corpus retains NaN-label tail rows the frontier is the max
    date with a non-null label (the trainer re-drops unlabeled rows anyway —
    the cutoff must not overstate what is trainable).
    """
    if not corpus_path.exists():
        raise CutoffDerivationError(
            f"training corpus missing: {corpus_path} — cannot derive the weekly "
            "cutoff. The static WF manifest is only a lower-bound sanity and can "
            "NEVER source the cutoff (S12 B3); run the corpus refresh first."
        )
    import pyarrow.parquet as pq

    try:
        available = set(pq.ParquetFile(corpus_path).schema_arrow.names)
    except Exception as exc:  # unreadable/corrupt parquet → fail closed
        raise CutoffDerivationError(
            f"training corpus unreadable ({corpus_path}): {exc}"
        ) from exc
    if "date" not in available:
        raise CutoffDerivationError(
            f"training corpus has no 'date' column: {corpus_path}"
        )
    columns = ["date"] + ([label] if label in available else [])
    frame = pd.read_parquet(corpus_path, columns=columns)
    if label in frame.columns:
        frame = frame[frame[label].notna()]
    if frame.empty:
        raise CutoffDerivationError(
            f"training corpus has no labeled rows (label={label}): {corpus_path}"
        )
    return pd.Timestamp(frame["date"].max()).date()


def implied_bar_frontier(frontier: _dt.date, lookahead_days: int) -> _dt.date:
    """Bar frontier implied by a labeled frontier: ``frontier + lookahead`` BDays.

    Inverse of ``build_patchtst_wf_manifest.data_end_for_cutoff`` and the same
    weekday-only ``BDay`` convention the #213 freshness monitor uses for its
    horizon-adjusted ``label_observation_cutoff`` (no holiday calendar; the few
    holiday days of skew are absorbed by ``--max-staleness-days``).
    """
    return (pd.Timestamp(frontier) + pd.offsets.BDay(lookahead_days)).date()


def quantize_to_weekly_grid(frontier: _dt.date) -> _dt.date:
    """Snap a frontier DOWN to the Monday of its ISO week (the WF cutoff grid)."""
    return frontier - _dt.timedelta(days=frontier.weekday())


def latest_manifest_cutoff(manifest_path: Path) -> str:
    """Latest cutoff of a static WF manifest — the LOWER-BOUND sanity input."""
    if not manifest_path.exists():
        raise CutoffDerivationError(
            f"lower-bound manifest missing: {manifest_path} — the sanity check "
            "cannot run; fix the path rather than deriving unchecked."
        )
    try:
        cutoffs = extract_cutoffs(manifest_path, None)
    except Exception as exc:
        raise CutoffDerivationError(
            f"lower-bound manifest unreadable ({manifest_path}): {exc}"
        ) from exc
    if not cutoffs:
        raise CutoffDerivationError(
            f"lower-bound manifest has no cutoffs: {manifest_path}"
        )
    return cutoffs[-1]


def derive_weekly_cutoff(
    corpus_path: Path,
    *,
    label: str = DEFAULT_LABEL,
    lower_bound_manifest: Path | None = None,
    max_staleness_days: int = DEFAULT_MAX_STALENESS_DAYS,
    today: _dt.date | None = None,
) -> str:
    """Derive the weekly retrain cutoff from the corpus frontier (fail-closed).

    Returns the ISO cutoff date, or raises :class:`CutoffDerivationError` when
    the corpus is missing, unlabeled, future-dated, stale beyond the
    horizon-adjusted bound, or regressed behind the static-manifest tail.
    """
    today = today or _dt.date.today()
    frontier = corpus_labeled_frontier(corpus_path, label=label)
    if frontier > today:
        raise CutoffDerivationError(
            f"corpus labeled frontier {frontier} is in the future (today "
            f"{today}) — corrupt corpus dates; refusing to derive a cutoff."
        )
    lookahead = infer_label_lookahead_days(label)
    bar_frontier = implied_bar_frontier(frontier, lookahead)
    age_days = (today - bar_frontier).days
    if age_days > max_staleness_days:
        raise CutoffDerivationError(
            f"corpus is STALE: labeled frontier {frontier} implies bar frontier "
            f"{bar_frontier} ({age_days}d old > {max_staleness_days}d bound) — "
            "the refresh has not advanced the corpus; refusing to retrain on "
            "frozen data (S12 B3 fail-closed). Re-run the corpus refresh or "
            "raise --max-staleness-days deliberately."
        )
    cutoff = quantize_to_weekly_grid(frontier)
    if lower_bound_manifest is not None:
        lower_bound = latest_manifest_cutoff(lower_bound_manifest)
        if cutoff.isoformat() < lower_bound:
            raise CutoffDerivationError(
                f"derived cutoff {cutoff} regressed behind the static manifest "
                f"tail {lower_bound} ({lower_bound_manifest}) — wrong/rolled-back "
                "corpus; refusing. The manifest is a lower bound only, never the "
                "cutoff source."
            )
    return cutoff.isoformat()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", required=True, type=Path,
                    help="Training corpus parquet (the refreshed frontier source).")
    ap.add_argument("--label", default=DEFAULT_LABEL,
                    help="Forward-label column; also sets the lookahead horizon.")
    ap.add_argument("--lower-bound-manifest", type=Path, default=None,
                    help="Static WF manifest whose latest cutoff is a LOWER-BOUND "
                         "sanity (never the cutoff source).")
    ap.add_argument("--max-staleness-days", type=int, default=DEFAULT_MAX_STALENESS_DAYS,
                    help="Max calendar age of the corpus's implied bar frontier.")
    ap.add_argument("--as-of", type=_dt.date.fromisoformat, default=None,
                    help="Override 'today' (testing/reproducibility).")
    args = ap.parse_args(argv)
    try:
        cutoff = derive_weekly_cutoff(
            args.corpus,
            label=args.label,
            lower_bound_manifest=args.lower_bound_manifest,
            max_staleness_days=args.max_staleness_days,
            today=args.as_of,
        )
    except CutoffDerivationError as exc:
        print(f"patchtst_weekly_cutoff: FAIL-CLOSED — {exc}", file=sys.stderr)
        return 1
    print(f"patchtst_weekly_cutoff: derived cutoff {cutoff} "
          f"(corpus={args.corpus})", file=sys.stderr)
    print(cutoff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
