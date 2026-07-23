"""Power / minimum-detectable-effect (MDE) analysis for cross-sectional IC.

This is the one primitive the pre-registered ``expkit`` surface does not yet
carry. A rigorous experiment starts by asking *can this measurement even
detect the effect I am looking for* BEFORE spending compute — not after.

The estimand is the time-mean of a per-date cross-sectional rank-IC series.
Because the label is a ``horizon``-day forward return, IC observations inside
one horizon window are near-perfectly autocorrelated, so the number of
*independent* observations is the count of non-overlapping date blocks
``K = n_dates // horizon`` (``expkit.stats.usable_blocks``), NOT ``n_dates``.
A one-sided z-test on that mean gives the closed forms below.

Everything here is a pure function of (blocks, sigma_ic, alpha, power); the
only dependency is ``scipy.stats.norm`` (already a repo dependency). The
numbers are unit-tested against textbook z-values in
``tests/test_tiered_screen.py``.
"""

from __future__ import annotations

import math

from scipy.stats import norm

from renquant_orchestrator.expkit.stats import usable_blocks

__all__ = [
    "effective_blocks",
    "min_detectable_ic",
    "required_blocks",
    "achieved_power",
]


def effective_blocks(n_dates: int, horizon: int) -> int:
    """Independent-observation count for a ``horizon``-day-overlap IC series:
    the number of full non-overlapping date blocks. Thin, explicit alias over
    ``expkit.stats.usable_blocks`` so callers read the *why* at the call site."""
    return usable_blocks(n_dates, horizon)


def min_detectable_ic(
    n_blocks: int,
    sigma_ic: float,
    *,
    alpha_one_sided: float = 0.05,
    power: float = 0.80,
) -> float:
    """Smallest true mean-IC a one-sided z-test can detect at the given
    ``alpha`` with the given ``power`` over ``n_blocks`` independent blocks:

        MDE = (z_{1-alpha} + z_{power}) * sigma_ic / sqrt(n_blocks)

    Returns ``inf`` for a degenerate (<=0 block) series — nothing is
    detectable. ``sigma_ic`` is the per-block SD of the IC estimate.
    """
    if n_blocks <= 0:
        return math.inf
    if sigma_ic <= 0:
        raise ValueError("sigma_ic must be > 0")
    z_alpha = norm.ppf(1.0 - alpha_one_sided)
    z_power = norm.ppf(power)
    return (z_alpha + z_power) * sigma_ic / math.sqrt(n_blocks)


def required_blocks(
    target_ic: float,
    sigma_ic: float,
    *,
    alpha_one_sided: float = 0.05,
    power: float = 0.80,
) -> int:
    """Independent blocks needed to detect a true mean-IC of ``target_ic`` at
    the given ``alpha``/``power`` — the inverse of :func:`min_detectable_ic`,
    rounded up. This is what turns "we need ~560 sessions" into an auditable
    number instead of a slogan.
    """
    if target_ic <= 0:
        raise ValueError("target_ic must be > 0")
    if sigma_ic <= 0:
        raise ValueError("sigma_ic must be > 0")
    z_alpha = norm.ppf(1.0 - alpha_one_sided)
    z_power = norm.ppf(power)
    k = ((z_alpha + z_power) * sigma_ic / target_ic) ** 2
    return int(math.ceil(k))


def achieved_power(
    n_blocks: int,
    true_ic: float,
    sigma_ic: float,
    *,
    alpha_one_sided: float = 0.05,
) -> float:
    """Probability a one-sided z-test rejects H0: mean-IC<=0 when the truth is
    ``true_ic``, over ``n_blocks`` independent blocks:

        power = 1 - Phi(z_{1-alpha} - true_ic*sqrt(n_blocks)/sigma_ic)

    Returns 0.0 for a degenerate series.
    """
    if n_blocks <= 0:
        return 0.0
    if sigma_ic <= 0:
        raise ValueError("sigma_ic must be > 0")
    z_alpha = norm.ppf(1.0 - alpha_one_sided)
    ncp = true_ic * math.sqrt(n_blocks) / sigma_ic
    return float(1.0 - norm.cdf(z_alpha - ncp))
