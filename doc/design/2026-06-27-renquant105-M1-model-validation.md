# renquant105 milestone M1 — model + validation (the make-or-break gate)

2026-06-27. Part of the renquant105 suite. **This is the GO/NO-GO milestone.** Per the
feasibility analysis (§A of the master spec) the PRIOR is that M1 FAILS — that is an
acceptable, honest outcome, not a project failure.

## Objective + scope
Train an intraday model (GBDT primary + PatchTST shadow) on **open→close** triple-barrier
labels and **validate it net-of-cost (on the M0 MEASURED cost model)** with CPCV /
probabilistic PSR-DSR / PBO / placebo. Offline only — no shadow run, no orders. The output
is a single decision: does a placebo-clean, cost-clearing **open→close** intraday edge
exist at this size/data, yes or no. **This is the H1 (intraday-alpha) experiment;** the H2
(execution-timing/risk) experiment is independent (master §7).

## Requirements
**Functional:**
- F1.1 Triple-barrier label builder (σ-scaled profit/stop + time barrier = the **session
  close**); **single primary horizon = open→close** (finding 2); 30min/2hr are *secondary
  diagnostics only*. **Separate overnight from intraday** (overnight gap excluded from
  label + features + PnL). Labels + forward returns are **bar-timestamped + session-aware**
  off the M0 session-horizon surface (the daily `fwd_5d`/`fwd_60d` surface is insufficient).
- F1.2 **Embargo = the open→close label horizon IN BARS, rounded to a session boundary**
  (session-aware) + overnight-gap purge (the single most important leakage fix — getting it
  wrong reproduces the inflated-IC bug). The block scheme for the **overlapping** labels
  defines **effective-independent observations** (feeds the sample-size requirement below).
- F1.3 Train GBDT (`rank:pairwise`) primary + PatchTST/PatchTSMixer ranker shadow on the
  M0 intraday panel.
- F1.4 **Lean-style cost model calibrated to the M0 MEASURED arrival/quote/fill sample**
  (spread + slippage + IEX adverse-selection by ticker × time-of-day; impact ≈ 0 at this
  size) — **NOT a fixed 11 bps** (finding 5) — every metric reported **net of it**.
- F1.5 **CPCV** harness (distribution of OOS Sharpes), **probabilistic PSR/DSR ≥ 0.95**
  (Bailey & López de Prado Deflated Sharpe — a *probability*, reconciled with PSR; the old
  vacuous "DSR>0" is dropped) fed the **full trial universe** (below), **PBO** (CSCV),
  shuffled-label + time-shift **placebo** — all **gating**.
- F1.6 **Full trial-universe ledger (finding 3).** N counts EVERY trial across:
  horizons × labels × features × seeds × models × gate variants, **plus the prior 104/105
  trials** (the ~70–81 PatchTST runs already carry into N). This N feeds the DSR/PSR
  deflation and the multiple-testing haircut (t≈3, Harvey-Liu-Zhu).
- F1.7 **Power / MinTRL pre-registration (finding 3).** Before training, pre-register the
  **minimum aged sample in effective-independent observations** required to detect the
  target effect at the chosen power, derived from MinTRL (Bailey & López de Prado), using
  the F1.2 block scheme — NOT a raw "40–80 dates" count. Phase gates use **CIs + effective N**.
**Non-functional:** reproducible; deseasonalized targets (intraday U-shape); average-
uniqueness weighting on overlapping labels.

## Deliverables
Intraday model artifacts (GBDT + PatchTST) + calibrator + WF-gate metadata; the
Alpaca/IEX cost model; the **validation report** (CPCV OOS-Sharpe distribution, DSR,
PBO, placebo deltas, net-of-cost Sharpe, IC + decay) with the trial count.

## Metrics / KPIs
OOS rank IC at the **open→close** horizon (placebo-clean), net-of-cost Sharpe,
probabilistic **PSR/DSR**, PBO, hit-rate on the cost-clearing subset,
cost-as-%-of-gross-alpha, IC decay half-life — all at the open→close horizon (NOT `fwd_5d`).

## Acceptance criteria (the GO bar — ALL must pass)
| Criterion | Threshold |
|---|---|
| OOS rank IC @ **open→close** horizon | ≥ **+0.03**, placebo-clean (above the shuffled-label floor by a clear margin) |
| Net-of-cost Sharpe (CPCV, **measured** cost) | ≥ **1.0** |
| **Probabilistic PSR/DSR** (Bailey & LdP) at the full trial N | **≥ 0.95** (the old "DSR>0" is dropped as vacuous) |
| PBO (CSCV) | **< 20%** |
| Net-PnL block-bootstrap 95% CI | lower bound **> 0** (block ≥ open→close label horizon) |
| Sample | ≥ the **power/MinTRL-derived minimum in effective-independent observations** (F1.7), not a raw date count |

## Expected outcome (预期) + kill condition
**Honest prior (§A): FAIL.** Expected net-Sharpe band −2.0 to +0.5 (centered negative);
single-bar edge ~1 bp vs ~11 bps cost. **KILL CONDITION:** if the GO bar is not cleared,
**STOP — intraday alpha trading stays OFF**, and the project falls back to the
defensible residual (execution-timing + risk on the daily book; master spec §0). Do NOT
ship a cost-negative book. A pass (improbable) unlocks M2.

## Dependencies / inputs
M0 (clean intraday panel); `renquant-common` CPCV / purged-CV / WF tooling; the cost
model; the trials ledger.

## Risks (FMEA subset)
Overfitting (multiple-testing across ~70–81 prior PatchTST trials → DSR mandatory);
overlapping-label leakage (purge/embargo in bars); the IEX adverse-selection penalty
(1–3 bps/leg) eating the entire net edge → may need SIP before a fair test.

## Effort
~3–5 weeks (label design + cost model + CPCV harness + train + the validation report).
The validation discipline, not the training, is the work.
