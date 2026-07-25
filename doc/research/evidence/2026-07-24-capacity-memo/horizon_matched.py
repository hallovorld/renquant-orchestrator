"""Horizon comparison with the data-recency confound REMOVED.

In the first pass the embargo matched each arm's own label (5/20/60), so the
5d arm trained on 55 more days per fold than the 60d arm. That is a genuine
production advantage of a short label, but it confounds the question "which
TARGET is better". Here every arm uses embargo = 60 so all three see the
IDENTICAL training rows and identical validation dates; the only difference
is what they are asked to predict.

Reports paired block-bootstrap CIs (block 60) for every contrast, plus the
effective number of independent blocks so the power is visible rather than
implied.
"""
import warnings, json, time
warnings.filterwarnings('ignore')
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
HZ = ["fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess"]
N_SPLITS, N_ROUNDS, SEEDS = 5, 100, (42, 43, 44)
EMBARGO = 60          # MATCHED across all arms — the whole point
BLK, NBOOT, BSEED = 60, 10_000, 20260724

train_all, FEATS, _ = load_panel(DD, label="fwd_60d_excess")
nb = partial(build_normalization, data_dir=DD)
dates = np.array(sorted(pd.to_datetime(train_all["date"].unique())))
folds = []
for vi in np.array_split(np.arange(len(dates)), N_SPLITS + 1)[1:]:
    end = int(vi[0]) - EMBARGO
    if end > 0 and len(vi):
        folds.append({"train": set(dates[:end]), "val": set(dates[vi])})
print(f"panel {len(train_all):,} rows · {len(FEATS)} feats · "
      f"{len(folds)} folds · embargo {EMBARGO}d MATCHED across arms", flush=True)


def per_date_ic(pred, va, label):
    s = va[[label, "date"]].copy()
    s["p"] = pred
    s = s.dropna()
    return {d: float(g["p"].corr(g[label], method="spearman"))
            for d, g in s.groupby("date")
            if len(g) >= 5 and g["p"].std() > 0 and g[label].std() > 0}


res = {}
for tl in HZ:
    t0 = time.time()
    acc = {ev: {} for ev in HZ}
    for seed in SEEDS:
        for f in folds:
            tr = train_all[train_all["date"].isin(f["train"])].dropna(subset=[tl])
            va = train_all[train_all["date"].isin(f["val"])]
            if tr["date"].nunique() < 20 or va.empty:
                continue
            mu, sd, kind, _, _ = nb(tr, FEATS)
            b, _ = train_xgb(tr, FEATS, label=tl,
                             params=dict(PANEL_LTR_PARAMS, seed=seed),
                             num_boost_round=N_ROUNDS, feature_means=mu,
                             feature_stds=sd, feature_norm_kind=kind)
            pred = b.predict(xgb.DMatrix(
                panel_training_matrix(va, FEATS, mu, sd, kind).values.astype(np.float64)))
            for ev in HZ:
                for d, v in per_date_ic(pred, va, ev).items():
                    acc[ev].setdefault(d, []).append(v)
    res[tl] = {ev: {d: float(np.mean(v)) for d, v in m.items()} for ev, m in acc.items()}
    print(f"trained {tl:18} [{time.time()-t0:.0f}s]  " +
          "  ".join(f"{ev.replace('fwd_','').replace('_excess',''):>4}="
                    f"{np.mean(list(res[tl][ev].values())):+.4f}" for ev in HZ), flush=True)

print("\n" + "=" * 78, flush=True)
print(f"MATCHED-EMBARGO ({EMBARGO}d) OOS IC — rows = TRAIN label, cols = EVAL horizon",
      flush=True)
print("=" * 78, flush=True)
print(f"{'train on':>16} " + "".join(f"{e.replace('_excess',''):>14}" for e in HZ), flush=True)
for tl in HZ:
    print(f"{tl.replace('_excess',''):>16} " +
          "".join(f"{np.mean(list(res[tl][e].values())):>+14.4f}" for e in HZ), flush=True)


def boot_ci(diff, alpha):
    rng = np.random.default_rng(BSEED)
    n = len(diff)
    starts = np.arange(n - BLK + 1)
    nb_ = int(np.ceil(n / BLK))
    m = np.array([np.concatenate([diff[i:i + BLK] for i in
                                  rng.choice(starts, size=nb_, replace=True)])[:n].mean()
                  for _ in range(NBOOT)])
    return float(np.percentile(m, 100 * alpha / 2)), float(np.percentile(m, 100 * (1 - alpha / 2)))


print("\nPAIRED CONTRASTS (block bootstrap, block=60, 90% CI)", flush=True)
print(f"{'contrast':>44} {'dIC':>9} {'lo':>9} {'hi':>9}  signif", flush=True)
print("-" * 86, flush=True)
out = []
for ev in HZ:
    for a, b_ in [("fwd_20d_excess", "fwd_60d_excess"),
                  ("fwd_5d_excess", "fwd_60d_excess"),
                  ("fwd_20d_excess", "fwd_5d_excess")]:
        sh = sorted(set(res[a][ev]) & set(res[b_][ev]))
        d = np.array([res[a][ev][x] - res[b_][ev][x] for x in sh])
        lo, hi = boot_ci(d, 0.10)
        sig = "YES" if (lo > 0 or hi < 0) else "no"
        lab = (f"train {a.replace('fwd_','').replace('_excess','')} vs "
               f"{b_.replace('fwd_','').replace('_excess','')} @eval "
               f"{ev.replace('fwd_','').replace('_excess','')}")
        print(f"{lab:>44} {d.mean():>+9.4f} {lo:>+9.4f} {hi:>+9.4f}  {sig}", flush=True)
        out.append({"contrast": lab, "d": float(d.mean()), "lo": lo, "hi": hi,
                    "signif": sig, "n_dates": len(sh)})

n_dates = len(res[HZ[0]][HZ[0]])
print(f"\nPOWER: {n_dates} validation dates / block {BLK} "
      f"= ~{n_dates // BLK} effective independent blocks.", flush=True)
print("A difference of ~0.005 IC is at or below what this design can resolve —", flush=True)
print("read non-significant contrasts as UNDERPOWERED, not as demonstrated equality.",
      flush=True)

json.dump({"embargo": EMBARGO, "n_dates": n_dates, "block": BLK,
           "grid": {tl: {ev: float(np.mean(list(res[tl][ev].values()))) for ev in HZ}
                    for tl in HZ},
           "contrasts": out},
          open(SCRATCH / "horizon_matched_result.json", "w"), indent=2)
print("\nSaved horizon_matched_result.json", flush=True)
