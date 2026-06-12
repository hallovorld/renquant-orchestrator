# Experiment Spec v5 — Active Experiments Only (E6, E8, E5)

**Status:** spec / awaiting review. Companion to design v5. Dropped
experiments (E1 FAILED archive, E2/E3/E4/E7) live in git history only
(#99/#103 branches); they are not part of this spec and may be reproposed
only with a new evidence-based rationale.

## 0. Common protocol
- No look-ahead: signals at close of t, execution at open of t+1.
- Costs: SPY borrow 0.3%/yr; single-name borrow 1%/yr (conservative ETB);
  slippage 5 bps/side; actual dividends paid while short.
- Statistics: block bootstrap (calendar-month blocks) for 90% CIs; cells
  with n<30 inconclusive; one pre-registered primary cell per experiment.
- Provenance: every replay stamps strategy/pipeline config fingerprints +
  `subrepos.lock.json` digest.

## E6 — Phase-A hedge replay (primary; can run now)
Three arms, same trigger stream (`hard_bear`, post-#112 semantics):
(a) short-SPY hedge h=0.5·β; (b) cash de-risk, same notional; (c) nothing.
- Windows: 2022 bear; 2025-04 dip; 2025-10→2026-01; full validation year;
  **negative control 2026-06-11** (post-fix detector must not fire).
- Sensitivities: h ∈ {0.25, 0.75}; vol-managed trigger variant
  (Moreira–Muir) — sensitivity only, NOT part of the v5 deliverable.
- Metrics & PASS: per design §2.1 (hedge must beat cash de-risk on Sortino
  AND Calmar in stress without >1% NAV/yr bull drag).

## E8 — Phase-B efficiency replay (after long-side WF gate is green)
QP with vs without bounded short sleeve (gross ≤120%, short ≤10% NAV,
per-name ≤3%, borrow priced). Primary cell 110/10; sensitivity 120/20.
PASS: net IR up AND MaxDD not worse AND turnover ≤1.5×.

## E5 — Short-interest event study (after FINRA backfill)
- Backfill: FINRA bi-monthly archives; **point-in-time join on publication
  date (settlement + ~9 business days)** — never settlement date.
- Event: rising shares_short m/m AND days-to-cover ∈ [2, 8].
- Primary outcome: 20d SPY-hedged P&L of hypothetical shorts, costs per §0.
- PASS bar: hit-rate(fall) ≥ 55% AND net hedged mean P&L > 0 (90% CI
  excluding 0) AND stop-sim worst event ≥ −25%. Only a PASS reopens any
  Phase-C discussion.
