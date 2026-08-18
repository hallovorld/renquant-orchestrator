"""Build the per-date outcome + state-variable table for the tail-switch study.

Implements DEFINITIONS.md exactly. Outputs:
  series_clf.csv    (primary corpus)
  series_phasea.csv (secondary corpus)
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

SCRATCH = Path(__file__).resolve().parent
OHLCV = Path("/Users/renhao/git/github/RenQuant/data/ohlcv")
CLF = Path("/Users/renhao/git/github/renquant-model/doc/research/data/"
           "2026-08-01-clf-wf-lineage-bundle/clf_wf_scores.parquet")
PHASEA = Path("/Users/renhao/git/github/renquant-orchestrator/experiments/phase_a_data")
REGIME = Path("/Users/renhao/git/github/renquant-orchestrator/doc/research/data/"
              "2026-08-10-bear-exit-regime-days.csv")

H = 60  # horizon, trading days
TOP_N = 10


def load_close(ticker):
    p = OHLCV / ticker / "1d.parquet"
    if not p.exists():
        return None
    try:
        s = pd.read_parquet(p, columns=["close"])["close"]
    except Exception:
        return None
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def build(scores, corpus_name):
    """scores: DataFrame[date, ticker, score, zlabel, (cal optional)]"""
    scores = scores.dropna(subset=["score", "zlabel"])
    counts = scores.groupby("date")["ticker"].nunique()
    good_dates = counts[counts >= 100].index.sort_values()
    scores = scores[scores["date"].isin(good_dates)]
    tickers = sorted(scores["ticker"].unique())

    closes, missing = {}, []
    for t in tickers:
        s = load_close(t)
        if s is None or len(s) < 60:
            missing.append(t)
        else:
            closes[t] = s
    close_df = pd.DataFrame(closes)  # union calendar
    spy = load_close("SPY")
    close_df = close_df.reindex(close_df.index.union(spy.index)).sort_index()
    spy = spy.reindex(close_df.index)
    print(f"[{corpus_name}] tickers {len(tickers)}, OHLCV missing {len(missing)}: "
          f"{missing[:10]}{'...' if len(missing) > 10 else ''}")

    rets = close_df.pct_change(fill_method=None)
    spy_ret = spy.pct_change(fill_method=None)
    trading_days = close_df.index  # OHLCV calendar

    # forward 60-trading-day raw return (per the OHLCV calendar), excess vs SPY
    fwd = close_df.shift(-H) / close_df - 1.0
    spy_fwd = spy.shift(-H) / spy - 1.0
    fwd_ex = fwd.sub(spy_fwd, axis=0)

    # ex-ante states on the corpus universe (per-date membership)
    sma50 = close_df.rolling(50, min_periods=50).mean()
    above50 = (close_df > sma50)
    have_sma = sma50.notna() & close_df.notna()
    xsec_std_1d = rets.std(axis=1)  # over ALL loaded tickers; membership refined below

    rows = []
    per_date = dict(list(scores.groupby("date")))
    dates = sorted(per_date)
    yz_hist = {}  # date -> Y_z for SKILL60
    for d in dates:
        g = per_date[d].sort_values("score", ascending=False)
        univ = [t for t in g["ticker"] if t in close_df.columns]
        n = len(g)
        top10 = g.head(TOP_N)["ticker"].tolist()
        ndec = int(round(n / 10.0))
        topdec = g.head(ndec)["ticker"].tolist()

        y_z10 = g.head(TOP_N)["zlabel"].mean()
        y_zdec = g.head(ndec)["zlabel"].mean()
        yz_hist[d] = y_z10

        if d in fwd_ex.index:
            fe = fwd_ex.loc[d]
            uvals = fe[univ].dropna()
            t10 = fe[[t for t in top10 if t in fe.index]].dropna()
            tdec = fe[[t for t in topdec if t in fe.index]].dropna()
            y_r10 = t10.mean() - uvals.mean() if len(t10) >= 7 and len(uvals) >= 50 else np.nan
            y_rdec = tdec.mean() - uvals.mean() if len(tdec) >= 7 and len(uvals) >= 50 else np.nan
            n_univ_r = len(uvals)
        else:
            y_r10 = y_rdec = np.nan
            n_univ_r = 0

        # states
        if d in trading_days:
            di = trading_days.get_loc(d)
            win = trading_days[max(0, di - 19): di + 1]
            # DISP20 on the corpus universe members only
            disp20 = rets.loc[win, univ].std(axis=1).mean() if len(win) == 20 else np.nan
            spyvol20 = (spy_ret.loc[win].std() * np.sqrt(252)) if len(win) == 20 else np.nan
            ok = have_sma.loc[d, univ]
            breadth = above50.loc[d, univ][ok].mean() if ok.sum() >= 50 else np.nan
        else:
            disp20 = spyvol20 = breadth = np.nan

        scoredisp = g["scoredisp_col"].std() if "scoredisp_col" in g else np.nan

        rows.append(dict(date=d, n_names=n, n_univ_r=n_univ_r,
                         y_z10=y_z10, y_zdec=y_zdec, y_r10=y_r10, y_rdec=y_rdec,
                         disp20=disp20, breadth=breadth, spyvol20=spyvol20,
                         scoredisp=scoredisp))

    out = pd.DataFrame(rows).set_index("date").sort_index()

    # SKILL60: mean of Y_z over the 60 most recent dates s <= t-60 (corpus-date index)
    dser = pd.Series(range(len(out)), index=out.index)
    yz = out["y_z10"]
    skill = []
    for i, d in enumerate(out.index):
        j = i - H  # corpus-date offset proxy for t-60 trading days
        if j >= 0:
            windowvals = yz.iloc[max(0, j - 59): j + 1]
            skill.append(windowvals.mean() if len(windowvals) >= 30 else np.nan)
        else:
            skill.append(np.nan)
    out["skill60"] = skill

    reg = pd.read_csv(REGIME, parse_dates=["date"]).set_index("date")["prod_gmm_label"]
    out["regime"] = reg.reindex(out.index)
    return out


# ---------- primary: clf WF ----------
clf = pd.read_parquet(CLF)
clf = clf.rename(columns={"raw": "score", "fwd_60d_excess": "zlabel"})
clf["scoredisp_col"] = clf["cal"]
series_clf = build(clf[["date", "ticker", "score", "zlabel", "scoredisp_col"]], "clf")
series_clf.to_csv(SCRATCH / "series_clf.csv")
print(series_clf[["y_z10", "y_r10", "disp20", "breadth", "spyvol20",
                  "scoredisp", "skill60"]].describe())
print("regime counts:", series_clf["regime"].value_counts(dropna=False).to_dict())

# ---------- secondary: phase-A xgb ----------
fr = pd.read_csv(PHASEA / "forward_returns.csv", parse_dates=["date"])
recs = []
for f in sorted((PHASEA / "xgb").glob("*.json")):
    d = pd.Timestamp(f.stem)
    sc = json.loads(f.read_text())["scores"]
    for t, v in sc.items():
        recs.append((d, t, v))
xs = pd.DataFrame(recs, columns=["date", "ticker", "score"])
ph = xs.merge(fr.rename(columns={"fwd_return": "zlabel"}), on=["date", "ticker"], how="inner")
ph["scoredisp_col"] = ph["score"]
series_ph = build(ph[["date", "ticker", "score", "zlabel", "scoredisp_col"]], "phaseA")
series_ph.to_csv(SCRATCH / "series_phasea.csv")
print(series_ph[["y_z10", "y_r10"]].describe())
print("regime counts:", series_ph["regime"].value_counts(dropna=False).to_dict())
