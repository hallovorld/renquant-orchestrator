#!/usr/bin/env python
"""Independent adversarial verification of the M8 cluster wave-1 NO-GO verdict.

Verifies PR #261 (doc/research/2026-07-03-m8-cluster-wave1.md) WITHOUT rerunning
scripts/m8_cluster_wave1.py: the load-bearing claims are re-derived with an
independently written implementation (different IC code, different group
construction, different data prep path) plus robustness probes the original
did not run (multi-seed retrains, random-wave control, leave-one-cut-out).

Checks (see doc/research/2026-07-03-m8-verification.md):
  1. training-dilution mechanism — independent retrain of baseline-133 vs
     augmented-233 on cuts 5 and 7, seeds {42, 7, 2026}, incumbent-subset IC
  2. paired-delta arithmetic — recompute every gate number from the committed
     evidence JSONs, plus internal consistency of the two evidence files
  3. selection-criterion leakage — empirical probes (feature-name audit,
     out-of-similarity-window cut 7, random-wave control); ruling in the memo
  4. qualifying-cut rule — recompute per-cut wave coverage and the candidate
     start-date topology from the raw dataset; gate sensitivity to the rule
  5. harness parity — compare frozen params/cuts against renquant-model
     panel_trainer and the umbrella walk_forward_extended.py sources

Read-only on all production data. Writes ONLY
doc/research/evidence/2026-07-03-m8-verification/verification_results.json.

Run with the umbrella venv (xgboost):
    /Users/renhao/git/github/RenQuant/.venv/bin/python \
        scripts/m8_independent_verification.py
"""
from __future__ import annotations

import ast
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("m8v")

REPO = Path(__file__).resolve().parent.parent
THEIR_EVIDENCE = REPO / "doc" / "research" / "evidence" / "2026-07-03-m8"
OUT_DIR = REPO / "doc" / "research" / "evidence" / "2026-07-03-m8-verification"

# ---- read-only production inputs (never written) ---------------------------
DATASET = Path("/Users/renhao/git/github/RenQuant/data/alpha158_816_dataset.parquet")
STRATEGY_CFG = Path(
    "/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json"
)
PANEL_TRAINER = Path(
    "/Users/renhao/git/github/renquant-model/src/renquant_model_gbdt/panel_trainer.py"
)
WF_EXTENDED = Path("/Users/renhao/git/github/RenQuant/scripts/walk_forward_extended.py")
THEIR_SCRIPT = REPO / "scripts" / "m8_cluster_wave1.py"

CUTS = [
    ("2016-01-01", "2018-12-31", "2019-02-01", "2019-12-31"),
    ("2017-01-01", "2019-12-31", "2020-02-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-02-01", "2021-12-31"),
    ("2019-01-01", "2021-12-31", "2022-02-01", "2022-12-31"),
    ("2020-01-01", "2022-12-31", "2023-02-01", "2023-12-31"),
    ("2021-01-01", "2023-12-31", "2024-02-01", "2024-12-31"),
    ("2022-01-01", "2024-12-31", "2025-02-01", "2025-12-31"),
]
LABEL = "fwd_60d_excess"
NON_FEATURE_COLS = {
    "ticker", "date", "split_label", "fwd_5d_excess", "fwd_20d_excess",
    "fwd_60d_excess",
}
FROZEN_PARAMS = {
    "objective": "rank:pairwise", "eta": 0.05, "max_depth": 5,
    "min_child_weight": 50, "subsample": 0.7, "colsample_bytree": 0.7,
    "verbosity": 0,
}
N_ROUNDS = 100
RETRAIN_CUTS = [5, 6, 7]       # all qualifying cuts — full frozen gate per seed
RETRAIN_SEEDS = [42, 7, 2026]  # 42 = their frozen seed; others = noise probe
N_RANDOM_DRAWS = 3             # random-wave control draws (rng 0, 1, 2)


# ---------------------------------------------------------------------------
# independent primitives (deliberately NOT the original implementations)
# ---------------------------------------------------------------------------
def spearman_ic_by_date(pred: np.ndarray, y: np.ndarray, dates: np.ndarray,
                        keep: np.ndarray | None = None) -> dict[str, float]:
    """Per-date cross-sectional Spearman via pandas ranks + np.corrcoef."""
    df = pd.DataFrame({"p": pred, "y": y, "d": dates})
    if keep is not None:
        df = df[keep]
    out: dict[str, float] = {}
    for d, g in df.groupby("d"):
        if len(g) < 5:
            continue
        rp = g["p"].rank().to_numpy()
        ry = g["y"].rank().to_numpy()
        if rp.std() == 0 or ry.std() == 0:
            continue
        ic = float(np.corrcoef(rp, ry)[0, 1])
        if np.isfinite(ic):
            out[str(pd.Timestamp(d).date())] = ic
    return out


def train_predict(train: pd.DataFrame, test: pd.DataFrame, feat_cols: list[str],
                  seed: int) -> np.ndarray:
    """Frozen-spec training (z-norm clip ±5, label clip ±5, rank:pairwise,
    per-date groups) with an independent implementation."""
    import xgboost as xgb

    train = train.sort_values(["date", "ticker"], kind="mergesort")
    Xtr = train[feat_cols].fillna(0.0).to_numpy(np.float64)
    Xte = test[feat_cols].fillna(0.0).to_numpy(np.float64)
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    Xtr = np.clip((Xtr - mu) / sd, -5, 5)
    Xte = np.clip((Xte - mu) / sd, -5, 5)
    ytr = train[LABEL].clip(-5, 5).to_numpy(np.float64)
    groups = train.groupby("date", sort=True).size().to_numpy()
    assert groups.sum() == len(train)
    dtr = xgb.DMatrix(Xtr, label=ytr)
    dtr.set_group(groups)
    params = dict(FROZEN_PARAMS, seed=seed)
    booster = xgb.train(params, dtr, num_boost_round=N_ROUNDS)
    return booster.predict(xgb.DMatrix(Xte))


def cut_frames(df: pd.DataFrame, cut_idx: int, tickers: list[str]):
    a, b, c, d = CUTS[cut_idx - 1]
    sub = df[df["ticker"].isin(tickers)]
    tr = sub[(sub["date"] >= a) & (sub["date"] <= b)].dropna(subset=[LABEL])
    te = sub[(sub["date"] >= c) & (sub["date"] <= d)].dropna(subset=[LABEL])
    return tr, te


# ---------------------------------------------------------------------------
# check 2 — paired-delta arithmetic from the committed evidence
# ---------------------------------------------------------------------------
def check_arithmetic() -> dict:
    res = json.loads((THEIR_EVIDENCE / "m8_paired_wf_results.json").read_text())
    per_date = json.loads((THEIR_EVIDENCE / "m8_per_date_ics.json").read_text())
    spec = json.loads((THEIR_EVIDENCE / "m8_frozen_spec.json").read_text())
    band = spec["gate"]["noise_band"]
    qual = res["qualifying_cuts"]

    runs = {(r["label"], r["arm"], r["cut"], r["placebo"]): r for r in res["runs"]}

    def ic(lbl, arm, cut, placebo=False):
        return runs[(lbl, arm, cut, placebo)]["ic_mean"]

    out: dict = {"noise_band": band, "qualifying_cuts": qual}
    for lbl in ("fwd_60d_excess", "fwd_20d_excess"):
        per_cut, dq, dall = [], [], []
        for cut in range(1, 8):
            dlt = ic(lbl, "augmented", cut) - ic(lbl, "baseline", cut)
            per_cut.append({"cut": cut, "delta": round(dlt, 6)})
            dall.append(dlt)
            if cut in qual:
                dq.append(dlt)
        pc = [
            (ic(lbl, "augmented", c) - ic(lbl, "augmented", c, True))
            - (ic(lbl, "baseline", c) - ic(lbl, "baseline", c, True))
            for c in qual
        ]
        pooled = []
        for c in qual:
            kb, ka = f"{lbl}|baseline|cut{c}|real", f"{lbl}|augmented|cut{c}|real"
            common = set(per_date[kb]) & set(per_date[ka])
            pooled += [per_date[ka][d] - per_date[kb][d] for d in common]
        out[lbl] = {
            "per_cut_delta": per_cut,
            "mean_delta_qualifying": round(float(np.mean(dq)), 6),
            "mean_delta_all_cuts": round(float(np.mean(dall)), 6),
            "placebo_clean_mean_delta_qualifying": round(float(np.mean(pc)), 6),
            "wins_qualifying": int(sum(1 for x in dq if x > 0)),
            "pooled_date_level_mean_delta": round(float(np.mean(pooled)), 6),
            "pooled_date_level_naive_se": round(
                float(np.std(pooled) / np.sqrt(len(pooled))), 6),
            "pooled_n_dates": len(pooled),
        }

    # internal consistency: every committed ic_mean must equal the mean of its
    # own committed per-date IC dict, and n_test_dates must match its length
    worst = 0.0
    mismatches = []
    for key, ics in per_date.items():
        lbl, arm, cut_s, kind = key.split("|")
        rec = runs[(lbl, arm, int(cut_s[3:]), kind == "placebo")]
        diff = abs(rec["ic_mean"] - float(np.mean(list(ics.values()))))
        worst = max(worst, diff)
        if diff > 5e-6 or rec["n_test_dates"] != len(ics):
            mismatches.append(key)
    out["evidence_internal_consistency"] = {
        "runs_cross_checked": len(per_date),
        "max_abs_ic_mean_discrepancy": round(worst, 8),
        "mismatches": mismatches,
    }
    gate_delta = out["fwd_60d_excess"]["mean_delta_qualifying"]
    out["gate_recheck"] = {
        "gate": f"PASS iff mean qualifying delta >= -{band} on fwd_60d_excess",
        "recomputed_mean_delta": gate_delta,
        "verdict_implied": "NO-GO" if gate_delta < -band else "not NO-GO",
        "matches_their_verdict": bool(gate_delta < -band),
    }
    return out


# ---------------------------------------------------------------------------
# check 4 — qualifying-cut rule and data topology, from the raw dataset
# ---------------------------------------------------------------------------
def check_coverage(df: pd.DataFrame, wave: list[str], candidates: set[str],
                   arithmetic: dict) -> dict:
    first = df.groupby("ticker")["date"].min()
    cand_first = first[first.index.isin(candidates)]
    start_hist = cand_first.value_counts().sort_values(ascending=False)
    top_start = str(pd.Timestamp(start_hist.index[0]).date())
    out: dict = {
        "n_candidates": int(len(cand_first)),
        "modal_candidate_start_date": top_start,
        "n_candidates_at_modal_start": int(start_hist.iloc[0]),
        "claim_512_of_683_start_2021_05_03": bool(
            top_start == "2021-05-03" and int(start_hist.iloc[0]) == 512
        ),
    }

    wave_df = df[df["ticker"].isin(wave)]
    cov = []
    qualifying = []
    for i, (a, b, c, d) in enumerate(CUTS, 1):
        tr = wave_df[(wave_df["date"] >= a) & (wave_df["date"] <= b)]
        te = wave_df[(wave_df["date"] >= c) & (wave_df["date"] <= d)]
        tr_ok = set(tr.groupby("ticker").size().pipe(lambda s: s[s >= 252]).index)
        te_ok = set(te.groupby("ticker").size().pipe(lambda s: s[s >= 100]).index)
        n_ok = len(tr_ok & te_ok)
        cov.append({"cut": i, "covered": n_ok, "fraction": round(n_ok / len(wave), 4)})
        if n_ok / len(wave) >= 0.5:
            qualifying.append(i)
    out["per_cut_wave_coverage"] = cov
    out["qualifying_cuts_recomputed"] = qualifying
    out["matches_their_qualifying_cuts"] = qualifying == [5, 6, 7]

    # gate sensitivity to the qualifying rule (uses committed per-cut deltas)
    deltas = {r["cut"]: r["delta"]
              for r in arithmetic["fwd_60d_excess"]["per_cut_delta"]}
    scenarios = {
        "frozen_rule_cuts_5_6_7": [5, 6, 7],
        "all_7_cuts": list(range(1, 8)),
        "coverage_ge_25pct_all_7_here": [c["cut"] for c in cov if c["fraction"] >= 0.25],
        "cuts_4_7": [4, 5, 6, 7],
        "leave_out_cut5": [6, 7],
        "leave_out_cut6": [5, 7],
        "leave_out_cut7": [5, 6],
    }
    out["gate_sensitivity"] = {
        name: {
            "cuts": cs,
            "mean_delta": round(float(np.mean([deltas[c] for c in cs])), 6),
            "passes_band": bool(np.mean([deltas[c] for c in cs]) >= -0.010),
        }
        for name, cs in scenarios.items()
    }
    return out


# ---------------------------------------------------------------------------
# check 1 — independent retrain: dilution on the incumbent subset
# ---------------------------------------------------------------------------
def check_dilution(df: pd.DataFrame, feat_cols: list[str], inc: list[str],
                   wave: list[str], eligible_pool: list[str]) -> dict:
    theirs = json.loads((THEIR_EVIDENCE / "m8_paired_wf_results.json").read_text())
    their_runs = {(r["arm"], r["cut"]): r for r in theirs["runs"]
                  if r["label"] == LABEL and not r["placebo"]}
    aug = sorted(set(inc) | set(wave))
    inc_set = set(inc)
    out: dict = {"cuts": {}, "random_wave_control": {}}

    for cut in RETRAIN_CUTS:
        base_tr, base_te = cut_frames(df, cut, inc)
        aug_tr, aug_te = cut_frames(df, cut, aug)
        rows = []
        for seed in RETRAIN_SEEDS:
            t0 = time.time()
            pb = train_predict(base_tr, base_te, feat_cols, seed)
            base_ics = spearman_ic_by_date(
                pb, base_te[LABEL].to_numpy(), base_te["date"].to_numpy())
            pa = train_predict(aug_tr, aug_te, feat_cols, seed)
            y_te, d_te = aug_te[LABEL].to_numpy(), aug_te["date"].to_numpy()
            aug_full = spearman_ic_by_date(pa, y_te, d_te)
            aug_inc = spearman_ic_by_date(
                pa, y_te, d_te, aug_te["ticker"].isin(inc_set).to_numpy())
            rows.append({
                "seed": seed,
                "baseline_ic": round(float(np.mean(list(base_ics.values()))), 6),
                "augmented_ic_full": round(float(np.mean(list(aug_full.values()))), 6),
                "augmented_ic_incumbent_subset": round(
                    float(np.mean(list(aug_inc.values()))), 6),
                "seconds": round(time.time() - t0, 1),
            })
            log.info("cut%d seed%d base=%+.4f aug_full=%+.4f aug_inc=%+.4f",
                     cut, seed, rows[-1]["baseline_ic"],
                     rows[-1]["augmented_ic_full"],
                     rows[-1]["augmented_ic_incumbent_subset"])
        dil = [r["baseline_ic"] - r["augmented_ic_incumbent_subset"] for r in rows]
        out["cuts"][str(cut)] = {
            "n_train_baseline": int(len(base_tr)),
            "n_train_augmented": int(len(aug_tr)),
            "their_n_train_baseline":
                their_runs[("baseline", cut)]["n_train"],
            "their_n_train_augmented":
                their_runs[("augmented", cut)]["n_train"],
            "their_baseline_ic": their_runs[("baseline", cut)]["ic_mean"],
            "their_augmented_ic_full": their_runs[("augmented", cut)]["ic_mean"],
            "their_augmented_ic_incumbent_subset":
                their_runs[("augmented", cut)]["ic_mean_incumbent_subset"],
            "per_seed": rows,
            "incumbent_dilution_baseline_minus_auginc": [round(x, 6) for x in dil],
            "dilution_positive_all_seeds": bool(all(x > 0 for x in dil)),
        }

    # the frozen gate (mean paired full-universe delta over cuts 5/6/7)
    # recomputed per seed — is the NO-GO robust to the training seed?
    per_seed_gate = []
    for si, seed in enumerate(RETRAIN_SEEDS):
        ds = [out["cuts"][str(c)]["per_seed"][si]["augmented_ic_full"]
              - out["cuts"][str(c)]["per_seed"][si]["baseline_ic"]
              for c in RETRAIN_CUTS]
        per_seed_gate.append({
            "seed": seed,
            "per_cut_delta": [round(x, 6) for x in ds],
            "mean_delta_qualifying": round(float(np.mean(ds)), 6),
            "passes_band": bool(np.mean(ds) >= -0.010),
        })
    out["frozen_gate_per_seed"] = per_seed_gate
    out["no_go_robust_across_seeds"] = bool(
        all(not g["passes_band"] for g in per_seed_gate))

    # random-wave control: 100 uniformly random eligible candidates outside
    # the similarity-selected wave — probes whether the dilution is specific
    # to the similarity-selected names or generic to +100 breadth
    non_wave_pool = [t for t in eligible_pool if t not in set(wave)]
    for draw in range(N_RANDOM_DRAWS):
        rng = np.random.default_rng(draw)
        rand_wave = sorted(rng.choice(non_wave_pool, size=100, replace=False))
        rand_aug = sorted(inc_set | set(rand_wave))
        draw_out = {}
        for cut in RETRAIN_CUTS:
            r_tr, r_te = cut_frames(df, cut, rand_aug)
            pr = train_predict(r_tr, r_te, feat_cols, 42)
            y, d = r_te[LABEL].to_numpy(), r_te["date"].to_numpy()
            full = spearman_ic_by_date(pr, y, d)
            sub = spearman_ic_by_date(
                pr, y, d, r_te["ticker"].isin(inc_set).to_numpy())
            base42 = out["cuts"][str(cut)]["per_seed"][0]["baseline_ic"]
            draw_out[str(cut)] = {
                "augmented_ic_full": round(float(np.mean(list(full.values()))), 6),
                "augmented_ic_incumbent_subset": round(
                    float(np.mean(list(sub.values()))), 6),
                "delta_full_vs_seed42_baseline": round(
                    float(np.mean(list(full.values()))) - base42, 6),
            }
            log.info("RANDOM draw%d cut%d aug_full=%+.4f aug_inc=%+.4f", draw,
                     cut, draw_out[str(cut)]["augmented_ic_full"],
                     draw_out[str(cut)]["augmented_ic_incumbent_subset"])
        gate = float(np.mean([draw_out[str(c)]["delta_full_vs_seed42_baseline"]
                              for c in RETRAIN_CUTS]))
        out["random_wave_control"][f"draw{draw}"] = {
            "cuts": draw_out,
            "gate_mean_delta_vs_seed42_baseline": round(gate, 6),
            "passes_band": bool(gate >= -0.010),
        }
    return out


# ---------------------------------------------------------------------------
# diagnostic — can THEIR exact implementation reproduce their committed cut-7
# baseline IC? (my cut-5 numbers match theirs to 6 dp; cut 7 differs, so
# establish whether their committed cut-7 number is itself re-runnable)
# ---------------------------------------------------------------------------
def check_their_impl_repro(df: pd.DataFrame, feat_cols: list[str],
                           inc: list[str]) -> dict:
    import importlib.util

    spec = importlib.util.spec_from_file_location("m8theirs", THEIR_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    theirs = json.loads((THEIR_EVIDENCE / "m8_paired_wf_results.json").read_text())
    out = {}
    for cut in (5, 7):
        tr, te = cut_frames(df, cut, inc)
        pred = mod._train_predict(tr, te, feat_cols, LABEL)
        ics = mod._per_date_ic(pred, te[LABEL].to_numpy(), te["date"].to_numpy())
        mine = float(np.mean(list(ics.values())))
        committed = [r["ic_mean"] for r in theirs["runs"]
                     if r["label"] == LABEL and r["arm"] == "baseline"
                     and r["cut"] == cut and not r["placebo"]][0]
        out[f"cut{cut}_baseline"] = {
            "their_committed_ic": committed,
            "their_impl_rerun_ic": round(mine, 6),
            "abs_diff": round(abs(mine - committed), 6),
        }
        # near-constant-feature probe: smallest train-window feature stds
        sds = np.sort(tr[feat_cols].fillna(0).to_numpy(np.float64).std(axis=0))
        out[f"cut{cut}_baseline"]["min_train_feature_stds"] = [
            float(f"{x:.3e}") for x in sds[:3]]
    return out


# ---------------------------------------------------------------------------
# check 5 — harness parity against the production sources
# ---------------------------------------------------------------------------
def check_parity(feat_cols: list[str]) -> dict:
    out: dict = {}
    # (a) production params in renquant-model
    src = PANEL_TRAINER.read_text()
    m = re.search(r"PANEL_LTR_PARAMS[^=]*=\s*(\{.*?\})", src, re.S)
    prod_params = ast.literal_eval(m.group(1)) if m else None
    n_rounds = re.search(r"DEFAULT_N_ROUNDS\s*=\s*(\d+)", src)
    default_label = re.search(r'DEFAULT_LABEL\s*=\s*"([^"]+)"', src)
    their_src = THEIR_SCRIPT.read_text()
    m2 = re.search(r"XGB_PARAMS\s*=\s*(\{.*?\})", their_src, re.S)
    their_params = ast.literal_eval(m2.group(1))
    extra = {k: v for k, v in their_params.items() if k not in (prod_params or {})}
    core_match = prod_params is not None and all(
        their_params.get(k) == v for k, v in prod_params.items())
    out["xgb_params"] = {
        "production_PANEL_LTR_PARAMS": prod_params,
        "their_XGB_PARAMS_extra_keys": extra,  # nthread only (perf, not math)
        "core_params_match": bool(core_match),
        "n_rounds_match": bool(n_rounds and int(n_rounds.group(1)) == 100),
        "default_label_match": bool(default_label
                                    and default_label.group(1) == LABEL),
    }
    # (b) CUTS identical to the umbrella harness
    wf = WF_EXTENDED.read_text()
    m3 = re.search(r"CUTS\s*=\s*(\[.*?\])", wf, re.S)
    umbrella_cuts = [tuple(x) for x in ast.literal_eval(m3.group(1))]
    out["cuts_match_umbrella_wf_extended"] = umbrella_cuts == CUTS
    # (c) single shared training path for both arms in their script
    out["single_train_fn_both_arms"] = bool(
        their_src.count("def _train_predict") == 1
        and "for arm_name, tickers in arms.items()" in their_src)
    # (d) feature audit: 158 features, none forward-looking by name
    fwd_like = [c for c in feat_cols if re.search(r"fwd|forward|future|label", c, re.I)]
    out["feature_audit"] = {
        "n_features": len(feat_cols),
        "forward_looking_feature_names": fwd_like,
    }
    return out


# ---------------------------------------------------------------------------
def main() -> None:
    t0 = time.time()
    results: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "verifies": "PR #261 M8 cluster wave-1 NO-GO "
                    "(doc/research/2026-07-03-m8-cluster-wave1.md)",
        "independent_implementation": (
            "IC via pandas ranks + np.corrcoef; groups via groupby(date).size(); "
            "sort by (date,ticker); zero-std guard instead of +1e-9 — written "
            "without reusing scripts/m8_cluster_wave1.py code"
        ),
    }

    log.info("check 2: arithmetic from committed evidence")
    results["check2_arithmetic"] = check_arithmetic()

    log.info("loading dataset (read-only): %s", DATASET)
    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])
    feat_cols = [c for c in df.columns if c not in NON_FEATURE_COLS]
    assert len(feat_cols) == 158, f"expected 158 features, got {len(feat_cols)}"

    watchlist = set(json.loads(STRATEGY_CFG.read_text())["watchlist"])
    tickers = set(df["ticker"].unique())
    inc = sorted(tickers & watchlist)
    candidates = tickers - watchlist
    sel = json.loads((THEIR_EVIDENCE / "m8_wave1_selection.json").read_text())
    wave = [w["ticker"] for w in sel["wave1"]]
    assert len(inc) == 133, f"incumbents changed: {len(inc)} != 133"
    assert not set(wave) & set(inc), "wave overlaps incumbents"
    row_counts = df.groupby("ticker").size()
    eligible = sorted(t for t in candidates if row_counts.get(t, 0) >= 756)
    results["universe"] = {
        "n_incumbents": len(inc), "n_candidates": len(candidates),
        "n_wave": len(wave), "n_eligible_candidates": len(eligible),
    }

    log.info("check 4: coverage + topology")
    results["check4_coverage"] = check_coverage(
        df, wave, candidates, results["check2_arithmetic"])

    log.info("check 5: harness parity")
    results["check5_parity"] = check_parity(feat_cols)

    log.info("check 1: independent dilution retrains (cuts %s, seeds %s)",
             RETRAIN_CUTS, RETRAIN_SEEDS)
    results["check1_dilution"] = check_dilution(df, feat_cols, inc, wave, eligible)

    log.info("diagnostic: rerun of their exact implementation (cuts 5, 7)")
    results["their_impl_reproduction"] = check_their_impl_repro(df, feat_cols, inc)

    results["runtime_seconds"] = round(time.time() - t0, 1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "verification_results.json"
    out_path.write_text(json.dumps(results, indent=2) + "\n")
    log.info("wrote %s (%.0fs)", out_path, results["runtime_seconds"])


if __name__ == "__main__":
    main()
