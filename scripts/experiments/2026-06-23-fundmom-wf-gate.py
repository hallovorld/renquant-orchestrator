#!/usr/bin/env python
"""Fundamental-MOMENTUM factor trial (the self-serviceable cousin of analyst-revision).

True analyst estimate-revision data is proprietary (IBES/FactSet/Zacks) and not in-repo.
But "fundamental momentum" (AQR) — *improving realized fundamentals* — can be built from the
SEC fundamentals we already have (`data/sec_fundamentals_daily.parquet`:
earnings_yield, book_to_price, gross_profitability, roe, asset_growth), entirely autonomously.

Hypothesis: stocks whose fundamentals are IMPROVING (positive trailing change in EY/GP/ROE,
falling asset_growth) keep outperforming — an orthogonal signal that might add a placebo-clean
BULL_CALM edge the price/technical stack lacks.

Features built (trailing, no leakage): for each of the 5 factors, the 63d (~1Q) and 252d (~1Y)
change. ~10 fundamental-momentum features, merged into the regime panel by (ticker,date).

Gate (identical to the neutralization/trend-scan trials, so comparable):
  6-cut WF, XGB rank:pairwise (production params), train on RAW fwd_60d_excess, IC measured vs
  raw, segmented per regime; PLACEBO = label shifted +60d. placebo-clean = real - placebo.
Variants compared: BASE (existing features), BASE+FM (+ fundamental momentum), FM_ONLY.
Decision: does fundamental momentum lift the BULL_CALM placebo-clean IC (>= +0.02 and >= BASE)?

Read-only on data; writes nothing to any canonical/production path.
"""
from __future__ import annotations
import logging
import numpy as np, pandas as pd, xgboost as xgb
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("fundmom-wf")

REGIME = "data/alpha158_291_fund_regime_dataset.parquet"
SEC = "data/sec_fundamentals_daily.parquet"
RAW = "fwd_60d_excess"
FACTORS = ["earnings_yield", "book_to_price", "gross_profitability", "roe", "asset_growth"]
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
REGIME_COLS = {"regime_p_bull_calm": "BULL_CALM", "regime_p_bear": "BEAR",
               "regime_p_bull_volatile": "BULL_VOLATILE"}


def cs_ic_by_regime(pred, y_raw, dates, regime):
    df = pd.DataFrame({"p": pred, "y": y_raw, "date": dates, "reg": regime})
    out = {}
    for name, sub in [("ALL", df)] + [(r, df[df["reg"] == r]) for r in df["reg"].unique()]:
        ics = [spearmanr(g["p"], g["y"])[0] for _, g in sub.groupby("date") if len(g) >= 5]
        ics = [x for x in ics if not np.isnan(x)]
        out[name] = float(np.mean(ics)) if ics else np.nan
    return out


def build_fundmom(sec: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    sec = sec.sort_values(["ticker", "date"]).copy()
    fm_cols = []
    g = sec.groupby("ticker", group_keys=False)
    for f in FACTORS:
        for w in (63, 252):
            col = f"fm_{f}_{w}"
            sec[col] = g[f].transform(lambda s: s - s.shift(w))
            fm_cols.append(col)
    return sec[["ticker", "date"] + fm_cols], fm_cols


def train_predict(tr, te, feat_cols, shift_days=0):
    if shift_days:
        tr = tr.sort_values(["ticker", "date"]).copy()
        tr[RAW] = tr.groupby("ticker")[RAW].shift(-shift_days)
    tr = tr.dropna(subset=[RAW])
    if len(tr) < 1000 or len(te) < 100:
        return None
    Xtr = tr[feat_cols].fillna(0).to_numpy(np.float64)
    ytr = tr[RAW].clip(-5, 5).to_numpy(np.float64)
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
    log.info("loading regime panel + SEC fundamentals ...")
    df = pd.read_parquet(REGIME)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=[RAW]).copy()
    probs = df[list(REGIME_COLS)].to_numpy(float)
    df["regime"] = np.array([REGIME_COLS[list(REGIME_COLS)[i]] for i in probs.argmax(1)])

    sec = pd.read_parquet(SEC); sec["date"] = pd.to_datetime(sec["date"])
    fm, fm_cols = build_fundmom(sec)
    df = df.merge(fm, on=["ticker", "date"], how="left")
    cov = df[fm_cols].notna().any(axis=1).mean()
    log.info("merged rows=%d  fundmom feature coverage=%.2f  regimes=%s",
             len(df), cov, dict(df["regime"].value_counts()))

    base_excl = {"ticker", "date", "split_label", "regime",
                 "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess"} | set(REGIME_COLS) | set(fm_cols)
    base_cols = [c for c in df.columns if c not in base_excl]
    variants = {"BASE": base_cols, "BASE+FM": base_cols + fm_cols, "FM_ONLY": fm_cols}
    log.info("feature counts: BASE=%d  BASE+FM=%d  FM_ONLY=%d",
             len(base_cols), len(base_cols) + len(fm_cols), len(fm_cols))

    rows = []
    for ci, cut in enumerate(CUTS, 1):
        ts_, tre, tes, tee = cut
        tr0 = df[(df["date"] >= ts_) & (df["date"] <= tre)]
        te = df[(df["date"] >= tes) & (df["date"] <= tee)].dropna(subset=[RAW])
        if len(te) < 100:
            continue
        y_raw = te[RAW].to_numpy(float); dts = te["date"].to_numpy(); rgs = te["regime"].to_numpy()
        for vname, feats in variants.items():
            for kind, shift in [("real", 0), ("placebo", 60)]:
                p = train_predict(tr0, te, feats, shift_days=shift)
                if p is None:
                    continue
                ic = cs_ic_by_regime(p, y_raw, dts, rgs)
                rows.append({"cut": ci, "variant": vname, "kind": kind, **ic})
                log.info("cut%d %-8s %-7s  ALL=%+.4f  BULL_CALM=%+.4f  BEAR=%+.4f  BULL_VOL=%+.4f",
                         ci, vname, kind, ic.get("ALL", np.nan), ic.get("BULL_CALM", np.nan),
                         ic.get("BEAR", np.nan), ic.get("BULL_VOLATILE", np.nan))

    R = pd.DataFrame(rows)
    def agg(v, k, r):
        s = R[(R.variant == v) & (R.kind == k)][r]
        return float(np.nanmean(s)) if len(s) else np.nan

    log.info("\n============ PER-REGIME WF SUMMARY (mean over cuts) ============")
    log.info("%-8s %-8s %8s %10s %8s %9s", "variant", "kind", "ALL", "BULL_CALM", "BEAR", "BULL_VOL")
    for v in variants:
        for k in ("real", "placebo"):
            log.info("%-8s %-8s %+8.4f %+10.4f %+8.4f %+9.4f", v, k,
                     agg(v, k, "ALL"), agg(v, k, "BULL_CALM"), agg(v, k, "BEAR"), agg(v, k, "BULL_VOLATILE"))
    log.info("\nDECISION (does fundamental momentum add a placebo-clean BULL_CALM edge?):")
    base_clean = agg("BASE", "real", "BULL_CALM") - agg("BASE", "placebo", "BULL_CALM")
    fm_clean = agg("BASE+FM", "real", "BULL_CALM") - agg("BASE+FM", "placebo", "BULL_CALM")
    only_clean = agg("FM_ONLY", "real", "BULL_CALM") - agg("FM_ONLY", "placebo", "BULL_CALM")
    log.info("  BASE     placebo-clean BULL_CALM = %+.4f", base_clean)
    log.info("  BASE+FM  placebo-clean BULL_CALM = %+.4f", fm_clean)
    log.info("  FM_ONLY  placebo-clean BULL_CALM = %+.4f (standalone signal)", only_clean)
    if fm_clean >= base_clean + 0.005 and fm_clean >= 0.02:
        log.info("  => POSITIVE: fundamental momentum adds a placebo-clean BULL_CALM edge; graduate.")
    elif only_clean >= 0.015:
        log.info("  => PARTIAL: standalone fund-momentum has signal but doesn't lift the ensemble; revisit as orthogonal sleeve.")
    else:
        log.info("  => NEGATIVE: realized fundamental momentum does not add a BULL_CALM edge (true estimate-revision may differ).")
    R.to_csv("/tmp/fundmom_wf_gate.csv", index=False)
    log.info("per-cut detail -> /tmp/fundmom_wf_gate.csv")


if __name__ == "__main__":
    main()
