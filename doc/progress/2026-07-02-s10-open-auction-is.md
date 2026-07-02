# S10 open-auction IS study — research PR

STATUS:   research evidence (read-only; script + JSON + memo; no code/config/broker change).
REVISION: r1.
WHAT:     task S10 (#231 Term EXEC): `scripts/s10_open_auction_is_study.py` upgrades POC-C to
          a formal verdict — TRUE 10-min VWAP references where coverage exists (20/41 fills;
          OHLC4-labeled fallback after 2026-05-01), date-clustered block bootstrap (5,000
          resamples, 18 independent days), and an explicit verdict block.
WHY/DIR:  the #230 §8 S10 row required the prize to be CI'd, not asserted. Result:
          fill≈open re-confirmed (−4.6 bps, median 0.0); prize vs same-day VWAP **+40.1 bps
          mean / +16.2 median, CI95 [−15.6, +99.2]** → **MATERIAL-BUT-UNPROVEN** (4× the
          10 bps bar at point estimate; CI includes 0 at N_days=18). Days-to-significance
          ≈38–40 → the N1 collector corpus is the binding step. Right-skew (median ≪ mean)
          feeds the §9.4 estimand choice (median/trimmed IS). G105 kill branch NOT triggered.
EVIDENCE: committed JSON with per-fill rows + ref_kind labels; reproduce with one command
          (script docstring). Read-only inputs: Alpaca closed orders, data/ohlcv,
          data/intraday 10min bars.
NEXT:     Codex review; collector corpus accrues N_days; the §9.4 prereg consumes the skew
          finding; re-run the script monthly (same command) as the standing EXEC-term metric.

ROUND 2 (Codex CHANGES_REQUESTED, 2026-07-02): the pooled fill_vs_vwap_bps estimand was
not coherent — it mixed 20 true-10min-VWAP fills with 21 OHLC4-proxy fills (different
references, different bias/variance) into one +40.1bps mean/CI; the materiality verdict
was set from the point estimate despite the CI including zero; "38-40 days to
significance" was a post-hoc power calculation using the observed effect as if it were
the true effect; "G105 kill branch NOT triggered" overclaimed resolution on an
inconclusive test; no tests existed for the new script.

Fix: `scripts/s10_open_auction_is_study.py` refactored around a pure `analyze(df)`
function (network-fetch separated from analysis, enabling tests against synthetic
fixtures). (1) true-VWAP and OHLC4-proxy cohorts now computed and reported separately
(`vwap_cohorts.true_vwap_10min` / `vwap_cohorts.ohlc4_proxy`); true-VWAP is the primary
estimand, proxy is descriptive-only and never moves the verdict. Fetching real SIP
minute bars to eliminate the proxy cohort was considered but not pursued — no SIP fetch
utility exists in this codebase yet, and #237 flags SIP entitlement itself as
unverified. (2) `_materiality_verdict()` is now a frozen CI-lower-bound rule (MATERIAL
requires CI lower bound > 10bps; NOT_MATERIAL requires CI upper bound < 10bps; else
INCONCLUSIVE), decided independent of the point estimate. (3) new
`_cluster_robust_prospective_n_days()` replaces the post-hoc days-to-significance
figure with a genuine prospective power calculation powered against the fixed 10bps
materiality bar (not the observed effect), using day-level cluster-robust SD. (4) G105
branch language corrected to UNRESOLVED (neither GO nor KILL triggered by an
inconclusive result). (5) new `tests/test_s10_open_auction_is_study.py` (7 tests):
mixed-cohort separation with a verdict-driven-by-primary-cohort-only assertion,
empty-data handling, single-day CI-unreliability flagging, DST-correct RTH bar
selection across a winter/summer transition, deterministic seeded resampling, and the
CI-lower-bound materiality rule directly.

**Re-run against the real committed fill data** (`analyze()` applied to the existing
41-fill dataset, no new network fetch needed): the corrected numbers are materially
different from R1's pooled figure — true-VWAP cohort alone: mean **+80.0bps** (higher
than R1's pooled +40.1, since pooling had diluted it with the near-zero proxy cohort),
CI95 **[−14.8, +165.2]** at only 10 independent days → verdict **INCONCLUSIVE** (was
"MATERIAL-BUT-UNPROVEN"). Proxy cohort alone: mean +2.1bps, CI [−59.2, +52.0] — much
smaller than assumed, would have pointed a pooled estimand in the wrong direction had it
dominated. Prospective power: day-level SD 151.7bps → ≈**1,804 days** required for 80%
power against the 10bps bar (vs. R1's post-hoc "38-40 days," which used the observed
effect as the assumed true effect). PR title changed from "...MATERIAL-BUT-UNPROVEN" to
reflect the corrected INCONCLUSIVE verdict. Research doc (`doc/research/2026-07-02-s10-
open-auction-is.md`) and the committed evidence JSON both regenerated with the R2
numbers. 7/7 new tests pass.

**Correcting the record:** the R1 "material-but-unproven, 4x the bar, 38-40 days to
significance" framing does not survive R2's methodology fix — it was an artifact of
pooling two different references and a post-hoc power calculation, not a robust finding.
The true-VWAP point estimate remains suggestive (well above the bar) but the corrected,
properly-scoped sample cannot distinguish it from noise; the S10/G105 branch is
UNRESOLVED, not resolved-toward-material.

ROUND 3 (Codex CHANGES_REQUESTED, 2026-07-02): the R2 power calculation's denominator
(`materiality_bps` alone) powers a test against a null of ZERO, not the actual
preregistered claim `H0: mu<=10bps` vs `H1: mu>10bps` — the correct denominator is
`(mu_alternative - 10bps)` for a stated alternative above the bar; at
`mu_alternative==10bps` the true required n is infinite. Also, "decided BEFORE
inspecting results" mischaracterized the materiality rule's application: the rule was
introduced in R2, AFTER R1 had already exposed the data's shape — its application to
this same cohort is retrospective/descriptive, not prospective.

Fix: `_cluster_robust_prospective_n_days()` now returns a sensitivity table across three
prespecified alternatives (20/30/50bps) via a new `_n_days_for_alternative()` helper,
each computed against `(mu_alternative - materiality_bps)`; `mu_alternative <=
materiality_bps` returns `math.inf` explicitly (surfaced as `null` in the JSON/table),
never a silently-wrong finite number. Day-clustering/autocorrelation assumptions are now
stated explicitly in the output (`assumptions` field). `_materiality_verdict()`'s
docstring and the `verdict.reading` text both now label the rule's application to this
cohort as RETROSPECTIVE/DESCRIPTIVE, with a genuine confirmatory test requiring a new,
non-overlapping cohort collected going forward. Research doc and evidence JSON
regenerated (`analyze()` re-applied to the existing 41-fill dataset, no new network
fetch needed) — sensitivity table: 20bps→≈1,804 days, 30bps→≈451 days, 50bps→≈113 days
(the 20bps row numerically matches R2's old "1,804 days" figure exactly, since R2's
formula was equivalent to implicitly powering against a 20bps alternative while
presenting it as powered against the 10bps bar itself). 5 new/updated tests
(`test_prospective_power_reports_sensitivity_not_post_hoc_point_estimate`,
`test_power_denominator_uses_gap_to_alternative_not_bar_alone`,
`test_power_at_or_below_materiality_bar_is_infinite_not_silently_finite`,
`test_power_sensitivity_n_decreases_as_alternative_grows`), 10/10 tests pass (was 7).

ROUND 4 (Codex CHANGES_REQUESTED, 2026-07-02): two more precision issues in R3's power
calculation. (1) The code described a ONE-SIDED alpha=0.05 superiority test
(`H0: mu<=materiality_bps` vs `H1: mu>materiality_bps`) but used `z=1.96` — the
TWO-SIDED critical value (correct one-sided value: `z≈1.645`) — systematically
OVERSTATING every required-n figure while labeling them one-sided. (2) R3 called the
20/30/50bps sensitivity grid "prespecified," but it was actually chosen AFTER this
cohort's result was already observed — a post-hoc planning table, not a genuinely
prospective specification.

Fix: `POWER_Z_ALPHA2`/hardcoded `1.96` replaced with `_z_alpha(alpha, one_sided)`, computed
via `scipy.stats.norm.ppf` from explicit `alpha`/`one_sided` parameters (default
alpha=0.05, one_sided=True, matching the test this script actually describes); same
treatment for `_z_beta(power)`. `_n_days_for_alternative()` and
`_cluster_robust_prospective_n_days()` both thread `alpha`/`one_sided`/`power` through as
real inputs rather than module constants, and the output dict now records `alpha`,
`one_sided`, and the actual `z_alpha` used, so a reader can verify the table matches the
claimed test. All "prespecified" language corrected to "post-hoc sensitivity table for
planning," with an explicit statement that a genuine confirmatory alternative/sample size
must be frozen prospectively on a new, non-overlapping cohort. Script re-run end-to-end
against the real 41-fill dataset (no new network fetch needed) — sensitivity table
recomputed with the corrected z: 20bps→≈1,422 days (was ≈1,804), 30bps→≈356 days (was
≈451), 50bps→≈89 days (was ≈113); the "R2 numerically matches the 20bps row" aside in
the research doc updated to reflect the corrected figure, since that coincidence is a
property of the denominator structure, not the critical value, and still holds. Research
doc and evidence JSON both regenerated. Fixed one existing test
(`test_power_denominator_uses_gap_to_alternative_not_bar_alone`) that hardcoded `1.96`
in its expected-value formula and would otherwise have started failing against the
corrected code; added 3 new tests (`test_power_z_alpha_one_sided_not_two_sided`,
`test_power_alpha_and_tail_are_explicit_not_hardcoded`,
`test_prospective_power_output_reports_alpha_and_actual_z_used`). 13/13 tests pass.
