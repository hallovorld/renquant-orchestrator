#!/usr/bin/env python3
"""M3 conviction uncertainty-haircut ledger replay (READ-ONLY study).

Question (#231 / unified-107 master plan Term TC row M3): does the admit rule
`mu - k*SE(mu) > floor` remove more losers than winners vs the current
`mu > floor` (floor = 0.03), for k in {0.5, 1.0}?

This is a replay over the historical live ledger only. It changes NO config
and NO behavior. It measures the HISTORICAL mu stream's ordering (the D1
model verdict is still pending), so a positive result here is evidence about
the admission RULE on past scores, not a validation of the model itself.

SE(mu) proxy (stated honestly):
  (a) PRIMARY - cross-run dispersion: for each (ticker, decision date), the
      sample standard deviation of that ticker's mu over its trailing
      <= WINDOW_OBS canonical daily runs (including the current one),
      restricted to the SAME scorer era (model_type regime), requiring
      >= MIN_OBS observations. This is a STABILITY proxy, not a sampling SE:
      it conflates real information arrival, feature drift, and retrains
      within an era. It is computable at decision time (no lookahead).
  (b) SENSITIVITY - calibration-band proxy: the live panel calibrator JSON
      stores only the point mapping (x,y knots) plus global metadata; it
      persists NO per-name band. The only derivable global figure is the
      label residual scale er_std*sqrt(1-pool_ic^2) (~0.046 on the
      calibrator's own 5d-lookahead scale, vs mu's 60d horizon). Applied as
      a constant SE it is not an uncertainty-SENSITIVE rule at all - it is
      a blunt floor raise to floor + k*0.046 (0.053 at k=0.5), which keeps
      only the high-mu May-era names and would remove the ENTIRE June
      panel-era floor-clearing pool (mu_p90 ~0.033-0.036). Reported as the
      scale-mismatched, per-name-blind sensitivity it is.

Outcome horizons (stated honestly): mu_horizon_days = 60, but fwd_60d is
unresolvable for the ENTIRE live window (first live run 2026-04-23; 60
trading days have not elapsed). Primary outcome = fwd_20d excess over SPY
(resolvable through 2026-06-03); fwd_10d (through 2026-06-17) and fwd_5d
(through 2026-06-25) reported as sensitivity. Winner = excess > COST_PROXY
(11 bps). The fwd_60d verdict is forward-only work (same posture as S5).

Reproduce (one command, sqlite opened mode=ro):
  python3 scripts/m3_haircut_replay.py
Inputs (read-only):
  /Users/renhao/git/github/RenQuant/data/runs.alpaca.db
  /Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/
      panel-rank-calibration.alpha158_linear.json  (proxy (b) metadata only)
Outputs (committed evidence):
  doc/research/evidence/2026-07-02-m3/m3_haircut_replay.json
  doc/research/evidence/2026-07-02-m3/m3_admission_composition.json
  doc/research/evidence/2026-07-02-m3/m3_fixture_cases.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import date as _date
from datetime import timedelta

# ---------------------------------------------------------------- constants
FLOOR = 0.03                  # conviction floor (production admit: mu > FLOOR)
K_LIST = (0.5, 1.0)           # haircut multipliers under study
WINDOW_OBS = 10               # trailing canonical-run observations for SE(mu)
MIN_OBS = 3                   # minimum observations before SE is defined
THIN_HI = 0.0375              # thin-margin band = mu in [FLOOR, FLOOR*1.25)
COST_PROXY = 0.0011           # 11 bps round-trip cost proxy (winner threshold)
BLOCK_LEN = 13                # date-block bootstrap block length (spec'd)
BLOCK_SENS = (5, 1)           # sensitivity block lengths (13 >= n_dates is degenerate)
N_BOOT = 5000
SEED = 20260702
MIN_FULL_RUN_CANDIDATES = 40  # "full" daily run threshold (S-TC #234 discipline)
HORIZONS = ("fwd_20d", "fwd_10d", "fwd_5d")
MAX_EFFDATE_LAG_DAYS = 4      # weekend runs map to the prior trading as_of_date

DEFAULT_DB = "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"
DEFAULT_CALIBRATOR = (
    "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/"
    "panel-rank-calibration.alpha158_linear.json"
)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT_DIR = os.path.join(_REPO_ROOT, "doc", "research", "evidence", "2026-07-02-m3")

FIXTURE_TICKERS = ("OXY", "GRMN")   # RS-2 / POC-B thin-margin forensic fixtures
FIXTURE_DATES = ("2026-06-30", "2026-07-01")

_LEGACY_TOURNAMENT_TYPES = {"Classification", "Manual", "QLearning", "XGBoost"}


# ------------------------------------------------------------------- helpers
def classify_era(model_type: str | None) -> str:
    """Coarse scorer-era label. Cross-era mu jumps are scorer churn, not
    sampling noise, so the SE window never mixes eras. The legacy per-ticker
    tournament (four model_type values, champion may flip day to day) is ONE
    era: its mu stream is what the admission gate actually saw."""
    if model_type is None or model_type == "":
        return "pre_tournament_null"
    if model_type in _LEGACY_TOURNAMENT_TYPES:
        return "legacy_tournament"
    return str(model_type)


def trailing_se(observations: list[float]) -> float | None:
    """Sample stdev of the trailing window (>= MIN_OBS obs required)."""
    if len(observations) < MIN_OBS:
        return None
    return statistics.stdev(observations)


def haircut_admits(mu: float, se: float, k: float, floor: float = FLOOR) -> bool:
    return (mu - k * se) > floor


def is_winner(excess: float, cost: float = COST_PROXY) -> bool:
    return excess > cost


def is_thin_margin(mu: float) -> bool:
    return FLOOR < mu < THIN_HI


def canonical_daily_runs(con: sqlite3.Connection) -> list[dict]:
    """One live pipeline_runs row per run_date: the row with the latest
    created_at among that date's runs having >= MIN_FULL_RUN_CANDIDATES
    candidate rows (same dedup discipline as scripts/poc_transfer_coefficient
    r2 fix / #234)."""
    rows = con.execute(
        """
        SELECT p.run_id, p.run_date, COALESCE(p.regime,'UNKNOWN') regime, p.created_at
        FROM pipeline_runs p
        WHERE p.run_type='live'
          AND (SELECT COUNT(*) FROM candidate_scores c
               WHERE c.run_id=p.run_id AND c.role='candidate') >= ?
        ORDER BY p.run_date, p.created_at
        """,
        (MIN_FULL_RUN_CANDIDATES,),
    ).fetchall()
    by_date: dict[str, tuple] = {}
    for run_id, run_date, regime, created_at in rows:
        by_date[run_date] = (run_id, regime, created_at)  # later created_at wins
    return [
        {"run_date": d, "run_id": v[0], "regime": v[1]}
        for d, v in sorted(by_date.items())
    ]


def load_candidates(con: sqlite3.Connection, runs: list[dict]) -> list[dict]:
    out = []
    for r in runs:
        for tkr, mu, model_type, blocked_by in con.execute(
            "SELECT ticker, mu, model_type, blocked_by FROM candidate_scores "
            "WHERE run_id=? AND role='candidate' AND mu IS NOT NULL",
            (r["run_id"],),
        ):
            out.append(
                {
                    "run_date": r["run_date"],
                    "run_id": r["run_id"],
                    "regime": r["regime"],
                    "ticker": tkr,
                    "mu": float(mu),
                    "era": classify_era(model_type),
                    "blocked_by": blocked_by,
                }
            )
    return out


def attach_se(cands: list[dict]) -> None:
    """Proxy (a): per ticker, era-stratified trailing-window stdev of mu."""
    stream: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        stream[c["ticker"]].append(c)
    for tkr, rows in stream.items():
        rows.sort(key=lambda x: x["run_date"])
        for i, c in enumerate(rows):
            window: list[float] = []
            for j in range(i, -1, -1):
                if rows[j]["era"] != c["era"]:
                    break  # never mix scorer eras
                window.append(rows[j]["mu"])
                if len(window) >= WINDOW_OBS:
                    break
            c["se"] = trailing_se(window)
            c["n_obs"] = len(window)


def effective_outcome_date(
    con: sqlite3.Connection, run_date: str, cache: dict
) -> str | None:
    """ticker_forward_returns has no rows on weekend run dates (05-09/17/30
    were Saturday/Sunday runs); map to the latest as_of_date <= run_date with
    any rows, within MAX_EFFDATE_LAG_DAYS."""
    if run_date in cache:
        return cache[run_date]
    row = con.execute(
        "SELECT MAX(as_of_date) FROM ticker_forward_returns WHERE as_of_date <= ?",
        (run_date,),
    ).fetchone()
    eff = row[0]
    if eff is not None:
        d0 = _date.fromisoformat(run_date)
        d1 = _date.fromisoformat(eff)
        if d0 - d1 > timedelta(days=MAX_EFFDATE_LAG_DAYS):
            eff = None
    cache[run_date] = eff
    return eff


def attach_outcomes(con: sqlite3.Connection, cands: list[dict]) -> dict:
    """Excess over SPY per horizon; both legs from the same effective
    as_of_date. Returns coverage counters."""
    eff_cache: dict[str, str | None] = {}
    fwd_cache: dict[tuple, tuple | None] = {}

    def fwd(ticker: str, eff: str):
        key = (ticker, eff)
        if key not in fwd_cache:
            fwd_cache[key] = con.execute(
                "SELECT fwd_20d, fwd_10d, fwd_5d FROM ticker_forward_returns "
                "WHERE ticker=? AND as_of_date=?",
                (ticker, eff),
            ).fetchone()
        return fwd_cache[key]

    coverage = {h: {"resolved": 0, "unresolved": 0} for h in HORIZONS}
    for c in cands:
        eff = effective_outcome_date(con, c["run_date"], eff_cache)
        c["eff_date"] = eff
        for h in HORIZONS:
            c[f"excess_{h}"] = None
        if eff is None:
            for h in HORIZONS:
                coverage[h]["unresolved"] += 1
            continue
        t_row, spy_row = fwd(c["ticker"], eff), fwd("SPY", eff)
        for idx, h in enumerate(HORIZONS):
            tv = t_row[idx] if t_row else None
            sv = spy_row[idx] if spy_row else None
            if tv is not None and sv is not None:
                c[f"excess_{h}"] = float(tv) - float(sv)
                coverage[h]["resolved"] += 1
            else:
                coverage[h]["unresolved"] += 1
    return coverage


# ------------------------------------------------------------------- replay
def _set_stats(rows: list[dict], horizon: str) -> dict:
    ex = [r[f"excess_{horizon}"] for r in rows]
    n = len(ex)
    if n == 0:
        return {"n": 0, "mean_excess": None, "expectancy_net_cost": None,
                "winner_rate": None, "n_winners": 0, "n_losers": 0}
    winners = sum(1 for e in ex if is_winner(e))
    mean_ex = sum(ex) / n
    return {
        "n": n,
        "mean_excess": mean_ex,
        "expectancy_net_cost": mean_ex - COST_PROXY,
        "winner_rate": winners / n,
        "n_winners": winners,
        "n_losers": n - winners,
    }


def replay_universe(cands: list[dict], horizon: str) -> list[dict]:
    """Floor-clearing candidates with a defined SE and a resolved outcome."""
    return [
        c for c in cands
        if c["mu"] > FLOOR and c.get("se") is not None
        and c.get(f"excess_{horizon}") is not None
    ]


def replay(cands: list[dict], horizon: str, k: float) -> dict:
    uni = replay_universe(cands, horizon)
    kept = [c for c in uni if haircut_admits(c["mu"], c["se"], k)]
    removed = [c for c in uni if not haircut_admits(c["mu"], c["se"], k)]
    cur, hc, rem = (_set_stats(s, horizon) for s in (uni, kept, removed))
    delta = (
        hc["mean_excess"] - cur["mean_excess"]
        if hc["mean_excess"] is not None and cur["mean_excess"] is not None
        else None
    )
    per_regime = {}
    for regime in sorted({c["regime"] for c in uni}):
        u = [c for c in uni if c["regime"] == regime]
        kp = [c for c in u if haircut_admits(c["mu"], c["se"], k)]
        rm = [c for c in u if not haircut_admits(c["mu"], c["se"], k)]
        per_regime[regime] = {
            "current": _set_stats(u, horizon),
            "haircut": _set_stats(kp, horizon),
            "removed": _set_stats(rm, horizon),
        }
    per_era = {}
    for era in sorted({c["era"] for c in uni}):
        u = [c for c in uni if c["era"] == era]
        kp = [c for c in u if haircut_admits(c["mu"], c["se"], k)]
        rm = [c for c in u if not haircut_admits(c["mu"], c["se"], k)]
        per_era[era] = {
            "current": _set_stats(u, horizon),
            "haircut": _set_stats(kp, horizon),
            "removed": _set_stats(rm, horizon),
        }
    return {
        "horizon": horizon,
        "k": k,
        "n_universe_dates": len({c["run_date"] for c in uni}),
        "current": cur,
        "haircut": hc,
        "removed": rem,
        "winners_removed": rem["n_winners"],
        "losers_removed": rem["n_losers"],
        "expectancy_delta_haircut_minus_current": delta,
        "per_regime": per_regime,
        "per_era": per_era,
    }


def block_bootstrap_delta(
    cands: list[dict], horizon: str, k: float, block_len: int,
    n_boot: int = N_BOOT, seed: int = SEED,
) -> dict:
    """Circular block bootstrap over the DATE axis of the expectancy delta.
    If block_len >= n_dates every draw is a rotation of the full sample and
    the CI is degenerate (zero width) - flagged, not hidden."""
    uni = replay_universe(cands, horizon)
    by_date: dict[str, list[dict]] = defaultdict(list)
    for c in uni:
        by_date[c["run_date"]].append(c)
    dates = sorted(by_date)
    n = len(dates)
    if n == 0:
        return {"block_len": block_len, "n_dates": 0, "ci": None, "degenerate": True}
    rng = random.Random(seed + block_len + int(k * 10))
    deltas, skipped = [], 0
    n_blocks = math.ceil(n / block_len)
    for _ in range(n_boot):
        sample_dates: list[str] = []
        for _b in range(n_blocks):
            start = rng.randrange(n)
            for off in range(block_len):
                sample_dates.append(dates[(start + off) % n])
        sample_dates = sample_dates[:n]
        pool = [c for d in sample_dates for c in by_date[d]]
        cur_ex = [c[f"excess_{horizon}"] for c in pool]
        hc_ex = [
            c[f"excess_{horizon}"] for c in pool
            if haircut_admits(c["mu"], c["se"], k)
        ]
        if not cur_ex or not hc_ex:
            skipped += 1
            continue
        deltas.append(sum(hc_ex) / len(hc_ex) - sum(cur_ex) / len(cur_ex))
    if not deltas:
        return {"block_len": block_len, "n_dates": n, "ci": None,
                "degenerate": True, "n_skipped": skipped}
    deltas.sort()
    lo = deltas[max(0, int(0.025 * len(deltas)) - 1)]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {
        "block_len": block_len,
        "n_dates": n,
        "n_boot_effective": len(deltas),
        "n_skipped": skipped,
        "ci95": [lo, hi],
        "median": deltas[len(deltas) // 2],
        "degenerate": block_len >= n,
    }


def passthrough_sensitivity(cands: list[dict], horizon: str, k: float) -> dict:
    """Alternative treatment of undefined-SE names: the haircut PASSES them
    through (a production rule would need this or fail-closed). Universe =
    all floor-clearing resolved names regardless of SE."""
    uni = [
        c for c in cands
        if c["mu"] > FLOOR and c.get(f"excess_{horizon}") is not None
    ]
    kept = [
        c for c in uni
        if c.get("se") is None or haircut_admits(c["mu"], c["se"], k)
    ]
    removed = [c for c in uni if c not in kept]
    cur, hc, rem = (_set_stats(s, horizon) for s in (uni, kept, removed))
    delta = (
        hc["mean_excess"] - cur["mean_excess"]
        if hc["mean_excess"] is not None and cur["mean_excess"] is not None
        else None
    )
    return {
        "treatment": "undefined_se_passthrough",
        "horizon": horizon, "k": k,
        "n_undefined_se_passed": sum(1 for c in kept if c.get("se") is None),
        "current": cur, "haircut": hc, "removed": rem,
        "expectancy_delta_haircut_minus_current": delta,
    }


def strided_subsample(cands: list[dict], horizon: str, k: float,
                      stride_days: int) -> dict:
    """Honest-call sensitivity: overlapping fwd windows -> greedily keep
    decision dates >= stride_days calendar days apart. Tiny n, flagged."""
    uni = replay_universe(cands, horizon)
    dates = sorted({c["run_date"] for c in uni})
    keep_dates, last = [], None
    for d in dates:
        dd = _date.fromisoformat(d)
        if last is None or (dd - last).days >= stride_days:
            keep_dates.append(d)
            last = dd
    sub = [c for c in uni if c["run_date"] in set(keep_dates)]
    kept = [c for c in sub if haircut_admits(c["mu"], c["se"], k)]
    removed = [c for c in sub if not haircut_admits(c["mu"], c["se"], k)]
    cur, hc, rem = (_set_stats(s, horizon) for s in (sub, kept, removed))
    return {
        "stride_days": stride_days, "kept_dates": keep_dates,
        "current": cur, "haircut": hc, "removed": rem,
        "expectancy_delta_haircut_minus_current": (
            hc["mean_excess"] - cur["mean_excess"]
            if hc["mean_excess"] is not None and cur["mean_excess"] is not None
            else None
        ),
    }


# ------------------------------------- admission composition (no outcomes)
def admission_composition(cands: list[dict]) -> dict:
    """AC check 'thin-margin buys -> ~0' needs no forward returns: over ALL
    canonical dates (incl. outcome-unresolved recent ones), what does each
    rule admit and how thin is it?"""
    floor_clearing = [c for c in cands if c["mu"] > FLOOR]
    with_se = [c for c in floor_clearing if c.get("se") is not None]
    out = {
        "n_floor_clearing": len(floor_clearing),
        "n_floor_clearing_with_se": len(with_se),
        "n_dates": len({c["run_date"] for c in floor_clearing}),
        "thin_margin_share_current": (
            sum(1 for c in floor_clearing if is_thin_margin(c["mu"]))
            / len(floor_clearing) if floor_clearing else None
        ),
        "margin_over_se_quantiles": None,
        "per_k": {},
    }
    if with_se:
        ratios = sorted((c["mu"] - FLOOR) / c["se"] for c in with_se if c["se"] > 0)
        if ratios:
            q = lambda p: ratios[min(len(ratios) - 1, int(p * len(ratios)))]
            out["margin_over_se_quantiles"] = {
                "p10": q(0.10), "p25": q(0.25), "p50": q(0.50),
                "p75": q(0.75), "p90": q(0.90),
            }
    for k in K_LIST:
        kept = [c for c in with_se if haircut_admits(c["mu"], c["se"], k)]
        out["per_k"][str(k)] = {
            "n_admitted": len(kept),
            "admitted_share_of_with_se": (
                len(kept) / len(with_se) if with_se else None
            ),
            "n_thin_margin_admitted": sum(1 for c in kept if is_thin_margin(c["mu"])),
            "thin_margin_share_admitted": (
                sum(1 for c in kept if is_thin_margin(c["mu"])) / len(kept)
                if kept else None
            ),
        }
    return out


def fixture_cases(cands: list[dict]) -> list[dict]:
    """OXY/GRMN on the RS-2/POC-B forensic dates: what would each rule do?
    Outcomes are forward-unresolved (too recent) - admission verdict only."""
    out = []
    for c in cands:
        if c["ticker"] in FIXTURE_TICKERS and c["run_date"] in FIXTURE_DATES:
            row = {
                "ticker": c["ticker"], "run_date": c["run_date"],
                "mu": c["mu"], "se": c.get("se"), "n_obs": c.get("n_obs"),
                "era": c["era"], "clears_floor": c["mu"] > FLOOR,
                "thin_margin": is_thin_margin(c["mu"]),
                "blocked_by": c["blocked_by"],
            }
            for k in K_LIST:
                row[f"haircut_admits_k{k}"] = (
                    haircut_admits(c["mu"], c["se"], k)
                    if c.get("se") is not None else None
                )
            out.append(row)
    return sorted(out, key=lambda r: (r["run_date"], r["ticker"]))


def calibrator_band_proxy(path: str, cands: list[dict]) -> dict:
    """Proxy (b). The calibrator JSON persists point knots + global metadata
    only - NO per-name band. The only global uncertainty figure derivable is
    er_std*sqrt(1-pool_ic^2). Applied as a constant SE it is per-name-blind:
    equivalent to raising the floor to floor + k*resid, nothing more."""
    try:
        with open(path) as f:
            cal = json.load(f)
    except OSError as e:
        return {"available": False, "error": str(e)}
    meta = cal.get("metadata", {})
    er_std = meta.get("er_std")
    ic = meta.get("pool_ic")
    if er_std is None or ic is None:
        return {"available": False, "error": "no er_std/pool_ic in metadata"}
    resid = er_std * math.sqrt(max(0.0, 1.0 - ic * ic))
    floor_clearing = [c for c in cands if c["mu"] > FLOOR]
    per_k = {}
    for k in K_LIST:
        per_k[str(k)] = {
            "n_admitted": sum(
                1 for c in floor_clearing if (c["mu"] - k * resid) > FLOOR
            ),
            "n_floor_clearing": len(floor_clearing),
        }
    return {
        "available": True,
        "calibrator_path": path,
        "calibrator_trained_date": cal.get("trained_date"),
        "calibrator_lookahead_days": meta.get("lookahead_days"),
        "note": (
            "vintage mismatch: this calibrator was trained after most of the "
            "replay window; no per-name band is persisted, so this is a "
            "single GLOBAL constant on the calibrator's 5d-label scale, not "
            "mu's 60d scale. A constant SE is per-name-blind: the 'haircut' "
            "degenerates to raising the floor to floor + k*resid (0.053 at "
            "k=0.5, 0.076 at k=1.0) - a blunt floor raise, not an "
            "uncertainty-sensitive rule"
        ),
        "er_std": er_std,
        "pool_ic": ic,
        "global_residual_std_proxy": resid,
        "per_k": per_k,
    }


# --------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--calibrator", default=DEFAULT_CALIBRATOR)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    args = ap.parse_args(argv)

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    runs = canonical_daily_runs(con)
    cands = load_candidates(con, runs)
    attach_se(cands)
    coverage = attach_outcomes(con, cands)

    n_floor = sum(1 for c in cands if c["mu"] > FLOOR)
    n_floor_se = sum(1 for c in cands if c["mu"] > FLOOR and c.get("se") is not None)

    replays, bootstraps, passthroughs, strides = {}, {}, {}, {}
    for h in HORIZONS:
        for k in K_LIST:
            key = f"{h}_k{k}"
            replays[key] = replay(cands, h, k)
            bootstraps[key] = {
                f"block{bl}": block_bootstrap_delta(cands, h, k, bl, args.n_boot)
                for bl in (BLOCK_LEN, *BLOCK_SENS)
            }
            if h in ("fwd_20d", "fwd_10d"):
                passthroughs[key] = passthrough_sensitivity(cands, h, k)
                strides[key] = strided_subsample(
                    cands, h, k, stride_days=28 if h == "fwd_20d" else 14
                )

    main_out = {
        "study": "M3 conviction uncertainty-haircut ledger replay",
        "date": "2026-07-02",
        "read_only": True,
        "db": args.db,
        "params": {
            "floor": FLOOR, "k_list": list(K_LIST), "window_obs": WINDOW_OBS,
            "min_obs": MIN_OBS, "cost_proxy": COST_PROXY,
            "thin_margin_band": [FLOOR, THIN_HI],
            "block_len_primary": BLOCK_LEN, "block_len_sensitivity": list(BLOCK_SENS),
            "n_boot": args.n_boot, "seed": SEED,
            "min_full_run_candidates": MIN_FULL_RUN_CANDIDATES,
        },
        "se_proxy": {
            "primary": (
                "(a) cross-run dispersion: era-stratified trailing stdev of the "
                "ticker's mu over <=10 canonical daily runs (>=3 obs); a "
                "STABILITY proxy computable at decision time, NOT a sampling SE"
            ),
            "sensitivity": "(b) calibrator global residual - see calibrator_band_proxy",
        },
        "canonical_runs": runs,
        "counts": {
            "n_canonical_dates": len(runs),
            "n_candidate_rows_with_mu": len(cands),
            "n_floor_clearing": n_floor,
            "n_floor_clearing_with_se": n_floor_se,
            "se_coverage_of_floor_clearing": (n_floor_se / n_floor) if n_floor else None,
        },
        "outcome_coverage": coverage,
        "honest_calls": {
            "horizon_mismatch": (
                "mu_horizon_days=60 but fwd_60d is unresolvable for the entire "
                "live window; primary outcome is fwd_20d excess vs SPY - a "
                "60d-mu judged on 20d outcomes"
            ),
            "unvalidated_model": (
                "this replays the HISTORICAL mu stream's ordering; D1 (model "
                "verdict) is pending - a haircut win here does not validate mu"
            ),
            "overlapping_horizons": (
                "consecutive decision dates share forward windows; primary "
                "correction = date-block bootstrap, plus strided subsample "
                "sensitivity (tiny n, flagged)"
            ),
            "block13_degenerate": (
                "block_len=13 >= n usable dates for fwd_20d -> the spec'd "
                "block-13 CI is degenerate by construction; block-5/1 shown"
            ),
            "survivorship": (
                "universe = names actually scored by live runs; names that "
                "left the watchlist keep their stamped forward returns, but "
                "the watchlist itself is winner-biased (survivorship not "
                "correctable from this ledger alone)"
            ),
            "se_proxy_limits": (
                "cross-run mu dispersion conflates sampling noise with real "
                "information arrival, feature drift and within-era retrains; "
                "era-stratification removes only the coarse scorer swaps"
            ),
        },
        "replays": replays,
        "bootstrap": bootstraps,
        "passthrough_sensitivity": passthroughs,
        "strided_sensitivity": strides,
        "calibrator_band_proxy": calibrator_band_proxy(args.calibrator, cands),
    }

    comp_out = admission_composition(cands)
    fix_out = {
        "note": (
            "RS-2/POC-B forensic fixtures; outcomes forward-unresolved on "
            "these dates - admission verdicts only"
        ),
        "cases": fixture_cases(cands),
    }

    os.makedirs(args.out_dir, exist_ok=True)
    for name, obj in (
        ("m3_haircut_replay.json", main_out),
        ("m3_admission_composition.json", comp_out),
        ("m3_fixture_cases.json", fix_out),
    ):
        with open(os.path.join(args.out_dir, name), "w") as f:
            json.dump(obj, f, indent=1, sort_keys=False)
            f.write("\n")

    # ------------------------------------------------------------- summary
    print(f"canonical dates: {len(runs)}   floor-clearing rows: {n_floor} "
          f"(with SE: {n_floor_se})")
    for h in HORIZONS:
        for k in K_LIST:
            r = replays[f"{h}_k{k}"]
            b = bootstraps[f"{h}_k{k}"]
            ci5 = b.get("block5", {}).get("ci95")
            print(
                f"{h} k={k}: universe n={r['current']['n']} "
                f"({r['n_universe_dates']} dates) | removed "
                f"{r['removed']['n']} (winners {r['winners_removed']} / "
                f"losers {r['losers_removed']}) | delta "
                f"{r['expectancy_delta_haircut_minus_current']} | "
                f"block5 CI {ci5}"
            )
    print("admission composition:", json.dumps(comp_out["per_k"]))
    print("fixtures:", json.dumps(fix_out["cases"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
