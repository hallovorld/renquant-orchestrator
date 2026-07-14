# 2026-07-14 — G3 Phase A: cross-repo parity tripwires (RELOCATED)

STATUS: relocated to RenQuant (umbrella) — see RenQuant#469
WHAT: Read-only checks that detect constant/contract drift between
      renquant-pipeline and renquant-execution, per the G3 refactoring plan
      Phase A, registry items A2 and A3.
WHY: Every Phase B single-source consolidation needs a tripwire that fires
     when the duplicated code drifts.

## Relocation (Codex review)

This PR originally added `tests/test_cross_repo_parity.py`: 6 pytest tests
importing `renquant_pipeline`/`renquant_execution` directly from local
sibling directories (available on a developer machine, since this repo's
own `pyproject.toml` `pythonpath` already lists all sibling `src` dirs for
local dev/test).

Codex review flagged that this repo is the wrong owner for a
pipeline-vs-execution contract test: orchestrator's normal CI has no job
that checks out those two sibling repos, so a green orchestrator build here
proves nothing about the actual invariants — it's the same no-op-green
pattern already fixed for F-6 in the umbrella (`RenQuant#468`,
`kernel-parity-ci.yml`).

The checks were moved to the RenQuant umbrella repo (`RenQuant#469`), which
owns `subrepos.lock.json` — the exact pipeline/execution pins — and now has
a dedicated strict CI job
(`.github/workflows/pipeline-execution-parity-ci.yml`) that checks out
renquant-pipeline, renquant-execution, and their own
renquant-common/renquant-base-data/renquant-artifacts dependencies as real
siblings at their pinned commits, and fails (does not skip) if the
comparison cannot run. `tests/test_cross_repo_parity.py` was removed from
this repo entirely — no non-authoritative stub was kept here, to avoid
re-creating the exact duplication Codex flagged. See
`RenQuant/doc/progress/2026-07-13-g3-a2-a3-pipeline-execution-parity-ci.md`
for the umbrella-side implementation and verification record.

## What the checks found (historical — now enforced in RenQuant#469)

### A2: duplicated constants parity

| Contract | Pipeline source | Execution source | Status |
|----------|----------------|-----------------|--------|
| `MIN_FRACTIONAL_NOTIONAL_USD` | `kernel.sizing:187` | `broker:73` | EQUAL (1.0) |
| `compute_parent_intent_id` | `intraday_decisioning:103` | `order_state_machine:179` | EQUAL (3 golden vectors) |

The functions differ only in docstrings — logic is byte-identical.

### A3: calendar implementation inventory

Found 7 raw `pandas_market_calendars` imports in the pipeline kernel that
should use `renquant_common.market_calendar`:

| File | Line |
|------|------|
| `__init__.py` | 9 |
| `data.py` | 64 |
| `execution/t2_settlement.py` | 28 |
| `exits.py` | 70, 126 |
| `pipeline/task_data_freshness.py` | 225 |
| `typed_past/typed_data_freshness.py` | 95 |

Baselined at 7 as an upper-bound (temporary Phase B2 migration guard, not a
hard zero gate) in the umbrella-side check.

## Risk assessment

ZERO risk — this PR now only removes a test file; no production code
changed at any point in this PR's lifetime.

## Files

- `tests/test_cross_repo_parity.py` (removed — relocated to RenQuant#469)
- `doc/progress/2026-07-14-g3-phase-a-parity-tripwires.md` (this file, updated)
