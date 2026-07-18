#!/usr/bin/env python3
"""G2 preregistered historical exercise — crypto reversal costed backtest (H1).

FROZEN LAW: doc/research/2026-07-17-g2-reversal-backtest-prereg.md (merged, sealed
by PR #546 with doc/research/g2-manifest/). This script implements the frozen
construction EXACTLY; every discretionary micro-convention the frozen text does
not pin down is declared in the results JSON under
``accounting_declarations`` so the exercise is reproducible and auditable.

Fail-closed seal check (prereg §3): the script re-derives the store ingestion
manifest fingerprint and every pair's canonical content sha256 and REFUSES to
run unless they match the sealed candidate
(sha256:0068eb93359ff3a7bc6e46e6be948d5b58ba6803940e4b5e80d0f4318d0c1cc1).

Construction (prereg §4, §6):
  - Signal at close(T): trailing L-day return close(T)/close(T-L) - 1.
  - Universe at T: pairs LISTED on T-1 per the frozen membership schedule;
    stablecoins excluded by rule; bars outside listed intervals are MASKED
    entirely (unrankable, untradeable, no volume contribution).
  - Liquid tier at T: top-10 by trailing 30-day median daily dollar volume
    (close*volume, days T-30..T-1, unmasked bars only) among the universe.
  - H1 portfolio: equal-weight LONG the bottom-3 by trailing 3-day return in
    the liquid tier; executed open(T+1); scored open(T+1)->open(T+2);
    rebalanced daily; min notional $10; un-investable residue sits in BTC.
  - Zero-volume day: unrankable and untradeable that day.
  - Delisting: forced exit at last available price, cost-charged.
  - Baseline: BTC buy-and-hold at identical notional and cost treatment.

Costs (prereg §5): 25 bp/side taker on EVERY leg incl. the baseline's entry;
slippage stresses +10 bp and +25 bp; gross (0 fee) reported for context.

Inference (prereg §2): d_t = daily strategy-minus-baseline net return; one-sided
moving-block bootstrap on mean(d_t) > 0 at alpha = 0.10, percentile lower bound,
block length precomputed from fitted d_t autocorrelation (Politis-White 2004
automatic selection with the Patton-Politis-White 2009 correction).

Family max-t diagnostic (prereg §1): 20 members = {momentum, reversal} x
lookback->horizon {3->1, 7->1, 7->7, 30->7, 90->20} x universe {full, liquid-10},
each the §4 template with those parameters substituted, k=3 in both tiers;
joint MBB max-t (reality-check) on the common valid-day grid. DIAGNOSTIC only.

Verdict (prereg §5, frozen): PASS requires net LB > 0 at BASE fees AND at
+10 bp; any PASS is downgraded to CONDITIONAL by the registered §3(b)
enumerated-censoring declaration. FAIL => G2 NO-GO + tombstone.

Usage:
  python scripts/g2_reversal_backtest.py \
    --store /path/to/data/crypto_ohlcv \
    --schedule doc/research/g2-manifest/crypto_membership_schedule.json \
    --sealed-manifest doc/research/g2-manifest/crypto_ohlcv_sealed_manifest_candidate_1d.json \
    --prereg doc/research/2026-07-17-g2-reversal-backtest-prereg.md \
    --out doc/research/g2-manifest/2026-07-18-g2-backtest-results.json

Read-only on the store. No orders, no capital, nothing touches 104.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Frozen constants (prereg + seal)
# ---------------------------------------------------------------------------

SEALED_STORE_FINGERPRINT = (
    "sha256:0068eb93359ff3a7bc6e46e6be948d5b58ba6803940e4b5e80d0f4318d0c1cc1"
)
WINDOW_START = pd.Timestamp("2021-01-01", tz="UTC")
WINDOW_END = pd.Timestamp("2026-07-16", tz="UTC")  # last bar open (close 07-17)

FEE_BASE = 0.0025  # 25 bp/side taker (Alpaca crypto tier-0)
K_PICKS = 3
MIN_NOTIONAL_USD = 10.0
INITIAL_NOTIONAL_USD = 10_700.0  # the G2 sleeve (prereg §2 economic rationale)
LIQUID_TIER_SIZE = 10
VOLUME_MEDIAN_WINDOW = 30
ALPHA = 0.10
N_BOOT = 10_000
SEED = 20260718
RESIDUE_ASSET = "BTC/USD"

# §1 frozen family: (signal_direction, lookback, horizon) x universe tier
FAMILY_LH = [(3, 1), (7, 1), (7, 7), (30, 7), (90, 20)]
FAMILY_DIRECTIONS = ["reversal", "momentum"]
FAMILY_TIERS = ["liquid10", "full"]
H1_MEMBER = ("reversal", 3, 1, "liquid10")

BAR_CLOSE_COL = "bar_close_utc"
CONTENT_SHA_COLS = ["open", "high", "low", "close", "volume", BAR_CLOSE_COL]


# ---------------------------------------------------------------------------
# Seal verification (fail-closed; prereg §3 "the backtest refuses to run on
# unsealed inputs")
# ---------------------------------------------------------------------------

def _to_utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def canonical_content_sha256(df: pd.DataFrame) -> str:
    """Replicates renquant_base_data.crypto_bars._content_sha256 exactly."""
    cols = [c for c in CONTENT_SHA_COLS if c in df.columns]
    canon = df.sort_index()[cols].copy()
    canon.index = pd.DatetimeIndex([_to_utc(ts) for ts in canon.index]).strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )
    if BAR_CLOSE_COL in canon.columns:
        closes = pd.to_datetime(canon[BAR_CLOSE_COL])
        closes = (
            closes.dt.tz_localize("UTC")
            if closes.dt.tz is None
            else closes.dt.tz_convert("UTC")
        )
        canon[BAR_CLOSE_COL] = closes.dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    return hashlib.sha256(canon.to_csv().encode("utf-8")).hexdigest()


def manifest_fingerprint(payload: dict) -> str:
    """Replicates renquant_base_data.crypto_bars.manifest_fingerprint exactly."""
    body = {k: v for k, v in payload.items() if k != "fingerprint"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_seal(store: Path, sealed_manifest_path: Path) -> dict:
    """Fail-closed seal check. Returns the verified manifest payload."""
    sealed = json.loads(sealed_manifest_path.read_text(encoding="utf-8"))
    if sealed.get("fingerprint") != SEALED_STORE_FINGERPRINT:
        sys.exit(
            "SEAL FAILURE: sealed-manifest candidate fingerprint "
            f"{sealed.get('fingerprint')!r} != frozen {SEALED_STORE_FINGERPRINT!r}; "
            "refusing to run (prereg §3 fail-closed)."
        )
    if manifest_fingerprint(sealed) != SEALED_STORE_FINGERPRINT:
        sys.exit(
            "SEAL FAILURE: sealed-manifest candidate does not re-derive its own "
            "fingerprint (tampered/corrupt); refusing to run."
        )
    live_path = store / "ingestion_manifest_1d.json"
    if not live_path.exists():
        sys.exit(f"SEAL FAILURE: store manifest missing at {live_path}; refusing to run.")
    live = json.loads(live_path.read_text(encoding="utf-8"))
    if manifest_fingerprint(live) != SEALED_STORE_FINGERPRINT:
        sys.exit(
            "SEAL FAILURE: live store manifest fingerprint "
            f"{manifest_fingerprint(live)!r} != sealed {SEALED_STORE_FINGERPRINT!r}; "
            "the store is not the sealed corpus; refusing to run."
        )
    if live != sealed:
        sys.exit(
            "SEAL FAILURE: live store manifest differs from the sealed candidate "
            "despite matching fingerprints (impossible unless tampered); refusing to run."
        )
    bad = []
    for pair, meta in sealed["symbols"].items():
        if meta.get("status") != "ok":
            bad.append((pair, "status!=ok"))
            continue
        df = pd.read_parquet(store / meta["path"])
        actual = canonical_content_sha256(df)
        if actual != meta["content_sha256"]:
            bad.append((pair, f"content sha {actual} != sealed {meta['content_sha256']}"))
    if bad:
        sys.exit(f"SEAL FAILURE: per-pair content mismatches {bad}; refusing to run.")
    print(f"[seal] OK — store matches sealed manifest {SEALED_STORE_FINGERPRINT}")
    return sealed


# ---------------------------------------------------------------------------
# Data layer — masked grids from the frozen membership schedule
# ---------------------------------------------------------------------------

def load_schedule(schedule_path: Path) -> dict:
    return json.loads(schedule_path.read_text(encoding="utf-8"))


def build_grids(store: Path, sealed: dict, schedule: dict) -> dict:
    """Daily UTC grids (open/close/volume/dollar-volume), masked outside listed
    intervals. Masked bars contribute NOTHING (prereg §3/§4)."""
    days = pd.date_range(WINDOW_START, WINDOW_END, freq="D", tz="UTC")
    pairs = sorted(schedule["pairs"].keys())
    stable = {p for p, rec in schedule["pairs"].items() if rec.get("excluded_by_rule") == "stablecoin"}
    obtainable = {p for p, rec in schedule["pairs"].items() if rec.get("obtainable", True)}

    listed = pd.DataFrame(False, index=days, columns=pairs)
    for p, rec in schedule["pairs"].items():
        for iv in rec["listed_intervals"]:
            lo = pd.Timestamp(iv["listed_from"], tz="UTC")
            hi = (
                pd.Timestamp(iv["listed_through"], tz="UTC")
                if iv["listed_through"]
                else WINDOW_END
            )
            lo, hi = max(lo, WINDOW_START), min(hi, WINDOW_END)
            if lo <= hi:
                listed.loc[lo:hi, p] = True

    cols = {}
    for field in ("open", "close", "volume"):
        cols[field] = pd.DataFrame(np.nan, index=days, columns=pairs)
    for p in pairs:
        meta = sealed["symbols"].get(p)
        if meta is None:
            continue  # WBTC/USD: listed but unobtainable — the registered omission
        df = pd.read_parquet(store / meta["path"])
        idx = pd.DatetimeIndex([_to_utc(t) for t in df.index])
        for field in ("open", "close", "volume"):
            s = pd.Series(df[field].to_numpy(), index=idx)
            s = s[(s.index >= WINDOW_START) & (s.index <= WINDOW_END)]
            cols[field].loc[s.index, p] = s
    # MASK: bars outside listed intervals are dropped entirely.
    for field in ("open", "close", "volume"):
        cols[field] = cols[field].where(listed)

    present = cols["close"].notna()
    dollar_vol = cols["close"] * cols["volume"]
    # Trailing 30-day median daily dollar volume through T-1 (unmasked bars only;
    # zero-volume bars inside listed intervals count as genuine $0 observations).
    med_dv_thru_prev = (
        dollar_vol.rolling(window=VOLUME_MEDIAN_WINDOW, min_periods=1).median().shift(1)
    )
    listed_prev = listed.shift(1, fill_value=False)

    return {
        "days": days,
        "pairs": pairs,
        "stable": stable,
        "obtainable": obtainable,
        "listed": listed,
        "listed_prev": listed_prev,
        "open": cols["open"],
        "close": cols["close"],
        "volume": cols["volume"],
        "present": present,
        "med_dv_thru_prev": med_dv_thru_prev,
    }


def build_signals(g: dict, lookbacks: list[int]) -> dict:
    """Trailing L-day return close(T)/close(T-L)-1 on masked closes; NaN when
    either endpoint is masked/missing. Zero-volume day T => unrankable at T."""
    signals = {}
    close = g["close"]
    rankable_today = g["present"] & (g["volume"] > 0)
    for L in lookbacks:
        sig = close / close.shift(L) - 1.0
        sig = sig.where(rankable_today)
        signals[L] = sig
    return signals


# ---------------------------------------------------------------------------
# Universe tiers (prereg §3/§4)
# ---------------------------------------------------------------------------

def universe_members(g: dict, t_idx: int) -> list[str]:
    """Non-stablecoin pairs listed on T-1 (the point-in-time universe at T)."""
    lp = g["listed_prev"].iloc[t_idx]
    return [
        p
        for p in g["pairs"]
        if lp[p] and p not in g["stable"]
    ]


def liquid_tier(g: dict, t_idx: int) -> list[str]:
    """Top-10 of the universe by trailing 30-day median dollar volume through
    T-1; pairs with no unmasked bar in the window have no median and cannot
    rank into the tier. Deterministic tiebreak: higher median, then symbol."""
    med = g["med_dv_thru_prev"].iloc[t_idx]
    cands = [(p, med[p]) for p in universe_members(g, t_idx) if pd.notna(med[p])]
    cands.sort(key=lambda x: (-x[1], x[0]))
    return [p for p, _ in cands[:LIQUID_TIER_SIZE]]


# ---------------------------------------------------------------------------
# Portfolio engine — the §4 template, generic over (direction, L, h, tier)
# ---------------------------------------------------------------------------

def run_member(
    g: dict,
    signals: dict,
    direction: str,
    lookback: int,
    horizon: int,
    tier: str,
    fee_rate: float,
) -> dict:
    """Simulate one family member under one fee scenario.

    Returns daily net return series (open(t)->open(t+1) marks), turnover,
    names-per-day, and edge-case counters. Deterministic; no RNG.
    """
    days = g["days"]
    n_days = len(days)
    openp = g["open"].to_numpy()
    closep = g["close"].to_numpy()
    volp = g["volume"].to_numpy()
    pair_ix = {p: i for i, p in enumerate(g["pairs"])}
    sig = signals[lookback]

    # Last available (unmasked) close through each day, for forced exits and
    # for marking held positions across in-interval data gaps.
    last_close = g["close"].ffill().to_numpy()

    counters = {
        "forced_exits": 0,
        "unexecutable_buys": 0,
        "frozen_sells": 0,
        "min_notional_clips": 0,
        "form_days_lt3_rankable": 0,
        "form_days_zero_rankable": 0,
    }

    def picks_at(t_idx: int) -> list[str] | None:
        """Ordered picks from the signal at close(T); None if T has no valid
        universe (member not yet active)."""
        members = (
            liquid_tier(g, t_idx) if tier == "liquid10" else universe_members(g, t_idx)
        )
        if not members:
            return None
        row = sig.iloc[t_idx]
        scored = [(p, row[p]) for p in members if pd.notna(row[p])]
        if not scored:
            return None if not members else []
        reverse = direction == "momentum"
        scored.sort(key=lambda x: (-x[1] if reverse else x[1], x[0]))
        return [p for p, _ in scored[:K_PICKS]]

    # Find activation: first form day T with >= K_PICKS rankable names.
    first_form = None
    for t in range(1, n_days - 2):
        members = (
            liquid_tier(g, t) if tier == "liquid10" else universe_members(g, t)
        )
        if not members:
            continue
        row = sig.iloc[t]
        if sum(1 for p in members if pd.notna(row[p])) >= K_PICKS:
            first_form = t
            break
    if first_form is None:
        raise RuntimeError(f"member {(direction, lookback, horizon, tier)} never activates")

    holdings: dict[str, float] = {}  # pair -> quantity
    charge = fee_rate if fee_rate is not None else 0.0

    exec_start = first_form + 1  # open(T+1)
    form_days = set(range(first_form, n_days - 1, horizon))
    values = np.full(n_days, np.nan)  # M(t): pre-trade, post-forced-exit value
    traded_notional = np.zeros(n_days)
    names_per_day = np.full(n_days, np.nan)

    cash_bootstrap = INITIAL_NOTIONAL_USD
    started = False

    for t in range(exec_start, n_days):
        # --- mark & forced exits at open(t) ---
        is_rebalance = (t - 1) in form_days
        if not started:
            m_val = cash_bootstrap
        else:
            m_val = 0.0
            forced_cash = 0.0
            new_holdings = {}
            for p, qty in sorted(holdings.items()):
                j = pair_ix[p]
                if not g["listed"].iat[t, j]:
                    # delisted: forced exit at last available price, cost-charged
                    proceeds = qty * last_close[t - 1, j]
                    fee = proceeds * charge
                    forced_cash += proceeds - fee
                    traded_notional[t] += proceeds
                    counters["forced_exits"] += 1
                elif np.isnan(openp[t, j]):
                    # in-interval data gap: hold, mark at last available close
                    m_val += qty * last_close[t, j]
                    new_holdings[p] = qty
                else:
                    m_val += qty * openp[t, j]
                    new_holdings[p] = qty
            holdings = new_holdings
            m_val += forced_cash
            if forced_cash > 0 and not is_rebalance:
                # Cash never idle: on non-rebalance days forced-exit proceeds
                # buy BTC immediately, buy leg fee-charged.
                jb = pair_ix[RESIDUE_ASSET]
                px = openp[t, jb] if not np.isnan(openp[t, jb]) else last_close[t, jb]
                buy_notional = forced_cash / (1.0 + charge)
                holdings[RESIDUE_ASSET] = (
                    holdings.get(RESIDUE_ASSET, 0.0) + buy_notional / px
                )
                traded_notional[t] += buy_notional
        values[t] = m_val

        # --- rebalance at open(t) iff t-1 was a form day ---
        if (t - 1) in form_days:
            picks = picks_at(t - 1) or []
            if len(picks) == 0:
                counters["form_days_zero_rankable"] += 1
            elif len(picks) < K_PICKS:
                counters["form_days_lt3_rankable"] += 1

            # Frozen positions: held pairs untradeable at t (zero-volume or gap)
            frozen_val = 0.0
            frozen = {}
            for p, qty in sorted(holdings.items()):
                j = pair_ix[p]
                tradeable = (
                    g["listed"].iat[t, j]
                    and not np.isnan(openp[t, j])
                    and volp[t, j] > 0
                )
                if not tradeable:
                    frozen[p] = qty
                    mark = openp[t, j] if not np.isnan(openp[t, j]) else last_close[t, j]
                    frozen_val += qty * mark
                    counters["frozen_sells"] += 1
            free_val = m_val - frozen_val

            # Target weights on total M(t): each executable pick 1/3; residue BTC.
            target_dollars: dict[str, float] = {}
            for p in picks:
                j = pair_ix[p]
                executable = (
                    g["listed"].iat[t, j]
                    and not np.isnan(openp[t, j])
                    and volp[t, j] > 0
                )
                if not executable:
                    counters["unexecutable_buys"] += 1
                    continue  # un-investable: allocation joins the BTC residue
                alloc = m_val / K_PICKS
                if alloc < MIN_NOTIONAL_USD:
                    counters["min_notional_clips"] += 1
                    continue
                target_dollars[p] = target_dollars.get(p, 0.0) + alloc
            names_per_day[t] = len(target_dollars)

            # Residue to BTC (cash never idle). BTC may also be a pick.
            picks_total = sum(target_dollars.values())
            resid = max(free_val - picks_total, 0.0)
            if picks_total > free_val + 1e-9:
                # frozen positions crowd out pick allocations: scale down
                scale = free_val / picks_total if picks_total > 0 else 0.0
                target_dollars = {p: d * scale for p, d in target_dollars.items()}
                picks_total = sum(target_dollars.values())
                resid = 0.0
            target_dollars[RESIDUE_ASSET] = target_dollars.get(RESIDUE_ASSET, 0.0) + resid

            # Fee-consistent scale factor: final invested = free_val - fees.
            cur_dollars = {}
            for p, qty in sorted(holdings.items()):
                if p in frozen:
                    continue
                j = pair_ix[p]
                cur_dollars[p] = qty * openp[t, j]
            trade_pairs = sorted(set(target_dollars) | set(cur_dollars))
            lam = 1.0
            for _ in range(8):
                tr = sum(
                    abs(lam * target_dollars.get(p, 0.0) - cur_dollars.get(p, 0.0))
                    for p in trade_pairs
                )
                lam_new = (free_val - charge * tr) / free_val if free_val > 0 else 0.0
                if abs(lam_new - lam) < 1e-14:
                    lam = lam_new
                    break
                lam = lam_new
            tr = sum(
                abs(lam * target_dollars.get(p, 0.0) - cur_dollars.get(p, 0.0))
                for p in trade_pairs
            )
            traded_notional[t] += tr

            new_holdings = dict(frozen)
            for p, d in target_dollars.items():
                j = pair_ix[p]
                if d > 0 and not np.isnan(openp[t, j]):
                    new_holdings[p] = new_holdings.get(p, 0.0) + lam * d / openp[t, j]
            holdings = new_holdings
            started = True
        elif not started:
            # before activation nothing happens (cash is notional only)
            values[t] = np.nan
            continue

    # Daily net returns r(t) = M(t+1)/M(t) - 1 over scored days.
    valid = ~np.isnan(values)
    idxs = np.where(valid)[0]
    t0 = idxs[0]
    rets = pd.Series(
        values[t0 + 1 :] / values[t0 : -1] - 1.0,
        index=days[t0:-1],
    )
    turno = pd.Series(traded_notional[t0:-1] / 2.0, index=days[t0:-1]) / pd.Series(
        values[t0:-1], index=days[t0:-1]
    )
    npd = pd.Series(names_per_day[t0:-1], index=days[t0:-1])
    return {
        "returns": rets,
        "turnover_oneway": turno,
        "names_per_day": npd,
        "counters": counters,
        "first_exec_day": str(days[t0].date()),
    }


def run_baseline(g: dict, fee_rate: float, start_day: pd.Timestamp) -> pd.Series:
    """BTC buy-and-hold from start_day at identical notional and cost treatment:
    entry leg charged at the same per-side rate; marks at open; across data gaps
    marks at last available close (BTC has none in practice)."""
    charge = fee_rate if fee_rate is not None else 0.0
    days = g["days"]
    j = g["pairs"].index(RESIDUE_ASSET)
    openp = g["open"].to_numpy()[:, j]
    lastc = g["close"].ffill().to_numpy()[:, j]
    t0 = int(np.where(days == start_day)[0][0])
    n = len(days)
    buy_notional = INITIAL_NOTIONAL_USD / (1.0 + charge)
    qty = buy_notional / openp[t0]
    vals = np.full(n, np.nan)
    vals[t0] = INITIAL_NOTIONAL_USD  # pre-trade capital at open(t0)
    for t in range(t0 + 1, n):
        vals[t] = qty * (openp[t] if not np.isnan(openp[t]) else lastc[t])
    return pd.Series(vals[t0 + 1 :] / vals[t0:-1] - 1.0, index=days[t0:-1])


# ---------------------------------------------------------------------------
# Inference — Politis-White block length + moving-block bootstrap (prereg §2)
# ---------------------------------------------------------------------------

def politis_white_block_length(x: np.ndarray) -> int:
    """Automatic block-length selection (Politis & White 2004; Patton, Politis
    & White 2009 correction), circular/moving-block variant."""
    n = len(x)
    x = x - x.mean()
    k_n = max(5, int(math.ceil(math.sqrt(math.log10(n)))))
    m_max = int(math.ceil(math.sqrt(n))) + k_n
    # sample autocorrelations
    acov = np.array([np.dot(x[: n - k], x[k:]) / n for k in range(m_max + 1)])
    rho = acov / acov[0]
    band = 2.0 * math.sqrt(math.log10(n) / n)
    m_hat = None
    for m in range(1, m_max - k_n + 1):
        if np.all(np.abs(rho[m + 1 : m + k_n + 1]) < band):
            m_hat = m
            break
    if m_hat is None:
        m_hat = m_max - k_n
    big_m = min(2 * m_hat, m_max)

    def lam(t: float) -> float:
        a = abs(t)
        if a <= 0.5:
            return 1.0
        if a <= 1.0:
            return 2.0 * (1.0 - a)
        return 0.0

    g_hat = 0.0
    d_sum = acov[0]
    for k in range(1, big_m + 1):
        w = lam(k / big_m) if big_m > 0 else 0.0
        g_hat += 2.0 * w * k * acov[k]
        d_sum += 2.0 * w * acov[k]
    d_cb = (4.0 / 3.0) * d_sum**2
    if d_cb <= 0 or g_hat == 0.0:
        return 1
    b = ((2.0 * g_hat**2) / d_cb) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    b_max = int(math.ceil(min(3.0 * math.sqrt(n), n / 3.0)))
    return int(min(max(1, round(b)), b_max))


def mbb_indices(rng: np.random.Generator, n: int, b: int, n_boot: int) -> np.ndarray:
    """Moving-block bootstrap index matrix (n_boot x n), blocks of length b."""
    n_blocks = int(math.ceil(n / b))
    starts = rng.integers(0, n - b + 1, size=(n_boot, n_blocks))
    offs = np.arange(b)
    idx = (starts[:, :, None] + offs[None, None, :]).reshape(n_boot, n_blocks * b)
    return idx[:, :n]


def mbb_lower_bound(
    d: np.ndarray, b: int, rng: np.random.Generator, n_boot: int, alpha: float
) -> dict:
    idx = mbb_indices(rng, len(d), b, n_boot)
    boot_means = d[idx].mean(axis=1)
    lb = float(np.percentile(boot_means, 100.0 * alpha))
    return {
        "mean": float(d.mean()),
        "sd": float(d.std(ddof=1)),
        "t_stat": float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))),
        "n": int(len(d)),
        "block_length": int(b),
        "lb_percentile": lb,
        "lb_gt_zero": bool(lb > 0),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--schedule", required=True, type=Path)
    ap.add_argument("--sealed-manifest", required=True, type=Path)
    ap.add_argument("--prereg", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    sealed = verify_seal(args.store, args.sealed_manifest)
    schedule = load_schedule(args.schedule)
    schedule_sha = file_sha256(args.schedule)
    prereg_sha = file_sha256(args.prereg)

    g = build_grids(args.store, sealed, schedule)
    signals = build_signals(g, sorted({L for L, _ in FAMILY_LH}))
    print(f"[data] grids built: {len(g['days'])} days x {len(g['pairs'])} pairs")

    # ---- all 20 family members x fee scenarios ----
    members = [
        (direction, L, h, tier)
        for direction in FAMILY_DIRECTIONS
        for (L, h) in FAMILY_LH
        for tier in FAMILY_TIERS
    ]
    assert H1_MEMBER in members and len(members) == 20

    fee_scenarios = {
        "gross": 0.0,
        "base": FEE_BASE,
        "plus10bp": FEE_BASE + 0.0010,
        "plus25bp": FEE_BASE + 0.0025,
    }

    member_results: dict = {}
    for mem in members:
        direction, L, h, tier = mem
        member_results[mem] = {}
        for scen, fee in fee_scenarios.items():
            res = run_member(g, signals, direction, L, h, tier, fee)
            member_results[mem][scen] = res
        print(f"[member] {mem} done (start {member_results[mem]['base']['first_exec_day']})")

    # ---- H1 verdict inference ----
    h1 = member_results[H1_MEMBER]
    h1_start = pd.Timestamp(h1["base"]["first_exec_day"], tz="UTC")
    d_series: dict[str, pd.Series] = {}
    for scen, fee in fee_scenarios.items():
        base_rets = run_baseline(g, fee, h1_start)
        strat = h1[scen]["returns"]
        common = strat.index.intersection(base_rets.index)
        d_series[scen] = (strat.loc[common] - base_rets.loc[common]).dropna()

    d_base = d_series["base"].to_numpy()
    b_len = politis_white_block_length(d_base)
    inference = {}
    for scen in fee_scenarios:
        rng = np.random.default_rng(args.seed)  # same seed per scenario: paired draws
        d = d_series[scen].to_numpy()
        inference[scen] = mbb_lower_bound(d, b_len, rng, N_BOOT, ALPHA)

    verdict_pass = inference["base"]["lb_gt_zero"] and inference["plus10bp"]["lb_gt_zero"]
    verdict = "CONDITIONAL-PASS" if verdict_pass else "FAIL"

    # ---- family max-t diagnostic (base-fee net, common grid) ----
    fam_d: dict[tuple, pd.Series] = {}
    for mem in members:
        s = member_results[mem]["base"]["returns"]
        base_rets = run_baseline(g, fee_scenarios["base"], pd.Timestamp(
            member_results[mem]["base"]["first_exec_day"], tz="UTC"))
        common = s.index.intersection(base_rets.index)
        fam_d[mem] = (s.loc[common] - base_rets.loc[common]).dropna()
    common_idx = None
    for s in fam_d.values():
        common_idx = s.index if common_idx is None else common_idx.intersection(s.index)
    fam_mat = np.column_stack([fam_d[mem].loc[common_idx].to_numpy() for mem in members])
    n_c = fam_mat.shape[0]
    b_fam = max(politis_white_block_length(fam_mat[:, j]) for j in range(len(members)))
    means = fam_mat.mean(axis=0)
    sds = fam_mat.std(axis=0, ddof=1)
    t_obs = means / (sds / math.sqrt(n_c))
    rng = np.random.default_rng(args.seed + 1)
    idx = mbb_indices(rng, n_c, b_fam, N_BOOT)
    maxt = np.empty(N_BOOT)
    h1_j = members.index(H1_MEMBER)
    for r in range(N_BOOT):
        sample = fam_mat[idx[r]]
        sm = sample.mean(axis=0)
        ss = sample.std(axis=0, ddof=1)
        t_star = (sm - means) / (ss / math.sqrt(n_c))
        maxt[r] = t_star.max()
    fam_p_h1 = float((1 + np.sum(maxt >= t_obs[h1_j])) / (N_BOOT + 1))

    # ---- results artifact (prereg §7) ----
    def mem_name(mem):
        d_, L, h, tier = mem
        return f"{d_}_{L}to{h}_{tier}"

    h1_names = h1["base"]["names_per_day"].dropna()
    h1_turno = h1["base"]["turnover_oneway"].dropna()
    results = {
        "schema": "g2-backtest-results-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "prereg": "doc/research/2026-07-17-g2-reversal-backtest-prereg.md",
        "seed": args.seed,
        "n_boot": N_BOOT,
        "alpha_one_sided": ALPHA,
        "input_digests": {
            "store_manifest_fingerprint": SEALED_STORE_FINGERPRINT,
            "membership_schedule_sha256": schedule_sha,
            "prereg_sha256": prereg_sha,
            "store_path": str(args.store),
        },
        "execution_proxy_declaration": (
            "Daily-bar proxy: signal at UTC close(T); fills at open(T+1); scoring "
            "open(T+1)->open(T+2); zero-latency zero-spread fills — the base case "
            "is the MOST-optimistic accounting (prereg §5/§6). Not an attainable-"
            "fill claim; the paper-shadow protocol supplies real fills."
        ),
        "construction": {
            "h1_member": mem_name(H1_MEMBER),
            "k_picks": K_PICKS,
            "liquid_tier_size": LIQUID_TIER_SIZE,
            "volume_median_window_days": VOLUME_MEDIAN_WINDOW,
            "min_notional_usd": MIN_NOTIONAL_USD,
            "initial_notional_usd": INITIAL_NOTIONAL_USD,
            "residue_asset": RESIDUE_ASSET,
            "fee_per_side_base": FEE_BASE,
            "window": [str(WINDOW_START.date()), str(WINDOW_END.date())],
        },
        "accounting_declarations": [
            "Universe at T = non-stablecoin pairs listed on T-1 per the frozen schedule; "
            "bars outside listed intervals are masked entirely (no price, no volume).",
            "Liquid tier = top-10 by trailing 30-day median daily dollar volume "
            "(close*volume) over unmasked bars in T-30..T-1; in-interval zero-volume "
            "bars count as $0 observations; ties broken by (higher median, symbol).",
            "'full' tier = ALL non-stablecoin pairs listed on T-1 (the §4 template "
            "with the top-10 liquidity cut removed); the prereg's 'full-20' label "
            "names the #532 screen's store; under the sealed point-in-time schedule "
            "the full tier is the schedule-listed set.",
            "Signal requires unmasked close(T) and close(T-L) and volume(T)>0 "
            "(zero-volume day = unrankable that day).",
            "Buys require an unmasked bar with volume>0 at the execution day; an "
            "unexecutable pick's allocation joins the BTC residue (un-investable "
            "residue rule). Held pairs untradeable at a rebalance are frozen "
            "(held, marked at last available price) until tradeable.",
            "Delisted holdings force-exit at the last available unmasked close, "
            "fee-charged, proceeds redeployed at the same open.",
            "In-interval data-gap days: held positions are marked at the last "
            "available close; no trading in the gapped pair that day.",
            "Fees are charged on every traded leg's notional (buys, sells, BTC "
            "residue legs, baseline entry, forced exits) at fee_per_side + stress; "
            "rebalance targets are scaled by a fixed-point factor so invested "
            "value = pre-trade value minus fees (exact, no negative cash).",
            "Daily net return r(t) = M(t+1)/M(t) - 1 where M(t) is the sleeve "
            "marked at open(t) after forced exits; day-t rebalance fees reduce "
            "M(t+1) via post-fee quantities. No terminal liquidation is charged.",
            "Horizon-h family members rebalance every h days (form at close(T), "
            "hold open(T+1)->open(T+1+h)); daily open-to-open marks give daily d_t.",
            "Activation: a member's first form day is the first T with >= 3 "
            "rankable names in its tier; if fewer than 3 names rank on a later "
            "form day the portfolio holds the rankable bottom-m (each at 1/3 "
            "weight, remainder in BTC residue) — occurrence counts reported.",
            "Baseline: BTC bought at open(first H1 execution day) at identical "
            "notional; entry leg charged at the same per-side rate; never trades "
            "again. Each fee scenario's d_t uses the same-scenario baseline.",
            "Family max-t: base-fee net d_t on the members' common valid-day "
            "grid; joint MBB (shared block indices) with block length = max of "
            "per-member Politis-White lengths; studentized centered max-t "
            "(reality-check); family-adjusted p for H1 reported. DIAGNOSTIC only.",
            "Block length: Politis-White (2004) automatic selection with the "
            "Patton-Politis-White (2009) correction, circular/MBB variant, fitted "
            "on base-fee d_t and reused across stress scenarios (paired seeds).",
        ],
        "h1": {
            "member": mem_name(H1_MEMBER),
            "first_execution_day": h1["base"]["first_exec_day"],
            "n_valid_days": int(len(d_series["base"])),
            "names_per_day": {
                "mean": float(h1_names.mean()),
                "min": float(h1_names.min()),
                "max": float(h1_names.max()),
                "share_days_full_3": float((h1_names == 3).mean()),
            },
            "turnover_oneway_daily": {
                "mean": float(h1_turno.mean()),
                "median": float(h1_turno.median()),
            },
            "edge_counters": h1["base"]["counters"],
            "inference_per_scenario": inference,
        },
        "family_max_t_diagnostic": {
            "n_members": len(members),
            "scenario": "base",
            "common_grid": [str(common_idx[0].date()), str(common_idx[-1].date())],
            "n_common_days": int(n_c),
            "block_length": int(b_fam),
            "members": [
                {
                    "name": mem_name(mem),
                    "mean_d": float(means[j]),
                    "t_stat": float(t_obs[j]),
                    "turnover_oneway_daily_mean": float(
                        member_results[mem]["base"]["turnover_oneway"].dropna().mean()
                    ),
                }
                for j, mem in enumerate(members)
            ],
            "observed_max_t": float(t_obs.max()),
            "observed_max_t_member": mem_name(members[int(np.argmax(t_obs))]),
            "h1_t_stat": float(t_obs[h1_j]),
            "h1_family_adjusted_p": fam_p_h1,
            "note": "Overfitting diagnostic only (prereg §1); no verdict rides on it.",
        },
        "verdict": {
            "rule": (
                "PASS requires net LB > 0 at BASE fees AND at +10bp (prereg §5); "
                "any PASS is downgraded to CONDITIONAL by the registered §3(b) "
                "enumerated-censoring declaration (inflates PASS; carried verbatim "
                "into any paper-shadow registration)."
            ),
            "base_lb": inference["base"]["lb_percentile"],
            "plus10bp_lb": inference["plus10bp"]["lb_percentile"],
            "plus25bp_lb": inference["plus25bp"]["lb_percentile"],
            "outcome": verdict,
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, sort_keys=False) + "\n")
    print(f"[out] {args.out}")
    print(
        f"[verdict] {verdict} — base LB {inference['base']['lb_percentile']:+.6f}, "
        f"+10bp LB {inference['plus10bp']['lb_percentile']:+.6f}, "
        f"n={inference['base']['n']}"
    )


if __name__ == "__main__":
    main()
