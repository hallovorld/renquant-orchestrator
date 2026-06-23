#!/usr/bin/env python
"""Localize the label-shuffle FAIL: is the +0.02 shuffled IC trend-scan-specific, or a
shared FEATURE-LEAKAGE floor that affects the raw label (and the production model) too?

Shuffle RAW label vs TREND-SCAN label (within each training date), retrain, measure OOS IC
vs raw fwd_60d_excess, ALL + BULL_CALM. If raw-shuffled also ~+0.02 -> shared feature
leakage floor (a pipeline finding, not a trend-scan defect).
"""
import importlib.util, numpy as np, pandas as pd, logging, xgboost as xgb
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("shuf-ctl")
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
rng = np.random.default_rng(42)

def shuffled_pred(tr, te, label):
    tr = tr.dropna(subset=[label]).copy()
    if len(tr) < 1000 or len(te) < 100: return None
    y = tr[label].to_numpy(np.float64).copy(); d = tr["date"].to_numpy()
    for dt in np.unique(d):
        idx = np.where(d == dt)[0]; y[idx] = rng.permutation(y[idx])
    X = tr[feat_cols].fillna(0).to_numpy(np.float64); Xte = te[feat_cols].fillna(0).to_numpy(np.float64)
    mu, sd = X.mean(0), X.std(0)+1e-9; X = ((X-mu)/sd).clip(-5,5); Xte = ((Xte-mu)/sd).clip(-5,5)
    o = np.argsort(d); _, g = np.unique(d[o], return_counts=True)
    dm = xgb.DMatrix(X[o], label=y[o]); dm.set_group(g)
    b = xgb.train(ts.PARAMS, dm, num_boost_round=ts.N_ROUNDS)
    return b.predict(xgb.DMatrix(Xte))

acc = {("raw","ALL"):[], ("raw","BC"):[], ("ts","ALL"):[], ("ts","BC"):[]}
for cut in ts.CUTS:
    s,e,tes,tee = cut
    tr = df[(df["date"]>=s)&(df["date"]<=e)]; te = df[(df["date"]>=tes)&(df["date"]<=tee)].dropna(subset=[ts.RAW])
    if len(te) < 100: continue
    y = te[ts.RAW].to_numpy(float); dd = te["date"].to_numpy(); rg = te["regime"].to_numpy()
    for name, label in [("raw", ts.RAW), ("ts", ts.TS)]:
        p = shuffled_pred(tr, te, label)
        if p is None: continue
        m = ts.cs_ic_by_regime(p, y, dd, rg)
        acc[(name,"ALL")].append(m["ALL"]); acc[(name,"BC")].append(m.get("BULL_CALM", np.nan))

log.info("SHUFFLED-label IC vs raw returns (mean over cuts):")
log.info("  RAW label shuffled        ALL=%+.4f  BULL_CALM=%+.4f", np.nanmean(acc[("raw","ALL")]), np.nanmean(acc[("raw","BC")]))
log.info("  TREND-SCAN label shuffled ALL=%+.4f  BULL_CALM=%+.4f", np.nanmean(acc[("ts","ALL")]), np.nanmean(acc[("ts","BC")]))
rawA = np.nanmean(acc[("raw","ALL")]); tsA = np.nanmean(acc[("ts","ALL")])
if rawA > 0.01 and tsA > 0.01:
    log.info("VERDICT: SHARED feature-leakage floor (~%+.3f) — affects raw + production model too, NOT trend-scan-specific.", (rawA+tsA)/2)
elif tsA > 0.01 >= rawA:
    log.info("VERDICT: TREND-SCAN-SPECIFIC leak — raw is clean (%.4f) but trend-scan leaks (%.4f). Suspect the label build.", rawA, tsA)
else:
    log.info("VERDICT: both ~clean on the metric of interest.")
