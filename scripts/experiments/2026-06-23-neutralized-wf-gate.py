#!/usr/bin/env python
"""Neutralized-label retrain through a per-regime WF + placebo gate.

Question (the cheapest-first model move, residual audit already positive):
  Does training XGB on a MOMENTUM/DRIFT-neutralized label produce a BULL_CALM
  IC that is REAL (placebo-clean) and >= +0.02 — i.e. recover the regime edge
  the raw 60d-excess label loses to slow-drift contamination?

Method (read-only on data; writes nothing to canonical paths):
  - Regime panel: data/alpha158_291_fund_regime_dataset.parquet (has regime_p_*,
    BETA60, ROC60). Regime label per date = argmax of the 3 GMM probs.
  - NEUTRALIZED label = per-date OLS residual of fwd_60d_excess on
    [sector dummies + BETA60 + ROC60(trailing-60d momentum/drift)].
    (vs the residual audit which used sector+beta only; ROC60 is the new
     drift control that targets the BULL_CALM placebo root.)
  - 7-cut walk-forward. For each label variant {raw, neutralized}:
      * train XGB rank:pairwise on the variant label,
      * predict on test, measure cross-sectional IC vs RAW fwd_60d_excess,
        segmented OVERALL + per regime,
      * PLACEBO: shift label +60d (predict t+120), retrain, same per-regime IC.
  - "placebo-clean" BULL_CALM IC = real - placebo (real is only credible if
    the placebo is ~0). Success = neutralized BULL_CALM placebo-clean >= +0.02.

All trainings use the same XGB params the production trainer uses.
"""
from __future__ import annotations
import json, logging, sys
import numpy as np, pandas as pd, xgboost as xgb
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("neutral-wf")

PANEL = "data/alpha158_291_fund_regime_dataset.parquet"
SECTOR_CFG = ".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json"
RAW = "fwd_60d_excess"
NEU = "fwd_60d_excess_neutral"
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
    """Mean per-date cross-sectional rank-IC vs RAW return, overall + per regime."""
    df = pd.DataFrame({"p": pred, "y": y_raw, "date": dates, "reg": regime})
    out = {}
    for name, sub in [("ALL", df)] + [(r, df[df["reg"] == r]) for r in df["reg"].unique()]:
        ics = [spearmanr(g["p"], g["y"])[0] for _, g in sub.groupby("date") if len(g) >= 5]
        ics = [x for x in ics if not np.isnan(x)]
        out[name] = float(np.mean(ics)) if ics else np.nan
    return out


def residualize_label(df):
    """Per-date residual of RAW on [sector dummies + BETA60 + ROC60]. Robust."""
    def _one(g):
        y = g[RAW].to_numpy(float)
        secs = pd.get_dummies(g["sector"].astype("object"), dummy_na=True).to_numpy(float)
        z = []
        for c in ("BETA60", "ROC60"):
            v = g[c].to_numpy(float)
            med = np.nanmedian(v)
            v = np.where(np.isfinite(v), v, med)
            s = v.std()
            z.append((v - v.mean()) / s if s > 1e-12 else v * 0.0)
        X = np.column_stack([secs, np.array(z).T, np.ones(len(g))])
        keep = X.std(axis=0) > 0  # drop constant/all-zero sector dummies
        keep[-1] = True
        X = X[:, keep]
        ok = np.isfinite(y)
        if ok.sum() < 5:
            return pd.Series(np.nan, index=g.index)
        beta, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
        resid = y - X @ beta
        resid[~ok] = np.nan
        return pd.Series(resid, index=g.index)
    return df.groupby("date", group_keys=False).apply(_one)


def train_predict(tr, te, feat_cols, label, shift_days=0):
    """Train XGB on `label` (optionally +shift_days placebo), return test preds."""
    if shift_days:
        tr = tr.sort_values(["ticker", "date"]).copy()
        tr[label] = tr.groupby("ticker")[label].shift(-shift_days)
        tr = tr.dropna(subset=[label])
    tr = tr.dropna(subset=[label])
    if len(tr) < 1000 or len(te) < 100:
        return None
    Xtr = tr[feat_cols].fillna(0).to_numpy(np.float64)
    ytr = tr[label].clip(-5, 5).to_numpy(np.float64)
    Xte = te[feat_cols].fillna(0).to_numpy(np.float64)
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    Xtr = ((Xtr - mu) / sd).clip(-5, 5)
    Xte = ((Xte - mu) / sd).clip(-5, 5)
    order = np.argsort(tr["date"].to_numpy())
    Xs, ys = Xtr[order], ytr[order]
    _, gsz = np.unique(tr["date"].to_numpy()[order], return_counts=True)
    dtr = xgb.DMatrix(Xs, label=ys); dtr.set_group(gsz)
    booster = xgb.train(PARAMS, dtr, num_boost_round=N_ROUNDS)
    return booster.predict(xgb.DMatrix(Xte))


def main():
    log.info("loading regime panel + sector map ...")
    sectors = json.load(open(SECTOR_CFG))["sector_map"]
    df = pd.read_parquet(PANEL)
    df["date"] = pd.to_datetime(df["date"])
    df["sector"] = df["ticker"].map(sectors)
    df = df.dropna(subset=[RAW]).copy()
    # regime label per row = argmax of the 3 GMM probs
    probs = df[list(REGIME_COLS)].to_numpy(float)
    df["regime"] = np.array([REGIME_COLS[list(REGIME_COLS)[i]] for i in probs.argmax(1)])
    excl = {"ticker", "date", "split_label", "sector", "regime",
            "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess", NEU}
    excl |= set(REGIME_COLS)  # don't let the model see regime probs directly
    feat_cols = [c for c in df.columns if c not in excl]
    log.info("rows=%d dates=%d feats=%d regimes=%s", len(df), df["date"].nunique(),
             len(feat_cols), dict(df["regime"].value_counts()))

    log.info("building momentum/drift-neutralized label (sector+BETA60+ROC60) ...")
    df[NEU] = residualize_label(df)
    corr = df[[RAW, NEU]].corr().iloc[0, 1]
    log.info("  neutralized vs raw label corr = %.3f (lower = more drift removed)", corr)

    rows = []
    for ci, cut in enumerate(CUTS, 1):
        ts, tre, tes, tee = cut
        tr = df[(df["date"] >= ts) & (df["date"] <= tre)]
        te = df[(df["date"] >= tes) & (df["date"] <= tee)].dropna(subset=[RAW])
        if len(te) < 100:
            continue
        y_raw = te[RAW].to_numpy(float); dts = te["date"].to_numpy(); reg = te["regime"].to_numpy()
        for variant, label in [("raw", RAW), ("neutral", NEU)]:
            for kind, shift in [("real", 0), ("placebo", 60)]:
                p = train_predict(tr, te, feat_cols, label, shift_days=shift)
                if p is None:
                    continue
                ic = cs_ic_by_regime(p, y_raw, dts, reg)
                rows.append({"cut": ci, "variant": variant, "kind": kind, **ic})
                log.info("cut%d %-7s %-7s  ALL=%+.4f  BULL_CALM=%+.4f  BEAR=%+.4f  BULL_VOL=%+.4f",
                         ci, variant, kind, ic.get("ALL", np.nan), ic.get("BULL_CALM", np.nan),
                         ic.get("BEAR", np.nan), ic.get("BULL_VOLATILE", np.nan))

    R = pd.DataFrame(rows)
    def agg(variant, kind, reg):
        s = R[(R.variant == variant) & (R.kind == kind)][reg]
        return float(np.nanmean(s)) if len(s) else np.nan

    log.info("\n================ PER-REGIME WF SUMMARY (mean over cuts) ================")
    log.info("%-9s %-9s %8s %10s %8s %9s", "variant", "kind", "ALL", "BULL_CALM", "BEAR", "BULL_VOL")
    for variant in ("raw", "neutral"):
        for kind in ("real", "placebo"):
            log.info("%-9s %-9s %+8.4f %+10.4f %+8.4f %+9.4f", variant, kind,
                     agg(variant, kind, "ALL"), agg(variant, kind, "BULL_CALM"),
                     agg(variant, kind, "BEAR"), agg(variant, kind, "BULL_VOLATILE"))

    for variant in ("raw", "neutral"):
        real = agg(variant, "real", "BULL_CALM"); plac = agg(variant, "placebo", "BULL_CALM")
        clean = real - plac
        log.info("[%s] BULL_CALM  real=%+.4f  placebo=%+.4f  placebo-clean=%+.4f",
                 variant, real, plac, clean)
    raw_clean = agg("raw", "real", "BULL_CALM") - agg("raw", "placebo", "BULL_CALM")
    neu_clean = agg("neutral", "real", "BULL_CALM") - agg("neutral", "placebo", "BULL_CALM")
    log.info("\nDECISION (target: neutralized BULL_CALM placebo-clean IC >= +0.02):")
    log.info("  raw     placebo-clean BULL_CALM = %+.4f", raw_clean)
    log.info("  neutral placebo-clean BULL_CALM = %+.4f", neu_clean)
    if neu_clean >= 0.02:
        log.info("  => PASS: neutralization recovers a real BULL_CALM edge; promote to a gated retrain.")
    elif neu_clean > raw_clean + 0.005:
        log.info("  => PARTIAL: neutralization helps BULL_CALM but below +0.02; iterate the control.")
    else:
        log.info("  => NEGATIVE: drift control does not recover BULL_CALM; the regime ceiling is elsewhere.")
    R.to_csv("/tmp/neutralized_wf_gate.csv", index=False)
    log.info("per-cut detail -> /tmp/neutralized_wf_gate.csv")


if __name__ == "__main__":
    main()
