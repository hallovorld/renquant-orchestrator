#!/usr/bin/env python3
"""Recompute every number in the breadth-precision memo, from pinned inputs.

Why this exists: the memo's numbers were first quoted from a scratch-only
corpus that a reviewer could not reproduce from the PR branch. This script is
the reviewable derivation. It pins each input by sha256, refuses to run against
a different one unless told to, and prints the same tables the memo states.

    python3 tools/breadth_precision_verify.py \
        --clf-corpus <path>/clf_wf_scores.parquet \
        --panel /Users/renhao/git/github/RenQuant/data/transformer_v4_wl200_clean.parquet

Both inputs are READ-ONLY. Nothing is written anywhere.

Determinism: every subsample draw is seeded off (date, N, replicate), so two
runs on the same corpus produce bit-identical tables. There is no global RNG
state to leak between sections.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

#: Inputs the memo's published numbers were computed from. A mismatch means the
#: numbers below are NOT the memo's numbers, which is exactly what a reviewer
#: needs to be told rather than left to assume.
PINNED = {
    "clf_wf_scores.parquet":
        "1da3fcfab06af1e597ac0eb83dff4741ed3dd027de8b8a6b4d58979f5bc4efe4",
    "clf_wf_manifest.json":
        "c1cb22e29db7b016cf223eb257f857d80bc8edd4f363685533e623d7bd092086",
}

LADDER = (20, 40, 80, 140, 200, 250, 292)
MIN_NAMES_PER_DATE = 250
DRAWS_PER_CELL = 3
BLOCK_TDAYS = 60


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_pin(path: Path, *, allow_mismatch: bool) -> str:
    digest = sha256(path)
    expected = PINNED.get(path.name)
    if expected is None:
        print(f"  {path.name}: sha256={digest}  (not pinned)")
        return digest
    if digest == expected:
        print(f"  {path.name}: sha256={digest}  PIN OK")
        return digest
    msg = (f"{path.name} sha256={digest} does NOT match the pinned "
           f"{expected}. The memo's published numbers were computed from the "
           f"pinned input; this run will produce different ones.")
    if not allow_mismatch:
        raise SystemExit(f"ABORT: {msg}\nPass --allow-input-mismatch to proceed anyway.")
    print(f"  WARNING: {msg}")
    return digest


def breadth_ladder(corpus: pd.DataFrame) -> list[tuple[int, float]]:
    """Var(per-date IC) as a function of names-per-date."""
    d = corpus.dropna(subset=["raw", "fwd_60d_excess"])
    by_date = {dt: g for dt, g in d.groupby("date") if len(g) >= MIN_NAMES_PER_DATE}
    print(f"  dates with >= {MIN_NAMES_PER_DATE} names: {len(by_date)}")
    out = []
    for n_names in LADDER:
        ics: list[float] = []
        for dt, g in by_date.items():
            take = min(n_names, len(g))
            for rep in range(DRAWS_PER_CELL):
                # seed off the cell, not a shared stream: order-independent
                seed = int(hashlib.sha256(
                    f"{dt}|{n_names}|{rep}".encode()).hexdigest()[:8], 16)
                s = g.sample(n=take, random_state=seed)
                if s["raw"].nunique() > 1:
                    ics.append(s["raw"].corr(s["fwd_60d_excess"], method="spearman"))
        out.append((n_names, float(np.nanvar(ics, ddof=1))))
    return out


def fit_a_plus_b_over_n(rows: list[tuple[int, float]]) -> tuple[float, float]:
    n = np.array([r[0] for r in rows], dtype=float)
    v = np.array([r[1] for r in rows], dtype=float)
    design = np.vstack([np.ones_like(n), 1.0 / n]).T
    a, b = np.linalg.lstsq(design, v, rcond=None)[0]
    return float(a), float(b)


def survivorship_probe(panel: pd.DataFrame) -> dict:
    """Does the historical panel contain names that left the universe?"""
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    end = panel["date"].max()
    final_names = set(panel.loc[panel["date"] == end, "ticker"])
    all_names = set(panel["ticker"])
    n_dates = panel["date"].nunique()
    return {
        "date_min": panel["date"].min().date(),
        "date_max": end.date(),
        "n_dates": n_dates,
        "span_years": (end - panel["date"].min()).days / 365.25,
        "blocks_available": n_dates // BLOCK_TDAYS,
        "n_tickers": len(all_names),
        "n_final": len(final_names),
        "n_ever_but_absent_at_end": len(all_names - final_names),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clf-corpus", required=True, type=Path)
    ap.add_argument("--panel", type=Path, default=None,
                    help="production panel parquet, for the history/survivorship probe")
    ap.add_argument("--allow-input-mismatch", action="store_true")
    args = ap.parse_args(argv)

    print("INPUTS")
    check_pin(args.clf_corpus, allow_mismatch=args.allow_input_mismatch)
    manifest = args.clf_corpus.with_name("clf_wf_manifest.json")
    if manifest.exists():
        check_pin(manifest, allow_mismatch=args.allow_input_mismatch)

    corpus = pd.read_parquet(args.clf_corpus)
    print(f"\nCORPUS  rows={len(corpus)}  dates={corpus['date'].nunique()}  "
          f"folds={corpus['fold_idx'].nunique()}  tickers={corpus['ticker'].nunique()}")

    print("\nBREADTH LADDER  Var(per-date IC) vs names/date")
    rows = breadth_ladder(corpus)
    print(f"  {'N':>5} {'Var':>10} {'sd':>9}")
    for n_names, var in rows:
        print(f"  {n_names:5} {var:10.5f} {np.sqrt(var):9.4f}")

    a, b = fit_a_plus_b_over_n(rows)
    print(f"\n  fit: Var(IC) = {a:.5f} + {b:.4f}/N")
    sd292 = np.sqrt(a + b / 292)
    print(f"  irreducible share at N=292: {a / (a + b / 292) * 100:.0f}%")
    for n2 in (292, 500, 830, 2000):
        sd = np.sqrt(a + b / n2)
        print(f"  N={n2:5} -> sd={sd:.4f}  ({(sd / sd292 - 1) * 100:+.1f}% vs N=292)")
    print(f"  N=inf   -> sd={np.sqrt(a):.4f}  "
          f"({(np.sqrt(a) / sd292 - 1) * 100:+.1f}% vs N=292)")

    if args.panel and args.panel.exists():
        print("\nHISTORY / SURVIVORSHIP PROBE (production panel, read-only)")
        probe = survivorship_probe(pd.read_parquet(args.panel, columns=["date", "ticker"]))
        for k, v in probe.items():
            print(f"  {k}: {v}")
        if probe["n_ever_but_absent_at_end"] == 0:
            print("  => ZERO names ever leave: this history is the CURRENT universe "
                  "backfilled, i.e. survivorship-contaminated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
