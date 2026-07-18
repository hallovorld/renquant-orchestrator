# VetoWeakBuys small-n degeneration — read-only analysis

Date: 2026-07-17
Status: evidence memo (no behavior change; the fix is a separate design PR in
renquant-pipeline, the implementation owner of `VetoWeakBuysTask`)
Scope: live 104 buy funnel, sessions 2026-04-22 → 2026-07-17
Data: `data/runs.alpaca.db` (opened `mode=ro&immutable=1`), `data/ohlcv/*/1d.parquet`,
`logs/daily_104/*.log` (cross-validation)

## 1. Summary

The live buy-admission floor (`buy_floor: adaptive_mean_std`, i.e.
`floor = max(0.20, mean + 1.0 * sample_std)` computed on the current scan's
candidate rank_scores) degenerates when the scan set is small. On both
governed-override sessions to date — 2026-07-16 and 2026-07-17 — the scan
produced n=5 candidates and the floor exceeded the **maximum** candidate score,
vetoing 5/5 by construction and leaving the book ~86% cash:

| session | n | floor (mean+1σ) | max score | vetoed |
|---|---|---|---|---|
| 2026-07-16 | 5 | 0.561 | 0.557 (ATI) | 5/5 |
| 2026-07-17 | 5 | 0.577 | 0.564 (BWXT) | 5/5 |

The floor also produced a ranking inversion: on 07-16 it vetoed ATI
(rank_score 0.557, μ=+0.025) while GRMN sat in the book as a holding at
rank_score 0.549, μ=+0.022 — the gate blocks entries that score above names we
already hold.

At normal scan sizes (n≥70) the floor's marginal veto is statistically
indistinguishable from noise (§4). The defect is specific to small n, and small
scans are the **expected steady state while the diagnostic-only override is
active** (both override sessions scanned exactly 5 candidates against the same
145-name watchlist hash that yields 85 candidates on normal days). Recurrence
is therefore structural until fixed.

Recommendation (§5): **Option (a) — minimum-n guard.** Keep mean+1σ at n ≥ 10;
below that fall back to an absolute calibrated threshold (default 0.50 =
better-than-even calibrated probability), fail-closed to current behavior when
the config is absent.

## 2. Ground truth: veto history by session

Method: for every `pipeline_runs` row with `candidate_scores` rank_score rows
(role='candidate'), count `blocked_by='veto:rank_score_below_floor'`. Floor
mode classified per run by exactly reproducing the observed veto count from the
recorded scores (sample stdev, matching the implementation); classification
cross-validated against `VetoWeakBuysTask` log lines (e.g. 07-10: log
`floor=0.544 (n=85)` dropped 67 = DB 85 scored / 67 vetoed).

All 23 veto-active daily sessions since 04-22 ran `mean+1σ` mode in the live
DB (the `q0.80` quantile arm exists only in the shadow track). All-vetoed
sessions:

| date | n | floor | note |
|---|---|---|---|
| 2026-05-04 | 43 | 0.26 | score-scale collapse era (post 05-03 calibration fix) |
| 2026-05-06 | 45 | 0.26 | same |
| 2026-07-16 | 5 | 0.561 | governed-override scan; floor > max |
| 2026-07-17 | 5 | 0.577 | governed-override scan; floor > max |

Partial vetoes at normal n run 76–86% of candidates (by design: mean+1σ admits
roughly the top sixth of the cross-section).

## 3. Why small n guarantees all-veto

Monte Carlo, P(max < mean + 1·sample_std), 20k trials per n:

| n | iid normal | bootstrap from real score pool (n≥70 sessions) |
|---|---|---|
| 3 | 50% | 50% |
| 4 | 33% | 35% |
| 5 | 20% | 22% |
| 6 | 13% | 14% |
| 8 | 5.5% | 6.3% |
| 10 | 2.0% | 3.0% |
| 15 | 0.2% | 0.5% |
| ≥20 | ~0 | ~0 |

The realized rate at n=5 is 2/2, far above the ~20% iid baseline, because the
override-era scan sets are bimodal — 3 stocks (~0.53–0.56) plus 2 sector ETFs
(~0.45). The ETF cluster inflates the sample σ, pushing mean+1σ above the top
stock. With that shape the all-veto outcome is essentially deterministic, not a
20%-tail event. A self-referential threshold cannot express "is this candidate
good" at small n; it only expresses "is this candidate an outlier within a
5-name set".

## 4. Counterfactual: what did the veto cost?

Timing convention: next-open entry after the decision session, open-to-open
forward returns, excess vs SPY over the same window.

**All-vetoed days.** 07-16/07-17 entries are too recent to measure (first
complete h=1 window lands 2026-07-20). The May pair is measurable but is 2
days, from the score-scale-collapse era, with overlapping top-3 names
(AAPL/ABBV/AMAT):

| day | h=1 | h=5 | h=20 |
|---|---|---|---|
| 2026-05-04 top-3 | +0.63% | +1.76% | +7.26% |
| 2026-05-06 top-3 | −0.64% | +2.12% | +8.19% |

Directionally the floor cost real upside on those two days, but 2 overlapping
days carry no statistical weight.

**Era-wide marginal test** (the stronger evidence): for each of the 16–18
sessions with floor survivors (2026-05-22 → 2026-07-13), compare top-3 vetoed
names (the marginal kills) vs admitted names, session-paired, 10k-resample
bootstrap on the paired difference:

| horizon | vetoed top-3 excess | admitted excess | paired diff [90% CI] |
|---|---|---|---|
| 1d | +0.33% | +0.01% | +0.33% [−0.29%, +0.93%] |
| 5d | +0.95% | +1.34% | −0.39% [−1.72%, +0.86%] |
| 20d | +0.41% | +1.76% | −1.35% [−6.66%, +3.97%] (5 sessions, heavy overlap) |

**Honest verdict: NULL at normal n.** Every CI straddles zero. There is no
evidence the floor is destroying value at the margin on normal days, and no
evidence it is adding value either. This cuts both ways and disciplines the
fix: do **not** relax the floor globally (no measured payoff, unquantified
risk); do fix the small-n branch, where the failure is structural
(floor > max) rather than statistical, and where the counterfactual isn't
"marginally weaker names" but "zero capital deployment while holding names that
score below the vetoed candidates".

## 5. Design options and recommendation

**(a) Minimum-n guard — RECOMMENDED.**
`floor = max(buy_floor_min, mean+1σ)` when `n ≥ buy_floor_min_n` (default 10,
where P(all-veto) ≤ ~3%); otherwise
`floor = max(buy_floor_min, buy_floor_absolute_smalln)` (default 0.50 — the
calibrated better-than-even point, an absolute reference that does not
self-destruct at small n). Applied to 07-16: admits ATI/EME/BWXT (0.533–0.557),
still vetoes XLI/XLY (0.449); the admitted names then face the unchanged
downstream gates (conviction μ floor, Kelly min-edge, QP admission) — this
change widens one gate, it does not bypass the funnel.

**(b) Absolute calibrated threshold everywhere — NOT recommended now.** §4
shows no evidence the statistical floor misbehaves at normal n; replacing the
normal-n rule is a behavior change without measured justification and belongs,
if ever, to the G1 equal-weight / breadth research track.

**(c) Leave as-is — rejected.** The small-n branch is not a filter, it is a
deterministic "no entries" switch (2/2 all-veto, floor > max score both times),
and small scans recur every session while the override is active.

Limitation stated plainly: option (a) does **not** recover May-type all-veto
days (max score 0.26 « 0.50 — the calibrator scale itself had collapsed).
That failure class needs a score-scale integrity check on the calibrator
output, which is a separate, also-worthwhile detection improvement.

### AC6 HARD-gate framing (capital-admission gate change)

- **Exception path:** none at runtime. The small-n branch activates only via
  explicit config (`buy_floor_min_n`, `buy_floor_absolute_smalln`); no env-var
  or operator bypass is introduced.
- **Fail-closed shape:** config absent/invalid, or n below N0 with no absolute
  threshold set → current mean+1σ behavior (status quo, which fails toward
  no-entry). NaN handling (`veto:rank_score_nan`) unchanged.
- **Detection surface:** the veto log line already emits `n` and the floor
  formula; `FunnelIntegrityTask` already fires `single_gate_funnel_kill`
  (verified `funnel_integrity_structural=1` on both override sessions). Add
  one degradation-sentinel rule: `all-vetoed AND n < N0` → LOUD alarm, so a
  recurrence pages instead of reading as a quiet no-trade day.

## 6. Provenance and caveats

- DB opened read-only (`mode=ro&immutable=1`); no state mutated anywhere.
- Floor-mode classification is exact (reproduces recorded veto counts); 07-10
  additionally cross-checked against the daily log line.
- Forward returns use raw opens (dividends ignored — negligible at h≤20);
  h=5/h=20 windows overlap across sessions, so CIs understate true width;
  the May pair shares top-3 names across both days.
- The shadow q0.80 arm (top-20% quantile) was out of scope; note that at n=5
  a 0.80 quantile keeps exactly one name, so quantile mode alone is not the
  small-n fix either.
- Adjacent observations, out of scope here, recorded for the parent loop:
  the 07-17 13:55 launchd daily FATAL'd on stray branch
  `feat/g4-training-metadata-wiring` (recurrence of the 07-17 morning
  incident); the override-era scan producing only 5 candidates from a 145-name
  watchlist is unattributed upstream of the veto and deserves its own look.

## 7. Next step

Separate design PR in **renquant-pipeline** (owner of `VetoWeakBuysTask`)
implementing option (a) + the sentinel rule, citing this memo as evidence;
codex adversarial review; no deployment before the design PR lands and pins
bump through the normal path.
