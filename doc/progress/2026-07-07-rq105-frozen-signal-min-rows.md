# 2026-07-07 — rq105 frozen-signal MIN_ROWS + --mode CLI fix

**PR**: fix(rq105): lower frozen-signal MIN_ROWS to 25 + restore --mode CLI arg

## Problem

Session scheduler connected to Alpaca paper account but immediately exited
with `aborted_class_a_unavailable` — no paper orders all day (07-07).

Root cause chain:
1. 07-06 daily-full produced only 35 candidates (WF gate filtered most)
2. `intraday_session_inputs.py` `DEFAULT_MIN_ROWS = 80` rejected the run
3. `load_frozen_daily_signal()` returned `FrozenSignalError`
4. Session scheduler aborted before any tick

Secondary: `--mode` CLI arg missing from the repo version of
`intraday_session_scheduler.py` (dropped in #420). The `-run` shell wrapper
passes `--mode paper`; next `-run` sync to repo would crash argparse.

## Fix

1. `intraday_session_inputs.py`: `DEFAULT_MIN_ROWS` 80 -> 25 (matches
   `export_batch_scores.py` which was already fixed in #415)
2. `intraday_session_scheduler.py`: restored `--mode` CLI arg with
   `choices=["shadow", "paper", "live"]` + config override logic
3. `paper` remains a Stage-1 shadow-only compatibility request, not a
   paper-order execution mode; manifests now record that explicitly so
   wrappers can keep passing `--mode paper` without creating false
   evidence that paper orders were authorized or submitted

## Verification

Ran session scheduler with `--max-cycles 0 --json` against `-run` checkout
after applying the MIN_ROWS fix:
- Before: `"status": "aborted_class_a_unavailable"`, `"errors": ["no qualifying completed live run..."]`
- After: `"status": "stopped_max_cycles"`, `"errors": []`, `"tick_count": 1`

Added targeted scheduler tests to verify:
- `mode=paper` is accepted by config/CLI as a compatibility request
- effective execution mode remains `shadow`
- manifests distinguish `live` downgrade counts from `paper`
  compatibility counts
