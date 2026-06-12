"""Ensemble backfill study v0 — PatchTST + quality blend (pre-registered metrics).

Per doc/research/2026-06-12-ensemble-primary-proposal.md §3.3-2. v0 omits the
GBDT leg (PIT scoring lands in v1); weights fixed 50/50, no fitting.
Metrics (pre-registered): full-year IC, dead-window IC, top-8 selection edge
in both windows. Ticker recovery via within-date rank pairing (label is a
per-date monotone transform of fwd_60d_excess).
"""
import pandas as pd, numpy as np
from scipy import stats as st

R = "/Users/renhao/git/github/RenQuant"
pred = pd.read_parquet(f"{R}/artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_val_preds.parquet").dropna(subset=["pred","label"])
panel = pd.read_parquet(f"{R}/data/transformer_v4_wl200_clean.parquet", columns=["ticker","date","asset_growth","roe","fwd_60d_excess"])
panel["date"] = pd.to_datetime(panel["date"])
val = panel[panel["date"] >= "2025-02-06"].dropna(subset=["fwd_60d_excess"])

rows = []
for dt, g in pred.groupby("date"):
    pg = val[val["date"] == dt]
    if len(pg) != len(g):
        continue
    a = g.sort_values("label").reset_index(drop=True)
    b = pg.sort_values("fwd_60d_excess").reset_index(drop=True)
    a[["ticker","asset_growth","roe"]] = b[["ticker","asset_growth","roe"]]
    rows.append(a)
m = pd.concat(rows)
for c, flip in [("pred",False), ("asset_growth",True), ("roe",False)]:
    z = m.groupby("date")[c].transform(lambda s: (s.rank()-s.rank().mean())/s.rank().std())
    m["z_"+c] = -z if flip else z
m["quality"] = (m["z_asset_growth"] + m["z_roe"]) / 2
m["ens"] = 0.5*m["z_pred"] + 0.5*m["quality"]

def ic(d, col):
    r = d.groupby("date").apply(lambda g: st.spearmanr(g[col], g["label"]).statistic if len(g) >= 10 else np.nan, include_groups=False).dropna()
    return float(r.mean()), len(r)

def top8_edge(d, col):
    t8 = d[d.groupby("date")[col].rank(ascending=False, method="first") <= 8].groupby("date")["label"].mean()
    return float(t8.mean() - d.groupby("date")["label"].mean().mean())

dead = m[(m["date"]>="2025-10-01") & (m["date"]<="2026-01-31")]
print(f"rows={len(m)} days={m['date'].nunique()}")
print(f"{'signal':28s} {'IC full':>8s} {'IC dead':>8s} {'top8 full':>10s} {'top8 dead':>10s}")
for name, col in [("PatchTST alone","z_pred"), ("quality alone","quality"), ("ENSEMBLE 50/50","ens")]:
    print(f"{name:28s} {ic(m,col)[0]:+8.4f} {ic(dead,col)[0]:+8.4f} {top8_edge(m,col):+10.3f} {top8_edge(dead,col):+10.3f}")
