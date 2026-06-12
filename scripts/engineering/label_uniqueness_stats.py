#!/usr/bin/env python3
"""Label overlap/uniqueness statistics (#106 acceptance contract; de Prado ch.4).

fwd_60d_excess labels overlap ~60×: consecutive daily samples share ~59/60
of their forward window. Computes, on the REAL panel: average label overlap,
de Prado average uniqueness, and the effective sample size — the number the
M6 placebo confound and any future loss-weighting must use.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

R = "/Users/renhao/git/github/RenQuant"
H = 60  # label horizon in trading days

panel = pd.read_parquet(f"{R}/data/transformer_v4_wl200_clean.parquet",
                        columns=["ticker", "date", "fwd_60d_excess"])
panel["date"] = pd.to_datetime(panel["date"])
days = np.array(sorted(panel.date.unique()))
n_days = len(days)

# per-ticker: each daily label spans [t, t+H); average uniqueness of sample t
# = mean over its window of 1/(concurrent labels covering that day) = 1/H for
# interior samples in a dense daily series. Verify empirically on one dense ticker:
g = panel[panel.ticker == "AAPL"].dropna().sort_values("date")
T = len(g)
coverage = np.zeros(T + H)
for i in range(T):
    coverage[i:i + H] += 1
uniq = np.array([np.mean(1.0 / coverage[i:i + H]) for i in range(T)])
avg_u = uniq.mean()
ess_per_ticker = uniq.sum()
print(f"AAPL: {T} daily labels, horizon {H} bars")
print(f"de Prado average uniqueness = {avg_u:.4f} (≈1/{1/avg_u:.0f})")
print(f"effective sample size per ticker = {ess_per_ticker:.0f} "
      f"({ess_per_ticker/T:.1%} of nominal)")
tickers = panel.ticker.nunique()
nominal = len(panel.dropna())
ess_total = nominal * avg_u
print(f"\nPANEL: nominal samples = {nominal:,} ({tickers} tickers) "
      f"→ effective ≈ {ess_total:,.0f}")
print(f"\nCONSEQUENCES: (1) any IC t-stat computed on nominal n overstates "
      f"significance by ≈√{1/avg_u:.0f} ≈ {np.sqrt(1/avg_u):.1f}× — e.g. the "
      f"capability doc's t=7.1 on daily ICs is fine (day-level), but row-level "
      f"stats are not; (2) training loss weights should be ∝ uniqueness "
      f"(de Prado ch.4) — fixed BEFORE training per the acceptance contract; "
      f"(3) the M6 placebo confound magnitude is now quantified.")
assert 0.014 < avg_u < 0.022, avg_u   # sanity: ≈1/60 for dense daily 60-bar labels
print("\nsanity bound ✓ (≈1/60 as theory predicts for dense daily sampling)")
