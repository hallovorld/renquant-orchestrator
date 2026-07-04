"""Evaluation primitives: the placebo-difference discipline as functions.

Consolidates the C3 primitives that C2 imported verbatim and C4/RS-5
re-implemented (per-date cross-sectional Spearman IC, shifted-label placebo,
forward-excess labels), plus paired deltas (D3) and the matched-admission-
rate solver (the M4-b matched-breadth protocol).

House rule carried through: absolute IC is never trusted (the ~+0.04
embargo-leakage floor); verdicts read placebo-clean DIFFERENCES only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

__all__ = [
    "MatchedAdmission",
    "fwd_excess",
    "gate_shift_sessions",
    "paired_deltas",
    "per_date_ic",
    "shifted_label_placebo",
    "shifted_label_placebo_long",
    "solve_matched_admission",
    "spearman",
]

LABEL_CLIP = 0.5  # repo label convention (C3/RS-5; analyze_manifest_sanity_placebo)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Cross-sectional Spearman rank correlation (c3_residual_momentum._spearman
    semantics: pandas average ranks, demeaned rank correlation). Returns NaN on
    a degenerate cross-section."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = math.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else float("nan")


def per_date_ic(
    score: pd.DataFrame,
    label: pd.DataFrame,
    placebo: pd.DataFrame,
    *,
    min_names: int = 30,
) -> pd.DataFrame:
    """Per-date real IC, placebo IC, and clean = real - placebo.

    Verbatim c3_residual_momentum.per_date_ic semantics (imported by C2,
    re-implemented by RS-5): wide date x name frames; a date needs
    >= min_names scored names AND >= min_names label (resp. placebo) joins to
    contribute; clean_ic defined only where BOTH legs exist — the clean
    series therefore ends ~(horizon + shift) before the last bar.
    """
    rows = []
    for dt in score.index:
        s = score.loc[dt].dropna()
        if len(s) < min_names:
            continue
        rec: dict[str, object] = {"date": dt, "n_scored": int(len(s))}
        y = label.loc[dt, s.index].dropna()
        if len(y) >= min_names:
            rec["real_ic"] = spearman(s[y.index].to_numpy(), y.to_numpy())
            rec["n_real"] = int(len(y))
        yp = placebo.loc[dt, s.index].dropna()
        if len(yp) >= min_names:
            rec["placebo_ic"] = spearman(s[yp.index].to_numpy(), yp.to_numpy())
            rec["n_placebo"] = int(len(yp))
        if "real_ic" in rec and "placebo_ic" in rec:
            rec["clean_ic"] = rec["real_ic"] - rec["placebo_ic"]
        rows.append(rec)
    return pd.DataFrame(rows).set_index("date")


def fwd_excess(
    close: pd.DataFrame,
    bench_close: pd.Series,
    horizon: int,
    *,
    clip: float = LABEL_CLIP,
) -> pd.DataFrame:
    """fwd_h excess vs the benchmark, clipped (repo label convention):
    (close[t+h]/close[t] - 1) - (bench[t+h]/bench[t] - 1), clip +/-clip."""
    f_stock = close.shift(-horizon) / close - 1.0
    f_bench = bench_close.shift(-horizon) / bench_close - 1.0
    return f_stock.sub(f_bench, axis=0).clip(-clip, clip)


def gate_shift_sessions(label_horizon: int) -> int:
    """The repaired-WF-gate placebo shift convention: 2x the label horizon
    (renquant-backtesting wf_gate/runner.py `_gate_shift_days = 2 *
    _label_horizon`, mirrored by analyze_manifest_sanity_placebo.
    shift_diagnostics and msig_c4_trendscan GATE_SHIFT_SESS) — the real and
    placebo legs then share zero overlapping return windows."""
    return 2 * label_horizon


def shifted_label_placebo(label: pd.DataFrame, shift_sessions: int) -> pd.DataFrame:
    """Shifted-label placebo on a wide date x name label frame:
    placebo(t) = label(t + shift_sessions), i.e. `label.shift(-shift)`.

    Two frozen conventions exist in the corpus — pass the one YOUR spec froze:
    - shift = horizon (C2/C3/RS-5: "label_shifted_plus_horizon_within_ticker")
    - shift = gate_shift_sessions(horizon) = 2x horizon (C4 / repaired WF
      gate semantics — the S2 convention)
    """
    if shift_sessions <= 0:
        raise ValueError("shift_sessions must be positive")
    return label.shift(-shift_sessions)


def shifted_label_placebo_long(
    df: pd.DataFrame,
    *,
    label_col: str,
    shift_sessions: int,
    ticker_col: str = "ticker",
    date_col: str = "date",
    clip: float = LABEL_CLIP,
) -> pd.Series:
    """Long-frame variant (msig_c4_trendscan semantics): per-ticker shift of
    the raw label by -shift_sessions, clipped +/-clip. The frame is sorted
    (ticker, date) internally; the returned Series is aligned to df.index."""
    if shift_sessions <= 0:
        raise ValueError("shift_sessions must be positive")
    order = df.sort_values([ticker_col, date_col]).index
    sorted_df = df.loc[order]
    shifted = (
        sorted_df.groupby(ticker_col)[label_col].shift(-shift_sessions).clip(-clip, clip)
    )
    return shifted.reindex(df.index)


def paired_deltas(ic_a: pd.Series, ic_b: pd.Series) -> pd.Series:
    """Paired per-date delta series delta_t = a_t - b_t on the common,
    date-ordered index where both are finite (d3_core_shrink_check.
    _paired_delta_series semantics). Verdicts read PAIRED differences —
    'not two separate CIs compared by eye' — so the common embargo-leakage
    floor cancels."""
    joined = pd.concat({"a": ic_a, "b": ic_b}, axis=1).dropna().sort_index()
    return joined["a"] - joined["b"]


@dataclass
class MatchedAdmission:
    """Outcome of the matched-admission-rate solve."""

    param: float
    achieved: float
    target: float
    iterations: int
    converged: bool
    history: list[tuple[float, float]]


def solve_matched_admission(
    admission_fn: Callable[[float], float],
    target: float,
    lo: float,
    hi: float,
    *,
    increasing: bool | None = None,
    tol: float = 0.0,
    max_iter: int = 60,
) -> MatchedAdmission:
    """Solve the single free parameter so the candidate arm's admission
    breadth matches the baseline's (the M4-b matched-breadth protocol: a
    replay is only interpretable arm-vs-arm when both arms admit the same
    number of names; one parameter — e.g. a floor or haircut k — is solved
    to match baseline breadth, never hand-tuned).

    `admission_fn(param)` returns the admission count/rate at `param` and is
    assumed monotone on [lo, hi]. Bisection; admission counts are integer
    step functions, so exact equality may be unreachable — the solver
    converges to the bracket edge whose achieved value is closest to target
    (ties -> the more conservative, lower-admission side).
    """
    f_lo = float(admission_fn(lo))
    f_hi = float(admission_fn(hi))
    history: list[tuple[float, float]] = [(lo, f_lo), (hi, f_hi)]
    if increasing is None:
        increasing = f_hi >= f_lo
    # normalize so g is non-decreasing in param
    def g(x: float) -> float:
        v = float(admission_fn(x))
        history.append((x, v))
        return v

    g_lo, g_hi = (f_lo, f_hi) if increasing else (f_hi, f_lo)
    lo_p, hi_p = (lo, hi) if increasing else (hi, lo)
    if not (min(g_lo, g_hi) <= target <= max(g_lo, g_hi)):
        # target outside the bracket: return the closer edge, honestly marked
        best = min(history[:2], key=lambda t: (abs(t[1] - target), t[1]))
        return MatchedAdmission(
            param=best[0], achieved=best[1], target=target,
            iterations=0, converged=False, history=history,
        )
    it = 0
    a, b = lo_p, hi_p
    fa, fb = g_lo, g_hi
    while it < max_iter:
        it += 1
        mid = 0.5 * (a + b)
        fm = g(mid)
        if abs(fm - target) <= tol:
            return MatchedAdmission(
                param=mid, achieved=fm, target=target,
                iterations=it, converged=True, history=history,
            )
        if fm < target:
            a, fa = mid, fm
        else:
            b, fb = mid, fm
    # closest of the final bracket (ties -> lower admission = conservative)
    candidates = [(a, fa), (b, fb)]
    best = min(candidates, key=lambda t: (abs(t[1] - target), t[1]))
    return MatchedAdmission(
        param=best[0], achieved=best[1], target=target,
        iterations=it, converged=abs(best[1] - target) <= max(tol, 0.0),
        history=history,
    )
