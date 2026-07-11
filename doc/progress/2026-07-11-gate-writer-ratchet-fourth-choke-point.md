# Gate-writer census ratchet: bump to 4 (task_data_availability.py)

**Status:** done. **Author:** claude, 2026-07-11.

## What happened

`renquant-pipeline#187` (DataAvailabilityGateTask, merged 2026-07-11) added
`task_data_availability.py::enforce_buy_block()`, which writes
`ctx.buy_blocked = True` directly. That made it a 4th file in
`renquant-pipeline/src` writing `buy_blocked` directly, tripping this repo's
`tests/test_census_ratchet.py::test_gate_writer_ratchet` — a cross-repo AST
census (`renquant_orchestrator.engineering_census`) that enforces
`scripts/engineering/census_ratchet.json`'s `max_buy_blocked_writers` (3
before this PR), designed to only shrink as gates migrate to the
`GateRegistry`.

Caught by the standing PR-review sweep: `orchestrator#475`'s CI failed with
`gate writers grew: census=4 > ratchet=3` after main advanced to include
`#187`.

## Why this is a legitimate 4th choke point, not a regression

The ratchet's own doc calls the floor of 3 "the designated job-boundary
choke points (one per pipeline with gates)". `enforce_buy_block()` runs
strictly AFTER the sell/exit pass and BEFORE the buy-candidate scan — a
pipeline phase none of the other 3 choke points (`job_gates.BuyGatesJob`,
`job_panel_scoring.py`, `panel_scoring.PanelScoringJob`) occupy; they all
run earlier in `InferencePipeline`. That ordering is the entire point of
#187's P1 safety fix (Codex review: a data-availability block must never
suppress a risk-reducing sell/exit). It is therefore impossible to fold
`enforce_buy_block()` into an existing choke point without reintroducing
the exact bug #187 fixed.

## Fix (two coordinated PRs)

- `renquant-pipeline#189`: `enforce_buy_block()` now also dual-writes the
  `GateRegistry` (`ctx_registry(ctx).submit(gate="data_availability",
  scope="book", verdict="block", ...)`), matching the pattern the other 3
  choke points already use — additive/shadow (decision-ledger feed only;
  the direct `ctx.buy_blocked` write remains the sole thing that actually
  gates buys today). Two new tests: submission on block, no phantom
  submission on a clean pass.
- This PR (orchestrator): bumped `census_ratchet.json`'s
  `max_buy_blocked_writers` and `floor` from 3 → 4, with a
  `breakdown_at_last_update` entry documenting the above rationale. Also
  updated `test_census_ratchet.py::test_ratchet_file_well_formed`'s
  hardcoded `floor == 3` assertion (a second place the old value was
  pinned).

## Verification

Ran the actual AST census against the real local sibling checkout
(`/Users/renhao/git/github/renquant-pipeline`, post-#187): count = 4,
listing all four files including `task_data_availability.py` at its actual
write line. Temporarily applied both edited files to the real
`renquant-orchestrator` checkout (verified clean first, reverted after) and
ran `CENSUS_ENFORCE=1 pytest tests/test_census_ratchet.py`: 2 passed.
Isolated-worktree testing alone can't validate this (the test hard-requires
true sibling directory layout via `ROOT.parent`), hence the temporary
real-checkout verification — no commits made there, files reverted via
`git checkout --`.

Links: pipeline#187 (introduced the 4th writer), pipeline#189 (registry
dual-write), this PR (ratchet bump).
