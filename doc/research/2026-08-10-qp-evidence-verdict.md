# qp re-enable evidence — official verdict: PASS

STATUS: the official execution of the merged freeze
`doc/design/2026-08-10-qp-reenable-evidence-prereg.md` (orch#955), run
on the MERGED runner (orch#956, 7 review-hardening rounds) against the
ADJUDICATED artifacts (model#221 + the model#222 stamps ruling). The
freeze grants this run its verdict authority.

## 1. The verdict and its numbers

| quantity | value | freeze requirement |
|---|---|---|
| **verdict** | **PASS** | — |
| realized comparison days | **898** of 1,357 scheduled | ≥ 700 ✓ |
| gate-starved days | 459 (33.8%) | coverage-recorded |
| mean daily top-5 excess-z (admitted days) | **+0.0981σ/day** (median +0.1184) | ≥ 0.0658 ✓ |
| bootstrap 95% CI (frozen: contiguous-run blocks 10 / B 2000 / seed 99) | **[+0.0139, +0.1782]** | excludes 0 ✓ |
| oracle plumbing control | +3.341 | strongly positive ✓ |
| cost companion (report-only) | 0.0030σ/day | no gate authority |

Gross-scale reading (the §5 median-day mapping, an upper bound on
realizable): +0.0981σ/day ≈ **20%/yr gross selection alpha** on
admitted days, pre-cost, pre-sizing.

[VERIFIED — committed `data/2026-08-10-qp-evidence_daily.csv` +
`…_coverage.csv` + `…_summary.json`, the merged runner's VERBATIM
outputs; runtime pins asserted: corpus 870f68eb…, harness 7ca9e48f…
(both runner-owned constants), scores b7c8158e…, stamps 0533ad12…,
manifest per model main after #222.]

## 2. The three-run trail (nothing hidden)

1. Run 1 (never adjudicated): on model#221's r1 artifacts — VOID, the
   momentum test arm served a single frozen artifact instead of the
   freeze's weekly cadence (the model#221 review caught it).
2. Run 2 (executed, HELD, never published): on the post-9f91df1 main —
   VOID, its stamps came from gate-fit momentum cutoffs INSIDE the
   validation segment, which freeze §4(i) explicitly forbids; the
   conflict was adjudicated in model#222 (freeze text upheld; test-arm
   scores were byte-identical in both constructions, so the ruling
   changed ONLY the stamps: folds 6+7 admitted vs fold 6). Run 2's
   numbers (POWER_INSUFFICIENT; 554 days; +0.1396σ/day) were disclosed
   on model#222 before the ruling, and are reproducible from the
   git history; they carry no authority.
3. Run 3 (THIS one): on adjudicated main — the official execution.

## 3. What PASS means and does not mean

MEANS (freeze §6): the 05-23 recorded condition — "WF shows
benchmark-relative alpha survives the strict admission gate" — is MET
under this prereg's reviewed reinterpretation (selection-level; the
designed gate fitted nested-OOS and applied forward). The deliverable
is a strategy-104 PR flipping `qp_min_invested_pct`, THROUGH REVIEW,
citing this document — never a live-tree hand-edit.

DOES NOT MEAN: (a) realized live P&L at this rate — the number is
gross, selection-level, pre-sizing, upper-bound by construction;
(b) any change to the admission gate itself — 33.8% of days remain
gate-starved and that trade-off now has a measured shape (the #942
fork's decision input); (c) automatic deployment — the knob PR's merge
and the machine's pin sync remain separately governed steps.

## 4. Pre-verdict P0 sweep

Swept this session before adjudication: the one machinery-adjacent open
item (#817, z-label ±0.5 clipping in per-regime ICs) does not touch
this run — the statistic consumes unclipped label-z; the gate consumes
raw pnl Spearman. No new P0 opened since the sweep.

## 5. Next (each separately governed)

1. strategy-104 PR: `qp_min_invested_pct` 0 → the reviewed value
   (the §6 deliverable; drafted next, cites this verdict).
2. The λ knob stays 0 (orch#945 measured it non-operative; revisiting
   it is out of this verdict's scope).
3. Deployment to the running machine = pin sync under the standing
   machine-landing grant discipline (operator's gate, unchanged).
4. The gate-starvation trade-off (459 days) feeds the #942 operator
   fork as measured decision input.
