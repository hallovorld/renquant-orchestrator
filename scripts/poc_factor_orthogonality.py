#!/usr/bin/env python3
"""POC-D: measure the ORTHOGONALITY of candidate signal families on our
panel — the discount on the "3 orthogonal 0.02s ~= 0.035" stacking claim
(roadmap #230 §2.4 path 2).

Theory: for k standardized signals with equal IC and equal pairwise score
correlation rho, the combined signal's IC is
    IC_comb = k*IC / sqrt(k + k*(k-1)*rho)
(rho=0 recovers sqrt(k)*IC; rho=1 collapses to IC). The stacking gain is
therefore bounded by the measured rho between candidate factor scores.

Method: from daily bars of the 142 panel tickers, build three price-family
factor score vectors at month-ends over the last ~3y:
    mom_12_1   = ret(252d) excluding last 21d
    reversal20 = -ret(21d)
    lowvol60   = -realized_vol(60d)
Cross-sectional Spearman correlation between each pair, averaged over dates.
(These proxy the price side; revisions/quality live on other data and their
rho is measured once the PIT store matures — stated limitation.)

Reproduce:
  cd /Users/renhao/git/github/RenQuant && .venv/bin/python \
    <orchestrator>/scripts/poc_factor_orthogonality.py
Inputs (read-only): data/ohlcv/<T>/1d.parquet; panel ticker list.
Output: doc/research/evidence/2026-07-02-roadmap-pocs/poc_d_factor_orthogonality.json
"""
import json
import os

import numpy as np
import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
LOOKBACK_D = 756


def main() -> None:
    tickers = pd.read_parquet(
        os.path.join(RQ, "data/transformer_v4_wl200_clean.parquet"),
        columns=["ticker"])["ticker"].unique().tolist()
    closes = {}
    for t in tickers:
        p = os.path.join(RQ, "data/ohlcv", t, "1d.parquet")
        if not os.path.exists(p):
            continue
        df = pd.read_parquet(p)
        df.columns = [c.lower() for c in df.columns]
        if "date" in df.columns:
            df = df.set_index("date")
        closes[t] = df["close"].sort_index()
    px = pd.DataFrame(closes).iloc[-LOOKBACK_D - 300:]
    mom = px.shift(21) / px.shift(252) - 1
    rev = -(px / px.shift(21) - 1)
    lv = -(np.log(px).diff().rolling(60).std() * np.sqrt(252))
    month_ends = px.index[px.index.to_series().dt.month.diff().fillna(1) != 0]
    month_ends = month_ends[-36:]
    pairs = {"mom~rev": [], "mom~lowvol": [], "rev~lowvol": []}
    for d in month_ends:
        if d not in mom.index:
            continue
        f = pd.DataFrame({"mom": mom.loc[d], "rev": rev.loc[d],
                          "lv": lv.loc[d]}).dropna()
        if len(f) < 60:
            continue
        c = f.rank().corr()
        pairs["mom~rev"].append(c.loc["mom", "rev"])
        pairs["mom~lowvol"].append(c.loc["mom", "lv"])
        pairs["rev~lowvol"].append(c.loc["rev", "lv"])
    rho = {k: round(float(np.mean(v)), 3) for k, v in pairs.items() if v}
    rho_abs = round(float(np.mean([abs(x) for v in pairs.values() for x in v])), 3)

    def ic_comb(k, ic, r):
        return k * ic / np.sqrt(k + k * (k - 1) * r)

    out = {
        "n_month_end_dates": int(min(len(v) for v in pairs.values())),
        "avg_pairwise_spearman": rho,
        "avg_abs_rho": rho_abs,
        "stacking_math": {
            "ideal_3x0.02_rho0": round(ic_comb(3, 0.02, 0.0), 4),
            "at_measured_avg_abs_rho": round(ic_comb(3, 0.02, rho_abs), 4),
            "at_rho_0.3": round(ic_comb(3, 0.02, 0.3), 4),
            "formula": "IC_comb = k*IC / sqrt(k + k*(k-1)*rho)",
        },
        "limitation": ("price-family trio only; revisions/quality rho is "
                       "measurable only after the PIT store matures (N2) — "
                       "cross-data-family rho is typically LOWER, so this "
                       "bounds the discount from the pessimistic side for "
                       "the price family specifically"),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_d_factor_orthogonality.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
