#!/usr/bin/env python
"""Lightweight portfolio-P&L backtest of the trend-scan vs raw label (the decisive test).

Absolute IC is untrustworthy here (wide shuffled null). P&L is NOT — it uses the REALIZED
forward excess return of the names the model actually selects, so it sidesteps the IC null.

Per WF cut, for each model {raw-label, trend-scan-label}: train, predict on test, and per test
date form the top-quintile (top 20% by predicted score), equal-weight. The portfolio's
realized return for that date = mean fwd_60d_excess of the held names; its ALPHA = that minus
the universe mean that date (selection skill, market-neutral). Aggregate alpha per regime
(mean + a rough Sharpe across dates; holding periods overlap so Sharpe is indicative, but the
RAW-vs-TRENDSCAN comparison shares the same overlap, so it is a fair relative test).

This is a SIMPLIFIED portfolio sim from WF predictions — not the production sim engine. It is
read-only on data and writes no canonical path.
"""
from __future__ import annotations
import importlib.util, numpy as np, pandas as pd, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("ts-portfolio")
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
TOPQ = 0.20

def portfolio_alpha(pred, te):
    """Per date: top-20% by pred, alpha = mean(top fwd_60d_excess) - mean(universe). Returns
    a DataFrame[date, regime, alpha]."""
    t = te[["date","regime",ts.RAW]].copy(); t["pred"] = pred
    rows = []
    for dt, g in t.groupby("date"):
        if len(g) < 10: continue
        k = max(1, int(round(len(g)*TOPQ)))
        top = g.nlargest(k, "pred")
        rows.append({"date": dt, "regime": g["regime"].mode().iloc[0],
                     "alpha": float(top[ts.RAW].mean() - g[ts.RAW].mean())})
    return pd.DataFrame(rows)

allrows = []
for cut in ts.CUTS:
    s,e,tes,tee = cut
    tr = df[(df["date"]>=s)&(df["date"]<=e)]
    te = df[(df["date"]>=tes)&(df["date"]<=tee)].dropna(subset=[ts.RAW])
    if len(te) < 100: continue
    for name, label in [("raw", ts.RAW), ("trendscan", ts.TS)]:
        p = ts.train_predict(tr, te, feat_cols, label, 0)
        if p is None: continue
        a = portfolio_alpha(p, te); a["model"] = name; allrows.append(a)

R = pd.concat(allrows, ignore_index=True)
def stat(model, regime):
    s = R[(R.model==model) & ((R.regime==regime) if regime!="ALL" else True)]["alpha"]
    if len(s) < 5: return (np.nan, np.nan, 0)
    # ~252 trading days/yr, 60d holding -> ~4.2 independent periods/yr for a rough annualized Sharpe
    sharpe = s.mean()/ (s.std()+1e-9) * np.sqrt(252/60)
    return (s.mean(), sharpe, len(s))

log.info("Top-20%% portfolio ALPHA (realized fwd_60d_excess vs universe), mean / annualized-Sharpe:")
log.info("%-10s %18s %18s %18s %18s", "model", "ALL", "BULL_CALM", "BEAR", "BULL_VOL")
for m in ("raw","trendscan"):
    cells=[]
    for rg in ("ALL","BULL_CALM","BEAR","BULL_VOLATILE"):
        mu,sh,n = stat(m,rg); cells.append(f"{mu:+.4f}/{sh:+.2f}(n{n})")
    log.info("%-10s %18s %18s %18s %18s", m, *cells)

log.info("\nDECISION (does selecting by trend-scan beat selecting by raw on realized P&L?):")
for rg in ("ALL","BULL_CALM"):
    rmu,rsh,_ = stat("raw",rg); tmu,tsh,_ = stat("trendscan",rg)
    log.info("  %-9s raw alpha %+.4f (Sharpe %+.2f)  vs  trendscan %+.4f (Sharpe %+.2f)  -> %s",
             rg, rmu, rsh, tmu, tsh, "trend-scan better" if tmu>rmu else "raw better")
R.to_csv("/tmp/trendscan_portfolio_sim.csv", index=False)
log.info("per-date detail -> /tmp/trendscan_portfolio_sim.csv")
