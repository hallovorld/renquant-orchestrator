"""Cap sweep on ONE fixed block set — the formation evidence for the prereg.

The block set is chosen INDEPENDENTLY of any cap (it requires only that a date
have >=20 names with both a PIT vol and a forward return), so every cap is
scored on identical dates. An earlier version filtered blocks per-cap and
produced a contradictory reading; that artefact is why this file exists.
"""
import json, math, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from cohort_measure import load_closes, CFG, VOL_WINDOW, ANNUALIZE

cfg = json.loads(CFG.read_text()); wl = sorted(set(cfg["watchlist"]))
px = load_closes(wl); vol = px.pct_change().rolling(VOL_WINDOW).std() * ANNUALIZE
for h in (20, 60):
    fwd = px.shift(-h) / px - 1.0
    dates = [d for d in vol.dropna(how="all").index if d in fwd.index][::h]
    dates = [d for d in dates if (vol.loc[d].notna() & fwd.loc[d].notna()).sum() >= 20]
    print(f"\n=== h={h}  {len(dates)} fixed non-overlapping blocks  "
          f"{dates[0].date()}..{dates[-1].date()} ===")
    series = {}
    for cap in (0.40, 0.50, 0.60, 0.70, 0.80, 1.00, 99.0):
        rr = []
        for d in dates:
            v, f = vol.loc[d], fwd.loc[d]; ok = v.notna() & f.notna()
            keep = ok & (v <= cap)
            rr.append(float(f[keep].mean()) if keep.sum() >= 3 else np.nan)
        s = pd.Series(rr, index=dates).dropna()
        series[cap] = s
        lbl = "none" if cap > 10 else f"{cap:.0%}"
        print(f"  {lbl:>5}  mean {s.mean():+.4f}  ret/sd {s.mean()/s.std(ddof=1):+.3f}  n={len(s)}")
    both = pd.concat([series[0.60].rename("c60"), series[1.00].rename("c100")], axis=1).dropna()
    d_ = both.c100 - both.c60
    t = d_.mean() / (d_.std(ddof=1) / math.sqrt(len(d_)))
    print(f"  paired 100% vs 60% on {len(d_)} shared blocks: diff {d_.mean():+.4f} "
          f"t {t:+.2f} positive {int((d_>0).sum())}/{len(d_)}")
