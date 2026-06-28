#!/usr/bin/env python
"""PEAD %-surprise follow-up: EVENT-DRIVEN long-side economics + ORTHOGONALITY.

The cheap screen (scripts/pead_test.py) flagged %-surprise as the one lead. The short
leg is unmonetizable under our shorting mandate, so usability rests on the LONG leg. This
script measures it FAITHFULLY:

  (1) EVENT-DRIVEN long-only economics. Each POSITIVE-surprise event (top-quintile /
      top-decile of positive %-surprises) opens a holding the first trading day AFTER the
      announcement (+1d) and CLOSES it at the horizon (20d / 60d). Overlapping holdings
      AGGREGATE into one equal-weight portfolio, rebalanced daily as names enter/expire.
      Weights are applied with a one-day lag (no same-day look-ahead). Excess return is vs
      the equal-weight universe. Cost is charged on ACTUAL daily turnover from
      membership/weight changes (|Δw| summed over names and days), entry + exit, at an
      11 bps one-way rate. This replaces the prior single arbitrary calendar phase + a
      single fixed per-horizon cost subtraction, which overstated the edge.

  (1b) 63-PHASE dispersion of the OLD calendar-sampled design (every 63 trading days),
      swept over all 63 phase offsets, to show how phase-sensitive that framing was.

  (2) ORTHOGONALITY: per-date cross-sectional rank correlation of the %-surprise signal
      vs the canonical price factors (mom_12_1, mom_6_1, ma200_dist) on the same panel.

PIT / look-ahead honesty (downgraded per PR #203 review, 2026-06-28): the earnings parquet
is a SINGLE CURRENT one-shot harvest; `epsEstimated` is today's value, NOT a captured
pre-announcement consensus, and `lastUpdated` is a generic floor before 2024-09. The +1d
convention controls ENTRY TIMING only. ALL results are NON-POINT-IN-TIME EXPLORATORY
evidence, not a clean PIT backtest.

Reproducibility (same standard as scripts/sighunt.py, PR #202): `--as-of` (pinned, no
datetime.now), `--bars-cache`, `--earnings`, `--out`; input hashes + parameters + commit
in a manifest.json; output dir created. READ-ONLY. No orders, no git, no canonical writes.

Caveat carried forward: correlation vs the LIVE model scores is PENDING faithful
decision-ledger data (ledger too thin/impaired); flagged as follow-up, NOT fabricated.
"""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

DEFAULT_EARN = "/Users/renhao/git/github/RenQuant/data/fmp_harvest/earnings_291.parquet"
DEFAULT_BARS = "/tmp/sighunt/bars.parquet"
DEFAULT_OUT = "/tmp/pead/"

FWD = [20, 60]
TRAIL = 63           # old calendar-sampling cadence (used only for the phase-dispersion check)
LAG = 1              # enter the first trading day AFTER the announcement (timing only)
COST_ONEWAY_BPS = 11.0   # one-way cost charged on actual |Δw| turnover (entry + exit)
WINSOR_Q = 0.05      # floor |epsEstimated| at this quantile so tiny denominators can't dominate


# ---------------------------------------------------------------- repro helpers
def sha256_file(path):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_commit():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.check_output(
            ["git", "-C", here, "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def spearman_ic(sig_row, ret_row):
    m = sig_row.notna() & ret_row.notna()
    if m.sum() < 5:
        return np.nan, m.sum()
    a = sig_row[m].rank()
    bb = ret_row[m].rank()
    if a.std() == 0 or bb.std() == 0:
        return np.nan, m.sum()
    return np.corrcoef(a, bb)[0, 1], m.sum()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--as-of", required=True,
                    help="Pinned end date YYYY-MM-DD (no datetime.now). Bars/events end here.")
    ap.add_argument("--bars-cache", default=DEFAULT_BARS, help="Cached close-panel parquet (read-only).")
    ap.add_argument("--earnings", default=DEFAULT_EARN,
                    help="FMP earnings harvest parquet (read-only, current one-shot harvest).")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output directory (created if missing).")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    out = args.out if args.out.endswith("/") else args.out + "/"
    as_of = pd.Timestamp(args.as_of).normalize()

    # ---------------------------------------------------------------- load
    bars = pd.read_parquet(args.bars_cache)
    bars.index = pd.to_datetime(bars.index)
    bars = bars.sort_index()
    bars = bars[bars.index <= as_of]
    uni = list(bars.columns)
    trading_days = bars.index
    px = bars.copy()
    colidx = {c: i for i, c in enumerate(uni)}

    e = pd.read_parquet(args.earnings)
    e['date'] = pd.to_datetime(e['date'])
    e = e[e['symbol'].isin(uni)].copy()
    e = e.dropna(subset=['epsActual', 'epsEstimated'])
    e = e[(e['date'] >= bars.index.min()) & (e['date'] <= as_of)]
    e = e.sort_values(['symbol', 'date']).reset_index(drop=True)

    e['surp'] = e['epsActual'] - e['epsEstimated']
    # WINSORIZED %-surprise denominator (review note): floor |epsEstimated| at WINSOR_Q
    # quantile so tiny estimates near zero can't dominate the top-positive selection.
    denom_floor = float(e['epsEstimated'].abs().quantile(WINSOR_Q))
    denom = e['epsEstimated'].abs().clip(lower=denom_floor)
    e['pct_surp'] = e['surp'] / denom
    print(f"[winsor] %-surprise denominator floored at |epsEstimated| p{int(WINSOR_Q*100)} = {denom_floor:.4f}")
    print(f"[data] panel {px.shape[0]}d x {px.shape[1]} names  "
          f"{px.index.min().date()}..{px.index.max().date()}  n_events={len(e)}")

    def first_td_on_or_after(ts):
        idx = trading_days.searchsorted(ts, side='left')
        return idx if idx < len(trading_days) else None

    ret = px.pct_change()
    uni_daily = ret.mean(axis=1)   # equal-weight universe daily return

    # ================================================================
    # (1) EVENT-DRIVEN long-only economics
    # ================================================================
    print("\n=== (1) EVENT-DRIVEN long-only economics "
          "(faithful entry+exit, turnover-based cost) ===")

    def event_driven(top_frac, H):
        """Open each top-fraction positive-surprise event +1d, hold H trading days, expire.
        Aggregate overlapping holdings into one EW portfolio; daily-rebalance; lag weights
        one day (no same-day look-ahead); charge cost on actual |Δw| turnover."""
        pos = e[e['pct_surp'] > 0].copy()
        if len(pos) == 0:
            return None
        thresh = pos['pct_surp'].quantile(1.0 - top_frac)
        sel = pos[pos['pct_surp'] >= thresh]
        holdings = np.zeros((len(trading_days), len(uni)))
        for _, r in sel.iterrows():
            i0 = first_td_on_or_after(r['date'] + pd.Timedelta(days=LAG))
            if i0 is None:
                continue
            i1 = min(i0 + H, len(trading_days))
            holdings[i0:i1, colidx[r['symbol']]] = 1.0
        held = pd.DataFrame(holdings, index=trading_days, columns=uni)
        nheld = held.sum(axis=1)
        w = held.div(nheld.replace(0, np.nan), axis=0).fillna(0.0)   # EW among held
        # portfolio return: weights set at entry act on the NEXT day's return (one-day lag)
        port = (w.shift(1).fillna(0.0) * ret.fillna(0.0)).sum(axis=1)
        excess = (port - uni_daily).iloc[1:]
        # actual one-way turnover: |Δw| summed over names, per day (counts entry AND exit)
        dturn = (w - w.shift(1)).abs().sum(axis=1).iloc[1:]
        tot_turn = float(dturn.sum())
        cost = tot_turn * COST_ONEWAY_BPS / 1e4
        gross_cum = float(excess.sum())
        net_cum = gross_cum - cost
        days = len(excess)
        yrs = days / 252.0
        mu = excess.mean()
        sd = excess.std(ddof=1)
        daily_t = mu / (sd / np.sqrt(days)) if sd > 0 else np.nan
        return dict(
            leg=('top_quintile' if abs(top_frac - 0.20) < 1e-9 else 'top_decile'),
            horizon=H, n_active_days=days, avg_held=float(nheld.mean()),
            n_events_sel=int(len(sel)), tot_turnover=tot_turn,
            gross_cum_excess_bps=gross_cum * 1e4, cost_bps=cost * 1e4,
            net_cum_excess_bps=net_cum * 1e4, net_ann_excess_bps=(net_cum / yrs) * 1e4,
            mean_daily_excess_bps=mu * 1e4, daily_t=daily_t,
        )

    ed_rows = []
    for tf in (0.20, 0.10):
        for H in FWD:
            row = event_driven(tf, H)
            if row is not None:
                ed_rows.append(row)
    ed_df = pd.DataFrame(ed_rows)
    pd.set_option('display.width', 220)
    print(ed_df.to_string(index=False))
    print("[read] net_cum = cumulative net excess over the whole sample; net_ann = annualized; "
          "daily_t = t-stat of mean DAILY portfolio excess (the honest significance metric).")

    # ---------------------------------------------------------------- (1b) 63-phase dispersion of the OLD design
    print("\n=== (1b) 63-PHASE dispersion of the OLD calendar-sampled design "
          "(top-quintile, fixed 11bps/rebal) ===")
    TRAIL_LOCAL = TRAIL
    pct_panel = pd.DataFrame(index=trading_days, columns=uni, dtype=float)
    for sym, g in e.groupby('symbol'):
        for _, row in g.sort_values('date').iterrows():
            i0 = first_td_on_or_after(row['date'] + pd.Timedelta(days=LAG))
            if i0 is None:
                continue
            pct_panel.iloc[i0:min(i0 + TRAIL_LOCAL, len(trading_days)),
                           pct_panel.columns.get_loc(sym)] = row['pct_surp']
    fwd_panels = {h: px.shift(-h) / px - 1.0 for h in FWD}

    def phase_net(top_frac, H, offset):
        fwd = fwd_panels[H]
        rebal = trading_days[252 + offset::TRAIL_LOCAL]
        exc = []
        for d in rebal:
            if d not in fwd.index:
                continue
            sig = pct_panel.loc[d]
            r = fwd.loc[d]
            ru = r[r.notna()]
            if len(ru) < 10:
                continue
            pos = sig[(sig.notna()) & (sig > 0)]
            common = pos.index.intersection(ru.index)
            if len(common) < 5:
                continue
            pos = pos.loc[common]
            sel = pos[pos.rank(pct=True) >= 1.0 - top_frac].index
            sr = r.loc[sel].dropna()
            if len(sr) == 0:
                continue
            exc.append(sr.mean() - ru.mean())
        if not exc:
            return np.nan
        return np.nanmean(exc) * 1e4 - COST_ONEWAY_BPS

    phase_rows = []
    for H in FWD:
        nets = np.array([phase_net(0.20, H, off) for off in range(TRAIL_LOCAL)])
        nets = nets[~np.isnan(nets)]
        phase_rows.append(dict(
            horizon=H, n_phases=len(nets), mean_net_bps=float(nets.mean()),
            std_net_bps=float(nets.std()), min_net_bps=float(nets.min()),
            max_net_bps=float(nets.max()), frac_phases_pos=float((nets > 0).mean()),
        ))
        print(f" H={H}: across {len(nets)} phases  net mean={nets.mean():.1f}bps "
              f"std={nets.std():.1f}  [min {nets.min():.1f}, max {nets.max():.1f}]  "
              f"frac>0={np.mean(nets > 0):.2f}")
    phase_df = pd.DataFrame(phase_rows)
    print(" -> the OLD single-phase headline was one draw from a wide phase distribution; "
          "the event-driven table above is the faithful read.")

    # ---------------------------------------------------------------- (1c) long-only IC (positive side only)
    print("\n=== (1c) long-only IC (restricted to POSITIVE %-surprise names) ===")
    loic_rows = []
    for h in FWD:
        fwd = fwd_panels[h]
        common = pct_panel.index.intersection(fwd.index)
        ics = []
        for dt in common:
            sig = pct_panel.loc[dt]
            pos = sig[(sig.notna()) & (sig > 0)]
            if len(pos) < 5:
                continue
            r = fwd.loc[dt].reindex(pos.index)
            ic, _ = spearman_ic(pos, r)
            if not np.isnan(ic):
                ics.append(ic)
        ics = np.array(ics)
        loic_rows.append({
            'horizon': h, 'n_dates': len(ics),
            'long_only_mean_IC': np.nanmean(ics),
            'hit_rate': (ics > 0).mean() if len(ics) else np.nan,
        })
    loic_df = pd.DataFrame(loic_rows)
    print(loic_df.to_string(index=False))

    # ================================================================
    # (2) ORTHOGONALITY vs canonical price factors
    # ================================================================
    print("\n=== (2) ORTHOGONALITY: rank-corr of %-surprise vs price factors ===")
    factors = {
        'mom_12_1': px.shift(21) / px.shift(252) - 1.0,
        'mom_6_1': px.shift(21) / px.shift(126) - 1.0,
        'ma200_dist': px / px.rolling(200, min_periods=150).mean() - 1.0,
    }
    orth_rows = []
    for fname, fpanel in factors.items():
        rhos = []
        for dt in pct_panel.index:
            sig = pct_panel.loc[dt]
            if dt not in fpanel.index:
                continue
            fac = fpanel.loc[dt]
            m = sig.notna() & fac.notna()
            if m.sum() < 10:
                continue
            a = sig[m].rank()
            b = fac[m].rank()
            if a.std() == 0 or b.std() == 0:
                continue
            rhos.append(np.corrcoef(a, b)[0, 1])
        rhos = np.array(rhos)
        orth_rows.append({
            'factor': fname, 'n_dates': len(rhos),
            'mean_rank_corr': np.nanmean(rhos),
            'abs_mean_rank_corr': np.nanmean(np.abs(rhos)),
            'p05': np.nanpercentile(rhos, 5) if len(rhos) else np.nan,
            'p95': np.nanpercentile(rhos, 95) if len(rhos) else np.nan,
        })
    orth_df = pd.DataFrame(orth_rows)
    print(orth_df.to_string(index=False))
    print("\nNOTE: correlation vs the LIVE model scores is PENDING faithful decision-ledger")
    print("data (ledger too thin/impaired; see prior audit). Flagged as follow-up; NOT fabricated.")

    # ---------------------------------------------------------------- save + manifest
    ed_df.to_csv(out + 'pead_eventdriven_economics.csv', index=False)
    phase_df.to_csv(out + 'pead_phase_dispersion.csv', index=False)
    loic_df.to_csv(out + 'pead_longonly_ic.csv', index=False)
    orth_df.to_csv(out + 'pead_orthogonality.csv', index=False)

    manifest = dict(
        script="scripts/pead_longonly_orthogonality.py",
        kind="NON-PIT exploratory event-driven long-only PEAD economics + orthogonality "
             "(single current one-shot FMP harvest; not a captured pre-announcement consensus)",
        pit_status="NON-POINT-IN-TIME: +1d convention controls entry timing only; "
                   "estimate values are from today's harvest, lastUpdated is a generic floor "
                   "pre-2024-09. ALL results are exploratory, not PIT-clean.",
        execution="event-driven (enter +1d, hold to horizon, overlapping holdings aggregated "
                  "into a daily-rebalanced EW portfolio, weights lagged one day); cost on "
                  "actual |Δw| turnover (entry + exit) at one-way rate.",
        as_of=args.as_of,
        code_commit=git_commit(),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        bars_cache=args.bars_cache,
        bars_cache_sha256=sha256_file(args.bars_cache),
        earnings=args.earnings,
        earnings_sha256=sha256_file(args.earnings),
        parameters=dict(
            fwd=FWD, trail=TRAIL, lag=LAG, cost_oneway_bps=COST_ONEWAY_BPS,
            winsor_q=WINSOR_Q, denom_floor=denom_floor,
        ),
        panel=dict(
            days=int(px.shape[0]), names=int(px.shape[1]),
            start=str(px.index.min().date()), end=str(px.index.max().date()),
        ),
        n_events=int(len(e)),
        kept_symbols=uni,
        kept_symbols_sha256=sha256_text(",".join(sorted(uni))),
    )
    with open(out + 'manifest_pead_longonly.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print("\n[saved] pead_eventdriven_economics.csv, pead_phase_dispersion.csv, "
          "pead_longonly_ic.csv, pead_orthogonality.csv, manifest_pead_longonly.json ->", out)
    print("[note] NON-PIT exploratory; single current harvest; +1d = entry timing only.")


if __name__ == "__main__":
    main()
