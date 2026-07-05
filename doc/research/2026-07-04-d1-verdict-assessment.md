# D1 First Definitive WF-Gate Verdict — Assessment

DATE: 2026-07-04
STATUS: VERIFIED (extracted from existing production gate metadata) — REVISED to
separate model-quality diagnostics from the currently enforced verdict; see
"Round 2 (Codex review)" below.
TAGS: D1, S1-S3, WF gate, regime IC, verdict

## Bottom line

**D1's currently-enforced verdict is FALSE because a required gate was skipped on
this run — not because the model was judged and rejected.** The regime-level IC
diagnostic (same artifact, same run) separately shows the production model likely
has genuine quality problems in BULL_CALM/CHOPPY, but that diagnostic comes from a
`diagnostic_only` run and has never been combined with a clean, non-skipped gate
pass/fail. We do not yet have a single run that tells us definitively whether D1
is gate-blocked, model-blocked, or both. See Layers 1–3 below.

## Source

Extracted from WF gate metadata on the active production model artifact:
`panel-ltr.alpha158_fund.json` (XGB, trained 2026-06-21, re-promoted 2026-06-23).

## Layer 1 — Regime-level model-quality diagnostics

This is what the regime-conditional genuine-IC breakdown shows on this artifact,
independent of gate enforcement:

| Regime | Mean IC | Placebo IC | Genuine IC | n | Pass? |
|--------|---------|------------|------------|---|-------|
| BEAR | 0.335 | 0.088 | 0.247 | ≥30 | PASS |
| BULL_CALM | 0.023 | 0.006 | 0.017 | ≥30 | **FAIL (< 0.02)** |
| BULL_VOLATILE | 0.025 | 0.010 | 0.015 | 19 | Ineligible (n < 30) |
| CHOPPY | 0.026 | 0.024 | 0.002 | ≥30 | **FAIL (≈ 0)** |

- BULL_CALM is ~78% of trading time — this is the dominant regime, and genuine IC
  there (0.017) sits just under the 0.02 bar.
- CHOPPY genuine IC (0.002) is effectively zero — the raw signal in this regime is
  indistinguishable from its own placebo.
- Pooled (non-regime-conditional) S3 genuine IC = 0.0415, which clears the 0.02 bar
  as a shadow computation — the regime split is what surfaces the BULL_CALM/CHOPPY
  weakness that the pooled number hides.

**This diagnostic is real and worth taking seriously as evidence of model quality**
— but per Layer 2/3 below, it comes from a run whose gate metadata is stamped
`diagnostic_only: true`, so it is not yet paired with a clean acceptance-grade
gate verdict.

## Layer 2 — Currently enforced gate verdict

- Gate version: v2 (absolute ceiling)
- `overall passed` (raw computation): `True`
- `diagnostic_only`: `True`
- **Gate verdict without override: `False`**
- Reason: `skipped_required_gates=[trade_monotonicity_pass_open_allowed]`

Reading `renquant-backtesting`'s `wf_gate/runner.py::_compute_overall_pass()`
directly: this function returns `False` unconditionally whenever
`skipped_required_gates` is non-empty, **regardless of the underlying WF/sanity/
regime results** — its own docstring states "a skipped WF, sanity battery, trade
gate, config parity check, or trace cannot be promoted as acceptance evidence."
`trade_monotonicity_pass_open_allowed` appears in that list specifically because
this run was invoked with the `--allow-pass-open-trade-monotonicity` emergency
override flag, which the gate code treats as disqualifying for acceptance
purposes — independent of, and unrelated to, the regime-level IC numbers in
Layer 1.

So: **the proximate cause of today's `False` verdict is a run-configuration
choice (an emergency skip flag was set), not the regime-level IC result.**

## Layer 3 — Entanglement assessment

Is the current D1 failure still entangled with configuration/skipped-gate policy,
or is it cleanly isolated to model quality? **It is still entangled.** Because
`_compute_overall_pass()` short-circuits to `False` the moment any required gate
is skipped, this artifact's metadata cannot tell us what the trade-monotonicity
gate itself would have concluded on its own merits, nor can it certify that the
Layer 1 regime-level numbers were computed under acceptance-grade (non-diagnostic)
conditions. Two things would both need to be true before "model-blocked, not
gate-blocked" becomes a safe claim:

1. A rerun without the `--allow-pass-open-trade-monotonicity` skip flag (and
   without any other required-gate skip) produces a genuine, non-`diagnostic_only`
   verdict — i.e., the trade-monotonicity gate and every other required check
   pass on their own merits.
2. That clean rerun's regime-level genuine IC still fails in BULL_CALM/CHOPPY the
   same way this diagnostic run's did.

Until (1) is done, we know the CURRENT enforced verdict is `False` for a
configuration reason, and we have a *separate*, suggestive-but-not-yet-paired
diagnostic pointing at real model-quality weakness. We do not have a single
clean run that lets us say "the gate would pass if not for the model."

## Walk-Forward Performance (3 cuts, 27 months)

(From the same diagnostic-only artifact — informational, not an acceptance result.)

| Cut | Sharpe | APY | SPY Sharpe | SPY APY | Beat SPY? |
|-----|--------|-----|------------|---------|-----------|
| 2024-01 → 2024-12 | 0.972 | 11.7% | 1.778 | 20.5% | No |
| 2024-07 → 2025-06 | 0.943 | 8.1% | 0.715 | 6.1% | Yes |
| 2025-04 → 2026-03 | 0.177 | 1.3% | 0.749 | 5.0% | No |

- 3/3 positive Sharpe (barely — 0.177 in latest cut)
- 1/3 beat SPY Sharpe
- 0/3 beat SPY APY
- Structural underperformance: declining Sharpe trajectory (0.97 → 0.94 → 0.18)

### Sanity Battery

| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Shuffled-label IC | −0.00039 | < 0.005 | PASS |
| Placebo/Real ratio | 0.453 | < 0.5 | PASS (barely) |
| S3 genuine IC | 0.0415 | > 0.02 | PASS (shadow) |

## Implications

1. **The gate machinery is producing internally consistent numbers.** S1-S3
   repairs are landed, and the placebo-clean difference test (S3 shadow)
   correctly separates BULL_CALM/CHOPPY weakness from the healthier pooled and
   BEAR-regime numbers.

2. **D1's current `False` verdict is a configuration artifact of this specific
   run (a skipped required gate), not yet a clean model-quality verdict.** The
   Layer 1 regime-level diagnostic is real evidence the model likely has a
   genuine problem, but it has not yet been produced under acceptance-grade
   (non-`diagnostic_only`) conditions.

3. **S3 v3 promotion remains valuable independent of this finding** — replacing
   the v2 absolute-ceiling gate (which has the structural +0.04 embargo floor
   problem) with the v3 placebo difference test would make the gate more honest.
   It does not, by itself, resolve the Layer 2/3 entanglement above — that needs
   a clean rerun without the skip flag.

4. **Next steps:**
   - Rerun the WF gate on this artifact WITHOUT `--allow-pass-open-trade-monotonicity`
     (and confirm no other required gate is skipped) to get a genuine,
     non-diagnostic verdict — this is the prerequisite for knowing whether D1 is
     gate-blocked, model-blocked, or both.
   - If that clean run still fails only on regime-level IC, THEN "D1 needs a model
     retrain demonstrating genuine BULL_CALM IC > 0.02" becomes the accurate
     next step — but that is conditional on step 1, not yet established.
   - Consider whether the CHOPPY genuine IC ≈ 0 should inform trading policy
     (fail-close in CHOPPY regimes vs continuing with a no-edge model),
     independent of the D1 gate question.

5. **This is consistent with the existing evidence base:**
   - Win rate is backtest not live (memory)
   - Canonical price-trend has no stable multi-day edge (memory)
   - The contrarian XGB picks (OXY forensics) carry this trust problem

## Cross-references

- S1-S3 gate repair: backtesting PRs #48-#51, #57-#58, #61, #64
- `renquant-backtesting/src/renquant_backtesting/wf_gate/runner.py::_compute_overall_pass`
  and `_required_validation_skip_reasons` — the skip-disqualifies-acceptance logic
  cited in Layer 2/3 above
- WF-gate embargo leakage floor: ~+0.04 shuffled-label floor (memory)
- WF-promote chronic reject: config tangle, not one root cause (memory)

## Round 2 (Codex review)

Codex held this memo: the original "D1 is MODEL-BLOCKED, not gate-blocked"
headline collapsed two distinct facts — (1) the regime-level IC diagnostic
(real, suggestive of model quality issues) and (2) the currently enforced verdict
being `False` solely because `trade_monotonicity_pass_open_allowed` was skipped
(a run-configuration fact, unrelated to regime IC). Restructured the memo into
three explicit layers (model-quality diagnostics / currently enforced verdict /
entanglement assessment), traced the actual gate logic
(`_compute_overall_pass`/`_required_validation_skip_reasons` in
`renquant-backtesting`) to confirm the skip genuinely short-circuits the verdict
independent of the regime results, and rewrote the bottom line + implications to
state the honest, still-entangled conclusion: we don't yet have a clean run that
isolates D1's failure to model quality alone.
