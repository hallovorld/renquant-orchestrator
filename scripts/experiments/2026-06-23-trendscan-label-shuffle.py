#!/usr/bin/env python
"""Label-shuffle sanity for the trend-scan lead (completes the production WF-sanity trio).

A/A (seed stability) and time-shift placebo are already done (seed-robustness + the gate's
placebo). The remaining control: shuffle the trend-scan label WITHIN each training date and
retrain — IC must collapse to ~0. If it doesn't, the signal is spurious/leaky.
"""
import importlib.util, numpy as np, pandas as pd, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("ts-shuffle")
spec = importlib.util.spec_from_file_location("tsgate", "/tmp/trendscan_wf_gate.py")
ts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ts)

reg = pd.read_parquet(ts.REGIME, columns=["ticker", "date"] + list(ts.REGIME_COLS))
reg["date"] = pd.to_datetime(reg["date"])
probs = reg[list(ts.REGIME_COLS)].to_numpy(float)
reg["regime"] = np.array([ts.REGIME_COLS[list(ts.REGIME_COLS)[i]] for i in probs.argmax(1)])
df = pd.read_parquet(ts.MULTIH); df["date"] = pd.to_datetime(df["date"])
df = df.dropna(subset=[ts.RAW]).copy()
df[ts.TS] = ts.build_trendscan_label(df)
df = df.merge(reg[["ticker", "date", "regime"]], on=["ticker", "date"], how="inner")
excl = {"ticker","date","split_label","regime",ts.TS,"fwd_5d_excess","fwd_20d_excess","fwd_60d_excess",
        "fwd_5d_excess_raw","fwd_10d_excess_raw","fwd_20d_excess_raw","fwd_60d_excess_raw"}
feat_cols = [c for c in df.columns if c not in excl]
rng = np.random.default_rng(42)

def train_predict_shuffled(tr, te):
    tr = tr.dropna(subset=[ts.TS]).copy()
    if len(tr) < 1000 or len(te) < 100: return None
    y = tr[ts.TS].to_numpy(np.float64).copy()
    d = tr["date"].to_numpy()
    for dt in np.unique(d):       # shuffle within each date (preserve date distribution)
        idx = np.where(d == dt)[0]; y[idx] = rng.permutation(y[idx])
    import xgboost as xgb
    X = tr[feat_cols].fillna(0).to_numpy(np.float64); Xte = te[feat_cols].fillna(0).to_numpy(np.float64)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    X = ((X - mu) / sd).clip(-5, 5); Xte = ((Xte - mu) / sd).clip(-5, 5)
    o = np.argsort(d); _, g = np.unique(d[o], return_counts=True)
    dm = xgb.DMatrix(X[o], label=y[o]); dm.set_group(g)
    b = xgb.train(ts.PARAMS, dm, num_boost_round=ts.N_ROUNDS)
    return b.predict(xgb.DMatrix(Xte))

real_all, shuf_all, shuf_bc = [], [], []
for cut in ts.CUTS:
    s, e, tes, tee = cut
    tr = df[(df["date"] >= s) & (df["date"] <= e)]
    te = df[(df["date"] >= tes) & (df["date"] <= tee)].dropna(subset=[ts.RAW])
    if len(te) < 100: continue
    y = te[ts.RAW].to_numpy(float); dd = te["date"].to_numpy(); rg = te["regime"].to_numpy()
    pr = ts.train_predict(tr, te, feat_cols, ts.TS, 0)
    ps = train_predict_shuffled(tr, te)
    if pr is not None: real_all.append(ts.cs_ic_by_regime(pr, y, dd, rg)["ALL"])
    if ps is not None:
        m = ts.cs_ic_by_regime(ps, y, dd, rg); shuf_all.append(m["ALL"]); shuf_bc.append(m.get("BULL_CALM", np.nan))

log.info("trend-scan REAL  ALL IC (mean over cuts) = %+.4f", np.nanmean(real_all))
log.info("trend-scan SHUFFLED ALL IC               = %+.4f  (must be ~0)", np.nanmean(shuf_all))
log.info("trend-scan SHUFFLED BULL_CALM IC         = %+.4f  (must be ~0)", np.nanmean(shuf_bc))
ok = abs(np.nanmean(shuf_all)) < 0.01 and abs(np.nanmean(shuf_bc)) < 0.01
log.info("VERDICT: %s", "PASS — shuffled label gives ~0 IC, signal is not spurious/leaky"
         if ok else "FAIL — shuffled label still yields IC, signal is suspect")
