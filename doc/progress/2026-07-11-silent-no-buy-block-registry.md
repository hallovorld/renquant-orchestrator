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

**r2 (Codex review, this round):** addressed all 4 points —
1. Sealed a content-addressed evidence bundle,
   [`renquant-artifacts#17`](https://github.com/hallovorld/renquant-artifacts/pull/17):
   the predeclared population rule + cross-check, per-session raw signals for all 56
   real sessions (log sha256 per session), the versioned C1-C8 classifier rubric, the
   I1-I10 online-identifiability assessment, and fresh broker-truth re-verification for
   GE/HON/EQIX.
2. Predeclared the denominator (61 cron-fired dates = 56 REAL_SESSION + 5 MARKET_CLOSED
   + 0 MISSING_LOG, three independent cross-checks) and gave 6 sessions an explicit
   `MISSING_DECISION_NO_NOTIFICATION` disposition instead of silently reading as
   no-trade — including a new finding (04-22's log truncates mid-run, a genuinely
   crashed session, not just "degraded inputs").
3. Added an explicit "descriptive taxonomy, not a validated detector" section (new §5):
   the percentages describe one historical population, are not detector
   precision/recall, and the specific numeric thresholds carried into §4 need their own
   validation before `pipeline#186` treats them as production defaults.
4. Added a per-invariant (I1-I10) online-identifiability assessment: I1/I4-I8 are
   online-identifiable same-session; I2 needs the existing fill-date lookup to gate the
   write instead of being discarded; I3 is only partial (a ledger-write failure is
   itself unobservable without an independent broker reconciliation pass); I9/I10
   require an EXTERNAL watchdog, since the defining C8 case is exactly when the run
   cannot self-report.

**This round's re-verification also caught and fixed two substantive errors** (not just
cosmetic — corrected the headline numbers): the GE broker-truth date was wrong (05-18
cited a canceled order, never filled; true value 06-01), which had inflated "GE
wrongfully wash-blocked in 8 sessions" — corrected to 1 confirmed session (07-10), with
07-03→07-09 explicitly flagged as un-re-audited rather than assumed clear. Separately,
cross-checking every zero-buy session against this doc's own C4/C7/C8 citations found
Appendix A's original "27 full-block" list under-counted by 9 sessions it already had
citations for elsewhere in the doc — corrected 27→36 full-block sessions (48%→64%), and
22/33→31/33 (67%→94%) of zero-buy sessions engineering-attributable.

**Headline numbers, corrected (56-session live history, 2026-04-21 → 2026-07-10):**
- 36/56 sessions (64%) scheduled buy path fully dead for engineering reasons;
  31/56 realized zero buys after 5 manual rescues.
- 94% of all zero-buy sessions (31/33) are engineering-attributable by this doc's own
  class citations; only 2/33 remain unclaimed (a portfolio-construction filter and an
  unresolved paper/live dual-track gap).
- Of the 36 full blocks: 47% loud, 28% semi-flagged, 25% fully silent. Degradations
  (wash mis-stamps, staleness creep, stale fundamentals overlay): 0% flagged at
  decision level.
- Live actionable: GE/HON/EQIX `last_sell_dates` stamps were corrected directly in
  live state 2026-07-11 (operator-approved, same precedent as the META fix), fresh
  broker re-verification confirms GE=06-01, HON=06-03, EQIX=06-17.

**Memory tier:** SHORT — feeds the funnel-integrity design; no LONG-ledger change.
