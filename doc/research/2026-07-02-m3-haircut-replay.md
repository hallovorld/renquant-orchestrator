# M3: conviction uncertainty-haircut ledger replay — AC FAIL (removes more winners
than losers at the 20d horizon; thin-margin admits do NOT go to ~0)

DATE: 2026-07-02
TASK: unified-107 master plan (#231) Term TC row M3 / H2 roadmap §M3 — READ-ONLY
ledger replay of admit rule `mu − k·SE(mu) > floor` vs current `mu > floor`
(floor = 0.03, k ∈ {0.5, 1.0}). No config or behavior change; evidence for the
"config PR only if the replay shows the haircut removes more losers than winners"
gate. Verdict: that condition is NOT met on this data.

Reproduce: `python3 scripts/m3_haircut_replay.py` (sqlite `mode=ro`; deterministic
seed). Committed evidence: `doc/research/evidence/2026-07-02-m3/*.json`.

## Method

**Data.** `runs.alpaca.db` (read-only): `candidate_scores` (`role='candidate'`,
`mu IS NOT NULL`) joined to `pipeline_runs` (`run_type='live'`), deduplicated to
**one canonical daily full run per date** — latest `created_at` among runs with
≥40 candidate rows, the same discipline as the corrected S-TC study (#234). That
gives **26 canonical dates, 2026-05-04 → 2026-07-02**, 1,769 candidate rows with
mu, **430 floor-clearing** (mu > 0.03).

**SE(mu) proxy (a) — PRIMARY (stated honestly).** There is no SE column. Proxy =
cross-run dispersion: per (ticker, date), the sample stdev of that ticker's mu over
its trailing ≤10 canonical runs (≥3 obs required), **stratified by scorer era**
(NULL-model_type era → legacy per-ticker tournament → hf_patchtst → panel_ltr_xgboost;
windows never cross an era boundary — cross-era jumps are scorer churn, not sampling
noise). Limits: this is a *stability* proxy, not a sampling SE — within an era it
still conflates real information arrival, feature drift, and retrains. It is
computable at decision time (no lookahead). Coverage: SE defined for **301/430
(70%)** of floor-clearing rows; the remaining 30% are fresh entrants/short histories
(see the fixture finding below).

**SE(mu) proxy (b) — sensitivity.** The live panel calibrator JSON
(`panel-rank-calibration.alpha158_linear.json`, trained 2026-07-02, read-only)
persists only point knots + global metadata — **no per-name band is derivable**.
The only global figure is `er_std·√(1−pool_ic²)` ≈ 0.0458 (on the calibrator's own
5d-lookahead label scale, vs mu's 60d horizon). As a constant SE it is per-name-blind:
the "haircut" degenerates to a blunt floor raise to 0.053 (k=0.5) / 0.076 (k=1.0),
admitting 173/144 of 430 — all high-mu May-era names — and would remove the ENTIRE
June panel-era floor-clearing pool (mu_p90 ≈ 0.033–0.036). Not an
uncertainty-sensitive rule; reported for completeness only.

**Outcomes (honest deviation from the AC's fwd_60d).** `mu_horizon_days = 60`, but
**fwd_60d is unresolvable for the entire live window** (first live run 2026-04-23;
60 trading days have not elapsed — same forward-only posture as S5). Primary outcome
= **fwd_20d excess over SPY** (resolvable decision dates through 2026-06-03);
fwd_10d (≤06-17) and fwd_5d (≤06-25) as sensitivity. Weekend run dates (05-09/17/30)
map to the prior trading `as_of_date` for both legs. Winner = excess > 11 bps cost
proxy. Coverage over candidate rows with mu: fwd_20d 682/1769 resolved, fwd_10d
1016, fwd_5d 1323.

**Comparison.** Universe per horizon = floor-clearing candidates with defined SE and
resolved excess (downstream gates like sector/correlation apply identically under
both rules, so they are not conditioned on). Current admits all; haircut admits
`mu − k·SE > 0.03`. CI: circular **date-block bootstrap, block 13 as specified** —
degenerate by construction here (only 8–13 usable dates < block length; flagged in
the JSON, zero-width) — with block-5 and block-1 sensitivity carried alongside.
Strided (non-overlapping-window) subsample also computed: it collapses to 1 date at
a 28d stride — flagged, not usable.

## Results

Universe fwd_20d: **191 floor-clearing decisions over 8 dates** (all BULL_CALM; eras:
pre-tournament 155, legacy tournament 36). fwd_10d: 214/11 dates; fwd_5d: 223/13.

| horizon | k | removed | **winners removed** | **losers removed** | Δ expectancy (haircut − current) | block-5 95% CI | block-1 CI |
|---|---|---|---|---|---|---|---|
| fwd_20d (primary) | 0.5 | 33/191 | **18** | 15 | **+0.14 pp** | [−0.11, +0.82] pp | [−0.23, +0.77] pp |
| fwd_20d (primary) | 1.0 | 50/191 | **28** | 22 | **−0.51 pp** | **[−0.89, −0.01] pp** | [−1.41, +0.28] pp |
| fwd_10d | 0.5 | 36/214 | 17 | 19 | +0.11 pp | [−0.23, +1.02] pp | spans 0 |
| fwd_10d | 1.0 | 55/214 | 29 | 26 | −0.13 pp | [−0.53, +0.61] pp | spans 0 |
| fwd_5d | 0.5 | 40/223 | 15 | 25 | +0.14 pp | [−0.13, +1.12] pp | spans 0 |
| fwd_5d | 1.0 | 61/223 | 29 | 32 | −0.11 pp | [−0.34, +0.61] pp | spans 0 |

Key reads:

1. **At the primary horizon the haircut removes MORE winners than losers at both k**
   (18/15 and 28/22). Removed-set winner rate (54.5% at k=0.5, 56.0% at k=1.0) is at
   or *above* the universe base rate (53.4%) — on the winner/loser axis the removal
   is no better than random at 20d.
2. **At k=1.0 the haircut is actively harmful at 20d**: removed-set mean excess
   **+5.9%** vs kept-set +3.9% — high-dispersion names were the big BULL_CALM
   winners; expectancy delta −0.51 pp with a block-5 CI excluding 0 (block-1 CI
   spans 0 — treat as weak, not conclusive, significance).
3. Only fwd_5d k=0.5 removes meaningfully more losers than winners (15W/25L), and
   even there the expectancy delta CI spans 0. No configuration shows a
   significantly positive delta.
4. **Thin-margin AC not met.** Admission composition across all 23 floor-clearing
   dates (no outcomes needed): thin-margin (mu ∈ [0.030, 0.0375)) share of admitted
   goes 39.5% → **23.7%** (k=0.5) / **20.0%** (k=1.0) — nowhere near ~0. Reason:
   margin and stability are near-orthogonal (margin/SE p50 = 1.28, p10 = 0.14,
   p90 = 11.0); many thin-margin names are *stably* thin (low dispersion), so the
   haircut keeps them and instead cuts high-dispersion names — which at 20d were
   disproportionately winners.
5. **The rule cannot even rule on its motivating fixtures.** OXY and GRMN on
   06-30/07-01 (RS-2/POC-B forensic cases) have **SE undefined** — 1–2 mu
   observations in the panel_ltr_xgboost era (fresh entrants to the candidate pool).
   Any production version needs an explicit fresh-entrant fallback, and fail-open
   reproduces exactly the OXY 07-01 admission (blocked_by=broker_pending_submitted —
   it WAS bought) the haircut was meant to stop; fail-closed bans every new name for
   its first ~3 sessions. Pass-through sensitivity (undefined-SE admitted) does not
   change the headline: fwd_20d k=1.0 delta −0.49 pp, still 28W/22L removed.
6. **Per-regime cuts are BULL_CALM-only.** Every outcome-resolvable decision is
   BULL_CALM; the single BEAR date (06-11) was the hf_patchtst era's first canonical
   day (SE undefined). The haircut's behavior in BEAR is unmeasured.

## Honest calls (beyond the above)

- **Retired-era evidence.** All resolved outcomes come from the pre-tournament and
  legacy-tournament mu streams (May–early June). The CURRENT scorer
  (panel_ltr_xgboost, since 06-22) has zero resolved fwd_10d/20d outcomes. This
  verdict is about the historical mu streams' interaction with the rule — it cannot
  be assumed to transfer to the current scorer; re-run forward once panel-era
  outcomes age in (S5 ledger).
- **Unvalidated model (D1 pending).** This measures the HISTORICAL mu ordering; a
  haircut win/loss here neither validates nor indicts mu itself.
- **Overlapping horizons.** Consecutive decision dates share forward windows; the
  block bootstrap is the primary correction, the spec'd block-13 is degenerate at
  this sample size (flagged), and the strided subsample collapses to n=1 date.
  Treat all CIs as descriptive of THIS window, not as inference to future windows.
- **Survivorship.** Universe = names actually scored by live runs; the watchlist
  itself is winner-biased and this ledger cannot correct that.

## Verdict vs #231 M3 AC

**"Replay shows the haircut removes more losers than winners (net expectancy gain)"
— NOT MET.** At the horizon closest to mu's 60d target, both k remove more winners
than losers; k=1.0 shows a negative expectancy delta (weakly significant at block-5).
"Thin-margin buys → ~0" — NOT MET (20–24% of admitted stay thin-margin; the proxy
punishes instability, not thinness). **Do not ship the haircut as a gate config
change on this evidence.** The master plan's own contingency (H2 roadmap M3 row:
ship the thin-margin *alert*, observe-only) is the indicated route; revisit the gate
after (i) S5 accrues panel-era fwd_60d outcomes and (ii) a real per-name uncertainty
(ensemble/bootstrap band persisted at scoring time, not a stability proxy) exists —
those two are exactly the "S5 dependency; replay inconclusive" branch the plan
pre-declared, except the replay is not inconclusive: on retired-era data it is
directionally against the gate.
