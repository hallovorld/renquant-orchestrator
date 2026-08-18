"""DECLARED ADDED VARIANT: vol-cohort-matched top-10 spread (tilt vs skill).

Per date: STD60(i,t) = std of ticker i's 1d returns over t-59..t (PIT).
Universe = scored tickers with STD60 available. Terciles of STD60 per date.
Adjusted outcome Y_adj(t) = mean over top-10 of [fwd60_excess(i) - mean
fwd60_excess of i's STD60-tercile cohort (self-excluded)].
Conditioned on prod_gmm regime label and spyvol20 terciles (same edges rule).
Same block machinery as conditional_analysis.py.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SCRATCH = Path(__file__).resolve().parent
OHLCV = Path("/Users/renhao/git/github/RenQuant/data/ohlcv")
CLF = Path("/Users/renhao/git/github/renquant-model/doc/research/data/"
           "2026-08-01-clf-wf-lineage-bundle/clf_wf_scores.parquet")
H = 60
TOP_N = 10

clf = pd.read_parquet(CLF).rename(columns={"raw": "score"})
counts = clf.groupby("date")["ticker"].nunique()
clf = clf[clf["date"].isin(counts[counts >= 100].index)]
tickers = sorted(clf["ticker"].unique())

closes = {}
for t in tickers + ["SPY"]:
    p = OHLCV / t / "1d.parquet"
    s = pd.read_parquet(p, columns=["close"])["close"]
    s.index = pd.to_datetime(s.index)
    closes[t] = s[~s.index.duplicated(keep="last")].sort_index()
cd = pd.DataFrame(closes).sort_index()
rets = cd.pct_change(fill_method=None)
std60 = rets.rolling(60, min_periods=45).std()
fwd = cd.shift(-H) / cd - 1.0
fwd_ex = fwd.sub(fwd["SPY"], axis=0)

rows = []
for d, g in clf.groupby("date"):
    if d not in cd.index:
        continue
    g = g.sort_values("score", ascending=False)
    univ = [t for t in g["ticker"] if t in cd.columns]
    sv = std60.loc[d, univ].dropna()
    fe = fwd_ex.loc[d, sv.index].dropna()
    common = fe.index
    if len(common) < 100:
        continue
    sv = sv[common]
    terc = pd.qcut(sv.rank(method="first"), 3, labels=False)
    cohort_sum = fe.groupby(terc).transform("sum")
    cohort_n = fe.groupby(terc).transform("count")
    bench = (cohort_sum - fe) / (cohort_n - 1)  # self-excluded cohort mean
    adj = fe - bench
    top10 = [t for t in g["ticker"].head(TOP_N) if t in adj.index]
    if len(top10) < 7:
        continue
    rows.append(dict(date=d, y_adj10=adj[top10].mean(), y_raw10=fe[top10].mean() - fe.mean(),
                     top_vol_pctile=sv.rank(pct=True)[top10].mean()))
adjdf = pd.DataFrame(rows).set_index("date").sort_index()

ser = pd.read_csv(SCRATCH / "series_clf.csv", parse_dates=["date"]).set_index("date")
adjdf = adjdf.join(ser[["spyvol20", "regime"]])
adjdf["block"] = np.arange(len(adjdf)) // H
last = adjdf["block"].max()
if (adjdf["block"] == last).sum() < 30:
    adjdf = adjdf[adjdf["block"] != last]


def cellstat(sub):
    means = [g["y_adj10"].mean() for b, g in sub.groupby("block") if len(g) >= 15]
    nb = len(means)
    if nb >= 5:
        a = np.array(means)
        t = a.mean() / (a.std(ddof=1) / np.sqrt(nb))
        return f"mean={sub['y_adj10'].mean():+.4f} n={len(sub)} nb={nb} t={t:+.2f} (crit {stats.t.ppf(0.975, nb-1):.2f})"
    return f"mean={sub['y_adj10'].mean():+.4f} n={len(sub)} nb={nb} t=NA"


print(f"corpus n={len(adjdf)}; top-10 mean STD60 percentile = {adjdf['top_vol_pctile'].mean():.2f}")
print("UNCOND vol-matched:", cellstat(adjdf))
print("(raw for reference: mean=%+.4f)" % adjdf["y_raw10"].mean())
print("\nby regime:")
for lab, g in adjdf.groupby("regime"):
    print(f"  {lab:14s}", cellstat(g))
print("\nby spyvol20 tercile:")
edges = adjdf["spyvol20"].quantile([1 / 3, 2 / 3]).values
terc = pd.cut(adjdf["spyvol20"], [-np.inf, *edges, np.inf], labels=["T1", "T2", "T3"])
for lev in ["T1", "T2", "T3"]:
    print(f"  {lev}", cellstat(adjdf[terc == lev]))
adjdf.to_csv(SCRATCH / "series_volmatched.csv")
