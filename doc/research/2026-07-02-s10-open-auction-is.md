# S10: open-auction implementation-shortfall study — INCONCLUSIVE

STATUS: research evidence (read-only). Task S10 of the unified plan (#231, Term EXEC);
upgrades POC-C leg 1 from point estimate to a CI-backed formal verdict.
DATE: 2026-07-02 (R2: corrected mixed-reference estimand; R3: corrected power-calculation
denominator + retrospective/descriptive framing; R4: corrected one-sided critical value
+ "prespecified" wording; all 2026-07-02)
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
#237). The materiality verdict is now a CI-lower-bound rule, not the point estimate.

## R3 correction (Codex review): power-calc denominator + retrospective framing

R2's prospective power calculation powered a test against the materiality bar **relative
to zero** (denominator = materiality_bps alone) — that is not the preregistered claim
(`H0: mu<=10bps` vs `H1: mu>10bps`), whose correct denominator is `(mu_alternative -
10bps)` for a stated alternative effect above the bar; at `mu_alternative==10bps` the
true required n is infinite (no gap to detect). R3 replaces the single point figure with
a sensitivity table across three alternatives (20/30/50bps) — see below.

R3 also corrects the "decided before inspecting results" framing: the materiality rule
was actually introduced in R2, **after** R1 had already exposed this data's point
estimates and general shape — its CURRENT application to this same 10-day cohort is
therefore RETROSPECTIVE/DESCRIPTIVE, not a valid prospective confirmatory test, even
though the 10bps threshold itself is a reasonable, externally-motivated number. A
genuinely prospective/confirmatory application of this same frozen rule requires a new,
non-overlapping cohort collected going forward.

## R4 correction (Codex review): one-sided critical value + "prespecified" wording

R3's power calculation described itself as a ONE-SIDED alpha=0.05 test but used
`z=1.96` — the TWO-SIDED critical value (correct one-sided value: `z≈1.645`). This
mismatch systematically OVERSTATED every required-n figure in the sensitivity table
below while presenting them as the smaller, correctly-sided numbers. Fixed: alpha and
tail (one-sided/two-sided) are now explicit function parameters, and the critical value
is computed from them via `scipy.stats.norm.ppf` rather than a hardcoded constant. All
sensitivity-table figures below are recomputed with the corrected `z≈1.645`.

R4 also corrects R3's own "prespecified alternatives" wording above: the 20/30/50bps
grid was actually chosen **after** this cohort's result was already observed, so it is
a POST-HOC sensitivity table for PLANNING purposes, not a prespecified/frozen
specification. A genuinely prospective confirmatory alternative and required sample
size must be frozen before collecting a new, non-overlapping cohort — not read off this
table.

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

## Verdict (per the #230 §8 S10 row, R3 rule — applied retrospectively to this cohort)

Equivalence/superiority rule, applied RETROSPECTIVELY/DESCRIPTIVELY to this
already-inspected sample (see R3 correction above — this is not a prospective
confirmatory test): **MATERIAL** requires the CI's lower bound to exceed +10bps;
**NOT_MATERIAL** requires the CI's upper bound to stay below +10bps; otherwise
**INCONCLUSIVE**.

- **vs true day VWAP (primary): INCONCLUSIVE.** CI [−14.8, +165.2] straddles both 0 and
  the 10bps bar. The point estimate is well above the bar, but the estimate is not
  precise enough at 10 independent days to call it material.
- **vs close: INCONCLUSIVE.** Same structure, CI [−51.4, +122.9].
- **OHLC4-proxy cohort is descriptive only** and does not move either verdict — its own
  point estimate (+2.1bps) is much smaller and would have pointed a pooled estimand in
  the wrong direction.
- **G105 kill-branch status: UNRESOLVED.** Neither GO nor KILL is triggered by an
  inconclusive result.

## Properly-powered prospective sample size (sensitivity table, not one point figure)

R1 reported "≈38–40 independent fill-days" to significance by extrapolating from the
*observed* +40bps effect and its standard error — a post-hoc calculation that assumes
the observed point estimate is the true effect, which overstates confidence. R2's
replacement computed a single required-n figure powered against the 10bps materiality
bar treated as a null of *zero* — but the actual preregistered claim is the one-sided
superiority test `H0: mu<=10bps` vs `H1: mu>10bps`, whose correct denominator is the gap
`(mu_alternative - 10bps)` for a stated alternative effect above the bar, not 10bps
alone. R3 replaced the single figure with a sensitivity table across three alternatives
(R4 corrects a critical-value error in that table — see below), using the same
cluster-robust (day-level) variance from the true-VWAP cohort:

- Day-level SD: **151.7bps** (the true-VWAP cohort's per-day mean dispersion — the fills
  are extremely noisy at the day-cluster level).
- Assumption: day-level means are treated as independent draws (no day-to-day
  autocorrelation correction); if fill quality is autocorrelated across days, this
  UNDERSTATES the true required sample size.
- **R4 correction**: R3's table used the two-sided critical value `z=1.96` while
  describing a one-sided alpha=0.05 test (correct one-sided value: `z≈1.645`),
  systematically overstating every figure below. Recomputed with the corrected value:

| Assumed true effect (mu_alternative) | Gap vs 10bps bar | Required independent days (80% power, one-sided alpha=0.05) |
|---|---|---|
| 20bps | 10bps | ≈1,422 |
| 30bps | 20bps | ≈356 |
| 50bps | 40bps | ≈89 |

(At `mu_alternative==10bps`, i.e. zero gap, the required n is infinite — not computed.
R2's original single figure of "≈1,804 days" (computed with R3's since-corrected z=1.96)
numerically matched R3's 20bps row under that same z: R2's denominator of 10bps alone is
equivalent to the formula evaluated at `mu_alternative=20bps`, since `20-10=10` — R2 was
implicitly powering against a 20bps alternative while presenting it as if it were
powered against the 10bps bar itself. That structural coincidence is a property of the
denominator, not the critical value, so it still holds under R4's corrected z — R2's
figure would have been ≈1,422 days (matching this table's 20bps row) had it used the
correct one-sided critical value from the start.)

This remains a **fragile planning scenario** at every row, not a validated result — every
figure is highly sensitive to the day-level SD estimate, which itself comes from only 10
days. Even the most favorable alternative (50bps, an effect five times the
materiality bar) still requires ≈89 independent days — nearly 9x the current 10-day
sample, and every less-favorable alternative requires several hundred to well over a
thousand days, an impractically large sample under the current per-day-noise estimand.
If a future confirmatory attempt is
preregistered, it should use a materially different design (e.g. matched-pair or
paired-difference estimand to cut cross-day noise) rather than simply accumulating more
days under the current estimand.

## Roadmap effects

- #230 §8 S10 row: outcome branch is **UNRESOLVED** — not "material at point estimate,"
  not ruled out either. The true-VWAP point estimate remains suggestive (+80bps, well
  above the bar) but the current sample cannot distinguish it from noise.
- #208 §9.4 prereg input: use the measured right-skew (median ≪ mean in both cohorts)
  when choosing the estimand (median-IS or trimmed-mean-IS may be the better
  pre-registered target) — this observation is unchanged by the R2 correction.
- G105 kill-branch check: **UNRESOLVED** (neither GO nor KILL triggered).
