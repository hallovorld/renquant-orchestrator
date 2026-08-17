# G-I MoE step 2 — the cheap IC screen: EXPLORATORY triage spec (before any scoring run)

STATUS: **exploratory triage spec (docs only — the run happens AFTER this merges AND
after the runner is committed and reviewed).** This screen **cannot kill a candidate.**
DATE: 2026-08-17. Implements design #984 §5 step 2 for the three step-1 emitters
(model#227: `high52w`, `lowbeta`, `quality_gp`). The estimand, corpus and thresholds are
fixed before any candidate score is computed (effective-sample-before-decision-rule;
runner guards are prereg content). Re-running with different parameters after seeing
results is FORBIDDEN — but see §1 for what a result here does and does not authorise.

## 1. Semantics — the screen TRIAGES; it neither kills nor admits

**Revised 2026-08-17 (codex review, MED).** An earlier draft of this spec claimed the
screen was kill-only and that its kills were final. That claim rested on a survivorship
argument that does not hold (§2), so it has been withdrawn rather than patched.

What this screen produces is a **triage signal**: a candidate that cannot show a
placebo-clean IC difference on seven years of data is **FLAGGED** — deprioritised in the
#984 §5b queue, and required to clear a point-in-time rerun before it may be killed.
A candidate that is not flagged has shown only "not obviously dead": admission to the
roster still requires the full §5 path (frozen prereg + episode-block WF + the |ρ|<0.7
incremental-information gate under #984 §5b's Holm family).

Because the screen is exploratory and non-confirmatory in **both** directions, it uses NO
multiplicity correction and a deliberately lenient threshold; all confirmatory burden
stays downstream.

**Nothing in this document authorises a kill.** A kill requires, at minimum, a
point-in-time universe (§2) and the committed runner of §7.

## 2. Frozen corpus

- **Dates**: 2019-01-14 .. 2026-03-02 (the 125-fold WF window; 1,792 trading days
  `[VERIFIED — #984 §3 corpus]`), sampled **weekly** (every 5th trading day) → 358
  cross-sections.
- **Universe**: the current watchlist (the 145-name live universe) with per-date data
  availability; names lacking an emitter's min_obs on a date are absent that date
  (the emitters' own frozen floors apply, incl. NAMES_PER_DATE_FLOOR=50).
- **Survivorship — direction UNKNOWN, and that is why this screen cannot kill**
  `[REVISED — codex review 2026-08-17]`. The current watchlist is survivorship-tilted for
  2019-era cross-sections. An earlier draft asserted this INFLATES measured ICs and
  therefore made kills "safely valid". **That is wrong**: a current-survivor universe does
  not monotonically inflate every factor's IC, nor every genuine-minus-placebo Δ. It can
  move either sign, and the plausible mechanisms run the wrong way for exactly two of the
  three candidates here:
  - `lowbeta` — survivors of a 2019–2026 window over-represent names that carried and
    survived high beta. Conditioning on that can **compress or invert** low-beta's
    measured cross-sectional edge.
  - `quality_gp` — if survival is itself partly quality-selected, the surviving
    cross-section has **less** dispersion in quality than the true one, which depresses a
    rank-IC computed on it.
  So a low Δ measured here may be an artifact of the universe rather than a property of
  the candidate, and a kill decided on it would be unsound. Hence §1: FLAG, do not kill.
  A point-in-time universe is the fix, and it is deferred, not assumed away.
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

## 5. Frozen triage rule (one shot per corpus)

A candidate is **NOT FLAGGED** iff, at h=20 on the frozen corpus:
1. Δ > 0, AND
2. block-t(Δ over the 89 non-overlapping 20d blocks) ≥ **1.0**, AND
3. the per-block Δ is positive in > **50%** of blocks with data.

Anything else = **FLAGGED** (recorded verdict; no re-run, no parameter search, no
alternative horizon rescue — h=60 is informational only). A FLAGGED candidate is
deprioritised and must clear a point-in-time rerun before any kill decision; it is not
killed by this document.

The lenient t≥1.0 is the exploratory asymmetry: the screen must not manufacture admits,
and a true-but-weak candidate that flags here could only have been rescued by exactly the
data-mining this program forbids.

## 6. Measured alongside (informational at this stage)

Pairwise Spearman ρ of each candidate's scores vs `multifactor_core`, `mom_slow_12m`,
`mom_fast` on common dates — early visibility for the |ρ|<0.7 roster gate, which is
APPLIED at prereg admission, not here.

## 7. Execution contract — the runner is frozen BEFORE the run, not with the results

`[REVISED — codex review 2026-08-17, HIGH]` An earlier draft deferred the derivation
script to the results PR. That left block assignment, missing-data handling, the common
genuine/placebo date set, minimum names per cross-section and per block, tie behaviour,
and the exact correlation aggregation mutable *after* this spec was visible — which is
precisely the freedom a frozen spec exists to remove. Runner guards are prereg content,
not implementation detail.

Required order, and no scoring run may start before step 3 completes:

1. **This spec merges.**
2. **The deterministic derivation script is committed and reviewed** — in this repo or a
   separate runner-only PR — with every guard above written down and testable:
   block assignment; missing-data handling; the common genuine/placebo date set;
   `NAMES_PER_DATE_FLOOR` and a minimum-blocks floor; tie behaviour in the Spearman
   ranking; the exact aggregation used for §6's ρ matrix.
3. **The emitter identity is pinned**: the exact `renquant-model` commit and artifact
   parameters the runner executes. The pin must name a **merged commit, never a branch**
   — the reason this clause exists is that model#227 was open, and therefore mutable,
   while this spec was being reviewed. It has since merged, so the pin is available:
   `74c22647a7880c6a3234e53fb5d037d82fde3faf` `[VERIFIED — merge commit of model#227,
   read back from the PR after merge at 2026-08-17T22:31:52Z]`. The runner PR must
   restate it and confirm the artifact parameters it executes match that commit.
4. The script then runs ONCE (read-only inputs; outputs to `doc/research/data/`), in an
   isolated worktree — never against a live tree.
5. Results PR carries: per-candidate genuine/placebo series, block table, verdicts, and
   the ρ matrix; every number provenance-tagged.

Verdicts are **triage outcomes**, not kills (§1). Not-flagged candidates proceed to the
#984 §5b manifest freeze; flagged candidates proceed only after a point-in-time rerun.
