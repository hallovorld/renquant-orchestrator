# S7 parking sleeve — shadow allocator module

STATUS: module + scheduled-job runtime wiring delivered, shadow-only (observe, never execute).
WHAT: `src/renquant_orchestrator/parking_sleeve.py` — computes β-budgeted
      SPY/SGOV split from current book state per RS-1 formula. Outputs to a
      JSONL shadow log. BEAR regime override zeros the SPY fraction.
      As of 2026-07-07, the scheduled-job entrypoint (`run-job
      parking_sleeve_shadow`) auto-derives book state from the latest live
      run + OHLCV store, writes to the canonical
      `backtesting/renquant_104/logs/parking_sleeve_shadow.jsonl`, and emits
      `spy_notional`/`sgov_notional` aliases so the risk-budget monitor can
      read the sleeve beta leg from real logs.
WHY: RS-1 measured 75.5% average cash weight over 46 sessions = foregone
     benchmark participation. The sleeve deploys idle cash into a β-budgeted
     SPY/SGOV mix (planning: β_max=0.6, SPY stress=-25% → sleeve ≈ 30/70).
     Shadow-first: arming requires the pre-registration gate per RS-1 §4.
FORMULA: spy_frac = clamp(0, 1, (β_max - β_positions) / (w_sleeve × β_spy))
TESTS: 23 unit tests covering formula, regime override, edge cases, shadow log.
NEXT: the remaining gap is NOT basic job wiring anymore; it is the higher-level
      integration: wire into the 105 session scheduler as a per-tick shadow
      computation; run the 10-session shadow-plumbing validation; complete the
      separate SPY-arm prereg per #228 §1.3 before any live enablement.

ROUND 2 (Codex review): the module docstring's formula omitted the w_sleeve
term (stated `(β_max − β_positions) / β_spy`, a different and wrong formula
from the executable `(β_max − β_positions) / (w_sleeve × β_spy)`). Fixed the
docstring to match the code exactly, and made "integration pending" explicit
in the module docstring itself (was already explicit in this doc's NEXT line,
but not in the code's own docstring). No executable-code change; 23/23 tests
unchanged.
