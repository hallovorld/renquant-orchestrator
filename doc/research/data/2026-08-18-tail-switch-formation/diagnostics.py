"""Post-table honesty diagnostics — ALL listed in the memo's variants ledger.
1. spyvol20 T3 leave-one-block-out (is the cell carried by one block?)
2. calendar composition of spyvol20 terciles (episode clustering)
3. correlations among state variables (is vol just dispersion?)
4. outcome by prod_gmm regime label (deployable-plane variant, declared addition)
5. breadth T2 t=16.9 anomaly check (between-block variance)
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SCRATCH = Path(__file__).resolve().parent
H = 60
df = pd.read_csv(SCRATCH / "series_clf.csv", parse_dates=["date"]).set_index("date").sort_index()
df["block"] = np.arange(len(df)) // H
last = df["block"].max()
if (df["block"] == last).sum() < 30:
    df = df[df["block"] != last]

edges = df["spyvol20"].quantile([1 / 3, 2 / 3]).values
df["volterc"] = pd.cut(df["spyvol20"], [-np.inf, *edges, np.inf], labels=["T1", "T2", "T3"])

print("1. spyvol20 T3 blocks (>=15 days) and LOBO on y_z10 / y_r10")
t3 = df[df["volterc"] == "T3"]
bm = t3.groupby("block").agg(n=("y_z10", "size"), yz=("y_z10", "mean"), yr=("y_r10", "mean"),
                             d0=("n_names", lambda s: s.index.min().date()),
                             d1=("n_names", lambda s: s.index.max().date()))
bm_ok = bm[bm.n >= 15]
print(bm)
arr = bm_ok["yz"].values
for i in range(len(arr)):
    a = np.delete(arr, i)
    t = a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))
    print(f"  LOBO drop block {bm_ok.index[i]}: mean={a.mean():+.4f} t={t:+.2f} "
          f"(crit {stats.t.ppf(0.975, len(a)-1):.2f})")
arr_r = bm_ok["yr"].values
for i in range(len(arr_r)):
    a = np.delete(arr_r, i)
    t = a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))
    print(f"  LOBO(y_r10) drop {bm_ok.index[i]}: mean={a.mean():+.4f} t={t:+.2f}")

print("\n2. calendar composition of vol terciles (days per quarter)")
comp = df.groupby([df.index.to_period("Q"), "volterc"], observed=False).size().unstack(fill_value=0)
print(comp)

print("\n3. state correlations (daily)")
print(df[["disp20", "breadth", "spyvol20", "scoredisp", "skill60"]].corr().round(2))

print("\n4. outcome by prod_gmm regime label (DECLARED ADDED VARIANT)")
for lab, g in df.groupby("regime"):
    means = [g2["y_z10"].mean() for b, g2 in g.groupby("block") if len(g2) >= 15]
    nb = len(means)
    if nb >= 5:
        a = np.array(means)
        t = a.mean() / (a.std(ddof=1) / np.sqrt(nb))
        ts = f"block_t={t:+.2f} (crit {stats.t.ppf(0.975, nb-1):.2f})"
    else:
        ts = "t=NA"
    print(f"  {lab:14s} y_z10={g['y_z10'].mean():+.4f} y_r10={g['y_r10'].mean():+.4f} "
          f"n={len(g)} nb={nb} {ts}")

print("\n5. breadth T2 anomaly: block means")
be = df["breadth"].quantile([1 / 3, 2 / 3]).values
bt = pd.cut(df["breadth"], [-np.inf, *be, np.inf], labels=["T1", "T2", "T3"])
t2 = df[bt == "T2"]
print(t2.groupby("block")["y_z10"].agg(["size", "mean"]))

print("\n6. T3 vs T1 spread of block means (descriptive, unpaired):",
      f"{bm_ok['yz'].mean() - df[df['volterc']=='T1'].groupby('block')['y_z10'].mean()[lambda s: df[df['volterc']=='T1'].groupby('block').size()>=15].mean():+.4f}" if True else "")
