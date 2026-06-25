"""RESEARCH: is the hard RealizedVolGate (drop candidates >60% annualized 60d vol)
leaving money on the table vs. admitting high-vol names and letting vol-target sizing
shrink them? Operator thesis: high-vol days are opportunities too — raise the bar, don't freeze.

Method (purged walk-forward, no lookahead):
- realized vol60_ann per (ticker,date) from OHLCV daily returns (std*sqrt(252)) — matches the gate.
- OOS model score per (ticker,date) from a pooled purged-WF XGB on the alpha158+regime panel.
- Among each day's TOP-QUINTILE by model score (the would-buy set), split by the 60% vol cap:
  ADMITTED (<=60%) vs GATED (>60%). Compare mean fwd_60d_excess, hit-rate, and per-name Sharpe
  (mean/std of fwd). If GATED high-score names have POSITIVE fwd return ~ comparable Sharpe,
  the hard cap discards alpha that inverse-vol sizing would capture at controlled risk.
- Sizing sim on the top-quintile: (A) hard cap = equal-weight admitted only; (B) inverse-vol =
  admit all, weight ∝ 1/vol (vol-target). Report mean daily basket fwd return + Sharpe.
"""
import glob
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")
R = "/Users/renhao/git/github/RenQuant"
LABEL = "fwd_60d_excess"
REG = {"BULL_CALM": "regime_p_bull_calm", "BEAR": "regime_p_bear", "BULL_VOLATILE": "regime_p_bull_volatile"}
N_CUTS, EMB, CAP = 6, 60, 0.60


def realized_vol(tickers):
    out = []
    for t in tickers:
        fs = glob.glob(f"{R}/data/ohlcv/{t}/1d.parquet")
        if not fs:
            continue
        d = pd.read_parquet(fs[0]).sort_index()
        ret = d["close"].pct_change()
        vol = ret.rolling(60).std() * np.sqrt(252)
        out.append(pd.DataFrame({"ticker": t, "date": pd.to_datetime(d.index), "vol60_ann": vol.values}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["ticker", "date", "vol60_ann"])


df = pd.read_parquet(f"{R}/data/alpha158_291_fund_regime_dataset.parquet").dropna(subset=[LABEL]).copy()
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["date", "ticker"]).reset_index(drop=True)
df["regime"] = df[[REG[r] for r in REG]].values.argmax(1)
tickers = sorted(str(t).upper() for t in df["ticker"].unique())
vol = realized_vol(tickers)
df = df.merge(vol, on=["ticker", "date"], how="left")
print(f"rows={len(df)} vol-merged cov={df['vol60_ann'].notna().mean()*100:.0f}%", flush=True)

meta = {"ticker", "date", "regime", "vol60_ann", "fwd_5d_excess", "fwd_20d_excess",
        "fwd_60d_excess", "split_label", *REG.values()}
feats = [c for c in df.columns if c not in meta]

# pooled purged-WF OOS predictions
dts = np.sort(df["date"].unique())
b = np.linspace(0, len(dts), N_CUTS + 1).astype(int)
preds = []
for k in range(1, N_CUTS):
    i = b[k]
    if i >= len(dts):
        break
    lo = dts[i]
    emb = pd.Timestamp(lo) - pd.Timedelta(days=EMB)
    tr = df[df.date <= min(pd.Timestamp(dts[b[k] - 1]), emb)]
    te = df[(df.date >= lo) & (df.date <= dts[min(b[k + 1], len(dts) - 1)])]
    if len(tr) < 1000 or len(te) < 200:
        continue
    m = XGBRegressor(n_estimators=180, max_depth=5, learning_rate=0.05, subsample=0.8,
                     colsample_bytree=0.8, n_jobs=4, random_state=0, verbosity=0)
    m.fit(tr[feats].values, tr[LABEL].values)
    p = te[["date", "ticker", "regime", "vol60_ann", LABEL]].copy()
    p["score"] = m.predict(te[feats].values)
    preds.append(p)
    print(f"  cut {k}: train={len(tr)} test={len(te)}", flush=True)
P = pd.concat(preds, ignore_index=True).dropna(subset=["vol60_ann"])
print(f"OOS scored rows={len(P)}", flush=True)

# would-buy set = top quintile by score each day
P["day_rank"] = P.groupby("date")["score"].rank(pct=True)
buy = P[P["day_rank"] >= 0.80].copy()
buy["gated"] = buy["vol60_ann"] > CAP


def stats(x):
    n = len(x)
    m = x[LABEL].mean()
    s = x[LABEL].std()
    return n, m, (x[LABEL] > 0).mean(), (m / s if s else np.nan)


print("\n=== TOP-QUINTILE would-buy names, split by the 60% vol cap ===", flush=True)
print(f"{'group':16s} {'n':>7s} {'meanFwd':>9s} {'hit':>6s} {'Sharpe(/name)':>13s}", flush=True)
for label, sub in [("ADMITTED <=60%", buy[~buy.gated]), ("GATED >60%", buy[buy.gated])]:
    n, m, h, sh = stats(sub)
    print(f"{label:16s} {n:7d} {m:+.4f}   {h:.2f}   {sh:+.3f}", flush=True)

print("\n--- GATED high-score names by regime (is the dropped alpha real?) ---", flush=True)
for ri, rn in enumerate(REG):
    sub = buy[(buy.gated) & (buy.regime == ri)]
    if len(sub) < 30:
        print(f"{rn:14s} n={len(sub)} (thin)", flush=True); continue
    n, m, h, sh = stats(sub)
    print(f"{rn:14s} n={n:5d} meanFwd={m:+.4f} hit={h:.2f} Sharpe={sh:+.3f}", flush=True)

# sizing sim on the daily top-quintile basket
print("\n=== sizing sim: per-day top-quintile basket fwd return ===", flush=True)
rowsA, rowsB = [], []
for d, g in buy.groupby("date"):
    adm = g[~g.gated]
    if len(adm):                                   # (A) hard cap: equal-weight admitted only
        rowsA.append(adm[LABEL].mean())
    if len(g):                                     # (B) inverse-vol: admit all, weight ∝ 1/vol
        w = (1.0 / g["vol60_ann"]).clip(upper=1 / 0.05)
        rowsB.append(float(np.average(g[LABEL], weights=w)))
A = np.array(rowsA); B = np.array(rowsB)
print(f"(A) hard-cap equal-wt   days={len(A)} meanFwd={A.mean():+.4f} Sharpe={A.mean()/A.std():+.3f}", flush=True)
print(f"(B) inverse-vol admit-all days={len(B)} meanFwd={B.mean():+.4f} Sharpe={B.mean()/B.std():+.3f}", flush=True)
print("\nDONE", flush=True)
