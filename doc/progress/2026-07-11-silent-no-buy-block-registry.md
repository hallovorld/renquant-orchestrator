# Progress — silent no-buy block registry (2026-07-11)

**What:** whole-history retrospective sweep (operator escalation from the META
wash-sale incident): quantify every episode where live buy capability was silently
degraded by an engineering cause while reporting looked like a normal no-trade.

**Deliverable:** `doc/research/2026-07-11-silent-no-buy-block-registry.md` —
per-class episode registry (8 classes C1–C8) mapped to detectable invariants
(I1–I10); requirements input for the funnel-integrity pipeline step designed in
parallel.

**Method:** read-only sweep of `runs.alpaca.db` (immutable open), all
`logs/daily_104` + `logs/intraday_104` logs, `live_state_snapshots`, and broker-truth
fill reconstruction; reused the decision-tree-review skill's extraction logic.
No production paths touched; work done in an isolated worktree.

**Headline numbers (56-session live history, 2026-04-21 → 2026-07-10):**
- 27/56 sessions (48%) scheduled buy path fully dead for engineering reasons;
  22/56 realized zero buys (5 rescued manually).
- 67% of all zero-buy sessions were engineering, not economics.
- Of the 27 full blocks: 63% loud, 22% semi-flagged, 15% fully silent.
  Degradations (wash mis-stamps, staleness creep, stale fundamentals overlay):
  0% flagged at decision level.
- Live actionable: GE/HON/EQIX `last_sell_dates` stamps still wrong in the 07-10
  snapshot (GE wrongfully wash-blocked in 8 sessions and counting).

**Memory tier:** SHORT — feeds the funnel-integrity design; no LONG-ledger change.
