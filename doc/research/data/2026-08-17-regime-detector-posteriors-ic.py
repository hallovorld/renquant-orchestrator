#!/usr/bin/env python
"""Regime detector assessment — posteriors + phase-A IC (part 2 of 3).

Read-only derivation script for doc/research/2026-08-17-regime-detector-assessment.md.
Deterministic: no RNG; SPY input clamped to END_DATE. Run part 1 first (this
reads the label-series CSV it writes).

(a) per-day GMM posteriors + decision-source attribution for the serving
    detector; (b) discriminative-power test on the phase-A corpus (daily XS IC
    grouped by 4-way regime vs 2-way realized-vol split).

Inputs (read-only; paths overridable via env, hashes in the committed manifest):
  RQ_UMBRELLA     RenQuant umbrella root  (default ~/git/github/RenQuant)
  RQ_COMMON_SRC   renquant-common src dir (default ~/git/github/renquant-common/src)
  PHASE_A_DIR     phase-A extraction dir  (default <repo>/experiments/phase_a_data —
                  NOT committed; recorded by path+hash in the manifest)

Outputs (written next to this script):
  2026-08-17-regime-detector-posteriors-ic.json
  2026-08-17-regime-detector-posterior-series.csv

Run:
  ~/git/github/RenQuant/.venv/bin/python \
      doc/research/data/2026-08-17-regime-detector-posteriors-ic.py
"""
import glob
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, f_oneway

OUT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
PREFIX = "2026-08-17-regime-detector"
END_DATE = pd.Timestamp("2026-08-14")

RQ = Path(os.environ.get("RQ_UMBRELLA", str(Path.home() / "git/github/RenQuant")))
COMMON = Path(os.environ.get("RQ_COMMON_SRC",
                             str(Path.home() / "git/github/renquant-common/src")))
R104 = RQ / "backtesting" / "renquant_104"
sys.path.insert(0, str(R104))
sys.path.insert(0, str(COMMON))

from kernel.regime import gmm_predict, compute_hurst  # noqa: E402

spy = pd.read_parquet(RQ / "data/ohlcv/SPY/1d.parquet").sort_index()
spy.index = pd.to_datetime(spy.index)
spy = spy.loc[:END_DATE]
close = spy["close"].astype(float)
simple_rets = close.pct_change().dropna()

config = json.load(open(R104 / "strategy_config.json"))
rcfg = config["regime"]
gmm_art = json.load(open(R104 / "artifacts/prod/spy-gmm-regime.json"))

lbl = pd.read_csv(OUT / f"{PREFIX}-label-series.csv", index_col=0, parse_dates=[0])

# ── per-day posteriors + decision source ────────────────────────────────────
rows = []
for d in lbl.index:
    upto = simple_rets.loc[:d].values[-100:]
    spy_df_t = spy.loc[:d]
    probs = gmm_predict(gmm_art, np.asarray(upto, float), spy_df_t,
                        vol_window=int(rcfg.get("vol_realized_window", 20)))
    dom = max(probs, key=probs.get)
    # replicate resolution inputs
    hurst = compute_hurst(np.asarray(upto, float), window=int(rcfg.get("hurst_window", 63)))
    hurst_regime = ("MOMENTUM" if hurst > float(rcfg.get("hurst_trending_threshold", 0.65))
                    else "REVERSION" if hurst < float(rcfg.get("hurst_reversion_threshold", 0.52))
                    else "AMBIGUOUS")
    w20 = upto[-20:]
    v20 = float(np.std(w20, ddof=1) * math.sqrt(252))
    r20 = float(np.prod(1 + w20) - 1)
    w5 = upto[-5:]
    v5 = float(np.std(w5, ddof=1) * math.sqrt(252))
    r5 = float(np.prod(1 + w5) - 1)
    hard_bear = (v20 > 0.35 or r20 < -0.08 or v5 > 0.25 or r5 < -0.04)
    w60 = upto[-60:]
    v60 = float(np.std(w60, ddof=1) * math.sqrt(252))
    vol_cluster = (v60 > 0 and v5 > v60 * 1.5 and abs(r20) < 0.02)
    sc = float(spy_df_t["close"].iloc[-1])
    ma50 = float(spy_df_t["close"].rolling(50).mean().iloc[-1])
    ma200 = float(spy_df_t["close"].rolling(200).mean().iloc[-1])
    bear_trend = sc < ma50 and sc < ma200
    if hard_bear:
        src = "hard_bear"
    elif probs.get("BEAR", 0) > 0.5:
        src = "gmm_bear"
    elif hurst_regime == "MOMENTUM":
        src = ("hurst_momentum_spy_bearish" if bear_trend
               else "hurst_momentum_vol_cluster_choppy" if vol_cluster
               else "hurst_momentum_bull")
    elif hurst_regime == "REVERSION" or vol_cluster:
        src = "hurst_reversion" if hurst_regime == "REVERSION" else "vol_cluster_choppy"
    else:
        src = "dominant_gmm"
    rows.append({"date": d, "gmm_dom": dom, "gmm_max": max(probs.values()),
                 "gmm_bear_p": probs.get("BEAR", 0.0), "hurst": hurst,
                 "hurst_regime": hurst_regime, "src": src, "vol20": v20})
P = pd.DataFrame(rows).set_index("date")
P["final"] = lbl["S"]

post = {
    "gmm_dominant_occupancy_pct": (P["gmm_dom"].value_counts(normalize=True) * 100).round(1).to_dict(),
    "gmm_max_posterior": {"mean": round(float(P["gmm_max"].mean()), 3),
                          "p10": round(float(P["gmm_max"].quantile(0.1)), 3),
                          "median": round(float(P["gmm_max"].median()), 3),
                          "share_lt_0.6": round(float((P["gmm_max"] < 0.6).mean()), 3),
                          "share_lt_0.8": round(float((P["gmm_max"] < 0.8).mean()), 3)},
    "gmm_bear_gt_0.5_days": int((P["gmm_bear_p"] > 0.5).sum()),
    "decision_source_pct": (P["src"].value_counts(normalize=True) * 100).round(1).to_dict(),
    "final_eq_gmm_dominant_pct": round(float((P["final"] == P["gmm_dom"]).mean()) * 100, 1),
    "hurst_regime_pct": (P["hurst_regime"].value_counts(normalize=True) * 100).round(1).to_dict(),
    "hurst": {"mean": round(float(P["hurst"].mean()), 3),
              "share_gt_0.65": round(float((P["hurst"] > 0.65).mean()), 3),
              "share_lt_0.52": round(float((P["hurst"] < 0.52).mean()), 3)},
    "final_by_source": {s: P.loc[P["src"] == s, "final"].value_counts().to_dict()
                        for s in P["src"].unique()},
}
P.to_csv(OUT / f"{PREFIX}-posterior-series.csv")

# ── phase-A discriminative test (EXPLORATORY — local corpus, NOT committed) ──
# Codex review 2026-08-17: this section depends on a local, uncommitted extraction
# corpus (experiments/phase_a_data). On a clean checkout it is SKIPPED — the
# reproducible core above still writes its full output — and every conclusion
# derived from this section is demoted to exploratory in the memo (it is NOT part
# of the ranked decision case).
PA = Path(os.environ.get("PHASE_A_DIR", str(REPO / "experiments" / "phase_a_data")))
if not (PA / "forward_returns.csv").exists():
    out = {"posterior_and_attribution": post,
           "phase_a_ic": {"skipped": True,
                          "reason": "local phase-A corpus absent (uncommitted; "
                                    "exploratory-only section)"}}
    (OUT / f"{PREFIX}-posteriors-ic.json").write_text(
        json.dumps(out, indent=1, default=str))
    print(f"wrote {PREFIX}-posteriors-ic.json + {PREFIX}-posterior-series.csv "
          f"({len(P)} rows; phase-A SKIPPED — local corpus absent)")
    raise SystemExit(0)
fr = pd.read_csv(PA / "forward_returns.csv")
fr["date"] = pd.to_datetime(fr["date"])
ics = []
for f in sorted(glob.glob(str(PA / "xgb" / "*.json"))):
    d = pd.Timestamp(Path(f).stem)
    scores = json.load(open(f))["scores"]
    day = fr[fr["date"] == d]
    merged = day.set_index("ticker").join(pd.Series(scores, name="score"), how="inner").dropna()
    if len(merged) < 5 or merged["score"].std() < 1e-12:
        continue
    r, _ = spearmanr(merged["score"], merged["fwd_return"])
    ics.append({"date": d, "ic": r, "n": len(merged)})
IC = pd.DataFrame(ics).set_index("date")

# attach labels: serving S, research V, and 2-way vol split
IC["S"] = lbl["S"].reindex(IC.index)
IC["V"] = lbl["V"].reindex(IC.index)
IC["vol20"] = P["vol20"].reindex(IC.index)
med = IC["vol20"].median()
IC["vol2way"] = np.where(IC["vol20"] > med, "HIGH_VOL", "LOW_VOL")
# also a fixed-threshold split (0.18 = detector's own calm bar)
IC["vol2way_fixed"] = np.where(IC["vol20"] > 0.18, "HIGH_VOL", "LOW_VOL")


def group_report(col):
    g = IC.groupby(col)["ic"]
    rep = {k: {"mean_ic": round(float(v.mean()), 4), "n_days": int(v.size),
               "hit": round(float((v > 0).mean()), 3)} for k, v in g}
    groups = [v.values for _, v in g if v.size >= 5]
    if len(groups) >= 2:
        F, p = f_oneway(*groups)
        rep["_anova"] = {"F": round(float(F), 2), "p": round(float(p), 5)}
    # between-group variance explained (eta^2)
    overall = IC["ic"].mean()
    ss_between = sum(v.size * (v.mean() - overall) ** 2 for _, v in g)
    ss_total = ((IC["ic"] - overall) ** 2).sum()
    rep["_eta2"] = round(float(ss_between / ss_total), 4)
    return rep

ic_out = {
    "corpus": "phase_a_data xgb scores vs fwd_60d_excess, 2025-03-13..2026-02-10",
    "n_days": int(len(IC)),
    "overall": {"mean_ic": round(float(IC["ic"].mean()), 4)},
    "by_serving_regime": group_report("S"),
    "by_research_regime_v": group_report("V"),
    "by_vol_2way_median": group_report("vol2way"),
    "by_vol_2way_fixed018": group_report("vol2way_fixed"),
    # per-day IC rows so part 3 can split BEAR days by drawdown windows
    "ic_daily": [{"date": str(d.date()), "ic": round(float(r["ic"]), 4),
                  "n": int(r["n"]), "S": r["S"]} for d, r in IC.iterrows()],
}

out = {"posterior_and_attribution": post, "phase_a_ic": ic_out}
(OUT / f"{PREFIX}-posteriors-ic.json").write_text(json.dumps(out, indent=1, default=str))
print(f"wrote {PREFIX}-posteriors-ic.json + {PREFIX}-posterior-series.csv "
      f"({len(P)} rows; phase-A {len(IC)} days)")
