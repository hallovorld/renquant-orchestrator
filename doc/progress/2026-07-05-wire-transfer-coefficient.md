# Wire transfer_coefficient into CLI

**Date:** 2026-07-05
**Sprint:** S-TC
**Status:** complete

## What

Added `transfer-coefficient` subcommand to the orchestrator CLI, wiring
the existing `transfer_coefficient.py` module (355 lines, already tested)
into the standard `renquant-orchestrator` entry point.

## Why

The TC measurement module existed as a standalone script
(`scripts/poc_transfer_coefficient.py`) and library module but was not
accessible via the CLI. Wiring it in makes it available to scheduled jobs,
operator skills, and the standard `renquant-orchestrator transfer-coefficient`
invocation pattern used by the rest of the control plane.

## Changes

- `src/renquant_orchestrator/cli.py`: added `transfer-coefficient` subcommand
  parser (REMAINDER delegation to `transfer_coefficient.main`) and dispatch
  handler.
- `data/strategy_snapshot.json`: updated baseline (new subcommand registered).

## Evidence

- `make test` passes (46/46 relevant tests; 2 pre-existing failures from
  missing `renquant_execution` in the worktree are unrelated).
- `tests/test_doc_alignment.py` passes (snapshot updated).
- `tests/test_transfer_coefficient.py` and `tests/test_poc_transfer_coefficient.py`
  continue to pass.
