"""Re-measure the vol-switch prereg's primary-corpus state geometry (README section 3).

Unit: consecutive NON-OVERLAPPING 60-trading-day blocks over the primary corpus
(2017-01-03..2023-09-29), per doc/design/2026-07-09-governor-prereg-replay-protocol.md
section 1.2 unit (ii). Vol definition matches the exploratory build_series.py:109
(20-td rolling sample std of close-to-close returns, ddof=1, annualized sqrt(252)).

Usage: python geometry_check.py [path/to/SPY/1d.parquet]
Default path is the umbrella workstation layout.
"""

import sys

import numpy as np
import pandas as pd

SPY_PARQUET = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet"
)
CORPUS = ("2017-01-03", "2023-09-29")
FIXED_THRESHOLD = 0.135  # frozen rounded exploratory upper-tercile edge
WARMUP_OBS = 504  # expanding-variant warmup, in vol20 observations
BLOCK_TD = 60  # = label horizon h, non-overlapping
ELIGIBLE_MIN_ON = 15
DOMINANT_MIN_ON = 45

spy = pd.read_parquet(SPY_PARQUET)
close = spy["close"].sort_index()
vol20 = close.pct_change().rolling(20).std() * np.sqrt(252)

corpus = vol20.loc[CORPUS[0] : CORPUS[1]]
assert corpus.notna().all(), "vol20 must be defined on every corpus day"
print(f"corpus trading days: {len(corpus)} ({corpus.index[0].date()} .. {corpus.index[-1].date()})")

on_fixed = corpus > FIXED_THRESHOLD
print(f"ON days fixed (>{FIXED_THRESHOLD:.1%}): {int(on_fixed.sum())}")

# Expanding upper-tercile variant: 66.7th pct of all vol20 history <= d, defined once
# >= WARMUP_OBS observations exist (series starts 2016-01-04); earlier corpus days are
# OFF by fail-closed convention.
thr = vol20.dropna().expanding(min_periods=WARMUP_OBS).quantile(2 / 3)
thr_corpus = thr.loc[corpus.index]
print(f"expanding threshold first available: {thr.dropna().index[0].date()}")
on_exp = corpus > thr_corpus  # NaN threshold compares False -> OFF
print(f"ON days expanding (pre-threshold OFF): {int(on_exp.sum())}")

n_blocks = len(corpus) // BLOCK_TD
print(f"complete {BLOCK_TD}-td blocks: {n_blocks} (trailing {len(corpus) - n_blocks * BLOCK_TD}-td remainder dropped)")

eligible = {}
for name, on in (("fixed", on_fixed), ("expanding", on_exp)):
    counts = [int(on.iloc[i * BLOCK_TD : (i + 1) * BLOCK_TD].sum()) for i in range(n_blocks)]
    eligible[name] = [c >= ELIGIBLE_MIN_ON for c in counts]
    print(
        f"{name}: ON-eligible(>={ELIGIBLE_MIN_ON})={sum(eligible[name])}, "
        f"ON-dominant(>={DOMINANT_MIN_ON})={sum(c >= DOMINANT_MIN_ON for c in counts)}"
    )
    print(f"{name}: per-block ON days={counts}")

both = sum(f and e for f, e in zip(eligible["fixed"], eligible["expanding"]))
print(f"blocks ON-eligible under BOTH: {both}")
