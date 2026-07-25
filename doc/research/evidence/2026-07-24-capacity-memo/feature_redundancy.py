"""How many INDEPENDENT signals are actually in the 172 production features?

The user's intuition: 158 alpha158 features is suspiciously many.
alpha158 is built as ~29 base operators x 5 windows {5,10,20,30,60} + 13
K-line features. MA5/MA10/MA20/MA30/MA60 are near-collinear by construction.

This measures the EFFECTIVE dimensionality — no model, no label, just the
covariance structure of the features themselves. Cheap and decisive.
"""
import pandas as pd, numpy as np, json, re, warnings
warnings.filterwarnings('ignore')

RQ = "/Users/renhao/git/github/RenQuant"
SCRATCH = "/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad"

# Production feature set = every panel col minus the label-ish ones
_EXCL = {"ticker", "date", "split_label",
         "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess", "fwd_60d_excess_raw"}
pan = pd.read_parquet(f"{RQ}/data/alpha158_291_fundamental_dataset_rawlabel.parquet")
pan["date"] = pd.to_datetime(pan["date"])
feats = [c for c in pan.columns if c not in _EXCL and pd.api.types.is_numeric_dtype(pan[c])]
print(f"Production-equivalent feature count: {len(feats)}")

# ── Cross-sectionally standardize per date (that's how the model sees them) ──
X = pan[["date"] + feats].copy()
g = X.groupby("date")
Z = (X[feats] - g[feats].transform("mean")) / g[feats].transform("std").replace(0, np.nan)
Z = Z.replace([np.inf, -np.inf], np.nan)
keep = Z.columns[Z.notna().mean() > 0.5].tolist()
Z = Z[keep].fillna(0.0)
print(f"Usable after per-date standardization: {len(keep)}")

# ── 1. Effective dimensionality via PCA ──────────────────────────────
C = np.corrcoef(Z.values, rowvar=False)
C = np.nan_to_num(C, nan=0.0)
ev = np.linalg.eigvalsh(C)[::-1]
ev = np.clip(ev, 0, None)
cum = np.cumsum(ev) / ev.sum()
print("\n" + "=" * 70)
print("EFFECTIVE DIMENSIONALITY (PCA of the per-date-standardized features)")
print("=" * 70)
for thr in (0.50, 0.80, 0.90, 0.95, 0.99):
    k = int(np.searchsorted(cum, thr) + 1)
    print(f"  {thr:.0%} of variance explained by {k:4d} of {len(keep)} components"
          f"   ({k/len(keep):5.1%})")
# participation-ratio effective rank
pr = (ev.sum() ** 2) / (ev ** 2).sum()
# entropy-based effective rank
p = ev / ev.sum(); p = p[p > 0]
er = float(np.exp(-(p * np.log(p)).sum()))
print(f"\n  Participation-ratio effective rank : {pr:6.1f}")
print(f"  Entropy effective rank             : {er:6.1f}")
print(f"  Nominal feature count              : {len(keep):6d}")
print(f"  -> redundancy multiple             : {len(keep)/pr:6.1f}x")

# ── 2. How much is pure window-duplication? ──────────────────────────
print("\n" + "=" * 70)
print("WINDOW DUPLICATION — the alpha158 construction")
print("=" * 70)
base = {}
for f in keep:
    m = re.match(r"^([A-Z]+?)(\d+)$", f)
    if m and m.group(2) in ("5", "10", "20", "30", "60"):
        base.setdefault(m.group(1), []).append(f)
fam = {k: v for k, v in base.items() if len(v) > 1}
n_in_fam = sum(len(v) for v in fam.values())
print(f"  {len(fam)} base operators x multiple windows = {n_in_fam} of {len(keep)} features")
print(f"  ({n_in_fam/len(keep):.0%} of the feature set is the SAME operator at a different window)")
print("\n  Median |corr| WITHIN each operator family (top 12 by family size):")
rows = []
Zv = Z.values
idx = {c: i for i, c in enumerate(keep)}
for op, cols in sorted(fam.items(), key=lambda kv: -len(kv[1]))[:12]:
    ii = [idx[c] for c in cols]
    sub = C[np.ix_(ii, ii)]
    off = sub[np.triu_indices(len(ii), 1)]
    rows.append((op, len(cols), float(np.median(np.abs(off))), float(np.max(np.abs(off)))))
    print(f"    {op:8} n={len(cols)}  median|r|={rows[-1][2]:.3f}  max|r|={rows[-1][3]:.3f}")
all_within = []
for op, cols in fam.items():
    ii = [idx[c] for c in cols]
    sub = C[np.ix_(ii, ii)]
    all_within.extend(np.abs(sub[np.triu_indices(len(ii), 1)]).tolist())
print(f"\n  ALL within-family pairs: median |r| = {np.median(all_within):.3f}, "
      f"{np.mean(np.array(all_within) > 0.9):.0%} have |r| > 0.90")

# ── 3. Greedy de-duplication: how few features cover the space? ──────
print("\n" + "=" * 70)
print("GREEDY DE-DUPLICATION (drop any feature with |r| > threshold to a kept one)")
print("=" * 70)
order = np.argsort(-np.abs(C).sum(axis=0))   # most-connected first as seeds
for thr in (0.95, 0.90, 0.80, 0.70, 0.60):
    kept_i, dropped = [], 0
    for i in order:
        if all(abs(C[i, j]) <= thr for j in kept_i):
            kept_i.append(i)
        else:
            dropped += 1
    print(f"  |r| > {thr:.2f} -> keep {len(kept_i):4d} / {len(keep)}  (drop {dropped})")
    if thr == 0.90:
        surv90 = [keep[i] for i in kept_i]

print(f"\n  Survivors at |r|<=0.90 ({len(surv90)}):")
for i in range(0, len(surv90), 8):
    print("    " + "  ".join(f"{s:<14}" for s in surv90[i:i+8]))

json.dump({"n_features": len(keep),
           "pca_k_for": {str(t): int(np.searchsorted(cum, t) + 1) for t in (0.5, 0.8, 0.9, 0.95, 0.99)},
           "participation_ratio_rank": float(pr), "entropy_rank": float(er),
           "redundancy_multiple": float(len(keep) / pr),
           "n_window_family_features": int(n_in_fam),
           "within_family_median_abs_r": float(np.median(all_within)),
           "within_family_pct_above_0.9": float(np.mean(np.array(all_within) > 0.9)),
           "survivors_r90": surv90},
          open(f"{SCRATCH}/feature_redundancy_result.json", "w"), indent=2)
print(f"\nSaved feature_redundancy_result.json")
