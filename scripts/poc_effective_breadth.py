#!/usr/bin/env python3
"""POC-A: measure the EFFECTIVE breadth (BR) of the 104 panel.

Claim under test (roadmap #230 §2.4/§7.1): nominal BR = 142 names x 4.2
independent 60d periods/yr ~= 600/yr, but cross-sectional correlation reduces
the effective number of independent bets to ~100-200/yr.

Theory: Grinold-Kahn fundamental law uses BR = number of INDEPENDENT bets/yr.
For correlated bets we report two standard reductions:
  (1) naive equicorrelation:  N_eff = N / (1 + (N-1)*rho_bar)
  (2) eigenvalue participation ratio (effective rank of the correlation
      matrix): N_eff = (sum(lambda))^2 / sum(lambda^2)
Independent periods/yr for a 60-trading-day label = 252/60 = 4.2 (labels
sampled at stride 60 so windows do not overlap).

Reproduce:
  cd /Users/renhao/git/github/RenQuant && .venv/bin/python \
    <orchestrator>/scripts/poc_effective_breadth.py
Inputs (read-only): data/transformer_v4_wl200_clean.parquet (142 tickers,
2016-01-04..2026-02-10, label fwd_60d_excess).
Output: doc/research/evidence/2026-07-02-roadmap-pocs/poc_a_effective_breadth.json
"""
import json
import os

import numpy as np
import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
PANEL = os.path.join(RQ, "data/transformer_v4_wl200_clean.parquet")
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
LABEL = "fwd_60d_excess"
STRIDE = 60  # trading days -> non-overlapping 60d label windows


def _measure(wide: pd.DataFrame, stride: int, min_obs: int) -> dict:
    sampled = wide.iloc[::stride]
    sampled = sampled.loc[:, sampled.notna().sum() >= min_obs]
    n_names = sampled.shape[1]
    n_dates = sampled.shape[0]
    corr = sampled.corr(min_periods=max(10, min_obs // 2))
    c = corr.values.copy()
    iu = np.triu_indices_from(c, k=1)
    pair = c[iu]
    pair = pair[np.isfinite(pair)]
    rho_bar = float(np.mean(pair))
    cf = corr.fillna(rho_bar).values
    np.fill_diagonal(cf, 1.0)
    lam = np.clip(np.linalg.eigvalsh(cf), 0, None)
    n_eff_pr = float(lam.sum() ** 2 / (lam**2).sum())
    n_eff_naive = float(n_names / (1 + (n_names - 1) * max(rho_bar, 0.0)))
    return {
        "n_names_used": int(n_names),
        "n_nonoverlap_dates": int(n_dates),
        "q_names_over_dates": round(n_names / n_dates, 2),
        "avg_pairwise_corr": round(rho_bar, 4),
        "n_eff_participation_ratio": round(n_eff_pr, 1),
        "n_eff_naive_equicorr": round(n_eff_naive, 1),
    }


def main() -> None:
    out = {}
    # Primary object: 60d label. CAVEAT: 142 names x ~43 windows => q≈3.3 —
    # the sample correlation matrix is rank-deficient and the participation
    # ratio is biased DOWN (Marchenko-Pastur noise inflates top eigenvalues).
    df60 = pd.read_parquet(PANEL, columns=["ticker", "date", LABEL])
    wide60 = df60.pivot_table(index="date", columns="ticker", values=LABEL).sort_index()
    out["fwd60_stride60"] = _measure(wide60, STRIDE, 20)
    out["fwd60_stride60"]["caveat"] = (
        "q>1: rank-deficient corr matrix; participation ratio is a "
        "noise-biased LOWER bound; naive equicorr is the upper bound")
    # Better-conditioned proxy of the SAME cross-sectional structure: the 5d
    # excess label at stride 5 (~500 non-overlapping windows, q≈0.28).
    df5 = pd.read_parquet(PANEL, columns=["ticker", "date", "fwd_5d_excess"])
    wide5 = df5.pivot_table(index="date", columns="ticker", values="fwd_5d_excess").sort_index()
    out["fwd5_stride5_proxy"] = _measure(wide5, 5, 100)
    out["fwd5_stride5_proxy"]["role"] = (
        "well-conditioned estimate of the cross-sectional dependence "
        "structure; horizon-independent to first order")
    n_eff_best = out["fwd5_stride5_proxy"]["n_eff_participation_ratio"]
    periods_per_yr = 252 / STRIDE
    out["conclusion"] = {
        "independent_periods_per_yr_60d": periods_per_yr,
        "BR_nominal_per_yr": round(142 * periods_per_yr, 0),
        "BR_eff_point_per_yr": round(n_eff_best * periods_per_yr, 0),
        "BR_eff_interval_per_yr": [
            round(out["fwd60_stride60"]["n_eff_participation_ratio"] * periods_per_yr, 0),
            round(out["fwd60_stride60"]["n_eff_naive_equicorr"] * periods_per_yr, 0)],
        "note": ("excess labels remove the market mode; residual factor "
                 "structure (sectors/styles) is what cuts N_eff below N. "
                 "sqrt(BR_eff) is the IR multiplier in IR = TC*IC*sqrt(BR)"),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_a_effective_breadth.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
