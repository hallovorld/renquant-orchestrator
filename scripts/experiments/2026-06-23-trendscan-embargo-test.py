#!/usr/bin/env python
"""Prove the embargo gap is the leakage floor: re-run the shuffle control WITH a proper
60d-label embargo (drop train rows whose forward-label window reaches into the test) and
show the shuffled-label IC collapses toward ~0.
"""
import importlib.util, numpy as np, pandas as pd, logging, xgboost as xgb
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("embargo")
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
EMBARGO = pd.Timedelta(days=90)  # 60 trading days ~ 84-90 calendar days

def shuffled_real(tr, te, label, shuffle, seed):
    rng = np.random.default_rng(seed)
    tr = tr.dropna(subset=[label]).copy()
    if len(tr) < 1000 or len(te) < 100: return None
    y = tr[label].to_numpy(np.float64).copy(); d = tr["date"].to_numpy()
    if shuffle:
        for dt in np.unique(d):
            idx = np.where(d == dt)[0]; y[idx] = rng.permutation(y[idx])
    X = tr[feat_cols].fillna(0).to_numpy(np.float64); Xte = te[feat_cols].fillna(0).to_numpy(np.float64)
    mu, sd = X.mean(0), X.std(0)+1e-9; X = ((X-mu)/sd).clip(-5,5); Xte = ((Xte-mu)/sd).clip(-5,5)
    o = np.argsort(d); _, g = np.unique(d[o], return_counts=True)
    dm = xgb.DMatrix(X[o], label=y[o]); dm.set_group(g)
    return xgb.train(ts.PARAMS, dm, num_boost_round=ts.N_ROUNDS).predict(xgb.DMatrix(Xte))

def run(embargo):
    # multi-shuffle null (5 seeds) for raw + trendscan, ALL IC, with/without embargo
    out = {}
    for label, name in [(ts.RAW,"raw"), (ts.TS,"trendscan")]:
        shuf = []
        for cut in ts.CUTS:
            s,e,tes,tee = cut
            cut_end = pd.Timestamp(tes) - embargo if embargo else pd.Timestamp(tes)
            tr = df[(df["date"]>=s)&(df["date"]<=pd.Timestamp(e))&(df["date"]<cut_end)]
            te = df[(df["date"]>=tes)&(df["date"]<=tee)].dropna(subset=[ts.RAW])
            if len(te)<100: continue
            y = te[ts.RAW].to_numpy(float); dd=te["date"].to_numpy(); rg=te["regime"].to_numpy()
            for seed in (1,2,3,4,5):
                p = shuffled_real(tr, te, label, True, seed)
                if p is not None: shuf.append(ts.cs_ic_by_regime(p,y,dd,rg)["ALL"])
        out[name] = (np.nanmean(shuf), np.nanstd(shuf))
    return out

log.info("multi-shuffle (5 seeds) ALL-IC null, mean +/- std:")
log.info("--- NO embargo (current gate) ---")
no = run(None)
for k,(m,s) in no.items(): log.info("  %-10s shuffled ALL IC = %+.4f +/- %.4f", k, m, s)
log.info("--- WITH 90d embargo (fix) ---")
yes = run(EMBARGO)
for k,(m,s) in yes.items(): log.info("  %-10s shuffled ALL IC = %+.4f +/- %.4f", k, m, s)
log.info("VERDICT: embargo %s the leakage floor (raw shuffled %+.4f -> %+.4f)",
         "REMOVES" if abs(yes["raw"][0]) < abs(no["raw"][0])/2 else "does NOT remove",
         no["raw"][0], yes["raw"][0])
