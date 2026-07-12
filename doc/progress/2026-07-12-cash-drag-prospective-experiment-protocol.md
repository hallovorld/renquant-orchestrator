# Cash-drag prospective experiment protocol

**Date:** 2026-07-12

## What changed

Added a design-only protocol for a valid 104 sizing-fidelity experiment and the
missing 105 pre-quantization measurement contract. No runtime code, strategy
configuration, broker behavior, scheduler, pin, or deployment record changed.

## Evidence basis

- The 2026-07-09 sweep audit establishes that the concentration sweep was
  non-decision-grade for production: it changed a Kelly cap while evaluating a
  QP/XGB system unlike the greedy-Kelly/PatchTST production path.
- The 2026-07-11 sealed floor replay supports a sizing-artifact hypothesis but is
  explicitly retrospective and therefore insufficient for enablement.
- The existing 105 scorecard states that `target_notional` and true pre-quantization
  zero drops are unavailable; the new protocol preserves that boundary rather than
  inferring missing data.

## Design result

The proposed 104 shadow uses identical production-mirror inputs in both arms and
permits one field difference only: `sizing.one_share_floor_enabled`. It separates:

- deterministic sizing-fidelity and safety claims;
- future virtual economic marks under a precommitted cost bound; and
- any later capital-risk decision.

It requires the pipeline-owned ledger and a verified orchestration evidence bundle
before a shadow run, and makes a live configuration change a later, separate decision.

## Verification

Documentation-only change. `git diff --check` is the applicable mechanical check.
