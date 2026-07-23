"""GOAL-4 Tier-0 + Tier-1 real-data existence probe (XGB), $0 / local.

Leakage-correct single-split as a FIRST read:
  train = dates <= split - embargo(h);  test = dates >= split.
The alpha158 features are PIT; the only future is the label (fwd_Nd_excess),
which is never in X. Feeds the committed g4_ensemble harness primitives.
"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/Users/renhao/git/github/renquant-orchestrator/src")

from renquant_orchestrator.expkit.evaluation import per_date_ic, shifted_label_placebo, gate_shift_sessions
from renquant_orchestrator.expkit.stats import block_bootstrap_conditional_mean, summarize_boot, usable_blocks
import xgboost as xgb

# inlined (decoupled from the concurrently-churning orchestrator module)
def min_detectable_ic(K, sd, factor=2.4865):  # one-sided z_.95 + z_.80
    return float("inf") if (K <= 0 or sd <= 0) else factor * sd / (K ** 0.5)

def positive_control_recovery_inline(label_wide, rho, horizon, seed, nboot):
    rng = np.random.default_rng(seed)
    std = label_wide.stack().std() or 1.0
    noise = pd.DataFrame(rng.standard_normal(label_wide.shape), index=label_wide.index, columns=label_wide.columns)
    score = rho * (label_wide / std) + ((1 - rho * rho) ** 0.5) * noise
    placebo = shifted_label_placebo(label_wide, gate_shift_sessions(horizon))
    ic = per_date_ic(score, label_wide, placebo, min_names=30)
    clean = ic["clean_ic"].dropna(); real = ic["real_ic"].dropna()
    boot = block_bootstrap_conditional_mean(clean.to_numpy(), np.ones(len(clean), bool),
                                            block=horizon, n_boot=nboot, seed=seed)
    s = summarize_boot(boot, alpha_one_sided=0.025)
    return float(real.mean()), float(s["lb_one_sided"])

PANEL = "/Users/renhao/git/github/RenQuant/data/alpha158_291_fundamental_dataset_rawlabel.parquet"
LABELS = {"5d": "fwd_5d_excess", "20d": "fwd_20d_excess", "60d": "fwd_60d_excess"}
HORIZ = {"5d": 5, "20d": 20, "60d": 60}
SPLIT = pd.Timestamp("2023-01-01")
ALPHA = 0.05 / 6  # Bonferroni k=6 (frozen spec)
NBOOT = 2000

print("loading panel ...", flush=True)
df = pd.read_parquet(PANEL)
df["date"] = pd.to_datetime(df["date"])
lab_cols = ["fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess", "fwd_60d_excess_raw"]
drop_like = lambda c: ("fwd" in c.lower() or "excess" in c.lower() or "label" in c.lower()
                       or c in ("ticker", "date"))
feat_cols = [c for c in df.columns if not drop_like(c) and pd.api.types.is_numeric_dtype(df[c])]
print(f"panel {df.shape} | {len(feat_cols)} feature cols | dates {df.date.min().date()}..{df.date.max().date()}", flush=True)

def wide(frame, col):
    return frame.pivot_table(index="date", columns="ticker", values=col, aggfunc="first")

# ---- Tier 0: positive control on the REAL 5d label frame ----
lab5 = wide(df, "fwd_5d_excess").dropna(how="all")
pc_real, pc_lb = positive_control_recovery_inline(lab5, rho=0.8, horizon=5, seed=44, nboot=NBOOT)
print(f"\n[T0 positive control] injected rho=0.8 into REAL 5d label -> "
      f"real_ic={pc_real:.3f}  clean_lb={pc_lb:.3f}  PASS={pc_real>0.5 and pc_lb>0}", flush=True)

# ---- Tier 1: XGB single-split existence per horizon ----
print("\n[T1 XGB existence — leakage-correct single split @ 2023-01-01]")
print(f"{'h':>4} {'n_test_dates':>12} {'blocks':>7} {'MDE':>7} {'real_ic':>8} {'floor':>7} {'clean_ic':>8} {'clean_lb95':>10} {'clean_lb_bonf':>13} {'EXISTS':>7}")
results = {}
for name, lbl in LABELS.items():
    h = HORIZ[name]
    sub = df[["date", "ticker", lbl] + feat_cols].dropna(subset=[lbl])
    embargo = pd.Timedelta(days=int(h * 1.6) + 5)  # gap so train labels don't peek into test
    tr = sub[sub.date <= (SPLIT - embargo)]
    te = sub[sub.date >= SPLIT]
    Xtr, ytr = tr[feat_cols].to_numpy("float32"), tr[lbl].to_numpy("float32")
    Xte = te[feat_cols].to_numpy("float32")
    model = xgb.XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.03,
                             subsample=0.8, colsample_bytree=0.6, min_child_weight=10,
                             reg_lambda=5.0, n_jobs=8, tree_method="hist")
    model.fit(Xtr, ytr)
    te = te.copy(); te["score"] = model.predict(Xte)
    score = te.pivot_table(index="date", columns="ticker", values="score", aggfunc="first")
    label = te.pivot_table(index="date", columns="ticker", values=lbl, aggfunc="first")
    placebo = shifted_label_placebo(label, gate_shift_sessions(h))
    ic = per_date_ic(score, label, placebo, min_names=30)
    clean = ic["clean_ic"].dropna() if "clean_ic" in ic else pd.Series(dtype=float)
    real = ic["real_ic"].dropna(); plc = ic["placebo_ic"].dropna()
    n = len(clean); K = usable_blocks(n, h)
    boot = block_bootstrap_conditional_mean(clean.to_numpy(), np.ones(n, bool), block=h, n_boot=NBOOT, seed=44)
    s95 = summarize_boot(boot, alpha_one_sided=0.025)      # two-sided 95 lb
    sbf = summarize_boot(boot, alpha_one_sided=ALPHA)      # Bonferroni one-sided lb
    sd = clean.std(ddof=1); mde = min_detectable_ic(K, sd)
    exists = sbf["lb_one_sided"] > 0
    results[name] = dict(n=n, K=K, real=real.mean(), floor=plc.mean(), clean=clean.mean(),
                         lb95=s95["lb_one_sided"], lb_bonf=sbf["lb_one_sided"], mde=mde, exists=exists)
    print(f"{name:>4} {n:>12} {K:>7} {mde:>7.3f} {real.mean():>8.3f} {plc.mean():>7.3f} "
          f"{clean.mean():>8.3f} {s95['lb_one_sided']:>10.3f} {sbf['lb_one_sided']:>13.3f} {str(exists):>7}", flush=True)

any_exists = any(r["exists"] for r in results.values())
print(f"\n[T1 VERDICT] any horizon exists (clean_ic Bonferroni-lb > 0)? -> {any_exists}")
print("  (single-split first read; model is ~stale toward test end -> a NULL here is suggestive,")
print("   not the KILL gate. KILL needs XGB *and* PatchTST null across horizons via full WF.)")
