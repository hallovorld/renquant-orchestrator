# renquant105 Phase -1 — cheap, bounded, read-only feasibility (the FIRST gate)

2026-06-27. Part of the renquant105 suite (master: `…-intraday-system.md`).
**Status: PROPOSAL (no code, no orders, no new data purchase).** This is a **read-only,
hard-time-capped** feasibility probe that runs **BEFORE M0** and is wired as the **FIRST gate
in the master DAG** (finding 9). Its purpose is to spend a few days of analyst time — not 10-17
weeks of build — to decide whether the full 105 stack is even worth standing up.

## Why this milestone exists (finding 9)
The full program (M0 → M0.5 → M1 → M2 → M3, plus H2) is **~10-17 weeks of work before any
credible alpha measurement**. Before committing that, we must spend a **bounded** amount of
effort to check that the cheap, decisive preconditions hold — using **ONLY existing historical
data already on disk** (no SIP purchase, no new ingestion, no model training, no orders). The
single most load-bearing assumption in §A is the open→close cross-sectional dispersion
`σ_oc ≈ 150-250 bps`, which the feasibility script currently **ASSUMES** (it is a PRIOR, not a
measurement). Phase -1 measures it (and three siblings) cheaply, so we do not build the full
stack on an unmeasured prior.

## Scope (hard boundaries)
- **Read-only.** Uses ONLY existing historical bars/fills already present (the parked intraday
  caches, the 104 fill history, daily bars). **No** new data subscription, **no** new ingestion
  cron, **no** model, **no** order (not even a paper order — this milestone places nothing).
- **Hard time/resource cap (PINNED):** **≤ 5 analyst-days of effort and ≤ 1 week wall-clock.**
  If the four measurements below cannot be produced within that cap on existing data, that is
  itself a STOP signal (the data foundation is not cheaply available → do not start M0).
- **No new claims of tradability.** Phase -1 produces *cheap measured bounds*, not the M1 GO
  estimand. A Phase -1 GO only means "the full stack is worth building"; it does **not** replace
  M1's frozen-policy replay.

## What Phase -1 measures (ONLY existing historical data)
1. **Basic intraday data availability.** On the existing parked caches: how many liquid large
   caps have usable intraday history, over what date span, at what NaN/gap rate. This is a
   *coverage census on data we already hold* — not the M0 point-in-time universe build.
2. **Causal open→close cross-sectional dispersion `σ_oc` (the number §A ASSUMES at 150-250 bps).**
   Measure the realized cross-sectional std of **open→close** (overnight-excluded, session-aware)
   returns per session, **bound by the event-time contract** (finding 1: dispersion of the
   *executable* open→close return — entry at the first executable quote after a hypothetical
   `first_eligible_fill_ts`, exit at the close — NOT the closed-bar-to-close dispersion, which is
   inflated). Report the distribution (median, IQR) across sessions, not a point value. **This is
   the verdict-driving measurement:** if the *causal* σ_oc is materially below the assumed band,
   §A's "marginal-to-viable" prior collapses toward "underwater".
3. **Attainable universe breadth.** The number of names that simultaneously clear a lagged-ADV
   liquidity floor AND have usable intraday history — i.e. the *realistic* breadth that feeds the
   Fundamental-Law `√breadth` term (§A.4 assumes ~4 independent bets/day). If breadth is far below
   that, the gross-IR prior shrinks.
4. **Conservative executable-cost bounds.** From the existing 104 fills + the quoted spreads in
   the historical bars, a *cheap conservative* round-trip cost band (the §A `11 bps` placeholder
   is a prior; this is a quick existing-data sanity bound, NOT the M0 calibrated stratified cost
   model — that remains an M0 deliverable). Purpose: confirm the cost placeholder is not wildly
   optimistic before building.

## Explicit stop/go criteria (PINNED — decided NOW, not after seeing data)
Phase -1 is a gate with a **pre-registered** decision rule (same discipline as M1 F1.7):

| Outcome | Condition |
|---|---|
| **GO to M0** | (a) ≥ ~30-40 liquid names have usable intraday history on existing data; **AND** (b) the **causal** open→close `σ_oc` median is **inside or above the §A assumed band's lower edge (≥ ~150 bps)** with the event-time contract applied; **AND** (c) attainable breadth supports ≥ ~4 effective independent bets/day; **AND** (d) the conservative existing-data cost band does not exceed ~17 bps (the §A conservative leg). |
| **STOP before M0** | the causal `σ_oc` is materially below the assumed band (so §A's marginal case does not survive a real dispersion), **OR** attainable breadth/coverage is too thin to power the program, **OR** the four measurements cannot be produced within the **≤5-day / ≤1-week cap** on existing data, **OR** the cheap cost band is materially worse than the §A conservative leg. |

**The binding stop rule (finding 1 + finding 9):** if the available history **cannot meet the
pre-registered N_eff** (M1 F1.7) **OR cannot satisfy the causal data contract** (finding 1 — a
non-look-ahead, executable open→close return), **STOP before building the full 105 stack.** Do
NOT proceed to M0 on the assumption that M0/M1 will fix a dispersion or coverage shortfall that
the existing data already refutes.

## Deliverables
A short Phase -1 report: the intraday-coverage census (existing data), the **measured causal
open→close σ_oc distribution** (with the event-time contract noted), the attainable-breadth
count, the conservative existing-data cost band, and the **pre-registered GO/STOP decision**
against the table above. No code beyond a read-only analysis script; no artifact that any later
milestone depends on for correctness (M0 re-measures everything properly).

## Relationship to M0 / the DAG
Phase -1 is **upstream of M0** in the acyclic DAG (master §7): it is the **first gate**. A
Phase -1 STOP ends the program before M0. A Phase -1 GO authorizes M0 (the proper point-in-time
universe build + the calibrated stratified cost model), which then supersedes Phase -1's cheap
bounds. Phase -1 does **not** authorize any cross-repo topology change (that is the umbrella ADR,
finding 8) and creates no new pinned repo.

## Effort
**≤ 5 analyst-days, ≤ 1 week wall-clock (hard cap).** Read-only analysis on existing data only.
If it costs more than that, the answer is STOP.
