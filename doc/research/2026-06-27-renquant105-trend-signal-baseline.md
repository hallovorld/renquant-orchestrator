# renquant105 trend-signal — DATA-QUALITY / PROVENANCE DIAGNOSTIC (verdict UNDETERMINED)

- **Date:** 2026-06-27 (run timestamp 2026-06-27 ~16:27 PDT)
- **Scope:** READ-ONLY diagnostic of whether the now-wired decision ledger can yet measure
  where renquant105 stands on its real goal — catch MORE (recall) and MORE-ACCURATE
  (precision) multi-period TREND signals — and whether a MODEL-vs-GATE bottleneck can be
  adjudicated. **It cannot, yet.** This document is therefore a data-quality / provenance
  diagnostic plus the design of the controlled experiments that WOULD answer the question. It
  is **not** a lever ranking and **not** a retraining recommendation.
- **Bottleneck verdict:** **`UNDETERMINED` — UNCONDITIONALLY.** The script has NO code path
  that flips the verdict or emits a model-vs-gate lever ranking. A faithful verdict requires a
  future STATEFUL production replay this script does not perform; sufficiency is necessary, not
  sufficient.
- **Reproduce:** `scripts/research_trend_signal_baseline.py --runs-db <ledger> --json`
  (add `--placebo-shuffles 200` for the on-cohort placebo). Every run emits the immutable
  input manifest below.

## Why the central conclusion is UNDETERMINED (the headline)

A prior draft of this study turned an explicitly insufficient sample into a "MODEL is the
~3.6× dominant bottleneck, retraining is the single highest-leverage move" claim. That claim
is **withdrawn.** The synthetic `(book_size, mu_floor)` killed-winner decomposition that
produced it is **scorer-mixed, k-dependent, non-causal, and NOT the deployed selection path**,
so **more dates do NOT repair that estimand.** The script therefore sets
`bottleneck_verdict = UNDETERMINED` **UNCONDITIONALLY** and `lever_ranking = null`
**always** — there is no `DETERMINED` branch and no `_lever_ranking()` builder. A "sufficient"
overlap-ratio may at most unlock IC *descriptives* (and an on-cohort placebo); it can NEVER
produce a model-vs-gate ranking. The report consumes that gate so prose cannot override it.

The faithful production cross-section is the **LIVE** ledger (`run_type='live'`). The
per-name decision ledger was only wired ~2026-05-04 (#133), and a 20-session (`fwd_20d`) label
needs 20 trading sessions to realize. As of 2026-06-27 that leaves **9 aged `fwd_20d` LIVE
dates** inside a single ~5-week window. With overlapping 20-session labels that is a
**≈ 0.45 overlap-ratio** — a conservative *descriptor*, NOT a power/N_eff figure (see
Finding 3) — roughly one independent observation, not nine. `fwd_60d` has **0** aged live
dates. The faithful model-vs-gate replay does not exist here regardless of date count.

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
| resolved_runs | 351 per-(date,run_type) run_ids (run_date ≤ as_of), max-row, **ties REJECTED** |
| ambiguous_dates_rejected | 241 dates dropped for tied max-row runs (deterministic) |
| runs_filtered_to_run_date_le_as_of | **true** — provenance/summary surfaces exclude later-dated runs |
| live_scorer_mix | None 448, **panel_ltr_xgboost 408**, QLearning 99, Manual 93, **hf_patchtst 85**, XGBoost 78, Classification 54 |

Run resolution is now **deterministic**: per `(date, run_type)` the max-candidate-row run is
kept and **tied dates are rejected** (recorded in `ambiguous_dates_rejected`), so no result
depends on row order. **AS-OF CORRECTNESS:** candidate runs (and therefore the resolved-run /
scorer-mix manifest surfaces) and the session calendar are filtered to `run_date ≤ as_of`, so
an as-of rerun never surfaces a later-dated run in provenance — independent of the horizon
aging that already filters the IC rows. CLI args, as-of, and the aged session calendar are all
in the manifest.

## Round-2 fixes (the airtightness blockers) and how each is addressed

The round-1 findings (1–8) were addressed in the previous revision; the round-2 review accepted
those and raised four remaining blockers + one correctness item. All five are accepted (no
defence) and addressed here.

**R2-1 — REMOVE the lever ranking ENTIRELY.** Done. The `live_ok`/sufficiency branch that flipped
the verdict to `DETERMINED` and called `_lever_ranking()` is **deleted**. `bottleneck_verdict`
is `UNDETERMINED` **unconditionally** and `lever_ranking` is **always `null`**; the
`_lever_ranking()` builder no longer exists. The synthetic `(book_size=8, mu_floor=.03)`
decomposition is scorer-mixed, k-dependent, non-causal, and not the deployed path — **more
dates do not repair the estimand.** Sufficiency is necessary, not sufficient. A faithful verdict
needs a future STATEFUL production replay (homogeneous artifact provenance + paired
counterfactuals + block-aware uncertainty) that this script does not do. A "sufficient"
overlap-ratio may at most unlock IC *descriptives* (`ic_descriptives_unlocked`), never a ranking.

**R2-2 — Placebo preserves time dependence.** The earlier within-date permutation destroyed
persistent ticker rank and cross-date dependence while the overlapping `fwd_20d` labels stay
correlated → the null was too narrow (the SIM ref even printed `p=0.0`). It is replaced by a
**dependence-preserving blockwise circular date-shift**: each date's WHOLE score cross-section
is kept intact (preserving within-date ticker ranks AND the score series' serial structure) and
re-paired to a DIFFERENT date's realized returns via a circular shift of the date axis by a
random non-zero lag. The p-value is the finite-MC estimator **`(exceedances+1)/(B+1)`** so it is
**never 0** (on-ledger LIVE `fwd_20d` now prints p≈0.33, not 0). The placebo runs **only on the
faithful homogeneous LIVE cohort** — it is explicitly NOT run on the unfaithful SIM cohort (which
also removes the >1-minute SIM-placebo runtime the reviewer flagged).

**R2-3 — overlap-ratio is a DESCRIPTOR, not power/N_eff.** `n_dates / horizon` (with a fixed
block count) ignores gaps, irregular coverage, autocorrelation beyond the horizon, scorer
composition and regime concentration, so it is renamed a **conservative overlap-ratio**
(`primary_overlap_ratio`, `--min-overlap-ratio`), never "power"/"N_eff", and it NEVER unlocks a
verdict. The real unblock — **which #201 must consume as the SAME criterion** — is, verbatim:
*a conservative overlap-ratio descriptor now; a pre-registered minimum-effect/power + an
empirical-dependence calc on a faithful homogeneous cohort as the real unblock (NO calendar
date).* This wording is emitted machine-readable as `overlap_ratio_unblock_note`.

**R2-4 — baselines implemented or removed; implemented distinguished from follow-ups.** The
random-recall baseline is now the **ANALYTIC `k/n`** expectation (no Monte-Carlo noise, no seed);
the **current-selected-book** baseline is implemented from the real persisted `selected` column
(on-ledger LIVE: `recall_selected_book ≈ 0.25` vs `recall_topk ≈ 0.285`); the market-sign
precision baseline stays. The **simple-momentum** claim is **removed from the implemented set**
(the ledger carries no trailing-price feature) and listed as a REQUIRED FOLLOW-UP. The report
emits `baselines_implemented` vs `baselines_followups_NOT_implemented` so the two are never
conflated.

**R2-5 (correctness) — as-of filter on runs + manifest.** `load()` now filters candidate runs
(and therefore the resolved-run / scorer-mix manifest surfaces) and the session calendar to
`run_date ≤ as_of`, so an as-of rerun never includes later-dated runs in provenance/summary —
independent of horizon aging. Manifest flag `runs_filtered_to_run_date_le_as_of = true`.

## Round-1 findings 1–8 (still addressed)

**1 — Insufficiency does not produce a ranking.** Reinforced by R2-1: the verdict is UNDETERMINED
unconditionally and `lever_ranking = null`. The descriptive numbers below are DIAGNOSTICS only.

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

**4 — Recall/precision baselines + no trend-event definition.** "Real trend" here is an
**ex-post top-decile positive `fwd_20d`** cross-section — a per-date drift label, **not** a
persistent trend EVENT with a start/end. Top-k recall is universe-size dependent and 75%
directional precision can reflect market drift. Per R2-4 the baselines are now **implemented
and stable**: the **analytic random-recall `k/n`** (no MC noise), the **current-selected-book**
recall, and the market-sign precision baseline. On the aged live subset model
`recall_topk ≈ 0.285` vs **analytic random ≈ 0.35** and **selected-book ≈ 0.25**, and top-k
precision ≈ 0.72 vs a **market-sign baseline ≈ 0.63** — i.e. the apparent skill is small once
baselined. REQUIRED FOLLOW-UPS (listed, not delivered; distinguished in the report):
simple-momentum (needs a trailing-price feature absent from the ledger), oracle-capacity,
regime/sector-neutral, lift / AUPRC / capacity-normalized recall, net-of-turnover/cost, and an
explicit event start/end + overlap definition.

**5 — `min_dates=30` invalid for overlapping 20-day outcomes.** Replaced. Sufficiency is now a
conservative **overlap-ratio** (`n_dates / horizon_n`; see R2-3), gated at `--min-overlap-ratio`
(default 6). 30 adjacent overlapping dates ≈ 1.5 → still insufficient. It is a DESCRIPTOR, not
power/N_eff, and it never unlocks a verdict; the pre-registered min-effect/power + empirical
dependence on a faithful cohort is the real unblock (R2-3).

**6 — Staleness 5-vs-6 split confounds age with regime/scorer/universe/overlap.** The causal
"freshness caused the decline" claim is **REMOVED**. The chronological IC split (older
+0.268 → recent +0.101) is emitted flagged `DESCRIPTIVE_ONLY_confounded` and is **not**
evidence of a freshness effect. The controlled experiment that would identify one is designed
below.

**7 — The 0.036 leakage floor is not portable.** It came from another experiment/horizon/purge
and is **no longer cited as a pass/fail bar** (kept only as a clearly-labelled foreign
reference). The script computes a **dependence-preserving on-cohort placebo** per horizon
(`--placebo-shuffles`), now via a **blockwise circular date-shift** (R2-2) that preserves both
cross-sectional and serial dependence, with a finite-MC `(exceedances+1)/(B+1)` p-value (never
0) run **only on the faithful LIVE cohort**. On today's ≈1-overlap-ratio cohort the placebo is
itself underpowered (LIVE `fwd_20d` p≈0.33) — which is exactly why the verdict is UNDETERMINED.

**8 — Immutable input manifest + labelled denominators.** Manifest above. Denominators are now
kept separate and labelled: the **all-live** gate stat and the **9-date aged subset** are
distinct windows and are no longer conflated — the prior prose mixed an all-live "5.5
admits/date" with an aged-subset figure (the aged-9 subset measures ≈ 7.9 admits/date). Each
number now carries its own window label.

## Descriptive diagnostics (UNDETERMINED — NO lever ranking is derivable from these)

LIVE, aged by trading sessions; **directional, ≈1-overlap-ratio cohort, not significance-tested.**

| horizon | aged dates (≈overlap-ratio) | mu rank-IC (IC_IR) | placebo p | note |
|---|---|---|---|---|
| fwd_5d  | 14 (≈2.8)  | +0.027 (0.14) | 0.79 | scorer-mixture; small |
| fwd_10d | 14 (≈1.4)  | +0.054 (0.36) | 0.57 | |
| fwd_20d | 9 (≈0.45)  | +0.175 (0.87) | 0.33 | ≈1 overlap-ratio — NOT validatable |
| fwd_60d | 0          | — | — | unrealized |

- Trend (fwd_20d, book=8): `recall_topk ≈ 0.285` vs **analytic random `k/n` ≈ 0.35** and
  **current-selected-book ≈ 0.25**; top-8 precision ≈ 0.72 (market-sign ≈ 0.63). Small/mixed
  edge over the implemented baselines on ≈1 overlap-ratio.
- Gate (one synthetic mu-demean threshold, aged-9 subset): ≈ 7.9 admits/date.
- Deployed selection (actual): ≈ 1.2 selected/date, 50% of dates zero; real blockers are the
  ordered `veto:* / kelly_zero / qp_* / quality_floor` stack, not the synthetic threshold.
- Killed split: k-dependent, ratio ≈ [0.91, 2.80], reverses at book=12/floor=0.06 — reported
  ONLY to expose k-dependence, NEVER turned into a model-vs-gate ranking.
- Placebo (dependence-preserving circular date-shift, LIVE only, p never 0): fwd_20d p≈0.33.
- Staleness (DESCRIPTIVE ONLY, confounded): older +0.268 → recent +0.101.

SIM (`run_type='sim'`) is **reference only, NOT validation-grade**: NULL `model_type`/
`active_scorer` on every row, `raw_score` to +200 (PatchTST is intrinsically negative
~−0.198), and far more distinct `mu` than tickers per date (conflicting run_ids). It is
excluded from any verdict.

## Controlled experiments REQUIRED before re-attempting a verdict

These replace the withdrawn "retrain now" recommendation. None can run until the data exists.
A "sufficient" overlap-ratio is necessary but **not** sufficient — only the faithful stateful
replay (item 2) may ever produce a model-vs-gate verdict; this script never will.

1. **Sufficiency criterion (the SAME one #201 must consume).** Verbatim: *a conservative
   overlap-ratio descriptor now; a pre-registered minimum-effect/power + an empirical-dependence
   calc on a faithful homogeneous cohort as the real unblock (NO calendar date).* Define the
   pre-registered min-effect/power and multiple-regime coverage with block-bootstrap CIs, and an
   empirical dependence estimator on a faithful cohort, BEFORE re-reading IC / recall /
   precision. The unblock follows that calc, never a raw-date or overlap-ratio count.
2. **Faithful STATEFUL path replay.** Require exact production run provenance and a homogeneous
   PatchTST-only cohort; replay the actual ordered gate stack + capacity using the persisted
   `selected`/`blocked_by`, and estimate paired counterfactual deltas (same scores gate-on/off;
   same gate vs oracle/ranking baseline) with block-aware CIs. Only this can produce a
   model-vs-gate split — the present script's synthetic decomposition cannot, at any date count.
3. **Dependence-preserving on-cohort placebo per horizon.** Already shipped here as the blockwise
   circular date-shift with `(exceedances+1)/(B+1)` on the LIVE cohort; at the verdict stage,
   run it on each homogeneous faithful cohort and multiplicity-correct across horizons. Stop
   citing 0.036.
4. **Controlled paired freshness experiment** (replaces the confounded staleness claim): same
   architecture / features / label / hyperparameters / evaluation folds, **old cutoff vs
   updated cutoff only**, with immutable data + artifact fingerprints. Test any **trend-label
   change SEPARATELY** — never bundle "fresh data" and "new trend label" into one retrain and
   attribute the delta to either.
5. **Baseline + event suite** (Finding 4 follow-ups): simple-momentum (needs a trailing-price
   feature), oracle-capacity; lift / AUPRC / capacity-normalized recall; regime/sector-neutral;
   net-of-cost; and an explicit trend-event start/end + overlap definition. (Analytic random
   `k/n`, current-selected-book, and market-sign are already implemented.)

## Honesty ledger

- Read-only: canonical `data/runs.alpaca.db` mtime unchanged (2026-06-26 14:07); analysis ran
  against a `/tmp` copy; no canonical path written; no git in the live tree; no order placed.
- Every live number rests on a ≈0.45-overlap-ratio scorer-mixture cohort → DIAGNOSTIC, not
  validated. Do not act on it. The script can NEVER emit a model-vs-gate lever ranking.
- UNBLOCK: let the live ledger reach the pre-registered min-effect/power (item 1) for `fwd_20d`,
  wire a faithful per-name PatchTST cohort with scorer provenance (#133 follow-through), run the
  placebo and the faithful stateful replay above, THEN — and only then — re-attempt a verdict.
