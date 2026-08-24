# LONG-ledger row 2b — one-time authority for the slot-cap raise (strategy-104#100)

STATUS: ledger-only PR. Adds row 2b to `doc/memory/long-term-agreements.md`,
following the row-2a precedent (orch#883) exactly: production-config writes are
read-only under row 2; each exception is a narrow, single-use, PR-named row
that must land on orchestrator `main` BEFORE the config PR merges.

## 1. The decision being recorded

Operator decision 2026-08-24, verbatim **"同意"**, in direct response to:
"同意的话，我按文档里写好的精确改动开 strategy-104 PR 走 codex" — the exact
change being orch#1046 §AC4 (`max_concurrent_positions: 8 → 10` +
`execution.fractional_shares.enabled: false → true`).

Row 2b authorises ONLY the slot-cap half, for exactly
**renquant-strategy-104#100**: `max_concurrent_positions` 8→10 in the active
config, golden twin, and the six prod-mirror lanes, plus the
`_max_concurrent_positions_reason` provenance note in active+golden (the key is
named explicitly because in the 2a round an unnamed `_reason` key voided an
approval).

## 2. Why the fractional half is withheld (§4b)

- `fractional_capability_gate` (umbrella
  `backtesting/renquant_104/adapters/commit_contract.py:190`) requires, flag-ON:
  (a) broker adapter exposes `is_fractionable` + a no-submit classifier;
  (b) `software_stops_armed(...) is True`.
- (a) FAILS: zero `def is_fractionable` implementations in the live umbrella
  [VERIFIED 2026-08-24 — `grep -rn` across the tree]; the active path's broker
  is umbrella `live/alpaca_broker.py`, not the dev renquant-execution checkout.
- (b) FAILS: `execution.software_stops.enabled=false` in the same config;
  stage-3 arming has its own contract with MISSING items (liveness pager never
  fired to the real topic — `doc/research/2026-07-11-enablement-evidence-floor-stops-fractional.md` §3.4 gap table).
- Consequence, by the gate's design (`adapters/runner.py:1110`): enabling the
  flag today logs `S-FRAC capability gate FAILED … ALL BUY emission
  fail-closes this bar` — every buy blocked, strictly worse than status quo.
  This is the exact "flag landed ahead of its dependencies" failure mode the
  gate was built for.
- The flip therefore waits for its dependency chain (umbrella broker-adapter
  contract PR; stage-3 arming per its own packet) and its own ledger row.

## 3. Evidence for the raise itself

orch#1025 grid + orch#1046 closeout: the cap is the binding deployment
constraint (20–27 admissible names vs 0–2 free slots on measured sessions);
replaying 350 held sessions through the production sizing seam,
cap 10 lifts capital deployment **17.3% → 32.6%** [VERIFIED — orch#1025
artifact]; saturation ~15. The strategy-104 test that pinned 8 was updated in
#100 to pin 10, keeping its docstring history (the 06-29 "10/4 is weak"
measurement predates the 08-04/08-06 config era that made the slot cap
binding).

## 4. Countersignature status

As in row 2a: Claude shares the `hallovorld` login, so no Claude comment can
countersign. Unlike 2a, the directive was received in a Claude session, so
Codex cannot attest first-hand receipt. The row is validated by Codex review of
this PR against the evidence chain (orch#1046, under Codex review in
parallel); the operator can add first-hand confirmation in either PR thread or
a Codex session if Codex requires it.

## 5. Merge order

1. This PR (row 2b) → orchestrator `main`.
2. renquant-strategy-104#100 (the config change).
3. Umbrella pin advance + runtime sync (merged-is-not-deployed).
