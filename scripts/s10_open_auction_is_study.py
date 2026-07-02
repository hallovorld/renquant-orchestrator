#!/usr/bin/env python3
"""S10: the full open-auction implementation-shortfall study (#231 S10; upgrades
POC-C leg 1 from point estimate to CI-backed verdict on the available history).

Improvements over POC-C:
  1. TRUE daily VWAP where 10-minute bars exist (data/intraday/<T>/10min.parquet
     carries a per-bar `vwap`; day VWAP = Σ(vwap·vol)/Σvol over RTH bars),
     falling back to OHLC4 with an explicit `ref_kind` label (10min coverage
     ends 2026-05-01; later fills use the proxy).
  2. Date-clustered BLOCK BOOTSTRAP 95% CI on every reference delta (fills on
     the same day share the day's market move — i.i.d. bootstrap would
     overstate precision).
  3. An explicit decision readout for the #230 §8 S10 row: is the prize
     point-estimate materially >10bps AND is its CI separated from zero?

Estimand: per real filled buy order, (fill − reference)/reference in bps for
reference ∈ {open, day_vwap, close}. fill≈open is already established (POC-C:
fills stamped 09:30:00–01); the economic quantity is fill_vs_vwap / fill_vs_close
— what a delayed entry could have obtained on the same day.

R2 (2026-07-02, Codex review): fill_vs_vwap_bps previously pooled the
true-10min-VWAP cohort (20 fills) with the OHLC4-proxy cohort (21 fills) into
one mean/CI — a single "+40.1bps vs day VWAP" number that mixed two different
references with different bias/variance. Fixed: the two cohorts are now
reported and adjudicated SEPARATELY; true-VWAP is the primary estimand for the
"vs VWAP" verdict, the proxy cohort is descriptive-only and never pulls that
verdict. Fetching real SIP minute bars to eliminate the proxy cohort entirely
was considered but not pursued this round — no SIP/minute-bar fetch utility
exists yet anywhere in this codebase, and #237 (this same session) flags that
even the *entitlement* to request `feed=sip` from Alpaca has not yet been
verified against the live key; building that pipeline is out of scope for
this fix. The materiality verdict is now a frozen lower-CI-bound rule (not the
point estimate), and the "days to significance" figure is now clearly labeled
a fragile planning scenario, with a separate, properly-powered prospective
sample-size estimate against the 10bps materiality bar (not the observed
effect) using cluster-robust (day-level) variance.

R3 (2026-07-02, Codex review): the prospective power calculation powered a
test against materiality_bps relative to ZERO (denominator = materiality_bps
alone) — that is not the preregistered claim (H0: mu<=materiality_bps vs
H1: mu>materiality_bps), whose correct denominator is
(mu_alternative - materiality_bps) for a stated alternative effect above the
bar; at mu_alternative==materiality_bps the true required n is infinite.
Fixed: `_cluster_robust_prospective_n_days` now reports a sensitivity table
across prespecified alternatives (20/30/50bps) instead of one point figure,
with day-clustering/autocorrelation assumptions stated explicitly. Also: the
materiality rule's CURRENT application to the existing 10-day cohort is now
labeled RETROSPECTIVE/DESCRIPTIVE (the rule was introduced after earlier
revisions had already exposed this data's shape) rather than a prospective
decision made before inspecting results — a genuinely prospective
confirmatory test requires a new, non-overlapping cohort going forward.

Reproduce:
  cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a && \
    .venv/bin/python <orchestrator>/scripts/s10_open_auction_is_study.py
Inputs (read-only): Alpaca /v2/orders (closed, filled buys);
  data/ohlcv/<T>/1d.parquet; data/intraday/<T>/10min.parquet.
Output: doc/research/evidence/2026-07-02-roadmap-pocs/s10_open_auction_is.json
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
BASE = os.environ.get("ALPACA_BASE_URL", "https://api.alpaca.markets")
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
N_BOOT = 5000
SEED = 20260702
MATERIALITY_BPS = 10.0
# Prospective power target for the NEXT (real, prereg'd) confirmatory sample.
POWER_Z_ALPHA2 = 1.96  # two-sided alpha=0.05
POWER_Z_BETA = 0.84    # 80% power


def _daily(t):
    p = os.path.join(RQ, "data/ohlcv", t, "1d.parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    df.columns = [c.lower() for c in df.columns]
    if "date" in df.columns:
        df = df.set_index("date")
    return df.sort_index()


def _true_vwap(t, day):
    p = os.path.join(RQ, "data/intraday", t, "10min.parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    df.columns = [c.lower() for c in df.columns]
    idx = pd.to_datetime(df.index)
    # bars are UTC-stamped; RTH 09:30–16:00 ET = 13:30–20:00 UTC (EDT) or
    # 14:30–21:00 (EST). Select by ET wall clock to be DST-correct.
    et = idx.tz_localize("UTC").tz_convert("America/New_York") if idx.tz is None \
        else idx.tz_convert("America/New_York")
    day_mask = (et.date == day.date())
    rth = day_mask & (et.time >= pd.Timestamp("09:30").time()) & \
        (et.time < pd.Timestamp("16:00").time())
    g = df.loc[rth]
    if len(g) < 10 or g["volume"].sum() <= 0:
        return None
    return float((g["vwap"] * g["volume"]).sum() / g["volume"].sum())


def _fills():
    req = urllib.request.Request(
        f"{BASE}/v2/orders?status=closed&side=buy&limit=500&direction=desc",
        headers={"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                 "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]})
    orders = json.load(urllib.request.urlopen(req))
    rows = []
    for o in orders:
        if o.get("filled_avg_price") is None or float(o.get("filled_qty") or 0) == 0:
            continue
        ts = pd.Timestamp(o["filled_at"]).tz_convert("America/New_York")
        day = ts.normalize().tz_localize(None)
        b = _daily(o["symbol"])
        if b is None or day not in b.index:
            continue
        bar = b.loc[day]
        fill = float(o["filled_avg_price"])
        tv = _true_vwap(o["symbol"], day)
        ref_vwap = tv if tv is not None else (bar.open + bar.high + bar.low + bar.close) / 4
        rows.append({
            "symbol": o["symbol"], "date": str(day.date()),
            "ref_kind": "true_vwap_10min" if tv is not None else "ohlc4_proxy",
            "fill_vs_open_bps": (fill / bar.open - 1) * 1e4,
            "fill_vs_vwap_bps": (fill / ref_vwap - 1) * 1e4,
            "fill_vs_close_bps": (fill / bar.close - 1) * 1e4,
        })
    return pd.DataFrame(rows)


def _cluster_boot(df, col, seed=SEED, n_boot=N_BOOT):
    """Date-clustered bootstrap of the mean (resample DAYS with replacement).

    Returns None for empty input. For n_days < 2 the CI is not a meaningful
    measure of precision (every bootstrap resample just repeats the single
    available day, understating uncertainty) — callers must check
    `reliable_ci` before treating ci95 as trustworthy.
    """
    if df.empty:
        return None
    rng = np.random.default_rng(seed)
    days = df["date"].unique()
    groups = {d: g[col].to_numpy() for d, g in df.groupby("date")}
    means = []
    for _ in range(n_boot):
        pick = rng.choice(days, size=len(days), replace=True)
        vals = np.concatenate([groups[d] for d in pick])
        means.append(vals.mean())
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "mean": round(float(df[col].mean()), 1),
        "median": round(float(df[col].median()), 1),
        "ci95": [round(float(lo), 1), round(float(hi), 1)],
        "n_fills": int(len(df)),
        "n_days": int(len(days)),
        "reliable_ci": bool(len(days) >= 2),
    }


def _materiality_verdict(stat, materiality_bps=MATERIALITY_BPS):
    """Equivalence/superiority rule: material only if the CI LOWER bound
    clears the bar; not-material only if the CI UPPER bound stays below it;
    otherwise INCONCLUSIVE. A bare point estimate above the bar is not
    sufficient — its CI may still include values at or below the bar (or
    below zero).

    R3 (2026-07-02, Codex review): this rule's CURRENT application to the
    existing 10-day cohort is RETROSPECTIVE/DESCRIPTIVE, not a prospective
    confirmatory test — the rule itself was introduced in a later revision of
    this study, AFTER earlier revisions had already exposed the data's point
    estimates and general shape. The 10bps threshold is reasonable and
    externally motivated, but its application here was informed by hindsight.
    A genuinely prospective/confirmatory application of this SAME frozen rule
    requires a NEW, NON-OVERLAPPING cohort collected after the rule was
    fixed (e.g. a fresh SIP-sourced sample with no overlap with the 10 days
    analyzed here) — only that future application should be treated as a
    true confirmatory test."""
    if stat is None:
        return "NO_DATA"
    if not stat["reliable_ci"]:
        return "INCONCLUSIVE_TOO_FEW_DAYS"
    lo, hi = stat["ci95"]
    if lo > materiality_bps:
        return "MATERIAL"
    if hi < materiality_bps:
        return "NOT_MATERIAL"
    return "INCONCLUSIVE"


SENSITIVITY_ALTERNATIVES_BPS = (20.0, 30.0, 50.0)


def _n_days_for_alternative(sigma, materiality_bps, mu_alternative_bps):
    """One-sided superiority test H0: mu <= materiality_bps vs H1: mu >
    materiality_bps. The detectable gap is (mu_alternative - materiality_bps),
    NOT materiality_bps alone (which would power a test against a null of
    zero, a different and easier claim than the one actually preregistered).
    At mu_alternative == materiality_bps there is no gap to detect and the
    required n is infinite — returns math.inf explicitly rather than a
    silently-wrong finite number.
    """
    gap = mu_alternative_bps - materiality_bps
    if gap <= 0:
        return float("inf")
    z = POWER_Z_ALPHA2 + POWER_Z_BETA
    return (z * sigma / gap) ** 2


def _cluster_robust_prospective_n_days(df, col, materiality_bps=MATERIALITY_BPS,
                                        alternatives_bps=SENSITIVITY_ALTERNATIVES_BPS):
    """Prospective sample-size sensitivity table for a FUTURE confirmatory
    test of the preregistered one-sided superiority claim H0: mu <=
    materiality_bps vs H1: mu > materiality_bps.

    A single number here is misleading: the required n depends entirely on
    what true effect size ("mu_alternative") you assume and want power to
    detect above the materiality bar. Powering against materiality_bps alone
    (treating the null as zero) understates the true requirement — at
    mu_alternative == materiality_bps the true required n is infinite, since
    there is zero gap between the null and alternative to resolve. This
    reports a sensitivity table across several prespecified, economically
    plausible alternatives instead of one point figure.

    Cluster-robust: sigma is the day-level (not fill-level) standard
    deviation, since fills within a day are not independent observations.
    This assumes trading DAYS themselves are independent draws — if fill
    quality is autocorrelated day-to-day (e.g. a multi-day liquidity regime),
    this understates the true required sample size; no autocorrelation
    correction is applied here, flagged as a known limitation.
    """
    if df.empty:
        return None
    day_means = df.groupby("date")[col].mean().to_numpy()
    n_days = len(day_means)
    if n_days < 2:
        return None
    sigma = float(day_means.std(ddof=1))
    if sigma <= 0:
        return None
    sensitivity = []
    for mu_alt in alternatives_bps:
        n_required = _n_days_for_alternative(sigma, materiality_bps, mu_alt)
        sensitivity.append({
            "mu_alternative_bps": mu_alt,
            "gap_vs_materiality_bar_bps": round(mu_alt - materiality_bps, 1),
            "required_n_days_80pct_power": (
                None if not np.isfinite(n_required) else int(np.ceil(n_required))
            ),
        })
    return {
        "method": "cluster_robust_day_level_sd, one-sided superiority test "
                  f"H0: mu<={materiality_bps}bps vs H1: mu>{materiality_bps}bps; "
                  "required n powered against (mu_alternative - materiality_bps), "
                  "NOT materiality_bps alone (that would power a test against a "
                  "null of zero, not the actual preregistered threshold)",
        "assumptions": "day-level means are treated as independent draws (no "
                       "day-to-day autocorrelation correction); if fill quality "
                       "is autocorrelated across days this UNDERSTATES the true "
                       "required sample size",
        "day_level_sd_bps": round(sigma, 1),
        "current_n_days": int(n_days),
        "materiality_bar_bps": materiality_bps,
        "sensitivity_by_alternative": sensitivity,
        "z_alpha2": POWER_Z_ALPHA2,
        "z_beta_80pct_power": POWER_Z_BETA,
    }


def analyze(df, seed=SEED, n_boot=N_BOOT, materiality_bps=MATERIALITY_BPS):
    """Pure function: fills DataFrame -> full result dict. Split out from
    main() so tests can exercise it against synthetic fixtures without
    hitting the network or the filesystem."""
    if df.empty:
        return {
            "estimand": "per real filled buy: (fill − ref)/ref bps; "
                        "ref ∈ {open, day_vwap[true|proxy], close}",
            "ref_kind_counts": {},
            "stats_date_clustered_bootstrap": {},
            "vwap_cohorts": {},
            "verdict": {"vs_day_vwap_true": "NO_DATA", "vs_close": "NO_DATA"},
            "fills": [],
        }

    open_stat = _cluster_boot(df, "fill_vs_open_bps", seed=seed, n_boot=n_boot)
    close_stat = _cluster_boot(df, "fill_vs_close_bps", seed=seed, n_boot=n_boot)

    true_df = df[df["ref_kind"] == "true_vwap_10min"]
    proxy_df = df[df["ref_kind"] == "ohlc4_proxy"]
    vwap_true_stat = _cluster_boot(true_df, "fill_vs_vwap_bps", seed=seed, n_boot=n_boot)
    vwap_proxy_stat = _cluster_boot(proxy_df, "fill_vs_vwap_bps", seed=seed, n_boot=n_boot)

    vwap_true_verdict = _materiality_verdict(vwap_true_stat, materiality_bps)
    close_verdict = _materiality_verdict(close_stat, materiality_bps)

    power = _cluster_robust_prospective_n_days(true_df, "fill_vs_vwap_bps", materiality_bps)

    verdict = {
        "vs_day_vwap_true": vwap_true_verdict,
        "vs_close": close_verdict,
        "vwap_proxy_cohort_is_descriptive_only": True,
        "reading": (
            "S10 verdict per #230 §8, R3 (frozen rule, applied RETROSPECTIVELY/"
            "DESCRIPTIVELY to the already-inspected 10-day cohort — the rule was "
            "introduced after earlier revisions exposed this data's point estimates, "
            "so this application cannot be called a prospective confirmatory test; a "
            "genuine confirmatory application of this same frozen rule requires a new, "
            "non-overlapping cohort collected going forward): MATERIAL requires the "
            f"date-clustered CI's LOWER bound to exceed {materiality_bps}bps; "
            f"NOT_MATERIAL requires the CI's UPPER bound to stay below "
            f"{materiality_bps}bps; otherwise INCONCLUSIVE. The primary estimand is "
            "the TRUE-10min-VWAP cohort only (n=%d fills / %d days) — the OHLC4-proxy "
            "cohort (n=%d fills / %d days) is reported for reference but never moves this "
            "verdict, since it uses a different, coarser reference with different "
            "bias/variance. G105 kill-branch status: neither GO nor KILL is triggered by "
            "an INCONCLUSIVE result — the branch remains UNRESOLVED pending a properly "
            "powered, genuinely prospective confirmatory sample on new data (see "
            "prospective_power_vs_vwap_true)."
        ) % (
            vwap_true_stat["n_fills"] if vwap_true_stat else 0,
            vwap_true_stat["n_days"] if vwap_true_stat else 0,
            vwap_proxy_stat["n_fills"] if vwap_proxy_stat else 0,
            vwap_proxy_stat["n_days"] if vwap_proxy_stat else 0,
        ),
    }

    return {
        "estimand": "per real filled buy: (fill − ref)/ref bps; "
                    "ref ∈ {open, day_vwap[true|proxy], close}",
        "ref_kind_counts": df["ref_kind"].value_counts().to_dict(),
        "stats_date_clustered_bootstrap": {
            "fill_vs_open_bps": open_stat,
            "fill_vs_close_bps": close_stat,
        },
        "vwap_cohorts": {
            "true_vwap_10min": vwap_true_stat,
            "ohlc4_proxy": vwap_proxy_stat,
        },
        "prospective_power_vs_vwap_true": power,
        "verdict": verdict,
        "fills": df.to_dict("records"),
    }


def main() -> None:
    df = _fills()
    out = analyze(df)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "s10_open_auction_is.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k != "fills"}, indent=2))


if __name__ == "__main__":
    main()
