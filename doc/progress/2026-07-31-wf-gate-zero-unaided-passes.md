# WF-gate unaided-pass evidence — RELOCATED to renquant-backtesting#91   (pointer)

STATUS:    relocated. This file carries no evidence, no number and no test.
WHAT:      The finding, its frozen census and its tests live in
           **renquant-backtesting#91** (`goal6/wf-gate-zero-unaided-passes`).
WHY/DIR:   Codex on orch#670: `renquant-backtesting` owns the WF gate, the
           candidate-versus-recipe admission semantics, and the referenced
           artifacts. The orchestrator should CONSUME a gate verdict or a
           surfaced run-bundle field, not become a second frozen-data and test
           authority for backtesting behaviour. Agreed — a finding about the
           gate belongs to the gate's owner, or the two repos drift into
           disagreeing about what the gate did.
EVIDENCE:  none here, by design. See renquant-backtesting#91.
NEXT:      Review the finding on renquant-backtesting#91.

## Why this is merged rather than closed

A closed PR is easy to miss. A merged one-file pointer is a permanent, greppable
record in this repo's own history, so anyone reading `doc/progress/` later can
follow it straight to the evidence. That is the pattern this programme has used
three times before (capacity-power-memo → renquant-model#69, factorial-HFR →
model#67, breadth-precision → model#98).

## Why this file states no numbers — demonstrated, not asserted

An earlier revision kept a short "the finding itself, for the reader who lands here
first" section restating the headline. Codex asked for it to go, and **the reason
proved itself within one review cycle**: that section said *"11 artifacts, 2 with
`passed=True`"*. Reviewing the census provenance on #91 showed the stated inclusion
query matches **29** artifacts, of which **18** pass — the 11 were a *deployed +
staging* subset whose choice had never been written down.

> **A pointer that restates a conclusion is a second source of truth, and it began
> rotting before the PR it points at had even been merged.** The numbers, their
> provenance and their tests live in one place. Nothing may be cited from this file.
