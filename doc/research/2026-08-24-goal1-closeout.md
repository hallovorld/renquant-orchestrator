# GOAL-1 closeout: AC2's structural finding and the AC4 decision package

STATUS: AC2 and AC4 delivered; with AC1 merged (#1028) and AC3 honoured
throughout (no config change shipped from Stage 0), **GOAL-1's measurement
programme is complete**. What remains is the capital decision itself, which
is the operator's by hard gate.

## AC2: a return-based cap comparison is STRUCTURALLY unavailable — not underpowered

The plan was Stage 1 = compare forward returns under cap variants, gated on
ESS. The measurement kills the plan at a level deeper than power:

1. **Counterfactual entries have no realized outcomes.** History ran cap 8
   only; the names a higher cap would have admitted were never bought, so
   there are no fills, no exits, no realized P&L — only forward-return
   proxies that ignore execution, wash-sale interactions, and the cash-path
   coupling between positions.
2. **Even the proxy is empty.** Of 467 cap-cut admissible names across live
   history, 50 have an `fwd_20d` proxy (the backfilled window is narrow), on
   10 sessions, and the non-overlapping ESS at h=20 is **n_eff = 1**
   [VERIFIED — runs DB, 2026-08-24].

A statistical comparison that cannot be constructed is not "pending more
data" at any horizon the book trades. AC3 anticipated exactly this shape:
**the cap decision is mechanical evidence + operator judgment**, and stating
so is AC2's honest deliverable.

## AC4: the recommendation, with every cost named

**Recommended: raise `max_concurrent_positions` 8 → 10 now; enable fractional
sizing SEPARATELY, later, under its own contract** (r2 — the first draft
proposed one coupled change; the review was right that coupling an
execution-mode change to a portfolio-capacity change destroys attribution,
and the grid never established the coupling's premise).

Mechanical evidence (AC1 v3 grid, production-seam parity 2.3e-5, era-gated):

| | cap 8 (today) | cap 10 | cap 15 |
|---|---:|---:|---:|
| median deployment, integer | 17.3% | **32.6%** | 44.6% (saturated) |
| median deployment, fractional | 20.3% | **35.2%** | 47.3% |
| price tilt, integer | 1.28× | 1.20× | **1.40×** |
| price tilt, fractional | 1.00× | 1.06× | 1.10× |

Why 10 and not 15: the marginal deployment from 10→15 (+12pp) is bought with
the worst integer-tilt regime (1.40×) and thinner per-name tickets; 8→10
captures the bulk of the unmet admissible demand (20–27 names/session vs 0–2
free slots) at the smallest structural change.

**Costs and couplings, named (the AC4 requirement):**
- **Ticket size**: at ~$10.9k equity, cap 10 → typical per-entry notional
  falls. The r1 draft claimed this makes cap-10 unsafe without fractional;
  the grid says otherwise: **cap-10 integer tilt is 1.20×, BETTER than
  today's 1.28×** — the extra slots admit mid-priced names that the cap,
  not price, had been excluding. Cap-alone is measured-safe on the only
  axis the coupling claim invoked. (Tilt worsens at cap 15, 1.40× — one
  more reason 10, not 15.)
- **Concentration**: per-name max weight unchanged (regime-capped), but the
  realized book spreads thinner; idiosyncratic single-name risk falls,
  factor-crowding risk (more names from the same admitted cohort) rises.
- **Wash-sale surface** (review r1 asked this be an explicit dependency or a
  bounded-impact argument — it is the latter): pipeline#223's mass-block
  zeroes whole buy sessions independent of slot count, so cap-10 does not
  change that failure mode's trigger; what cap-10 does add is ~25% more lots
  in steady state → proportionally more per-name wash-sale windows. The
  measured stake on the floor issue is tax of ~$15-scale per episode vs
  thousands idle — bounded, and the floor fix (#223) is independently
  justified regardless of cap. The post-deploy monitoring gate below watches
  the realized block rate so "bounded" is checked, not assumed.
- **Fractional is NOT ready, and the r1 readiness claim was wrong** —
  corrected after verifying on the ACTIVE tree [VERIFIED 2026-08-24]: the
  live path's capability gate (`fractional_capability_gate`, umbrella
  `adapters/commit_contract.py:190`) requires `is_fractionable` + a
  no-submit classifier on the broker adapter, and an ARMED software-stop
  layer. The live umbrella has **zero** `is_fractionable` implementations
  (r1 had checked the dev `renquant-execution` checkout — not the active
  path), and `execution.software_stops.enabled` is `false` with its own
  stage-3 contract unmet (2026-07-11 enablement packet gap table). Flipping
  the bit today fail-closes ALL BUY emission by the gate's design
  (`adapters/runner.py:1110`).

**Staged landing plan (r2, supersedes the one-PR plan):**
1. **Cap only, now**: strategy-104#100 (`max_concurrent_positions: 8 → 10`
   + `_reason` note; golden + six prod-mirror lanes; frozen arms untouched),
   authority = LONG-ledger row 2b (orch#1049), operator decision 2026-08-24.
   *Rollback*: single-key revert PR + pin advance — no state migration; if
   the book holds >8 names at revert time, positions age out through normal
   exits (the cap gates ENTRIES only).
   *Monitoring gates (first 10 completed sessions post-deploy):*

   Pre-deploy baseline: the 10 sessions immediately before the pin advance
   that activates cap 10 (all under cap 8). Sessions with zero buys
   (model lapse, holiday) are excluded from both baseline and post windows;
   if fewer than 5 eligible sessions remain in either window, the gate is
   INCONCLUSIVE and the window extends until 5 are collected.

   | gate | metric | source | formula | breach rule |
   |---|---|---|---|---|
   | G1 deployment | `deployed_pct` | run bundle `equity_snapshot` | `sum(position_market_value) / net_liquidation_value` at session close | 10-session median < 25% (halfway between today's ~17% and the grid's 32.6%) |
   | G2 price tilt | `integer_tilt` | run bundle `order_log` | `median(fill_price of new buys) / median(fill_price of all cap-admitted names)` per session | 10-session median > 1.35× (midpoint between today's 1.28× and cap-15's 1.40×) |
   | G3 wash block | `wash_block_rate` | run bundle `decision_ledger` | `count(sessions where wash_sale_mass_block zeroed all buys) / count(eligible sessions)` | post rate > baseline rate + 1 session (i.e., more than 1 additional blocked session in 10, accounting for the ~3/5 baseline rate) |

   A breach on ANY gate → revert PR filed within 24h of detection, findings
   appended to this doc. The revert is a single-key change
   (`max_concurrent_positions: 10 → 8`) + pin advance; no state migration.
2. **Fractional, separately, under its own contract**: (a) umbrella
   broker-adapter PR implementing the renquant-execution#19 contract on the
   ACTIVE adapter (`live/alpaca_broker.py`); (b) software-stops stage-3
   arming per its own packet (liveness pager + operator sign-off); (c) only
   then the one-bit flip under its own ledger row, at whatever cap is then
   current — attribution stays clean because stage 1's monitoring window
   will have closed.
   Order rationale vs "S-FRAC first at cap 8": stage 2's dependency chain is
   two reviewed PRs plus an ops-act (weeks), stage 1 is executable today,
   measured-safe on the tilt axis (1.20× < 1.28×), and carries the bulk of
   the deployment gain (17.3 → 32.6 of the 35.2 endpoint). Sequencing
   fractional first would idle that gain behind an unrelated dependency
   chain.

**This document still makes no change itself** (AC3; landing actions are
ask-first); the changes travel as the reviewed PRs named above.

## GOAL-1 ledger

| AC | state |
|---|---|
| AC1 mechanical grid, reproducible | ✅ merged (#1028, v3 with parity + provenance) |
| AC2 ESS before any return rule | ✅ this doc — the rule is structurally unavailable, stated as the finding |
| AC3 no config change from Stage 0 | ✅ honoured throughout |
| AC4 recommendation with named costs | ✅ this doc |
