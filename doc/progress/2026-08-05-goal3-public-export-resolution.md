# 2026-08-05 — GOAL-3: the published surface hands out the non-kernel twin, 19 times out of 20

## The question after the census

The census (orch#821) answers *could a caller reach two definitions of this
name*. This is the next question, and the one with consequences: **for the names
the package publishes, which definition does `from <pkg> import <name>` actually
give you?**

That is decided by the package's own `__init__`, so it is resolved by importing
and reading `__module__` off the exported object — no heuristic.

## Measured `[VERIFIED — this session]`

**Which copy was measured**, because `import` resolves against `sys.path` and a
record naming only the package *name* could have measured another checkout or an
installed wheel `[codex on orch#833]`:

```
/Users/renhao/git/github/renquant-pipeline/src/renquant_pipeline
repo revision 5d41b31249df
```

A test parses that revision back out of **this file** and asserts it is the one
the measurement actually ran against `[codex on orch#833]`. Asserting only that
the revision is 40 characters proved nothing: the pipeline checkout could
advance while the aggregate stayed 20/19/0, and CI would have stayed green over
a provenance claim that had quietly gone stale.

`renquant_pipeline` at that revision, over its **20** duplicated `__all__`
exports:

| resolves to | count |
|---|---:|
| the **non-kernel** twin, while a `kernel/` twin exists | **19** |
| the `kernel/` twin | **0** |
| no `kernel/` twin at all (`InferenceContext`) | 1 |

Every one of the 19 is `differing-bodies` — **not** a thin wrapper around the
kernel definition.

This generalises a fact the ledger already held for one name (*"the PUBLIC
`VetoWeakBuysTask` export is the non-kernel twin"*) into a property of the whole
published surface.

## The sharpest instance, read line by line

`validate_order_attribution` — the two are not variants, they are **mutually
incompatible contracts** `[VERIFIED — both bodies read]`:

| | public (`order_attribution.py`, 28L) | kernel (`kernel/pipeline/order_attribution.py`, 22L) |
|---|---|---|
| shape | a **nested** `attribution` dict | **flat** keys |
| required | `version`, `source_job`, `source_task`, `acceptance_reason` | `attribution_version`, `order_source`, `score_snapshot`, `decision_inputs` |
| returns | the order | `None` |

An order valid under one is invalid under the other. The **flat** shape is the
one `kernel/persistence.py` and `kernel/trade_events.py` write to the database,
i.e. the shape production records.

## What I could NOT establish, stated rather than glossed

`renquant_orchestrator/daily.py:186` calls the **public** validator on every
order intent before execution. That reads like the production guard. It is not:
the scheduled run is `daily_104.sh` → `-m renquant_orchestrator daily-bridge`,
which **delegates to `live.runner.main()`**, and `renquant_orchestrator.daily`
is imported by **nothing but tests** in this repo `[VERIFIED — this session]`.

So this is *not* a claim that production validates with the wrong schema. Two
things block that claim and both are worth naming:

1. which definition runs depends on what each caller imports, and most
   in-package callers import `kernel.` directly (8 kernel-path imports vs 1
   public-path, inside the pipeline);
2. **order intents are not persisted in the run bundle**, so I could not read a
   real intent's shape from the durable record at all — the same
   "not-persisted, therefore unauditable" gap already logged for serving
   feature vectors.

The tool says so in its own output: *"NOT a claim about which definition
production runs"*, and a test asserts that sentence is there.

## What lands

`scripts/goal3_public_export_resolution.py` — read-only, unscheduled.
Four states, none of them a default: resolves-to-counterpart,
resolves-to-the-other-twin, no-counterpart-twin, did-not-resolve. A package
without a `kernel/` root reads **UNDEFINED**, not clean — the same three-valued
discipline the census uses.

Suites: 10 tests. All four states are exercised — including the two the first
version only *claimed* to cover `[codex on orch#833]`: an export bound to
something with no `__module__` (`EXPORT_DID_NOT_RESOLVE`), and a package with no
`kernel/` root, which reads **UNDEFINED** and prints no per-export verdict at
all. Plus the shape riding along (a wrapper is not a twin), the render refusing
the production claim, the measured copy being recorded, and the live 20/19/0
pinned to a named repository revision.

## Next

The actionable follow-up is **not** in this repo: `renquant-pipeline` decides
what its `__all__` exports resolve to. The candidate change is to re-point the
19 exports at the kernel definitions — which is a behaviour change for anyone
importing the public surface, and needs the pipeline's own review. This record
is the evidence for that proposal, not the proposal.
