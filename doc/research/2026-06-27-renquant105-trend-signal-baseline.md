# renquant105 trend-signal — DATA-QUALITY / PROVENANCE DIAGNOSTIC (verdict UNDETERMINED)

- **Date:** 2026-06-27 (run timestamp 2026-06-27 ~16:27 PDT)
- **Scope:** READ-ONLY diagnostic of whether the now-wired decision ledger can yet measure
  where renquant105 stands on its real goal — catch MORE (recall) and MORE-ACCURATE
  (precision) multi-period TREND signals — and whether a MODEL-vs-GATE bottleneck can be
  adjudicated. **It cannot, yet.** This document is therefore a data-quality / provenance
  diagnostic plus the design of the controlled experiments that WOULD answer the question. It
  is **not** a lever ranking and **not** a retraining recommendation.
- **Bottleneck verdict:** **`UNDETERMINED`** (the script emits this whenever the live primary
  horizon is below the pre-registered effective-block bar; it is today).
- **Reproduce:** `scripts/research_trend_signal_baseline.py --runs-db <ledger> --json`
  (add `--placebo-shuffles 200` for the on-cohort placebo). Every run emits the immutable
  input manifest below.

## Why the central conclusion is UNDETERMINED (the headline)

A prior draft of this study turned an explicitly insufficient sample into a "MODEL is the
~3.6× dominant bottleneck, retraining is the single highest-leverage move" claim. That claim
is **withdrawn.** The estimator cannot support it, for the reasons below, and the script now
**gates the conclusion**: under insufficiency it sets `bottleneck_verdict = UNDETERMINED`,
computes **no lever ranking** (`lever_ranking = null`), and the report consumes that gate so
prose cannot override it.

The faithful production cross-section is the **LIVE** ledger (`run_type='live'`). The
per-name decision ledger was only wired ~2026-05-04 (#133), and a 20-session (`fwd_20d`) label
needs 20 trading sessions to realize. As of 2026-06-27 that leaves **9 aged `fwd_20d` LIVE
dates** inside a single ~5-week window. With overlapping 20-session labels that is
**≈ 0.45 effective non-overlapping blocks** — roughly one independent observation, not nine.
`fwd_60d` has **0** aged live dates. No model-vs-gate ranking, IC significance claim, or
retraining prioritization is admissible on ≈1 effective observation.

## Reproducibility — immutable input manifest

Emitted machine-readable under `manifest` in `--json`. As measured 2026-06-27 against a `/tmp`
copy of the canonical ledger (canonical opened `mode=ro`, mtime unchanged):

| field | value (this run) |
|---|---|
| db_path | `data/runs.alpaca.db` (copied to `/tmp` for the read) |
| db_sha256 | `731d566f2d696c37…` (full 64-hex in JSON) |
| db_size_bytes / mtime | 90.6 MB / 2026-06-26 14:07 |
| sqlite schema_version | 138 |
| code_commit | (git HEAD of this branch, in JSON) |
| session_calendar | 2024-01-02 … 2026-06-26 (605 sessions) |
| resolved_runs | 351 per-(date,run_type) run_ids, max-row, **ties REJECTED** |
| ambiguous_dates_rejected | 235 dates dropped for tied max-row runs (deterministic) |
| live_scorer_mix | None 448, **panel_ltr_xgboost 408**, QLearning 99, Manual 93, **hf_patchtst 85**, XGBoost 78, Classification 54 |

Run resolution is now **deterministic**: per `(date, run_type)` the max-candidate-row run is
kept and **tied dates are rejected** (recorded in `ambiguous_dates_rejected`), so no result
depends on row order. CLI args, as-of, and the aged session calendar are all in the manifest.

## Findings 1–8 (review) and how this diagnostic addresses each

**1 — Insufficiency gates the conclusion.** Done. `bottleneck_verdict = UNDETERMINED`,
`lever_ranking = null`. The descriptive numbers below are explicitly DIAGNOSTICS only.

**2 — This is NOT the production model-vs-gate path.** The live `mu` cohort is a **SCORER
MIXTURE** (panel_ltr_xgboost-dominant; only **85** `hf_patchtst` rows ledger-wide), not a
PatchTST-primary cross-section. The de-meaned `(mu − mean) ≥ mu_floor` rule is **one
synthetic threshold**, not the deployed ordered gate stack + capacity. The diagnostic now
(a) **labels** the output "scorer-mixture ranking vs one synthetic threshold", and (b)
summarizes the **actual deployed selection** from the persisted `selected`/`blocked_by`
columns. On the aged live subset the real path **selected ~1.2 names/date, 50% of dates
selected zero**, and the dominant real blockers are `veto:rank_score_below_floor` (145),
`kelly_zero:mu_le_min_edge` (52), `qp_delta_below_min_dw` (51), `qp_no_trade_band`,
`quality_floor:gate_b` — i.e. an ordered stack the synthetic single threshold does not
represent. A faithful adjudication requires replaying that stack (or a homogeneous
PatchTST-only cohort), which today's data does not permit.

**3 — Killed-winner split is k-dependent and non-causal.** Reported across a sensitivity grid
of (book_size ∈ {5,8,12}, mu_floor ∈ {0,0.03,0.06}). The `missed_by_model / killed_by_gate`
ratio **spans ≈ [0.91, 2.80]** on this cohort and **reverses**: at book=12, mu_floor=0.06 the
gate (`killed_by_gate ≈ 0.49`) exceeds the model (`missed_by_model ≈ 0.45`). The earlier
"3.6×" was a single arbitrary operating point. The split is therefore reported with its
sensitivity surface and is **never** labelled a "bottleneck"; a causal answer needs the
replayed path, paired counterfactual deltas (same scores gate-on/off; same gate vs
oracle/ranking baseline), and a block CI — none yet computable.

**4 — Recall/precision lack baselines + no trend-event definition.** "Real trend" here is an
**ex-post top-decile positive `fwd_20d`** cross-section — a per-date drift label, **not** a
persistent trend EVENT with a start/end. Top-k recall is universe-size dependent and 75%
directional precision can reflect market drift. The diagnostic now reports **naive baselines**
inline (random-ranking recall, market-sign precision); on the aged live subset model
`recall_topk ≈ 0.285` barely exceeds **random ≈ 0.272**, and top-k precision ≈ 0.72 vs a
**market-sign baseline ≈ 0.63** — i.e. the apparent skill is small once baselined. Still
REQUIRED before any verdict (listed, not delivered): oracle-capacity, simple-momentum,
current-selected-book, regime/sector-neutral variants, lift / AUPRC / capacity-normalized
recall, net-of-turnover/cost, and an explicit event start/end + overlap definition.

**5 — `min_dates=30` invalid for overlapping 20-day outcomes.** Replaced. Sufficiency is now
pre-registered in **effective non-overlapping blocks** (`n_dates / horizon_n`), gated at
`--min-eff-blocks` (default 6). 30 adjacent overlapping dates ≈ 1.5 blocks → still
insufficient. The unblock target is stated in N_eff, not raw dates, and requires multiple
regimes; block-bootstrap CIs are the reporting standard once N_eff is met.

**6 — Staleness 5-vs-6 split confounds age with regime/scorer/universe/overlap.** The causal
"freshness caused the decline" claim is **REMOVED**. The chronological IC split (older
+0.268 → recent +0.101) is emitted flagged `DESCRIPTIVE_ONLY_confounded` and is **not**
evidence of a freshness effect. The controlled experiment that would identify one is designed
below.

**7 — The 0.036 leakage floor is not portable.** It came from another experiment/horizon/purge
and is **no longer cited as a pass/fail bar** (kept only as a clearly-labelled foreign
reference). The script now computes an **on-cohort shuffled-label placebo** per horizon
(`--placebo-shuffles`), shuffling the score WITHIN each date to preserve cross-sectional/time
dependence, and reports a p-value of observed IC vs the placebo distribution. (On today's ≈1
effective block the placebo is itself underpowered — which is exactly why the verdict is
UNDETERMINED rather than "IC beats floor".)

**8 — Immutable input manifest + labelled denominators.** Manifest above. Denominators are now
kept separate and labelled: the **all-live** gate stat and the **9-date aged subset** are
distinct windows and are no longer conflated — the prior prose mixed an all-live "5.5
admits/date" with an aged-subset figure (the aged-9 subset measures ≈ 7.9 admits/date). Each
number now carries its own window label.

## Descriptive diagnostics (UNDETERMINED — do NOT rank levers off these)

LIVE, aged by trading sessions; **directional, ≈1 effective block, not significance-tested.**

| horizon | aged dates (≈eff blocks) | mu rank-IC (IC_IR) | note |
|---|---|---|---|
| fwd_5d  | 14 (≈2.8) | +0.027 (0.14) | scorer-mixture; small |
| fwd_10d | 14 (≈1.4) | +0.054 (0.36) | |
| fwd_20d | 9 (≈0.45) | +0.175 (0.87) | ≈1 effective block — NOT validatable |
| fwd_60d | 0 | — | unrealized |

- Trend (fwd_20d, book=8): `recall_topk ≈ 0.285` (random ≈ 0.272); top-8 precision ≈ 0.72
  (market-sign ≈ 0.63). Small edge over naive baselines on ≈1 block.
- Gate (one synthetic mu-demean threshold, aged-9 subset): ≈ 7.9 admits/date.
- Deployed selection (actual): ≈ 1.2 selected/date, 50% of dates zero; real blockers are the
  ordered `veto:* / kelly_zero / qp_* / quality_floor` stack, not the synthetic threshold.
- Killed split: k-dependent, ratio ≈ [0.91, 2.80], reverses at book=12/floor=0.06.
- Staleness (DESCRIPTIVE ONLY, confounded): older +0.268 → recent +0.101.

SIM (`run_type='sim'`) is **reference only, NOT validation-grade**: NULL `model_type`/
`active_scorer` on every row, `raw_score` to +200 (PatchTST is intrinsically negative
~−0.198), and far more distinct `mu` than tickers per date (conflicting run_ids). It is
excluded from any verdict.

## Controlled experiments REQUIRED before re-attempting a verdict

These replace the withdrawn "retrain now" recommendation. None can run until the data exists.

1. **N_eff power pre-registration.** Define the required effective non-overlapping blocks per
   horizon and the multiple-regime coverage, with block-bootstrap CIs, BEFORE re-reading IC /
   recall / precision. The unblock date follows N_eff, not a raw-date count.
2. **Faithful path replay.** Require exact production run provenance and a homogeneous
   PatchTST-only cohort; replay the actual ordered gate stack + capacity using the persisted
   `selected`/`blocked_by`, and estimate paired counterfactual deltas (same scores gate-on/off;
   same gate vs oracle/ranking baseline) with block CIs. Only then is a model-vs-gate split
   admissible.
3. **On-cohort placebo per horizon.** Recompute shuffled-label / time-shift placebos on THIS
   exact cohort and each horizon, preserving cross-sectional/time dependence; compare observed
   IC to the placebo distribution; multiplicity-correct across horizons. Stop citing 0.036.
4. **Controlled paired freshness experiment** (replaces the confounded staleness claim): same
   architecture / features / label / hyperparameters / evaluation folds, **old cutoff vs
   updated cutoff only**, with immutable data + artifact fingerprints. Test any **trend-label
   change SEPARATELY** — never bundle "fresh data" and "new trend label" into one retrain and
   attribute the delta to either.
5. **Baseline + event suite** (Finding 4): random, SPY/market-sign, simple-momentum,
   current-selected-book, oracle-capacity; lift / AUPRC / capacity-normalized recall;
   regime/sector-neutral; net-of-cost; and an explicit trend-event start/end + overlap
   definition.

## Honesty ledger

- Read-only: canonical `data/runs.alpaca.db` mtime unchanged (2026-06-26 14:07); analysis ran
  against a `/tmp` copy; no canonical path written; no git in the live tree; no order placed.
- Every live number rests on ≈1 effective block of a scorer-mixture cohort → DIAGNOSTIC, not
  validated. Do not act on it.
- UNBLOCK: let the live ledger reach ≥ the pre-registered N_eff for `fwd_20d`, wire a faithful
  per-name PatchTST cohort with scorer provenance (#133 follow-through), run the placebo and
  the controlled paired experiments above, THEN — and only then — re-attempt a verdict.
