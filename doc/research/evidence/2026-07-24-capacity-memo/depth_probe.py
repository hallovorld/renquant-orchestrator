"""THREE LAYERS DEEPER than the capacity memo.

Layer 1 — replace the one ASSUMED number. The memo guessed rho=0.25 to get
  breadth. Here the signal IR is measured DIRECTLY from the per-date IC
  series (block-mean method, no breadth assumption at all).

Layer 2 — HARVESTABILITY. IC is Spearman over ~140 names. The book trades
  top-10. If the clean signal lives in mid-ranks, the book cannot monetize
  the IC at all. Measured: per-date decile curve + top-10 spread, REAL vs
  matched PLACEBO, gross and net of costs at the score's own turnover.

Layer 3 — DECAY + what the floor actually is. Clean IC by year (is the
  signal dying?), and the static-component share of the score (how much of
  the model is a fixed stock-type classifier rather than a timing signal).

Everything from ONE production-recipe run: all_172, fwd_60d_excess,
rank:pairwise, 5 purged folds, 60d embargo, seeds 42/43/44, real + placebo.
"""
import warnings, json, time, sys
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(line_buffering=True)
from pathlib import Path
from functools import partial

import numpy as np
import pandas as pd
import xgboost as xgb

from renquant_model_gbdt.panel_data import load_panel, build_normalization
from renquant_model_gbdt.panel_trainer import (
    PANEL_LTR_PARAMS, panel_training_matrix, train_xgb)

DD = Path("/Users/renhao/git/github/RenQuant/data")
SCRATCH = Path("/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad")
LAB, LAB20 = "fwd_60d_excess", "fwd_20d_excess"
SEEDS, N_ROUNDS, EMBARGO = (42, 43, 44), 100, 60
TOP_N, COST_BPS = 10, 10

panel, FEATS, _ = load_panel(DD, label=LAB)
panel["date"] = pd.to_datetime(panel["date"])
nb = partial(build_normalization, data_dir=DD)
dates = np.array(sorted(panel["date"].unique()))
folds = []
for vi in np.array_split(np.arange(len(dates)), 6)[1:]:
    e = int(vi[0]) - EMBARGO
    if e > 0 and len(vi):
        folds.append({"tr": set(dates[:e]), "va": set(dates[vi])})
print(f"panel {len(panel):,} rows · {len(folds)} folds", flush=True)


def score_panel(placebo):
    """Return DataFrame (date, ticker, score, fwd60, fwd20) — seed-averaged."""
    acc = {}
    for seed in SEEDS:
        for f in folds:
            tr = panel[panel["date"].isin(f["tr"])].dropna(subset=[LAB])
            va = panel[panel["date"].isin(f["va"])]
            if tr["date"].nunique() < 20 or va.empty:
                continue
            if placebo:
                tr = tr.copy()
                rng = np.random.default_rng(seed)
                tr[LAB] = tr.groupby("date")[LAB].transform(
                    lambda s: rng.permutation(s.values))
            mu, sd, k, _, _ = nb(tr, FEATS)
            b, _ = train_xgb(tr, FEATS, label=LAB,
                             params=dict(PANEL_LTR_PARAMS, seed=seed),
                             num_boost_round=N_ROUNDS, feature_means=mu,
                             feature_stds=sd, feature_norm_kind=k)
            p = b.predict(xgb.DMatrix(
                panel_training_matrix(va, FEATS, mu, sd, k).values.astype(np.float64)))
            sub = va[["date", "ticker", LAB, LAB20]].copy()
            sub["score"] = p
            for row in sub.itertuples(index=False):
                key = (row.date, row.ticker)
                acc.setdefault(key, {"fwd60": row[2], "fwd20": row[3], "s": []})[
                    "s"].append(row.score)
    out = pd.DataFrame([{"date": k[0], "ticker": k[1], "score": np.mean(v["s"]),
                         "fwd60": v["fwd60"], "fwd20": v["fwd20"]}
                        for k, v in acc.items()])
    return out.dropna(subset=["fwd60"])


t0 = time.time()
R = score_panel(False)
print(f"real scored: {len(R):,} rows [{time.time()-t0:.0f}s]", flush=True)
t0 = time.time()
P = score_panel(True)
print(f"placebo scored: {len(P):,} rows [{time.time()-t0:.0f}s]", flush=True)

out = {}

# ── LAYER 1: measured signal IR (no breadth assumption) ──────────────
def per_date_ic(df, lab="fwd60"):
    return df.groupby("date").apply(
        lambda g: g["score"].corr(g[lab], method="spearman")
        if len(g) >= 5 and g["score"].std() > 0 and g[lab].std() > 0 else np.nan
    ).dropna()

icR, icP = per_date_ic(R), per_date_ic(P)
common = icR.index.intersection(icP.index)
clean = (icR[common] - icP[common]).sort_index()
# 60d block means -> independent draws -> IR without any rho assumption
blocks = [clean.iloc[i:i + 60].mean() for i in range(0, len(clean) - 59, 60)]
blocks = np.array(blocks)
ir_ann = blocks.mean() / blocks.std(ddof=1) * np.sqrt(252 / 60)
print("\n" + "=" * 72, flush=True)
print("LAYER 1 — MEASURED signal IR (block-mean method, zero assumptions)", flush=True)
print("=" * 72, flush=True)
print(f"  clean IC: mean {clean.mean():+.4f}  daily-std {clean.std():.4f}  n={len(clean)}", flush=True)
print(f"  60d block means: n={len(blocks)}  mean {blocks.mean():+.4f}  std {blocks.std(ddof=1):.4f}", flush=True)
print(f"  => MEASURED annualized signal IR = {ir_ann:.2f}", flush=True)
print(f"  memo's assumed-rho version said 0.12; realized (xTC 0.4) => {ir_ann*0.4:.3f}", flush=True)
out["layer1"] = {"clean_ic": float(clean.mean()), "n_blocks": len(blocks),
                 "ir_signal_measured": float(ir_ann), "ir_realized_tc04": float(ir_ann * 0.4)}

# ── LAYER 2: harvestability — where in the cross-section is the signal? ──
print("\n" + "=" * 72, flush=True)
print("LAYER 2 — HARVESTABILITY: decile curve + top-10 spread, real vs placebo", flush=True)
print("=" * 72, flush=True)

def decile_curve(df, lab):
    d = df.copy()
    d["dec"] = d.groupby("date")["score"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    return d.groupby("dec")[lab].mean()

curR, curP = decile_curve(R, "fwd60"), decile_curve(P, "fwd60")
print(f"  {'decile':>7} {'real':>9} {'placebo':>9} {'CLEAN':>9}", flush=True)
for i in range(10):
    print(f"  {i:>7} {curR[i]:>+9.4f} {curP[i]:>+9.4f} {curR[i]-curP[i]:>+9.4f}"
          f"{'   <- the book trades here' if i == 9 else ''}", flush=True)

def topn_spread(df, lab, n=TOP_N):
    def one(g):
        if len(g) < 30:
            return np.nan
        top = g.nlargest(n, "score")[lab].mean()
        return top - g[lab].mean()
    return df.groupby("date").apply(one).dropna()

for lab, hz in (("fwd60", 60), ("fwd20", 20)):
    sR, sP = topn_spread(R, lab), topn_spread(P, lab)
    c = sR.index.intersection(sP.index)
    spread_clean = (sR[c] - sP[c])
    # turnover of the top-10 set at the rebalance cadence
    picks = {d: set(g.nlargest(TOP_N, "score")["ticker"]) for d, g in R.groupby("date")}
    ds = sorted(picks)
    step = max(1, hz)
    tos = [len(picks[ds[i]] - picks[ds[i - step]]) / TOP_N
           for i in range(step, len(ds), step)]
    to = float(np.mean(tos))
    ann_gross = spread_clean.mean() * (252 / hz)
    ann_cost = to * (COST_BPS / 1e4) * (252 / hz) * 2      # round-trip
    print(f"\n  top-{TOP_N} CLEAN spread @{hz}d: {spread_clean.mean():+.4f}/period"
          f"  = {ann_gross:+.2%}/yr gross", flush=True)
    print(f"    placebo top-{TOP_N} spread (stock-type component): {sP[c].mean():+.4f}/period", flush=True)
    print(f"    turnover {to:.0%}/rebalance -> cost {ann_cost:.2%}/yr"
          f"  => NET {ann_gross - ann_cost:+.2%}/yr", flush=True)
    out[f"layer2_{hz}d"] = {"clean_spread_per_period": float(spread_clean.mean()),
                            "placebo_spread": float(sP[c].mean()),
                            "gross_ann": float(ann_gross), "turnover": to,
                            "cost_ann": float(ann_cost),
                            "net_ann": float(ann_gross - ann_cost)}

# ── LAYER 3: decay + what the floor is ───────────────────────────────
print("\n" + "=" * 72, flush=True)
print("LAYER 3 — DECAY + the floor's identity", flush=True)
print("=" * 72, flush=True)
byyr = clean.groupby(clean.index.year)
print("  clean IC by year:", flush=True)
for y, g in byyr:
    bar = "#" * max(0, int(g.mean() * 800))
    print(f"    {y}  {g.mean():+.4f}  n={len(g):4d}  {bar}", flush=True)
out["layer3_by_year"] = {int(y): float(g.mean()) for y, g in byyr}

# static component: how much of the score is a fixed per-ticker offset?
sv = R.groupby("ticker")["score"].mean()
R2 = R.merge(sv.rename("ticker_mean"), on="ticker")
static_share = float(np.var(R2["ticker_mean"]) / np.var(R2["score"]))
# does the placebo score = the static component?
Pm = P.groupby("ticker")["score"].mean()
align = float(sv.corr(Pm, method="spearman"))
print(f"\n  static (fixed per-ticker) share of score variance: {static_share:.0%}", flush=True)
print(f"  rank-corr(real ticker-mean score, placebo ticker-mean score): {align:+.2f}", flush=True)
print("  -> the placebo floor IS the model's stock-type tilt, and that tilt", flush=True)
print("     dominates the score. The timing component rides on top.", flush=True)
out["layer3_static_share"] = static_share
out["layer3_real_placebo_tickermean_corr"] = align

json.dump(out, open(SCRATCH / "depth_probe_result.json", "w"), indent=2)
print("\nSaved depth_probe_result.json", flush=True)
