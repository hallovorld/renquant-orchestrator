# Gate threshold calibration diagnostic

**Date:** 2026-07-04
**Status:** ready for review

## What

Read-only diagnostic that answers: are the conviction/rotation thresholds
achievable given the model's actual output distribution?

When thresholds sit ABOVE the model's max achievable mu/er, "no trade" is a
structural artifact of mis-scaled gates, not a genuine "nothing good" verdict.
This tool quantifies the gap and classifies each gate as PASS / MARGINAL /
STRUCTURAL_BLOCK.

## Changes

1. **`gate_calibration_diagnostic.py`** — core diagnostic module:
   - Reads `candidate_scores` from score_db (read-only)
   - Extracts gate thresholds from strategy_config.json or explicit CLI args
   - Per-gate: computes clearance rate (% of runs where at least 1 candidate
     clears), score distribution percentiles, and a verdict
   - Verdict classification: STRUCTURAL_BLOCK (<=10% clearance),
     MARGINAL (<=50%), PASS (>50%)
   - Text and JSON output, non-zero exit codes for block/marginal

2. **CLI**: `rq gate-calibration` subcommand (pass-through to module)

3. **20 tests** covering: normal pass, structural block, marginal, empty data,
   below-direction gates, multiple gates (worst wins), config extraction,
   rendering, CLI smoke tests with exit codes.

## Why

The 104 decision-tree forensics repeatedly found that "no trade" was caused by
conviction mu_floor or rotation initiate_threshold sitting above the model's
compressed score range — a calibration problem, not a signal problem. This
diagnostic makes that check mechanical and repeatable.

## Guardrails

- Strictly read-only: never modifies score_db, strategy config, or any artifact
- Does not recommend threshold changes — reports the gap for operator decision
