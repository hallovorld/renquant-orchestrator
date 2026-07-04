# Progress: risk-budget ledger — observe-only budgets/consumption/runway (sprint D3)

DATE: 2026-07-03

- Built `src/renquant_orchestrator/risk_budget/` (budget definitions with
  provenance, read-only consumption readers, attribution-engine bridge,
  monthly statement CLI with 0/2/1 breach exit codes) + ops wrapper/plist
  FILES under `ops/renquant104/` (no install performed).
- Budgets: DD 15% HARD (G* bar) · β 0.6 planning (RS-1 §2) · per-name
  concentration per pinned regime caps · sleeve DD sub-budget (#157).
  Existing controls consumed, not reimplemented; no gates, no trading
  behavior — anything behavior-changing is a separate design PR.
- First real statement (2026-07-02): **CRITICAL** — pt book β 0.745 vs 0.6
  (MU β 4.29 × 9.1% = 0.391 alone); DD 50.2% of budget consumed (max 7.5%,
  runway ≈ 53 sessions at current burn); PANW 81.3% of the BULL_CALM
  per-name cap (WARN); sleeve sub-budget censored (shadow log absent,
  flag default-OFF). Leg finding: SIZING is the only negative leg
  (−$1.2k in the current DD window); June-era legs partially censored (#253)
  — propagated explicitly, nothing imputed.
- Tests: 34 new (`tests/test_risk_budget.py` — DD/burn/HHI/β incl. sleeve
  leg arithmetic, breach thresholds + exit codes, censoring, real-DB
  read-only smoke). Full suite green: 1718 passed, 3 skipped.
- Design note: `doc/design/2026-07-03-risk-budget-ledger.md`.
