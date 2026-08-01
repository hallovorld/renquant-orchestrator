# GOAL-5 AC6 R4 — the live-bundle paths are "validated" over keys nothing reads

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 (P0) / AC6 R4, issue #564

## The question R4 was stuck on

#564: *"R4 needs to decide which bundle the [override-provenance] field belongs on (or
both) and wire real validation."* The blocker was framed as a choice between the daily
`run_bundle.json` and the shared `LiveRunBundle`. Measuring both answers it.

## Measurement 1 — the daily bundle is ONE field from validating, and that is a trap

All 7 persisted daily bundles under `.subrepo_runs/`, run through
`validate_live_run_bundle` `[本次实测 2026-07-31]`:

| | |
|---|---:|
| bundles examined | **7** |
| pass | **0** |
| fail | **7** |
| distinct causes | **1** — `source: Field required` |
| keys that would be **silently dropped** if it did pass | **12–13 of 17–18** |

So adding `source` would flip 0/7 → 7/7 "valid" while discarding
`strategy_config_hash`, `artifact_manifest`, `data_manifest`, `strategy_manifest`,
`run_id`, `stage_trace` — **every provenance field in the document**. That is a green
check over an unread field, and it is the specific outcome AC6 exists to prevent.

`LiveRunBundle`'s own docstring says what it is: *"Readonly live-run bundle for
native-vs-bridge offboard parity."* `source` means *which implementation produced this*.
The daily run has no such notion. **The name says "live run bundle"; the contract says
"parity record".** Wiring the daily bundle into it would be validating the wrong object.

## Measurement 2 — the paths that DO use it carry keys the schema never reads

`ops/bundle_producer_key_audit.py` (new) reads both producers by **AST**
`[本次实测 2026-07-31]`:

```
producers declared=2 read=2 unread_keys=2 ['metadata', 'smalln_ledger']
schema drops undeclared keys : True
```

- `build_native_live_bundle` builds 8 keys — **`metadata`** is undeclared.
- `build_bridge_live_bundle` builds 7 keys — **`metadata`** and **`smalln_ledger`** are
  undeclared.

Confirmed by executing the validator, not by reading it:

```
validate_live_run_bundle({..., "smalln_ledger": {...}})   ->  LiveRunBundle
"smalln_ledger" in result.model_dump()                    ->  False
```

**Narrowed, and the narrowing matters: no data is lost.** Both producers call the
validator for its side effect and return **their own** dict, so both keys reach disk
intact. The defect is **coverage**, not loss: `smalln_ledger` — the small-n capital-gate
ledger — travels a path that reads as validated while nothing validates it. If it became
malformed, changed type or vanished, no check in this repo would notice.

A regex over the dict literal finds only `smalln_ledger`; `metadata` is assigned by
subscript. That is why this reads AST, and why a computed key is reported as
**UNKNOWABLE** rather than skipped.

## The R4 decision these two measurements support

1. **Do not wire the daily bundle into `LiveRunBundle`.** Different contract, and the
   validation would discard the provenance it is meant to protect.
2. **Adding override provenance to the live-bundle path is not enforcement today** —
   it would land among `metadata` and `smalln_ledger` as a third unread key. Either
   `extra="forbid"` plus declaring the real fields, or a purpose-built daily-bundle
   contract, has to come first.
3. This audit makes (2) a **re-derivable number** instead of an observation, so the
   precondition is checkable rather than remembered.

## What this does NOT do

It does not change any schema, does not touch a producer, and does not decide between the
two remedies in (2) — that is a shared-contract change across repos and it needs the
owning decision, not an audit's opinion. Read-only: parses files, writes nothing, never
invokes git.

## Tests

`tests/test_bundle_producer_key_audit.py` — 11 tests. The audit's own failure modes are
the subject: a **missing** producer and a **renamed** target function are failures, not a
shrinking denominator (otherwise deleting a producer is the cheapest way to go green); a
computed key is **UNKNOWABLE**, never silently dropped; the schema field set is read off
the model, never hardcoded; `main()`'s **exit code** is driven directly, because that is
what a scheduled job reads; and the report is asserted to state that unread is **not**
lost, so the finding cannot be read as data loss.

---

## ROUND 2 2026-07-31 — a key census is not a statement about a validated boundary

Reviewed `[codex on orch#690]`: *"it currently proves only that named functions contain
assignments with particular keys. It does not verify that each function actually passes
its constructed bundle to `validate_live_run_bundle`, so a refactor that removes or
bypasses that call can still yield a confident report about a validated producer path."*

Correct — and it is **this audit committing the defect it was written to expose**, one
level up. The tool's whole claim is *"these keys travel a validated path uncovered"*. If
the validation call went away, the claim would keep being emitted about a boundary that
no longer exists.

**`_validates()` now requires both halves:** the validator must be **called**, and its
first positional argument must be a name that was **assigned a dict literal in the same
function**. Calling the validator on some other object is not validating the bundle you
built — that is the bypass a presence-only check misses. A module-qualified call
(`schemas.validate_live_run_bundle(bundle)`) counts, since rejecting it would be a false
positive on a legitimate import style.

A producer that no longer validates its own bundle is reported as **`NOT VALIDATED`** —
ranked ahead of unread keys in the output, because it invalidates the rest of the report —
and drives the exit code.

**Live measurement `[本次实测 2026-07-31]`: both real producers still validate their own
bundle.** So the boundary this report describes is currently real, and the check earns its
place by being able to fail — which the negative fixtures demonstrate.

### Tests — 16 (was 11)

The three new negative cases are the ones that matter: the **builder remains but the
validation call is removed** (the case named in review), the validator **called on a
different object**, and an anti-vacuity case where a producer that genuinely validates its
bundle passes and exits `0`. Plus a module-qualified call, and a live assertion that both
real producers still validate — so a future refactor that drops the call fails here.
