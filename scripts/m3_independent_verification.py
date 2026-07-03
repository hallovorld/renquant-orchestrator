#!/usr/bin/env python3
"""M3 uncertainty-haircut AC-FAIL verdict: INDEPENDENT ADVERSARIAL VERIFICATION.

Re-derives the M3 replay (doc/research/2026-07-02-m3-haircut-replay.md,
scripts/m3_haircut_replay.py) from scratch -- own SQL, own SE proxy code, own
outcome computation (fwd returns recomputed from the ohlcv parquets, not
trusted from ticker_forward_returns), own bootstrap (exact enumeration where
feasible, multi-seed Monte Carlo otherwise) -- and stress-tests every small
implementation choice that could flip a CI that barely excludes zero:

  C1  headline harm claim (fwd_20d k=1.0: delta -0.51pp, block-5 CI
      excluding 0): reproduction + sensitivity grid over ddof, window
      inclusion, era stratification, min-obs, dedup rule, run threshold,
      outcome source, outcome window, weekend handling.
  C2  "removed set were winners" mechanism (+5.9% vs +3.9%): reproduction +
      ticker-concentration / cluster-bootstrap analysis.
  C3  POSITIVE CONTROL (absent from the original): plant synthetic outcomes
      where high-dispersion names ARE losers and verify this harness detects
      the haircut helping; plus a within-date permutation NULL control for
      empirical size.
  C4  thin-margin orthogonality (margin/SE p50=1.28; thin share 20-24%):
      recomputation of the joint distribution.
  C5  multiple comparisons: exact bootstrap tail masses for all 6
      horizon x k cells; Bonferroni/Sidak read on 1-of-6 nominal
      significance.

READ-ONLY: sqlite opened mode=ro; ohlcv parquets only read. No config or
behavior change. Reproduce:

  python3 scripts/m3_independent_verification.py

Outputs: doc/research/evidence/2026-07-03-m3-verification/*.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import date as _date
from datetime import timedelta

import numpy as np
import pandas as pd

# --------------------------------------------------------------- constants
# Deliberately identical to the original study where the SPEC is shared, so
# that differences in results isolate implementation choices, not parameters.
FLOOR = 0.03
K_LIST = (0.5, 1.0)
WINDOW_OBS = 10
MIN_OBS = 3
THIN_HI = 0.0375
COST_PROXY = 0.0011
N_BOOT = 5000
MC_SEEDS = tuple(range(11, 21))       # deliberately != original seed 20260702
ORIG_SEED = 20260702                  # used ONLY for the 1:1 reproduction cell
MIN_FULL_RUN_CANDIDATES = 40
HORIZONS = {"fwd_20d": 20, "fwd_10d": 10, "fwd_5d": 5}
MAX_EFFDATE_LAG_DAYS = 4
EXACT_ENUM_LIMIT = 300_000            # max block-start tuples to enumerate

DB = "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"
OHLCV_DIR = "/Users/renhao/git/github/RenQuant/data/ohlcv"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(
    _REPO_ROOT, "doc", "research", "evidence", "2026-07-03-m3-verification"
)

_LEGACY = {"Classification", "Manual", "QLearning", "XGBoost"}


def era_of(model_type, mode: str) -> str:
    if mode == "none":
        return "all"
    if model_type is None or model_type == "":
        return "pre_tournament_null"
    if mode == "fine":
        return str(model_type)
    return "legacy_tournament" if model_type in _LEGACY else str(model_type)


# ------------------------------------------------------------ trading calendar
class Calendar:
    """SPY parquet index = the trading calendar (independent of the DB)."""

    def __init__(self, ohlcv_dir: str = OHLCV_DIR):
        spy = pd.read_parquet(os.path.join(ohlcv_dir, "SPY", "1d.parquet"))
        self.days = [d.date().isoformat() for d in spy.index]
        self._set = set(self.days)

    def eff_date(self, run_date: str) -> str | None:
        """Latest trading day <= run_date (weekend runs -> prior Friday)."""
        if run_date in self._set:
            return run_date
        d = _date.fromisoformat(run_date)
        for lag in range(1, MAX_EFFDATE_LAG_DAYS + 1):
            c = (d - timedelta(days=lag)).isoformat()
            if c in self._set:
                return c
        return None

    def is_trading_day(self, run_date: str) -> bool:
        return run_date in self._set


# --------------------------------------------------------------- run dedup
def canonical_runs(con, cal: Calendar, thr: int = MIN_FULL_RUN_CANDIDATES,
                   mode: str = "their_latest") -> list[dict]:
    """One canonical run per (run_date | eff trading date).

    modes:
      their_latest  - original rule: per run_date, latest created_at among
                      live runs with >= thr candidate rows (mu NOT required).
      latest_mu     - per run_date, latest created_at among live runs with
                      >= thr candidate rows AND >= 1 mu row. (The original
                      rule silently selects a 0-mu run on 2026-05-08.)
      eff_latest_mu - key by effective TRADING date (weekend runs compete
                      with the Friday runs they duplicate); latest
                      created_at mu-bearing qualifying run wins.
    """
    rows = con.execute(
        """
        SELECT p.run_id, p.run_date, COALESCE(p.regime,'UNKNOWN'), p.created_at,
          (SELECT COUNT(*) FROM candidate_scores c
           WHERE c.run_id=p.run_id AND c.role='candidate') n_cand,
          (SELECT COUNT(*) FROM candidate_scores c
           WHERE c.run_id=p.run_id AND c.role='candidate' AND c.mu IS NOT NULL) n_mu
        FROM pipeline_runs p WHERE p.run_type='live'
        ORDER BY p.run_date, p.created_at
        """
    ).fetchall()
    by_key: dict[str, tuple] = {}
    for run_id, run_date, regime, created_at, n_cand, n_mu in rows:
        if n_cand < thr:
            continue
        if mode in ("latest_mu", "eff_latest_mu") and n_mu == 0:
            continue
        key = cal.eff_date(run_date) if mode == "eff_latest_mu" else run_date
        if key is None:
            continue
        by_key[key] = (run_id, regime, created_at, run_date)  # later created_at wins
    return [
        {"run_date": k, "run_id": v[0], "regime": v[1], "src_run_date": v[3]}
        for k, v in sorted(by_key.items())
    ]


def load_mu_rows(con, runs: list[dict]) -> list[dict]:
    out = []
    for r in runs:
        for tkr, mu, model_type in con.execute(
            "SELECT ticker, mu, model_type FROM candidate_scores "
            "WHERE run_id=? AND role='candidate' AND mu IS NOT NULL",
            (r["run_id"],),
        ):
            out.append({
                "run_date": r["run_date"], "run_id": r["run_id"],
                "regime": r["regime"], "ticker": tkr, "mu": float(mu),
                "model_type": model_type,
            })
    return out


# ------------------------------------------------------------------ SE proxy
def attach_se(rows: list[dict], *, ddof: int = 1, include_current: bool = True,
              era_mode: str = "coarse", min_obs: int = MIN_OBS,
              window_obs: int = WINDOW_OBS) -> None:
    """Era-stratified trailing cross-run dispersion of mu, per (ticker, date).

    ddof=1 + include_current + era_mode='coarse' reproduces the original
    spec; the flags are the adversarial sensitivity axes.
    """
    for c in rows:
        c["era"] = era_of(c["model_type"], era_mode)
    stream: dict[str, list[dict]] = defaultdict(list)
    for c in rows:
        stream[c["ticker"]].append(c)
    for tkr, rr in stream.items():
        rr.sort(key=lambda x: x["run_date"])
        for i, c in enumerate(rr):
            start = i if include_current else i - 1
            window: list[float] = []
            for j in range(start, -1, -1):
                if rr[j]["era"] != c["era"]:
                    break
                window.append(rr[j]["mu"])
                if len(window) >= window_obs:
                    break
            c["n_obs"] = len(window)
            if len(window) >= min_obs:
                arr = np.asarray(window)
                c["se"] = float(arr.std(ddof=ddof))
            else:
                c["se"] = None


# ------------------------------------------------------------------ outcomes
class ParquetOutcomes:
    """fwd_h excess vs SPY recomputed from ohlcv parquets (close-to-close,
    trading-day offsets). Independent of ticker_forward_returns."""

    def __init__(self, cal: Calendar, ohlcv_dir: str = OHLCV_DIR):
        self.cal = cal
        self.dir = ohlcv_dir
        self._series: dict[str, pd.Series | None] = {}

    def _close(self, ticker: str) -> pd.Series | None:
        if ticker not in self._series:
            p = os.path.join(self.dir, ticker, "1d.parquet")
            if os.path.exists(p):
                df = pd.read_parquet(p, columns=["close"])
                s = df["close"]
                s.index = [d.date().isoformat() for d in df.index]
                self._series[ticker] = s
            else:
                self._series[ticker] = None
        return self._series[ticker]

    def fwd(self, ticker: str, eff: str, h_days: int) -> float | None:
        s = self._close(ticker)
        if s is None or eff not in s.index:
            return None
        i = s.index.get_loc(eff)
        j = i + h_days
        if j >= len(s):
            return None
        c0, c1 = float(s.iloc[i]), float(s.iloc[j])
        if not (c0 > 0 and math.isfinite(c0) and math.isfinite(c1)):
            return None
        return c1 / c0 - 1.0

    def excess(self, ticker: str, run_date: str, horizon: str) -> float | None:
        eff = self.cal.eff_date(run_date)
        if eff is None:
            return None
        h = HORIZONS[horizon]
        tv, sv = self.fwd(ticker, eff, h), self.fwd("SPY", eff, h)
        if tv is None or sv is None:
            return None
        return tv - sv


class ParquetTotalReturnOutcomes(ParquetOutcomes):
    """Total-return variant: adds dividends paid in (t, t+h] to the terminal
    price (no reinvestment -- second-order at 20d). Both legs adjusted, so
    only DIFFERENTIAL dividend timing vs SPY moves the excess."""

    def __init__(self, cal: Calendar, ohlcv_dir: str = OHLCV_DIR):
        super().__init__(cal, ohlcv_dir)
        self._div: dict[str, pd.Series | None] = {}

    def _dividends(self, ticker: str) -> pd.Series | None:
        if ticker not in self._div:
            p = os.path.join(self.dir, ticker, "1d.parquet")
            if os.path.exists(p):
                df = pd.read_parquet(p)
                if "dividend" in df.columns:
                    s = df["dividend"]
                else:  # some tickers have no dividend column: treat as 0
                    s = pd.Series(0.0, index=df.index)
                s.index = [d.date().isoformat() for d in df.index]
                self._div[ticker] = s
            else:
                self._div[ticker] = None
        return self._div[ticker]

    def fwd(self, ticker: str, eff: str, h_days: int) -> float | None:
        s = self._close(ticker)
        d = self._dividends(ticker)
        if s is None or d is None or eff not in s.index:
            return None
        i = s.index.get_loc(eff)
        j = i + h_days
        if j >= len(s):
            return None
        c0, c1 = float(s.iloc[i]), float(s.iloc[j])
        if not (c0 > 0 and math.isfinite(c0) and math.isfinite(c1)):
            return None
        div_sum = float(d.iloc[i + 1:j + 1].fillna(0.0).sum())
        return (c1 + div_sum) / c0 - 1.0


class DBOutcomes:
    """Original source: ticker_forward_returns (for the 1:1 reproduction and
    the source-sensitivity comparison)."""

    def __init__(self, con, cal: Calendar):
        self.con = con
        self.cal = cal
        self._cache: dict[tuple, tuple | None] = {}

    def _row(self, ticker: str, eff: str):
        key = (ticker, eff)
        if key not in self._cache:
            self._cache[key] = self.con.execute(
                "SELECT fwd_20d, fwd_10d, fwd_5d FROM ticker_forward_returns "
                "WHERE ticker=? AND as_of_date=?", (ticker, eff)).fetchone()
        return self._cache[key]

    def excess(self, ticker: str, run_date: str, horizon: str) -> float | None:
        eff = self.cal.eff_date(run_date)
        if eff is None:
            return None
        idx = {"fwd_20d": 0, "fwd_10d": 1, "fwd_5d": 2}[horizon]
        t, s = self._row(ticker, eff), self._row("SPY", eff)
        if not t or not s or t[idx] is None or s[idx] is None:
            return None
        return float(t[idx]) - float(s[idx])


# ------------------------------------------------------------------- replay
def build_universe(rows, horizon, outcomes, max_eff_date: str | None,
                   cal: Calendar) -> list[dict]:
    uni = []
    for c in rows:
        if not (c["mu"] > FLOOR and c.get("se") is not None):
            continue
        eff = cal.eff_date(c["run_date"])
        if eff is None or (max_eff_date is not None and eff > max_eff_date):
            continue
        ex = outcomes.excess(c["ticker"], c["run_date"], horizon)
        if ex is None:
            continue
        d = dict(c)
        d["eff"] = eff
        d["excess"] = ex
        uni.append(d)
    return uni


def admits(c, k: float) -> bool:
    return (c["mu"] - k * c["se"]) > FLOOR


def set_stats(rows) -> dict:
    if not rows:
        return {"n": 0, "mean_excess": None, "n_winners": 0, "n_losers": 0,
                "winner_rate": None}
    ex = [r["excess"] for r in rows]
    w = sum(1 for e in ex if e > COST_PROXY)
    return {"n": len(ex), "mean_excess": float(np.mean(ex)), "n_winners": w,
            "n_losers": len(ex) - w, "winner_rate": w / len(ex)}


def replay_cell(uni, k: float) -> dict:
    kept = [c for c in uni if admits(c, k)]
    removed = [c for c in uni if not admits(c, k)]
    cur, hc, rem = set_stats(uni), set_stats(kept), set_stats(removed)
    return {
        "n_universe": cur["n"],
        "n_dates": len({c["run_date"] for c in uni}),
        "n_removed": rem["n"], "winners_removed": rem["n_winners"],
        "losers_removed": rem["n_losers"],
        "removed_mean_excess": rem["mean_excess"],
        "kept_mean_excess": hc["mean_excess"],
        "universe_mean_excess": cur["mean_excess"],
        "universe_winner_rate": cur["winner_rate"],
        "removed_winner_rate": rem["winner_rate"],
        "delta_pp": (
            round((hc["mean_excess"] - cur["mean_excess"]) * 1e4) / 1e2
            if hc["mean_excess"] is not None and cur["mean_excess"] is not None
            else None),
    }


# --------------------------------------------------------------- bootstrap
def per_date_agg(uni, k: float):
    agg: dict[str, list[float]] = {}
    for c in uni:
        a = agg.setdefault(c["run_date"], [0.0, 0, 0.0, 0])
        a[0] += c["excess"]
        a[1] += 1
        if admits(c, k):
            a[2] += c["excess"]
            a[3] += 1
    dates = sorted(agg)
    A = np.array([[agg[d][0], agg[d][1], agg[d][2], agg[d][3]] for d in dates])
    return dates, A


def _delta_from_counts(sumA, nA, sumK, nK) -> float | None:
    if nA == 0 or nK == 0:
        return None
    return sumK / nK - sumA / nA


def exact_block_bootstrap(dates, A, block_len: int) -> dict:
    """The circular block bootstrap sample is fully determined by the tuple
    of block starts (each uniform on n, ceil(n/block_len) blocks, truncated
    to n dates). When n^n_blocks is enumerable the bootstrap distribution is
    EXACT -- no Monte Carlo noise, no seed, no quantile-indexing convention.
    Significance reduces to exact tail masses P(delta>=0) / P(delta<=0)."""
    n = len(dates)
    n_blocks = math.ceil(n / block_len)
    n_tuples = n ** n_blocks
    if n == 0 or n_tuples > EXACT_ENUM_LIMIT:
        return {"exact": False, "n_dates": n, "n_tuples": n_tuples}
    # contribution (how many dates) of each block after truncation
    lens = [block_len] * n_blocks
    lens[-1] = n - block_len * (n_blocks - 1)
    deltas, skipped = [], 0
    for starts in itertools.product(range(n), repeat=n_blocks):
        sumA = nA = sumK = nK = 0.0
        for b, s in enumerate(starts):
            for off in range(lens[b]):
                r = A[(s + off) % n]
                sumA += r[0]; nA += r[1]; sumK += r[2]; nK += r[3]
        d = _delta_from_counts(sumA, nA, sumK, nK)
        if d is None:
            skipped += 1
        else:
            deltas.append(d)
    deltas = np.sort(np.array(deltas))
    m = len(deltas)
    p_ge0 = float(np.sum(deltas >= 0)) / m
    p_le0 = float(np.sum(deltas <= 0)) / m
    return {
        "exact": True, "n_dates": n, "block_len": block_len,
        "n_tuples": n_tuples, "n_skipped_empty": skipped,
        "delta_min": float(deltas[0]), "delta_max": float(deltas[-1]),
        "ci95_lower_interp": float(np.percentile(deltas, 2.5)),
        "ci95_upper_interp": float(np.percentile(deltas, 97.5)),
        "p_ge_0": p_ge0, "p_le_0": p_le0,
        "two_sided_p": min(1.0, 2 * min(p_ge0, p_le0)),
        "ci_excludes_0_upper": p_ge0 <= 0.025,
        "ci_excludes_0_lower": p_le0 <= 0.025,
        "n_atoms_ge_0": int(np.sum(deltas >= 0)),
    }


def mc_block_bootstrap(dates, A, block_len: int, seed: int,
                       n_boot: int = N_BOOT) -> dict:
    n = len(dates)
    if n == 0:
        return {"n_dates": 0}
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block_len)
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    deltas = []
    lens = [block_len] * n_blocks
    lens[-1] = n - block_len * (n_blocks - 1)
    for row in starts:
        sumA = nA = sumK = nK = 0.0
        for b, s in enumerate(row):
            for off in range(lens[b]):
                r = A[(s + off) % n]
                sumA += r[0]; nA += r[1]; sumK += r[2]; nK += r[3]
        d = _delta_from_counts(sumA, nA, sumK, nK)
        if d is not None:
            deltas.append(d)
    deltas = np.sort(np.array(deltas))
    return {
        "seed": seed, "block_len": block_len, "n_dates": n,
        "ci95": [float(np.percentile(deltas, 2.5)),
                 float(np.percentile(deltas, 97.5))],
        "p_ge_0": float(np.mean(deltas >= 0)),
    }


def original_mc_block5(dates, A, k: float, n_boot: int = N_BOOT) -> dict:
    """1:1 re-implementation of the ORIGINAL script's block-5 draw loop,
    RNG (random.Random), seed derivation and quantile indexing -- to verify
    their reported CI is reproducible before diverging from it."""
    n = len(dates)
    rng = random.Random(ORIG_SEED + 5 + int(k * 10))
    n_blocks = math.ceil(n / 5)
    deltas = []
    for _ in range(n_boot):
        sample = []
        for _b in range(n_blocks):
            s = rng.randrange(n)
            for off in range(5):
                sample.append((s + off) % n)
        sample = sample[:n]
        sumA = nA = sumK = nK = 0.0
        for idx in sample:
            r = A[idx]
            sumA += r[0]; nA += r[1]; sumK += r[2]; nK += r[3]
        d = _delta_from_counts(sumA, nA, sumK, nK)
        if d is not None:
            deltas.append(d)
    deltas.sort()
    lo = deltas[max(0, int(0.025 * len(deltas)) - 1)]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {"ci95_their_indexing": [lo, hi],
            "p_ge_0": sum(1 for d in deltas if d >= 0) / len(deltas)}


def jackknife_dates(uni, k: float) -> list[dict]:
    dates = sorted({c["run_date"] for c in uni})
    out = []
    for d in dates:
        sub = [c for c in uni if c["run_date"] != d]
        kept = [c for c in sub if admits(c, k)]
        if not sub or not kept:
            continue
        delta = float(np.mean([c["excess"] for c in kept])
                      - np.mean([c["excess"] for c in sub]))
        out.append({"left_out": d, "delta_pp": round(delta * 1e4) / 1e2})
    return out


def ticker_cluster_bootstrap(uni, k: float, seed: int = 7,
                             n_boot: int = 10_000) -> dict:
    """Resample TICKERS (the other clustering axis: the same name's
    overlapping forward windows repeat across dates) with replacement."""
    by_t: dict[str, list[dict]] = defaultdict(list)
    for c in uni:
        by_t[c["ticker"]].append(c)
    tickers = sorted(by_t)
    nt = len(tickers)
    pre = {}
    for t in tickers:
        rr = by_t[t]
        pre[t] = (
            sum(c["excess"] for c in rr), len(rr),
            sum(c["excess"] for c in rr if admits(c, k)),
            sum(1 for c in rr if admits(c, k)),
        )
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, nt, size=(n_boot, nt))
    deltas = []
    for row in draws:
        sumA = nA = sumK = nK = 0.0
        for i in row:
            a = pre[tickers[i]]
            sumA += a[0]; nA += a[1]; sumK += a[2]; nK += a[3]
        d = _delta_from_counts(sumA, nA, sumK, nK)
        if d is not None:
            deltas.append(d)
    deltas = np.sort(np.array(deltas))
    return {
        "n_tickers": nt,
        "ci95": [float(np.percentile(deltas, 2.5)),
                 float(np.percentile(deltas, 97.5))],
        "p_ge_0": float(np.mean(deltas >= 0)),
    }


# ---------------------------------------------------- inference anchors (C1)
def iid_anchor(uni, k: float) -> dict:
    """Naive i.i.d. two-sample anchor for the kept-vs-removed gap. Not the
    right correlation structure (rows cluster by date AND ticker, clustering
    only WIDENS this) but an honest scale check: is the observed 2pp gap
    even large relative to the 13pp cross-sectional noise?"""
    kept = np.array([c["excess"] for c in uni if admits(c, k)])
    rem = np.array([c["excess"] for c in uni if not admits(c, k)])
    if len(kept) < 2 or len(rem) < 2:
        return {}
    gap = float(kept.mean() - rem.mean())
    s = float(np.sqrt(((len(kept) - 1) * kept.var(ddof=1)
                       + (len(rem) - 1) * rem.var(ddof=1))
                      / (len(kept) + len(rem) - 2)))
    se = s * math.sqrt(1 / len(kept) + 1 / len(rem))
    t = gap / se if se > 0 else None
    return {"kept_minus_removed_gap_pp": round(gap * 1e4) / 1e2,
            "pooled_row_std_pp": round(s * 1e4) / 1e2,
            "iid_se_of_gap_pp": round(se * 1e4) / 1e2,
            "iid_t": round(t * 100) / 100 if t is not None else None,
            "note": "clustering by date/ticker only shrinks effective n; "
                    "|t|<1 under the MOST favorable independence assumption"}


def permutation_test(uni, k: float, n_perm: int = 20_000,
                     seed: int = 31) -> dict:
    """Within-date permutation of outcomes across tickers (removal sets
    fixed): valid under within-date exchangeability, and ANTI-conservative
    w.r.t. cross-date ticker dependence (same name's overlapping windows
    repeat across dates), i.e. the TRUE p is at least this large."""
    ex = np.array([c["excess"] for c in uni])
    kept_mask = np.array([admits(c, k) for c in uni])
    dates = sorted({c["run_date"] for c in uni})
    idx_by_date = [np.array([i for i, c in enumerate(uni)
                             if c["run_date"] == d]) for d in dates]
    uni_mean = ex.mean()
    obs_delta = ex[kept_mask].mean() - uni_mean
    rng = np.random.default_rng(seed)
    deltas = np.empty(n_perm)
    exp = ex.copy()
    for p in range(n_perm):
        for idxs in idx_by_date:
            exp[idxs] = ex[idxs][rng.permutation(len(idxs))]
        deltas[p] = exp[kept_mask].mean() - uni_mean
    return {
        "n_perm": n_perm, "observed_delta_pp": round(obs_delta * 1e4) / 1e2,
        "p_one_sided_le_obs": float(np.mean(deltas <= obs_delta)),
        "p_two_sided": float(np.mean(np.abs(deltas) >= abs(obs_delta))),
        "perm_delta_std_pp": round(float(deltas.std()) * 1e4) / 1e2,
    }


# ------------------------------------------------------------- controls (C3)
def _plant_and_test(uni, k: float, target_gap: float, n_reps: int,
                    seed: int, n_perm_inner: int = 400) -> dict:
    """Plant outcomes where high-dispersion names ARE losers, with the
    planted kept-minus-removed gap calibrated to `target_gap`, and noise
    matched to the REAL data (within-date residual std + date-mean std).

    Planting axis = rank of the HAIRCUT DEFICIT k*SE - (mu - floor): the
    smooth noise-correlated quantity the rule thresholds (deficit > 0 ==
    removed). Planting on raw rank(SE) instead requires a ~7x steeper slope
    (the kept/removed rank(SE) gap is only ~0.05) whose injected variance
    swamps the signal -- that mis-design was our first attempt; kept here as
    a documented dead end, not used.

    Detection is measured with BOTH inference engines:
      - exact block-5 CI excluding 0 on the helpful side (their machinery)
      - within-date permutation test, one-sided alpha=0.05 (this study's)"""
    deficit = np.array([k * c["se"] - (c["mu"] - FLOOR) for c in uni])
    rank = deficit.argsort().argsort() / max(1, len(deficit) - 1)  # high=removed-ish
    kept_mask = np.array([admits(c, k) for c in uni])
    gap_rank = float(rank[~kept_mask].mean() - rank[kept_mask].mean())
    slope = target_gap / gap_rank                            # calibration
    ex = np.array([c["excess"] for c in uni])
    dates = sorted({c["run_date"] for c in uni})
    idx_by_date = [np.array([i for i, c in enumerate(uni)
                             if c["run_date"] == d]) for d in dates]
    # real noise scales
    resid = np.concatenate([ex[idxs] - ex[idxs].mean() for idxs in idx_by_date])
    sigma_idio = float(resid.std())
    sigma_date = float(np.std([ex[idxs].mean() for idxs in idx_by_date]))
    rng = np.random.default_rng(seed)
    det_exact, det_perm, deltas = 0, 0, []
    for _ in range(n_reps):
        shock = rng.normal(0.0, sigma_date, size=len(dates))
        synth_ex = 0.04 - slope * (rank - rank.mean()) \
            + rng.normal(0.0, sigma_idio, size=len(ex))
        for di, idxs in enumerate(idx_by_date):
            synth_ex[idxs] += shock[di]
        synth = []
        for i, c in enumerate(uni):
            d = dict(c)
            d["excess"] = float(synth_ex[i])
            synth.append(d)
        dd, A = per_date_agg(synth, k)
        eb = exact_block_bootstrap(dd, A, 5)
        deltas.append(_delta_from_counts(*A.sum(axis=0)))
        if eb.get("exact") and eb["ci_excludes_0_lower"]:
            det_exact += 1
        # inner permutation test (helpful side)
        uni_mean = synth_ex.mean()
        obs = synth_ex[kept_mask].mean() - uni_mean
        perm = np.empty(n_perm_inner)
        tmp = synth_ex.copy()
        for p in range(n_perm_inner):
            for idxs in idx_by_date:
                tmp[idxs] = synth_ex[idxs][rng.permutation(len(idxs))]
            perm[p] = tmp[kept_mask].mean() - uni_mean
        if np.mean(perm >= obs) <= 0.05:
            det_perm += 1
    return {
        "target_kept_minus_removed_gap_pp": round(target_gap * 1e4) / 1e2,
        "planting_rank_gap_removed_minus_kept": round(gap_rank * 1e3) / 1e3,
        "slope_pp": round(slope * 1e4) / 1e2,
        "noise": {"sigma_idio_pp": round(sigma_idio * 1e4) / 1e2,
                  "sigma_date_pp": round(sigma_date * 1e4) / 1e2},
        "n_reps": n_reps,
        "mean_delta_pp": round(float(np.mean(deltas)) * 1e4) / 1e2,
        "power_exact_block5_ci": det_exact / n_reps,
        "power_permutation_test_a05": det_perm / n_reps,
    }


def positive_control(uni, k: float, n_reps: int = 300, seed: int = 99) -> dict:
    """The original study had NO positive control (the lambda-sweep lesson).
    Plant a TRUE 'high-dispersion names are losers' effect at (i) the size
    the study claims to have detected (2pp kept-vs-removed gap, mirrored),
    (ii) 2x, (iii) 4x -- with noise matched to the real data -- and measure
    how often each inference engine detects the haircut HELPING."""
    out = {"design": (
        "synth excess = 0.04 - slope*(rank(haircut deficit k*SE-margin) - "
        "mean) + date shock + idio noise; slope calibrated so "
        "E[kept-removed] hits the target gap; noise scales estimated from "
        "the real universe; same SE, same removal sets as the real replay")}
    for i, gap in enumerate((0.02, 0.04, 0.08)):
        out[f"gap_{int(gap * 1e4)}bps"] = _plant_and_test(
            uni, k, gap, n_reps, seed + i)
    return out


def null_control(uni, k: float, n_reps: int = 400, seed: int = 101) -> dict:
    """Within-date permutation of the REAL outcomes across tickers: the
    haircut's removal choice becomes outcome-irrelevant by construction.
    Fraction of reps where the exact block-5 CI excludes 0 (either side) =
    empirical size of the CI machinery (nominal 5%). NOTE: within-date
    permutation preserves date-level shocks but destroys ticker-level
    cross-date dependence, so this size check is a LOWER bound on the true
    anti-conservativeness."""
    rng = np.random.default_rng(seed)
    ex = np.array([c["excess"] for c in uni])
    idx_by_date: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(uni):
        idx_by_date[c["run_date"]].append(i)
    fp = fp_harm = fp_help = 0
    for _ in range(n_reps):
        synth = [dict(c) for c in uni]
        for d, idxs in idx_by_date.items():
            vals = ex[np.array(idxs)][rng.permutation(len(idxs))]
            for i, v in zip(idxs, vals):
                synth[i]["excess"] = float(v)
        dd, A = per_date_agg(synth, k)
        eb = exact_block_bootstrap(dd, A, 5)
        if not eb.get("exact"):
            continue
        if eb["ci_excludes_0_upper"]:      # CI entirely below 0: "harmful"
            fp_harm += 1
        if eb["ci_excludes_0_lower"]:      # CI entirely above 0: "helpful"
            fp_help += 1
        if eb["ci_excludes_0_lower"] or eb["ci_excludes_0_upper"]:
            fp += 1
    return {"n_reps": n_reps, "false_positive_rate": fp / n_reps,
            "false_positive_rate_harm_side": fp_harm / n_reps,
            "false_positive_rate_help_side": fp_help / n_reps,
            "k": k, "nominal": 0.05, "nominal_per_side": 0.025}


# ------------------------------------------------------- composition (C4)
def composition(rows) -> dict:
    """NOTE on reproducing the original quantiles: statistics.stdev returns
    an EXACT 0.0 for constant windows where numpy returns ~1e-19; the
    original 'se > 0' filter therefore silently dropped 20 constant-window
    rows, ours would keep 11 of them at astronomical ratios. We use a 1e-9
    tolerance (the defensible choice); with the exact-zero convention our
    faithful reimplementation reproduces their published quantiles to the
    last digit."""
    fc = [c for c in rows if c["mu"] > FLOOR]
    with_se = [c for c in fc if c.get("se") is not None]
    ratios = np.array(sorted((c["mu"] - FLOOR) / c["se"]
                             for c in with_se if c["se"] > 1e-9))
    out = {
        "n_floor_clearing": len(fc),
        "n_with_se": len(with_se),
        "thin_share_current": float(np.mean(
            [FLOOR < c["mu"] < THIN_HI for c in fc])) if fc else None,
        "margin_over_se_quantiles": {
            p: float(np.percentile(ratios, q))
            for p, q in (("p10", 10), ("p25", 25), ("p50", 50),
                         ("p75", 75), ("p90", 90))},
        "corr_margin_se_spearman": None,
        "per_k": {},
    }
    if len(with_se) > 2:
        m = pd.Series([c["mu"] - FLOOR for c in with_se])
        s = pd.Series([c["se"] for c in with_se])
        out["corr_margin_se_spearman"] = float(m.corr(s, method="spearman"))
    for k in K_LIST:
        kept = [c for c in with_se if admits(c, k)]
        thin_kept = sum(1 for c in kept if FLOOR < c["mu"] < THIN_HI)
        out["per_k"][str(k)] = {
            "n_admitted": len(kept),
            "thin_share_admitted": thin_kept / len(kept) if kept else None,
        }
    return out


# ------------------------------------------------------------------ pipeline
def run_config(con, cal, pq_out, db_out, *, dedup="their_latest", thr=40,
               ddof=1, include_current=True, era_mode="coarse",
               min_obs=MIN_OBS, window_obs=WINDOW_OBS, source="db",
               max_eff="db_limit", horizon="fwd_20d", k=1.0,
               tr_out=None) -> dict:
    """One full replay under one configuration; returns the cell + exact
    block-5 inference."""
    runs = canonical_runs(con, cal, thr=thr, mode=dedup)
    rows = load_mu_rows(con, runs)
    attach_se(rows, ddof=ddof, include_current=include_current,
              era_mode=era_mode, min_obs=min_obs, window_obs=window_obs)
    outcomes = {"db": db_out, "parquet": pq_out,
                "parquet_tr": tr_out or pq_out}[source]
    if max_eff == "db_limit":
        lim = con.execute(
            "SELECT MAX(as_of_date) FROM ticker_forward_returns "
            f"WHERE {horizon} IS NOT NULL").fetchone()[0]
    else:
        lim = None  # whatever the parquets resolve
    uni = build_universe(rows, horizon, outcomes, lim, cal)
    cell = replay_cell(uni, k)
    dates, A = per_date_agg(uni, k)
    cell["exact_block5"] = exact_block_bootstrap(dates, A, 5)
    cell["universe_dates"] = dates
    return {"cell": cell, "uni": uni, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--n-reps-controls", type=int, default=500)
    args = ap.parse_args(argv)

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cal = Calendar()
    pq_out = ParquetOutcomes(cal)
    tr_out = ParquetTotalReturnOutcomes(cal)
    db_out = DBOutcomes(con, cal)

    results: dict = {"study": "M3 independent adversarial verification",
                     "date": "2026-07-03", "read_only": True}

    # ---------------- C1a: reproduce the original setup exactly (own code)
    base = run_config(con, cal, pq_out, db_out)   # all defaults = their spec
    uni20 = base["uni"]
    dates20, A20 = per_date_agg(uni20, 1.0)
    repro = dict(base["cell"])
    repro["orig_mc_block5_reimpl"] = original_mc_block5(dates20, A20, 1.0)
    repro["mc_block5_seeds"] = [
        mc_block_bootstrap(dates20, A20, 5, s) for s in MC_SEEDS]
    repro["mc_block1_seeds"] = [
        mc_block_bootstrap(dates20, A20, 1, s) for s in MC_SEEDS[:5]]
    repro["exact_block4"] = exact_block_bootstrap(dates20, A20, 4)
    repro["exact_block3"] = exact_block_bootstrap(dates20, A20, 3)
    repro["jackknife_loo_dates"] = jackknife_dates(uni20, 1.0)
    repro["ticker_cluster_bootstrap"] = ticker_cluster_bootstrap(uni20, 1.0)
    repro["iid_anchor"] = iid_anchor(uni20, 1.0)
    repro["permutation_test"] = permutation_test(uni20, 1.0)
    rem = [c for c in uni20 if not admits(c, 1.0)]
    repro["removed_distinct_tickers"] = len({c["ticker"] for c in rem})
    repro["removed_ticker_date_counts"] = {
        t: sum(1 for c in rem if c["ticker"] == t)
        for t in sorted({c["ticker"] for c in rem})}
    rem_w = [c for c in rem if c["excess"] > COST_PROXY]
    repro["removed_winner_distinct_tickers"] = len({c["ticker"] for c in rem_w})
    # winner/loser counts under alternative cost thresholds (label recompute)
    repro["removed_WL_by_cost_bps"] = {
        str(bps): {
            "W": sum(1 for c in rem if c["excess"] > bps / 1e4),
            "L": sum(1 for c in rem if c["excess"] <= bps / 1e4)}
        for bps in (0, 11, 25, 50)}
    # concentration: which removed rows drive the +5.9% removed mean?
    top = sorted(rem, key=lambda c: -c["excess"])[:8]
    repro["removed_top_contributors"] = [
        {"ticker": c["ticker"], "run_date": c["run_date"],
         "excess_pp": round(c["excess"] * 1e4) / 1e2} for c in top]
    rem_sum = sum(c["excess"] for c in rem)
    by_t = defaultdict(float)
    for c in rem:
        by_t[c["ticker"]] += c["excess"]
    top_t = sorted(by_t.items(), key=lambda kv: -kv[1])[:5]
    repro["removed_mean_top5_ticker_share"] = (
        sum(v for _, v in top_t) / rem_sum if rem_sum else None)
    repro["removed_top5_tickers"] = [
        {"ticker": t, "sum_excess_pp": round(v * 1e4) / 1e2}
        for t, v in top_t]
    results["c1_reproduction_fwd20_k1"] = repro

    # ---------------- C1b: sensitivity grid on the headline cell
    variants = {
        "V01_ddof0": dict(ddof=0),
        "V02_exclude_current": dict(include_current=False),
        "V03_era_none": dict(era_mode="none"),
        "V04_era_fine": dict(era_mode="fine"),
        "V05_min_obs4": dict(min_obs=4),
        "V06_min_obs5": dict(min_obs=5),
        "V07_window5": dict(window_obs=5),
        "V08_dedup_latest_mu": dict(dedup="latest_mu"),
        "V09_dedup_eff_latest_mu": dict(dedup="eff_latest_mu"),
        "V10_thr30": dict(thr=30),
        "V11_outcomes_parquet": dict(source="parquet"),
        "V12_outcomes_parquet_extended": dict(source="parquet", max_eff=None),
        "V13_dedup_mu_and_parquet_extended": dict(
            dedup="latest_mu", source="parquet", max_eff=None),
        "V14_eff_dedup_parquet_extended": dict(
            dedup="eff_latest_mu", source="parquet", max_eff=None),
        "V15_outcomes_total_return": dict(source="parquet_tr"),
    }
    grid = {}
    for name, kw in variants.items():
        r = run_config(con, cal, pq_out, db_out, tr_out=tr_out, **kw)
        c = r["cell"]
        eb = c["exact_block5"]
        grid[name] = {
            "n_universe": c["n_universe"], "n_dates": c["n_dates"],
            "winners_removed": c["winners_removed"],
            "losers_removed": c["losers_removed"],
            "delta_pp": c["delta_pp"],
            "removed_mean_excess": c["removed_mean_excess"],
            "kept_mean_excess": c["kept_mean_excess"],
            "exact_p_ge_0": eb.get("p_ge_0"),
            "ci_excludes_0": eb.get("ci_excludes_0_upper"),
            "universe_dates": c["universe_dates"],
        }
    results["c1_sensitivity_grid_fwd20_k1"] = grid

    # DB-vs-parquet outcome agreement on the base universe
    agree = []
    for c in uni20:
        pv = pq_out.excess(c["ticker"], c["run_date"], "fwd_20d")
        if pv is not None:
            agree.append((c["excess"], pv))
    if agree:
        a = np.array(agree)
        flips = int(np.sum((a[:, 0] > COST_PROXY) != (a[:, 1] > COST_PROXY)))
        results["outcome_source_agreement_fwd20"] = {
            "n_compared": len(agree),
            "max_abs_diff": float(np.max(np.abs(a[:, 0] - a[:, 1]))),
            "corr": float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]),
            "winner_label_flips": flips,
        }

    # ---------------- C2: removed-vs-kept mechanism (already in repro cell)
    results["c2_mechanism"] = {
        "removed_mean_excess": repro["removed_mean_excess"],
        "kept_mean_excess": repro["kept_mean_excess"],
        "removed_winner_rate": repro["removed_winner_rate"],
        "universe_winner_rate": repro["universe_winner_rate"],
        "removed_distinct_tickers": repro["removed_distinct_tickers"],
        "removed_winner_distinct_tickers":
            repro["removed_winner_distinct_tickers"],
        "removed_WL_by_cost_bps": repro["removed_WL_by_cost_bps"],
        "removed_top_contributors": repro["removed_top_contributors"],
        "removed_mean_top5_ticker_share":
            repro["removed_mean_top5_ticker_share"],
        "removed_top5_tickers": repro["removed_top5_tickers"],
        "ticker_cluster_bootstrap": repro["ticker_cluster_bootstrap"],
        "iid_anchor": repro["iid_anchor"],
        "permutation_test": repro["permutation_test"],
    }

    # ---------------- C3: positive + null controls
    results["c3_positive_control"] = positive_control(
        uni20, 1.0, n_reps=args.n_reps_controls)
    results["c3_null_control"] = null_control(
        uni20, 1.0, n_reps=args.n_reps_controls)

    # ---------------- C4: thin-margin orthogonality
    results["c4_composition"] = composition(base["rows"])

    # ---------------- C5: all 6 cells, exact inference, multiplicity
    cells = {}
    for h in HORIZONS:
        for k in K_LIST:
            r = run_config(con, cal, pq_out, db_out, tr_out=tr_out,
                           horizon=h, k=k)
            c = r["cell"]
            eb = c["exact_block5"]
            cells[f"{h}_k{k}"] = {
                "n_universe": c["n_universe"], "n_dates": c["n_dates"],
                "winners_removed": c["winners_removed"],
                "losers_removed": c["losers_removed"],
                "delta_pp": c["delta_pp"],
                "exact_p_ge_0": eb.get("p_ge_0"),
                "exact_p_le_0": eb.get("p_le_0"),
                "exact_two_sided_p": eb.get("two_sided_p"),
                "exact_ci_excludes_0": (eb.get("ci_excludes_0_upper")
                                        or eb.get("ci_excludes_0_lower")),
                "exact_enum_n_tuples": eb.get("n_tuples"),
            }
    n_cells = len(cells)
    n_nominal = sum(1 for c in cells.values()
                    if c["exact_two_sided_p"] is not None
                    and c["exact_two_sided_p"] <= 0.05)
    results["c5_all_cells"] = cells
    results["c5_multiplicity"] = {
        "n_cells": n_cells,
        "n_nominally_significant_2sided_05": n_nominal,
        "bonferroni_threshold": 0.05 / n_cells,
        "sidak_familywise_alpha_note": (
            "6 correlated tests at alpha=.05: familywise false-positive "
            "probability up to 1-(0.95^6)=26.5% if independent; the cells "
            "share data so the effective number is lower, but 1-of-6 at the "
            "boundary is unremarkable under the null"),
    }

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "m3_verification.json"), "w") as f:
        json.dump(results, f, indent=1, default=str)
        f.write("\n")

    # ------------------------------------------------------------- summary
    eb = repro["exact_block5"]
    print("=== C1 reproduction (their spec, own code), fwd_20d k=1.0 ===")
    print(f"universe n={repro['n_universe']} dates={repro['n_dates']} "
          f"removed {repro['n_removed']} (W {repro['winners_removed']} / "
          f"L {repro['losers_removed']}) delta {repro['delta_pp']}pp")
    print(f"their-MC-reimpl block5 CI {repro['orig_mc_block5_reimpl']}")
    print(f"EXACT block5: n_tuples={eb['n_tuples']} "
          f"P(delta>=0)={eb['p_ge_0']:.4f} "
          f"({eb['n_atoms_ge_0']} atoms) two-sided p={eb['two_sided_p']:.4f} "
          f"CI excl 0: {eb['ci_excludes_0_upper']}")
    print("jackknife LOO:", repro["jackknife_loo_dates"])
    print("ticker cluster boot:", repro["ticker_cluster_bootstrap"])
    print("iid anchor:", repro["iid_anchor"])
    print("permutation test:", repro["permutation_test"])
    print("removed W/L by cost bps:", repro["removed_WL_by_cost_bps"])
    print("removed top contributors:", repro["removed_top_contributors"])
    print("removed top5 ticker share of mean:",
          repro["removed_mean_top5_ticker_share"])
    print("\n=== C1 sensitivity grid ===")
    for name, g in grid.items():
        print(f"{name}: n={g['n_universe']}/{g['n_dates']}d "
              f"W{g['winners_removed']}/L{g['losers_removed']} "
              f"delta {g['delta_pp']}pp exact_p_ge0 {g['exact_p_ge_0']} "
              f"CIexcl0 {g['ci_excludes_0']}")
    print("\n=== C3 controls ===")
    print("positive:", results["c3_positive_control"])
    print("null:", results["c3_null_control"])
    print("\n=== C4 composition ===")
    print(json.dumps(results["c4_composition"], indent=1))
    print("\n=== C5 all cells ===")
    for name, c in cells.items():
        print(f"{name}: delta {c['delta_pp']}pp p2s {c['exact_two_sided_p']} "
              f"CIexcl0 {c['exact_ci_excludes_0']}")
    print(json.dumps(results["c5_multiplicity"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
