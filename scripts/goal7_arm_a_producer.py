#!/usr/bin/env python3
"""Arm A INPUT PRODUCER for the frozen prereg
`doc/research/2026-08-05-goal7-momentum-per-regime-prereg.md`.

The Arm A runner (`goal7_arm_a_per_regime_runner.py`) applies §6's predicate to
a payload it refuses unless the payload names the gate's own producers. This is
the thing that produces that payload — and it is a separate file on purpose, so
the harness that JUDGES can never be the harness that CHOOSES.

WHAT IT COMPUTES, and every statistic is the gate's own:

    build_regime_series(dates)       the PRODUCTION regime label per date
    regime_diagnostics(...)          E1(R): mean per-date Spearman IC per regime
    regime_shift_diagnostics(...)    the same on the 2x-horizon-shifted label

The momentum score is not re-implemented either: it is
`train_momentum_artifact` under the SERVED artifact's own params, the same
packaged construction `momentum_eval_run.py` uses. Nothing here is re-fit.

THREE IMPLEMENTATION CHOICES THE REGISTRATION DID NOT FIX, declared here BEFORE
the run so they cannot be chosen after seeing an outcome:

1. **Evaluation window = every matured panel date.** No date range is selected.
   A span chosen after the fact is the forking path this whole registration
   exists to close, and "all of it" is the only choice with no freedom in it.
2. **Universe per date = the panel's own names for that date**, which is the
   rule `momentum_eval_run.py` already uses.
3. **The label is clipped to +/-0.5 inside `regime_diagnostics`.** That is the
   gate helper's own behaviour, not a choice made here, but it is load-bearing
   and therefore stated: on the served scorer the same clip moved the paired
   per-date IC by +0.00521 `[VERIFIED — orch#817/#822]`.

REFUSES rather than proceeds when the served params do not match the packaged
`params_v0()` — registration §1 voids this study for a different fingerprint.

Read-only. Writes ONLY the payload path given on the command line.

Usage:
    python scripts/goal7_arm_a_producer.py --out <payload.json> [--limit N]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import time

import numpy as np
import pandas as pd

RQ = pathlib.Path("/Users/renhao/git/github/RenQuant")
MODEL_REPO = pathlib.Path("/Users/renhao/git/github/renquant-model")
BT_REPO = pathlib.Path("/Users/renhao/git/github/renquant-backtesting")
PIPELINE_REPO = pathlib.Path("/Users/renhao/git/github/renquant-pipeline")
SERVED_ARTIFACT = (RQ / "backtesting" / "renquant_104" / "artifacts" /
                   "momentum" / "2026-08-02" / "momentum_residual_v0.json")
LABEL = "fwd_60d_excess"
GATE_SHIFT_DAYS = 120          # the enforced placebo leg's own shift (2 x 60)
SHUFFLE_SEEDS = (1, 2, 3, 4, 5)

PRODUCERS = ("build_regime_series", "regime_diagnostics",
             "regime_shift_diagnostics")


class ServedParamsChanged(RuntimeError):
    """Registration §1: this study is void for a different params fingerprint."""


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def served_params(artifact_path: pathlib.Path = SERVED_ARTIFACT) -> dict:
    """The SERVED params, checked against the packaged construction's own.

    A mismatch is a refusal, not a warning: scoring history with params the
    served artifact does not carry would answer a question nobody registered.
    """
    from renquant_model_momentum.train import params_v0

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    served = dict(artifact["params"])
    packaged = params_v0()
    compared = ("params_version", "window", "skip", "min_obs", "min_features",
                "names_per_date_floor", "min_side_obs")
    diff = {k: (served.get(k), packaged.get(k)) for k in compared
            if served.get(k) != packaged.get(k)}
    if diff:
        raise ServedParamsChanged(
            f"served params differ from the packaged construction on {diff} — "
            "registration §1 voids this study for a changed fingerprint")
    return {"artifact": artifact, "params": served}


def score_panel(panel: pd.DataFrame, params: dict, *, limit: int | None = None,
                progress_every: int = 100) -> pd.DataFrame:
    """(ticker, date, label, mu) for every matured panel date.

    `mu` is `train_momentum_artifact`'s composite score — the packaged
    construction, not a second implementation of it.
    """
    train_cli = _load_module("mtr", MODEL_REPO / "tools" / "momentum_train_run.py")
    from renquant_model_momentum.train import train_momentum_artifact

    readers = train_cli.LiveReaders()
    dates = sorted(pd.unique(panel["date"]))
    if limit:
        dates = dates[-limit:]
    rows: list[pd.DataFrame] = []
    t0 = time.time()
    for i, d in enumerate(dates, 1):
        day = panel[panel["date"] == d]
        art = train_momentum_artifact(d, sorted(day["ticker"].unique()),
                                      params, readers=readers)
        scores = art["scores"]
        block = day.copy()
        block["mu"] = [np.nan if scores.get(t) is None else float(scores.get(t, np.nan))
                       for t in block["ticker"]]
        rows.append(block)
        if progress_every and i % progress_every == 0:
            print(f"  scored {i}/{len(dates)} dates  ({time.time() - t0:.0f}s)",
                  flush=True)
    out = pd.concat(rows, ignore_index=True)
    return out.dropna(subset=["mu", LABEL]).reset_index(drop=True)


def _shuffle_within_date(val: pd.DataFrame, seed: int) -> pd.DataFrame:
    """A within-date permutation of the label. The registration's placebo is a
    label shuffle INSIDE each cross-section — shuffling across dates would also
    destroy the date structure the IC is computed over, which is a different
    (and weaker) null."""
    rng = np.random.default_rng(seed)
    out = val.copy()
    shuffled = out.groupby("date", sort=False)[LABEL].transform(
        lambda s: s.to_numpy()[rng.permutation(len(s))])
    out[LABEL] = shuffled
    return out


def produce(*, limit: int | None = None) -> dict:
    for repo in (MODEL_REPO, BT_REPO, PIPELINE_REPO):
        sys.path.insert(0, str(repo / "src"))
    # The gate helpers resolve their strategy dir at IMPORT time from
    # RENQUANT_REPO_ROOT. Pointed at the umbrella deliberately: `[VERIFIED —
    # orch#805/#807]` the BEAR/BULL_CALM numbers this registration was written
    # against came from these helpers under that same root, and a regime chain
    # read from a different config would not be comparable with them. READ-ONLY.
    os.environ.setdefault("RENQUANT_REPO_ROOT", str(RQ))
    from renquant_backtesting.analysis.analyze_manifest_sanity_placebo import (
        build_regime_series, regime_diagnostics, regime_shift_diagnostics)

    served = served_params()
    train_cli = _load_module("mtr2", MODEL_REPO / "tools" / "momentum_train_run.py")
    panel = pd.read_parquet(train_cli.PANEL_PATH,
                            columns=["ticker", "date", LABEL])
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.dropna(subset=[LABEL])

    print(f"scoring {panel['date'].nunique()} matured panel dates …", flush=True)
    scored = score_panel(panel, served["params"], limit=limit)
    print(f"scored rows: {len(scored)}  dates: {scored['date'].nunique()}",
          flush=True)

    dates = sorted(pd.unique(scored["date"]))
    print(f"running the PRODUCTION regime chain over {len(dates)} dates …",
          flush=True)
    regimes = build_regime_series(dates)
    print(f"  regimes: {regimes['regime'].value_counts().to_dict()}", flush=True)

    val = scored[["ticker", "date", LABEL]].copy()
    mu = pd.Series(scored["mu"].to_numpy(), index=val.index)

    e1 = regime_diagnostics(val, mu, LABEL, regimes)
    shift = regime_shift_diagnostics(panel, val, mu, LABEL, regimes,
                                     shifts=(GATE_SHIFT_DAYS,))

    print(f"running {len(SHUFFLE_SEEDS)} label-shuffle replications …", flush=True)
    shuffles: dict[str, list[float | None]] = {}
    for seed in SHUFFLE_SEEDS:
        rep = regime_diagnostics(_shuffle_within_date(val, seed), mu, LABEL, regimes)
        for regime, stats in rep.items():
            shuffles.setdefault(regime, []).append(stats.get("mean_ic"))

    per_regime: dict[str, dict] = {}
    for regime, stats in e1.items():
        reps = [v for v in shuffles.get(regime, []) if v is not None]
        legs = shift.get(regime) or []
        leg = next((row for row in legs
                    if row.get("shift_days") == GATE_SHIFT_DAYS), None)
        per_regime[regime] = {
            "mean_ic": stats.get("mean_ic"),
            "n_dates": stats.get("n_dates"),
            "n_rows": stats.get("n_rows"),
            "hit_rate": stats.get("hit_rate"),
            # §4: the WORST of the five, never their mean.
            "placebo_shuffle": max(reps) if reps else None,
            "placebo_shuffle_reps": shuffles.get(regime, []),
            "placebo_shift": (leg or {}).get("model_placebo_ic"),
            "label_autocorr_ic": (leg or {}).get("label_autocorr_ic"),
            "placebo_shift_n_dates": (leg or {}).get("n_dates"),
        }

    return {
        "arm": "A",
        "registration": "doc/research/2026-08-05-goal7-momentum-per-regime-prereg.md",
        "provenance": {
            "producers": list(PRODUCERS),
            "score_construction": "renquant_model_momentum.train.train_momentum_artifact",
            "served_artifact": str(SERVED_ARTIFACT),
            "served_artifact_content_sha256": served["artifact"]["content_sha256"],
            "params": served["params"],
            "label": LABEL,
            "shift_days": GATE_SHIFT_DAYS,
            "shuffle_seeds": list(SHUFFLE_SEEDS),
            "window_rule": "every matured panel date — no range selected",
            "n_scored_rows": int(len(scored)),
            "n_scored_dates": int(scored["date"].nunique()),
            "first_date": str(pd.Timestamp(dates[0]).date()),
            "last_date": str(pd.Timestamp(dates[-1]).date()),
            "label_clip": "regime_diagnostics clips the label to +/-0.5 (the "
                          "gate helper's own behaviour, not a choice here)",
        },
        "per_regime": per_regime,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None,
                    help="score only the LAST N matured dates (a smoke run — "
                         "a limited run is NOT the registered Arm A window and "
                         "says so in the payload)")
    args = ap.parse_args(argv)
    try:
        payload = produce(limit=args.limit)
    except ServedParamsChanged as exc:
        print(f"REFUSED: {exc}")
        return 3
    if args.limit:
        payload["provenance"]["window_rule"] = (
            f"SMOKE RUN — last {args.limit} matured dates only; NOT the "
            f"registered Arm A window")
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=2, default=str),
                                      encoding="utf-8")
    print(json.dumps(payload["per_regime"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
