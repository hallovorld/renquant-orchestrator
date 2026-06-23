#!/usr/bin/env python
"""Drift-free LABEL trial: trend-scanning label through the per-regime WF + placebo gate.

Roadmap's next untested in-repo model lever (neutralization already rejected). A
trend-scanning label (Lopez de Prado) measures the STRENGTH/PERSISTENCE of the forward
trend rather than its raw 60d magnitude — the hypothesis is that this is more "drift-free"
and recovers a real BULL_CALM edge (placebo-clean IC >= +0.02).

Construction (faithful + feasible with in-repo data):
  - Data `data/alpha158_291_fundamental_dataset_multih.parquet` carries RAW cumulative
    forward excess returns at h in {5,10,20,60} (`fwd_{h}d_excess_raw`).
  - For each row the forward cum-return path is R(0)=0, R(5)=r5, R(10)=r10, R(20)=r20,
    R(60)=r60. For each candidate window (endpoints 20 and 60) fit OLS R~h (with intercept)
    and take the slope t-stat; the trend-scan label = the SIGNED t-stat of the window with
    the larger |t| (the most statistically significant trend) — Lopez de Prado trend-scanning.
  - Regime label merged from the GMM regime dataset by (ticker,date).

Gate (identical to the neutralization trial, so results are comparable):
  6-cut WF, XGB rank:pairwise (production params), IC measured vs RAW fwd_60d_excess,
  segmented per regime; PLACEBO = label shifted +60d. placebo-clean = real - placebo.
  Compare the trend-scan label vs the raw fwd_60d_excess label.

Read-only on data; writes nothing to any canonical/production path.
"""
from __future__ import annotations
import json, logging
import numpy as np, pandas as pd, xgboost as xgb
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("trendscan-wf")

MULTIH = "data/alpha158_291_fundamental_dataset_multih.parquet"
REGIME = "data/alpha158_291_fund_regime_dataset.parquet"
RAW = "fwd_60d_excess"          # economic target IC is always measured against this
TS = "trendscan_label"
PARAMS = {"objective": "rank:pairwise", "eta": 0.05, "max_depth": 5,
          "min_child_weight": 50, "subsample": 0.7, "colsample_bytree": 0.7,
          "nthread": 8, "verbosity": 0, "seed": 42}
N_ROUNDS = 100
CUTS = [
    ("2017-01-01", "2019-12-31", "2020-02-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-02-01", "2021-12-31"),
    ("2019-01-01", "2021-12-31", "2022-02-01", "2022-12-31"),
    ("2020-01-01", "2022-12-31", "2023-02-01", "2023-12-31"),
    ("2021-01-01", "2023-12-31", "2024-02-01", "2024-12-31"),
    ("2022-01-01", "2024-12-31", "2025-02-01", "2025-12-31"),
]
REGIME_COLS = {"regime_p_bull_calm": "BULL_CALM",
               "regime_p_bear": "BEAR",
               "regime_p_bull_volatile": "BULL_VOLATILE"}


def cs_ic_by_regime(pred, y_raw, dates, regime):
    df = pd.DataFrame({"p": pred, "y": y_raw, "date": dates, "reg": regime})
    out = {}
    for name, sub in [("ALL", df)] + [(r, df[df["reg"] == r]) for r in df["reg"].unique()]:
        ics = [spearmanr(g["p"], g["y"])[0] for _, g in sub.groupby("date") if len(g) >= 5]
        ics = [x for x in ics if not np.isnan(x)]
        out[name] = float(np.mean(ics)) if ics else np.nan
    return out


def _ols_slope_t(hs, Rs):
    """Vectorized OLS slope t-stat of R~h (with intercept) for a fixed set of x-points `hs`
    across all rows. Rs: (n_rows, len(hs)). Returns t-stat array (n_rows,)."""
    x = np.asarray(hs, float)
    n = len(x); xm = x.mean(); Sxx = ((x - xm) ** 2).sum()
    Rm = Rs.mean(axis=1, keepdims=True)
    b = ((x - xm)[None, :] * (Rs - Rm)).sum(axis=1) / Sxx          # slope
    a = Rm[:, 0] - b * xm                                          # intercept
    fit = a[:, None] + b[:, None] * x[None, :]
    sse = ((Rs - fit) ** 2).sum(axis=1)
    se_b = np.sqrt((sse / (n - 2)) / Sxx) + 1e-12
    return b / se_b


def build_trendscan_label(df):
    """Signed t-stat of the most significant forward-trend window (endpoints 20 and 60)."""
    need = ["fwd_5d_excess_raw", "fwd_10d_excess_raw", "fwd_20d_excess_raw", "fwd_60d_excess_raw"]
    r5, r10, r20, r60 = (df[c].to_numpy(float) for c in need)
    z = np.zeros(len(df))
    # window A: endpoint 20  (h=0,5,10,20)
    tA = _ols_slope_t([0, 5, 10, 20], np.column_stack([z, r5, r10, r20]))
    # window B: endpoint 60  (h=0,5,10,20,60)
    tB = _ols_slope_t([0, 5, 10, 20, 60], np.column_stack([z, r5, r10, r20, r60]))
    lab = np.where(np.abs(tA) >= np.abs(tB), tA, tB)
    # rows missing any horizon -> NaN label (dropped downstream)
    miss = ~np.isfinite(r5 + r10 + r20 + r60)
    lab[miss] = np.nan
    return lab


def train_predict(tr, te, feat_cols, label, shift_days=0):
    if shift_days:
        tr = tr.sort_values(["ticker", "date"]).copy()
        tr[label] = tr.groupby("ticker")[label].shift(-shift_days)
    tr = tr.dropna(subset=[label])
    if len(tr) < 1000 or len(te) < 100:
        return None
    Xtr = tr[feat_cols].fillna(0).to_numpy(np.float64)
    ytr = tr[label].clip(*np.percentile(tr[label], [1, 99])).to_numpy(np.float64)
    Xte = te[feat_cols].fillna(0).to_numpy(np.float64)
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    Xtr = ((Xtr - mu) / sd).clip(-5, 5); Xte = ((Xte - mu) / sd).clip(-5, 5)
    order = np.argsort(tr["date"].to_numpy())
    Xs, ys = Xtr[order], ytr[order]
    _, gsz = np.unique(tr["date"].to_numpy()[order], return_counts=True)
    dtr = xgb.DMatrix(Xs, label=ys); dtr.set_group(gsz)
    booster = xgb.train(PARAMS, dtr, num_boost_round=N_ROUNDS)
    return booster.predict(xgb.DMatrix(Xte))


def main():
    log.info("loading multih panel + regime labels ...")
    reg = pd.read_parquet(REGIME, columns=["ticker", "date"] + list(REGIME_COLS))
    reg["date"] = pd.to_datetime(reg["date"])
    probs = reg[list(REGIME_COLS)].to_numpy(float)
    reg["regime"] = np.array([REGIME_COLS[list(REGIME_COLS)[i]] for i in probs.argmax(1)])
    reg = reg[["ticker", "date", "regime"]]

    df = pd.read_parquet(MULTIH)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=[RAW]).copy()
    df[TS] = build_trendscan_label(df)
    df = df.merge(reg, on=["ticker", "date"], how="inner")
    log.info("merged rows=%d dates=%d regimes=%s", len(df), df["date"].nunique(),
             dict(df["regime"].value_counts()))
    corr = df[[RAW, TS]].corr(method="spearman").iloc[0, 1]
    log.info("trendscan vs raw label rank-corr = %.3f (low = genuinely different target)", corr)

    excl = {"ticker", "date", "split_label", "regime", TS,
            "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess",
            "fwd_5d_excess_raw", "fwd_10d_excess_raw", "fwd_20d_excess_raw", "fwd_60d_excess_raw"}
    feat_cols = [c for c in df.columns if c not in excl]
    log.info("feats=%d", len(feat_cols))

    rows = []
    for ci, cut in enumerate(CUTS, 1):
        ts_, tre, tes, tee = cut
        tr = df[(df["date"] >= ts_) & (df["date"] <= tre)]
        te = df[(df["date"] >= tes) & (df["date"] <= tee)].dropna(subset=[RAW])
        if len(te) < 100:
            continue
        y_raw = te[RAW].to_numpy(float); dts = te["date"].to_numpy(); rgs = te["regime"].to_numpy()
        for variant, label in [("raw", RAW), ("trendscan", TS)]:
            for kind, shift in [("real", 0), ("placebo", 60)]:
                p = train_predict(tr, te, feat_cols, label, shift_days=shift)
                if p is None:
                    continue
                ic = cs_ic_by_regime(p, y_raw, dts, rgs)
                rows.append({"cut": ci, "variant": variant, "kind": kind, **ic})
                log.info("cut%d %-9s %-7s  ALL=%+.4f  BULL_CALM=%+.4f  BEAR=%+.4f  BULL_VOL=%+.4f",
                         ci, variant, kind, ic.get("ALL", np.nan), ic.get("BULL_CALM", np.nan),
                         ic.get("BEAR", np.nan), ic.get("BULL_VOLATILE", np.nan))

    R = pd.DataFrame(rows)
    def agg(v, k, r):
        s = R[(R.variant == v) & (R.kind == k)][r]
        return float(np.nanmean(s)) if len(s) else np.nan

    log.info("\n============ PER-REGIME WF SUMMARY (mean over cuts) ============")
    log.info("%-10s %-8s %8s %10s %8s %9s", "variant", "kind", "ALL", "BULL_CALM", "BEAR", "BULL_VOL")
    for v in ("raw", "trendscan"):
        for k in ("real", "placebo"):
            log.info("%-10s %-8s %+8.4f %+10.4f %+8.4f %+9.4f", v, k,
                     agg(v, k, "ALL"), agg(v, k, "BULL_CALM"), agg(v, k, "BEAR"), agg(v, k, "BULL_VOLATILE"))
    raw_clean = agg("raw", "real", "BULL_CALM") - agg("raw", "placebo", "BULL_CALM")
    ts_clean = agg("trendscan", "real", "BULL_CALM") - agg("trendscan", "placebo", "BULL_CALM")
    log.info("\nDECISION (target: trendscan BULL_CALM placebo-clean IC >= +0.02 AND >= raw):")
    log.info("  raw       placebo-clean BULL_CALM = %+.4f", raw_clean)
    log.info("  trendscan placebo-clean BULL_CALM = %+.4f", ts_clean)
    if ts_clean >= 0.02 and ts_clean >= raw_clean:
        log.info("  => PASS: trend-scanning label recovers/keeps a real BULL_CALM edge; graduate to a gated retrain.")
    elif ts_clean >= raw_clean + 0.005:
        log.info("  => PARTIAL: trend-scanning helps BULL_CALM but not decisively; iterate.")
    else:
        log.info("  => NEGATIVE: trend-scanning label does not beat the raw label in BULL_CALM.")
    R.to_csv("/tmp/trendscan_wf_gate.csv", index=False)
    log.info("per-cut detail -> /tmp/trendscan_wf_gate.csv")


if __name__ == "__main__":
    main()
