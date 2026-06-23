#!/usr/bin/env python
"""Stress-test the baseline's credibility: portfolio P&L under EMBARGO + NON-OVERLAPPING
rebalances + transaction COSTS, raw vs trend-scan.

The simple sim's +0.134 top-quintile 60d alpha is implausibly high (overlap + no cost +
possible boundary leakage). This re-measures with:
  - 90-day train/test EMBARGO on the REAL model (drop train rows whose 60d label reaches test),
  - NON-OVERLAPPING holding: rebalance only every 60 trading days (one entry per 60d window),
  - a turnover COST of 10 bps per name per rebalance,
to see whether the raw baseline's absolute P&L survives — and whether raw still >= trend-scan.
Read-only on data.
"""
from __future__ import annotations
import importlib.util, numpy as np, pandas as pd, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("hardened")
spec = importlib.util.spec_from_file_location("tsgate", "/tmp/trendscan_wf_gate.py")
ts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ts)

reg = pd.read_parquet(ts.REGIME, columns=["ticker","date"]+list(ts.REGIME_COLS))
reg["date"] = pd.to_datetime(reg["date"])
probs = reg[list(ts.REGIME_COLS)].to_numpy(float)
reg["regime"] = np.array([ts.REGIME_COLS[list(ts.REGIME_COLS)[i]] for i in probs.argmax(1)])
df = pd.read_parquet(ts.MULTIH); df["date"] = pd.to_datetime(df["date"])
df = df.dropna(subset=[ts.RAW]).copy()
df[ts.TS] = ts.build_trendscan_label(df)
df = df.merge(reg[["ticker","date","regime"]], on=["ticker","date"], how="inner")
excl = {"ticker","date","split_label","regime",ts.TS,"fwd_5d_excess","fwd_20d_excess","fwd_60d_excess",
        "fwd_5d_excess_raw","fwd_10d_excess_raw","fwd_20d_excess_raw","fwd_60d_excess_raw"}
feat_cols = [c for c in df.columns if c not in excl]
EMB = pd.Timedelta(days=90); COST = 0.001; TOPQ = 0.20

def train_embargoed(tr, te, label):
    tr = tr.dropna(subset=[label])
    if len(tr) < 1000 or len(te) < 100: return None
    import xgboost as xgb
    X = tr[feat_cols].fillna(0).to_numpy(np.float64); y = tr[label].clip(-5,5).to_numpy(np.float64)
    Xte = te[feat_cols].fillna(0).to_numpy(np.float64)
    mu, sd = X.mean(0), X.std(0)+1e-9; X=((X-mu)/sd).clip(-5,5); Xte=((Xte-mu)/sd).clip(-5,5)
    o = np.argsort(tr["date"].to_numpy()); _,g = np.unique(tr["date"].to_numpy()[o], return_counts=True)
    dm = xgb.DMatrix(X[o], label=y[o]); dm.set_group(g)
    return xgb.train(ts.PARAMS, dm, num_boost_round=ts.N_ROUNDS).predict(xgb.DMatrix(Xte))

rows = []
for cut in ts.CUTS:
    s,e,tes,tee = cut
    cut_end = pd.Timestamp(tes) - EMB
    tr = df[(df["date"]>=s)&(df["date"]<=pd.Timestamp(e))&(df["date"]<cut_end)]   # EMBARGOED train
    te = df[(df["date"]>=tes)&(df["date"]<=tee)].dropna(subset=[ts.RAW])
    if len(te) < 100: continue
    # NON-OVERLAPPING rebalance dates: every 60th trading day present in test
    udates = np.sort(te["date"].unique())[::60]
    for name, label in [("raw", ts.RAW), ("trendscan", ts.TS)]:
        p = train_embargoed(tr, te, label)
        if p is None: continue
        tt = te[["date","regime",ts.RAW]].copy(); tt["pred"]=p
        for dt in udates:
            g = tt[tt["date"]==dt]
            if len(g) < 10: continue
            k = max(1, int(round(len(g)*TOPQ)))
            top = g.nlargest(k, "pred")
            alpha = float(top[ts.RAW].mean() - g[ts.RAW].mean()) - COST  # net of turnover cost
            rows.append({"model":name,"regime":g["regime"].mode().iloc[0],"alpha":alpha})

R = pd.DataFrame(rows)
def stat(m, rg):
    s = R[(R.model==m) & ((R.regime==rg) if rg!="ALL" else True)]["alpha"]
    if len(s) < 3: return (np.nan, np.nan, len(s))
    return (s.mean(), s.mean()/(s.std()+1e-9)*np.sqrt(252/60), len(s))

log.info("HARDENED top-20%% alpha (embargo 90d + NON-overlap 60d rebal + 10bps cost), mean/Sharpe(n):")
log.info("%-10s %16s %16s %16s", "model","ALL","BULL_CALM","BULL_VOL")
for m in ("raw","trendscan"):
    cells=[f"{stat(m,rg)[0]:+.4f}/{stat(m,rg)[1]:+.2f}(n{stat(m,rg)[2]})" for rg in ("ALL","BULL_CALM","BULL_VOLATILE")]
    log.info("%-10s %16s %16s %16s", m, *cells)
log.info("\nVS the naive sim (overlap, no cost, no embargo): raw BULL_CALM was +0.1344.")
rmu = stat("raw","BULL_CALM")[0]; tmu = stat("trendscan","BULL_CALM")[0]
log.info("DECISION:")
log.info("  raw BULL_CALM hardened alpha = %+.4f  (naive was +0.1344 -> %s)",
         rmu, "COLLAPSED, baseline was inflated" if (rmu==rmu and rmu < 0.05) else "survives, baseline credible-ish")
log.info("  relative: raw %+.4f vs trendscan %+.4f -> %s", rmu, tmu,
         "raw still >= trend-scan (verdict holds)" if (rmu==rmu and tmu==tmu and rmu>=tmu) else "ordering changed!")
R.to_csv("/tmp/hardened_pnl.csv", index=False)
