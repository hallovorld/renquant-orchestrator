# GOAL-5 AC6 R4 step 2: the daily run bundle now records the gate it served under

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 AC6 (#564)

**Bottom line.** #669 made the daily bundle record a **contract verdict** against
`LiveRunBundle`. It still recorded **nothing about the WF gate or any operator
override** — and `LiveRunBundle` has no override-provenance field either. So a run that
served under an override left no trace of it in the artifact kept precisely to answer
*"what was in force."*

## The gap, measured

| | |
|---|---|
| `LiveRunBundle` fields (`renquant-common`) | `schema_version, source, decision_trace, order_intents, state_mutations, execution_audit, submitted_orders` — **no override field** `[本次实测 2026-07-31]` |
| daily bundle keys built by `PersistDailyRunBundleTask` on `main` | no `wf_gate*` key of any kind `[本次实测 — read from origin/main]` |
| `run_type=daily_full` bundles on disk carrying any override key | **0 of 7** `[本次实测]` — **note: all seven predate #669**, so they evidence the historical gap, not today's code. The current gap is established by reading `main`, not by these files |

## What landed

`wf_gate_provenance(artifact_manifest)` → a new `wf_gate_provenance` block in the daily
bundle, following the `serving_bundle_provenance` / `g4_session_bundle_block` idiom
already in that dict: **additive, absent-tolerant, and it never raises.**

**Three statuses, because absent is not clean and the two absences differ:**

| status | meaning |
|---|---|
| `no_artifact_manifest` | nothing was resolved to read a stamp from — *"not evidence that the gate passed"* |
| `artifact_carries_no_gate_stamp` | an artifact was resolved and carries no usable block |
| `present` | the seven AC6 fields that exist are copied, and `fields_absent` names the rest |

**A block that omitted itself when it found nothing would be indistinguishable from a
clean gate** — the failure this programme keeps re-learning.

## Canonical key, and the bug I reproduced writing it

The gate stamp lives at `metadata.wf_gate_metadata`; a legacy top-level copy exists and
the two **disagree on 2 of the 14** prod panels carrying both (twin registry R8). So
**presence of the canonical key ends the search** — a present-but-empty canonical block
means *"no usable stamp"*, never *"look in the legacy copy"*, because falling through
would seal a run with a dead value from a copy the gate stopped writing.

**The first version of this module got that exactly wrong.** `_gate_block` returned `{}`
for an empty canonical block, and the caller tests `block is None` — so an empty stamp
read as **present**. That is the same presence-vs-truthiness confusion codex caught on
orch#683, **reproduced inside the module written to avoid it**, and caught only by a test
written for that specific case.

## Why it records rather than rejects

The bundle is written **after** decisions are made and orders submitted — it is the
receipt of a run that already happened. Raising here would turn a documentation defect
into a no-trade day, which this repo has already paid for more than once. The binding
check lives where being binding is safe: **CI**, via the tests below.

## Verification

- **9 tests**, including: the two absences are distinct statuses; no absent status ever
  carries `passed` or `operator_authorized_override`; the canonical key wins on
  **conflicting** values (a precedence test whose arms are identical asserts nothing);
  an empty canonical block does **not** resurrect the legacy one; a partial stamp names
  what is missing; and hostile input never raises.
- **Mutation:** returning `{}` instead of `None` for an empty canonical block fails the
  empty-block test.
- The repo's own `test_doc_alignment.py::test_snapshot_not_stale` caught the new module
  before I did; `data/strategy_snapshot.json` regenerated.
- Suite **4841 passed, 2 skipped**.

## Not claimed

That AC6 R4 is complete — the **schema** side is untouched: `LiveRunBundle` still has no
override field, so the contract does not yet *require* what this bundle now *carries*.
That is R4's remaining half and it belongs in `renquant-common`. Nor is any historical
run bundle retro-filled: the seven on disk stay as they are.
