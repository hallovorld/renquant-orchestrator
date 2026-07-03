#!/usr/bin/env python3
"""S9 — Track A conditional pick-quality test (FROZEN spec: direction-decision §4).

Executes, EXACTLY as pre-registered in
``doc/design/2026-06-28-renquant105-direction-decision.md`` §4 (origin/main),
the Track A candidate-quality test against the freshly regenerated durable OOS
pick table (``data/exp/oos_pick_table_recipe_v2.parquet``, umbrella tree,
RenQuant#430 / backtesting#59 contract). The criteria are pre-registered and
are NOT altered here; a NULL is recorded, never re-argued.

One-command reproduce (read-only on all inputs; writes evidence JSONs only):

    PYTHONPATH=<renquant-backtesting>/src python3 scripts/s9_track_a_conditional.py \
        --umbrella /Users/renhao/git/github/RenQuant \
        --out-dir doc/research/evidence/2026-07-03-s9

Steps:
  0. Verify the substrate with the owning contract's ``verify_pick_table``
     (canonical content hash + counts against the sidecar). Hard-fail on any
     mismatch — writing the file is not evidence; matching the hash is.
  1. Label (frozen): per (date, name) in the model's TOP-DECILE long-side
     candidates, ``y = 1`` iff realized fwd 60d excess > 11 bps round-trip
     cost proxy. UNITS NOTE: the pick table's ``fwd_60d_excess`` column is the
     per-date CROSS-SECTIONALLY STANDARDIZED training label (mean 0 / std 1 by
     date — verified below); the 11 bps threshold and every bps-denominated
     gate in §4 are in RETURN units, so the raw-unit label
     ``fwd_60d_excess_raw`` is joined from §4's own named durable label input
     (``data/alpha158_291_fundamental_dataset_rawlabel.parquet``). The join is
     proven faithful by requiring the panel's standardized column to match the
     table's exactly.
  2. Conditioning variables per §4's PIT flags: (1) regime [VERIFIED — table
     column]; (2) cross-sectional score dispersion [VERIFIED — derived];
     (3) score margin vs the decile cutoff [VERIFIED — derived];
     (4) earnings-surprise window [GUESS — needs check]: PIT key must be SEC
     ``acceptedDate`` in ``data/fmp_harvest/earnings_291.parquet`` — checked
     mechanically, DROPPED if absent/incomplete (no substitution: that would
     be Track B); (5) liquidity/vol state [GUESS — needs check]: trailing 60d
     realized vol + ADV from a durable bars panel — ``data/ohlcv/<T>/1d.parquet``
     coverage and history depth are checked mechanically, DROPPED if not
     durable/covered.
  3. Split (frozen): chronological 60/40 over the 508 OOS dates with a
     60-trading-day embargo between train and test (embargo dates excluded
     from both; test starts ~2025-08 per §4). No shuffling.
  4. Baseline (frozen): the unconditional top-decile candidate set over the
     same test window.
  5. Metrics (frozen; all on the held-out test window): hit-rate lift,
     per-pick net-of-cost expectancy lift, ANNUALIZED CAPITAL-WEIGHTED
     book-return lift (the binding economic gate), turnover / missed-winner
     cost, active-day exposure. Bootstrap 95% CIs via date-block bootstrap,
     block = 13 (the A1 convention).
  6. Verdict (frozen): GO iff a conditioning clears ALL of §4 (a)-(e);
     STOP/NULL otherwise, with the pre-registered consequence recorded:
     Track B (an input change) is then the only remaining directional path.

Multiplicity honesty: three conditioning candidates are evaluated (a logistic
meta-model on all surviving variables; a regime whitelist; a within-date
margin top-half rule). Champion-by-train selection is reported, but the
verdict applies §4's literal rule — GO iff ANY conditioning clears all of
(a)-(e) on test — which is the GENEROUS direction; a NULL under it is a NULL.

All inputs are read strictly read-only. No git operation is performed
anywhere. Output evidence lands under ``--out-dir`` only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# FROZEN constants (direction-decision §4 — pre-registered, do not alter)
# ---------------------------------------------------------------------------
COST_RT = 0.0011                 # 11 bps round-trip cost proxy (return units)
TRAIN_FRAC = 0.60                # chronological 60/40 split
EMBARGO_DAYS = 60                # trading days == label horizon
BLOCK = 13                       # date-block bootstrap block size (A1 convention)
N_BOOT = 2000                    # bootstrap resamples
SEED = 20260703                  # deterministic
PERIODS_PER_YEAR = 252.0 / 60.0  # "~4 60d-periods/yr" per §4 (= 4.2)

# §4 GO gates (all must hold on the held-out test window)
GATE_A_BOOK_LIFT_ANN = 0.0050    # (a) >= +50 bps/yr, CI LB > 0  [binding economic gate]
GATE_B_PER_PICK_LIFT = 0.0005    # (b) >= +5 bps per 60d, CI LB > 0
GATE_C_HITRATE_LIFT = 0.03       # (c) >= +3 pp, CI excluding 0
GATE_D_ACTIVE_FRAC = 0.25        # (d) active-day exposure >= 25% of test dates
GATE_E_MAX_WINNER_DROP = 1 / 3   # (e) drops <= 1/3 of baseline winners ...
GATE_E_MAX_TURNOVER_X = 2.0      # ... and <= 2x baseline turnover

TOP_DECILE = 9                   # decile_rank 9 = best (per the #59/#430 contract)
VOL_ADV_WINDOW = 60              # trailing sessions for realized vol / ADV
MIN_VAR5_COVERAGE = 0.995        # var-5 usable only if computable for >=99.5% of picks


# ---------------------------------------------------------------------------
# Step 0 — substrate verification (owning contract)
# ---------------------------------------------------------------------------
def verify_substrate(pick_table: Path, bt_src: Path | None) -> dict:
    if bt_src is not None:
        sys.path.insert(0, str(bt_src))
    try:
        from renquant_backtesting.analysis.pick_table import verify_pick_table
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "renquant_backtesting is not importable — pass --bt-src pointing at a "
            f"renquant-backtesting@main src/ checkout ({exc})"
        )
    result = verify_pick_table(pick_table)  # raises ValueError on any mismatch
    sidecar = json.loads(
        pick_table.with_name(pick_table.stem + ".manifest.json").read_text()
    )
    return {
        "verify_pick_table": result,
        "sidecar_recipe": sidecar.get("recipe", {}),
        "sidecar_counts": sidecar.get("counts", {}),
    }


# ---------------------------------------------------------------------------
# PIT checks for §4 conditioning variables 4 and 5
# ---------------------------------------------------------------------------
def pit_check_var4_earnings(earnings_path: Path, names: list[str]) -> dict:
    """Var 4 (earnings-surprise window): §4 requires PIT via SEC acceptedDate in
    data/fmp_harvest/earnings_291.parquet. Mechanical check; DROP on failure."""
    out: dict = {"variable": "earnings_surprise_window", "source": str(earnings_path)}
    if not earnings_path.exists():
        out.update(passed=False, reason="source file missing")
        return out
    cols = list(pd.read_parquet(earnings_path).columns)
    out["columns"] = cols
    if "acceptedDate" not in cols:
        out.update(
            passed=False,
            reason=(
                "PIT key absent: the file has no acceptedDate column (only a "
                "single-snapshot fetched_at and a vendor lastUpdated) — the "
                "announcement timestamps are backfilled, not point-in-time "
                "collected. Per §4 the variable is DROPPED; substituting "
                "another source would be Track B."
            ),
        )
        return out
    ear = pd.read_parquet(earnings_path)
    covered = set(ear["symbol"].unique()) | set(ear.get("ticker", ear["symbol"]).unique())
    missing = sorted(set(names) - covered)
    out["missing_names"] = missing
    out["passed"] = len(missing) == 0
    if missing:
        out["reason"] = f"coverage incomplete: {len(missing)} names missing"
    return out


def pit_check_var5_ohlcv(ohlcv_dir: Path, top: pd.DataFrame) -> dict:
    """Var 5 (liquidity/vol state): needs a DURABLE bars panel with >=60 trailing
    sessions before every pick. data/ohlcv/<T>/1d.parquet is the umbrella tree's
    committed daily-bars home (back-adjusted closes — verified around the NVDA
    2024-06-10 10:1 split). Trailing-window vol/ADV are PIT-safe by construction."""
    out: dict = {"variable": "liquidity_vol_state", "source": str(ohlcv_dir / "<T>" / "1d.parquet")}
    first_pick = top.groupby("name")["date"].min()
    missing_files, short_history = [], []
    for name, fp in first_pick.items():
        f = ohlcv_dir / name / "1d.parquet"
        if not f.exists():
            missing_files.append(name)
            continue
        idx = pd.read_parquet(f, columns=["close"]).index
        if int((idx < fp).sum()) < VOL_ADV_WINDOW + 1:
            short_history.append(name)
    out["missing_files"] = missing_files
    out["short_history_names"] = short_history
    out["passed"] = not missing_files and not short_history
    if not out["passed"]:
        out["reason"] = "bars panel missing or insufficient trailing history"
    return out


def compute_var5_features(ohlcv_dir: Path, top: pd.DataFrame) -> pd.DataFrame:
    """Trailing 60d realized vol (std of daily close-to-close returns) and 60d
    average dollar volume, as-of each pick date (inclusive — scores are computed
    from data through the pick date, so the same-day close is ex-ante)."""
    pick_dates = sorted(top["date"].unique())
    frames = []
    for name in sorted(top["name"].unique()):
        bars = pd.read_parquet(ohlcv_dir / name / "1d.parquet", columns=["close", "volume"])
        bars = bars.sort_index()
        ret = bars["close"].pct_change()
        vol60 = ret.rolling(VOL_ADV_WINDOW).std()
        adv60 = (bars["close"] * bars["volume"]).rolling(VOL_ADV_WINDOW).mean()
        feat = pd.DataFrame({"vol60": vol60, "adv60": adv60})
        # as-of alignment onto pick dates (bars are daily; pick dates are trading days)
        feat = feat.reindex(pd.DatetimeIndex(pick_dates), method="ffill")
        feat["name"] = name
        feat.index.name = "date"
        frames.append(feat.reset_index())
    allf = pd.concat(frames, ignore_index=True)
    return top.merge(allf, on=["date", "name"], how="left")


# ---------------------------------------------------------------------------
# Conditioning candidates (fit on TRAIN only; frozen structure, no test peeking)
# ---------------------------------------------------------------------------
def fit_logistic(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> tuple[pd.Series, pd.Series]:
    from sklearn.linear_model import LogisticRegression

    Xtr = train[feats].to_numpy(dtype=float)
    Xte = test[feats].to_numpy(dtype=float)
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    model = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")
    model.fit((Xtr - mu) / sd, train["y"].to_numpy(dtype=int))
    p_tr = pd.Series(model.predict_proba((Xtr - mu) / sd)[:, 1], index=train.index)
    p_te = pd.Series(model.predict_proba((Xte - mu) / sd)[:, 1], index=test.index)
    return p_tr, p_te


def build_candidates(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> dict:
    """Returns {candidate: {'train': mask, 'test': mask, 'definition': str}}."""
    cands: dict = {}

    # C1 — logistic meta-model on all surviving ex-ante variables;
    # threshold = TRAIN median predicted probability (~50% retention, fixed ex ante).
    p_tr, p_te = fit_logistic(train, test, feats)
    tau = float(p_tr.median())
    cands["C1_logit_all"] = {
        "train": p_tr >= tau,
        "test": p_te >= tau,
        "definition": (
            f"logistic regression on {feats}; keep picks with predicted "
            f"P(y=1) >= train-median tau={tau:.4f}"
        ),
    }

    # C2 — regime whitelist: keep regimes whose TRAIN hit-rate strictly exceeds
    # the unconditional TRAIN hit-rate.
    base_hr = float(train["y"].mean())
    reg_hr = train.groupby("regime")["y"].mean()
    whitelist = sorted(reg_hr[reg_hr > base_hr].index.tolist())
    cands["C2_regime_whitelist"] = {
        "train": train["regime"].isin(whitelist),
        "test": test["regime"].isin(whitelist),
        "definition": (
            f"keep regimes with train hit-rate > unconditional ({base_hr:.4f}): "
            f"{whitelist}; train per-regime hit-rates = "
            f"{ {k: round(float(v), 4) for k, v in reg_hr.items()} }"
        ),
    }

    # C3 — within-date margin top-half: keep picks with score margin >= the
    # within-date median margin among top-decile picks (structural rule).
    def margin_top_half(df: pd.DataFrame) -> pd.Series:
        med = df.groupby("date")["margin"].transform("median")
        return df["margin"] >= med

    cands["C3_margin_top_half"] = {
        "train": margin_top_half(train),
        "test": margin_top_half(test),
        "definition": "keep picks with within-date score margin >= within-date median margin",
    }
    return cands


# ---------------------------------------------------------------------------
# §4 metric suite on a (baseline, conditioned) pair over one window
# ---------------------------------------------------------------------------
def _membership_turnover(df: pd.DataFrame, mask: pd.Series, dates: list) -> int:
    sets = {d: frozenset(df.loc[mask & (df["date"] == d), "name"]) for d in dates}
    turn = 0
    for a, b in zip(dates[:-1], dates[1:]):
        turn += len(sets[a] ^ sets[b])
    return turn


def evaluate(df: pd.DataFrame, mask: pd.Series, rng: np.random.Generator) -> dict:
    """df = all top-decile picks in the window; mask = conditioned subset."""
    dates = sorted(df["date"].unique())
    n_dates = len(dates)
    base_ret, cond_ret = df["ret_raw"], df.loc[mask, "ret_raw"]
    base_y, cond_y = df["y"], df.loc[mask, "y"]

    n_base, n_cond = len(df), int(mask.sum())
    capital_frac = n_cond / n_base if n_base else 0.0
    active_dates = df.loc[mask, "date"].nunique()
    active_frac = active_dates / n_dates if n_dates else 0.0

    hit_lift = float(cond_y.mean() - base_y.mean()) if n_cond else float("nan")
    pick_lift = float(cond_ret.mean() - base_ret.mean()) if n_cond else float("nan")
    book_lift_ann = pick_lift * PERIODS_PER_YEAR * capital_frac if n_cond else float("nan")

    # date-block bootstrap (block = BLOCK consecutive dates, resample with replacement)
    blocks = [dates[i : i + BLOCK] for i in range(0, n_dates, BLOCK)]
    by_date_idx = {d: np.flatnonzero((df["date"] == d).to_numpy()) for d in dates}
    mask_arr = mask.to_numpy()
    y_arr = df["y"].to_numpy(dtype=float)
    r_arr = df["ret_raw"].to_numpy(dtype=float)
    hit_bs, pick_bs, book_bs = [], [], []
    for _ in range(N_BOOT):
        chosen = rng.integers(0, len(blocks), size=len(blocks))
        idx = np.concatenate([np.concatenate([by_date_idx[d] for d in blocks[j]]) for j in chosen])
        m = mask_arr[idx]
        nb, nc = len(idx), int(m.sum())
        if nc == 0 or nb == 0:
            hit_bs.append(np.nan); pick_bs.append(np.nan); book_bs.append(np.nan)
            continue
        hl = y_arr[idx][m].mean() - y_arr[idx].mean()
        pl = r_arr[idx][m].mean() - r_arr[idx].mean()
        hit_bs.append(hl)
        pick_bs.append(pl)
        book_bs.append(pl * PERIODS_PER_YEAR * (nc / nb))

    def ci(v):
        v = np.asarray(v, dtype=float)
        v = v[~np.isnan(v)]
        return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if len(v) else [None, None]

    hit_ci, pick_ci, book_ci = ci(hit_bs), ci(pick_bs), ci(book_bs)

    # (e) missed winners + turnover
    base_winners = int(base_y.sum())
    kept_winners = int(cond_y.sum())
    dropped_winners = base_winners - kept_winners
    winner_drop_frac = dropped_winners / base_winners if base_winners else 0.0
    turn_base = _membership_turnover(df, pd.Series(True, index=df.index), dates)
    turn_cond = _membership_turnover(df, mask, dates)
    turnover_x = turn_cond / turn_base if turn_base else float("inf")

    gates = {
        "a_book_lift": bool(
            n_cond and book_lift_ann >= GATE_A_BOOK_LIFT_ANN
            and book_ci[0] is not None and book_ci[0] > 0
        ),
        "b_per_pick_lift": bool(
            n_cond and pick_lift >= GATE_B_PER_PICK_LIFT
            and pick_ci[0] is not None and pick_ci[0] > 0
        ),
        "c_hit_rate_lift": bool(
            n_cond and hit_lift >= GATE_C_HITRATE_LIFT
            and hit_ci[0] is not None and hit_ci[0] > 0
        ),
        "d_active_exposure": bool(active_frac >= GATE_D_ACTIVE_FRAC),
        "e_winner_drop_and_turnover": bool(
            winner_drop_frac <= GATE_E_MAX_WINNER_DROP and turnover_x <= GATE_E_MAX_TURNOVER_X
        ),
    }
    return {
        "n_picks_baseline": n_base,
        "n_picks_conditioned": n_cond,
        "n_dates": n_dates,
        "capital_fraction": capital_frac,
        "active_day_fraction": active_frac,
        "baseline_hit_rate": float(base_y.mean()),
        "conditioned_hit_rate": float(cond_y.mean()) if n_cond else None,
        "hit_rate_lift": hit_lift,
        "hit_rate_lift_ci95": hit_ci,
        "baseline_net_expectancy_per_pick": float(base_ret.mean() - COST_RT),
        "conditioned_net_expectancy_per_pick": float(cond_ret.mean() - COST_RT) if n_cond else None,
        "per_pick_lift": pick_lift,
        "per_pick_lift_ci95": pick_ci,
        "book_lift_annualized": book_lift_ann,
        "book_lift_annualized_ci95": book_ci,
        "baseline_winners": base_winners,
        "dropped_winners": dropped_winners,
        "winner_drop_fraction": winner_drop_frac,
        "turnover_baseline": turn_base,
        "turnover_conditioned": turn_cond,
        "turnover_multiple": turnover_x,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
    }


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--umbrella", type=Path, default=Path("/Users/renhao/git/github/RenQuant"))
    ap.add_argument("--pick-table", type=Path, default=None)
    ap.add_argument("--rawlabel-panel", type=Path, default=None)
    ap.add_argument("--earnings", type=Path, default=None)
    ap.add_argument("--ohlcv-dir", type=Path, default=None)
    ap.add_argument("--bt-src", type=Path, default=None,
                    help="renquant-backtesting src/ for verify_pick_table (else PYTHONPATH)")
    ap.add_argument("--out-dir", type=Path,
                    default=Path("doc/research/evidence/2026-07-03-s9"))
    args = ap.parse_args()

    u = args.umbrella
    pick_table = args.pick_table or u / "data/exp/oos_pick_table_recipe_v2.parquet"
    rawlabel = args.rawlabel_panel or u / "data/alpha158_291_fundamental_dataset_rawlabel.parquet"
    earnings = args.earnings or u / "data/fmp_harvest/earnings_291.parquet"
    ohlcv_dir = args.ohlcv_dir or u / "data/ohlcv"
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # -- Step 0: substrate verification ------------------------------------
    sub = verify_substrate(pick_table, args.bt_src)
    print(f"[0] substrate verified: content_sha256={sub['verify_pick_table']['content_sha256'][:16]}… "
          f"counts={sub['sidecar_counts']}")

    table = pd.read_parquet(pick_table)
    # standardized-label sanity (documents WHY the raw-unit join is required)
    g = table.groupby("date")["fwd_60d_excess"]
    std_label_stats = {
        "per_date_mean_of_means": float(g.mean().mean()),
        "per_date_mean_of_stds": float(g.std().mean()),
    }
    sub["table_label_is_standardized"] = std_label_stats

    top = table[table["decile_rank"] == TOP_DECILE].copy()

    # -- Step 1: frozen label in return units ------------------------------
    lab = pd.read_parquet(rawlabel, columns=["ticker", "date", "fwd_60d_excess", "fwd_60d_excess_raw"])
    top = top.merge(
        lab.rename(columns={"ticker": "name", "fwd_60d_excess": "fwd_60d_excess_panel"}),
        on=["date", "name"], how="left",
    )
    n_missing = int(top["fwd_60d_excess_raw"].isna().sum())
    max_z_diff = float((top["fwd_60d_excess"] - top["fwd_60d_excess_panel"]).abs().max())
    if n_missing or max_z_diff > 1e-9:
        raise SystemExit(f"label join not faithful: missing={n_missing} max_z_diff={max_z_diff}")
    sub["raw_label_join"] = {"missing_rows": n_missing, "max_std_label_abs_diff": max_z_diff}
    (args.out_dir / "substrate_verification.json").write_text(json.dumps(sub, indent=2) + "\n")

    top["ret_raw"] = top["fwd_60d_excess_raw"]
    top["y"] = (top["ret_raw"] > COST_RT).astype(int)

    # -- Step 2: conditioning variables + PIT checks ------------------------
    disp = table.groupby("date")["score"].std().rename("dispersion")
    cutoff = top.groupby("date")["score"].min().rename("decile_cutoff")
    top = top.merge(disp, on="date").merge(cutoff, on="date")
    top["margin"] = top["score"] - top["decile_cutoff"]

    names = sorted(top["name"].unique())
    pit4 = pit_check_var4_earnings(earnings, names)
    pit5 = pit_check_var5_ohlcv(ohlcv_dir, top)
    feats = ["dispersion", "margin"]  # regime enters as dummies below
    if pit5["passed"]:
        top = compute_var5_features(ohlcv_dir, top)
        cov = float(top[["vol60", "adv60"]].notna().all(axis=1).mean())
        pit5["feature_coverage"] = cov
        if cov >= MIN_VAR5_COVERAGE:
            top["adv_rank"] = top.groupby("date")["adv60"].rank(pct=True)
            med_v = top["vol60"].median()
            top["vol60"] = top["vol60"].fillna(med_v)
            top["adv_rank"] = top["adv_rank"].fillna(0.5)
            feats += ["vol60", "adv_rank"]
        else:
            pit5["passed"] = False
            pit5["reason"] = f"feature coverage {cov:.4f} < {MIN_VAR5_COVERAGE}"
    for reg in sorted(top["regime"].unique())[:-1]:  # drop-one dummy coding
        col = f"regime_{reg}"
        top[col] = (top["regime"] == reg).astype(float)
        feats.append(col)
    pit = {
        "var1_regime": {"passed": True, "status": "VERIFIED — table column"},
        "var2_dispersion": {"passed": True, "status": "VERIFIED — derived from table"},
        "var3_score_margin": {"passed": True, "status": "VERIFIED — derived from table"},
        "var4_earnings_surprise_window": pit4,
        "var5_liquidity_vol_state": pit5,
        "surviving_model_features": feats,
    }
    (args.out_dir / "pit_checks.json").write_text(json.dumps(pit, indent=2) + "\n")
    print(f"[2] PIT checks: var4={'PASS' if pit4['passed'] else 'FAIL->DROP'} "
          f"var5={'PASS' if pit5['passed'] else 'FAIL->DROP'}; features={feats}")

    # -- Step 3: frozen chronological split with embargo ---------------------
    dates = sorted(top["date"].unique())
    n_train = round(TRAIN_FRAC * len(dates))
    train_dates = set(dates[:n_train])
    embargo_dates = dates[n_train : n_train + EMBARGO_DAYS]
    test_dates = dates[n_train + EMBARGO_DAYS :]
    train = top[top["date"].isin(train_dates)].reset_index(drop=True)
    test = top[top["date"].isin(set(test_dates))].reset_index(drop=True)
    split = {
        "n_oos_dates": len(dates),
        "n_train_dates": len(train_dates),
        "n_embargo_dates": len(embargo_dates),
        "n_test_dates": len(test_dates),
        "train_window": [str(min(train_dates).date()), str(max(train_dates).date())],
        "embargo_window": [str(embargo_dates[0].date()), str(embargo_dates[-1].date())],
        "test_window": [str(test_dates[0].date()), str(test_dates[-1].date())],
        "per_regime_cells": {
            "train_picks": train["regime"].value_counts().to_dict(),
            "train_dates": train.groupby("regime")["date"].nunique().to_dict(),
            "test_picks": test["regime"].value_counts().to_dict(),
            "test_dates": test.groupby("regime")["date"].nunique().to_dict(),
        },
    }
    print(f"[3] split: train {split['train_window']} ({len(train_dates)}d) | "
          f"embargo {split['embargo_window']} ({len(embargo_dates)}d) | "
          f"test {split['test_window']} ({len(test_dates)}d)")

    # -- Steps 4-6: candidates, metrics, verdict -----------------------------
    rng = np.random.default_rng(SEED)
    cands = build_candidates(train, test, feats)
    results = {}
    for cname, c in cands.items():
        res_tr = evaluate(train, c["train"], rng)
        res_te = evaluate(test, c["test"], rng)
        results[cname] = {"definition": c["definition"], "train": res_tr, "test": res_te}
        t = res_te
        print(f"[4] {cname}: test book_lift_ann={t['book_lift_annualized']*1e4:+.1f}bps/yr "
              f"CI[{t['book_lift_annualized_ci95'][0]*1e4:+.1f},{t['book_lift_annualized_ci95'][1]*1e4:+.1f}] "
              f"pick_lift={t['per_pick_lift']*1e4:+.1f}bps CI[{t['per_pick_lift_ci95'][0]*1e4:+.1f},"
              f"{t['per_pick_lift_ci95'][1]*1e4:+.1f}] hit_lift={t['hit_rate_lift']*100:+.2f}pp "
              f"active={t['active_day_fraction']:.2f} winner_drop={t['winner_drop_fraction']:.2f} "
              f"turnover_x={t['turnover_multiple']:.2f} gates={t['gates']} "
              f"ALL={'PASS' if t['all_gates_pass'] else 'FAIL'}")

    # champion-by-train protocol (reported; verdict below uses §4's literal rule)
    eligible = {
        k: v for k, v in results.items()
        if v["train"]["gates"]["d_active_exposure"] and v["train"]["gates"]["e_winner_drop_and_turnover"]
    }
    pool = eligible or results
    champion = max(pool, key=lambda k: pool[k]["train"]["book_lift_annualized"])

    any_pass = [k for k, v in results.items() if v["test"]["all_gates_pass"]]
    verdict = "GO" if any_pass else "NULL"
    out = {
        "task": "S9 — Track A conditional pick-quality test",
        "frozen_spec": "doc/design/2026-06-28-renquant105-direction-decision.md §4 (origin/main)",
        "constants": {
            "cost_round_trip": COST_RT, "train_frac": TRAIN_FRAC, "embargo_days": EMBARGO_DAYS,
            "bootstrap": {"n": N_BOOT, "block": BLOCK, "seed": SEED},
            "periods_per_year": PERIODS_PER_YEAR,
            "gates": {
                "a_book_lift_ann_min": GATE_A_BOOK_LIFT_ANN,
                "b_per_pick_lift_min": GATE_B_PER_PICK_LIFT,
                "c_hit_rate_lift_min": GATE_C_HITRATE_LIFT,
                "d_active_frac_min": GATE_D_ACTIVE_FRAC,
                "e_max_winner_drop": GATE_E_MAX_WINNER_DROP,
                "e_max_turnover_multiple": GATE_E_MAX_TURNOVER_X,
            },
        },
        "split": split,
        "candidates": results,
        "champion_by_train_protocol": {
            "champion": champion,
            "train_eligible": sorted(eligible),
            "champion_test_all_gates_pass": results[champion]["test"]["all_gates_pass"],
        },
        "verdict": verdict,
        "verdict_rule": "GO iff ANY conditioning clears ALL of §4 (a)-(e) on the held-out test window",
        "candidates_passing_all_gates": any_pass,
        "pre_registered_consequence_if_null": (
            "Track A is null: no conditioning delivers materially higher pick quality "
            "at book level. Track B (an input change: universe down-cap or new PIT-clean "
            "data) becomes the only remaining directional path. No filter fishing."
        ),
    }
    (args.out_dir / "s9_results.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"[6] VERDICT: {verdict}"
          + (f" (passing: {any_pass})" if any_pass else " — Track A null; Track B is the only remaining directional path"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
