# Progress — ZM/NFLX buy-bias forensics (mirror of the META fade)

**Date:** 2026-07-11 (revised 2026-07-11, same day, per Codex review — see "Correction"
section below) · **Author:** claude · **Type:** research forensic (read-only; no
production path written; isolated clone; local compute)
**Deliverable:** `doc/research/2026-07-11-zm-nflx-buy-bias-forensics.md`

## What was asked

Operator: the live model repeatedly recommends buying ZM and NFLX (ZM "bought" 07-07,
ZM+NFLX admitted 07-10) — find the root cause with the same four-layer rigor as the META
studies (#473/#475/#476), on the opposite side.

## Verdict (one paragraph, corrected framing — see "Correction" below)

Same attribution pattern as META, mirrored, presented as a **hypothesis, not a validated
root cause**: on an approximate replay, every ZM/NFLX admission in 4 weeks shows the STD
family dominating each name's replayed score (ex-STD SHAP both names negative on every
admission day, all three model vintages) — this is model-representation attribution, not
a counterfactual proof that either name would fail admission without STD (§4.0 of the
research doc). Produced by models that failed BULL_CALM regime-IC/monotonicity and
reached primary via operator override (06-21 and 07-06 models) or via a silent local-file
regression (05-18 model, 06-26..07-02). NFLX's recomputed dispersion features under the
(untrained, disabled) #44 v2 definitions move from 81st to 51st percentile — a fact about
recomputed feature values, not a remedy or trained-model rank result. ZM's recomputed
features barely move (72nd → 70th/86th pct) — descriptively consistent with genuinely
real dispersion, not a validated re-rank. ZM is also valuation-blind (ey/b2p never finite
→ #43); this document takes no position on what serving real ratios would do to its
score. No performance or exit-quality conclusion is drawn from the scoreboard: the only
realized outcome is one NFLX round trip (−$3.68, local exit-plane discrepancy); the rest
is 7 immature paper-cohort pick-days with no out-of-sample holdout, no cost/slippage
model, and no corporate-action handling. Street analyst targets were removed — not
evidence for a pipeline investigation.

## New engineering findings (beyond the META chain; local-state facts, see Correction)

1. **Local exit-plane state shows a stale-model disagreement at the sell decision** (a
   local-state finding, not a broker-truth claim beyond the fill prices): the fills
   themselves are broker-confirmed; `ModelProtectionExitTask` sold NFLX 24h after entry
   on `mu=-0.0505 strikes=3/3` from the stale holding re-score plane (per-ticker vintage
   `live_train_end=2026-04-23`, a verified log line) while an approximate REPLAY of the
   panel scores it +0.066 same-day (not a recorded score — NFLX was wash-blocked from
   panel admission that day); NFLX closed +2.8% above the sale price by 07-10.
2. **06-25 live-tree incident collateral — two LOCAL-STATE defects:** (a) prod panel
   artifact silently regressed 06-21→05-18 for 5 sessions (byte-verified via run-bundle
   shas + exact replay of the committed 05-18 artifact), unalerted, violating the 28d
   freshness policy — a local file/artifact-identity fact; (b) NFLX's local wash-sale
   stamp (written 06-25 after the loss sale) vanished from local live_state by 06-26 →
   the 07-10 NFLX buy submission went out 15 days into the 30d window with the internal
   gate blind (`blocked_wash=0`). **This is a ledger-integrity near-miss, not a
   broker-side wash-sale event**: the order was independently canceled before fill, so
   no actual re-entry occurred; confirming what a fill would have meant at the
   broker/tax level would require reconciliation not performed here.
3. **ZM was never actually bought** `[broker-confirmed — Alpaca orders/activities API]`
   — 5 broker orders, 0 fills (pre-open cancel gate + morning re-selection); the trades
   DB records intents only, no fill truth.

## Fix mapping (candidate follow-ups, none validated or ready — see Correction)

**No runtime gate, retrain, or strategy-flag change should follow from this document
until the preregistered, full-cross-section experiment (#476 §7) validates the
hypothesis.** Candidates already scoped by the existing stack: #44 v2 features (a
descriptive feature-value fact only — NFLX −30pp, FTNT −20..26pp, ZM unmoved — not a
trained-model result, since #44 ships the features disabled and untrained), F4 #479
override consequences, base-data #43 (ZM's ey/b2p, input-integrity only, no
score-direction claim), gated retrain. Independent local-engineering candidates (not
gated on the STD60 experiment, still unbuilt): exit/entry plane coherence + freshness
fail-close on protection mu (pipeline), durable broker-reconciled wash-sale ledger
(pipeline + orchestrator checker), model-identity regression tripwire (orchestrator
monitor), fill-truth in the runs DB (execution/pipeline).

## Correction 2026-07-11 (Codex review response)

Codex posted CHANGES_REQUESTED on orchestrator#484, with five findings:

1. **SHAP subtraction is not a counterfactual rescore.** The "ex-STD" score does not
   prove either name would fail the admission floor without an exact serving-path
   replay, a SHAP additivity-residual check, and a feature intervention preserving the
   remaining feature vector.
2. **The post-hoc `vol_trend_v2` recomputation cannot establish a trained-model rank
   result.** No trained v2 artifact, immutable training vintage, scoring config, or
   full-population OOS result exists (#44 ships v2 disabled behind an experiment-id
   gate).
3. **The ZM valuation-score-direction claim is unestablished.** The model's transform,
   imputation behavior, feature interactions, and retraining response to real
   fundamentals are unknown.
4. **Thin-sample performance/exit claims cannot diagnose a defect or rank a strategy.**
   One realized trade and a few immature paper cohorts need a stated population,
   horizon, cost/slippage treatment, corporate-action handling, and benchmark
   definition before any conclusion — and street analyst targets are not evidence for a
   pipeline investigation.
5. **Local-state facts must be separated from broker-truth claims.** A missing local
   wash-sale stamp supports a ledger-integrity incident, not a broker-side re-entry
   claim without broker reconciliation; likewise for the exit-plane and model-regression
   findings.

**What was corrected in `doc/research/2026-07-11-zm-nflx-buy-bias-forensics.md`:**

- Added new §4.0 stating explicitly what SHAP subtraction is and is not (no exact
  replay, no additivity-residual check, no feature intervention), and a
  replay-error-vs-admission-margin comparison computed from the document's own numbers
  (NFLX's disclosed ±0.02-0.05 replay noise is the same order of magnitude as its actual
  admission margin on two of three admission days). Reframed §4.1's title and closing
  claim from "decides the question" / "pure dispersion-credit picks" to "motivates the
  hypothesis" / "representationally STD-dominated on this replay."
- Removed the "#44 v2 features de-rank NFLX 30pp" remedy/rank framing throughout (§1
  item 2/3, §5.1, §8 item 1); kept only the descriptive fact that recomputed feature
  VALUES move percentile, with explicit notes that #44 ships v2 disabled/untrained and
  no trained artifact, vintage, scoring config, or OOS result exists.
- Removed the claim that recovering ZM's ey/b2p "would likely raise its score" (§1 item
  4, §5.2); replaced with an explicit statement that the model's transform/imputation/
  interaction/retraining response to real fundamentals is not established.
- Rewrote §3 (Scoreboard) to state population (2 names, 7 pick-days, 1 realized trade),
  pre-entry horizon (0-19 days, no matured 60d label), missing cost/slippage/
  corporate-action treatment, and the benchmark definition (SPY price return only) up
  front; states explicitly that no performance/exit-quality conclusion can be drawn.
  Removed the street analyst price-target citations (ZM ~$115, NFLX ~$113) entirely.
- Re-labeled §7.1 (exit-plane) and §7.2 (wash-sale/regression) findings throughout to
  separate verified LOCAL STATE facts (fills, log lines, snapshot contents, artifact
  shas) from claims that would require broker reconciliation not performed here;
  restated the wash-sale finding as a ledger-integrity near-miss (no actual re-entry
  occurred, since the order was independently canceled) rather than a broker-side
  wash-sale claim.
- Reframed §8 (fix mapping) with an explicit top-level statement that no runtime gate,
  retrain, or strategy-flag change should follow before the preregistered experiment;
  relabeled the section "candidate fix mapping (NOT a validated or ready-to-build
  list)."
- Rewrote §9 "Known Limitations" into an itemized (a)-(f) mapping against each of
  Codex's five points, matching the #475/#476 convention, plus the carried-over
  pre-existing limitations.
- Updated the PR title/body to match (verdict language, "New engineering findings," and
  "Fix mapping" sections reframed as hypotheses/candidates, not validated conclusions).

## Method / evidence

- Facts: runs DB (candidate_scores/trades/ticker_daily_state/live_state_snapshots,
  copied before opening) + Alpaca orders/activities (read-only GET) + daily/intraday logs.
- Attribution: #475's sealed reproduction method; July days read from the already-sealed
  renquant-artifacts #18 bundle (ZM byte-exact, diff 0.000000); June days replayed
  against the byte-verified 06-21 backup (corr 0.95-0.97, disclosed); regression window
  replayed against the committed 05-18 artifact (ZM/FTNT exact).
- Honest view: v2 features computed with the merged renquant-model #44 module verbatim
  (descriptive feature-value recomputation only, per the Correction above); trend-share
  decomposition; live fundamentals feed finiteness. A WebSearch for street consensus
  price targets was made in the original pass; the citation was removed from the
  research doc per Codex point 4 (not evidence for a pipeline investigation).

## Constraints honored

Read-only on all production paths; no git in the live umbrella tree or any primary
checkout (fresh isolated clone); local compute only; PR left for Codex review — not
self-merged.
