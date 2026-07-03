#!/usr/bin/env python
"""M8 cluster wave-1 breadth expansion — frozen-spec selection + paired WF gate.

Master-plan row M8 (doc/design/2026-07-02-unified-107-master-plan.md, Term BR):
cluster-based admission of ~100 quality names per E34's resume condition
(umbrella doc/research/failed-experiments-log.md E34), paired walk-forward
per wave, halt on degradation. AC (FROZEN, may not be altered): wave-1 paired
walk-forward IC must be >= baseline within a pre-registered noise band — else
the wave is a recorded NO-GO and waves STOP (BR then comes only via D3
down-cap).

Read-only on all production data. Everything this script writes goes to
doc/research/evidence/2026-07-03-m8/ inside this repo.

Stages (run in this order; `freeze` is committed BEFORE `select`/`evaluate`
are run so the criterion and gate are pre-registered):

    python scripts/m8_cluster_wave1.py freeze     # write frozen spec JSON
    python scripts/m8_cluster_wave1.py select     # stage A: wave-1 selection
    python scripts/m8_cluster_wave1.py evaluate   # stage B: paired WF (slow)
    python scripts/m8_cluster_wave1.py verdict    # apply frozen gate

Requires the umbrella venv (xgboost): /Users/renhao/git/github/RenQuant/.venv
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("m8")

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "doc" / "research" / "evidence" / "2026-07-03-m8"

# ---- read-only production inputs (absolute paths; never written) ----------
DATASET = Path("/Users/renhao/git/github/RenQuant/data/alpha158_816_dataset.parquet")
STRATEGY_CFG = Path(
    "/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json"
)
R1K_SECTORS = Path(
    "/Users/renhao/git/github/RenQuant/scripts/"
    "strategy_config.russell_1000_universe.with_sectors.json"
)
# Committed in this repo (PR #244 evidence); used for DIAGNOSTIC per-regime
# cuts only — inherits the C3 substrate caveats (not point-in-time).
REGIME_SERIES = (
    REPO / "doc" / "research" / "evidence" / "2026-07-02-c3" / "c3_regime_series.json"
)

# ---- E35 harness constants (scripts/walk_forward_extended.py, umbrella) ---
CUTS = [
    ("2016-01-01", "2018-12-31", "2019-02-01", "2019-12-31"),
    ("2017-01-01", "2019-12-31", "2020-02-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-02-01", "2021-12-31"),
    ("2019-01-01", "2021-12-31", "2022-02-01", "2022-12-31"),
    ("2020-01-01", "2022-12-31", "2023-02-01", "2023-12-31"),
    ("2021-01-01", "2023-12-31", "2024-02-01", "2024-12-31"),
    ("2022-01-01", "2024-12-31", "2025-02-01", "2025-12-31"),
]

# Production XGB params — renquant-model panel_trainer.PANEL_LTR_PARAMS +
# DEFAULT_N_ROUNDS (byte-identical values).
XGB_PARAMS = {
    "objective": "rank:pairwise",
    "eta": 0.05,
    "max_depth": 5,
    "min_child_weight": 50,
    "subsample": 0.7,
    "colsample_bytree": 0.7,
    "verbosity": 0,
    "seed": 42,
    "nthread": 8,
}
N_ROUNDS = 100

NON_FEATURE_COLS = {
    "ticker",
    "date",
    "split_label",
    "fwd_5d_excess",
    "fwd_20d_excess",
    "fwd_60d_excess",
}

FROZEN_SPEC = {
    "spec_version": 1,
    "task": (
        "M8 cluster wave-1 (+~100 quality names, E34 resume condition) — "
        "research measurement only; no watchlist/config change (D-gate)"
    ),
    "candidate_pool": {
        "source": "RenQuant/data/alpha158_816_dataset.parquet (E34 R1K screen, built 2026-05-07)",
        "rule": (
            "816 dataset tickers MINUS current strategy_config.json watchlist "
            "(145 entries incl. SPY/sector-ETFs/ADRs; 133 equity incumbents are "
            "in the dataset and form the baseline arm)"
        ),
        "eligibility": [
            ">=756 dataset rows (~3y trading days; E34 short-history exclusion)",
            ">=26 weekly dates inside the similarity window",
            ">=2 same-GICS-sector incumbents (structure-similarity undefined otherwise)",
        ],
    },
    "selection_criterion": {
        "name": "outcome-free feature-rank-structure similarity to incumbent sector peers",
        "definition": (
            "On every 5th trading date d in the similarity window, rank all "
            "dataset tickers cross-sectionally (percentile) on each of the 158 "
            "alpha158 features. similarity(c,i) = mean over shared dates of the "
            "Pearson correlation between candidate c's and incumbent i's "
            "158-dim feature-rank vectors at d. Candidate score S(c) = mean of "
            "similarity(c,i) over incumbents i in c's GICS sector. Higher = "
            "occupies/moves through the same feature-space region as the "
            "incumbent book — the direct operationalization of E34's lesson "
            "that breadth only adds when tickers share the signal structure."
        ),
        "similarity_window": ["2023-01-01", "2024-12-31"],
        "sector_taxonomy": (
            "GICS-short from RenQuant/scripts/strategy_config."
            "russell_1000_universe.with_sectors.json (covers all 816)"
        ),
        "uses_no_outcome_data": True,
        "interpretation_window_overlap": (
            "The similarity window overlaps evaluation test windows IN TIME, "
            "but the criterion reads features only — never forward returns — "
            "so it cannot select on evaluation-window IC luck "
            "(no selection-on-outcome by construction)."
        ),
        "rejected_alternative": (
            "per-ticker single-factor IC on a selection window strictly "
            "disjoint from the evaluation span — REJECTED: 512/683 candidates "
            "start 2021-05-03 (5y OHLCV fetch-window artifact), so no window "
            "with adequate candidate coverage is disjoint from the 2019-2025 "
            "evaluation span; selecting on any in-span outcome would be "
            "selection-on-outcome."
        ),
    },
    "wave1": {
        "size": 100,
        "allocation": (
            "slots across GICS sectors proportional to the incumbent GICS mix "
            "(largest-remainder rounding, ties by sector name asc); within each "
            "sector take top-S(c) candidates (ties by ticker asc); sectors with "
            "fewer eligible candidates than slots release the remainder to the "
            "global S(c) ranking"
        ),
    },
    "evaluation": {
        "harness": (
            "E35-style 7-cut walk-forward (identical CUTS constants to umbrella "
            "scripts/walk_forward_extended.py), XGB rank:pairwise with "
            "production params (eta 0.05, depth 5, min_child_weight 50, "
            "subsample 0.7, colsample 0.7, seed 42, 100 rounds), train-window "
            "z-normalization clipped to +-5, train labels clipped to +-5"
        ),
        "labels": {
            "primary": "fwd_60d_excess (production label, panel_trainer.DEFAULT_LABEL)",
            "secondary": "fwd_20d_excess (diagnostic consistency check, not gated)",
        },
        "arms": {
            "baseline": "133 incumbents present in the dataset",
            "augmented": "baseline + wave-1 (same rows, same features, same cuts)",
        },
        "metric": (
            "per-test-date cross-sectional Spearman rank IC over the arm's full "
            "universe (dates with >=5 names), mean per cut — the breadth thesis "
            "requires the EXPANDED universe to rank as well as the base one"
        ),
        "qualifying_cut_rule": (
            "a cut qualifies iff >=50% of wave-1 names have >=252 train rows "
            "AND >=100 test rows in it; the gate reads ONLY qualifying cuts "
            "(the 5y fetch-window artifact leaves cuts with near-zero wave "
            "membership, where the paired delta is 0 by construction and would "
            "dilute the gate); minimum 3 qualifying cuts else INFEASIBLE"
        ),
        "placebo": (
            "within-date label shuffle (rng seed 42) on the TRAIN window, both "
            "arms, qualifying cuts only; placebo-clean IC = real - placebo "
            "(house rule: trust placebo-clean differences, embargo floor "
            "~+0.04 on fwd_60d is common to both arms)"
        ),
    },
    "gate": {
        "statement": (
            "PASS iff mean over qualifying cuts of "
            "[IC_augmented(cut) - IC_baseline(cut)] >= -0.010 on fwd_60d_excess"
        ),
        "noise_band": 0.010,
        "noise_band_basis": (
            "the corpus's established paired-comparison materiality threshold "
            "(E36 verdict used |delta| 0.01 on the same 7-cut harness)"
        ),
        "integrity_downgrade": (
            "if the raw gate passes but the placebo-clean mean paired delta "
            "< -0.010, verdict is INCONCLUSIVE, not PASS (the downgrade can "
            "never rescue a failed raw gate)"
        ),
        "no_go_consequence": (
            "recorded NO-GO; waves STOP; BR then comes only via D3 down-cap "
            "(master-plan Plan B) — not re-argued"
        ),
    },
    "diagnostics_only_not_gated": [
        "all-7-cut mean paired delta",
        "incumbent-subset IC under the augmented model (book-degradation view)",
        "per-regime paired deltas via the committed C3 regime series (exploratory; inherits C3 substrate caveats — labels are NOT point-in-time)",
        "fwd_20d_excess secondary label",
        "date-level pooled paired delta with naive SE (autocorrelation-biased; labeled as such)",
    ],
    "caveats": [
        "survivorship: the 816 pool is May-2026 R1K membership projected back to 2016 — inflates BOTH arms' absolute IC; the paired difference partially controls for it but wave-1 candidates are the more survivorship-exposed set",
        "546/816 candidates have short history (512 start exactly 2021-05-03, a 5y fetch-window artifact, not IPO dates) — handled by the >=756-row exclusion + qualifying-cut rule",
        "costs not modeled at this stage — IC-level gate only, per the master-plan M8 row",
        "features are alpha158-only (the 816 dataset has no fundamentals); production scorer uses alpha158+fund — the gate reads the paired delta under identical featurization, not absolute production IC",
        "absolute IC levels carry the ~+0.04 embargo-leakage floor (house rule); only the paired same-cut differences are trusted",
    ],
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _load_universe() -> tuple[set[str], set[str], dict[str, str]]:
    """Return (incumbents_in_dataset, candidates, gics_map)."""
    cfg = json.loads(STRATEGY_CFG.read_text())
    watchlist = set(cfg["watchlist"])
    gics = json.loads(R1K_SECTORS.read_text())["sector_map"]
    tickers = set(
        pd.read_parquet(DATASET, columns=["ticker"])["ticker"].unique()
    )
    incumbents = tickers & watchlist
    candidates = tickers - watchlist
    return incumbents, candidates, gics


def _feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLS]


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")
    log.info("wrote %s", path)


# --------------------------------------------------------------------------
# stage: freeze
# --------------------------------------------------------------------------
def cmd_freeze(_args) -> None:
    spec = dict(FROZEN_SPEC)
    spec["frozen_utc"] = datetime.now(timezone.utc).isoformat()
    _write(EVIDENCE / "m8_frozen_spec.json", spec)


# --------------------------------------------------------------------------
# stage A: select
# --------------------------------------------------------------------------
def cmd_select(_args) -> None:
    spec = json.loads((EVIDENCE / "m8_frozen_spec.json").read_text())
    win_lo, win_hi = spec["selection_criterion"]["similarity_window"]
    wave_size = spec["wave1"]["size"]

    incumbents, candidates, gics = _load_universe()
    log.info("incumbents=%d candidates=%d", len(incumbents), len(candidates))

    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])
    feat_cols = _feature_cols(df)
    assert len(feat_cols) == 158, f"expected 158 features, got {len(feat_cols)}"

    # eligibility: >=756 rows overall
    row_counts = df.groupby("ticker").size()
    eligible = {t for t in candidates if row_counts.get(t, 0) >= 756}
    dropped_short = sorted(candidates - eligible)

    # similarity window, every 5th trading date
    win = df[(df["date"] >= win_lo) & (df["date"] <= win_hi)]
    all_dates = np.sort(win["date"].unique())
    sim_dates = all_dates[::5]
    log.info("similarity dates: %d (of %d)", len(sim_dates), len(all_dates))

    inc_sorted = sorted(incumbents)
    cand_sorted = sorted(eligible)
    inc_idx = {t: i for i, t in enumerate(inc_sorted)}
    cand_idx = {t: i for i, t in enumerate(cand_sorted)}

    sum_corr = np.zeros((len(cand_sorted), len(inc_sorted)))
    n_dates = np.zeros((len(cand_sorted), len(inc_sorted)))

    win = win[win["date"].isin(sim_dates)]
    for d, g in win.groupby("date"):
        g = g.drop_duplicates(subset="ticker").set_index("ticker")
        ranks = g[feat_cols].rank(pct=True).to_numpy(dtype=np.float64)
        # standardize each ticker's 158-dim rank vector (row-wise) for Pearson
        with np.errstate(all="ignore"):
            mu = np.nanmean(ranks, axis=1, keepdims=True)
            sd = np.nanstd(ranks, axis=1, keepdims=True) + 1e-12
            z = (ranks - mu) / sd
        z[~np.isfinite(z)] = 0.0
        k = z.shape[1]
        tickers_here = list(g.index)
        c_rows = [i for i, t in enumerate(tickers_here) if t in cand_idx]
        i_rows = [i for i, t in enumerate(tickers_here) if t in inc_idx]
        if not c_rows or not i_rows:
            continue
        corr = z[c_rows] @ z[i_rows].T / k
        ci = [cand_idx[tickers_here[i]] for i in c_rows]
        ii = [inc_idx[tickers_here[i]] for i in i_rows]
        sum_corr[np.ix_(ci, ii)] += corr
        n_dates[np.ix_(ci, ii)] += 1

    with np.errstate(invalid="ignore"):
        mean_corr = np.where(n_dates > 0, sum_corr / np.maximum(n_dates, 1), np.nan)

    # per-candidate score = mean similarity to same-GICS-sector incumbents
    min_dates = 26
    inc_by_sector: dict[str, list[int]] = {}
    for t in inc_sorted:
        inc_by_sector.setdefault(gics.get(t, "unknown"), []).append(inc_idx[t])

    scores = {}
    dropped_no_peers, dropped_thin = [], []
    for t in cand_sorted:
        sec = gics.get(t, "unknown")
        peers = inc_by_sector.get(sec, [])
        if len(peers) < 2:
            dropped_no_peers.append(t)
            continue
        row = mean_corr[cand_idx[t], peers]
        cnt = n_dates[cand_idx[t], peers]
        ok = cnt >= min_dates
        if not ok.any():
            dropped_thin.append(t)
            continue
        scores[t] = float(np.nanmean(row[ok]))

    # sector allocation proportional to incumbent GICS mix, largest remainder
    inc_mix = pd.Series({s: len(v) for s, v in inc_by_sector.items()})
    inc_mix = inc_mix / inc_mix.sum()
    raw = inc_mix * wave_size
    slots = raw.astype(int)
    remainder = raw - slots
    order = sorted(remainder.index, key=lambda s: (-remainder[s], s))
    for s in order:
        if slots.sum() >= wave_size:
            break
        slots[s] += 1

    by_sector: dict[str, list[tuple[float, str]]] = {}
    for t, sc in scores.items():
        by_sector.setdefault(gics.get(t, "unknown"), []).append((sc, t))
    for s in by_sector:
        by_sector[s].sort(key=lambda x: (-x[0], x[1]))

    wave, released = [], 0
    for s, k in slots.items():
        pool = by_sector.get(s, [])
        take = pool[: int(k)]
        wave.extend(t for _, t in take)
        released += int(k) - len(take)
    if released > 0:
        chosen = set(wave)
        global_rank = sorted(
            ((sc, t) for t, sc in scores.items() if t not in chosen),
            key=lambda x: (-x[0], x[1]),
        )
        wave.extend(t for _, t in global_rank[:released])

    wave = sorted(wave)
    sector_counts = pd.Series([gics.get(t, "unknown") for t in wave]).value_counts()

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_incumbents_in_dataset": len(incumbents),
        "n_candidates_raw": len(candidates),
        "n_dropped_short_history": len(dropped_short),
        "n_dropped_no_sector_peers": len(dropped_no_peers),
        "dropped_no_sector_peers": dropped_no_peers,
        "n_dropped_thin_similarity": len(dropped_thin),
        "n_scored": len(scores),
        "n_similarity_dates": int(len(sim_dates)),
        "incumbent_gics_mix": {s: int(len(v)) for s, v in inc_by_sector.items()},
        "sector_slots": {s: int(k) for s, k in slots.items()},
        "slots_released_to_global_rank": released,
        "wave1_sector_counts": sector_counts.to_dict(),
        "wave1": [
            {"ticker": t, "gics": gics.get(t, "unknown"), "similarity": round(scores[t], 6)}
            for t in wave
        ],
        "score_distribution_all_candidates": {
            "min": round(min(scores.values()), 4),
            "p25": round(float(np.percentile(list(scores.values()), 25)), 4),
            "median": round(float(np.median(list(scores.values()))), 4),
            "p75": round(float(np.percentile(list(scores.values()), 75)), 4),
            "max": round(max(scores.values()), 4),
        },
    }
    _write(EVIDENCE / "m8_wave1_selection.json", out)
    log.info(
        "wave-1: %d names, sectors: %s", len(wave), dict(sector_counts)
    )


# --------------------------------------------------------------------------
# stage B: evaluate
# --------------------------------------------------------------------------
def _per_date_ic(pred, actual, dates, subset_mask=None) -> dict[str, float]:
    df = pd.DataFrame({"p": pred, "y": actual, "date": dates})
    if subset_mask is not None:
        df = df[subset_mask]
    out = {}
    for d, g in df.groupby("date"):
        if len(g) < 5:
            continue
        ic, _ = spearmanr(g["p"], g["y"])
        if not np.isnan(ic):
            out[str(pd.Timestamp(d).date())] = float(ic)
    return out


def _train_predict(train, test, feat_cols, label, shuffle_labels=False):
    import xgboost as xgb  # local import: umbrella venv only needed here

    y_tr = train[label].clip(-5, 5).to_numpy(dtype=np.float64)
    if shuffle_labels:
        rng = np.random.default_rng(42)
        y_tr = y_tr.copy()
        codes = pd.factorize(train["date"].to_numpy())[0]
        for d in np.unique(codes):
            m = codes == d
            y_tr[m] = rng.permutation(y_tr[m])
    X_tr = train[feat_cols].fillna(0).to_numpy(dtype=np.float64)
    X_te = test[feat_cols].fillna(0).to_numpy(dtype=np.float64)
    mu, sd = X_tr.mean(axis=0), X_tr.std(axis=0) + 1e-9
    X_tr = ((X_tr - mu) / sd).clip(-5, 5)
    X_te = ((X_te - mu) / sd).clip(-5, 5)

    dates_tr = train["date"].to_numpy()
    order = np.argsort(dates_tr, kind="stable")
    _, gsz = np.unique(dates_tr[order], return_counts=True)
    dtr = xgb.DMatrix(X_tr[order], label=y_tr[order])
    dtr.set_group(gsz)
    booster = xgb.train(XGB_PARAMS, dtr, num_boost_round=N_ROUNDS)
    return booster.predict(xgb.DMatrix(X_te))


def cmd_evaluate(_args) -> None:
    spec = json.loads((EVIDENCE / "m8_frozen_spec.json").read_text())
    sel = json.loads((EVIDENCE / "m8_wave1_selection.json").read_text())
    wave = [w["ticker"] for w in sel["wave1"]]
    incumbents, _, _ = _load_universe()
    inc = sorted(incumbents)
    aug = sorted(set(inc) | set(wave))
    log.info("baseline arm=%d augmented arm=%d (wave=%d)", len(inc), len(aug), len(wave))

    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])
    feat_cols = _feature_cols(df)

    # qualifying cuts (frozen rule): >=50% of wave names with >=252 train rows
    # and >=100 test rows
    wave_df = df[df["ticker"].isin(wave)]
    qualifying = []
    cut_coverage = []
    for i, (a, b, c, d) in enumerate(CUTS, 1):
        tr = wave_df[(wave_df["date"] >= a) & (wave_df["date"] <= b)].groupby("ticker").size()
        te = wave_df[(wave_df["date"] >= c) & (wave_df["date"] <= d)].groupby("ticker").size()
        n_ok = len(set(tr[tr >= 252].index) & set(te[te >= 100].index))
        frac = n_ok / len(wave)
        cut_coverage.append({"cut": i, "wave_names_covered": n_ok, "fraction": round(frac, 4)})
        if frac >= 0.5:
            qualifying.append(i)
    log.info("qualifying cuts: %s", qualifying)

    results = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "arms": {"baseline_n": len(inc), "augmented_n": len(aug)},
        "cut_wave_coverage": cut_coverage,
        "qualifying_cuts": qualifying,
        "runs": [],
        "runtime_seconds": {},
    }
    out_path = EVIDENCE / "m8_paired_wf_results.json"
    per_date_path = EVIDENCE / "m8_per_date_ics.json"
    per_date_store: dict[str, dict] = {}

    arms = {"baseline": inc, "augmented": aug}
    labels = [spec["evaluation"]["labels"]["primary"].split(" ")[0],
              spec["evaluation"]["labels"]["secondary"].split(" ")[0]]

    t_total = time.time()
    for label in labels:
        for arm_name, tickers in arms.items():
            arm_df = df[df["ticker"].isin(tickers)]
            for i, cut in enumerate(CUTS, 1):
                a, b, c, d = cut
                train = arm_df[(arm_df["date"] >= a) & (arm_df["date"] <= b)].dropna(subset=[label])
                test = arm_df[(arm_df["date"] >= c) & (arm_df["date"] <= d)].dropna(subset=[label])
                if len(train) < 1000 or len(test) < 100:
                    continue
                for placebo in ([False, True] if i in qualifying else [False]):
                    t0 = time.time()
                    pred = _train_predict(train, test, feat_cols, label, shuffle_labels=placebo)
                    ics = _per_date_ic(pred, test[label].to_numpy(), test["date"].to_numpy())
                    rec = {
                        "label": label,
                        "arm": arm_name,
                        "cut": i,
                        "placebo": placebo,
                        "n_train": int(len(train)),
                        "n_test": int(len(test)),
                        "ic_mean": round(float(np.mean(list(ics.values()))), 6),
                        "n_test_dates": len(ics),
                        "seconds": round(time.time() - t0, 1),
                    }
                    # diagnostic: incumbent-subset IC under the augmented model
                    if arm_name == "augmented" and not placebo:
                        mask = test["ticker"].isin(inc).to_numpy()
                        sub = _per_date_ic(pred, test[label].to_numpy(), test["date"].to_numpy(), mask)
                        rec["ic_mean_incumbent_subset"] = round(float(np.mean(list(sub.values()))), 6)
                    results["runs"].append(rec)
                    key = f"{label}|{arm_name}|cut{i}|{'placebo' if placebo else 'real'}"
                    per_date_store[key] = ics
                    log.info("%s ic=%+.4f (%.0fs)", key, rec["ic_mean"], rec["seconds"])
                    # incremental persistence — partial progress survives
                    results["runtime_seconds"]["total_so_far"] = round(time.time() - t_total, 1)
                    _write(out_path, results)
    _write(per_date_path, per_date_store)
    results["runtime_seconds"]["total"] = round(time.time() - t_total, 1)
    _write(out_path, results)


# --------------------------------------------------------------------------
# stage: verdict
# --------------------------------------------------------------------------
def cmd_verdict(_args) -> None:
    spec = json.loads((EVIDENCE / "m8_frozen_spec.json").read_text())
    res = json.loads((EVIDENCE / "m8_paired_wf_results.json").read_text())
    per_date = json.loads((EVIDENCE / "m8_per_date_ics.json").read_text())
    band = spec["gate"]["noise_band"]
    qual = res["qualifying_cuts"]
    primary = "fwd_60d_excess"

    def ic(label, arm, cut, placebo=False):
        for r in res["runs"]:
            if (r["label"], r["arm"], r["cut"], r["placebo"]) == (label, arm, cut, placebo):
                return r["ic_mean"]
        return None

    verdict: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                     "qualifying_cuts": qual, "noise_band": band}

    if len(qual) < 3:
        verdict["verdict"] = "INFEASIBLE"
        verdict["reason"] = "fewer than 3 qualifying cuts (frozen minimum)"
        _write(EVIDENCE / "m8_verdict.json", verdict)
        return

    for label in ["fwd_60d_excess", "fwd_20d_excess"]:
        deltas_all, deltas_qual, rows = [], [], []
        for i in range(1, len(CUTS) + 1):
            b_, a_ = ic(label, "baseline", i), ic(label, "augmented", i)
            if b_ is None or a_ is None:
                continue
            dlt = a_ - b_
            deltas_all.append(dlt)
            if i in qual:
                deltas_qual.append(dlt)
            rows.append({"cut": i, "baseline_ic": b_, "augmented_ic": a_,
                         "delta": round(dlt, 6), "qualifying": i in qual})
        pc_deltas = []
        for i in qual:
            rb, ra = ic(label, "baseline", i), ic(label, "augmented", i)
            pb, pa = ic(label, "baseline", i, True), ic(label, "augmented", i, True)
            if None in (rb, ra, pb, pa):
                continue
            pc_deltas.append((ra - pa) - (rb - pb))
        verdict[label] = {
            "per_cut": rows,
            "mean_delta_qualifying": round(float(np.mean(deltas_qual)), 6),
            "mean_delta_all_cuts": round(float(np.mean(deltas_all)), 6),
            "placebo_clean_mean_delta_qualifying": (
                round(float(np.mean(pc_deltas)), 6) if pc_deltas else None
            ),
            "wins_qualifying": sum(1 for x in deltas_qual if x > 0),
            "n_qualifying": len(deltas_qual),
        }

    g = verdict[primary]
    raw_pass = g["mean_delta_qualifying"] >= -band
    pc = g["placebo_clean_mean_delta_qualifying"]
    if not raw_pass:
        verdict["verdict"] = "NO-GO"
        verdict["reason"] = (
            f"frozen gate FAILED: mean paired delta over qualifying cuts "
            f"{g['mean_delta_qualifying']:+.4f} < -{band} on {primary}; "
            f"waves STOP (BR via D3 down-cap only)"
        )
    elif pc is not None and pc < -band:
        verdict["verdict"] = "INCONCLUSIVE"
        verdict["reason"] = (
            f"raw gate passed ({g['mean_delta_qualifying']:+.4f} >= -{band}) but "
            f"placebo-clean paired delta {pc:+.4f} < -{band} (frozen integrity downgrade)"
        )
    else:
        verdict["verdict"] = "PASS"
        verdict["reason"] = (
            f"mean paired delta over qualifying cuts {g['mean_delta_qualifying']:+.4f} "
            f">= -{band} on {primary}; placebo-clean delta "
            f"{pc if pc is not None else 'n/a'} consistent"
        )

    # diagnostics: date-level pooled delta + per-regime cuts (exploratory)
    regime_map = {}
    if REGIME_SERIES.exists():
        for r in json.loads(REGIME_SERIES.read_text()):
            regime_map[str(pd.Timestamp(r["date"]).date())] = r["regime"]
    diag = {}
    for label in ["fwd_60d_excess", "fwd_20d_excess"]:
        pooled, by_regime = [], {}
        for i in qual:
            kb = f"{label}|baseline|cut{i}|real"
            ka = f"{label}|augmented|cut{i}|real"
            if kb not in per_date or ka not in per_date:
                continue
            common = set(per_date[kb]) & set(per_date[ka])
            for d in sorted(common):
                dlt = per_date[ka][d] - per_date[kb][d]
                pooled.append(dlt)
                reg = regime_map.get(d, "UNKNOWN")
                by_regime.setdefault(reg, []).append(dlt)
        if pooled:
            diag[label] = {
                "pooled_date_level_mean_delta": round(float(np.mean(pooled)), 6),
                "pooled_date_level_naive_se": round(
                    float(np.std(pooled) / np.sqrt(len(pooled))), 6
                ),
                "naive_se_caveat": "iid SE; fwd-label overlap autocorrelation biases it low",
                "n_dates": len(pooled),
                "per_regime_mean_delta_EXPLORATORY": {
                    k: {"mean_delta": round(float(np.mean(v)), 6), "n_dates": len(v)}
                    for k, v in sorted(by_regime.items())
                },
            }
    verdict["diagnostics"] = diag
    _write(EVIDENCE / "m8_verdict.json", verdict)
    log.info("VERDICT: %s — %s", verdict["verdict"], verdict["reason"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("freeze", cmd_freeze), ("select", cmd_select),
                     ("evaluate", cmd_evaluate), ("verdict", cmd_verdict)]:
        sub.add_parser(name).set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
