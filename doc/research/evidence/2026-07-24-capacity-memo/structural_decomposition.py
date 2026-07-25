"""STRUCTURAL DECOMPOSITION of the book's P&L generation chain.

Theory frame (Grinold 1989; Daniel-Grinblatt-Titman-Wermers 1997):

    realized alpha = [ skill + characteristic premia ] x dispersion x capture
                      ------ TEST 1 (DGTW) ------        TEST 2       TEST 3

TEST 1 — DGTW characteristic-matched benchmark. Each stock's benchmark is
  the mean fwd60 of its (vol x momentum x beta) cell that date, self-excluded.
  Pick-minus-cell = SKILL. Raw-minus-DGTW = the characteristic tilt.
  If DGTW-adjusted spread ~ 0, the model selects CHARACTERISTICS, not stocks.

TEST 2 — dispersion conditioning. Grinold: expected spread = IC x sigma_CS.
  Regress per-date clean IC and per-date top-10 spread on cross-sectional
  dispersion of fwd60. If the 'episodes' are just high-dispersion states,
  the model's usefulness is PREDICTABLE from a live observable.

TEST 3 — exit-stack counterfactual, measured not inferred. Apply the
  PRODUCTION stop parameters (strategy_config.json, BULL_CALM regime — 72%
  of days) to the real daily price paths of the actual top-10 picks.
  Buy-and-hold-60d vs exit-stack capture. Excluded: 3-strike model
  protection + panel exits (need model re-runs) => measured amputation is a
  LOWER bound.

Inputs: cached real/placebo scores (this session), the panel's own STD60 /
ROC60 / BETA60 columns, OHLCV closes, production strategy_config.json.
"""
import warnings, json, sys
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(line_buffering=True)
from pathlib import Path
import numpy as np
import pandas as pd

RQ = Path("/Users/renhao/git/github/RenQuant")
S = Path("/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad")
TOP_N = 10

R = pd.read_parquet(S / "scores_real.parquet")
P = pd.read_parquet(S / "scores_placebo.parquet")
pan = pd.read_parquet(RQ / "data/alpha158_291_fundamental_dataset.parquet",
                      columns=["ticker", "date", "STD60", "ROC60", "BETA60"])
pan["date"] = pd.to_datetime(pan["date"])
R = R.merge(pan, on=["ticker", "date"], how="left")
print(f"scored rows {len(R):,} · char coverage {R['STD60'].notna().mean():.1%}", flush=True)

# ════════════════════════ TEST 1 — DGTW ════════════════════════════
print("\n" + "=" * 76, flush=True)
print("TEST 1 — DGTW (1997): skill vs characteristic tilt", flush=True)
print("=" * 76, flush=True)

def dgtw_cells(df):
    d = df.dropna(subset=["STD60", "ROC60", "BETA60", "f60"]).copy()
    for c, q in (("STD60", 3), ("ROC60", 3), ("BETA60", 3)):
        d[c + "_t"] = d.groupby("date")[c].transform(
            lambda s: pd.qcut(s.rank(method="first"), q, labels=False))
    d["cell"] = (d["STD60_t"].astype(int) * 9 + d["ROC60_t"].astype(int) * 3
                 + d["BETA60_t"].astype(int))
    g = d.groupby(["date", "cell"])["f60"]
    d["cell_sum"] = g.transform("sum")
    d["cell_n"] = g.transform("count")
    # self-excluded cell mean
    d["bench"] = (d["cell_sum"] - d["f60"]) / (d["cell_n"] - 1).replace(0, np.nan)
    d["dgtw"] = d["f60"] - d["bench"]
    return d

D = dgtw_cells(R)
def daily_top_spread(df, col, wins=None):
    def one(g):
        if len(g) < 30:
            return np.nan
        v = g[col] if wins is None else g[col].clip(-wins, wins)
        return v.loc[g.nlargest(TOP_N, "score").index].mean() - v.mean()
    return df.groupby("date").apply(one).dropna()

raw_sp = daily_top_spread(D, "f60")
dgtw_sp = daily_top_spread(D, "dgtw")
raw_w = daily_top_spread(D, "f60", wins=0.5)
dgtw_w = daily_top_spread(D, "dgtw", wins=0.5)

def block_t(x):
    x = x.sort_index()
    b = np.array([x.iloc[i:i + 60].mean() for i in range(0, len(x) - 59, 60)])
    return b.mean(), b.mean() / (b.std(ddof=1) / np.sqrt(len(b))), len(b)

for name, sp in (("RAW top-10 spread", raw_sp), ("DGTW-ADJUSTED (skill)", dgtw_sp),
                 ("RAW winsorized ±50%", raw_w), ("DGTW winsorized ±50%", dgtw_w)):
    m, t, n = block_t(sp)
    print(f"  {name:24} {m:+.4f}/60d   block-t={t:+.2f} (n={n})", flush=True)
tilt = raw_sp.mean() - dgtw_sp.mean()
print(f"\n  characteristic tilt = raw − DGTW = {tilt:+.4f}/60d "
      f"({100 * tilt / raw_sp.mean():.0f}% of the raw spread)", flush=True)
# what characteristics do the picks tilt to?
picks = D.loc[D.groupby("date")["score"].rank(ascending=False) <= TOP_N]
print("  top-10 mean percentile of: vol {:.0f} · momentum {:.0f} · beta {:.0f}".format(
    *[100 * picks.groupby("date")[c].rank(pct=True).groupby(picks["date"]).mean().mean()
      if False else 100 * D.groupby("date")[c].rank(pct=True).loc[picks.index].mean()
      for c in ("STD60", "ROC60", "BETA60")]), flush=True)

# ════════════════════════ TEST 2 — dispersion ═══════════════════════
print("\n" + "=" * 76, flush=True)
print("TEST 2 — Grinold: are the 'episodes' just cross-sectional dispersion?", flush=True)
print("=" * 76, flush=True)
disp = R.groupby("date")["f60"].std().rename("disp")
icR = R.groupby("date").apply(lambda g: g["score"].corr(g["f60"], method="spearman")
                              if len(g) >= 5 else np.nan).dropna()
icP = P.groupby("date").apply(lambda g: g["score"].corr(g["f60"], method="spearman")
                              if len(g) >= 5 else np.nan).dropna()
common = icR.index.intersection(icP.index)
clean_ic = (icR[common] - icP[common]).rename("clean_ic")
J = pd.concat([clean_ic, disp, raw_sp.rename("spread")], axis=1).dropna()
J["dt"] = pd.qcut(J["disp"], 3, labels=["LOW", "MID", "HIGH"])
print(f"  corr(clean IC, dispersion)        : {J['clean_ic'].corr(J['disp']):+.2f}", flush=True)
print(f"  corr(top-10 spread, dispersion)   : {J['spread'].corr(J['disp']):+.2f}", flush=True)
print("\n  by dispersion tercile:", flush=True)
for t_, g in J.groupby("dt"):
    print(f"    {t_:5}  clean IC {g['clean_ic'].mean():+.4f}   "
          f"spread {g['spread'].mean():+.4f}/60d   n={len(g)}", flush=True)
yr = J.groupby(J.index.year)[["clean_ic", "disp"]].mean()
print(f"\n  corr(YEARLY clean IC, YEARLY dispersion): "
      f"{yr['clean_ic'].corr(yr['disp']):+.2f}", flush=True)
cur = J["disp"].iloc[-250:].mean()
pct = 100 * (J["disp"] < cur).mean()
print(f"  trailing-250d dispersion now at the {pct:.0f}th percentile of history", flush=True)

# ════════════════════════ TEST 3 — exit stack ═══════════════════════
print("\n" + "=" * 76, flush=True)
print("TEST 3 — exit-stack counterfactual on real price paths (production params)", flush=True)
print("=" * 76, flush=True)
cfg = json.loads((RQ / "backtesting/renquant_104/strategy_config.json").read_text())
rp = cfg["regime_params"]["BULL_CALM"]
STOP = float(rp["stop_loss_pct"])
TRIG = float(rp["trailing_stop_trigger_pct"])
TRAIL = float(rp["trailing_stop_trail_pct"])
print(f"  BULL_CALM params from strategy_config.json: stop_loss {STOP:.0%} · "
      f"trailing trigger {TRIG:.0%} / trail {TRAIL:.0%}", flush=True)
print("  (excluded: 3-strike model exits, panel exits, single-day-loss ⇒ the", flush=True)
print("   measured amputation is a LOWER bound on the real stack's)", flush=True)

closes = {}
for t in R["ticker"].unique():
    fp = RQ / "data/ohlcv" / t / "1d.parquet"
    if fp.exists():
        df = pd.read_parquet(fp)
        df.index = pd.to_datetime(df.index if "date" not in df.columns else df["date"])
        closes[t] = (df["close"] if "close" in df.columns else df["Close"]).sort_index()
print(f"  price paths loaded: {len(closes)}", flush=True)

all_dates = sorted(R["date"].unique())
rebals = all_dates[::20]
rows = []
for d in rebals:
    g = R[R["date"] == d]
    if len(g) < 30:
        continue
    for t in g.nlargest(TOP_N, "score")["ticker"]:
        px = closes.get(t)
        if px is None or d not in px.index:
            continue
        i0 = px.index.get_loc(d)
        path = px.iloc[i0:i0 + 61]
        if len(path) < 10:
            continue
        entry = path.iloc[0]
        bh = path.iloc[-1] / entry - 1
        peak, exit_ret, reason = entry, None, "held_60d"
        for j in range(1, len(path)):
            p_ = path.iloc[j]
            peak = max(peak, p_)
            if p_ <= entry * (1 - STOP):
                exit_ret, reason = p_ / entry - 1, "stop_loss"
                break
            if peak >= entry * (1 + TRIG) and p_ <= peak * (1 - TRAIL):
                exit_ret, reason = p_ / entry - 1, "trailing"
                break
        if exit_ret is None:
            exit_ret = bh
        rows.append({"date": d, "ticker": t, "bh60": bh, "stack": exit_ret,
                     "reason": reason, "big_winner": bh >= 0.5})
E = pd.DataFrame(rows)
print(f"\n  simulated positions: {len(E):,} over {E['date'].nunique()} rebalances", flush=True)
print(f"  buy-and-hold 60d mean return : {E['bh60'].mean():+.4f}", flush=True)
print(f"  exit-stack mean return       : {E['stack'].mean():+.4f}", flush=True)
amp = E["bh60"].mean() - E["stack"].mean()
print(f"  AMPUTATION                   : {amp:+.4f}/position/60d "
      f"= {amp * 4.2:+.2%}/yr on the sleeve", flush=True)
print(f"\n  exit reasons: {dict(E['reason'].value_counts())}", flush=True)
bw = E[E["big_winner"]]
print(f"\n  BIG WINNERS (bh60 ≥ +50%): {len(bw)} positions", flush=True)
print(f"    stopped out before the run completed: "
      f"{(bw['reason'] != 'held_60d').mean():.0%}", flush=True)
print(f"    their bh60 mean {bw['bh60'].mean():+.2f} vs stack-captured "
      f"{bw['stack'].mean():+.2f}  → tail capture ratio "
      f"{bw['stack'].mean() / bw['bh60'].mean():.0%}", flush=True)
lose = E[E["bh60"] <= -0.15]
print(f"  BIG LOSERS (bh60 ≤ −15%): {len(lose)} — stack saved "
      f"{(lose['bh60'].mean() - lose['stack'].mean()):+.4f}/position", flush=True)

json.dump({"dgtw": {"raw": float(raw_sp.mean()), "dgtw": float(dgtw_sp.mean()),
                    "raw_w50": float(raw_w.mean()), "dgtw_w50": float(dgtw_w.mean())},
           "dispersion_corr": float(J["clean_ic"].corr(J["disp"])),
           "amputation_per_pos": float(amp)},
          open(S / "structural_decomposition_result.json", "w"), indent=2)
print("\nSaved structural_decomposition_result.json", flush=True)
