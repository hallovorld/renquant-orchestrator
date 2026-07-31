# WF-gate unaided-pass evidence — RELOCATED to renquant-backtesting   (pointer)

STATUS:    relocated. This PR carries no evidence and no test of its own.
WHAT:      The finding, its frozen CSV and its 5 tests now live in
           **renquant-backtesting#91**
           (`goal6/wf-gate-zero-unaided-passes`).
WHY/DIR:   Codex on orch#670: `renquant-backtesting` owns the WF gate, the
           candidate-versus-recipe admission semantics, and the referenced
           artifacts. The orchestrator should CONSUME a gate verdict or a
           surfaced run-bundle field, not become a second frozen-data and test
           authority for backtesting behaviour. Agreed — a finding about the
           gate belongs to the gate's owner, or the two repos drift into
           disagreeing about what the gate did.
EVIDENCE:  n/a — this PR makes no claim of its own any more. Every number now
           sits in renquant-backtesting#91 with its CSV.
NEXT:      Review the finding on renquant-backtesting#91.

## Why this is merged rather than closed

A closed PR is easy to miss. A merged one-file pointer is a permanent, greppable
record in this repo's own history, so anyone reading `doc/progress/` later can
follow it straight to the evidence. That is the pattern this programme has used
three times before (capacity-power-memo → renquant-model#69, factorial-HFR →
model#67, breadth-precision → model#98).

## The finding itself, for the reader who lands here first

Across every `panel-ltr.alpha158_fund` artifact carrying `wf_gate_metadata`:
**11 artifacts, 2 with `passed=True`, both operator overrides, ZERO unaided
passes.** The model trading the live book today was **not admitted by the gate** —
an operator override dated 2026-06-22 admitted it over its own sanity battery's
`FAIL`.

Stated here because it is decision-relevant and a pointer nobody reads is not much
better than a closed PR. The numbers, their provenance and their tests are in
renquant-backtesting#91; nothing above may be cited from this file.
