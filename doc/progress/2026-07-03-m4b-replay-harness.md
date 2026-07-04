# 2026-07-03 — M4-b floor-replay evaluation harness (BUILD + VALIDATE; run-gated)

Implements the replay-implementation step (§6 step 2) of the merged M4-b design
(`doc/design/2026-07-03-m4b-relative-conviction-floor.md`, #260): the frozen §4
protocol as a read-only tool, plus the P1 A/B baseline reader. The confirmatory
Stage-1 RUN is **gated** — this PR ships and validates the machinery only.

## Delivered

- `scripts/m4b_floor_replay.py` — four modes, all read-only (`mode=ro` sqlite,
  pure-python calibrator head per the V5-verified (#272) recomputation):
  - `--replay`: candidates (a) quantile top-K% ∧ μ>0, (b) k·MAD ∧ μ>0,
    (c) re-anchored absolute vs the current absolute floor (stored prod μ ≥
    0.03) at matched admission rates (single parameter per candidate, set once
    to match baseline mean breadth B ±0.5, no per-bar retuning); (d) NGBoost
    σ-band SKIPPED with the design's deferral note (σ-wire OFF per the
    2026-05-17 A/B; separate operator decision). fwd_20d primary (fwd_60d
    auto-noted when it resolves), block-5 bootstrap + block-1 sensitivity,
    per-regime/per-era cuts, the five frozen Stage-1 criteria verbatim,
    deviations ledger (criterion 6).
  - `--baseline-report`: per-run intercept / sign-laundering / floor-clearing
    stats under the CURRENT calibrator with a fidelity-based pairing check —
    the reader for registered prediction #280.
  - `--controls`: S-REL positive plant + two true-nulls (iid noise;
    within-date permutation of real outcomes), all through the same
    small-n exact-tail / MC dispatch as the verdict path (V3 method note).
  - `--gate-check`: Stage-1 run-gate status.
- `tests/test_m4b_floor_replay.py` — 47 tests on synthetic fixtures (no prod
  inputs): calibrator head, recentering/pairing detection, floor rules,
  matched-breadth solver, exact enumeration vs independent brute force,
  degeneracy guard, criteria wiring, controls, run gate, sqlite-fixture modes.
  Full suite: 1518 passed, 3 skipped.
- Machinery-validation evidence (PRE-GATE EXPLORATORY, never Stage-1 input):
  `doc/research/evidence/2026-07-03-m4b-harness-validation/`.

## P1-restore handling (why the run is gated)

The calibrator was refit 2026-07-03 against the restored 06-21 scorer
(neutral −0.2667; artifact `abac923a35c3…`). Pre-restore June bars carry the
retired pairing's intercept, so the harness re-measures the CURRENT pairing's
baseline B before replaying: `--window pairing` (default) restricts the
substrate to bars whose stored μ reproduces under the live calibrator
(fidelity ≤ 1e−9, never date-assumed). **Run gate: ≥10 current-pairing
sessions with resolved fwd_20d outcomes** (also the block-5 non-degeneracy
floor). Today: 0/10 — no full 07-03 run in the DB yet. `--window all` gives a
cross-era exploratory read and is auto-recorded as a deviation.

## Pre-registered (before any results)

Criterion-5 tolerances (design required them set in this PR): saturation-freq
±0.10, p90/p95 admitted-count ±2, QP-spill-freq ±0.10, max zero-streak ≤
baseline+1. **Recorded deviation:** QP spill is proxied as floor-clearing
count > `panel_buy_top_n` (3) — the full QP-cap replay (correlation/sector/
whole-share) is not reconstructable read-only from stored scores; the Stage-1
results doc must carry this note. BL-4 default `prod-raw` (identical raw>0
mask across arms per §4); `arm`/`off` as sensitivities.

## Validation findings (machinery, not verdicts)

- Baseline-report reproduces the prod BL-2 `calibrator_sign_laundered`
  counter exactly on all 8 recent full runs (23/20/24/44/22/42/44/45).
- Controls caught a real inference bug during build: with ≤5 resolved dates,
  block-5 covers the whole window — every bootstrap atom equals the observed
  delta and the "CI" always excludes 0 (the M3 block-13 pathology, exact-branch
  form; perm-null false-fired 52%). Fixed with a degeneracy guard; criterion 1
  can never fire on a degenerate distribution (perm-null → 0.0 after).
- Cross-era exploratory (window=all, 14 bars, 9 evaluable, ~4 resolved dates):
  all three arms solve matched breadth exactly (B=13.64); iid-null false-fire
  7–10.5% vs nominal 2.5% at this n — criterion-1 verdicts must be read
  against the same-window measured null (V3 lesson); positive-plant power at
  gap 0.08: 0.62–0.78.
- Fixed en route: matched-breadth bisection had a reversed-interval bug in the
  decreasing branch; laundering counts made directional (BL-2 semantics).

## expkit note

`src/renquant_orchestrator/expkit/` is not on origin/main and no open PR
carries it (a parallel sprint builds it, uncommitted); the harness is
standalone pure-stdlib+numpy with primitives structured for direct migration
(`exact_block_bootstrap`/`delta_significance` ↔ expkit `stats`,
`run_controls` ↔ `controls`, `solve_matched_param` ↔
`evaluation.solve_matched_admission`).

## Next

1. ~10 sessions accrue under the restored pairing → `--gate-check` flips.
2. Run `--baseline-report` after Monday's session for the #280 prediction.
3. Gate met → Stage-1 confirmatory run, verdict recorded either way
   (candidate-for-shadow / no-winner); a winner authorizes SHADOW only —
   Stage 2 prospective confirmation gates any strategy-104 config PR (§3/§6).
