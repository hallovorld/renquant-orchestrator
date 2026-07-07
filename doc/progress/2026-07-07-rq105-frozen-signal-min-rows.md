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

## Verification

Ran session scheduler with `--max-cycles 0 --json` against `-run` checkout
after applying the MIN_ROWS fix:
- Before: `"status": "aborted_class_a_unavailable"`, `"errors": ["no qualifying completed live run..."]`
- After: `"status": "stopped_max_cycles"`, `"errors": []`, `"tick_count": 1`

## Round 2 (Codex review)

STATUS: fixed
WHAT: `--mode paper` fixed the argparse crash, but `resolve_mode()` still
only special-cased `mode == "live"` — a paper request silently fell through
to the identical `(MODE_SHADOW, False)` result as a plain shadow request,
with no recorded evidence in the manifest that `paper` was ever requested.
The PR's own "tomorrow confirm ... places paper orders" claim was therefore
misleading: no such path exists in this repo (see #400, which removed the
last attempt at a real paper-broker submission path as an architecture-
boundary violation — implementing broker execution here is not allowed).
WHY-DIR: a caller cannot afford to silently lose the distinction between "I
asked for paper mode and it was honestly downgraded to shadow" and "I asked
for plain shadow" — the module docstring is explicit that Stage 1 is
shadow-only, so any non-shadow request must be recorded as a downgrade, not
absorbed invisibly.
EVIDENCE: added `MODE_PAPER`; `resolve_mode()` now returns
`(effective_mode, downgraded, downgrade_kind)` with `downgrade_kind` in
`{"live", "paper", None}`; manifest gained a `paper_mode_downgraded_count`
field distinct from the existing `live_mode_downgraded_count`. Two new
tests (`test_paper_mode_downgrades_to_shadow`,
`test_paper_mode_config_downgrades_and_counts_distinctly_from_live`) plus
updated assertions on the existing live-mode tests, all confirmed to fail
against the pre-fix code via `git stash` (unpacking error / stale manifest
schema / wrong terminal status) and pass after. Corrected the PR body to
remove the "places paper orders" claim — `--mode paper` is Stage-1
shadow-only compatibility, nothing more.
NEXT: real paper-order submission remains out of scope here; any future
work belongs in `renquant-execution` with its own authorization design, per
#400.
