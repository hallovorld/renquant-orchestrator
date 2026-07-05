# D1 verdict assessment — gate works, model diagnostic suggests weakness, but verdict still entangled with a skipped gate

DATE: 2026-07-04

## What

Extracted D1 WF-gate verdict from the existing production model metadata.
S1-S3 gate code confirmed ALL MERGED in backtesting (PRs #48-#64).

## Finding

The memo originally claimed "D1 is model-blocked, not gate-blocked" — Codex
correctly flagged this as collapsing two separate facts. Restructured into three
layers:

- **Layer 1 (model-quality diagnostic)**: BULL_CALM genuine IC = 0.017 (< 0.02
  bar, ~78% of trading time), CHOPPY genuine IC = 0.002 (≈ placebo), BEAR genuine
  IC = 0.247 (strong but rare), pooled S3 genuine IC = 0.0415 (PASS as shadow).
- **Layer 2 (currently enforced verdict)**: `False`, solely because
  `skipped_required_gates=[trade_monotonicity_pass_open_allowed]` — traced to
  `renquant-backtesting/wf_gate/runner.py::_compute_overall_pass()`, which
  short-circuits to `False` whenever any required gate is skipped, regardless of
  the underlying WF/sanity/regime results. This run used the
  `--allow-pass-open-trade-monotonicity` emergency flag.
- **Layer 3 (entanglement)**: still entangled — we don't have a clean,
  non-`diagnostic_only` rerun that isolates D1's failure to model quality alone.
  The Layer 1 diagnostic is real and suggestive, but hasn't been paired with a
  genuine acceptance-grade verdict yet.

## Impact

D1 clearance needs, in order: (1) a rerun without the skip flag to get a genuine
verdict, then (2) if that clean run still fails on regime IC, a model retrain
demonstrating genuine BULL_CALM IC > 0.02. Step 2 was being treated as already
established; it is conditional on step 1, which hasn't happened yet.

## Round 2 (Codex review)

Codex blocked the original memo for internal inconsistency between the headline
and the body's own `skipped_required_gates` finding. Fixed by separating the
three layers explicitly in the research doc and rewriting the bottom line to
state the honest, still-entangled conclusion rather than the overstated
"model-blocked, not gate-blocked" claim.
