#!/usr/bin/env python
"""Evidence computations for pipeline#204 round-1 P1s (VetoWeakBuys small-n guard).

Read-only: runs.alpaca.db opened mode=ro&immutable=1; ohlcv parquets read only.
Sections:
  1. Mixture Monte Carlo of P(all-veto) vs n  (P1-2: N0 justification)
  2. 0.50 absolute-threshold scale stability + forward-return split (P1-3)
  3. Three-rule admission comparison on small-n / all-veto sessions (P2 quantile)
"""
import math
import sqlite3
import statistics as st

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260717)
DB = "file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro&immutable=1"
OHLCV = "/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet"
ETFS = {"XLI", "XLY", "XLE", "XLF", "XLK", "XLV", "XLP", "XLU", "XLB", "XLRE", "XLC"}
N_TRIALS = 20_000

db = sqlite3.connect(DB, uri=True)

# ---- candidate scores, one live run per date (latest run_id) --------------
cand = pd.read_sql_query(
    """
    SELECT pr.run_date, pr.run_id, cs.ticker, cs.rank_score
    FROM candidate_scores cs
    JOIN pipeline_runs pr ON cs.run_id = pr.run_id
    WHERE pr.run_type='live' AND cs.role='candidate' AND cs.rank_score IS NOT NULL
    """,
    db,
)
last_run = cand.groupby("run_date")["run_id"].transform("max")
cand = cand[cand.run_id == last_run].copy()
cand["is_etf"] = cand.ticker.isin(ETFS)


def floor_mean_std(scores):
    if len(scores) < 2:
        return 0.20
    return max(0.20, st.fmean(scores) + st.stdev(scores))


def floor_q80(scores):
    if len(scores) < 2:
        return 0.20
    return max(0.20, float(np.quantile(scores, 0.80, method="linear")))


def floor_smalln(scores, n0=10, abs_fl=0.50):
    if len(scores) >= n0:
        return floor_mean_std(scores)
    return max(0.20, abs_fl)


def admitted(scores, fl):
    return sum(1 for s in scores if s >= fl)


# ============================================================
print("=" * 70)
print("PART 1 — P(all-veto) vs n: iid vs empirical mixture")
print("=" * 70)
post = cand[cand.run_date >= "2026-06-01"]
stock_pool = post.loc[~post.is_etf, "rank_score"].to_numpy()
etf_pool = post.loc[post.is_etf, "rank_score"].to_numpy()
pooled = post["rank_score"].to_numpy()
print(f"post-06-01 pools: stocks n={len(stock_pool)} mean={stock_pool.mean():.3f} sd={stock_pool.std(ddof=1):.3f} | "
      f"ETFs n={len(etf_pool)} mean={etf_pool.mean():.3f} sd={etf_pool.std(ddof=1):.3f} | "
      f"pooled mean={pooled.mean():.3f} sd={pooled.std(ddof=1):.3f}")

s_mu, s_sd = stock_pool.mean(), stock_pool.std(ddof=1)
e_mu, e_sd = etf_pool.mean(), etf_pool.std(ddof=1)
p_mu, p_sd = pooled.mean(), pooled.std(ddof=1)


def trial_allveto(draw):
    m = draw.mean(axis=1)
    s = draw.std(axis=1, ddof=1)
    fl = np.maximum(0.20, m + s)
    return (draw.max(axis=1) < fl).mean()


def mc_row(n):
    out = {}
    out["iid"] = trial_allveto(RNG.normal(p_mu, p_sd, size=(N_TRIALS, n)))
    for label, frac in (("mix40", 0.40), ("mix20", 0.20)):
        k = max(0, round(frac * n))
        k = min(k, n - 1)  # at least one stock
        stocks = RNG.normal(s_mu, s_sd, size=(N_TRIALS, n - k))
        etfs = RNG.normal(e_mu, e_sd, size=(N_TRIALS, k))
        out[label] = trial_allveto(np.concatenate([stocks, etfs], axis=1))
    # bootstrap-from-empirical robustness at 40%
    k = min(max(0, round(0.40 * n)), n - 1)
    stocks = RNG.choice(stock_pool, size=(N_TRIALS, n - k), replace=True)
    etfs = RNG.choice(etf_pool, size=(N_TRIALS, k), replace=True)
    out["mix40_boot"] = trial_allveto(np.concatenate([stocks, etfs], axis=1))
    return out


rows = {}
print(f"{'n':>3} {'iid':>8} {'mix20':>8} {'mix40':>8} {'mix40boot':>10}")
for n in range(3, 21):
    r = mc_row(n)
    rows[n] = r
    print(f"{n:>3} {r['iid']:>8.3f} {r['mix20']:>8.3f} {r['mix40']:>8.3f} {r['mix40_boot']:>10.3f}")

for thresh in (0.05, 0.01):
    n_norm = next((n for n in range(3, 21) if rows[n]["mix40"] <= thresh), None)
    n_boot = next((n for n in range(3, 21) if rows[n]["mix40_boot"] <= thresh), None)
    print(f"smallest n with mix40 P(all-veto) <= {thresh:.0%}: normal-fit {n_norm}, bootstrap {n_boot}")

# ============================================================
print()
print("=" * 70)
print("PART 2 — 0.50 scale stability + forward-return split")
print("=" * 70)
cand["month"] = cand.run_date.str[:7]
print(f"{'month':>8} {'n_sess':>7} {'median':>7} {'IQR':>13} {'max':>6} {'frac sess max<0.50':>19}")
for month, g in cand.groupby("month"):
    per_sess_max = g.groupby("run_date")["rank_score"].max()
    q1, q3 = g.rank_score.quantile([0.25, 0.75])
    print(f"{month:>8} {per_sess_max.size:>7} {g.rank_score.median():>7.3f} "
          f"[{q1:.3f},{q3:.3f}] {g.rank_score.max():>6.3f} {(per_sess_max < 0.50).mean():>19.2f}")

# forward returns, post-scale-fix era
cal = pd.read_parquet(OHLCV.format(t="SPY"))
cal_idx = cal.index
opens_cache = {"SPY": cal["open"]}


def opens(t):
    if t not in opens_cache:
        try:
            opens_cache[t] = pd.read_parquet(OHLCV.format(t=t))["open"]
        except Exception:
            opens_cache[t] = None
    return opens_cache[t]


def fwd_excess(ticker, run_date, h):
    """Open-to-open excess vs SPY, entry next session open after run_date."""
    o = opens(ticker)
    if o is None:
        return None
    d = pd.Timestamp(run_date)
    pos = cal_idx.searchsorted(d, side="right")  # next session
    if pos + h >= len(cal_idx):
        return None
    d0, d1 = cal_idx[pos], cal_idx[pos + h]
    try:
        p0, p1 = float(o.loc[d0]), float(o.loc[d1])
        s0, s1 = float(opens_cache["SPY"].loc[d0]), float(opens_cache["SPY"].loc[d1])
    except KeyError:
        return None
    if not (p0 > 0 and s0 > 0):
        return None
    return (p1 / p0 - 1.0) - (s1 / s0 - 1.0)


era = cand[cand.run_date >= "2026-05-22"].copy()
print(f"\nforward-return split, era {era.run_date.min()}..{era.run_date.max()}, "
      f"{era.run_date.nunique()} sessions, {len(era)} candidate rows")

for thresh, label in ((0.50, "PRIMARY 0.50"), (0.45, "sensitivity 0.45 (not tuning)"), (0.55, "sensitivity 0.55 (not tuning)")):
    for h in (1, 5, 20):
        rows_h = []
        for rd, g in era.groupby("run_date"):
            hi = [fwd_excess(t, rd, h) for t in g.loc[g.rank_score >= thresh, "ticker"]]
            lo = [fwd_excess(t, rd, h) for t in g.loc[g.rank_score < thresh, "ticker"]]
            hi = [x for x in hi if x is not None]
            lo = [x for x in lo if x is not None]
            if hi and lo:
                rows_h.append((rd, st.fmean(hi), st.fmean(lo), len(hi), len(lo)))
        if not rows_h:
            print(f"  thr={thresh} h={h:>2}: no paired sessions")
            continue
        diffs = np.array([r[1] - r[2] for r in rows_h])
        n_hi = sum(r[3] for r in rows_h)
        n_lo = sum(r[4] for r in rows_h)
        boot = RNG.choice(diffs, size=(10_000, len(diffs)), replace=True).mean(axis=1)
        lo_ci, hi_ci = np.quantile(boot, [0.05, 0.95])
        print(f"  thr={thresh} h={h:>2}: sessions={len(diffs):>2} "
              f"mean(>=thr)={st.fmean([r[1] for r in rows_h])*100:+.2f}% (n={n_hi}) "
              f"mean(<thr)={st.fmean([r[2] for r in rows_h])*100:+.2f}% (n={n_lo}) "
              f"paired diff={diffs.mean()*100:+.2f}% [90% CI {lo_ci*100:+.2f}%,{hi_ci*100:+.2f}%]  ({label})")

# ============================================================
print()
print("=" * 70)
print("PART 3 — three-rule admissions on small-n / all-veto sessions + synthetic")
print("=" * 70)
sess = cand.groupby("run_date")["rank_score"].agg(list)
targets = []
for rd, scores in sess.items():
    fl = floor_mean_std(scores)
    if len(scores) < 10 or admitted(scores, fl) == 0:
        targets.append((rd, scores))
print(f"{'date':>12} {'n':>4} {'mean+1σ':>8} {'q80':>6} {'smalln0.50':>10}   one-sided?")
violations = 0
for rd, scores in targets:
    a1 = admitted(scores, floor_mean_std(scores))
    a2 = admitted(scores, floor_q80(scores))
    a3 = admitted(scores, floor_smalln(scores))
    flag = "" if a3 >= a1 else "  << VIOLATION (proposed < status quo)"
    if a3 < a1:
        violations += 1
    print(f"{rd:>12} {len(scores):>4} {a1:>8} {a2:>6} {a3:>10}{flag}")

print("\nsynthetic Platt-compressed sets (range ~0.07), n=5:")
for center in (0.45, 0.55):
    scores = [center - 0.035 + 0.07 * i / 4 for i in range(5)]
    a1 = admitted(scores, floor_mean_std(scores))
    a2 = admitted(scores, floor_q80(scores))
    a3 = admitted(scores, floor_smalln(scores))
    flag = "" if a3 >= a1 else "  << VIOLATION"
    print(f"  center={center}: scores=[{', '.join(f'{s:.3f}' for s in scores)}] "
          f"mean+1σ admits {a1}, q80 admits {a2}, smalln-0.50 admits {a3}{flag}")
print(f"\none-sidedness violations vs status quo on real sessions: {violations}")
