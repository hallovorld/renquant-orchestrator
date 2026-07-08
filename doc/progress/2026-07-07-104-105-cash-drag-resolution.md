# 2026-07-07 — Design: resolve 104/105 cash drag

**PR**: design RFC (docs only, no behavior change)

## What

Evidence-first execution plan for cash-drag remediation across 104 and 105.
Corrective review result: the plan is now explicitly multi-repo. Orchestrator owns
parking-sleeve shadow/runtime plumbing; Lane A policy/runtime changes stay in
`renquant-strategy-104` + `renquant-pipeline`; fractional shares are demoted from
"mandatory first phase" to an optional later track if A-3 + sleeve evidence still
shows material sizing-fidelity loss.

## Why

104 runs 54-76% cash. The measured binding constraint is whole-share
quantization on high-price names (BLK/AVGO/GS blocked at $0), but the merged
07-07 design draft overreached in two ways: it treated fractional shares as the
default first implementation phase, and it put new implementation back onto the
umbrella path despite the current multi-repo operating model. This correction
keeps the evidence but fixes the ownership and sequencing contract.

## Key decisions

1. `renquant-orchestrator#423` is in the right repo: sleeve shadow/runtime wiring is
   orchestration + provenance work
2. Lane A remains separate A-1 / A-2 / A-3 work in `renquant-strategy-104` and
   `renquant-pipeline`; the concentration sweep does not replace it
3. Fractional shares require a fresh active-path justification after A-3 + sleeve
   evidence, not an automatic Phase-1 slot
4. 105 remains compatibility + instrumentation only (no live deployment)
