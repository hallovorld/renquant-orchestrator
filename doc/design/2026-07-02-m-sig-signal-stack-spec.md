# M-SIG: the G106 signal-stack spec — candidates, estimands, frozen thresholds, kill conditions

STATUS: design / pre-registration scaffold for review (docs only). This is the MID-term IC
core of the unified plan (#231 §1 Term IC) — the explicit build+measure task G106 gates on.
Thresholds below are FROZEN by this document BEFORE any candidate is measured; loosening any
of them after seeing evidence violates the prereg discipline (#230 §1).
DATE: 2026-07-02

## 0. The gate this feeds (fixed, from the merged route)

**G106 (2027-Q4): ≥2 orthogonal signals, each placebo-clean IC ≥ 0.015 individually,
combined ≥ 0.02, measured cross-family ρ committed, TC ≥ 0.6.** Stacking math planning range
0.028–0.033 at the measured intra-family ρ = 0.217 (POC-D). Kill branch if nothing clears:
benchmark-sleeve default + PIT accrual continues + 107 re-scoped execution-only.

## 1. The candidate table (all evidence tiers declared)

| # | Candidate | Estimand | Substrate | Prior evidence (tier) | Individual threshold (frozen) | Earliest test | Kill condition |
|---|---|---|---|---|---|---|---|
| C1 | **Estimate-revision drift** | x-sec rank of trailing Δ(consensus FY1/FY2) over 1m/3m, PIT `available_at`-lagged | #233 forward store (N2) | literature standalone monthly IC 0.02–0.03 post-decay (cited); OUR data: none yet — that is the point of N2 | placebo-clean IC ≥ 0.015 on ≥6mo of accrued PIT history, per-regime cuts reported | **2027-Q1** (≥6mo accrual) | <0.010 at 9mo accrual ⇒ drop from stack |
| C2 | **Quality composite (FMP-full)** | x-sec rank of {GP/A, accruals, net-issuance} composite, quarterly, `acceptedDate`-lagged | FMP harvest post-N3 coverage verdict | fundamentals_scan (measured): quality NULL on the THIN free-tier panel — the re-test is justified ONLY by the coverage upgrade, else it re-litigates a NULL | same ≥0.015 bar; additionally must beat the thin-panel null by a stated margin (the coverage delta is the hypothesis) | 2026-Q4 (post-N3 verdict) | coverage report shows <20% panel improvement ⇒ do NOT re-run (the NULL stands) |
| C3 | **Regime-conditioned residual momentum** | mom_12_1 orthogonalized to sector+β, gated to BULL_CALM/BULL_VOLATILE only | price panel (exists) + sector map + regime labels | regimemom (measured): UNCONDITIONAL trend-gate fails (2021 sign-flip inside UP-trend); the RESIDUAL×regime cell is the one untested combination; canonical raw momentum NULL stands and is not re-tested | ≥0.015 in the conditioned cell AND conditioned-minus-unconditioned difference > 0 with CI | 2026-Q3 (data exists) | conditioned cell ≤ unconditioned ⇒ the lead is dead; record and stop |
| C4 | **Trend-scanning label** (model-side lever, not an additive signal) | retrain target = signed t-stat of the strongest forward trend window (LdP), vs raw fwd_60d | alpha158 multih panel (exists) + the REPAIRED WF gate (S1–S3) | #176 (measured): BULL_CALM placebo-clean beats raw 3/3 seeds, mean +0.0149; absolute ICs untrustworthy (embargo floor) — a promote-to-proper-gate result | the PROPER gate's own bar: placebo-DIFFERENCE > frozen margin on the production WF + sim non-inferiority | 2026-Q3 (gate repair done — S1/S2 merged, S3 pending) | fails the proper gate ⇒ recorded; raw label stands |

## 2. Design rules (bind all candidates)

1. **Measurement substrate**: every candidate is evaluated on the S5/S8 substrate (durable
   pick-table + ledger), never on ad-hoc /tmp panels — the A1 lesson.
2. **Placebo-clean differences only** (never absolute IC — the ~+0.04 embargo floor).
   Per-regime cuts mandatory; BULL_CALM is the binding cell (79% of live time).
3. **No settled-NULL re-litigation**: raw momentum, fundmom, label neutralization,
   multi-horizon sleeves stay closed. C2 re-runs ONLY under its coverage-delta hypothesis;
   C3 tests ONLY the untested residual×regime cell.
4. **Orthogonality is measured, not assumed**: pairwise score ρ committed per candidate pair
   as each lands (extends POC-D beyond the price family); the combined-IC projection uses
   measured ρ.
5. **One candidate PR at a time**, each with its own frozen threshold cited from THIS table;
   a candidate that misses its bar is recorded (evidence doc) and dropped — the stack's
   value is the survivors, not the roster.

## 3. Sequencing and what it means for G106's probability

C4 and C3 are testable in Q3 with existing data; C2's slot depends on the N3 coverage
verdict (Q4); C1 — the literature-strongest and truly orthogonal leg — cannot be measured
before 2027-Q1 by construction (PIT accrual). G106's ≈0.45–0.50 composite therefore rests
on ≥2 of {C1, C2, C3, C4} clearing bars whose earliest reads span Q3-2026 → Q1-2027. An
early double-clear by C3+C4 would pull the G106 read forward a quarter; an early double-miss
does NOT trigger the kill branch before C1's window has run (the branch requires ALL
candidates' windows exhausted — killing the stack before its strongest leg can even be
measured would be a sequencing artifact, not evidence).

## 4. Open review questions

1. C2's "coverage-delta ≥20% or don't re-run" — right bar for justifying a NULL re-test?
2. C3's conditioned-cell CI construction (date-block bootstrap, block=13 per A1 convention?).
3. C4's frozen placebo-difference margin: propose 0.02 (vs the measured ~+0.04 shared floor),
   to be fixed in the S3 gate-repair PR before any C4 run.
