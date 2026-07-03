# C2 — quality composite (FMP-full): frozen-spec measurement — VERDICT: coverage precondition NOT MET; exploratory placebo-clean ≈ 0 (NON-VOTING; C2 remains OPEN)

STATUS: EXPLORATORY research measurement (read-only on all production data; one committed
script + committed JSON evidence + committed pytest positive-control fixture). This run does
NOT cast C2's formal M-SIG vote — the spec's own re-test precondition reads NOT MET (§2) and
the substrate is independently disqualified from confirmatory use (§6). The C3/#268 pattern
applies: the mechanical rule output is reported, labeled non-voting, and C2 stays OPEN.

**VERDICT, in full:**
1. **The spec's frozen coverage-delta precondition FAILS decisively**: measured panel-coverage
   improvement of the Starter-tier harvest over the free-tier `fundamentals_scan` baseline is
   **−0.02%** against the frozen **≥20%** bar. The r1 premise that the free-tier panel was
   "thin" is factually wrong for C2's three legs on this universe: the free-tier harvest
   (2026-06-25) already covers all 134 equity names at ~20 annual periods with zero nulls in
   every needed field and native `acceptedDate`. Per the frozen spec, a C2 confirmatory
   re-test is therefore NOT justified by the N3 upgrade — this precondition reading is itself
   the spec-governed result of this PR.
2. **The exploratory harness reading is a placebo-clean NULL**: mean real fwd_60d IC +0.0355
   is almost exactly explained by the shifted-label placebo +0.0360 → placebo-clean
   **−0.0005** (n=2,241 daily dates), 98.33% one-sided bounds ≈ [−0.055, +0.048] across seeds
   {42,43,44} → mechanical rule output **INCONCLUSIVE** (neither GO nor KILL), non-voting.
3. **Positive controls PASS** (S-REL R2): the identical harness detects a planted decaying
   effect at 2× the bar (GO on all seeds) and does not flag a permuted null — so this NULL
   reading is admissible as exploratory evidence, and the raw+0.035 → clean−0.0005 collapse
   is a measured property of the data, not of a broken harness.

## 1. What was measured (frozen estimand and rule, spec §1.2 + §2a, merged PR #243 r4)

Frozen thresholds, quoted verbatim from `doc/design/2026-07-02-m-sig-signal-stack-spec.md`
(frozen 2026-07-02, BEFORE this measurement; not altered here):

> **Estimand**: cross-sectional rank of a quality composite over {gross-profit/assets,
> total accruals, net share issuance}, quarterly-refreshed, `acceptedDate`-lagged.

> **Composite construction (frozen)**: `composite(i,t) = mean(zscore(GP/A(i,t)),
> −zscore(accruals(i,t)), −zscore(net_issuance(i,t)))` ... This is an EQUAL-WEIGHT
> composite, frozen — no PCA, no IC-weighted blend, no "whichever weighting wins" search.

> **"Beats the thin-panel NULL by a stated margin" (frozen)**: the `fundamentals_scan`
> measured NULL on the free-tier panel is the baseline to beat; re-test is justified ONLY if
> the FMP-full/N3 coverage report shows ≥20% panel-coverage improvement over that baseline
> ... The composite's OWN individual threshold, once re-tested, is the same ≥0.015
> placebo-clean bar as every other candidate (§0) — there is no separate, weaker bar for C2.

> **IC estimator & aggregation**: daily Spearman rank IC vs fwd_60d, block-bootstrap CI per
> the shared default (block=60, n≥600 decision dates, seeds {42,43,44})

> **Deterministic decision rule** (§0 + §2a): GO iff the block-bootstrap CI lower bound, at
> ... 98.33% one-sided [Bonferroni k=3, α = 0.05/3] ... exceeds the candidate's frozen
> individual threshold; KILL iff the same-level CI upper bound is below the threshold; else
> INCONCLUSIVE.

> **As-of lag**: 1 trading day after the fundamentals record's PIT-acceptance timestamp.
> [r4 admissible-mapping rule:] (1) `acceptedDate` ... (2) `filingDate` if present and
> `acceptedDate` is not. If NEITHER is present ... that observation is **INADMISSIBLE** —
> excluded ... not backfilled with any proxy [with the SEC EDGAR `available_date` join
> attempted before declaring inadmissibility].

> **Universe & missingness**: a name missing ANY of the three legs at date `t` is excluded
> from that date's cross-section entirely.

> **Earliest test**: 2026-Q4, strictly after the N3 coverage verdict.

Build-time choices the spec left to the build PR (exact field mapping) were frozen in
`doc/research/evidence/2026-07-03-c2/c2_frozen_addendum.json`, committed BEFORE any IC was
computed (the M8 three-commit pattern, `doc/research/2026-07-03-m8-cluster-wave1.md`):
GP/A = `grossProfitMargin × assetTurnover`; accruals = `(netProfitMargin −
operatingCashFlowSalesRatio) × assetTurnover` (Sloan accruals-to-assets); net issuance =
`financial_growth.weightedAverageSharesGrowth` (verified retroactively split-adjusted —
NVDA 10:1 / AAPL 4:1 / TSLA 3:1 show no seams; splits do not masquerade as issuance).
Pre-freeze inspection was outcome-free only (schemas, nulls, split seams, key alignment);
selection among candidate derivations was by availability/consistency, never IC.

## 2. The spec's own precondition: NOT MET (and the premise behind C2's re-test is refuted)

| Panel | mean all-3-leg coverage of the 134-name universe, 2017-07-01→2026-07-01 |
|---|---:|
| Starter `fmp_harvest_5y` (2026-07-03, 10y annual, 4 endpoints) | 0.93957 |
| Free-tier `fmp_harvest/*_291` (2026-06-25, ~20y annual, full statements) | 0.93973 |
| **Relative improvement** | **−0.02% (bar: ≥ +20%)** |

The free-tier baseline was never thin for C2's purposes: all 134 equities, ~20 annual
periods, zero nulls in grossProfit/totalAssets/netIncome/operatingCashFlow/shares, native
`acceptedDate` on every statement row. (What the free tier plan-locks is OTHER endpoint
families — the FMP-vendor facts memo; C2's three legs never needed them.) The Starter
harvest actually has LESS depth (10y vs 20y) and FEWER statement endpoints (no balance
sheet/cash flow files), forcing the ratio-based leg derivation frozen in the addendum.
Consequence, per the frozen spec: **the event that justifies C2's confirmatory re-test has
not occurred.** The remaining axis a paid tier could add — quarterly cadence — is
plan-locked on Starter too (harvest is annual-only), so the estimand's "quarterly-refreshed"
clause is also not achievable on this substrate.

## 3. Headline numbers (exploratory; gating configuration: fwd_60d, daily, block=60)

| Cut | n dates | mean real IC | mean placebo IC | mean placebo-clean IC | hit rate |
|---|---:|---:|---:|---:|---:|
| **Unconditional (the C2 gate cell)** | **2,241** | +0.0355 | +0.0360 | **−0.0005** | 0.510 |
| BULL_CALM (binding diagnostic cell) | 1,637 | +0.0308 | +0.0299 | +0.0009 | 0.489 |
| BULL_VOLATILE (thin) | 171 | +0.1072 | +0.0845 | +0.0227 | 0.591 |
| BEAR (thin) | 327 | +0.0234 | +0.0396 | −0.0162 | 0.566 |
| CHOPPY (thin) | 106 | +0.0292 | +0.0402 | −0.0110 | 0.547 |

Bootstrap (moving-block, block=60, n_boot=2000), one-sided 98.33% bounds on the clean mean:
seed 42 [−0.0553, +0.0475], seed 43 [−0.0519, +0.0442], seed 44 [−0.0512, +0.0429];
two-sided 95% ≈ [−0.047, +0.042]. LB < 0.015 and UB > 0.015 on every seed → mechanical rule
output **INCONCLUSIVE** (n=2,241 ≥ 600 floor met). Supporting fwd_20d: real +0.0257 /
placebo +0.0224 / clean +0.0032, 98.33% bounds [−0.033, +0.033] → same reading. Per-regime
fwd_20d disagrees with fwd_60d in the thin cells (BULL_VOLATILE +0.0227 @60 vs −0.0759 @20)
— noise-scale sign flips, reported per design rule 2, never gating.

Per-leg diagnostics (signed as in the composite): GP/A clean +0.0033 (real +0.0520),
−accruals clean −0.0006, −issuance clean −0.0005. Even the strongest leg is ~5× below the
0.015 bar once placebo-cleaned. Absolute-IC diagnostic (within-date shuffle placebo): real
+0.0330 vs shuffle floor +0.0016 — a naive absolute read would call this "significant
quality IC"; the shifted-label placebo shows it is persistent cross-sectional structure, not
decaying predictive signal (see PC-B). Rank-z composite sensitivity: clean +0.0022, same
reading. Turnover diagnostic: 21-day rank autocorrelation 0.981 (annual-refresh signal, as
expected; reported per spec, not gated).

Consistency with prior evidence: the free-tier `fundamentals_scan` quality lanes read NULL
(`doc/research/2026-06-28-renquant105-fundamentals-scan.md`, PR #204: ROE −0.040, gross
margin −0.024, low-accruals +0.015 at 252d, none significant) — that retrospective NULL was
the baseline to beat; this exploratory run, on the composite the spec actually froze, agrees
with it.

## 4. Positive controls (S-REL R2, PR #265) — the NULL is admissible

| Control | design | real IC | clean IC | rule output | expectation met |
|---|---|---:|---:|---|---|
| PC-A planted decaying effect | zscore(label)+κ·noise, κ=33.17 (≈2× bar) | +0.0302 | +0.0286 | **GO** (all seeds) | YES — harness detects |
| PC-B planted persistent tilt | z(full-sample mean excess return) | +0.1644 | −0.0083 | INCONCLUSIVE | YES — placebo nets out survivorship structure |
| PC-C permuted composite | within-date permutation | −0.0026 | −0.0004 | KILL (i.e. not GO) | YES — no false GO |

PC-A proves the full frozen path (composite→IC→shifted-label placebo→block bootstrap→rule)
returns GO when a genuinely horizon-decaying effect of decision scale is present. PC-B is
the design-property demonstration, stated honestly in both directions: on this
survivorship-backfilled panel a pure persistence/survivorship oracle scores real IC +0.164
and the placebo removes essentially all of it — which is exactly why the raw quality IC of
+0.035 cannot be read as alpha; and conversely, the harness is BY DESIGN insensitive to a
true quality premium that never decays within the horizon (a persistent-tilt claim cannot be
adjudicated on a survivorship panel at all — it needs PIT accrual or as-filed vintage data).
The committed pytest fixture (`tests/test_msig_c2_quality.py`, 7 tests) plants the same
effect classes at small scale and runs in CI.

## 5. PIT admissibility (binding r4 rule, executed fail-closed)

- 1,324 (symbol, period) observations → **1,263 admissible via `acceptedDate`** (95.4%);
  0 via `filingDate`; 0 needed the SEC EDGAR `available_date` join; **61 INADMISSIBLE**
  (fail-closed, never proxy-dated).
- The 61 fail-closed rows are exactly the S9 backfill trap caught at row level: FMP stamps
  `acceptedDate == period_end` (±hours) on rows where no genuine same-year acceptance event
  exists — pre-IPO fiscal years (AFRM, APP, RBLX, COIN, SOFI, SNOW, PLTR, CRWD, ZM, NET…)
  and foreign-issuer years (ASML 8, COHR 7, MRVL 5). Those statements were NOT public on
  their period-end date; using them would be lookahead. This is the same failure class that
  dropped `earnings_291.parquet` in S9 (`doc/research/2026-07-03-s9-track-a-conditional.md`,
  variable 4: no acceptedDate; backfilled announcement dates) — here it appears as forged
  same-day timestamps instead of missing ones, and the frozen anomaly guard
  (`acceptedDate ≤ period_end → INADMISSIBLE`) catches it.
- Acceptance-lag sanity (admissible rows): median 49 days after period end, p5 29, p95 60,
  min 18 — consistent with real 10-K acceptance physics (no zero-lag rows survive). 7 rows
  have lag > 120d: SMCI×3 (its genuinely delayed 2024–25 filings) + 4 fiscal-year-labeling
  fallback joins (ADI/CRM/GRMN/HD) whose availability lands LATE — conservative direction,
  no lookahead.
- Same-filing derivation assumption, stated: `ratios`/`financial_growth`/`key_metrics` carry
  no timestamps; their `acceptedDate` is joined from `income_statement` per (symbol, date)
  (1,317 exact) with a (symbol, fiscalYear) fallback (7 rows, ADI/MDT period-end labeling
  drift). Spot-checks on AAPL/NVDA/MDT/ADI/JPM: recomputing `grossProfitMargin` and
  `netProfitMargin` from the income statement reproduces the ratios file EXACTLY (max abs
  diff 0.0 on all five) — the derived files are computed from the same filing, so acceptance
  timing transfers. Full detail: `c2_pit_spotcheck.json`.

## 6. Evidence boundary (S-REL R3 literal block)

- **Window**: 2017-02-09 → 2026-01-08 (clean-IC series; the last clean date is bounded
  ~2·60 trading days before the 2026-07-02 calendar end); n = 2,241 daily decision dates.
- **n per regime cell**: BULL_CALM 1,637; BEAR 327; BULL_VOLATILE 171 (thin); CHOPPY 106
  (thin). Thin cells named; their per-horizon sign flips are noise-scale.
- **Resolved-outcome era**: fwd_60d/fwd_20d price-return excess vs SPY, split-adjusted, NOT
  dividend-adjusted; labels clipped ±0.5.
- **Cost-model status**: NOT covered — IC-level reading only; no turnover costs, no
  implementation shortfall (the signal's 0.98 rank-autocorr makes cost drag minimal but
  unmeasured here).
- **Substrate PIT/survivorship**: fundamentals are CURRENT-VINTAGE (restated values, no
  revision identity — the harvest manifest itself pins `research_descriptive_only` and bars
  confirmatory claims); universe = today's 134-name panel projected back (survivorship:
  backfilled current watchlist over-represents names that turned out high-quality-and-
  successful, biasing the RAW quality-return association upward; the shifted-label placebo
  nets the persistent part of that bias out — PC-B measures that removal at +0.164 → −0.008
  — but restatement bias on leg VALUES has no placebo and is uncorrected). Regime labels are
  today's production chain replayed backward (C3's contamination caveat inherited verbatim).
- **Cadence**: annual-only (quarterly plan-locked) — the signal refreshes ~once/year/name,
  so cross-sectional re-ranking between filings comes only from names' staggered fiscal
  calendars; the spec's "quarterly-refreshed" estimand is NOT what was measured.
- **Multiplicity**: M-SIG voting family {C2, C3, C4}, k=3, per-candidate one-sided
  α=0.05/3 (98.33% CI), frozen at spec time. Channels measured to date: C3 (2026-07-02,
  UNADJUDICATED per Codex r2 + S-REL V4 #268, OPEN), C2 (this run, second channel,
  exploratory non-voting). C4 not yet run (gated on S3). Within this run: fwd_20d and all
  sensitivities labeled non-gating; seeds are robustness, not extra looks; per-leg ICs are
  diagnostics, not candidate re-picks.
- **Not covered**: incremental value over the production alpha158 stack (an E35-style paired
  WF add-on test was NOT run — the spec's own named C2 harness is the direct rank-IC rule,
  which governs; the "does quality ADD to the model" question is a different, unasked
  question here); shorting-side monetization; any claim about as-filed (unrestated)
  fundamentals.

## 7. Deviations from the frozen spec (disclosed as deviations, spec unaltered)

1. **Timing**: run 2026-07-03 (Q3) vs frozen "Earliest test: 2026-Q4, strictly after the N3
   coverage verdict" — operator dispatch; the coverage verdict is produced inside this same
   PR (§2) rather than before it.
2. **Cadence**: annual-only substrate vs the frozen "quarterly-refreshed" estimand.
3. **Substrate**: S5/S8 pick-table/ledger (design rule 1) has no multi-year history — same
   stated deviation as C3; durable umbrella OHLCV + fixed 134-name universe used instead.
4. **Harness**: the measurement dispatch named an E35-style WF harness as an option; the
   spec's own C2 row names the direct daily-Spearman/block-bootstrap rule — the spec
   governs; the WF add-on is recorded as not-run (see §6 "Not covered").

All four were disclosed in the frozen addendum BEFORE measurement (commit order verifiable
in this PR's history).

## 8. G106 impact (V4 corrected composition, PR #268)

Under #268's reconciliation the G106 calculus is **≥2-of-4 candidates with C3 pending
(UNADJUDICATED), not 2-of-3**. This run does not change that composition: **C2 remains
OPEN/pending** — it is neither a GO (clean IC ≈ 0, nowhere near the bar), nor a KILL (CI
spans the bar), nor a formally-adjudicated MISS (precondition unmet + non-confirmatory
substrate mean the spec's confirmatory test was never run — exactly the C3 pattern). Per
spec §3, if no admissible substrate materializes by 2027-Q3, C2 resolves INCONCLUSIVE
(excluded from the denominator, not a stack KILL vote). The exploratory evidence here
lowers the realistic prior on C2 ever clearing +0.015 placebo-clean on this universe.

## 9. Reopening conditions (S-REL R4 — reopening = a NEW frozen prereg, never a rerun with tweaks)

C2's confirmatory test becomes possible iff one of:
- **(a) PIT accrual**: an as-received fundamentals snapshotter (the N2/N3 pattern) collects
  quarterly statements forward; a clean test needs ≥600 daily clean decision dates ≈ 2.4y of
  accrual — decide explicitly whether that fits the 2027-Q3 deadline before building.
- **(b) Purchased as-filed vintage data** (point-in-time fundamentals with revision
  identity) covering 2016→present for the production universe — this also unlocks the
  quarterly estimand as frozen.
- **(c) Operator-amended protocol** explicitly accepting the current-vintage substrate for
  C2 (the #268 option-(b) route) — in which case THIS run's numbers (clean −0.0005, CI
  [−0.055, +0.048]) stand and C2 would read INCONCLUSIVE under the frozen rule, still not GO.

Absent (a)/(b)/(c) by 2027-Q3: INCONCLUSIVE per spec §3. No coverage-delta re-run of the
free-tier-vs-Starter comparison can reopen C2 — that hypothesis is now measured and refuted.

## 10. Reproduce

```
/Users/renhao/git/github/RenQuant/.venv/bin/python \
    scripts/msig_c2_quality.py --out doc/research/evidence/2026-07-03-c2
/Users/renhao/git/github/RenQuant/.venv/bin/python -m pytest tests/test_msig_c2_quality.py -q
```

Evidence: `doc/research/evidence/2026-07-03-c2/{c2_frozen_addendum, c2_results,
c2_per_date_ic_fwd60, c2_coverage, c2_pit_spotcheck, c2_positive_control}.json` — manifests
carry input content SHA-256 (all 8 fundamentals parquets + harvest manifest + pinned config
+ GMM artifact + the exact aligned close/SPY panel), code git-sha + dirty flag, and an env
lock hash (S-REL hardened-evidence convention).

[VERIFIED — `scripts/msig_c2_quality.py` run end-to-end against the real read-only stores
(exit 0); every number above is read from the regenerated committed JSONs, not from memory;
`tests/test_msig_c2_quality.py` 7/7 passing under the umbrella venv; the frozen addendum
commit (d8608204) predates the harness commit and the evidence commit in this branch's
history, and the spec file itself is untouched by this PR.]
