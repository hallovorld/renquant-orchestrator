#!/usr/bin/env python
"""Seed robustness for the trend-scan BULL_CALM placebo-clean result (PR #176).

The headline (+0.0224 vs raw +0.0188) is a THIN margin, so confirm it is not seed-luck:
re-run the same per-regime+placebo gate across seeds {42,43,44} and report the BULL_CALM
placebo-clean IC for raw vs trend-scan each time. Reuses the committed experiment functions.
"""
import importlib.util, numpy as np, pandas as pd, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("ts-seed")

spec = importlib.util.spec_from_file_location("tsgate", "/tmp/trendscan_wf_gate.py")
ts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ts)

# load + prep once (same as the harness main)
reg = pd.read_parquet(ts.REGIME, columns=["ticker", "date"] + list(ts.REGIME_COLS))
reg["date"] = pd.to_datetime(reg["date"])
probs = reg[list(ts.REGIME_COLS)].to_numpy(float)
reg["regime"] = np.array([ts.REGIME_COLS[list(ts.REGIME_COLS)[i]] for i in probs.argmax(1)])
reg = reg[["ticker", "date", "regime"]]
df = pd.read_parquet(ts.MULTIH); df["date"] = pd.to_datetime(df["date"])
df = df.dropna(subset=[ts.RAW]).copy()
df[ts.TS] = ts.build_trendscan_label(df)
df = df.merge(reg, on=["ticker", "date"], how="inner")
excl = {"ticker","date","split_label","regime",ts.TS,"fwd_5d_excess","fwd_20d_excess","fwd_60d_excess",
        "fwd_5d_excess_raw","fwd_10d_excess_raw","fwd_20d_excess_raw","fwd_60d_excess_raw"}
feat_cols = [c for c in df.columns if c not in excl]

def bull_calm_clean(seed):
    ts.PARAMS["seed"] = seed
    acc = {("raw","real"):[], ("raw","placebo"):[], ("trendscan","real"):[], ("trendscan","placebo"):[]}
    for cut in ts.CUTS:
        _, _, tes, tee = cut; s, e = cut[0], cut[1]
        tr = df[(df["date"] >= s) & (df["date"] <= e)]
        te = df[(df["date"] >= tes) & (df["date"] <= tee)].dropna(subset=[ts.RAW])
        if len(te) < 100: continue
        y = te[ts.RAW].to_numpy(float); d = te["date"].to_numpy(); rg = te["regime"].to_numpy()
        for variant, label in [("raw", ts.RAW), ("trendscan", ts.TS)]:
            for kind, shift in [("real", 0), ("placebo", 60)]:
                p = ts.train_predict(tr, te, feat_cols, label, shift_days=shift)
                if p is None: continue
                acc[(variant, kind)].append(ts.cs_ic_by_regime(p, y, d, rg).get("BULL_CALM", np.nan))
    m = {k: np.nanmean(v) for k, v in acc.items()}
    return m[("raw","real")]-m[("raw","placebo")], m[("trendscan","real")]-m[("trendscan","placebo")]

log.info("seed   raw_clean   trendscan_clean   trendscan-raw")
rows = []
for sd in (42, 43, 44):
    rc, tc = bull_calm_clean(sd)
    rows.append((sd, rc, tc))
    log.info("%4d   %+.4f      %+.4f          %+.4f", sd, rc, tc, tc - rc)
rc = np.mean([r[1] for r in rows]); tc = np.mean([r[2] for r in rows])
log.info("MEAN   %+.4f      %+.4f          %+.4f", rc, tc, tc - rc)
wins = sum(1 for r in rows if r[2] >= r[1] and r[2] >= 0.02)
log.info("trend-scan >= raw AND >= +0.02 in %d/3 seeds", wins)
log.info("VERDICT: %s", "ROBUST — holds across seeds" if wins == 3 else
         ("MOSTLY holds (%d/3)" % wins if wins >= 2 else "FRAGILE — seed-sensitive, downgrade the claim"))
