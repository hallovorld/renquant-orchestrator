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
    """Raised on any attempt to certify from this module. Registration §3."""


class ProvenanceMissing(RuntimeError):
    """The per-regime input does not declare that it came from the gate's own
    helpers. [codex on orch#816] Without this the runner accepted ANY JSON from
    ANY source while the write-up claimed it was 'built on the gate's own
    statistics' — a claim the runtime did not enforce."""


# The exact producers the registration's estimand is computed by. An input that
# does not name all of them is refused: this module orchestrates those helpers'
# output and must be able to say so about the numbers it judges.
REQUIRED_PRODUCERS = ("build_regime_series", "regime_diagnostics",
                      "regime_shift_diagnostics")


def require_gate_provenance(payload: dict) -> dict:
    """Return the per-regime block, or raise. Fails CLOSED on any doubt."""
    prov = (payload or {}).get("provenance")
    if not isinstance(prov, dict):
        raise ProvenanceMissing(
            "input carries no `provenance` block — this runner judges numbers "
            f"produced by {', '.join(REQUIRED_PRODUCERS)} and cannot verify "
            "an unattributed payload")
    producers = prov.get("producers")
    missing = [p for p in REQUIRED_PRODUCERS
               if not isinstance(producers, (list, tuple)) or p not in producers]
    if missing:
        raise ProvenanceMissing(
            f"`provenance.producers` does not name {missing} — refusing to "
            f"apply the registered predicate to numbers of unknown origin")
    per_regime = (payload or {}).get("per_regime")
    if not isinstance(per_regime, dict):
        raise ProvenanceMissing("input carries no `per_regime` block")
    return per_regime


def genuine(ic: float | None, placebo: float | None) -> float | None:
    if ic is None or placebo is None:
        return None
    return float(ic) - float(placebo)


def evaluate_predicate(per_regime: dict) -> dict:
    """Apply §6's four conditions and report them EXPLORATORILY.

    [codex on orch#816] An earlier version took an `arm` argument and returned
    CERTIFIED for `arm="B"`. That made an Arm-A-named runner able to certify by
    passing a string — the frozen distinction in §3 undone by an argument. This
    module is Arm A. It has no Arm B path, and it cannot grow one by being
    called differently: Arm B is the SERVED ledger and is calendar-blocked to
    roughly 2027, so its runner does not exist yet and should not be faked here.

    `per_regime[R]` must carry `mean_ic`, `n_dates`, `placebo_shuffle` (the MAX
    over the 5 fixed-seed replications — the WORST case, §4) and `placebo_shift`.
    """
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
    return {
        "arm": "A",
        "primary_regime": PRIMARY_REGIME,
        "mean_ic": ic,
        "n_dates": n_dates,
        "genuine_vs_shuffle": g_shuffle,
        "genuine_vs_shift": g_shift,
        "conditions": conditions,
        "failed_conditions": sorted(k for k, v in conditions.items() if not v),
        "outcome": "EXPLORATORY — NOT A CERTIFICATION",
        "meaning": (
            "Arm A is a reconstruction, not the served artifact. Registration "
            "§3: it can motivate running Arm B or designing a different "
            "candidate; it cannot certify, whatever the numbers say. Even all "
            "four conditions holding here certifies nothing."),
    }


def certify(verdict: dict) -> str:
    """ALWAYS raises. This module is Arm A; Arm A cannot certify (§3).

    Kept as a function so the misuse has one loud place to land rather than
    being an absence someone reimplements.
    """
    raise ArmMisuse(
        "this is the Arm A runner and Arm A cannot certify (registration §3). "
        "Only Arm B — the SERVED ledger with >=30 matured BULL_CALM dates, "
        "calendar-blocked to roughly 2027 — may produce a verdict, and its "
        f"runner does not exist yet. Verdict was: {verdict.get('outcome')!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input-json", required=True,
                    help="a JSON payload with a `provenance.producers` list "
                         "naming the gate helpers and a `per_regime` block of "
                         "{mean_ic, n_dates, placebo_shuffle, placebo_shift}")
    args = ap.parse_args(argv)
    with open(args.input_json, encoding="utf-8") as fh:
        payload = json.load(fh)
    try:
        per_regime = require_gate_provenance(payload)
    except ProvenanceMissing as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps(evaluate_predicate(per_regime), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
