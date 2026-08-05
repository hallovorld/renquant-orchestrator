#!/usr/bin/env python3
"""Arm A of the FROZEN prereg `doc/research/2026-08-05-goal7-momentum-per-regime-prereg.md`.

Arm A is the RECONSTRUCTION arm: recompute the momentum score from history with
the served params and measure `E1(R)` — the mean per-date Spearman IC against
`fwd_60d_excess`, per production regime — with its matched placebos. It is
EXPLORATORY by registration: it can motivate, it cannot certify. Only Arm B (the
served ledger, ≥30 matured BULL_CALM dates) certifies, and that is calendar-
blocked to roughly 2027.

WHY THIS FILE IS THIN, ON PURPOSE. The registered estimand already has an
implementation — the WF gate's own, the same code that produced the BEAR/
BULL_CALM numbers in orch#805/#807:

    build_regime_series(dates)          -> the PRODUCTION regime chain per date
    regime_diagnostics(val, mu, label, regimes)
                                        -> {regime: summarize_ic(...)} with
                                           mean_ic / median_ic / std_ic /
                                           hit_rate / n_dates / n_rows
    regime_shift_diagnostics(..., shifts=(120,))
                                        -> the same, on the 2x-shifted label

Writing a second statistical harness beside a reviewed one is how two answers to
the same question appear. This module supplies inputs and applies the frozen
decision predicate; it computes no statistic of its own.

NOT A RUN. This is the harness. Running Arm A is a separate, deliberate act.
"""
from __future__ import annotations

import argparse
import json
import sys

# The FROZEN predicate, transcribed from §6 of the registration. Arm A reports
# it for information; only Arm B may CERTIFY on it.
PRIMARY_REGIME = "BULL_CALM"
MIN_DATES_PRIMARY = 30
GATE_SHIFT_DAYS = 120          # the enforced placebo leg's own shift (2 x 60)
N_SHUFFLE_REPS = 5
SHUFFLE_SEEDS = (1, 2, 3, 4, 5)


class ArmMisuse(RuntimeError):
    """Raised when a caller tries to certify on Arm A. Registration §3."""


def genuine(ic: float | None, placebo: float | None) -> float | None:
    if ic is None or placebo is None:
        return None
    return float(ic) - float(placebo)


def evaluate_predicate(*, arm: str, per_regime: dict) -> dict:
    """Apply §6's four conditions. Returns a verdict block; never raises except
    on an attempt to certify from Arm A.

    `per_regime[R]` must carry `mean_ic`, `n_dates`, `placebo_shuffle` (the MAX
    over the 5 fixed-seed replications — the WORST case, §4) and `placebo_shift`.
    """
    if arm not in ("A", "B"):
        raise ValueError(f"arm must be 'A' or 'B', got {arm!r}")
    cell = per_regime.get(PRIMARY_REGIME) or {}
    ic = cell.get("mean_ic")
    n_dates = cell.get("n_dates")
    g_shuffle = genuine(ic, cell.get("placebo_shuffle"))
    g_shift = genuine(ic, cell.get("placebo_shift"))

    conditions = {
        "n_dates>=30": (isinstance(n_dates, int) and n_dates >= MIN_DATES_PRIMARY),
        "E1>0": (isinstance(ic, (int, float)) and ic > 0),
        "E1>max_shuffle": (g_shuffle is not None and g_shuffle > 0),
        "E1>placebo_shift": (g_shift is not None and g_shift > 0),
    }
    met = all(conditions.values())
    verdict = {
        "arm": arm,
        "primary_regime": PRIMARY_REGIME,
        "mean_ic": ic,
        "n_dates": n_dates,
        "genuine_vs_shuffle": g_shuffle,
        "genuine_vs_shift": g_shift,
        "conditions": conditions,
        "failed_conditions": sorted(k for k, v in conditions.items() if not v),
    }
    if arm == "B":
        verdict["outcome"] = "CERTIFIED" if met else "NOT CERTIFIED"
        verdict["meaning"] = (
            "the member met this preregistered evidence standard" if met else
            "the member did NOT meet this preregistered evidence standard — "
            "NOT a finding that the signal is absent; the predicate is "
            "deliberately conservative (worst-of-5 shuffles)")
    else:
        verdict["outcome"] = "EXPLORATORY — NOT A CERTIFICATION"
        verdict["meaning"] = (
            "Arm A is a reconstruction, not the served artifact. Registration "
            "§3: it can motivate running Arm B or designing a different "
            "candidate; it cannot certify, whatever the numbers say")
    return verdict


def certify(verdict: dict) -> str:
    """Guard the one misuse the registration names. Arm A can never certify."""
    if verdict.get("arm") != "B":
        raise ArmMisuse(
            "Arm A cannot certify (registration §3). Only Arm B — the SERVED "
            "ledger with >=30 matured BULL_CALM dates — may produce a verdict.")
    return verdict["outcome"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-regime-json", required=True,
                    help="path to a JSON {regime: {mean_ic, n_dates, "
                         "placebo_shuffle, placebo_shift}} produced by the "
                         "gate's own regime_diagnostics / regime_shift_diagnostics")
    ap.add_argument("--arm", choices=("A", "B"), default="A")
    args = ap.parse_args(argv)
    with open(args.per_regime_json, encoding="utf-8") as fh:
        per_regime = json.load(fh)
    print(json.dumps(evaluate_predicate(arm=args.arm, per_regime=per_regime),
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
