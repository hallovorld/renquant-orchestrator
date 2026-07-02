# S10: open-auction implementation-shortfall study — INCONCLUSIVE

STATUS: research evidence (read-only). Task S10 of the unified plan (#231, Term EXEC);
upgrades POC-C leg 1 from point estimate to a CI-backed formal verdict.
DATE: 2026-07-02 (R2: corrected mixed-reference estimand, 2026-07-02)
SCRIPT: `scripts/s10_open_auction_is_study.py` (one-command reproduce, constants at top).
EVIDENCE: `doc/research/evidence/2026-07-02-roadmap-pocs/s10_open_auction_is.json`.

## Upgrades over POC-C

1. **TRUE daily VWAP** where 10-minute bars exist (`data/intraday/<T>/10min.parquet`
   carries per-bar `vwap`; day VWAP = Σ(vwap·vol)/Σvol over RTH, DST-correct ET
   selection): 20/41 fills; the other 21 (post-2026-05-01, where 10min coverage ends)
   fall back to OHLC4 with an explicit `ref_kind` label.
2. **Date-clustered block bootstrap** (5,000 resamples of DAYS, seed fixed): fills on
   one day share the market move; i.i.d. CIs would overstate precision.

## R2 correction (Codex review): the pooled estimand was not coherent

R1 pooled the 20 true-10min-VWAP fills and the 21 OHLC4-proxy fills into one
`fill_vs_vwap_bps` mean/CI (+40.1bps). These are two different references with
different bias/variance — a single number cannot be called "vs day VWAP." R2 reports
and adjudicates them **separately**; the true-VWAP cohort is the primary estimand.
Fetching real SIP minute bars to eliminate the proxy cohort entirely was considered but
not pursued this round (no SIP/minute-bar fetch utility exists yet in this codebase, and
even Alpaca SIP feed *entitlement* has not been verified against the live key — see
#237). The materiality verdict is now a frozen CI-lower-bound rule, decided before
inspecting results, not the point estimate.

## Results

| Reference | mean bps | median bps | 95% CI (date-clustered) | n fills / n days |
|---|---|---|---|---|
| fill vs open (all fills, single reference) | −4.6 | 0.0 | [−23.0, +7.8] — **fills ARE the open auction** (re-confirmed) | 41 / 18 |
| fill vs close (all fills, single reference) | +43.4 | +27.4 | [−51.4, +122.9] | 41 / 18 |
| **fill vs day VWAP — TRUE cohort (primary estimand)** | **+80.0** | +14.8 | **[−14.8, +165.2]** | 20 / 10 |
| fill vs day VWAP — OHLC4-proxy cohort (descriptive only) | +2.1 | +21.3 | [−59.2, +52.0] | 21 / 8 |

The true-VWAP cohort's point estimate (+80.0bps) is actually *higher* than the R1
pooled figure — pooling with the near-zero proxy cohort had been diluting it. But its
CI is also far wider (only 10 independent days) and still includes both zero and
values well below the materiality bar.

## Verdict (per the #230 §8 S10 row, R2 frozen rule)

Frozen equivalence/superiority rule (decided before inspecting this sample): **MATERIAL**
requires the CI's lower bound to exceed +10bps; **NOT_MATERIAL** requires the CI's upper
bound to stay below +10bps; otherwise **INCONCLUSIVE**.

- **vs true day VWAP (primary): INCONCLUSIVE.** CI [−14.8, +165.2] straddles both 0 and
  the 10bps bar. The point estimate is well above the bar, but the estimate is not
  precise enough at 10 independent days to call it material.
- **vs close: INCONCLUSIVE.** Same structure, CI [−51.4, +122.9].
- **OHLC4-proxy cohort is descriptive only** and does not move either verdict — its own
  point estimate (+2.1bps) is much smaller and would have pointed a pooled estimand in
  the wrong direction.
- **G105 kill-branch status: UNRESOLVED.** Neither GO nor KILL is triggered by an
  inconclusive result.

## Properly-powered prospective sample size (not the R1 post-hoc figure)

R1 reported "≈38–40 independent fill-days" to significance by extrapolating from the
*observed* +40bps effect and its standard error — a post-hoc calculation that assumes
the observed point estimate is the true effect, which overstates confidence. R2 replaces
this with a genuine prospective calculation: sample size required for 80% power to
detect the **10bps materiality bar** (not the observed effect), using cluster-robust
(day-level) variance from the true-VWAP cohort:

- Day-level SD: **151.7bps** (the true-VWAP cohort's per-day mean dispersion — the fills
  are extremely noisy at the day-cluster level).
- Required independent days for 80% power at alpha=0.05: **≈1,804 days**.

This is a **fragile planning scenario**, not a validated result — it is highly sensitive
to the day-level SD estimate, which itself comes from only 10 days. It should be read as
"the true-VWAP fill population, at its currently observed dispersion, would need an
impractically large number of independent days to confirm a 10bps effect via this exact
estimand" — not as a commitment to collect 1,804 days of data. If a future confirmatory
attempt is preregistered, it should use a materially different design (e.g. matched-pair
or paired-difference estimand to cut cross-day noise) rather than simply accumulating
more days under the current estimand.

## Roadmap effects

- #230 §8 S10 row: outcome branch is **UNRESOLVED** — not "material at point estimate,"
  not ruled out either. The true-VWAP point estimate remains suggestive (+80bps, well
  above the bar) but the current sample cannot distinguish it from noise.
- #208 §9.4 prereg input: use the measured right-skew (median ≪ mean in both cohorts)
  when choosing the estimand (median-IS or trimmed-mean-IS may be the better
  pre-registered target) — this observation is unchanged by the R2 correction.
- G105 kill-branch check: **UNRESOLVED** (neither GO nor KILL triggered).
