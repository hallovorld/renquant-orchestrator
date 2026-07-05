# S7 parking sleeve — shadow allocator module

STATUS: module delivered, shadow-only (observe, never execute).
WHAT: `src/renquant_orchestrator/parking_sleeve.py` — computes β-budgeted
      SPY/SGOV split from current book state per RS-1 formula. Outputs to a
      JSONL shadow log. BEAR regime override zeros the SPY fraction.
WHY: RS-1 measured 75.5% average cash weight over 46 sessions = foregone
     benchmark participation. The sleeve deploys idle cash into a β-budgeted
     SPY/SGOV mix (planning: β_max=0.6, SPY stress=-25% → sleeve ≈ 30/70).
     Shadow-first: arming requires the pre-registration gate per RS-1 §4.
FORMULA: spy_frac = clamp(0, 1, (β_max - β_positions) / (w_sleeve × β_spy))
TESTS: 23 unit tests covering formula, regime override, edge cases, shadow log.
NEXT: wire into the 105 session scheduler as a per-tick shadow computation;
      10-session shadow run (plumbing validation); separate SPY-arm prereg per
      #228 §1.3 before any live enablement.
