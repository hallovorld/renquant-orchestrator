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
≥ 0.0658σ/day with a stationary-bootstrap 95% CI excluding zero
(dependence-adjusted; §5).

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
* **Gate — the DESIGNED mechanism, fitted pre-test, applied forward
  (review r2: the r1 text was outcome-leaky — it stamped from the test
  fold's own closed trades and then filtered that fold's statistic;
  corrected to production temporal semantics; r3 adds the NESTED
  split so validation scores are themselves out-of-sample)**: each
  fold is split THREE ways —
  (i) GATE-FIT SEGMENT: train days up to `validation_start − 1`,
      where `validation_start` = train end − 251 sessions. The
      gate-fit models (panel leg trained with per-row purge so every
      training label's 60-session endpoint lands strictly before
      `validation_start`; momentum leg with recipe cutoffs ≤
      `validation_start`) see NOTHING from the validation segment;
  (ii) VALIDATION SEGMENT: the final 252 train-period days, scored
      OUT-OF-SAMPLE by the gate-fit models; the entry-rank
      trade-monotonicity stamps are computed there by the designed
      criteria (`trade_monotonicity.py` / `admission_tasks.py`) and
      FROZEN. Every gate input (entry score, trade entry/exit,
      realized 5d outcome) ends before the fold's train end, which
      precedes the test start by the 91-day embargo;
  (iii) TEST FOLD: scored by the FULL-TRAIN models (train ≤ the fold's
      train end, the §4 scorer bullet), retrained only AFTER the gate
      stamps are frozen; the frozen stamps filter these selections
      unchanged. Both boundaries (`gate_fit_end = validation_start −
      1` and `train_end`) and the per-fold OOS validation day counts
      are recorded in the run summary. So gate certification uses only
      out-of-sample scores on pre-test data, and the test statistic
      uses only a pre-fitted gate. The resulting
  per-regime eligible/passed stamps are FROZEN and applied UNCHANGED
  to the test fold's selections; no test-period outcome ever touches
  the filter. Simulated-trade convention for the validation segment
  (frozen): enter the recipe's top-5 each validation day, exit after 5
  sessions, `pnl_pct` = raw 5d ticker return minus SPY (production
  round-trip semantics), `entry_rank_score` = the recipe's composite
  score, `entry_regime` from the production regime series as recorded
  for those dates; the designed thresholds apply verbatim
  (`min_n_per_regime` 30, `min_spearman` 0.02, positive top-bottom
  spread — `trade_monotonicity.py:20-33`). For quantitative context,
  the served artifact's BULL_CALM Spearman 0.0023 sits 8.7× below the
  0.02 bar. No live artifact's stamps are reused; no bar is
  re-leveled. Decision basis for not waiting on the #942 serving fork:
  the served artifact's BULL_CALM entry-rank Spearman is 0.0023 over
  n=104 — a full miss; an evidence design presupposing a repaired
  model would assume away what the gate tests. If the pre-fitted gate
  admits nothing in a test fold's active regime, its fold-days are
  coverage-recorded as gate-starved; if starvation pushes the realized
  day count below the §5 power floor, THAT is the published finding
  ("the recipe's alpha cannot be shown to survive the gate").
* **Vintage**: all legs and labels share today's OHLCV vintage
  (as-of-then files do not exist); stated openly — the serving-fidelity
  line measured same-week reconstruction at 0.97+ (orch#949/#950).

## 5. Power and the numeric bar (computed pre-freeze, PRE-2026 data;
review r2 — serial dependence now calibrated, not assumed away)

Selection-level daily mean-z statistic, k=5: σ = 0.443σ/day. The r1
independence assumption was WRONG for this estimand (review P1): a
model's top-5 is persistent across days, so the overlapping 5-day
labels induce strong serial dependence in the daily statistic. This
was calibrated on pre-2026 data with PERSISTENT random selections
[VERIFIED — `data/2026-08-10-qp-dependence-calib.py`, 400 seeded draws
per variant]:

| hold length | ACF lags 1-4 | Newey-West κ (Bartlett L=10) |
|---|---|---|
| 5 sessions (weekly refresh) | 0.63 / 0.35 / 0.16 / 0.03 | 2.972 |
| 21 sessions (sticky) | 0.75 / 0.53 / 0.32 / 0.15 | 3.863 |

The FROZEN calibration takes the CONSERVATIVE κ = 3.863. The eight
test folds contain **N = 1,357 corpus days** (191/191/191/189/188/191/
190/26) → N_eff = 351 → MDE at 80%/α=0.05 = **0.0658σ/day ≈ 13.5%/yr
gross** (z→raw via the median per-day raw dispersion 4.04%; gross,
pre-cost, pre-sizing — an upper bound on realizable, stated as such).
The bar remains reachable in principle: the orch#953 diagnostic point
estimate for the served arm was +0.113σ/day (non-inheritable, cited
only for scale). Power floor: if gate-starvation drops realized
comparison days below 700 (N_eff 181), the MDE degrades past
0.0915σ/day and the run reports POWER_INSUFFICIENT instead of a
verdict on the bar.

Frozen inference parameters: stationary bootstrap with expected block
length 10 (≥ 2× the calibrated ACF decay span of ~4-5 lags), B = 2000,
seed = 99; the same parameters produce the 95% CI in §3 and the §6
decision — no other inference procedure is admissible.

## 6. Outcome semantics and non-inheritance

* PASS (statistic ≥ 0.0658σ/day, CI excludes 0, ≥700 realized days) ⇒
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
the fixture as tests (the model#220 convention); use EXACTLY the §5
frozen inference parameters (stationary bootstrap, expected block 10,
B 2000, seed 99); and emit
`verdict: PASS|FAIL|POWER_INSUFFICIENT` exactly as §6 defines. Model
internals (training, scoring) live in renquant-model; this repo's
runner joins and reports (the orch#953-P0 boundary). Any deviation
voids the run.
