"""The attribution identity (107 sprint D3): per-decision P&L decomposition.

For one round trip (or one open position marked at the latest recorded
close), with

- ``N_i``  intended notional (kelly_target_pct x portfolio_value),
- ``N_r``  realized notional (shares x confirmed entry fill),
- ``r_ref``  = ref_exit / ref_entry − 1   (decision-session reference closes),
- ``r_spy``  = spy_exit / spy_entry − 1   (benchmark over the same window),
- ``r_real`` = exit_px / entry_px − 1     (confirmed fills),
- ``cost``   = fees + half-spread proxy (explicit, flagged when estimated),

the identity is::

    TOTAL  =  N_r * r_real − cost
           =  MARKET + SIGNAL + SIZING + TIMING + COST      (RESIDUAL ≡ 0)

    MARKET = N_i * r_spy                    benchmark/beta component
    SIGNAL = N_i * (r_ref − r_spy)          the pick vs benchmark, at
                                            intended sizing, reference prices
    SIZING = (N_r − N_i) * r_ref            realized vs intended notional —
                                            shrinkage stack + whole-share
                                            artifact land here
    TIMING = N_r * (r_real − r_ref)         fill prices vs the session
                                            reference — the entry-slippage
                                            leak (POC-C +23–49 bps) lands here
    COST   = −(fees + spread_proxy)

The sum is exact by construction (MARKET+SIGNAL = N_i*r_ref; +SIZING =
N_r*r_ref; +TIMING = N_r*r_real), so RESIDUAL = TOTAL − Σlegs must be ~0 up
to float noise; :func:`decompose_round_trip` computes it and stamps
``sum_check.ok``, and :func:`assert_identity` raises on any violation.

Censoring (HARD honesty rule): when an input is missing — unconfirmed entry
fill (#253: no fill-confirmation writer since 2026-05-22 on the live path),
unconfirmed exit, missing reference close, missing intended notional — every
leg that needs it is reported as ``None`` with an explicit machine-readable
reason in ``censored``; nothing is ever imputed, and the sum-check is only
emitted for fully decomposable records.
"""
from __future__ import annotations

from typing import Any, Mapping

LEG_NAMES = ("market", "signal", "sizing", "timing", "cost")

# Censoring reasons (machine-readable; keep stable — reports key on them).
CENSOR_ENTRY_FILL = "entry_fill_unconfirmed(#253: no fill-confirmation writer)"
CENSOR_EXIT_FILL = "exit_fill_unconfirmed(submit-time reference only)"
CENSOR_NO_INTENDED = "no_intended_notional(kelly_target_pct or portfolio_value missing)"
CENSOR_NO_REF_ENTRY = "no_reference_price(entry session close missing)"
CENSOR_NO_REF_EXIT = "no_reference_price(exit session close missing)"
CENSOR_NO_BENCH = "no_benchmark_price(SPY close missing)"
CENSOR_SHARES_CONFLICT = (
    "conflicting_re_records(share count varies across cross-day re-recorded rows)"
)
CENSOR_UNMATCHED_EXIT = "exit_unmatched(no in-window entry decision)"

SUM_CHECK_ABS_TOL = 1e-6  # dollars; identity is exact, this is float noise


def _ret(a: float | None, b: float | None) -> float | None:
    """b/a - 1 when both present and a != 0."""
    if a is None or b is None or a == 0:
        return None
    return b / a - 1.0


def decompose_round_trip(
    rec: Mapping[str, Any],
    half_spread_bps: float = 0.0,
) -> dict[str, Any]:
    """Decompose one ledger round-trip record (see
    :func:`renquant_orchestrator.attribution.ledger.build_round_trips`) into
    the five legs + enforced sum-check.

    ``half_spread_bps`` > 0 adds an *estimated* spread cost per traded side
    (flagged ``cost_is_estimate``); default 0 keeps the COST leg to recorded
    fees only (none are recorded in the current DB — commission-free broker).
    """
    legs: dict[str, float | None] = {name: None for name in LEG_NAMES}
    censored: dict[str, str] = {}
    status = rec.get("status")

    if status == "exit_unmatched":
        for name in LEG_NAMES:
            censored[name] = CENSOR_UNMATCHED_EXIT
        return _result(rec, legs, censored, total=None, diagnostics={})

    n_i = rec.get("intended_notional")
    n_r = rec.get("realized_notional")
    entry_px = rec.get("entry_px")
    exit_px = rec.get("exit_px")
    ref_entry = rec.get("ref_entry_px")
    ref_exit = rec.get("ref_exit_px")
    spy_entry = rec.get("spy_entry_px")
    spy_exit = rec.get("spy_exit_px")
    entry_confirmed = bool(rec.get("entry_fill_confirmed"))
    exit_confirmed = rec.get("exit_fill_confirmed")  # None for open_mtm

    r_ref = _ret(ref_entry, ref_exit)
    r_spy = _ret(spy_entry, spy_exit)
    # Open positions: exit_px is the same recorded close as ref_exit (set by
    # the ledger) so r_real - r_ref isolates ENTRY timing; a closed trip needs
    # a confirmed exit fill for r_real.
    exit_leg_ok = status == "open_mtm" or exit_confirmed is True
    r_real = _ret(entry_px, exit_px) if (entry_confirmed and exit_leg_ok) else None

    # --- input-availability reasons, most specific first ---------------------
    entry_reason = None if entry_confirmed else CENSOR_ENTRY_FILL
    exit_reason = None if exit_leg_ok else CENSOR_EXIT_FILL
    ref_reason = (
        CENSOR_NO_REF_ENTRY if (ref_entry is None or ref_entry == 0)
        else (CENSOR_NO_REF_EXIT if (ref_exit is None or ref_exit == 0) else None)
    )
    bench_reason = CENSOR_NO_BENCH if (spy_entry in (None, 0) or spy_exit is None) else None
    intended_reason = CENSOR_NO_INTENDED if n_i is None else None

    # MARKET = N_i * r_spy
    if intended_reason or bench_reason:
        censored["market"] = intended_reason or bench_reason
    else:
        legs["market"] = n_i * r_spy

    # SIGNAL = N_i * (r_ref - r_spy)
    if intended_reason or ref_reason or bench_reason:
        censored["signal"] = intended_reason or ref_reason or bench_reason
    else:
        legs["signal"] = n_i * (r_ref - r_spy)

    # A confirmed fill can still have an ambiguous share count when cross-day
    # re-records disagree (ledger shares_conflict) — distinct censor reason.
    no_notional_reason = (
        CENSOR_SHARES_CONFLICT if rec.get("shares_conflict") else CENSOR_ENTRY_FILL
    )

    # SIZING = (N_r - N_i) * r_ref  — needs the confirmed fill for N_r
    if entry_reason or intended_reason or ref_reason or n_r is None:
        censored["sizing"] = entry_reason or intended_reason or ref_reason or no_notional_reason
    else:
        legs["sizing"] = (n_r - n_i) * r_ref

    # TIMING = N_r * (r_real - r_ref)
    if entry_reason or exit_reason or ref_reason or n_r is None or r_real is None:
        censored["timing"] = entry_reason or exit_reason or ref_reason or no_notional_reason
    else:
        legs["timing"] = n_r * (r_real - r_ref)

    # COST = -(fees + spread proxy); spread proxy needs the traded notionals
    fees = rec.get("fees") or 0.0
    cost_is_estimate = False
    if entry_reason or n_r is None:
        censored["cost"] = entry_reason or no_notional_reason
    else:
        spread = 0.0
        if half_spread_bps:
            cost_is_estimate = True
            spread += (half_spread_bps / 1e4) * n_r  # entry side
            if status == "closed" and exit_px is not None and rec.get("shares") is not None:
                spread += (half_spread_bps / 1e4) * (rec["shares"] * exit_px)
        legs["cost"] = -(fees + spread)

    # TOTAL (net) = N_r * r_real + cost_leg — computable iff both fills known
    total: float | None = None
    if n_r is not None and r_real is not None and legs["cost"] is not None:
        total = n_r * r_real + legs["cost"]

    diagnostics = {
        "r_ref": r_ref,
        "r_spy": r_spy,
        "r_real": r_real,
        "intended_notional": n_i,
        "realized_notional": n_r,
        "entry_slippage_bps": (
            (entry_px / ref_entry - 1.0) * 1e4
            if (entry_confirmed and entry_px is not None and ref_entry not in (None, 0))
            else None
        ),
        "exit_slippage_bps": (
            (exit_px / ref_exit - 1.0) * 1e4
            if (status == "closed" and exit_confirmed and exit_px is not None and ref_exit not in (None, 0))
            else None
        ),
        "cost_is_estimate": cost_is_estimate,
    }
    return _result(rec, legs, censored, total, diagnostics)


def _result(
    rec: Mapping[str, Any],
    legs: dict[str, float | None],
    censored: dict[str, str],
    total: float | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    sum_check = None
    if total is not None and all(legs[name] is not None for name in LEG_NAMES):
        legs_sum = sum(legs[name] for name in LEG_NAMES)  # type: ignore[misc]
        residual = total - legs_sum
        sum_check = {
            "total": total,
            "legs_sum": legs_sum,
            "residual": residual,
            "ok": abs(residual) <= SUM_CHECK_ABS_TOL,
        }
    return {
        "decision_id": rec.get("decision_id"),
        "date": rec.get("date"),
        "exit_date": rec.get("exit_date"),
        "ticker": rec.get("ticker"),
        "status": rec.get("status"),
        "regime": rec.get("regime"),
        "run_type": rec.get("run_type"),
        "mu": rec.get("mu"),
        "rank_score": rec.get("rank_score"),
        "blocked_by": rec.get("blocked_by"),
        "exit_reason": rec.get("exit_reason"),
        "legs": legs,
        "censored": censored,
        "total_pnl": total,
        "sum_check": sum_check,
        "diagnostics": diagnostics,
    }


def assert_identity(results: list[dict[str, Any]]) -> None:
    """Enforce the identity: every fully-decomposed record's residual must be
    ~0. Raises ``AssertionError`` naming the first offending decision —
    a nonzero residual means the decomposition code is wrong, never the data.
    """
    for r in results:
        sc = r.get("sum_check")
        if sc is not None and not sc["ok"]:
            raise AssertionError(
                f"attribution identity violated for {r['decision_id']}: "
                f"total={sc['total']:.10f} legs_sum={sc['legs_sum']:.10f} "
                f"residual={sc['residual']:.3e}"
            )
