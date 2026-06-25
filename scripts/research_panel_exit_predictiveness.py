"""Empirical test of the CrossSectionalPanelExit (`panel_conviction_xs`) rule.

The rule exits a held name when it is in the bottom `xs_panel_percentile_floor` (0.20) of
today's panel-score cross-section AND `mu <= mu_sell_ceiling` (0.0) — the AND-rule — or when
`mu <= mu_strong_sell_ceiling` (-0.05) alone (the OR-bypass). It is σ-blind and runs pre-QP,
overriding it. Question: does the AND-rule's "bottom-20% + mu≈0" trigger (AMZN's 2026-06-25
case) actually predict forward underperformance, or fire on noise — and does that depend on the
regime?

Method: pooled purged-WF XGB proxy panel score (NOT the live PatchTST — directional only),
per (date,ticker) cross-sectional score percentile, forward 60d excess return by percentile band
and by regime, with bootstrap CIs. The decision-relevant statistic is (exit-zone fwd) − (the
median name you'd hold instead): if ~0, exiting captures no alpha.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

R = "/Users/renhao/git/github/RenQuant"
LABEL = "fwd_60d_excess"
REGC = {"BULL_CALM": "regime_p_bull_calm", "BEAR": "regime_p_bear", "BULL_VOLATILE": "regime_p_bull_volatile"}


def boot_ci(x, n=2000, seed=0):
    """Bootstrap 95% CI of the mean. Returns (mean, lo, hi); CI is NaN for tiny n."""
    x = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    if len(x) < 20:
        return (float(x.mean()) if len(x) else np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    bs = np.array([rng.choice(x, len(x), replace=True).mean() for _ in range(n)])
    return float(x.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main():
    from xgboost import XGBRegressor
    warnings.filterwarnings("ignore")
    df = pd.read_parquet(f"{R}/data/alpha158_291_fund_regime_dataset.parquet").dropna(subset=[LABEL]).copy()
    df["date"] = pd.to_datetime(df["date"]); df = df.sort_values(["date", "ticker"]).reset_index(drop=True)
    df["regime"] = df[[REGC[r] for r in REGC]].values.argmax(1)
    meta = {"ticker", "date", "regime", "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess", "split_label", *REGC.values()}
    feats = [c for c in df.columns if c not in meta]
    dts = np.sort(df["date"].unique()); b = np.linspace(0, len(dts), 7).astype(int)
    P = []
    for k in range(1, 6):
        lo = dts[b[k]]; emb = pd.Timestamp(lo) - pd.Timedelta(days=60)
        tr = df[df.date <= min(pd.Timestamp(dts[b[k] - 1]), emb)]
        te = df[(df.date >= lo) & (df.date <= dts[min(b[k + 1] - 1, len(dts) - 1)])]
        if len(tr) < 1000 or len(te) < 200:
            continue
        m = XGBRegressor(n_estimators=180, max_depth=5, learning_rate=0.05, subsample=0.8,
                         colsample_bytree=0.8, n_jobs=4, random_state=0, verbosity=0)
        m.fit(tr[feats].values, tr[LABEL].values)
        p = te[["date", "ticker", "regime", LABEL]].copy(); p["score"] = m.predict(te[feats].values)
        P.append(p)
    P = pd.concat(P, ignore_index=True)
    P["pctile"] = P.groupby("date")["score"].rank(pct=True)
    print(f"OOS rows={len(P)}", flush=True)

    print("\n=== forward 60d excess return by cross-sectional score percentile ===", flush=True)
    bands = [(0.0, 0.10, "deep bottom 0-10"), (0.10, 0.20, "AMZN zone 10-20"), (0.20, 0.40, "20-40"),
             (0.40, 0.60, "middle 40-60"), (0.60, 0.80, "60-80"), (0.80, 1.01, "top 80-100")]
    for lo, hi, name in bands:
        s = P[(P.pctile >= lo) & (P.pctile < hi)][LABEL]
        m, cl, ch = boot_ci(s.values)
        print(f"{name:16s} n={len(s):6d} mean={m:+.4f} CI=[{cl:+.4f},{ch:+.4f}] hit={ (s>0).mean():.2f}", flush=True)

    print("\n=== decision delta: exit-zone fwd MINUS the median name you'd hold instead ===", flush=True)
    mid = P[(P.pctile >= 0.40) & (P.pctile < 0.60)][LABEL].mean()
    for lo, hi, name in [(0.0, 0.10, "deep bottom"), (0.10, 0.20, "AMZN zone")]:
        s = P[(P.pctile >= lo) & (P.pctile < hi)][LABEL]
        m, cl, ch = boot_ci(s.values - mid)
        verdict = "exit JUSTIFIED (sig worse)" if ch < 0 else "exit captures ~0 alpha (CI incl 0)"
        print(f"  {name:12s} fwd-median={m:+.4f} CI=[{cl:+.4f},{ch:+.4f}] → {verdict}", flush=True)

    print("\n=== AMZN-zone (bottom-20%) forward return BY REGIME ===", flush=True)
    for ri, rn in enumerate(REGC):
        s = P[(P.regime == ri) & (P.pctile >= 0.10) & (P.pctile < 0.20)][LABEL]
        m, cl, ch = boot_ci(s.values)
        flag = " ← CI incl 0: NOT predictive" if (np.isfinite(cl) and cl <= 0 <= ch) else ""
        print(f"  {rn:14s} n={len(s):6d} mean={m:+.4f} CI=[{cl:+.4f},{ch:+.4f}]{flag}", flush=True)
    print("\nDONE", flush=True)


if __name__ == "__main__":
    main()
