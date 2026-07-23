"""Generic tiered evaluation harness — a thin *composition* of the codex-
reviewed ``expkit`` primitives (PR #287). It implements no statistics of its
own; every number comes from ``expkit`` (IC, shifted-label placebo, paired
deltas, gap-respecting block bootstrap) or :mod:`.power`.

  Tier 0  harness validation — positive control (inject a known-rho signal,
          the pipeline must recover it inside the bootstrap CI) + negative
          control (shifted-label placebo IS the leakage floor the real IC
          must clear). :func:`positive_control_recovery`, and the placebo leg
          of every existence run.
  Tier 1  signal EXISTENCE at a given horizon. :func:`evaluate_existence`.
  Tier 2  paired INCREMENT of one score over another on identical dates/names
          (the common embargo-leakage floor cancels). :func:`evaluate_increment`.

The ``score`` inputs are wide ``date x name`` frames of model output — this
module has no opinion on what produced them. ``alpha_one_sided`` is a
required keyword on every public entrypoint (no default): the caller's own
pre-registered spec sets the multiplicity-corrected alpha, and a silent
default here would let a caller run at a looser alpha than their spec froze
without noticing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from renquant_orchestrator.expkit.evaluation import (
    fwd_excess,
    gate_shift_sessions,
    paired_deltas,
    per_date_ic,
    shifted_label_placebo,
)
from renquant_orchestrator.expkit.stats import (
    block_bootstrap_conditional_mean,
    summarize_boot,
    usable_blocks,
)
from renquant_orchestrator.tiered_screen.power import min_detectable_ic

__all__ = [
    "ExistenceResult",
    "IncrementResult",
    "evaluate_existence",
    "evaluate_increment",
    "positive_control_recovery",
]


def _mean_ci(series: pd.Series, *, block: int, n_boot: int, seed: int, alpha_one_sided: float):
    """Unconditional block-bootstrap of a per-date series mean (all-True mask),
    summarized. Returns (mean, summary_dict_or_None)."""
    vals = series.to_numpy(dtype=float)
    boot = block_bootstrap_conditional_mean(
        vals, np.ones(len(vals), dtype=bool), block=block, n_boot=n_boot, seed=seed
    )
    return float(np.nanmean(vals)) if len(vals) else float("nan"), summarize_boot(
        boot, alpha_one_sided=alpha_one_sided
    )


@dataclass(frozen=True)
class ExistenceResult:
    """Tier-1 read for one (score, horizon)."""

    horizon: int
    n_dates: int
    n_blocks: int
    mde: float
    real_ic_mean: float
    placebo_floor_mean: float
    clean_ic_mean: float
    clean_boot: dict[str, Any] | None
    # H1 met iff the one-sided lower bound of the CLEAN IC (real - placebo,
    # i.e. already floor-subtracted) is strictly above 0.
    exists: bool = field(default=False)


@dataclass(frozen=True)
class IncrementResult:
    """Tier-2 read: score_ensemble minus score_best_single, paired."""

    horizon: int
    n_dates: int
    n_blocks: int
    delta_mean: float
    delta_boot: dict[str, Any] | None
    beats_best_single: bool = field(default=False)


def evaluate_existence(
    score: pd.DataFrame,
    close: pd.DataFrame,
    bench_close: pd.Series,
    horizon: int,
    *,
    n_boot: int = 2000,
    seed: int = 44,
    alpha_one_sided: float,
    min_names: int = 30,
    sigma_ic: float | None = None,
) -> ExistenceResult:
    """Tier-1 existence test for one score at one horizon.

    label = horizon-day forward excess return; placebo = the shifted-label
    leakage floor at the frozen shift (``gate_shift_sessions(horizon)``);
    clean_ic = real - placebo per date. H1 (signal exists) is met iff the
    one-sided lower bound of the bootstrap CI of mean(clean_ic) > 0.

    The block length equals the horizon (one independent block per horizon
    window). ``sigma_ic`` for the reported MDE defaults to the realized SD of
    the clean-IC series when not supplied.
    """
    label = fwd_excess(close, bench_close, horizon)
    placebo = shifted_label_placebo(label, gate_shift_sessions(horizon))
    ic = per_date_ic(score, label, placebo, min_names=min_names)

    clean = ic["clean_ic"].dropna() if "clean_ic" in ic else pd.Series(dtype=float)
    real = ic["real_ic"].dropna() if "real_ic" in ic else pd.Series(dtype=float)
    plc = ic["placebo_ic"].dropna() if "placebo_ic" in ic else pd.Series(dtype=float)

    n_dates = int(len(clean))
    n_blocks = usable_blocks(n_dates, horizon)
    clean_mean, clean_boot = _mean_ci(
        clean, block=horizon, n_boot=n_boot, seed=seed, alpha_one_sided=alpha_one_sided
    ) if n_dates else (float("nan"), None)

    sd = float(clean.std(ddof=1)) if n_dates > 1 else float("nan")
    sigma = sigma_ic if sigma_ic is not None else sd
    mde = min_detectable_ic(n_blocks, sigma, alpha_one_sided=alpha_one_sided) if (
        sigma and sigma > 0
    ) else float("inf")

    exists = bool(clean_boot is not None and clean_boot["lb_one_sided"] > 0.0)
    return ExistenceResult(
        horizon=horizon,
        n_dates=n_dates,
        n_blocks=n_blocks,
        mde=float(mde),
        real_ic_mean=float(real.mean()) if len(real) else float("nan"),
        placebo_floor_mean=float(plc.mean()) if len(plc) else float("nan"),
        clean_ic_mean=float(clean_mean),
        clean_boot=clean_boot,
        exists=exists,
    )


def evaluate_increment(
    score_ensemble: pd.DataFrame,
    score_best_single: pd.DataFrame,
    close: pd.DataFrame,
    bench_close: pd.Series,
    horizon: int,
    *,
    n_boot: int = 2000,
    seed: int = 44,
    alpha_one_sided: float,
    min_names: int = 30,
) -> IncrementResult:
    """Tier-2 paired increment: does score_ensemble out-rank score_best_single
    on the SAME dates/names? Evaluated on the paired clean-IC delta so the
    common embargo-leakage floor cancels (the whole point of pairing).

    H2 met iff the one-sided lower bound of mean(delta) > 0.
    """
    label = fwd_excess(close, bench_close, horizon)
    placebo = shifted_label_placebo(label, gate_shift_sessions(horizon))
    ic_ens = per_date_ic(score_ensemble, label, placebo, min_names=min_names)
    ic_bst = per_date_ic(score_best_single, label, placebo, min_names=min_names)

    clean_ens = ic_ens["clean_ic"].dropna() if "clean_ic" in ic_ens else pd.Series(dtype=float)
    clean_bst = ic_bst["clean_ic"].dropna() if "clean_ic" in ic_bst else pd.Series(dtype=float)
    delta = paired_deltas(clean_ens, clean_bst)

    n_dates = int(len(delta))
    n_blocks = usable_blocks(n_dates, horizon)
    delta_mean, delta_boot = _mean_ci(
        delta, block=horizon, n_boot=n_boot, seed=seed, alpha_one_sided=alpha_one_sided
    ) if n_dates else (float("nan"), None)

    beats = bool(delta_boot is not None and delta_boot["lb_one_sided"] > 0.0)
    return IncrementResult(
        horizon=horizon,
        n_dates=n_dates,
        n_blocks=n_blocks,
        delta_mean=float(delta_mean),
        delta_boot=delta_boot,
        beats_best_single=beats,
    )


def positive_control_recovery(
    label: pd.DataFrame,
    *,
    rho: float,
    horizon: int,
    seed: int = 44,
    n_boot: int = 2000,
    alpha_one_sided: float,
    min_names: int = 30,
) -> ExistenceResult:
    """Tier-0 positive control: synthesize a score that is the true label
    corrupted with noise to a target rank-correlation ``rho``, then run it
    through the SAME existence machinery. A working harness must recover a
    clean IC whose CI covers ``rho`` (for rho well above the floor). This
    proves the pipeline can detect a *known* effect before any real result is
    trusted.

    The score is built as ``rho_scale * label + noise`` per date; the exact
    realized rank-IC is what the bootstrap reports (``rho`` sets the target).
    """
    rng = np.random.default_rng(seed)
    # Build a synthetic score correlated with the label at ~rho, per date.
    lab = label.copy()
    noise = pd.DataFrame(
        rng.standard_normal(lab.shape), index=lab.index, columns=lab.columns
    )
    lab_std = lab.stack().std() or 1.0
    noise_scale = (1.0 - float(rho) * float(rho)) ** 0.5 if abs(rho) < 1 else 0.0
    score = rho * (lab / lab_std) + noise_scale * noise
    # A flat close/bench pair is not needed: reuse the label directly as the
    # "forward excess" by passing an identity close that reproduces it is
    # overkill — instead evaluate IC of score against the label with a
    # shifted-label placebo, exactly as Tier-1 does.
    placebo = shifted_label_placebo(lab, gate_shift_sessions(horizon))
    ic = per_date_ic(score, lab, placebo, min_names=min_names)
    clean = ic["clean_ic"].dropna() if "clean_ic" in ic else pd.Series(dtype=float)
    real = ic["real_ic"].dropna() if "real_ic" in ic else pd.Series(dtype=float)
    plc = ic["placebo_ic"].dropna() if "placebo_ic" in ic else pd.Series(dtype=float)
    n_dates = int(len(clean))
    n_blocks = usable_blocks(n_dates, horizon)
    clean_mean, clean_boot = _mean_ci(
        clean, block=horizon, n_boot=n_boot, seed=seed, alpha_one_sided=alpha_one_sided
    ) if n_dates else (float("nan"), None)
    sd = float(clean.std(ddof=1)) if n_dates > 1 else float("nan")
    mde = min_detectable_ic(n_blocks, sd, alpha_one_sided=alpha_one_sided) if (
        sd and sd > 0
    ) else float("inf")
    exists = bool(clean_boot is not None and clean_boot["lb_one_sided"] > 0.0)
    return ExistenceResult(
        horizon=horizon,
        n_dates=n_dates,
        n_blocks=n_blocks,
        mde=float(mde),
        real_ic_mean=float(real.mean()) if len(real) else float("nan"),
        placebo_floor_mean=float(plc.mean()) if len(plc) else float("nan"),
        clean_ic_mean=float(clean_mean),
        clean_boot=clean_boot,
        exists=exists,
    )
