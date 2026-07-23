"""GOAL-4 Tier-1 PatchTST existence — score the 3 single-split models on the
2023+ test window, feed the SAME expkit existence machinery as XGB.

Leakage-correct: each model trained on data <= 2023-01-01 - horizon_lookahead
(hf_trainer --train-cutoff). Test dates are strictly after. Apples-to-apples
with g4_t1_xgb_existence.py.
"""
from __future__ import annotations
import sys, glob, numpy as np, pandas as pd
sys.path.insert(0, "/Users/renhao/git/github/renquant-orchestrator/src")
for r in ("renquant-pipeline", "renquant-common", "renquant-base-data", "renquant-model"):
    sys.path.insert(0, f"/Users/renhao/git/github/{r}/src")
sys.path.insert(0, "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-pipeline/src")

from renquant_orchestrator.expkit.evaluation import per_date_ic, shifted_label_placebo, gate_shift_sessions
from renquant_orchestrator.expkit.stats import block_bootstrap_conditional_mean, summarize_boot, usable_blocks
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer

SP = "/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad"
PANEL = "/Users/renhao/git/github/RenQuant/data/transformer_v4_wl200_clean.parquet"
LABELS = {"5d": "fwd_5d_excess", "20d": "fwd_20d_excess", "60d": "fwd_60d_excess"}
HORIZ = {"5d": 5, "20d": 20, "60d": 60}
SPLIT = pd.Timestamp("2023-01-01")
ALPHA = 0.05 / 6
NBOOT = 2000

from scipy.stats import norm as _norm
def min_detectable_ic(K, sd, alpha_one_sided=ALPHA, power=0.80):  # Bonferroni-correct by default
    if K <= 0 or sd <= 0: return float("inf")
    return (_norm.ppf(1-alpha_one_sided) + _norm.ppf(power)) * sd / (K ** 0.5)

print("loading panel ...", flush=True)
df = pd.read_parquet(PANEL)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["date", "ticker"]).reset_index(drop=True)

def score_window(scorer, panel, test_dates, feat_cols, seq_len):
    """Score each test date at its as-of point using a trailing history window."""
    keep = ["ticker", "date"] + [c for c in feat_cols if c in panel.columns]
    p = panel[keep]
    dates_all = np.array(sorted(p["date"].unique()))
    rows = []
    for t in test_dates:
        lo = t - pd.Timedelta(days=int(seq_len * 2.2) + 15)  # enough calendar days for seq_len bars
        hist = p[(p["date"] > lo) & (p["date"] <= t)]
        tickers = hist.loc[hist["date"] == t, "ticker"].unique().tolist()
        if not tickers:
            continue
        try:
            s = scorer.score_with_history(hist, tickers)
        except Exception as e:
            if not rows:
                print("  score_with_history error:", repr(e)[:200], flush=True)
            continue
        for tk, val in s.items():
            rows.append((t, tk, float(val)))
    return pd.DataFrame(rows, columns=["date", "ticker", "score"])

print(f"\n[T1 PatchTST existence — single-split @ 2023-01-01]")
print(f"{'h':>4} {'n':>7} {'blocks':>7} {'MDE':>7} {'real_ic':>8} {'floor':>7} {'clean_ic':>8} {'clean_lb95':>10} {'clean_lb_bonf':>13} {'EXISTS':>7}")
results = {}
for name, lbl in LABELS.items():
    h = HORIZ[name]
    pts = glob.glob(f"{SP}/patchtst_ss_fixed/pt_{name}/**/*model*.pt", recursive=True) + \
          glob.glob(f"{SP}/patchtst_ss_fixed/pt_{name}/*.pt")
    if not pts:
        print(f"{name:>4}  (no model .pt found — training not done?)", flush=True); continue
    scorer = HFPatchTSTPanelScorer.load(sorted(pts)[0])
    seq_len = scorer.seq_len; feat_cols = scorer.feature_cols
    test_dates = np.array(sorted(df.loc[df["date"] >= SPLIT, "date"].unique()))
    sc = score_window(scorer, df, test_dates, feat_cols, seq_len)
    if sc.empty:
        print(f"{name:>4}  (scored 0 rows)", flush=True); continue
    score = sc.pivot_table(index="date", columns="ticker", values="score", aggfunc="first")
    sub = df[df["date"] >= SPLIT]
    label = sub.pivot_table(index="date", columns="ticker", values=lbl, aggfunc="first")
    placebo = shifted_label_placebo(label, gate_shift_sessions(h))
    ic = per_date_ic(score, label, placebo, min_names=30)
    clean = ic["clean_ic"].dropna() if "clean_ic" in ic else pd.Series(dtype=float)
    real = ic["real_ic"].dropna(); plc = ic["placebo_ic"].dropna()
    n = len(clean); K = usable_blocks(n, h)
    boot = block_bootstrap_conditional_mean(clean.to_numpy(), np.ones(n, bool), block=h, n_boot=NBOOT, seed=44)
    s95 = summarize_boot(boot, alpha_one_sided=0.025)
    sbf = summarize_boot(boot, alpha_one_sided=ALPHA)
    sd = clean.std(ddof=1); mde = min_detectable_ic(K, sd)
    exists = sbf["lb_one_sided"] > 0
    results[name] = dict(n=n, K=K, real=real.mean(), floor=plc.mean(), clean=clean.mean(),
                         lb95=s95["lb_one_sided"], lb_bonf=sbf["lb_one_sided"], mde=mde, exists=exists,
                         val_ic=scorer.metadata.get("val_ic"))
    print(f"{name:>4} {n:>7} {K:>7} {mde:>7.3f} {real.mean():>8.3f} {plc.mean():>7.3f} "
          f"{clean.mean():>8.3f} {s95['lb_one_sided']:>10.3f} {sbf['lb_one_sided']:>13.3f} {str(exists):>7}", flush=True)

any_exists = any(r["exists"] for r in results.values())
print(f"\n[T1 PatchTST VERDICT] any horizon exists? -> {any_exists}")
import json
json.dump(results, open(f"{SP}/g4_patchtst_existence_FIXED_results.json", "w"), indent=2, default=str)
print(f"saved -> {SP}/g4_patchtst_existence_FIXED_results.json")
