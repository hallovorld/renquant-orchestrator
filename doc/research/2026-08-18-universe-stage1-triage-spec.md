# Universe-extension Stage 1 — FROZEN triage spec (before any scoring)

STATUS: **frozen experiment spec (docs only — the run happens AFTER this merges AND the
committed runner is reviewed).** DATE: 2026-08-18. Operator-directed ("我要真正的alpha,
bull列"). Tests the structural thesis: the $11k account's one structural advantage —
no capacity constraint — is unused in 145 mega-caps; does the PROVEN tail statistic
transfer to a mid/small-cap extension where institutions cannot operate?

## 1. Semantics — TRIAGE, per the house's own withdrawn-convention ruling

The data store is a **survivor-only May-2026 snapshot (zero delisted names)**, and the
"kills survive survivorship" convention was formally WITHDRAWN in #987 (survivor
conditioning can compress or invert an edge). Therefore Stage 1 **neither kills nor
admits**: a FAIL deprioritizes the thesis (at ~zero cost); a PASS authorizes ONLY
Stage-2 spend (PIT universe hardening, ~$37-66/mo trial-first) — never a serving change,
never a retrain, never a capital decision. One shot per corpus; no re-runs.

## 2. Adverse priors, declared before the run

(a) E34 (2026-05-07): blind expansion 103→816 was NO-GO — whole-cross-section IC fell
+0.031→+0.0164; resume condition = clustered ~100-name waves. (b) RS-5: canonical
MOM/REV cleared nothing net of bucket costs down-cap; liquid slice read best.
**Neither tested the panel's tail statistic** (top-decile DGTW spread, t=+2.92, vs IC
t=1.15 on identical data) — the untested gap this Stage 1 fills. The t=2.92 benchmark's
own caveats carry: single-run, tail-dependent (winsorized t=1.70), not independently
reproduced.

## 3. Frozen corpus and arms — ZERO new data, ZERO writes to any live store

Everything reads the existing on-disk May-2026 snapshot as-is (no refresh needed: the
label window ends inside the data edge). Any corpus-build intermediate lands in an
isolated scratch dir, NEVER in `data/` (production inputs are untouchable; additive
writes are still writes).

- **Arm A (primary)**: the ~609-name full-recipe extension (non-watchlist; price $5-400,
  ADV≥$5M/63d, listing ≥3y; SEC-fundamentals-covered; OHLCV ≥5y). Scored by the
  **served production model pin VERBATIM** (the #987-frozen artifact lineage) — a pure
  TRANSFER test, no retrain: exactly the axis E34 died on, now on the high-power
  statistic.
- **Arm W (positive control, mandatory)**: the 145-name watchlist through the IDENTICAL
  harness and window — must reproduce the known tail-spread result, else the run is
  void (instrument failure, not evidence).
- **Arm B (exploratory only, labeled)**: the ~1,955-name alpha158-only set (missing 14
  features NaN-filled — a recipe VARIANT, not the recipe; reported by ADV bucket,
  never pooled with Arm A).
- **Corpus dates**: 2021-07-01 .. 2026-02-13 (h=60 labels mature inside the 2026-05-08
  snapshot edge), cross-sections every 5th trading day.
- **The $1-5M-ADV band is EXCLUDED from all verdict arms** — the frozen cost model has
  no bucket below $5M; admitting uncostable names manufactures false GOs.

## 4. Frozen estimand

Primary statistic = **per-date top-decile (by score) DGTW-adjusted spread** at h=60
(the proven instrument's own construction: vol×mom×beta tercile cells within-arm,
self-excluded, ≥15 names/cell else cell-unadjusted-and-flagged), with the paired
2h-lag placebo and decision quantity Δ = mean(genuine) − mean(placebo). h=20 secondary
(power support, never decisive alone). Whole-cross-section IC reported, informational.
**Costs charged per name**: RS-5 frozen buckets (25/40/60 bps RT for ADV ≥$25M /
$10-25M / $5-10M) applied to the top-decile turnover implied at the weekly cadence;
net-of-cost spread reported per ADV bucket.

## 5. Effective sample — counted, then the bars

~1,155 trading days → 231 weekly cross-sections; **19 non-overlapping 60d blocks**
(58 at h=20). Triage-grade only — stated before the rule, per the effective-sample
rule. **Frozen triage bars (h=60 primary, Arm A):**
1. net-of-cost Δspread > 0, AND
2. block-t(Δ over the 19 blocks) ≥ 1.0 (df=18 Student-t context; never 1.96), AND
3. >50% of blocks-with-data positive, AND
4. **the transfer prediction**: Arm-A Δspread ≥ Arm-W Δspread (same harness/window) in
   at least one costable ADV bucket.
All four → **PASS (triage)** → authorizes the Stage-2 PIT program only. Anything else →
**DEPRIORITIZED** (not killed — survivor-universe fails are directional, not final, in
both directions). Arm B can neither pass nor fail anything; it maps where coverage
spend would matter.

## 6. Execution contract

Deterministic runner committed AND REVIEWED before the run (the #990
freeze-then-review-then-run sequencing): guards must include served-pin byte-identity,
universe-filter assertions (name counts per §3 recomputed, not asserted), positive-
control reproduction check (Arm W within stated tolerance of the known result before
Arm A is even computed), cross-section/block-count assertions, paired-placebo identity,
snapshot-edge assertion (no label extends past 2026-05-08), and zero-writes-outside-
scratch. Results as their own PR: verdict table first, per-ADV-bucket net-of-cost
table, Arm-W control outcome, every number provenance-tagged. Compute: scoring is
minutes (served pin, no training); the one-time extension corpus build (~1h, hurst
un-memoized on the training path) runs under caffeinate in the isolated scratch.

## 7. Corpus-exposure ledger

First screen family on THIS extension corpus. The watchlist arm re-uses dates
overlapping prior corpora as a POSITIVE CONTROL only (it decides nothing). The Stage-2
confirmatory, if reached, uses fresh design + PIT universe + its own prereg.
