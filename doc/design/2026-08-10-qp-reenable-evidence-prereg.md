# qp re-enable evidence prereg — selection-level WF alpha of the served recipe through the designed gate

STATUS: FREEZE CANDIDATE (orch#954). Binds at merge; post-merge edits
void it (a new dated design is then required). The runner lands as a
separate PR bound to §7 and executes ONCE. This document REINTERPRETS a
recorded condition (stated in §2 and flagged for review as such).

## 1. The condition being operationalized

The 05-23 record set `qp_min_invested_pct = 0` + `qp_cash_drag_lambda
= 0` with: "re-enable only after WF shows benchmark-relative alpha
survives the strict admission gate." orch#945 measured
`qp_min_invested_pct = 0` as the operative lock; post-06-23 the
optimizer's optimum is the ~79%-cash book (orch#943). This prereg
defines what evidence satisfies that sentence.

## 2. Why the literal reading cannot be tested — and the reinterpretation

Portfolio-level power, computed on PRE-2026 data only (2023-2025,
291-name corpus universe, 400 seeded random held-5 books): a 5-name
book's daily excess-vs-SPY volatility is σ_d = 0.94%/day (ρ₁ −0.016),
giving MDE at 80%/α=0.05 of **82.4%/yr (63d) / 58.3%/yr (126d) /
41.2%/yr (252d)**; a plausible 10%/yr alpha needs ~17 years [VERIFIED —
`data/2026-08-10-qp-power-calc.py`]. The literal portfolio-significance
reading is therefore NOT testable at policy grade on any feasible
window (the G-1 power-gate block, recurring at the portfolio level).

**REINTERPRETATION (the review must approve this as such):** "WF shows
benchmark-relative alpha" is evaluated at the SELECTION level, where
power exists (§5): the WF-replayed served recipe's gate-surviving
selections must show positive cross-sectional forward alpha. The
operator's separate right to a policy-rule decision (point estimate +
guardrails + rollback, no significance requirement) is unaffected and
orthogonal.

## 3. Estimand (one sentence)

On the eight embargoed v2-CUTS test folds (91-day gaps, per-row purge
on the corpus's own calendar — model#213's frozen convention), the mean
daily top-5 `fwd_5d_excess` (per-day cross-sectional z, the corpus
label convention) of the SERVED RECIPE's admission-gate-surviving
selections, minus the per-day labelled-universe mean, must be
≥ 0.0337σ/day with a stationary-bootstrap 95% CI excluding zero.

## 4. Arms and machinery (all frozen)

* **Scorer under test — the served recipe, replayed per fold**: the
  blend construction z(panel leg) + z(momentum leg), where the panel
  leg is the production panel family trained per WF fold (train ≤ the
  fold's train end, per-row purge; production trainer params
  `PANEL_LTR_PARAMS`, 100 rounds, the 172-column feature contract),
  and the momentum leg REPLAYS the frozen recipe (`momentum-v0-
  fd65161a…` params fingerprint) at historical weekly cutoffs
  mirroring the live publish cadence — recomputed, not backfilled (no
  artifacts exist pre-2026-08). Fallback if the recipe replay fails
  its golden checks at any cutoff: drop the leg for the affected
  window and publish the composite degradation (z(panel) alone)
  alongside. z semantics per `blend_scorer.py` (ddof=0, NaN
  propagates).
* **Gate — the DESIGNED mechanism, per fold**: within each test fold,
  entry-rank trade-monotonicity stamps are computed from the replayed
  scorer's own fold-local trades by the designed criteria
  (`admission_tasks.py`), and admission filters selections BEFORE the
  statistic. No live artifact's stamps are reused; no bar is
  re-leveled. Decision basis for not waiting on the #942 serving fork:
  the served artifact's BULL_CALM entry-rank Spearman is 0.0023 over
  n=104 — a full miss; an evidence design presupposing a repaired
  model would assume away what the gate tests. If the gate starves a
  fold-day below k selections it is coverage-recorded; if starvation
  pushes the realized day count below the §5 power floor, THAT is the
  published finding ("the recipe's alpha cannot be shown to survive
  the gate").
* **Vintage**: all legs and labels share today's OHLCV vintage
  (as-of-then files do not exist); stated openly — the serving-fidelity
  line measured same-week reconstruction at 0.97+ (orch#949/#950).

## 5. Power and the numeric bar (computed pre-freeze, PRE-2026 data)

Selection-level daily mean-z statistic, k=5: σ = 0.443σ/day
[VERIFIED — `data/2026-08-10-qp-power-selection.py`]. The eight test
folds contain **N = 1,357 corpus days** (191/191/191/189/188/191/190/
26). MDE at 80%/α=0.05: **0.0337σ/day ≈ 6.9%/yr gross** (z→raw via the
median per-day raw dispersion 4.04%; gross, pre-cost, pre-sizing — an
upper bound on realizable, stated as such). Power floor: if
gate-starvation drops realized comparison days below 700, the MDE
degrades past 0.047σ/day and the run reports power-insufficiency
instead of a verdict on the bar.

## 6. Outcome semantics and non-inheritance

* PASS (statistic ≥ 0.0337σ/day, CI excludes 0, ≥700 realized days) ⇒
  the 05-23 condition is met under this prereg's reinterpretation; the
  deliverable is a strategy-104 PR flipping `qp_min_invested_pct`
  THROUGH REVIEW (never a live-tree hand-edit — containment protocol
  otherwise), citing this document and the run artifacts.
* FAIL or power-insufficient ⇒ the locks stay; the report states which
  component failed. Every outcome publishes the full table.
* NON-INHERITANCE: orch#953's diagnostic (its window 2026-05-20..07-31
  and results) informed this design and may not be cited as
  confirmatory; the corpus test folds end 2026-05-07, before that
  window, so the exclusion is satisfied by construction.
* No sweeps: one k (5), one horizon (5d), one bar, one window. A 60d
  variant when extension labels realize (~Oct) is a NEW dated design.
* Report-only cost companion: top-5 membership turnover and the L2-S
  10bps convention expressed in σ/day via the same mapping; no gate
  authority.

## 7. Freeze surface (binds the runner PR)

The runner must: ast-read the v2 CUTS/purge convention from the frozen
harness text; assert the frozen corpus sha (870f68eb…); read
`PANEL_LTR_PARAMS` from the production trainer module and record the
module's git revision; replay the momentum recipe from its frozen
params fingerprint with golden checks; compute per-fold designed-gate
stamps from fold-local trades only; produce verbatim evidence files
(`_daily.csv`, `_coverage.csv` with both asymmetric name lists,
`_summary.json` with every pin above); rehearse on a synthetic fixture
with planted/null/starvation controls BEFORE the real run and commit
the fixture as tests (the model#220 convention); and emit
`verdict: PASS|FAIL|POWER_INSUFFICIENT` exactly as §6 defines. Model
internals (training, scoring) live in renquant-model; this repo's
runner joins and reports (the orch#953-P0 boundary). Any deviation
voids the run.
