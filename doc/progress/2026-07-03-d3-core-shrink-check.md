# 2026-07-03 — D3 incumbent-book core-shrink check — NULL (no core helps; raw reads uniformly negative)

Durable record for the D3 core-shrink research PR (single source; details live
in `doc/research/2026-07-03-d3-core-shrink-check.md`).

## What happened

- Executed the incumbent-book core-shrink check RS-5 (#282 §4) explicitly
  deferred to the D3 memo — the LAST input to the D3 down-cap decision.
  Freeze-first three-commit discipline: commit 1 = frozen mini-spec BEFORE any
  measurement; commit 2 = harness + controls
  (`scripts/d3_core_shrink_check.py`); commit 3 = results + verdict. 0
  deviations against the frozen spec.
- Question: does shrinking the incumbent panel to a high-separability core
  improve the CORE'S OWN pick quality (mirror image of M8's verified dilution
  finding #261/#264; RS-5's exploratory liquid-core echo)?
- Frozen family: {LIQ dollar-ADV, SEP per-name |IC| on a strictly disjoint
  pre-2019 window, SECBAL sector-balanced SEP} × {60, 90}; WF arm = paired
  core-trained vs 133-trained per-date ΔIC on the core's dates (E35 harness,
  M8 parity, seeds 42/43/44, all 7 cuts qualify, n=1,618 dates); S8 arm =
  pick-table top-decile pick-quality Δ (no retrain, book-restriction read);
  Bonferroni k=12 one-sided 99.5833% block-bootstrap bounds; ±0.010 band.
- **Verdict: NULL on all 6 members, both arms.** 18/18 WF seed-member raw
  deltas NEGATIVE (−0.012…−0.050); all 6 S8 deltas negative (n.s.). HELPS is
  nowhere close; HURTS narrowly fails its pre-registered unanimity legs
  (SECBAL-90 missed only on one seed's placebo-clean sign).
- Controls all PASS: plant detected ×3 seeds (+0.087, LB +0.084); true-null
  retrains never clear (noise floor ±0.006); S8 oracle detected; 6 random S8
  cores NULL.
- Mechanism (diagnostics): random same-size cores degrade the same → panel
  SIZE dominates, selection buys nothing; the 133-trained model ranks the
  cores fine (selection-only read ≈0…+0.02) → the cost is RETRAINING NARROW,
  not the names; placebo deltas are themselves negative (−0.023 mean) → the
  leakage floor is panel-size-dependent and much of the raw degradation is
  mechanical.

## What it means for D3

- No IC-level support for a down-cap's shrink leg; both BR-path hedges have
  now reported (M8 adds = NO-GO; shrink-and-retrain = NULL/negative). Term BR
  should not be priced as an IC gain from panel-composition moves.
- If D3 elects a down-cap for cost/ops/data reasons: keep the TRAINING panel
  broad; evidence a book restriction via a production-scorer shadow replay,
  not this harness.

## Evidence

`doc/research/evidence/2026-07-03-d3-core-shrink/` — frozen_spec,
core_selection, wf_results, s8_results, verdict, manifest (input SHA-256s +
code sha), per-date series (gz) sufficient to recompute every bootstrap.
VERDICTS.md row added in this PR.

## Next

- D3/L1 synthesis consumes this memo + S9 (NULL) + M8 (NO-GO, UPHELD) + M7
  (INCONCLUSIVE pending Norgate primary panel) + N2 PIT accrual.
- Reopening: PIT panel-era outcome accrual re-runs the S8 arm; a
  book-restriction decision routes through a shadow replay (ops).
