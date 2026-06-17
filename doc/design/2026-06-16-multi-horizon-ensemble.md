# Multi-Horizon Ensemble — Parked Research Note

**Status:** parked research note · no implementation authority
**Date:** 2026-06-16
**Relates to:** `renquant-system-feature-map.md` §2.4 (model-capability), the
scorer-lineup decision (PatchTST primary; ensemble not adopted; no further
ensemble implementation work unless a defined reopening trigger occurs).

This note preserves a possible future ensemble hypothesis. It does **not**
reopen the active scorer-lineup decision, authorize a shadow scorer, or create
implementation work on `main`. Any implementation must first cite the specific
reopening trigger that has been satisfied and the evidence window that satisfies
it.

## 1. Motivation — the horizon/placebo discovery

Six 60-day retrains (B1 bare, B2/B5 pruned, B3 cross-stock, A1 fresh-source,
xstock) ALL fail the WF sanity placebo. The failure is **not** a prunable
feature family — it is intrinsic to the **60-day label's own slow persistence**:
the model's score correlates with a 120-day-shifted label as strongly as with
the aligned one (placebo ratio 2.8–25; the gate requires `< 0.5`). After pruning
the slow-vol/drawdown family the model just reconstructs the same drift from the
remaining features.

A **20-day** model (same recipe, `--label fwd_20d_excess`) **passes** the placebo
at its proper 2×-horizon (40-day) shift — **reproducibly across two seeds**:

| model | full real IC | 40d aligned | 40d placebo | ratio (<0.5) |
|---|---|---|---|---|
| 20d seed44 | +0.0074 | +0.0150 | +0.0073 | **0.49 ✅** |
| 20d seed45 | +0.0119 | +0.0401 | −0.0198 | **0.49 ✅** |
| (all 60d) | — | — | — | 2.8–25 ✗ |

**Read:** shorter label horizons carry genuine horizon-specific signal; longer
horizons mix in slow cross-sectional drift that the gate (correctly) rejects.
The 20d edge is *real but small* (marginal pass). This is a plausible regime
where an **ensemble across horizons** might help: each horizon may contribute a
weak-but-genuine signal, and averaging cross-sectional ranks could diversify
and damp per-horizon drift. That remains a hypothesis until it is tested under
the active reopening rules.

## 2. Candidate design if reopened

### 2.1 Components
PatchTST models, identical recipe (pruned 157 features, `--val-days 126`, seq 24,
distributional head), differing only in label horizon:
- **5d** (`fwd_5d_excess`) — fastest, lowest drift, captures short reversal/momentum.
- **20d** (`fwd_20d_excess`) — the confirmed placebo-passing sweet spot.
- **60d** (`fwd_60d_excess`) — the production horizon; included for the medium-term
  component (its drift is damped, not relied on, by rank-averaging).

Multi-seed per horizon (>=2) to average training noise.

### 2.2 Combiner — per-day cross-sectional percentile-rank average
For each trading day, rank each component's scores **cross-sectionally** to
percentiles in `[0,1]`, then average across components (and seeds). Rationale:
- **Scale-invariant** — the components' raw outputs live on different return
  scales (5d vs 60d); ranks make them comparable without calibration.
- **Robust** — averaging ranks is a well-behaved rank aggregation (Borda-style),
  insensitive to any one component's outlier days.
- **Drift-damping** — a component whose "signal" is drift contributes a noisier
  rank that the average dilutes, while genuine agreement reinforces.

Optionally weight by each component's validated genuine-IC (the placebo-passing
aligned IC), down-weighting horizons whose signal is mostly drift.

### 2.3 Candidate scorer architecture
If the scorer-lineup decision is reopened, a `HorizonEnsembleScorer` could load
N PatchTST checkpoints (via the fixed cross-stock-aware loader), expose
`score_with_history(panel_history, tickers)`, score each component,
percentile-rank per day, and return the weighted average. It should not be built
or wired while the current decision record remains active.

## 3. Evidence required before reopening
Before any implementation, shadow wiring, or promotion discussion, the proposal
must satisfy at least one reopening trigger from
`doc/decisions/2026-06-12-scorer-lineup-decision.md`:

- The WF gate fails a fresh-cutoff PatchTST retrain while an ensemble or
  alternative candidate passes the same gate on the same evidence windows.
- The shadow rail shows the shadow scorer dominating the primary on rolling
  60-day live IC for a sustained period (>=1 quarter), measured fairly
  (same-cutoff, strict OOS).
- A regime of sustained calm-tape losses attributable to the primary's measured
  calm-window weakness occurs with real PnL impact.

Only after one of those conditions is documented should an ensemble evaluation
be run as an adoption candidate:

1. Train the component set (5d×≥2, 20d×≥2, 60d×≥2 seeds).
2. Offline: score all components over the OOS sanity panel; build the ensemble;
   compute the placebo diagnostic vs **each** horizon label (shift = 2×horizon).
   **Acceptance signal:** the ensemble's placebo ratio `< 0.5` at the 60d shift
   (i.e. the blend passes where the 60d component fails) AND aligned IC ≥ the
   best single component.
3. Compare to each component and to equal-weight vs IC-weighted blends.

## 4. Deployment constraints
No deployment is approved by this note. If a reopening trigger is satisfied and
an implementation PR is later authorized, the deployment path must still be
shadow-first, with no live orders, and must accumulate live out-of-sample
evidence before any A/B/C promotion decision. Promotion still requires the full
WF gate (3-cut + sanity) and an explicit horizon contract for sizing and
rotation.

## 5. Risks & open questions
- **Marginal 20d (0.49 ≈ 0.5):** the single-horizon edge is thin; the ensemble's
  value is the bet that horizons *stack*. Must be shown, not assumed.
- **Trading horizon contract:** the live sizing/rotation layer is `strict` 60d
  (`qp_mu_horizon_days`, `kelly_sigma_horizon_days`, `rotation.target_horizon_days`).
  A promoted ensemble needs a defined "ensemble horizon" for μ/σ — open question
  (use the dominant component's horizon, or recalibrate μ on realized blended-rank
  returns).
- **Weighting:** equal vs genuine-IC-weighted — decide empirically on shadow data.
- **Component count / cost:** ≥6 checkpoints to load per score; fine offline and
  in shadow, watch latency if ever promoted.

## 6. Non-goals while parked
- Do not build `HorizonEnsembleScorer`.
- Do not wire an ensemble into the daily shadow path.
- Do not train additional components on `main` for ensemble adoption.
- Do not treat this note as changing the PatchTST-primary / XGB-shadow lineup.

## 7. Permitted next step
If new evidence appears, add a decision-update PR that cites the exact reopening
trigger, links the evidence window, and explains why the active scorer-lineup
decision should be reopened. Implementation should come only after that
decision-update PR lands.
