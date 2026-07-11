# Progress — STD60 rule provenance (deepest-layer root cause of the META fade)

- **Date:** 2026-07-11
- **Scope:** research only — adjudicate where the live XGB's low-STD60→bearish rule came
  from in the training data and whether it was ever valid OOS. Follow-up to #475
  (META score attribution). No code, no config, no gate changes.
- **Deliverable:** `doc/research/2026-07-11-std60-rule-provenance.md`.

## What was done

- Established the live booster's exact training window from the artifact + corpus
  (row-count match): full-panel fit, 2016-01-04 → 2026-04-08, label = CS-z of fwd-60d
  excess vs SPY.
- Adjudicated four hypotheses with per-date cross-sectional analysis of the actual
  training corpus + OHLCV-recomputed raw labels + HMM regime labels, plus the artifact's
  own WF-gate record:
  - **H1 class confusion: REFUTED** (low-STD60 is 66% uptrend names, and the
    uptrend/near-high subset had the *worst* in-corpus forward returns — the corpus
    genuinely taught "fade calm-at-highs"). Surviving kernel: survivorship bias
    (0 delisted names; 42% of high-STD60 rows from eventual ≥5x survivors).
  - **H2 regime generalization: SURVIVES (primary).** Rule pays only in
    BEAR/BULL_VOLATILE/rebound years (2020 +0.213, 2023 +0.117, 2025 +0.122); dead
    2021/2022/2024; BULL_CALM 2026 in-corpus IC −0.088 (hit 0.15); post-corpus OOS:
    paid in the Apr-May rebound (+0.128 fwd-20 IC), inverted in the June melt-up
    (−0.019, truncated).
  - **H3 feature mis-specification: SURVIVES (mechanism).** META fade week: 101% of the
    STD60 decline is the price denominator; returns-vol rose +4.8% and stayed above the
    panel mean; FTNT's top rank is 92% trend component.
  - **H4 governance: SURVIVES (terminal link).** The live booster failed its own gate on
    exactly this failure mode (BULL_CALM regime-IC FAIL, monotonicity inverted −13.7pp)
    and reached primary via the 2026-07-06 freshness `manual_override`.
- Settled the operator's literal question: **no short position/order/intent on META ever**
  (ledger actions are buy/sell only; `long_short.enabled=false`; book = MU/GRMN/AVGO).
- Fix menu with owners/effort (F1 returns-vol feature, F2 trend-interaction features,
  F3 per-feature regime screen at training, F4 regime-scoped override consequences on the
  #467 weekly rail, F5 survivorship remediation, F6 ledger cohort tracking).

## Method / safety

- READ-ONLY on all production paths (runs DB opened `mode=ro`; corpus/OHLCV/artifacts read
  only). No git in the live umbrella tree or primary checkouts; authored in an isolated
  orchestrator worktree. Local compute only (no Modal).
- Statistics: overlap-adjusted t-stats (n_eff = n_dates/horizon); Spearman/quintile results
  invariant to the corpus's z transforms; raw economics recomputed from OHLCV.

## Memory-tier touch

- SHORT/MID: this doc is the durable record; key correction to prior working assumption —
  the low-STD60 rule is NOT class confusion (H1 refuted), it is a regime-conditional
  pattern learned unconditionally from a survivor-only corpus through a mis-specified
  feature, shipped through the freshness-override path the gate had already failed.

## Next

- Operator/Codex review of the fix menu; F4 (#467 rail consequence wiring) is the
  immediate governance patch; F1+F2 ride the next retrain cycle behind the standard gate.
