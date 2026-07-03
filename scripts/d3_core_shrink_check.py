#!/usr/bin/env python
"""D3 incumbent-book core-shrink check — frozen-spec execution.

The measurement RS-5 (#282) explicitly deferred to the D3 memo: does shrinking
the incumbent panel to a high-separability core improve the CORE'S OWN realized
pick quality (mirror image of M8's verified dilution finding, #261/#264)?

FROZEN SPEC (committed BEFORE any measurement — commit 1 of this branch):
    doc/research/evidence/2026-07-03-d3-core-shrink/frozen_spec.json
This script implements it verbatim; any deviation must be disclosed in the memo.

Read-only on all production data. Everything written goes to the evidence dir
inside this repo. Stages (in order):

    python scripts/d3_core_shrink_check.py select    # cores (LIQ/SEP/SECBAL/…)
    python scripts/d3_core_shrink_check.py evaluate  # WF arm (slow, ~400 XGB fits)
    python scripts/d3_core_shrink_check.py s8        # pick-table supporting arm
    python scripts/d3_core_shrink_check.py verdict   # frozen gates + controls
    python scripts/d3_core_shrink_check.py all

Requires the umbrella venv (xgboost): /Users/renhao/git/github/RenQuant/.venv
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("d3core")

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "doc" / "research" / "evidence" / "2026-07-03-d3-core-shrink"

# ---- read-only production inputs (absolute paths; never written) ----------
DATASET = Path("/Users/renhao/git/github/RenQuant/data/alpha158_816_dataset.parquet")
STRATEGY_CFG = Path(
    "/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json"
)
R1K_SECTORS = Path(
    "/Users/renhao/git/github/RenQuant/scripts/"
    "strategy_config.russell_1000_universe.with_sectors.json"
)
PICK_TABLE = Path(
    "/Users/renhao/git/github/RenQuant/data/exp/oos_pick_table_recipe_v2.parquet"
)
RAWLABEL = Path(
    "/Users/renhao/git/github/RenQuant/data/"
    "alpha158_291_fundamental_dataset_rawlabel.parquet"
)
BAR_STORE = Path("/Users/renhao/git/github/RenQuant/data/ohlcv")
REGIME_SERIES = (
    REPO / "doc" / "research" / "evidence" / "2026-07-02-c3" / "c3_regime_series.json"
)

# ---- E35 harness constants (byte-identical to M8 / walk_forward_extended) -
CUTS = [
    ("2016-01-01", "2018-12-31", "2019-02-01", "2019-12-31"),
    ("2017-01-01", "2019-12-31", "2020-02-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-02-01", "2021-12-31"),
    ("2019-01-01", "2021-12-31", "2022-02-01", "2022-12-31"),
    ("2020-01-01", "2022-12-31", "2023-02-01", "2023-12-31"),
    ("2021-01-01", "2023-12-31", "2024-02-01", "2024-12-31"),
    ("2022-01-01", "2024-12-31", "2025-02-01", "2025-12-31"),
]
XGB_BASE_PARAMS = {
    "objective": "rank:pairwise",
    "eta": 0.05,
    "max_depth": 5,
    "min_child_weight": 50,
    "subsample": 0.7,
    "colsample_bytree": 0.7,
    "verbosity": 0,
    "nthread": 8,
}
N_ROUNDS = 100
NON_FEATURE_COLS = {
    "ticker", "date", "split_label",
    "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess",
}
PRIMARY_LABEL = "fwd_60d_excess"
SECONDARY_LABEL = "fwd_20d_excess"

# ---- frozen-spec constants -------------------------------------------------
TRAIN_SEEDS = [42, 43, 44]
NULL_OFFSET = 100                      # null baselines at seeds 142/143/144
CORE_SIZES = [60, 90]
CORE_DEFS = ["LIQ", "SEP", "SECBAL"]
MATERIALITY = 0.010                    # E36/M8 band
ALPHA_ONE_SIDED = 0.05 / 12            # Bonferroni: 6 members x 2 directions
BLOCK = 60
N_BOOT = 2000
MIN_NAMES_PER_DATE = 5                 # M8 floor
QUALIFYING_FRAC = 0.5                  # M8 rule applied to the core
MIN_QUALIFYING_CUTS = 3
SEP_TRAIN = ("2016-01-01", "2017-06-30")
SEP_SCORE = ("2017-08-01", "2018-09-30")
SEP_MIN_DATES = 126
LIQ_WINDOW = ("2016-01-04", "2026-05-08")
PLANT_MEMBER = "SEP-60"
PLANT_LABEL_WEIGHT = 0.10
S8_BAR = 0.0005                        # 5 bps / 60d (S9 (b)-bar magnitude)
S8_BOOT_SEEDS = [42, 43, 44]
RANDOM_CORE_SEED_BASE = 4200
RANDOM_DRAWS = [1, 2, 3]
ETFS = {"SPY", "XLE", "XLF", "XLI", "XLK", "XLU", "XLY"}

MEMBERS = [f"{d}-{n}" for d in CORE_DEFS for n in CORE_SIZES]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")
    log.info("wrote %s", path)


def _write_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(obj, f, default=str)
    log.info("wrote %s", path)


def _read_gz(path: Path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_incumbents() -> tuple[list[str], dict[str, str]]:
    cfg = json.loads(STRATEGY_CFG.read_text())
    watchlist = set(cfg["watchlist"])
    gics = json.loads(R1K_SECTORS.read_text())["sector_map"]
    tickers = set(pd.read_parquet(DATASET, columns=["ticker"])["ticker"].unique())
    return sorted(tickers & watchlist), gics


def _load_dataset(tickers: list[str]) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["ticker"].isin(tickers)].copy()
    feat_cols = [c for c in df.columns if c not in NON_FEATURE_COLS]
    assert len(feat_cols) == 158, f"expected 158 features, got {len(feat_cols)}"
    return df, feat_cols


def _train_predict(train, test, feat_cols, label, seed, shuffle_labels=False):
    """M8 _train_predict verbatim, with the training seed as a parameter."""
    import xgboost as xgb  # local import: umbrella venv only needed here

    y_tr = train[label].clip(-5, 5).to_numpy(dtype=np.float64)
    if shuffle_labels:
        rng = np.random.default_rng(seed)
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
    params = dict(XGB_BASE_PARAMS, seed=seed)
    booster = xgb.train(params, dtr, num_boost_round=N_ROUNDS)
    return booster.predict(xgb.DMatrix(X_te))


def _per_date_ic(pred, actual, dates, mask=None) -> dict[str, float]:
    df = pd.DataFrame({"p": pred, "y": actual, "date": dates})
    if mask is not None:
        df = df[mask]
    out = {}
    for d, g in df.groupby("date"):
        if len(g) < MIN_NAMES_PER_DATE:
            continue
        ic, _ = spearmanr(g["p"], g["y"])
        if not np.isnan(ic):
            out[str(pd.Timestamp(d).date())] = float(ic)
    return out


def _moving_block_bootstrap(series: np.ndarray, seed: int) -> tuple[float, float]:
    """One-sided lower/upper bounds of the mean at the frozen Bonferroni level."""
    n = len(series)
    if n < BLOCK + 1:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    k = int(np.ceil(n / BLOCK))
    starts = rng.integers(0, n - BLOCK + 1, size=(N_BOOT, k))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(N_BOOT, -1)[:, :n]
    means = series[idx].mean(axis=1)
    lb = float(np.percentile(means, 100 * ALPHA_ONE_SIDED))
    ub = float(np.percentile(means, 100 * (1 - ALPHA_ONE_SIDED)))
    return lb, ub


def _paired_delta_series(ic_a: dict, ic_b: dict) -> tuple[list[str], np.ndarray]:
    """Date-ordered Delta_t = ic_a[t] - ic_b[t] on common dates."""
    common = sorted(set(ic_a) & set(ic_b))
    return common, np.array([ic_a[d] - ic_b[d] for d in common])


# --------------------------------------------------------------------------
# stage: select
# --------------------------------------------------------------------------
def cmd_select(_args) -> None:
    spec = json.loads((EVIDENCE / "frozen_spec.json").read_text())
    incumbents, gics = _load_incumbents()
    assert len(incumbents) == spec["pre_freeze_feasibility_facts"][
        "incumbents_in_e35_dataset"
    ], "incumbent universe drifted since the freeze"
    df, feat_cols = _load_dataset(incumbents)

    out: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_incumbents": len(incumbents),
        "incumbents": incumbents,
    }

    # ---- LIQ: full-span median daily dollar volume (outcome-free) ----------
    lo, hi = LIQ_WINDOW
    adv = {}
    for t in incumbents:
        bars = pd.read_parquet(BAR_STORE / t / "1d.parquet",
                               columns=["close", "volume"]).loc[lo:hi]
        adv[t] = float((bars["close"] * bars["volume"]).median())
    liq_rank = sorted(incumbents, key=lambda t: (-adv[t], t))
    out["liq_median_dollar_volume"] = {t: round(adv[t], 2) for t in liq_rank}

    # ---- SEP: per-name |IC| on the disjoint pre-2019 window ----------------
    a, b = SEP_TRAIN
    c, d = SEP_SCORE
    train = df[(df["date"] >= a) & (df["date"] <= b)].dropna(subset=[PRIMARY_LABEL])
    score_win = df[(df["date"] >= c) & (df["date"] <= d)].dropna(subset=[PRIMARY_LABEL])
    log.info("SEP model: train rows=%d score rows=%d", len(train), len(score_win))
    pred = _train_predict(train, score_win, feat_cols, PRIMARY_LABEL, seed=42)
    sw = score_win[["ticker", "date", PRIMARY_LABEL]].copy()
    sw["pred"] = pred
    sw["p_rank"] = sw.groupby("date")["pred"].rank(pct=True)
    sw["y_rank"] = sw.groupby("date")[PRIMARY_LABEL].rank(pct=True)
    sep_ic, sep_n = {}, {}
    for t, g in sw.groupby("ticker"):
        sep_n[t] = int(len(g))
        if len(g) >= SEP_MIN_DATES:
            ic, _ = spearmanr(g["p_rank"], g["y_rank"])
            if not np.isnan(ic):
                sep_ic[t] = float(ic)
    eligible = sorted(sep_ic)
    sep_rank = sorted(eligible, key=lambda t: (-abs(sep_ic[t]), t))
    out["sep"] = {
        "n_eligible": len(eligible),
        "ineligible": sorted(set(incumbents) - set(eligible)),
        "per_name_ic": {t: round(sep_ic[t], 6) for t in sep_rank},
        "scored_dates_per_name": sep_n,
        "n_scored_dates_window": int(sw["date"].nunique()),
    }

    # ---- SECBAL: sector-balanced separability (M8 allocation verbatim) -----
    def secbal(size: int) -> list[str]:
        elig_by_sector: dict[str, list[str]] = {}
        for t in sep_rank:  # already |IC| desc, ticker asc
            elig_by_sector.setdefault(gics.get(t, "unknown"), []).append(t)
        mix = pd.Series({s: len(v) for s, v in elig_by_sector.items()}, dtype=float)
        mix = mix / mix.sum()
        raw = mix * size
        slots = raw.astype(int)
        remainder = raw - slots
        for s in sorted(remainder.index, key=lambda s: (-remainder[s], s)):
            if slots.sum() >= size:
                break
            slots[s] += 1
        core, released = [], 0
        for s, k in slots.items():
            take = elig_by_sector.get(s, [])[: int(k)]
            core.extend(take)
            released += int(k) - len(take)
        if released > 0:
            chosen = set(core)
            core.extend([t for t in sep_rank if t not in chosen][:released])
        return sorted(core)

    cores: dict[str, list[str]] = {}
    for n in CORE_SIZES:
        cores[f"LIQ-{n}"] = sorted(liq_rank[:n])
        cores[f"SEP-{n}"] = sorted(sep_rank[:n])
        cores[f"SECBAL-{n}"] = secbal(n)
        for m in (f"LIQ-{n}", f"SEP-{n}", f"SECBAL-{n}"):
            assert len(cores[m]) == n, (m, len(cores[m]))

    # ---- WF random-core diagnostics + S8 random-null cores -----------------
    random_wf: dict[str, list[str]] = {}
    for n in CORE_SIZES:
        for dr in RANDOM_DRAWS:
            rng = np.random.default_rng(RANDOM_CORE_SEED_BASE + dr)
            random_wf[f"RAND{dr}-{n}"] = sorted(
                rng.choice(np.array(incumbents), size=n, replace=False).tolist()
            )

    # S8 universes: equity incumbents in the pick table
    cfg_watchlist = set(json.loads(STRATEGY_CFG.read_text())["watchlist"])
    pt_names = set(
        pd.read_parquet(PICK_TABLE, columns=["name"])["name"].unique()
    )
    s8_full = sorted((cfg_watchlist & pt_names) - ETFS)
    random_s8: dict[str, list[str]] = {}
    for n in CORE_SIZES:
        for dr in RANDOM_DRAWS:
            rng = np.random.default_rng(RANDOM_CORE_SEED_BASE + dr)
            random_s8[f"S8RAND{dr}-{n}"] = sorted(
                rng.choice(np.array(s8_full), size=n, replace=False).tolist()
            )

    # overlap matrix (correlated-tests honesty)
    overlap = {
        m1: {m2: len(set(cores[m1]) & set(cores[m2])) for m2 in MEMBERS}
        for m1 in MEMBERS
    }

    out.update({
        "cores": cores,
        "core_gics_mix": {
            m: pd.Series([gics.get(t, "unknown") for t in v]).value_counts().to_dict()
            for m, v in cores.items()
        },
        "overlap_matrix": overlap,
        "random_wf_cores": random_wf,
        "s8_full_book": s8_full,
        "n_s8_full_book": len(s8_full),
        "random_s8_cores": random_s8,
    })
    _write(EVIDENCE / "core_selection.json", out)


# --------------------------------------------------------------------------
# stage: evaluate (WF arm)
# --------------------------------------------------------------------------
def _qualifying_cuts(df: pd.DataFrame, core: list[str]) -> tuple[list[int], list[dict]]:
    sub = df[df["ticker"].isin(core)]
    qual, cov = [], []
    for i, (a, b, c, d) in enumerate(CUTS, 1):
        tr = sub[(sub["date"] >= a) & (sub["date"] <= b)].groupby("ticker").size()
        te = sub[(sub["date"] >= c) & (sub["date"] <= d)].groupby("ticker").size()
        n_ok = len(set(tr[tr >= 252].index) & set(te[te >= 100].index))
        frac = n_ok / len(core)
        cov.append({"cut": i, "covered": n_ok, "fraction": round(frac, 4)})
        if frac >= QUALIFYING_FRAC:
            qual.append(i)
    return qual, cov


def cmd_evaluate(_args) -> None:
    sel = json.loads((EVIDENCE / "core_selection.json").read_text())
    incumbents = sel["incumbents"]
    cores: dict[str, list[str]] = sel["cores"]
    random_wf: dict[str, list[str]] = sel["random_wf_cores"]
    df, feat_cols = _load_dataset(incumbents)

    qual_map, cov_map = {}, {}
    for m, core in {**cores, **random_wf}.items():
        qual_map[m], cov_map[m] = _qualifying_cuts(df, core)
        log.info("%s qualifying cuts: %s", m, qual_map[m])

    results: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "qualifying_cuts": qual_map,
        "cut_coverage": cov_map,
        "runs": [],
    }
    per_date: dict[str, dict] = {}
    out_path = EVIDENCE / "wf_results.json"
    pd_path = EVIDENCE / "wf_per_date.json.gz"
    t_total = time.time()

    # which cuts need a placebo (union over members' qualifying cuts)
    placebo_cuts = sorted({c for m in MEMBERS for c in qual_map[m]})

    core_masks_needed = {**cores, **random_wf}
    for ci, (a, b, c, d) in enumerate(CUTS, 1):
        train = df[(df["date"] >= a) & (df["date"] <= b)].dropna(subset=[PRIMARY_LABEL])
        test = df[(df["date"] >= c) & (df["date"] <= d)].dropna(subset=[PRIMARY_LABEL])
        test_y = test[PRIMARY_LABEL].to_numpy()
        test_dates = test["date"].to_numpy()

        # -- baselines: real at 42/43/44 + null at 142/143/144; placebo at 42/43/44
        base_pred: dict[tuple[int, bool], np.ndarray] = {}
        for s in TRAIN_SEEDS + [s + NULL_OFFSET for s in TRAIN_SEEDS]:
            t0 = time.time()
            base_pred[(s, False)] = _train_predict(train, test, feat_cols,
                                                   PRIMARY_LABEL, seed=s)
            log.info("cut%d baseline seed=%d (%.0fs)", ci, s, time.time() - t0)
        for s in TRAIN_SEEDS:
            if ci in placebo_cuts:
                base_pred[(s, True)] = _train_predict(train, test, feat_cols,
                                                      PRIMARY_LABEL, seed=s,
                                                      shuffle_labels=True)

        # baseline per-date IC on the full universe (diagnostic: selection-only read)
        for s in TRAIN_SEEDS:
            per_date[f"base_full|s{s}|cut{ci}"] = _per_date_ic(
                base_pred[(s, False)], test_y, test_dates)

        # -- member cores (real + placebo at each seed) + random cores (seed 42)
        for m, core in core_masks_needed.items():
            is_member = m in MEMBERS
            if ci not in qual_map[m]:
                continue
            mask = test["ticker"].isin(core).to_numpy()
            tr_core = train[train["ticker"].isin(core)]
            te_core = test[mask]
            seeds = TRAIN_SEEDS if is_member else [42]
            for s in seeds:
                t0 = time.time()
                pred_core = _train_predict(tr_core, te_core, feat_cols,
                                           PRIMARY_LABEL, seed=s)
                ic_core = _per_date_ic(pred_core, te_core[PRIMARY_LABEL].to_numpy(),
                                       te_core["date"].to_numpy())
                ic_base_on_core = _per_date_ic(base_pred[(s, False)], test_y,
                                               test_dates, mask)
                per_date[f"{m}|core|s{s}|cut{ci}"] = ic_core
                per_date[f"{m}|base_on_core|s{s}|cut{ci}"] = ic_base_on_core
                results["runs"].append({
                    "member": m, "cut": ci, "seed": s, "kind": "real",
                    "n_train_rows": int(len(tr_core)), "n_test_rows": int(len(te_core)),
                    "core_ic_mean": round(float(np.mean(list(ic_core.values()))), 6),
                    "base_on_core_ic_mean": round(
                        float(np.mean(list(ic_base_on_core.values()))), 6),
                    "seconds": round(time.time() - t0, 1),
                })
                # null read: offset-seed baseline vs paired-seed baseline on core
                if is_member:
                    ic_null = _per_date_ic(base_pred[(s + NULL_OFFSET, False)],
                                           test_y, test_dates, mask)
                    per_date[f"{m}|null_on_core|s{s}|cut{ci}"] = ic_null
                # placebo pair
                if is_member:
                    t0 = time.time()
                    pred_pc = _train_predict(tr_core, te_core, feat_cols,
                                             PRIMARY_LABEL, seed=s,
                                             shuffle_labels=True)
                    ic_core_pc = _per_date_ic(pred_pc,
                                              te_core[PRIMARY_LABEL].to_numpy(),
                                              te_core["date"].to_numpy())
                    ic_base_pc = _per_date_ic(base_pred[(s, True)], test_y,
                                              test_dates, mask)
                    per_date[f"{m}|core_placebo|s{s}|cut{ci}"] = ic_core_pc
                    per_date[f"{m}|base_placebo_on_core|s{s}|cut{ci}"] = ic_base_pc
                log.info("cut%d %s seed=%d done (%.0fs)", ci, m, s, time.time() - t0)

        # -- positive plant on the designated member (no training needed)
        pm_core = cores[PLANT_MEMBER]
        if ci in qual_map[PLANT_MEMBER]:
            mask = test["ticker"].isin(pm_core).to_numpy()
            sub = test[mask][["ticker", "date"]].copy()
            sub["y"] = test_y[mask]
            for s in TRAIN_SEEDS:
                sub["b"] = base_pred[(s, False)][mask]
                g = sub.groupby("date")
                plant = (0.9 * g["b"].rank(pct=True)
                         + PLANT_LABEL_WEIGHT * g["y"].rank(pct=True))
                per_date[f"PLANT|core|s{s}|cut{ci}"] = _per_date_ic(
                    plant.to_numpy(), sub["y"].to_numpy(), sub["date"].to_numpy())

        results["runtime_seconds_so_far"] = round(time.time() - t_total, 1)
        _write(out_path, results)
        _write_gz(pd_path, per_date)

    # -- fwd_20d secondary diagnostic (seed 42, members only) ----------------
    for ci, (a, b, c, d) in enumerate(CUTS, 1):
        train = df[(df["date"] >= a) & (df["date"] <= b)].dropna(subset=[SECONDARY_LABEL])
        test = df[(df["date"] >= c) & (df["date"] <= d)].dropna(subset=[SECONDARY_LABEL])
        pred_b = _train_predict(train, test, feat_cols, SECONDARY_LABEL, seed=42)
        for m in MEMBERS:
            if ci not in qual_map[m]:
                continue
            core = cores[m]
            mask = test["ticker"].isin(core).to_numpy()
            tr_core = train[train["ticker"].isin(core)]
            te_core = test[mask]
            pred_c = _train_predict(tr_core, te_core, feat_cols, SECONDARY_LABEL, seed=42)
            per_date[f"{m}|fwd20_core|s42|cut{ci}"] = _per_date_ic(
                pred_c, te_core[SECONDARY_LABEL].to_numpy(), te_core["date"].to_numpy())
            per_date[f"{m}|fwd20_base_on_core|s42|cut{ci}"] = _per_date_ic(
                pred_b, test[SECONDARY_LABEL].to_numpy(), test["date"].to_numpy(), mask)
        log.info("fwd20 diag cut%d done", ci)

    results["runtime_seconds_total"] = round(time.time() - t_total, 1)
    _write(out_path, results)
    _write_gz(pd_path, per_date)


# --------------------------------------------------------------------------
# stage: s8 (pick-table supporting arm)
# --------------------------------------------------------------------------
def _s8_delta_series(pt: pd.DataFrame, full: list[str], core: list[str],
                     label_col: str) -> tuple[list[str], np.ndarray]:
    fullset, coreset = set(full), set(core)
    dates, deltas = [], []
    for d, g in pt.groupby("date"):
        gf = g[g["name"].isin(fullset)]
        gc = g[g["name"].isin(coreset)]
        if len(gf) < MIN_NAMES_PER_DATE or len(gc) < MIN_NAMES_PER_DATE:
            continue
        kf = max(1, int(np.floor(0.1 * len(gf) + 0.5)))
        kc = max(1, int(np.floor(0.1 * len(gc) + 0.5)))
        top_f = gf.sort_values(["score", "name"], ascending=[False, True]).head(kf)
        top_c = gc.sort_values(["score", "name"], ascending=[False, True]).head(kc)
        dates.append(str(pd.Timestamp(d).date()))
        deltas.append(float(top_c[label_col].mean() - top_f[label_col].mean()))
    return dates, np.array(deltas)


def cmd_s8(_args) -> None:
    sel = json.loads((EVIDENCE / "core_selection.json").read_text())
    full = sel["s8_full_book"]
    cores: dict[str, list[str]] = sel["cores"]
    random_s8: dict[str, list[str]] = sel["random_s8_cores"]

    pt = pd.read_parquet(PICK_TABLE)
    pt["date"] = pd.to_datetime(pt["date"])
    n_rows_all = len(pt)
    pt = pt[pt["name"].isin(set(full))].copy()

    raw = pd.read_parquet(RAWLABEL, columns=["ticker", "date", "fwd_60d_excess_raw"])
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.rename(columns={"ticker": "name"})
    merged = pt.merge(raw, on=["date", "name"], how="left")
    join_rate = float(merged["fwd_60d_excess_raw"].notna().mean())
    label_col = "fwd_60d_excess_raw"
    fallback = False
    if join_rate < 0.99:
        label_col, fallback = "fwd_60d_excess", True
        log.warning("raw-label join rate %.4f < 0.99 — falling back to the "
                    "standardized label (disclosed)", join_rate)
    merged = merged.dropna(subset=[label_col])

    out: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_pick_table_rows": n_rows_all,
        "n_equity_incumbent_rows": int(len(pt)),
        "raw_label_join_rate": round(join_rate, 6),
        "label_col_used": label_col,
        "fallback_to_standardized": fallback,
        "n_dates": int(merged["date"].nunique()),
        "members": {},
        "controls": {},
    }

    # oracle core (positive-plant control): outcome-selected BY CONSTRUCTION
    mean_lab = merged.groupby("name")[label_col].mean()
    oracle = sorted(mean_lab.sort_values(ascending=False).head(60).index.tolist())

    def read(core: list[str]) -> dict:
        dates, deltas = _s8_delta_series(merged, full, core, label_col)
        rec = {
            "n_dates": len(dates),
            "pooled_delta": round(float(deltas.mean()), 6) if len(deltas) else None,
            "per_seed_bounds": {},
        }
        for bs in S8_BOOT_SEEDS:
            lb, ub = _moving_block_bootstrap(deltas, seed=bs)
            rec["per_seed_bounds"][str(bs)] = {"lb": round(lb, 6), "ub": round(ub, 6)}
        point = rec["pooled_delta"]
        pos = point is not None and point >= S8_BAR and all(
            v["lb"] > 0 for v in rec["per_seed_bounds"].values())
        neg = point is not None and point <= -S8_BAR and all(
            v["ub"] < 0 for v in rec["per_seed_bounds"].values())
        rec["read"] = "SUPPORTIVE-POS" if pos else ("SUPPORTIVE-NEG" if neg else "NULL")
        return rec, dates, deltas

    per_date_store = {}
    for m in MEMBERS:
        core_in_book = sorted(set(cores[m]) & set(full))
        rec, dates, deltas = read(core_in_book)
        rec["n_core_names_in_book"] = len(core_in_book)
        out["members"][m] = rec
        per_date_store[m] = dict(zip(dates, np.round(deltas, 6).tolist()))
        log.info("s8 %s: delta=%s read=%s", m, rec["pooled_delta"], rec["read"])

    rec, dates, deltas = read(oracle)
    out["controls"]["oracle_core"] = {**rec, "names": oracle,
                                      "control_passes": rec["read"] == "SUPPORTIVE-POS"}
    per_date_store["ORACLE"] = dict(zip(dates, np.round(deltas, 6).tolist()))

    null_reads = {}
    for m, core in random_s8.items():
        rec, _, _ = read(core)
        null_reads[m] = rec
    out["controls"]["random_null_cores"] = null_reads
    out["controls"]["random_null_passes"] = all(
        v["read"] == "NULL" for v in null_reads.values())

    _write(EVIDENCE / "s8_results.json", out)
    _write_gz(EVIDENCE / "s8_per_date.json.gz", per_date_store)


# --------------------------------------------------------------------------
# stage: verdict
# --------------------------------------------------------------------------
def _pool(per_date: dict, member: str, kind_a: str, kind_b: str, seed: int,
          cuts: list[int]) -> tuple[list[str], np.ndarray]:
    ic_a: dict[str, float] = {}
    ic_b: dict[str, float] = {}
    for ci in cuts:
        ic_a.update(per_date.get(f"{member}|{kind_a}|s{seed}|cut{ci}", {}))
        ic_b.update(per_date.get(f"{member}|{kind_b}|s{seed}|cut{ci}", {}))
    return _paired_delta_series(ic_a, ic_b)


def cmd_verdict(_args) -> None:
    sel = json.loads((EVIDENCE / "core_selection.json").read_text())
    wf = json.loads((EVIDENCE / "wf_results.json").read_text())
    per_date = _read_gz(EVIDENCE / "wf_per_date.json.gz")
    s8 = json.loads((EVIDENCE / "s8_results.json").read_text())
    qual_map = wf["qualifying_cuts"]

    regime_map = {}
    if REGIME_SERIES.exists():
        for r in json.loads(REGIME_SERIES.read_text()):
            regime_map[str(pd.Timestamp(r["date"]).date())] = r["regime"]

    verdict: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "alpha_one_sided": ALPHA_ONE_SIDED,
        "ci_level_one_sided_pct": round(100 * (1 - ALPHA_ONE_SIDED), 4),
        "materiality_band": MATERIALITY,
        "members": {},
        "controls": {},
        "diagnostics": {},
    }

    def member_read(m: str, kind_core: str, kind_base: str,
                    placebo: bool) -> dict:
        cuts = qual_map[m]
        rec: dict = {"qualifying_cuts": cuts, "per_seed": {}}
        if len(cuts) < MIN_QUALIFYING_CUTS:
            rec["gated"] = "INFEASIBLE"
            return rec
        helps, hurts = [], []
        for s in TRAIN_SEEDS:
            dates, deltas = _pool(per_date, m, kind_core, kind_base, s, cuts)
            lb, ub = _moving_block_bootstrap(deltas, seed=1000 + s)
            point = float(deltas.mean()) if len(deltas) else float("nan")
            row = {"n_dates": len(dates), "pooled_delta": round(point, 6),
                   "ci_lb": round(lb, 6), "ci_ub": round(ub, 6)}
            if placebo:
                _, d_pc = _pool(per_date, m, "core_placebo",
                                "base_placebo_on_core", s, cuts)
                pc_clean = point - (float(d_pc.mean()) if len(d_pc) else float("nan"))
                row["placebo_clean_pooled_delta"] = round(pc_clean, 6)
                row["placebo_pooled_delta"] = round(float(d_pc.mean()), 6) if len(d_pc) else None
            rec["per_seed"][str(s)] = row
            pc_ok_pos = (not placebo) or row.get("placebo_clean_pooled_delta", -1) > 0
            pc_ok_neg = (not placebo) or row.get("placebo_clean_pooled_delta", 1) < 0
            helps.append(point >= MATERIALITY and lb > 0 and pc_ok_pos)
            hurts.append(point <= -MATERIALITY and ub < 0 and pc_ok_neg)
        rec["gated"] = ("HELPS" if all(helps) else
                        "HURTS" if all(hurts) else "NULL")
        return rec

    # ---- gated members ------------------------------------------------------
    for m in MEMBERS:
        rec = member_read(m, "core", "base_on_core", placebo=True)
        rec["s8_read"] = s8["members"][m]["read"]
        rec["s8_pooled_delta"] = s8["members"][m]["pooled_delta"]
        verdict["members"][m] = rec

    # ---- WF controls ---------------------------------------------------------
    # plant per-date keys are PLANT|core|...; baseline side is the member's
    plant: dict = {"qualifying_cuts": qual_map[PLANT_MEMBER], "per_seed": {}}
    plant_ok = []
    for s in TRAIN_SEEDS:
        ic_p, ic_b = {}, {}
        for ci in qual_map[PLANT_MEMBER]:
            ic_p.update(per_date.get(f"PLANT|core|s{s}|cut{ci}", {}))
            ic_b.update(per_date.get(f"{PLANT_MEMBER}|base_on_core|s{s}|cut{ci}", {}))
        dates, deltas = _paired_delta_series(ic_p, ic_b)
        lb, ub = _moving_block_bootstrap(deltas, seed=1000 + s)
        point = float(deltas.mean())
        plant["per_seed"][str(s)] = {"n_dates": len(dates),
                                     "pooled_delta": round(point, 6),
                                     "ci_lb": round(lb, 6), "ci_ub": round(ub, 6)}
        plant_ok.append(point >= MATERIALITY and lb > 0)
    plant["detected_on_all_seeds"] = all(plant_ok)
    verdict["controls"]["wf_positive_plant"] = plant

    nulls: dict = {}
    null_violation = False
    for m in MEMBERS:
        cuts = qual_map[m]
        nrec = {"per_seed": {}}
        helps, hurts = [], []
        for s in TRAIN_SEEDS:
            dates, deltas = _pool(per_date, m, "null_on_core", "base_on_core", s, cuts)
            lb, ub = _moving_block_bootstrap(deltas, seed=1000 + s)
            point = float(deltas.mean()) if len(deltas) else float("nan")
            nrec["per_seed"][str(s)] = {"n_dates": len(dates),
                                        "pooled_delta": round(point, 6),
                                        "ci_lb": round(lb, 6), "ci_ub": round(ub, 6)}
            helps.append(point >= MATERIALITY and lb > 0)
            hurts.append(point <= -MATERIALITY and ub < 0)
        nrec["clears_gate"] = all(helps) or all(hurts)
        null_violation |= nrec["clears_gate"]
        nulls[m] = nrec
    verdict["controls"]["wf_true_null"] = nulls
    verdict["controls"]["wf_true_null_passes"] = not null_violation
    verdict["controls"]["s8_oracle_passes"] = s8["controls"]["oracle_core"]["control_passes"]
    verdict["controls"]["s8_random_null_passes"] = s8["controls"]["random_null_passes"]

    # ---- diagnostics (not gated) --------------------------------------------
    diag: dict = {}
    # selection-only read: baseline IC on core vs on full universe
    sel_only = {}
    for m in MEMBERS:
        cuts = qual_map[m]
        rows = {}
        for s in TRAIN_SEEDS:
            ic_core, ic_full = {}, {}
            for ci in cuts:
                ic_core.update(per_date.get(f"{m}|base_on_core|s{s}|cut{ci}", {}))
                ic_full.update(per_date.get(f"base_full|s{s}|cut{ci}", {}))
            dates, deltas = _paired_delta_series(ic_core, ic_full)
            rows[str(s)] = {"n_dates": len(dates),
                            "mean_delta_core_minus_full": round(float(deltas.mean()), 6)}
        sel_only[m] = rows
    diag["selection_only_baseline_ic_core_vs_full"] = sel_only

    rand = {}
    for m in sel["random_wf_cores"]:
        cuts = qual_map[m]
        dates, deltas = _pool(per_date, m, "core", "base_on_core", 42, cuts)
        rand[m] = {"n_dates": len(dates),
                   "pooled_delta": round(float(deltas.mean()), 6) if len(deltas) else None}
    diag["random_core_reference_seed42"] = rand

    fwd20 = {}
    for m in MEMBERS:
        cuts = qual_map[m]
        dates, deltas = _pool(per_date, m, "fwd20_core", "fwd20_base_on_core", 42, cuts)
        fwd20[m] = {"n_dates": len(dates),
                    "pooled_delta": round(float(deltas.mean()), 6) if len(deltas) else None}
    diag["fwd20_secondary_seed42"] = fwd20

    regimes = {}
    for m in MEMBERS:
        cuts = qual_map[m]
        by_reg: dict[str, list[float]] = {}
        for s in [42]:
            dates, deltas = _pool(per_date, m, "core", "base_on_core", s, cuts)
            for d, x in zip(dates, deltas):
                by_reg.setdefault(regime_map.get(d, "UNKNOWN"), []).append(float(x))
        regimes[m] = {k: {"mean_delta": round(float(np.mean(v)), 6), "n": len(v)}
                      for k, v in sorted(by_reg.items())}
    diag["per_regime_seed42_EXPLORATORY"] = regimes
    diag["core_overlap_matrix"] = sel["overlap_matrix"]
    verdict["diagnostics"] = diag

    # ---- synthesis (frozen) ---------------------------------------------------
    controls_ok = plant["detected_on_all_seeds"] and not null_violation
    gated = {m: verdict["members"][m]["gated"] for m in MEMBERS}
    any_helps = any(v == "HELPS" for v in gated.values())
    any_hurts = any(v == "HURTS" for v in gated.values())
    if not controls_ok:
        headline = "INCONCLUSIVE"
    elif any_helps and not any_hurts:
        helping = [m for m, v in gated.items() if v == "HELPS"]
        if all(verdict["members"][m]["s8_read"] == "SUPPORTIVE-NEG" for m in helping):
            headline = "MIXED"
        else:
            headline = "HELPS"
    elif any_hurts and not any_helps:
        headline = "HURTS"
    elif any_hurts and any_helps:
        headline = "MIXED"
    else:
        headline = "NULL"
    verdict["member_gated"] = gated
    verdict["headline"] = headline
    _write(EVIDENCE / "verdict.json", verdict)
    log.info("HEADLINE: %s | members: %s", headline, gated)

    # ---- manifest -------------------------------------------------------------
    incumbents = sel["incumbents"]
    bar_fp = hashlib.sha256()
    for t in incumbents:
        bar_fp.update(t.encode())
        bar_fp.update(sha256_file(BAR_STORE / t / "1d.parquet").encode())
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec_sha256": sha256_file(EVIDENCE / "frozen_spec.json"),
        "code_sha256": sha256_file(Path(__file__)),
        "inputs": {
            "alpha158_816_dataset": sha256_file(DATASET),
            "strategy_config": sha256_file(STRATEGY_CFG),
            "gics_map": sha256_file(R1K_SECTORS),
            "pick_table": sha256_file(PICK_TABLE),
            "rawlabel_join_source": sha256_file(RAWLABEL),
            "bar_store_combined_133": bar_fp.hexdigest(),
            "regime_series_diag": sha256_file(REGIME_SERIES) if REGIME_SERIES.exists() else None,
        },
        "evidence_files": {
            p.name: sha256_file(p)
            for p in sorted(EVIDENCE.glob("*.json*")) if p.name != "manifest.json"
        },
    }
    _write(EVIDENCE / "manifest.json", manifest)


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["select", "evaluate", "s8", "verdict", "all"])
    args = ap.parse_args()
    stages = {"select": cmd_select, "evaluate": cmd_evaluate,
              "s8": cmd_s8, "verdict": cmd_verdict}
    if args.stage == "all":
        for fn in stages.values():
            fn(args)
    else:
        stages[args.stage](args)


if __name__ == "__main__":
    main()
