# G-D shadow-fleet information census: 13 recorded lane-identities reduce to ~3 independent rankings, none outcome-measurable

STATUS: census of EXISTING records only (operator directive: records + backtest,
no future accrual, no new runs). All DB access read-only (`mode=ro`). This is a
census, not a gate: day counts are reported everywhere and no significance is
claimed on single-digit n.

Derivation: `scripts/g_d_shadow_information_census.py` (CLI paths, re-runnable).
Evidence CSVs: `doc/research/data/2026-08-10-shadow-census_*.csv` — the verbatim
outputs of the committed script run 2026-08-10.

## 1. Bottom line

The task's claim — "the shadow fleet carries less information than it appears
to" — is [VERIFIED] on every axis measurable from existing records:

1. **Surface vs substance.** 9 shadow strategy configs + 6 shadow DB sinks + 3
   file surfaces present as a fleet; the records contain 13 lane-identities with
   any measurable daily panel. **7 of 13 are >0.95-redundant** with the primary
   or with another lane under the task's frozen rule
   [VERIFIED: `_redundancy.csv`].
2. **Two lanes are literal duplicates.**
   - `blend_mom` (S1) IS the served primary since the 08-04 promotion: median
     daily Spearman vs the primary canonical panel **0.99976** (n=4 days);
     max per-ticker |Δrank_score| 0.007-0.20 on 08-05..07
     [VERIFIED: `_pairwise_spearman.csv`, `_bit_identity.csv`].
   - `blend_rb_fast` (F3) emitted rank_scores **bit-identical** to
     `blend_mom_fast` (F2) — max|Δ| = 0.0 across 114-120 names — on time-adjacent
     runs on ALL 4 of its recorded days, while its run bundle and pinned config
     declare a third component (panel-clf, sha256:1e644354…) that the sibling
     slow lane (F1 vs S1) visibly applies (85-87 of ~120 names moved, time-adjacent
     runs). A declared component contributed exactly zero, silently
     [VERIFIED: `_bit_identity.csv`; bundle/config quotes in §5].
3. **Zero realized-outcome evidence exists.** The frozen corpus ends
   2026-05-07; the first shadow-sink record is 2026-05-19, and even the primary
   DB's first broad scored panel is 2026-05-08 — one day late. **Every lane has
   exactly 0 corpus-overlapping panel days** [VERIFIED: `_corpus_outcome_census.csv`].
   The auxiliary recorded-forward-return census (§6, NOT the frozen corpus)
   gives the 08-04 four-lane fleet **0 accrued outcome days** and gives the only
   long-lived independent lane (`shared:hf_patchtst`, ρ = −0.09 vs primary) 20
   days at mean daily top-5 z +0.31 / median −0.11 / 45% positive — noise-level
   at this n, and that lane was retired 08-03.
4. **Net.** After removing duplicates, the currently-recording fleet carries at
   most **3 independent rankings** beyond the primary — clf-blend (ρ≈0.41 vs
   primary, 9 days), F1 (ρ≈0.92, 4 days), F2≡F3 counted once (ρ≈0.37, 4 days)
   — and none of them has any realized-outcome record usable under the
   existing-data directive.

## 2. Method (frozen before reading results)

- **Sinks read** (all `file:…?mode=ro`): `runs.alpaca_shadow.db` (the shared
  sink; lanes split by the `active_scorer` identity stamp, NULL →
  `unattributed`), the five dedicated `runs.alpaca_shadow_blend*.db` sinks, the
  primary `runs.alpaca.db` (ONE lane: the served scorer of the day), the
  `qp-live-shadow.jsonl` allocator ledger, `shadow_predictions.json`,
  `shadow_analyst/` artifacts, and `challenger_decisions` in every DB.
- **Canonical run per (lane, date):** the run with the most non-null
  `rank_score` rows (ties: latest `pipeline_runs.created_at`, then run_id).
  Monitor-loop runs score only holdings (~6-7 rows) and are thereby excluded;
  panels < 20 scored names never enter measurement.
- **Correlation:** per-day Spearman over common scored tickers (floor 20),
  median across days; redundancy rule fixed by the task: median |ρ| > 0.95 vs
  the primary or vs another lane.
- **Outcome labels:** per-day cross-sectional z of `fwd_5d_excess` from the
  frozen corpus (`alpha158_291_fundamental_dataset.parquet`, labels end
  2026-05-07); lane statistic = daily top-5 mean label-z. Auxiliary only (§6):
  the same statistic on the per-day cross-sectional z of the RECORDED `fwd_5d`
  in the primary DB's `ticker_forward_returns` sink (a per-day z of raw fwd_5d
  equals the z of same-day benchmark excess; universe = the ~78-95 names the
  primary recorded that day, so it is selection-biased toward the primary's
  tracked set — stated, not corrected).

## 3. Lane inventory ([VERIFIED: `_inventory.csv`])

| lane | sink | first → last | rows | days | med tickers/day | panel days (≥20 scored) |
|---|---|---|---|---|---|---|
| shared:unattributed | runs.alpaca_shadow.db | 05-19 → 07-28 | 9,242 | 20 | 142 | 19 |
| shared:panel_ltr_xgboost | runs.alpaca_shadow.db | 06-11 → 07-15 | 2,580 | 11 | 142 | 10 |
| shared:hf_patchtst | runs.alpaca_shadow.db | 06-22 → 08-03 | 8,987 | 28 | 145 | 25 |
| shared:xgb | runs.alpaca_shadow.db | 06-22 (1 day) | 145 | 1 | 145 | 1 |
| shared:momentum_residual | runs.alpaca_shadow.db | 08-03 (1 day) | 145 | 1 | 145 | 1 |
| shared:momentum_residual_v0 | runs.alpaca_shadow.db | 08-03 (1 day) | 435 | 1 | 145 | 1 |
| shared:blend | runs.alpaca_shadow.db | 08-04 (1 day) | 145 | 1 | 145 | 1 |
| blend:blend (clf blend) | runs.alpaca_shadow_blend.db | 07-28 → 08-07 | 2,755 | 9 | 145 | 9 |
| blend:unattributed | runs.alpaca_shadow_blend.db | 07-28 (1 day) | 290 | 1 | 145 | 1 |
| blend_mom:blend (S1) | runs.alpaca_shadow_blend_mom.db | 08-04 → 08-07 | 1,595 | 4 | 145 | 4 |
| blend_mom_fast:blend (F2) | runs.alpaca_shadow_blend_mom_fast.db | 08-04 → 08-07 | 1,015 | 4 | 145 | 4 |
| blend_rb_fast:blend (F3) | runs.alpaca_shadow_blend_rb_fast.db | 08-04 → 08-07 | 1,015 | 4 | 145 | 4 |
| blend_rb_mom:blend (F1) | runs.alpaca_shadow_blend_rb_mom.db | 08-04 → 08-07 | 1,305 | 4 | 145 | 4 |
| primary:served (reference) | runs.alpaca.db | 04-27 → 08-07 | 260,776 | 75 | 142 | 48 |
| file:qp_live_shadow | qp-live-shadow.jsonl | 07-06 → 07-21 | 35 | 10 | ~11 held names | 0 (not rank-comparable) |
| file:shadow_predictions_snapshot | shadow_predictions.json | 05-05 (1 day) | 30 | 1 | 30 | 0 (one-shot top-30) |
| file:shadow_analyst_artifacts | shadow_analyst/ | — | 3 json | 0 | — | 0 (model artifacts, no records) |
| db:challenger_decisions | all runs.*.db | — | **0** | 0 | — | 0 (designed sink, never wrote) |

Census observations on the inventory itself:

- **43% of the shared sink is unattributed.** 9,242 of 21,679 rows carry a NULL
  `active_scorer` (the stamp landed mid-life, pipeline#257/s104#79 era), and
  the NULL span (05-19 → 07-28) OVERLAPS the stamped spans — identity for those
  20 days is recoverable only by config archaeology, not from the record.
- **Config-to-sink fan-in:** `shadow.json`, `shadow_a.json`, `shadow_b.json`
  all feed the ONE shared sink; `shadow_momentum.json` has NO dedicated sink —
  the momentum lane's total recorded life is ONE day (08-03: `momentum_residual`
  + 3 runs of `momentum_residual_v0`) before the 08-04 fleet swap (#908 era).
- Four lane-identities (`shared:xgb`, both momentum stamps, `shared:blend`)
  have exactly one recorded day each.
- The allocator shadow (`qp_live_shadow`) stopped recording 07-21; the
  challenger sink has never written a row.

## 4. Cross-lane correlation and redundancy ([VERIFIED: `_pairwise_spearman.csv`, `_median_spearman_matrix.csv`, `_redundancy.csv`])

Median daily Spearman vs the primary served panel (day counts in parens):

| lane | ρ vs primary | closest other lane | max ρ other | flagged >0.95 |
|---|---|---|---|---|
| blend_mom (S1) | **0.9998** (4) | shared:blend 0.997 (1) | 0.997 | YES — duplicates the promoted primary |
| shared:panel_ltr_xgboost | **0.986** (5) | hf_patchtst 0.650 (3) | 0.650 | YES — the prior XGB primary re-run as shadow |
| blend_rb_fast (F3) | 0.365 (4) | **blend_mom_fast 1.0000 (4)** | 1.0000 | YES — bit-identical twin (§5) |
| blend_mom_fast (F2) | 0.365 (4) | **blend_rb_fast 1.0000 (4)** | 1.0000 | YES — same pair |
| shared:blend | 0.310 (1) | blend_mom 0.997 (1) | 0.997 | YES — transition-day double-write of S1 |
| blend:blend (clf blend) | 0.409 (9) | blend:unattributed 0.986 (1) | 0.986 | YES — but the partner is its OWN sink's pre-stamp day-one; genuine profile is ρ≈0.41 |
| blend:unattributed | 0.351 (1) | blend:blend 0.986 (1) | 0.986 | YES — same-lane twin as above |
| blend_rb_mom (F1) | 0.924 (4) | blend_mom 0.922 (4) | 0.922 | no (but 0.92 is marginal) |
| shared:hf_patchtst | **−0.095** (23) | momentum_residual 0.942 (1) | 0.942 | no — the only long-lived independent ranking |
| shared:unattributed | 0.441 (11) | blend:unattributed 0.296 (1) | 0.296 | no (identity unknown) |
| shared:momentum_residual | −0.080 (1) | hf_patchtst 0.942 (1) | 0.942 | no (n=1) |
| shared:momentum_residual_v0 | 0.029 (1) | blend:blend 0.124 (1) | 0.124 | no (n=1) |
| shared:xgb | −0.183 (1) | hf_patchtst −0.237 (1) | 0.237 | no (n=1) |

**Redundancy count: 7 of 13** measurable lane-identities flagged by the frozen
>0.95 rule. Of the 6 unflagged, three have exactly one recorded day and one is
the unattributed era. The currently-recording fleet (post-08-04: clf-blend, S1,
F2, F3, F1) collapses to **three** distinct rankings — clf-blend (0.41 vs
primary), F2≡F3 (0.37), F1 (0.92) — plus S1, which is the primary.

## 5. The F3/F2 bit-identity (defect-shaped observation, records only)

- F3 (`blend_rb_fast`) run bundles declare THREE components with hashes:
  prod panel-ltr (sha256:6461b827…), panel-clf top-decile (sha256:1e644354…),
  fast momentum ledger. F2 (`blend_mom_fast`) declares TWO (no clf).
  [VERIFIED: `pipeline_runs.run_bundle_json`, runs 2026-08-05-live-7c88501a /
  2026-08-05-live-c5d2ef40.]
- On ALL 4 recorded days, every time-adjacent F3/F2 run pair emitted
  **bit-identical** rank_scores (max|Δ| = 0.0 over 114-120 common names; on
  08-06 all four run pairs checked, cross-time pairs differ by ≤0.263 in BOTH
  lanes identically — shared intraday input drift, not a component).
  [VERIFIED: `_bit_identity.csv` + §7 reproduction commands.]
- Control: F1 (`blend_rb_mom`) declares the SAME clf artifact and its
  time-adjacent runs differ from S1 on 85-87 of ~120 names (max|Δ| 2.65-3.45)
  — the clf component demonstrably moves scores in the slow pair.
- Records alone cannot attribute the mechanism (clf leg silently inert in F3's
  process vs F2 mislabeled); either way ONE of the two "fast" lanes is not what
  its manifest declares, and nothing in the sink flags it. Follow-up belongs to
  the pipeline/strategy-104 owners (see NEXT in the progress doc). This is the
  strongest single quantification of the task's claim: a lane that looks like a
  third model family contributed literally zero new information on every day of
  its life.

## 6. Realized-outcome census

**Frozen corpus (the preregistered label source): zero measurable lane-days.**
Corpus labels end 2026-05-07. First shadow record: 2026-05-19. First broad
primary panel: 2026-05-08. Every DB lane: `lane_days_in_corpus_window = 0`
[VERIFIED: `_corpus_outcome_census.csv`]. The ONLY shadow-surface record
predating the corpus end is the one-shot `shadow_predictions.json` snapshot
(2026-05-05, top-30 of the PROD panel-ltr artifact): top-5 mean label-z
**−0.079**, top-30 **+0.121**, n = 1 day — reported for completeness, carries
no inference.

**Auxiliary census (recorded `ticker_forward_returns` in the primary DB — NOT
the frozen corpus; selection-biased universe, stated in §2):**

| lane | days | mean daily top-5 z | median | % days > 0 | top-5 coverage /5 |
|---|---|---|---|---|---|
| primary:served (baseline) | 43 | +0.211 | +0.215 | 56% | 4.7 |
| shared:hf_patchtst | 20 | +0.309 | −0.110 | 45% | 3.1 |
| shared:unattributed | 11 | −0.286 | −0.507 | 36% | 3.6 |
| shared:panel_ltr_xgboost | 5 | +0.163 | +0.150 | 80% | 4.4 |
| blend:blend (clf blend) | 4 | +0.808 | +1.039 | 75% | **1.75** |
| blend_mom / F1 / F2 / F3 | **0** | — | — | — | — |
| single-day lanes | ≤1 | — | — | — | ≤2 |

Honest reading: no lane clears noise. hf_patchtst's mean is dragged positive by
tails while its median day is negative on 20 days. The clf blend's +0.81 rests
on 4 days at 1.75-of-5 coverage — its top picks are mostly OUTSIDE the recorded
universe, so this is not evidence of signal. The entire 08-04 fleet has zero
accrued outcome days within existing records.

## 7. What is NOT measurable from existing records, and why

1. **Any lane vs the frozen corpus** — zero date overlap (corpus ends 05-07;
   shadow recording started 05-19). The fleet's entire life post-dates the
   frozen labels; under the no-future-accrual directive there is NO
   preregistered-label outcome evidence for any shadow lane, full stop.
2. **The 08-04 fleet's realized outcomes** — no accrued fwd_5d in the recorded
   sink for any of its 4 trading days at run time.
3. **Identity of 43% of the shared sink** (9,242 unattributed rows / 20 days)
   — the stamp post-dates the records; recoverable only by archaeology.
4. **clf-blend outcome quality even in the auxiliary census** — the recorded
   forward-return universe covers 1.75 of its top-5 per day (the sink tracks
   the primary's names, not shadow picks).
5. **The allocator shadow's information** — `qp_live_shadow` records weights on
   ~6 held names, no cross-section; and it stopped 07-21.
6. **Anything from `challenger_decisions`** — the sink exists in every DB and
   has never recorded a row.
7. **F3's clf mechanism** — records prove the component contributed zero;
   attributing WHERE it died requires pipeline internals (out of this repo's
   boundary).

## 8. Reproduction

```bash
python3 scripts/g_d_shadow_information_census.py \
  --data-dir /Users/renhao/git/github/RenQuant/data \
  --qp-ledger /Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/live-shadow/qp-live-shadow.jsonl \
  --out-dir doc/research/data --out-prefix 2026-08-10-shadow-census
```

Read-only over production DBs (`mode=ro` URIs); writes only the CSVs. Paths are
CLI-overridable; defaults match this machine's live tree (stated, not hidden).
