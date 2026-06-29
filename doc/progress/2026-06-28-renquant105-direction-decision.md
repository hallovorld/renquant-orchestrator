# renquant105 direction decision — progress

2026-06-28.

## STATUS
DECISION RECORD doc opened for Codex + operator discussion. The operator
delegated the directional call to me; this PR is the discussion vehicle. No code,
no scans, no orders, no git in the live tree, no canonical writes — the §1
evidence was produced by already-shipped read-only scans (referenced, not
re-run here).

## WHAT
- `doc/design/2026-06-28-renquant105-direction-decision.md` — the decision
  record: §1 the rigorous finding (directional cross-sectional alpha exhausted on
  current inputs, with numbers), §2 the two-track decision, §3 why (honest), §4
  the proposed first step, §5 references.

## WHY
The original 105 goal — "catch more / more-accurate trends" — requires a
directional edge. This session's rigorous read-only diagnostics establish there
is no usable directional cross-sectional edge on the current 134-large-cap
universe + current data. The binding constraint is the INPUTS, not validation or
model architecture. So the decision pivots: do the immediate non-directional
thing now (Track A), and flag the real directional path (Track B = input change)
as the operator's call.

## KEY FINDINGS (§1, this session, read-only, proper OOS/CI/placebo)
- **A1** existing model: genuine (leak-controlled) IC CI includes 0; not
  leak-free (predictor-side persistence inflates naive IC); skill is entirely a
  ~10% BEAR-slice artifact; BULL_CALM (~79% of live time) genuine IC ≈ −0.003
  (coin flip); tradable net Sharpe ≈ 0. (The live-ledger diagnostic's own verdict
  is UNDETERMINED on ≈1 overlap-ratio — it can't prove skill either.)
- **A2** ML combination (Gu–Kelly–Xiu, sector+beta neutral, walk-forward, 1002
  OOS dates): every combo dominated by single momentum, itself a recent-bull
  artifact (null full-sample); no multi-factor synergy.
- **Single factors:** price-trend (5 canonical, no robust 20/60d edge; mom_12_1
  clears floor only at h=5; h20 IC 0.74×), regime-momentum (NO — flip survives
  inside UP-trend), fundamentals (value wrong-sign & soft, quality/growth null),
  PEAD/minute (null or net-negative under faithful costs).
- **BEAR/short audit:** NOT a short edge — V-recovery LONG-ranking
  (config-forbidden), short leg net-negative, effective N≈6, bootstrap CI
  includes 0, 盘中 adds nothing.
- **Binding constraint = DATA + UNIVERSE.** Large-cap cross-sectional anomalies
  are documented weak; our null is consistent. More validation / fancier model
  won't change a coin-flip primary on these inputs.

## THE DECISION (two-track)
- **Track A (immediate, no new inputs):** meta-label entry filter (López de
  Prado) to improve the EXISTING book's expectancy. HONEST CAVEAT: meta-labeling
  improves precision of acting on a primary signal — it CANNOT manufacture edge
  from a coin-flip primary; so step 1 is to confirm a *conditional* signal worth
  filtering exists, else Track A is also null and we say so. Secondary levers:
  vol/risk-timing (minute data verified to improve vol estimation), execution/cost.
- **Track B (operator-level; FLAG, don't start):** change an input — broaden /
  down-cap the universe (anomalies strong in small/mid-cap) OR acquire new data
  (#205 revision-history snapshotter, alt-data). Months-long, conflicts with the
  large-cap liquidity design → explicitly the operator's call.

## HONEST FRAMING
Track A = "lose less / size better / enter better", NOT new alpha. Only Track B
creates directional edge that isn't there today. Do not mistake A for solving the
directional problem. The §1 diagnostics are current-watchlist / survivorship-biased
read-only reads → "no robust edge surfaced under this diagnostic," not a universal
proof — but they agree, and the inputs are the documented reason.

## ASK (for Codex)
Challenge the decision: is Track A worth it given the coin-flip primary? Is Track B
(input change) the honest answer? Is the conditional-pick-quality step 1 the right
gate before building any filter?

## NOT DONE / OUT OF SCOPE
No new scan, no retraining, no order, no live-tree mutation, no self-merge. No
CPCV/FWER/DSR framework — a decision record, not a research cathedral. Track A
step 1 and Track B are NOT started under this PR.
