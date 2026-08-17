# G-I MoE step 2 — the cheap IC screen: FROZEN spec (before any scoring run)

STATUS: **frozen experiment spec (docs only — the run happens AFTER this merges).**
DATE: 2026-08-17. Implements design #984 §5 step 2 for the three step-1 emitters
(model#227: `high52w`, `lowbeta`, `quality_gp`). Frozen BEFORE any candidate score is
computed on the corpus (effective-sample-before-decision-rule; runner guards are prereg
content). Re-running the screen on this corpus after seeing results is FORBIDDEN.

## 1. Semantics — the screen KILLS, it never admits

A candidate that cannot show a placebo-clean IC **difference** on seven years of data
dies here, before any prereg cathedral. Passing means only "not obviously dead":
admission to the roster still requires the full §5 path (frozen prereg + episode-block
WF + the |ρ|<0.7 incremental-information gate under #984 §5b's Holm family). Because the
screen is kill-only and non-confirmatory, it uses NO multiplicity correction and a
deliberately lenient threshold; all confirmatory burden stays downstream.

## 2. Frozen corpus

- **Dates**: 2019-01-14 .. 2026-03-02 (the 125-fold WF window; 1,792 trading days
  `[VERIFIED — #984 §3 corpus]`), sampled **weekly** (every 5th trading day) → 358
  cross-sections.
- **Universe**: the current watchlist (the 145-name live universe) with per-date data
  availability; names lacking an emitter's min_obs on a date are absent that date
  (the emitters' own frozen floors apply, incl. NAMES_PER_DATE_FLOOR=50).
- **Survivorship caveat (stated, accepted)**: the current watchlist is
  survivorship-tilted for 2019-era cross-sections. This INFLATES measured ICs, which
  makes the screen EASIER to pass — so **kills remain valid** (dead even on an inflated
  corpus = safely dead) while **passes are non-confirmatory** (consistent with §1; the
  prereg stage owns point-in-time discipline).
- **Inputs**: existing OHLCV parquet + the upstream `gross_profitability` column,
  read-only. SPY from the same store. Zero new data.

## 3. Frozen estimand

Per candidate, per horizon h ∈ {20 (primary), 60 (secondary)} trading days:
- **Genuine series**: weekly cross-sectional Spearman IC of the RAW emitter score
  (as the artifact emits it — the serve-time z-scoring is monotone, Spearman-invariant)
  vs the h-day **forward excess return over SPY**.
- **Placebo series**: identical computation with scores LAGGED by 2h trading days
  (the house placebo convention: a stale copy of the same signal), same dates.
- **Decision quantity**: Δ = mean(genuine IC) − mean(placebo IC). Differences, never
  absolute levels (embargo-leakage floor ~+0.04 makes absolute IC untrustworthy).
- The screen is deliberately **regime-blind**: no per-regime cells here — the label
  plane is under consolidation (#985); regime conditioning enters at the #984 §5b
  Stage-A batch on the re-derived plane, not before.

## 4. Effective sample — counted BEFORE the rule `[DERIVED, frozen]`

Weekly obs n=358, but h-day labels overlap across weekly samples
(ρ_overlap ≈ (h−5)/h): **n_eff ≈ 51 at h=20; ≈ 16 at h=60.** Non-overlapping blocks in
the window: **89 (h=20) / 29 (h=60)**. Inference is therefore **block-t over
non-overlapping h-blocks** (block mean differences; df = blocks−1), never a 1.96 normal
critical value on the raw weekly series. h=60's n_eff≈16 is annotation-grade —
which is why h=20 is primary and h=60 is reported but never decisive.

## 5. Frozen kill rule (one shot per corpus)

A candidate **SURVIVES** iff, at h=20 on the frozen corpus:
1. Δ > 0, AND
2. block-t(Δ over the 89 non-overlapping 20d blocks) ≥ **1.0**, AND
3. the per-block Δ is positive in > **50%** of blocks with data.
Anything else = **KILLED** (recorded verdict; no re-run, no parameter search, no
alternative horizon rescue — h=60 is informational only). The lenient t≥1.0 is the
kill-only asymmetry: the screen must not manufacture admits, and a true-but-weak
candidate that dies here could only have been rescued by exactly the data-mining this
program forbids.

## 6. Measured alongside (informational at this stage)

Pairwise Spearman ρ of each candidate's scores vs `multifactor_core`, `mom_slow_12m`,
`mom_fast` on common dates — early visibility for the |ρ|<0.7 roster gate, which is
APPLIED at prereg admission, not here.

## 7. Execution contract

A committed, deterministic derivation script (read-only inputs; outputs to
doc/research/data/) runs ONCE after this spec merges, in an isolated worktree — never
against a live tree. Results PR carries: per-candidate genuine/placebo series, block
table, verdicts, and the ρ matrix; every number provenance-tagged. Kill verdicts are
final for this corpus; survivors proceed to the #984 §5b manifest freeze.
