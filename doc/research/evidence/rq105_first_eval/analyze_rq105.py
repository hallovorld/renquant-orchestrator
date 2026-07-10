#!/usr/bin/env python3
"""First systematic evaluation of renquant105 Stage-1 shadow data (READ-ONLY).

Reads:
  logs/renquant105_pilot/intraday_ticks.jsonl (+ .censored.jsonl)
  logs/renquant105_pilot/entry_timing_shadow.jsonl
  logs/renquant105_pilot/entry_timing_policy_shadow.jsonl
  data/ohlcv/<TICKER>/1d.parquet  (official open prints)
  data/runs.alpaca.db             (buy_pending decisions, read-only)

Writes evidence JSONs to OUT_DIR only.
"""
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path("/Users/renhao/git/github/RenQuant")
PILOT = ROOT / "logs/renquant105_pilot"
OUT_DIR = Path(
    "/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/"
    "2244bd05-9699-4a07-8836-2b6d9e43ca5f/scratchpad/evidence"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)
ET = ZoneInfo("America/New_York")


def pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * q
    f = math.floor(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def rnd(x, n=2):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- 1. ticks
rows = []
with open(PILOT / "intraday_ticks.jsonl") as fh:
    for line in fh:
        r = json.loads(line)
        rows.append(
            (
                r["date"],
                r["ticker"],
                r["bid"],
                r["ask"],
                r["mid"],
                r["quote_ts"],
                r["ts"],
                r.get("quote_age"),
                r.get("status"),
            )
        )
tk = pd.DataFrame(
    rows,
    columns=["date", "ticker", "bid", "ask", "mid", "quote_ts", "cycle_ts", "quote_age", "status"],
)
tk["quote_dt"] = pd.to_datetime(tk["quote_ts"], utc=True, format="ISO8601").dt.tz_convert(ET)
tk["tod"] = tk["quote_dt"].dt.hour * 60 + tk["quote_dt"].dt.minute  # minutes ET

cen_counts = Counter()
cen_by_date = defaultdict(Counter)
with open(PILOT / "intraday_ticks.jsonl.censored.jsonl") as fh:
    for line in fh:
        r = json.loads(line)
        cen_counts[r.get("status")] += 1
        cen_by_date[r["date"]][r.get("status")] += 1

inventory = {"per_session": {}, "censored_status_overall": dict(cen_counts)}
for d, g in tk.groupby("date"):
    cycles = g["cycle_ts"].nunique()
    cyc_times = sorted(pd.to_datetime(g["cycle_ts"].unique(), format="ISO8601"))
    gaps = [
        (b - a).total_seconds() for a, b in zip(cyc_times, cyc_times[1:])
    ]
    inventory["per_session"][d] = {
        "rows_ok": int(len(g)),
        "rows_censored": int(sum(cen_by_date[d].values())),
        "censored_reasons": dict(cen_by_date[d]),
        "n_tickers": int(g["ticker"].nunique()),
        "n_cycles": int(cycles),
        "first_tick_ET": g["quote_dt"].min().strftime("%H:%M:%S"),
        "last_tick_ET": g["quote_dt"].max().strftime("%H:%M:%S"),
        "median_cycle_gap_s": rnd(statistics.median(gaps), 1) if gaps else None,
        "p95_cycle_gap_s": rnd(pct(gaps, 0.95), 1) if gaps else None,
        "quote_age_p50_s": rnd(float(g["quote_age"].median()), 1),
        "quote_age_p95_s": rnd(float(g["quote_age"].quantile(0.95)), 1),
    }
inventory["overall"] = {
    "total_rows_ok": int(len(tk)),
    "total_rows_censored": int(sum(cen_counts.values())),
    "sessions": sorted(tk["date"].unique().tolist()),
    "n_sessions": int(tk["date"].nunique()),
    "n_tickers": int(tk["ticker"].nunique()),
    "source": "alpaca-iex (IEX top-of-book, NOT consolidated NBBO)",
    "watchlist_tickers": sorted(tk["ticker"].unique().tolist()),
}
json.dump(inventory, open(OUT_DIR / "inventory.json", "w"), indent=2)

# ---------------------------------------------------------------- 2. spreads
ok = tk[(tk["bid"] > 0) & (tk["ask"] > 0)].copy()
crossed = ok[ok["ask"] < ok["bid"]]
ok = ok[ok["ask"] >= ok["bid"]].copy()
ok["spread_bps"] = (ok["ask"] - ok["bid"]) / ((ok["ask"] + ok["bid"]) / 2) * 1e4

BUCKETS = [
    ("open_0935_1000", 9 * 60 + 35, 10 * 60),
    ("morning_1000_1130", 10 * 60, 11 * 60 + 30),
    ("midday_1130_1430", 11 * 60 + 30, 14 * 60 + 30),
    ("afternoon_1430_1530", 14 * 60 + 30, 15 * 60 + 30),
    ("close_1530_1600", 15 * 60 + 30, 16 * 60),
]


def bucket_of(m):
    for name, lo, hi in BUCKETS:
        if lo <= m < hi:
            return name
    return "outside"


ok["bucket"] = ok["tod"].map(bucket_of)

spreads = {"quality": {
    "rows_with_both_sides": int(len(ok)) + int(len(crossed)),
    "crossed_quotes": int(len(crossed)),
    "rows_spread_gt_100bps_share": rnd(float((ok["spread_bps"] > 100).mean()), 4),
    "rows_spread_gt_300bps_share": rnd(float((ok["spread_bps"] > 300).mean()), 4),
}}

per_ticker = {}
for t, g in ok.groupby("ticker"):
    per_ticker[t] = {
        "n": int(len(g)),
        "p50_bps": rnd(float(g["spread_bps"].median())),
        "p95_bps": rnd(float(g["spread_bps"].quantile(0.95))),
    }
spreads["per_ticker"] = per_ticker
medians = [v["p50_bps"] for v in per_ticker.values()]
spreads["cross_ticker_summary"] = {
    "median_of_ticker_medians_bps": rnd(statistics.median(medians)),
    "p25_of_ticker_medians_bps": rnd(pct(medians, 0.25)),
    "p75_of_ticker_medians_bps": rnd(pct(medians, 0.75)),
    "min_ticker_median_bps": rnd(min(medians)),
    "max_ticker_median_bps": rnd(max(medians)),
    "n_tickers_median_le_5bps": sum(1 for m in medians if m <= 5),
    "n_tickers_median_gt_50bps": sum(1 for m in medians if m > 50),
}

by_bucket = {}
for name, _, _ in BUCKETS:
    g = ok[ok["bucket"] == name]
    tick_meds = g.groupby("ticker")["spread_bps"].median()
    by_bucket[name] = {
        "n": int(len(g)),
        "pooled_p50_bps": rnd(float(g["spread_bps"].median())),
        "pooled_p95_bps": rnd(float(g["spread_bps"].quantile(0.95))),
        "median_of_ticker_medians_bps": rnd(float(tick_meds.median())),
    }
spreads["by_time_bucket"] = by_bucket

BOUGHT = ["FTNT", "APH", "ZM", "NFLX", "GRMN", "CSCO", "PANW", "AVGO", "MCHP", "CME", "AMZN"]
bought_tbl = {}
for t in BOUGHT:
    g = ok[ok["ticker"] == t]
    if g.empty:
        continue
    row = {"n": int(len(g)), "all_day_p50_bps": rnd(float(g["spread_bps"].median())),
           "all_day_p95_bps": rnd(float(g["spread_bps"].quantile(0.95)))}
    for name, _, _ in BUCKETS:
        gg = g[g["bucket"] == name]
        row[name + "_p50_bps"] = rnd(float(gg["spread_bps"].median())) if len(gg) else None
    bought_tbl[t] = row
spreads["bought_names"] = bought_tbl
json.dump(spreads, open(OUT_DIR / "spreads.json", "w"), indent=2)

# tight subset: names whose IEX median spread is small enough that the IEX mid
# is a usable proxy for the true consolidated mid
TIGHT_BPS = 25.0
tight_names = {t for t, v in per_ticker.items() if v["p50_bps"] <= TIGHT_BPS}
spreads["tight_subset"] = {
    "definition_bps": TIGHT_BPS,
    "n_tickers": len(tight_names),
    "tickers": sorted(tight_names),
}
json.dump(spreads, open(OUT_DIR / "spreads.json", "w"), indent=2)


# ------------------------------------------------- 3. timing counterfactuals
def load_open(ticker):
    p = ROOT / "data/ohlcv" / ticker / "1d.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "split_ratio" not in df.columns:
        df["split_ratio"] = float("nan")
    df = df[["open", "close", "split_ratio"]]
    df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
    return df


ohlcv_cache = {}
def get_ohlcv(t):
    if t not in ohlcv_cache:
        ohlcv_cache[t] = load_open(t)
    return ohlcv_cache[t]


WINDOWS = {
    "open_plus5_0935_0940": (9 * 60 + 35, 9 * 60 + 40),
    "midday_1100_1300": (11 * 60, 13 * 60),
    "close_minus30_1525_1535": (15 * 60 + 25, 15 * 60 + 35),
    "near_close_1550_1600": (15 * 60 + 50, 16 * 60),
}

# per ticker-session window mids
win_mids = {}  # (date,ticker) -> {window: mid}
for (d, t), g in ok.groupby(["date", "ticker"]):
    e = {}
    for w, (lo, hi) in WINDOWS.items():
        gg = g[(g["tod"] >= lo) & (g["tod"] < hi)]
        e[w] = float(gg["mid"].dropna().mean()) if len(gg) else None
    win_mids[(d, t)] = e

# deltas vs official open, raw and SPY-adjusted
spy_delta = {}  # (date, window) -> bps
for d in tk["date"].unique():
    o = get_ohlcv("SPY")
    if o is None or d not in o.index:
        continue
    op = float(o.loc[d, "open"])
    e = win_mids.get((d, "SPY"), {})
    for w in WINDOWS:
        m = e.get(w)
        spy_delta[(d, w)] = (m - op) / op * 1e4 if m else None

def dist(v):
    if not v:
        return None
    return {"n": len(v), "mean": rnd(statistics.mean(v), 1), "p50": rnd(statistics.median(v), 1),
            "p25": rnd(pct(v, 0.25), 1), "p75": rnd(pct(v, 0.75), 1),
            "p5": rnd(pct(v, 0.05), 1), "p95": rnd(pct(v, 0.95), 1)}


deltas = defaultdict(list)            # window -> [bps]  (all names)
deltas_adj = defaultdict(list)        # SPY-adjusted (all names)
deltas_t = defaultdict(list)          # tight subset only
deltas_t_adj = defaultdict(list)
per_sess_tmp = defaultdict(lambda: defaultdict(list))
n_pairs = 0
for (d, t), e in win_mids.items():
    if t == "SPY":
        continue
    o = get_ohlcv(t)
    if o is None or d not in o.index:
        continue
    op = float(o.loc[d, "open"])
    if not op or op <= 0:
        continue
    n_pairs += 1
    for w in WINDOWS:
        m = e.get(w)
        if m is None:
            continue
        bps = (m - op) / op * 1e4
        deltas[w].append(bps)
        sd = spy_delta.get((d, w))
        if sd is not None:
            deltas_adj[w].append(bps - sd)
        if t in tight_names:
            deltas_t[w].append(bps)
            if sd is not None:
                deltas_t_adj[w].append(bps - sd)
            per_sess_tmp[d][w].append(bps)

timing = {
    "method": "window mid (IEX) vs official opening print (OHLCV 1d open); "
              "positive bps = buying in that window cost MORE than the open fill",
    "n_ticker_sessions_with_open": n_pairs,
    "windows_vs_official_open_bps_ALL_names": {},
    "windows_vs_official_open_bps_TIGHT_subset": {},
}
for w in WINDOWS:
    timing["windows_vs_official_open_bps_ALL_names"][w] = {
        "raw": dist(deltas[w]), "spy_adjusted": dist(deltas_adj[w])}
    timing["windows_vs_official_open_bps_TIGHT_subset"][w] = {
        "raw": dist(deltas_t[w]), "spy_adjusted": dist(deltas_t_adj[w])}

# per-session medians (tight subset) to expose day-to-day sign instability
timing["per_session_median_bps_vs_open_TIGHT"] = {
    d: {w: rnd(statistics.median(v), 1) for w, v in ws.items()}
    for d, ws in sorted(per_sess_tmp.items())
}

# --- recent actual buys: decision-ref -> next-open slippage + counterfactuals
con = sqlite3.connect(f"file:{ROOT/'data/runs.alpaca.db'}?mode=ro", uri=True)
buys = pd.read_sql_query(
    "SELECT trade_date, ticker, shares, price, order_type FROM trades "
    "WHERE action='buy_pending' AND trade_date>='2026-06-22' ORDER BY trade_date, ticker",
    con,
)
buys = buys.drop_duplicates(subset=["trade_date", "ticker"], keep="first")
buy_rows = []
for _, b in buys.iterrows():
    t, d, ref = b["ticker"], b["trade_date"], float(b["price"])
    o = get_ohlcv(t)
    if o is None:
        continue
    later = [dd for dd in o.index if dd > d]
    if not later:
        buy_rows.append({"ticker": t, "decision_date": d, "shares": b["shares"],
                         "ref_price": rnd(ref), "fill_session": None,
                         "note": "not yet filled (next session beyond data)"})
        continue
    fs = later[0]
    # OHLCV is back-adjusted: a split AFTER the decision date makes the stored
    # open incomparable with the live (unadjusted) decision reference price.
    post_splits = o.loc[[dd for dd in o.index if dd > d], "split_ratio"].fillna(0)
    if (post_splits > 0).any():
        buy_rows.append({"ticker": t, "decision_date": d, "fill_session": fs,
                         "note": "EXCLUDED: split after decision date back-adjusts "
                                 "OHLCV; ref price incomparable"})
        continue
    op = float(o.loc[fs, "open"])
    slip = (op - ref) / ref * 1e4
    spy = get_ohlcv("SPY")
    spy_slip = None
    if spy is not None and d in spy.index and fs in spy.index:
        spy_slip = (float(spy.loc[fs, "open"]) - float(spy.loc[d, "close"])) / float(spy.loc[d, "close"]) * 1e4
    row = {"ticker": t, "decision_date": d, "shares": float(b["shares"]),
           "order_type": b["order_type"], "ref_price": rnd(ref), "fill_session": fs,
           "open_fill_proxy": rnd(op), "overnight_slip_bps": rnd(slip, 1),
           "spy_overnight_bps": rnd(spy_slip, 1) if spy_slip is not None else None,
           "excess_slip_bps": rnd(slip - spy_slip, 1) if spy_slip is not None else None}
    e = win_mids.get((fs, t))
    if e:
        for w in WINDOWS:
            m = e.get(w)
            row["alt_" + w + "_bps_vs_open"] = rnd((m - op) / op * 1e4, 1) if m else None
    buy_rows.append(row)
timing["recent_buys"] = buy_rows

slips = [r["overnight_slip_bps"] for r in buy_rows if r.get("overnight_slip_bps") is not None]
ex = [r["excess_slip_bps"] for r in buy_rows if r.get("excess_slip_bps") is not None]
timing["recent_buys_summary"] = {
    "n_filled": len(slips),
    "overnight_slip_bps": {"mean": rnd(statistics.mean(slips), 1), "p50": rnd(statistics.median(slips), 1),
                           "min": rnd(min(slips), 1), "max": rnd(max(slips), 1)},
    "excess_over_spy_bps": {"mean": rnd(statistics.mean(ex), 1), "p50": rnd(statistics.median(ex), 1)},
}
json.dump(timing, open(OUT_DIR / "timing.json", "w"), indent=2)

# ------------------------------------------------- 4. policy shadow files
recs = [json.loads(l) for l in open(PILOT / "entry_timing_shadow.jsonl")]
base = {}
for r in recs:
    if r["policy"] == "immediate_first_eligible_tick" and r.get("entry_ref_quote"):
        base[(r["date"], r["ticker"])] = r["entry_ref_quote"]
pol_stats = {}
for pol in ["vwap_cross", "opening_range_breakout", "pullback_to_ref"]:
    diffs, diffs_t, elig, cens = [], [], 0, Counter()
    for r in recs:
        if r["policy"] != pol:
            continue
        if not r.get("eligible") or not r.get("entry_ref_quote"):
            cens[r.get("censored_reason") or "ineligible"] += 1
            continue
        elig += 1
        b = base.get((r["date"], r["ticker"]))
        if b:
            bps = (r["entry_ref_quote"] - b) / b * 1e4
            diffs.append(bps)
            if r["ticker"] in tight_names:
                diffs_t.append(bps)
    pol_stats[pol] = {
        "n_eligible": elig, "censored": dict(cens),
        "entry_vs_immediate_bps_ALL": dist(diffs),
        "entry_vs_immediate_bps_TIGHT": dist(diffs_t),
    }
policy = {"entry_timing_shadow": {
    "n_records": len(recs),
    "sessions": sorted({r["date"] for r in recs}),
    "note": "hypothetical BUY entries for ALL 145 watchlist names each session; "
            "baseline = immediate_first_eligible_tick (~09:35 ET); positive bps = later policy paid more",
    "policies_vs_immediate": pol_stats}}

precs = [json.loads(l) for l in open(PILOT / "entry_timing_policy_shadow.jsonl")]
psum = defaultdict(list)
for r in precs:
    if r.get("saved_vs_baseline_bps") is not None:
        psum[r["policy"]].append(r["saved_vs_baseline_bps"])
policy["entry_timing_policy_shadow"] = {
    "n_records": len(precs),
    "sessions": sorted({r["session_date"] for r in precs}),
    "tickers": sorted({r["ticker"] for r in precs}),
    "saved_vs_baseline_bps_by_policy": {k: [rnd(x, 1) for x in v] for k, v in psum.items()},
    "note": "tiny sample (real parent intents, 2 sessions); listed for completeness only",
}
json.dump(policy, open(OUT_DIR / "policy_shadow.json", "w"), indent=2)

# ------------------------------------------------- 5. dollar value bound
buys_all = pd.read_sql_query(
    "SELECT trade_date, ticker, invest FROM trades WHERE action='buy_pending' "
    "AND trade_date>='2026-05-25'", con)
inv = buys_all["invest"].dropna()
med_notional = float(inv.median())
mean_notional = float(inv.mean())
dollar = {
    "recent_buy_notional_usd": {"n_buys_since_2026-05-25": int(len(inv)),
                                "median": rnd(med_notional), "mean": rnd(mean_notional),
                                "min": rnd(float(inv.min())), "max": rnd(float(inv.max()))},
    "assumption": "~250 entries/yr at current sizes (buys only; improvement applies per entry)",
    "annual_value_usd_of_X_bps_improvement": {
        f"{x}bps": rnd(250 * mean_notional * x / 1e4, 2) for x in [5, 10, 20, 30, 50]
    },
    "account_equity_usd_2026_07_10": 10753,
}
json.dump(dollar, open(OUT_DIR / "dollar_value.json", "w"), indent=2)
con.close()

# tight-subset half-spread cost by bucket (only honest spread-cost estimate)
tight_ok = ok[ok["ticker"].isin(tight_names)]
half_spread = {}
for name, _, _ in BUCKETS:
    g = tight_ok[tight_ok["bucket"] == name]
    half_spread[name] = {
        "n": int(len(g)),
        "half_spread_p50_bps": rnd(float(g["spread_bps"].median()) / 2, 2),
        "half_spread_p95_bps": rnd(float(g["spread_bps"].quantile(0.95)) / 2, 2),
    }
spreads["tight_subset_half_spread_cost_by_bucket"] = half_spread
json.dump(spreads, open(OUT_DIR / "spreads.json", "w"), indent=2)

# ------------------------------------------------- headline print
print("=== HEADLINES ===")
print("sessions:", inventory["overall"]["n_sessions"], inventory["overall"]["sessions"])
print("rows ok/censored:", inventory["overall"]["total_rows_ok"], inventory["overall"]["total_rows_censored"])
print("tickers:", inventory["overall"]["n_tickers"], "tight:", len(tight_names))
print("per-session inventory:", json.dumps(inventory["per_session"], indent=1))
print("spread cross-ticker:", spreads["cross_ticker_summary"])
print("tight half-spread by bucket:", json.dumps(half_spread, indent=1))
print("timing TIGHT:", json.dumps(timing["windows_vs_official_open_bps_TIGHT_subset"], indent=1))
print("per-session medians TIGHT:", json.dumps(timing["per_session_median_bps_vs_open_TIGHT"], indent=1))
print("recent buys summary:", json.dumps(timing["recent_buys_summary"], indent=1))
print("policy stats:", json.dumps(pol_stats, indent=1))
print("policy shadow small:", json.dumps(policy["entry_timing_policy_shadow"], indent=1))
print("dollar:", json.dumps(dollar, indent=1))
