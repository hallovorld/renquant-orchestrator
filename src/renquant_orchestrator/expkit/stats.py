"""Statistics: gap-respecting block bootstrap + the automatic small-n branch.

Bootstrap core = c3_residual_momentum.block_bootstrap_conditional_mean /
block_bootstrap_diff, kept numerically bit-identical (C2 imported them
verbatim; C4 re-implemented them as carried_mask_block_bootstrap; RS-5 as
bootstrap_mask_removed_mean). The carried-mask design is the round-2 fix:
blocks are drawn over the FULL dated series with the cell mask carried
through — never over a pre-filtered in-cell subseries, which would splice
regime episodes separated by a calendar gap.

Small-n branch = the V3 method note (doc/research/2026-07-03-m3-verification.md),
codified: "with <~15 dates, report exact-enumeration tail masses instead of
MC quantile CIs, always pair a null control (empirical size) with any
significance claim, and treat the date-block bootstrap as unusable when
n_dates/block_len < ~4." `bootstrap_or_exact` applies it AUTOMATICALLY.

Multi-seed unanimity = the #264 lesson (D3 frozen spec seed_unanimity_basis):
"the gate statistic moves ~±0.02 across training seeds, so single-seed reads
against a ±0.01 band are under-powered; unanimity over 3 seeds is the
protection." Seeds are a robustness check on one corrected result, not extra
looks — never Bonferroni-counted.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

import numpy as np

__all__ = [
    "EXACT_ENUM_LIMIT",
    "SMALL_N_MIN_USABLE_BLOCKS",
    "SmallNExactResult",
    "block_bootstrap_conditional_mean",
    "block_bootstrap_diff",
    "bootstrap_admissible",
    "bootstrap_or_exact",
    "exact_block_tail_masses",
    "exact_sign_test",
    "multi_seed_unanimity",
    "summarize_boot",
    "usable_blocks",
]

#: V3 method note: the date-block bootstrap is unusable when
#: n_dates / block_len < ~4.
SMALL_N_MIN_USABLE_BLOCKS = 4

#: m3_independent_verification.exact_block_bootstrap enumeration budget:
#: the bootstrap distribution is exact only when n**n_blocks is enumerable.
EXACT_ENUM_LIMIT = 300_000


def usable_blocks(n_dates: int, block: int) -> int:
    """Number of full non-overlapping date blocks in the series."""
    if block < 1:
        raise ValueError("block must be >= 1")
    return n_dates // block


def bootstrap_admissible(
    n_dates: int, block: int, *, min_usable_blocks: int = SMALL_N_MIN_USABLE_BLOCKS
) -> bool:
    return usable_blocks(n_dates, block) >= min_usable_blocks and n_dates > block


def block_bootstrap_conditional_mean(
    vals: np.ndarray,
    in_cell: np.ndarray,
    *,
    block: int,
    n_boot: int,
    seed: int,
) -> np.ndarray | None:
    """Conditioned-cell mean bootstrap: resample date-BLOCKS OF THE FULL
    SERIES (never a pre-filtered in-cell-only array), then average only the
    in-cell values inside each drawn block.

    Numerically bit-identical to c3_residual_momentum.
    block_bootstrap_conditional_mean (the C2 evidence reproduces against this
    implementation exactly). For the unconditional mean pass an all-True mask.
    """
    vals = np.asarray(vals, dtype=float)
    in_cell = np.asarray(in_cell)
    mask_fin = np.isfinite(vals)
    a = vals[mask_fin]
    c = in_cell[mask_fin].astype(bool)
    n = len(a)
    if n < 2 or block < 1 or n <= block or c.sum() < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block
    means = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        av = a[idx]
        cv = c[idx]
        n_in = cv.sum()
        means[i] = av[cv].mean() if n_in >= 2 else np.nan
    means = means[np.isfinite(means)]
    return means if len(means) else None


def block_bootstrap_diff(
    vals: np.ndarray,
    in_cell: np.ndarray,
    *,
    block: int,
    n_boot: int,
    seed: int,
) -> np.ndarray | None:
    """Paired difference bootstrap: per resample of full-series date blocks,
    mean(in-cell) - mean(all). Preserves the pairing/overlap structure
    ('computed via the paired daily difference series ... not two separate
    CIs compared by eye'). Bit-identical to c3_residual_momentum.
    block_bootstrap_diff."""
    vals = np.asarray(vals, dtype=float)
    in_cell = np.asarray(in_cell)
    mask_fin = np.isfinite(vals)
    a = vals[mask_fin]
    c = in_cell[mask_fin].astype(bool)
    n = len(a)
    if n < 2 or block < 1 or n <= block or c.sum() < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        av = a[idx]
        cv = c[idx]
        n_in = cv.sum()
        diffs[i] = (av[cv].mean() - av.mean()) if n_in >= 2 else np.nan
    diffs = diffs[np.isfinite(diffs)]
    return diffs if len(diffs) else None


def summarize_boot(
    means: np.ndarray | None, *, alpha_one_sided: float
) -> dict[str, Any] | None:
    """Two-sided 95% CI + one-sided Bonferroni-adjusted bounds from the SAME
    resamples (c3_residual_momentum.summarize_boot, alpha made explicit —
    D3 0.05/12, RS-5 0.05/4, M-SIG 0.05/3)."""
    if means is None:
        return None
    lo95, hi95 = np.percentile(means, [2.5, 97.5])
    lb, ub = np.percentile(means, [100 * alpha_one_sided, 100 * (1 - alpha_one_sided)])
    return {
        "boot_se": float(means.std(ddof=1)),
        "ci95_two_sided": [float(lo95), float(hi95)],
        "lb_one_sided": float(lb),
        "ub_one_sided": float(ub),
        "alpha_one_sided": float(alpha_one_sided),
        "n_boot_effective": int(len(means)),
    }


@dataclass
class SmallNExactResult:
    """Exact-enumeration replacement for the refused bootstrap.

    `requires_null_control=True` always: per the V3 method note, a
    significance claim from this method is inadmissible without a paired
    null control demonstrating empirical size (the M3 verifier measured a
    28.4% false-positive rate on machinery that looked significant).

    `p_ge_threshold`/`p_le_threshold` are the method's RAW tail masses and
    their meaning DIFFERS by method: for `exact_block_tail_masses` they are
    tail masses of the (data-centered) bootstrap resample-mean distribution;
    for `exact_sign_test` they are null-hypothesis (p=0.5) binomial tail
    p-values. The two conventions have OPPOSITE GO/KILL orientation, so the
    verdict layer must never read them directly — it reads the explicitly
    oriented `go_evidence_p` / `kill_evidence_p` instead (small
    go_evidence_p = evidence the effect exceeds the threshold; small
    kill_evidence_p = evidence it is below)."""

    method: str
    n_dates: int
    block: int
    n_tuples: int
    mean: float
    p_ge_threshold: float
    p_le_threshold: float
    two_sided_p: float
    go_evidence_p: float
    kill_evidence_p: float
    threshold: float
    exact: bool
    requires_null_control: bool = True
    detail: dict[str, Any] = field(default_factory=dict)


def exact_block_tail_masses(
    vals: np.ndarray,
    *,
    block: int,
    threshold: float = 0.0,
    enum_limit: int = EXACT_ENUM_LIMIT,
) -> SmallNExactResult:
    """Exact circular-block-bootstrap tail masses
    (m3_independent_verification.exact_block_bootstrap): the circular block
    resample is fully determined by the tuple of block starts (each uniform
    on n, ceil(n/block) blocks, truncated to n dates). When n**n_blocks is
    enumerable the bootstrap distribution is EXACT — no Monte Carlo noise,
    no seed, no quantile-indexing convention. Significance reduces to exact
    tail masses P(mean >= threshold) / P(mean <= threshold).

    Falls back to the exact sign test when enumeration is infeasible.
    """
    a = np.asarray([v for v in np.asarray(vals, dtype=float) if np.isfinite(v)])
    n = len(a)
    if n == 0:
        raise ValueError("empty series")
    n_blocks = math.ceil(n / block)
    n_tuples = n**n_blocks
    if n_tuples > enum_limit:
        sign = exact_sign_test(a, threshold=threshold)
        sign.detail["fallback_reason"] = (
            f"n_tuples={n_tuples} exceeds enum_limit={enum_limit}"
        )
        return sign
    lens = [block] * n_blocks
    lens[-1] = n - block * (n_blocks - 1)
    means = []
    for starts in itertools.product(range(n), repeat=n_blocks):
        total = 0.0
        count = 0
        for b, s in enumerate(starts):
            for off in range(lens[b]):
                total += a[(s + off) % n]
                count += 1
        means.append(total / count)
    m = np.sort(np.asarray(means))
    p_ge = float(np.sum(m >= threshold)) / len(m)
    p_le = float(np.sum(m <= threshold)) / len(m)
    return SmallNExactResult(
        method="exact_block_tail_masses",
        n_dates=n,
        block=block,
        n_tuples=int(n_tuples),
        mean=float(a.mean()),
        p_ge_threshold=p_ge,
        p_le_threshold=p_le,
        two_sided_p=min(1.0, 2 * min(p_ge, p_le)),
        # bootstrap-distribution orientation: LB > threshold <=> almost no
        # resample mass at or below the threshold
        go_evidence_p=p_le,
        kill_evidence_p=p_ge,
        threshold=float(threshold),
        exact=True,
        detail={
            "dist_min": float(m[0]),
            "dist_max": float(m[-1]),
            "ci95_lower_interp": float(np.percentile(m, 2.5)),
            "ci95_upper_interp": float(np.percentile(m, 97.5)),
        },
    )


def exact_sign_test(vals: np.ndarray, *, threshold: float = 0.0) -> SmallNExactResult:
    """Exact binomial sign test of the per-date values against `threshold`
    (ties dropped): distribution-free exact tail masses for tiny samples."""
    a = np.asarray([v for v in np.asarray(vals, dtype=float) if np.isfinite(v)])
    n = len(a)
    if n == 0:
        raise ValueError("empty series")
    above = int(np.sum(a > threshold))
    below = int(np.sum(a < threshold))
    m = above + below  # ties dropped
    if m == 0:
        p_ge = p_le = 1.0
    else:
        p_ge = sum(math.comb(m, k) for k in range(above, m + 1)) / 2.0**m
        p_le = sum(math.comb(m, k) for k in range(0, above + 1)) / 2.0**m
    return SmallNExactResult(
        method="exact_sign_test",
        n_dates=n,
        block=1,
        n_tuples=int(2**m) if m < 64 else -1,
        mean=float(a.mean()),
        p_ge_threshold=float(p_ge),
        p_le_threshold=float(p_le),
        two_sided_p=float(min(1.0, 2 * min(p_ge, p_le))),
        # null-hypothesis orientation (OPPOSITE of the tail-mass method):
        # a small P(>= this many above | p=.5) is GO evidence
        go_evidence_p=float(p_ge),
        kill_evidence_p=float(p_le),
        threshold=float(threshold),
        exact=True,
        detail={"n_above": above, "n_below": below, "n_ties_dropped": n - m},
    )


def bootstrap_or_exact(
    vals: np.ndarray,
    *,
    block: int,
    n_boot: int,
    seeds: Iterable[int],
    alpha_one_sided: float,
    in_cell: np.ndarray | None = None,
    threshold: float = 0.0,
    min_usable_blocks: int = SMALL_N_MIN_USABLE_BLOCKS,
) -> dict[str, Any]:
    """The automatic small-n branch (V3 method note, codified).

    - If usable blocks >= min_usable_blocks: per-seed carried-mask block
      bootstrap; returns {"method": "block_bootstrap", "by_seed": {...}}.
    - Otherwise the bootstrap is REFUSED (never silently run degenerate):
      returns {"method": "exact", ...} with exact tail masses and
      `requires_null_control: True` — the verdict layer refuses GO/KILL from
      this branch without a passed null control.
    """
    a = np.asarray(vals, dtype=float)
    fin = a[np.isfinite(a)]
    n = len(fin)
    if bootstrap_admissible(n, block, min_usable_blocks=min_usable_blocks):
        mask = (
            np.ones(len(a), dtype=bool) if in_cell is None else np.asarray(in_cell, dtype=bool)
        )
        by_seed = {
            str(s): summarize_boot(
                block_bootstrap_conditional_mean(
                    a, mask, block=block, n_boot=n_boot, seed=int(s)
                ),
                alpha_one_sided=alpha_one_sided,
            )
            for s in seeds
        }
        return {
            "method": "block_bootstrap",
            "n_dates": n,
            "block": block,
            "usable_blocks": usable_blocks(n, block),
            "by_seed": by_seed,
            "requires_null_control": False,
        }
    if in_cell is not None:
        fin = a[np.isfinite(a) & np.asarray(in_cell, dtype=bool)]
        n = len(fin)
        if n == 0:
            raise ValueError("no finite in-cell values")
    exact = exact_block_tail_masses(fin, block=block, threshold=threshold)
    return {
        "method": "exact",
        "n_dates": n,
        "block": block,
        "usable_blocks": usable_blocks(n, block),
        "refusal": (
            f"date-block bootstrap refused: usable blocks {usable_blocks(n, block)} < "
            f"{min_usable_blocks} (V3 method note: n_dates/block < ~4 makes the "
            "date-block bootstrap unusable)"
        ),
        "exact": exact,
        "requires_null_control": True,
    }


def multi_seed_unanimity(
    by_seed: Mapping[str, Any],
    predicate: Callable[[Any], bool],
) -> dict[str, Any]:
    """The #264 lesson as a helper: evaluate `predicate` per seed summary and
    report unanimity. A split across seeds is INCONCLUSIVE evidence, never a
    cherry-pick. A None summary (degenerate resample) fails the seed."""
    per_seed = {
        str(k): bool(v is not None and predicate(v)) for k, v in by_seed.items()
    }
    values = list(per_seed.values())
    return {
        "per_seed": per_seed,
        "unanimous_true": bool(values) and all(values),
        "unanimous_false": bool(values) and not any(values),
        "split": bool(values) and (any(values) and not all(values)),
        "n_seeds": len(values),
    }
