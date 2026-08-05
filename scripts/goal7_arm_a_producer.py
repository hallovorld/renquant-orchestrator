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
`params_v0()` — registration §1 voids this study for a different fingerprint —
or when **no ledger row carries the artifact's content sha**. Reading the
artifact FILE and trusting its own hash proves only that the file is
self-consistent; the served object is the ledger's row `[codex on orch#825]`.

AND IT FINGERPRINTS ITS OWN INPUTS. The producer reads MUTABLE surfaces — the
panel, 145 OHLCV files, the sector map. A payload that records only summary
counts could be reproduced with revised data, or by revised feature code under
unchanged params, and report different numbers while looking identical. So the
payload carries: every reader-recorded digest (itemised and rolled up), the
panel file's own sha, a content hash of the scored table, the git revision of
all four repositories, and the ledger row's identity.

Read-only. Writes ONLY the payload path given on the command line.

Usage:
    python scripts/goal7_arm_a_producer.py --out <payload.json> [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time

import numpy as np
import pandas as pd

#: This file's own repository — NOT `Path.cwd()`, which identifies whatever
#: checkout the caller happened to stand in `[codex on orch#825]`.
ORCH_REPO = pathlib.Path(__file__).resolve().parent.parent
RQ = pathlib.Path("/Users/renhao/git/github/RenQuant")
MODEL_REPO = pathlib.Path("/Users/renhao/git/github/renquant-model")
BT_REPO = pathlib.Path("/Users/renhao/git/github/renquant-backtesting")
PIPELINE_REPO = pathlib.Path("/Users/renhao/git/github/renquant-pipeline")
SERVED_ARTIFACT = (RQ / "backtesting" / "renquant_104" / "artifacts" /
                   "momentum" / "2026-08-02" / "momentum_residual_v0.json")
LEDGER = (RQ / "backtesting" / "renquant_104" / "artifacts" / "momentum" /
          "momentum_artifact_ledger.jsonl")
LABEL = "fwd_60d_excess"
GATE_SHIFT_DAYS = 120          # the enforced placebo leg's own shift (2 x 60)
SHUFFLE_SEEDS = (1, 2, 3, 4, 5)

PRODUCERS = ("build_regime_series", "regime_diagnostics",
             "regime_shift_diagnostics")


class ServedParamsChanged(RuntimeError):
    """Registration §1: this study is void for a different params fingerprint."""


class ServedArtifactNotLedgered(RuntimeError):
    """The artifact being reconstructed is not the one the ledger serves.

    [codex on orch#825] Reading the artifact FILE and trusting its own
    `content_sha256` proves only that the file is self-consistent. The served
    object is the ledger's row; an artifact on disk that no ledger row points at
    is not what the blend loads, and reconstructing it would answer a question
    about a file rather than about production.
    """


def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _digest_of_mapping(mapping: dict) -> str:
    payload = json.dumps(sorted(mapping.items()), separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _digest_of_rows(rows: list[tuple]) -> str:
    """Order-independent over a MULTISET of rows — duplicates are preserved."""
    payload = json.dumps(sorted(rows), separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _git_head(repo: pathlib.Path) -> str | None:
    """The revision of the code that produced the numbers.

    Recorded because "the served params are unchanged" does not mean "the
    construction is unchanged": the same params through revised feature code
    give different scores, and the payload would look identical
    `[codex on orch#825]`.
    """
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):       # pragma: no cover
        return None
    return out.stdout.strip() or None


def ledger_row_for(content_sha: str, ledger: pathlib.Path = LEDGER) -> dict:
    """The ledger row serving ``content_sha``, or REFUSE.

    [codex on orch#825, round 2] The first version only parsed JSON lines and
    matched a DECLARED sha. That is not verification: a forged-but-parseable
    ledger passed, and carrying `prev_row_sha` in the output made it look
    checked. The chain is now verified by the model package's own
    ``load_and_verify_ledger`` — row ordering, `prev_row_sha` linkage and each
    row's self-digest — rather than by a second implementation here that would
    drift exactly when it mattered.

    Fails closed on every branch: an absent ledger, a broken chain, a sha no
    row carries. "I could not check" must not read like "it checks out".
    """
    from renquant_model_momentum.ledger import (LedgerIntegrityError,
                                                load_and_verify_ledger)

    if not ledger.is_file():
        raise ServedArtifactNotLedgered(
            f"no momentum artifact ledger at {ledger} — the served object "
            "cannot be identified, so there is nothing to reconstruct")
    try:
        rows = load_and_verify_ledger(ledger)
    except LedgerIntegrityError as exc:
        raise ServedArtifactNotLedgered(
            f"{ledger} fails its own chain contract ({exc}) — a ledger that "
            "does not verify cannot identify the served object") from exc
    hit = [r for r in rows if r.get("artifact_content_sha256") == content_sha]
    if not hit:
        raise ServedArtifactNotLedgered(
            f"no ledger row carries artifact_content_sha256={content_sha!r} "
            f"({len(rows)} row(s) read) — the artifact on disk is not the one "
            "the blend serves, and registration §1 is void for it")
    row = hit[-1]
    return {
        "ledger_path": str(ledger),
        "chain_verified_by": "renquant_model_momentum.ledger.load_and_verify_ledger",
        "n_rows": len(rows),
        "row_sha": row.get("row_sha"),
        "row_index_from_end": len(rows) - rows.index(row),
        "is_ledger_tail": rows.index(row) == len(rows) - 1,
        "appended_at_utc": row.get("appended_at_utc"),
        "cutoff_date": row.get("cutoff_date"),
        "effective_train_cutoff_date": row.get("effective_train_cutoff_date"),
        "prev_row_sha": row.get("prev_row_sha"),
        "n_scored": row.get("n_scored"),
        "artifact_content_sha256": row.get("artifact_content_sha256"),
    }


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
    from renquant_model_momentum.train import (params_v0,
                                                verify_artifact_content_sha)

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    # RECOMPUTED, not read. The artifact's own content_sha256 is the identity
    # the ledger matches on; trusting the field it carries makes a corrupted
    # artifact indistinguishable from the served one [codex on orch#825].
    try:
        verify_artifact_content_sha(artifact)
    except ValueError as exc:
        raise ServedArtifactNotLedgered(
            f"{artifact_path}: {exc} — the artifact does not hash to the "
            "identity it claims, so it is not the served object") from exc
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
                progress_every: int = 100) -> tuple[pd.DataFrame, dict]:
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
    # The readers RECORD a sha for every surface they served. Discarding them
    # was the gap: a later run over revised OHLCV would report different
    # numbers under an identical-looking payload [codex on orch#825].
    return (out.dropna(subset=["mu", LABEL]).reset_index(drop=True),
            dict(readers.read_digests()))


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

    ledger = ledger_row_for(served["artifact"]["content_sha256"])
    print(f"served artifact is ledgered: cutoff {ledger['cutoff_date']}, "
          f"row {ledger['row_index_from_end']} from the end, "
          f"tail={ledger['is_ledger_tail']}", flush=True)

    print(f"scoring {panel['date'].nunique()} matured panel dates …", flush=True)
    scored, read_digests = score_panel(panel, served["params"], limit=limit)
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
            # WHAT WAS READ. Rolled up AND itemised: the roll-up is what a
            # mutation test compares, the itemisation is what an auditor reads.
            "input_read_digests_sha256": _digest_of_mapping(read_digests),
            "n_input_surfaces": len(read_digests),
            "panel_path": str(train_cli.PANEL_PATH),
            "panel_sha256": _sha256_file(train_cli.PANEL_PATH),
            # A canonical ORDERED LIST, not a dict: a (ticker, date) mapping
            # silently overwrites duplicate rows, so two scored tables that
            # differ only in duplicates would hash the same [codex on orch#825].
            "scored_table_sha256": _digest_of_rows(
                [(str(r.ticker), f"{r.date:%Y-%m-%d}", float(r.mu))
                 for r in scored.itertuples()]),
            "scored_table_n_rows": int(len(scored)),
            # WHAT CODE PRODUCED IT. Unchanged params through revised feature
            # code give different scores under an identical-looking payload.
            "code_revisions": {
                "renquant-orchestrator": _git_head(ORCH_REPO),
                "renquant-model": _git_head(MODEL_REPO),
                "renquant-backtesting": _git_head(BT_REPO),
                "renquant-pipeline": _git_head(PIPELINE_REPO),
            },
            "served_ledger_row": ledger,
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
        "input_read_digests": read_digests,
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
    except (ServedParamsChanged, ServedArtifactNotLedgered) as exc:
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
