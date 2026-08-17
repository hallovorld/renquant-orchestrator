#!/usr/bin/env python
"""Regime detector assessment — measurement battery (part 1 of 3).

Read-only derivation script for doc/research/2026-08-17-regime-detector-assessment.md.
Deterministic: no RNG; input clamped to END_DATE so re-runs reproduce the memo
numbers even after the SPY parquet gains new bars.

Label series computed on RenQuant SPY 1d.parquet (clamped 2016-01-04..2026-08-14):
  L = stateless approximation, legacy (hurst-only BULL_CALM)     [research pre-06-01]
  V = stateless approximation, v2026-05-31 (vol-path BULL_CALM)  [research default / WF gate]
  S = serving replica: kernel.regime.detect_regime, prod GMM artifact,
      strategy_config.json regime block, state persisted across bars,
      simple pct_change returns (last 100) INCLUDING current bar (matches
      adapters/runner.py:763-767).

Inputs (read-only; paths overridable via env, hashes in the committed manifest):
  RQ_UMBRELLA     RenQuant umbrella root  (default ~/git/github/RenQuant)
  RQ_COMMON_SRC   renquant-common src dir (default ~/git/github/renquant-common/src)

Outputs (written next to this script):
  2026-08-17-regime-detector-measurements.json
  2026-08-17-regime-detector-label-series.csv

Run:
  ~/git/github/RenQuant/.venv/bin/python \
      doc/research/data/2026-08-17-regime-detector-measurements.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
PREFIX = "2026-08-17-regime-detector"
END_DATE = pd.Timestamp("2026-08-14")  # data cutoff used by the memo

RQ = Path(os.environ.get("RQ_UMBRELLA", str(Path.home() / "git/github/RenQuant")))
COMMON = Path(os.environ.get("RQ_COMMON_SRC",
                             str(Path.home() / "git/github/renquant-common/src")))
R104 = RQ / "backtesting" / "renquant_104"
SPY_PATH = RQ / "data" / "ohlcv" / "SPY" / "1d.parquet"

sys.path.insert(0, str(R104))          # kernel.*
sys.path.insert(0, str(COMMON))        # renquant_common

from renquant_common.hmm_regime_labels import compute_hmm_regime_labels  # noqa: E402
from kernel.regime import RegimeState, detect_regime  # noqa: E402

spy = pd.read_parquet(SPY_PATH).sort_index()
spy.index = pd.to_datetime(spy.index)
spy = spy.loc[:END_DATE]
close = spy["close"].astype(float)

# compute_hmm_regime_labels reads a path; hand it the clamped slice so the
# result is independent of bars appended after END_DATE.
with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tf:
    clamped_path = Path(tf.name)
spy.to_parquet(clamped_path)

# ── Series L and V (stateless research approximation) ────────────────────────
lab_L = compute_hmm_regime_labels(clamped_path, detector_version="legacy").set_index("date")["regime"]
lab_V = compute_hmm_regime_labels(clamped_path, detector_version="v2026-05-31").set_index("date")["regime"]
clamped_path.unlink()

# ── Series S (serving replica) ───────────────────────────────────────────────
config = json.load(open(R104 / "strategy_config.json"))
gmm_art = json.load(open(R104 / "artifacts" / "prod" / "spy-gmm-regime.json"))

simple_rets = close.pct_change().dropna()
state = RegimeState()
rows = []
dates = spy.index
START = 210  # warmup for MA200 + hurst
for i in range(START, len(dates)):
    d = dates[i]
    # serving: last 100 simple returns INCLUDING today's bar
    upto = simple_rets.loc[:d].values[-100:]
    spy_df_t = spy.loc[:d]
    state = detect_regime(np.asarray(upto, dtype=float), spy_df_t, gmm_art, state, config)
    rows.append({
        "date": d,
        "regime": state.regime,
        "confidence": state.confidence,
        "in_transition": state.in_transition,
        "gmm_max": max(state.gmm_probs.values()) if state.gmm_probs else np.nan,
        "gmm_bear": state.gmm_probs.get("BEAR", np.nan) if state.gmm_probs else np.nan,
        "gmm_dom": max(state.gmm_probs, key=state.gmm_probs.get) if state.gmm_probs else None,
    })
S = pd.DataFrame(rows).set_index("date")

# align all on serving index
idx = S.index
L = lab_L.reindex(idx)
V = lab_V.reindex(idx)
df = pd.DataFrame({"S": S["regime"], "V": V, "L": L,
                   "conf": S["confidence"], "gmm_max": S["gmm_max"],
                   "gmm_bear": S["gmm_bear"], "gmm_dom": S["gmm_dom"],
                   "in_transition": S["in_transition"]})

REGIMES = ["BULL_CALM", "BULL_VOLATILE", "CHOPPY", "BEAR"]


def episodes(series: pd.Series):
    """list of (regime, start, end, n_days)"""
    out = []
    cur, start = None, None
    prev_d = None
    for d, r in series.items():
        if r != cur:
            if cur is not None:
                out.append((cur, start, prev_d, series.loc[start:prev_d].shape[0]))
            cur, start = r, d
        prev_d = d
    out.append((cur, start, prev_d, series.loc[start:prev_d].shape[0]))
    return out


def series_stats(series: pd.Series, name: str):
    occ = series.value_counts().to_dict()
    eps = episodes(series)
    ep_by = {}
    for r, s, e, n in eps:
        ep_by.setdefault(r, []).append(n)
    # transitions
    trans = {}
    prev = None
    for r in series:
        if prev is not None and r != prev:
            trans[(prev, r)] = trans.get((prev, r), 0) + 1
        prev = r
    n_switch = sum(trans.values())
    flicker = [(r, n) for r, s, e, n in eps if n <= 2]
    stats = {
        "name": name,
        "n_days": int(len(series)),
        "occupancy": {k: int(v) for k, v in occ.items()},
        "occupancy_pct": {k: round(100 * v / len(series), 1) for k, v in occ.items()},
        "n_episodes": len(eps),
        "n_switches": n_switch,
        "flicker_episodes_le2d": len(flicker),
        "flicker_share_of_episodes": round(len(flicker) / len(eps), 3),
        "episode_stats": {
            r: {"n_ep": len(v), "mean_len": round(float(np.mean(v)), 1),
                "median_len": float(np.median(v)), "max_len": int(max(v)),
                "n_le2d": int(sum(1 for x in v if x <= 2))}
            for r, v in ep_by.items()},
        "switches_per_year": round(n_switch / (len(series) / 252), 1),
    }
    return stats, eps


stats_S, eps_S = series_stats(df["S"], "serving detect_regime (S)")
stats_V, eps_V = series_stats(df["V"].dropna(), "stateless v2026-05-31 (V)")
stats_L, eps_L = series_stats(df["L"].dropna(), "stateless legacy (L)")

# window restricted to WF fold span for comparability with the 125-fold context
wf_lo, wf_hi = pd.Timestamp("2019-01-14"), pd.Timestamp("2026-03-02")
wf_mask = (df.index >= wf_lo) & (df.index <= wf_hi)
occ_wf = {k: df.loc[wf_mask, k].value_counts().to_dict() for k in ("S", "V", "L")}
n_wf_days = int(wf_mask.sum())
occ_wf_pct = {k: {kk: round(100 * vv / n_wf_days, 1) for kk, vv in v.items()}
              for k, v in occ_wf.items()}

# ── agreement matrices ───────────────────────────────────────────────────────
def agree(a, b):
    m = df[[a, b]].dropna()
    same = float((m[a] == m[b]).mean())
    cm = pd.crosstab(m[a], m[b])
    return same, cm

same_SV, cm_SV = agree("S", "V")
same_SL, cm_SL = agree("S", "L")
same_VL, cm_VL = agree("V", "L")
# lag-adjusted: research label at t+1 uses data through t (excludes current bar)
v_shift = df["V"].shift(-1)
same_SV_lag = float((df["S"] == v_shift).dropna().mean())

# BEAR-only agreement (decision-relevant for exit line)
bear_S = df["S"] == "BEAR"
bear_V = df["V"] == "BEAR"
bear_both = int((bear_S & bear_V).sum())
bear_only_S = int((bear_S & ~bear_V).sum())
bear_only_V = int((~bear_S & bear_V).sum())

# ── mechanical drawdown BEAR dating (Lunde–Timmermann style, causal trigger) ─
def drawdown_dating(close: pd.Series, thr: float):
    """Enter bear when drawdown from running peak <= -thr; exit when
    price recovers >= +thr off the running trough (or new high).
    Returns episodes with peak/trigger/trough/exit dates."""
    peak = close.iloc[0]
    peak_d = close.index[0]
    in_bear = False
    trough = None
    trough_d = None
    eps = []
    cur = None
    for d, px in close.items():
        if not in_bear:
            if px > peak:
                peak, peak_d = px, d
            elif px / peak - 1 <= -thr:
                in_bear = True
                trough, trough_d = px, d
                cur = {"peak_date": peak_d, "peak": peak, "trigger_date": d}
        else:
            if px < trough:
                trough, trough_d = px, d
            if px / trough - 1 >= thr or px > peak:
                cur.update({"trough_date": trough_d, "trough": trough,
                            "exit_date": d,
                            "depth": round(trough / cur["peak"] - 1, 4)})
                eps.append(cur)
                in_bear = False
                peak, peak_d = px, d
                cur = None
    if in_bear:
        cur.update({"trough_date": trough_d, "trough": trough,
                    "exit_date": None, "depth": round(trough / cur["peak"] - 1, 4)})
        eps.append(cur)
    return eps


mech15 = drawdown_dating(close.loc[idx[0]:], 0.15)
mech20 = drawdown_dating(close.loc[idx[0]:], 0.20)
mech10 = drawdown_dating(close.loc[idx[0]:], 0.10)


def bear_lag_report(series: pd.Series, mech_eps, name):
    """Per mechanical episode: detector entry/exit timing."""
    out = []
    bear_days = series[series == "BEAR"].index
    for ep in mech_eps:
        p, t, tr = ep["peak_date"], ep["trigger_date"], ep["trough_date"]
        ex = ep["exit_date"] or series.index[-1]
        win = series.loc[p:ex]
        in_win = bear_days[(bear_days >= p) & (bear_days <= ex)]
        first = in_win[0] if len(in_win) else None
        # trading-day lags
        ti = series.index
        def td(a, b):
            if a is None or b is None:
                return None
            return int(ti.searchsorted(b) - ti.searchsorted(a))
        # coverage of decline phase (peak..trough)
        decline = series.loc[p:tr]
        cov = float((decline == "BEAR").mean()) if len(decline) else np.nan
        # exit behavior: last BEAR day in window vs trough
        last = in_win[-1] if len(in_win) else None
        out.append({
            "peak": str(p.date()), "trigger": str(t.date()),
            "trough": str(tr.date()), "exit": str(ex.date()),
            "depth": ep["depth"],
            "first_bear": str(first.date()) if first is not None else None,
            "lag_vs_peak_td": td(p, first),
            "lag_vs_trigger_td": td(t, first),
            "decline_coverage": round(cov, 3),
            "last_bear": str(last.date()) if last is not None else None,
            "last_bear_minus_trough_td": td(tr, last),
            "n_bear_days_in_window": int(len(in_win)),
            "n_days_peak_to_trough": td(p, tr),
        })
    return out


lag_S15 = bear_lag_report(df["S"], mech15, "S")
lag_V15 = bear_lag_report(df["V"].dropna(), mech15, "V")
lag_S10 = bear_lag_report(df["S"], mech10, "S")
lag_V10 = bear_lag_report(df["V"].dropna(), mech10, "V")

# false-alarm accounting vs the 10% dating (most permissive mechanical set):
def false_alarms(series, mech_eps):
    windows = []
    for ep in mech_eps:
        ex = ep["exit_date"] or series.index[-1]
        windows.append((ep["peak_date"], ex))
    bear_eps = [(r, s, e, n) for r, s, e, n in episodes(series) if r == "BEAR"]
    fa = []
    for r, s, e, n in bear_eps:
        if not any((s <= w_e and e >= w_s) for w_s, w_e in windows):
            fa.append({"start": str(s.date()), "end": str(e.date()), "days": n})
    return bear_eps, fa

bear_eps_S, fa_S = false_alarms(df["S"], mech10)
bear_eps_V, fa_V = false_alarms(df["V"].dropna(), mech10)

# ── posterior / confidence stats (serving) ───────────────────────────────────
conf_stats = {
    "mean_confidence": round(float(df["conf"].mean()), 3),
    "confidence_by_regime": {r: round(float(df.loc[df.S == r, "conf"].mean()), 3)
                             for r in REGIMES if (df.S == r).any()},
    "gmm_max_posterior_mean": round(float(df["gmm_max"].mean()), 3),
    "gmm_max_lt_0.6_share": round(float((df["gmm_max"] < 0.6).mean()), 3),
    "gmm_dom_occupancy": df["gmm_dom"].value_counts().to_dict(),
    "share_days_in_transition": round(float(df["in_transition"].mean()), 4),
    "gmm_bear_gt_0.5_days": int((df["gmm_bear"] > 0.5).sum()),
}

# serving final label vs GMM dominant label (how much do overrides do?)
dom_agree = float((df["S"] == df["gmm_dom"]).dropna().mean())

out = {
    "span": [str(idx[0].date()), str(idx[-1].date())],
    "stats_S": stats_S, "stats_V": stats_V, "stats_L": stats_L,
    "occ_wf_window": {k: {kk: int(vv) for kk, vv in v.items()} for k, v in occ_wf.items()},
    "occ_wf_window_pct": occ_wf_pct,
    "occ_wf_window_n_days": n_wf_days,
    "agreement": {
        "S_vs_V_same_day": round(same_SV, 4),
        "S_vs_V_lag1": round(same_SV_lag, 4),
        "S_vs_L": round(same_SL, 4),
        "V_vs_L": round(same_VL, 4),
        "bear_both": bear_both, "bear_only_serving": bear_only_S,
        "bear_only_research": bear_only_V,
        "serving_final_vs_gmm_dominant_agree": round(dom_agree, 4),
    },
    "confusion_S_rows_V_cols": cm_SV.to_dict(),
    "mech15_episodes": [{k: (str(v) if hasattr(v, "isoformat") else v) for k, v in ep.items()} for ep in mech15],
    "mech10_episodes": [{k: (str(v) if hasattr(v, "isoformat") else v) for k, v in ep.items()} for ep in mech10],
    "mech20_episodes": [{k: (str(v) if hasattr(v, "isoformat") else v) for k, v in ep.items()} for ep in mech20],
    "bear_lag_S_vs_15pct": lag_S15,
    "bear_lag_V_vs_15pct": lag_V15,
    "bear_lag_S_vs_10pct": lag_S10,
    "bear_lag_V_vs_10pct": lag_V10,
    "bear_episodes_serving": [{"start": str(s.date()), "end": str(e.date()), "days": n} for _, s, e, n in bear_eps_S],
    "bear_episodes_research": [{"start": str(s.date()), "end": str(e.date()), "days": n} for _, s, e, n in bear_eps_V],
    "false_alarms_S_vs_10pct": fa_S,
    "false_alarms_V_vs_10pct": fa_V,
    "confidence_stats": conf_stats,
}

(OUT / f"{PREFIX}-measurements.json").write_text(json.dumps(out, indent=1, default=str))
df.to_csv(OUT / f"{PREFIX}-label-series.csv")
print(f"wrote {PREFIX}-measurements.json + {PREFIX}-label-series.csv "
      f"({len(df)} rows {out['span'][0]}..{out['span'][1]})")
