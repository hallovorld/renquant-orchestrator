# AC6 R4 — the contract it was going to extend had never run

**Bottom line.** AC6 R4 planned to add an override-provenance field to
`renquant_common.LiveRunBundle` and validate the daily run bundle against it. Two
measurements say that sequencing was wrong, and one of them says following it as
written would have **fail-closed every daily run**.

## What was measured `[本次实测 2026-07-31]`

**1. The contract has zero production callers.** Every reference to
`validate_live_run_bundle` in every repo is a test file:

| repo | `src/` files referencing `LiveRunBundle` | tests |
|---|---:|---:|
| `renquant-orchestrator` | **0** | 3 |
| `renquant-common` | 3 (the definition + two re-exports) | 2 |

orch#564's *Current state* says the schema "is wired into `renquant-orchestrator`'s
native/bridge live-bundle path." It is not wired into any runtime path. (The design
doc `2026-07-20-ac6-gate-design-rule.md:103` is more careful and says so.)

**2. Real daily bundles do not satisfy it — and are one field away.**
Seven real `run_bundle.json` files from `.subrepo_runs/`:

```
as written           PASS 0 / 7      all seven: `source` Field required
after adding `source`  PASS 7 / 7    nothing else missing
```

`schema_version` is already `1`; `state_mutations` is absent but the contract's
"at least one state source" clause is satisfied by `execution_audit` /
`submitted_orders`, both non-empty. **The entire distance between the daily bundle
and the shared contract is one string key.**

> So R4's hard question — *"which bundle does the override-provenance field belong
> on?"* — was premature. The daily bundle can satisfy `LiveRunBundle` **today**.
> And wiring the validator first, as R4 proposed, would have failed 7/7.

## What landed

1. `PersistDailyRunBundleTask` emits `"source": "daily_run_bundle"`.
2. `_record_bundle_contract()` validates the bundle and writes the verdict into
   both the bundle (`contract_validation`) and `stage_trace`.

**It records; it does not raise — and that is not a fail-open default.** The bundle
is written *after* decisions are made and orders submitted; it is the **receipt** of
a run that already happened. Aborting because the receipt is malformed would convert
a documentation defect into a no-trade day, a failure this repo has already paid for.
The check is made binding where being binding is safe: the **test suite asserts a
real-shaped bundle PASSES**, so drift is caught in CI rather than at 09:00.

The verdict is deliberately **tri-state** — `True` / `False` / `None`. An
`ImportError` on `renquant_common` yields `None`, never `True`: *contract
unavailable is not contract met*, which is the enumerated-allow-list fail-open shape
this repo keeps re-learning.

## What this unblocks, and what it does not

R4's remaining work is now small and correctly ordered: the daily bundle meets the
shared contract, so **adding the override-provenance field is a single additive
change to one schema** rather than a cross-repo design question. That field is **not
added here** — this PR deliberately stops at making the contract true, because a
field nothing populates is the inert scaffolding rule.

R2 (per-repo PR-template checklist items) is still open and is still only a *prompt*,
not enforcement.

Tests: 6 new, **4793 passed / 2 skipped** repo-wide.

## Review round 1 — the verdict never reached the file

Codex: `PersistDailyRunBundleTask` called `_write_json(out, bundle)` **before**
`_record_bundle_contract()`, and the latter only mutates the in-memory dict and
`stage_trace`. So `run_bundle.json` carried no `contract_validation` at all —
**including when validation FAILED**.

The one reader who needs the verdict is whoever opens the artifact after the run, and
they got a file that looked like the contract had never been checked. Recording is now
done **before** the final write.

**The regression asserts ORDER in the emitted source, deliberately.** An in-memory
assertion would have passed throughout the bug: `ctx.run_bundle` was always correct and
the FILE was the only thing wrong, so any test that never opens the artifact — or never
checks the sequence — cannot see this defect.

`[VERIFIED — this session]` 7 pass. Load-bearing by injection: restoring the old order
fails the new test, and all 7 pass again on restore.
