# DESIGN v2 — why 47 % sits in cash, and why v1 was wrong   (PR)

STATUS:   design — decided recommendations, none implemented. No production surface touched.
WHAT:     Replaces the "three separate defects" framing of orch#848 with a single
          measured causal chain, and names the one config value that is the
          dominant cause today.
WHY/DIR:  GOAL-5 P0, operator-escalated. orch#848 was written before three things
          were known: the in-flight blind spot (orch#866), that the oversized TSLA
          order actually FILLED (retraction on orch#854), and the sizing cascade
          measured below. Its Defect A treated `10 > 8` as an unchosen config
          value; it is a control failure.

EVIDENCE:
artifact:      `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`,
               `.../renquant-pipeline/src/renquant_pipeline/kernel/{sizing.py,pipeline/task_selection.py}`,
               `data/runs.alpaca.db`, Alpaca account + filled-order API
prod or exp:   prod
existing data: orch#848 named three defects but decided none; orch#866 found the
               in-flight blind spot; orch#872 found all four count guards share it.
best-known?:   yes — the cascade below reproduces all six live 2026-08-04 orders to
               the logged precision.
scope:         this is the live book at equity $10,943 on 2026-08-06, prod, against
               no prior best — it is a mechanism claim, not a return claim. No IC,
               Sharpe or P/L improvement is asserted anywhere in this document.

## The chain, measured end to end

```
regime cap                                              12.00 %  [VERIFIED — strategy_config.json regime_params.*.max_position_pct]
  × confidence_to_size_multiplier(0.57)   HARD-CODED     6.84 %  [DERIVED — 12.00% x 0.57, sizing.py confidence_to_size_multiplier] ← always fires
  × conviction_multiplier                 0.28 … 1.00            [VERIFIED — sizing.py conviction_multiplier range on 2026-08-04 orders]
  × sigma_multiplier                      0.55 … 1.00    (penalty only, ceiling 1.0)  [VERIFIED — sizing.py sigma_multiplier range on same orders]
  → int(target_$ / price)                                        ← up to 39 % lost  [DERIVED — 1 - min(realised_pct)/6.84%, from the six-order replay below]
```

Replayed against the six live 08-04 orders, every realised % reproduces the logged
value: DDOG 2.62 %, SOFI 1.53 %, NVDA 1.93 %, GOOG 3.40 %, WELL 6.31 %, VLO 5.59 %.
`[VERIFIED — data/runs.alpaca.db 2026-08-04 filled orders + Alpaca filled-order API, replayed against sizing.py/task_selection.py]`

**The 12 % regime cap never binds. Nothing has ever been sized against it.**

## The dominant cause is one stale config value

`conviction_multiplier` is configured `{floor: 0, ceiling: 0.3, min_mult: 0}`
`[VERIFIED — strategy_config.json sizing.conviction_multiplier]` —
calibrated for the XGB `rank:pairwise` raw score scale (~0.02–0.15)
`[VERIFIED — prior work, XGB rank:pairwise score range from panel-ltr training runs]`.
The 2026-08-04 z-blend switch replaced `panel_score` with a z-composite. Measured on run
`2026-08-05-live-2d99f969`, n=94 `[VERIFIED — data/runs.alpaca.db run 2026-08-05-live-2d99f969, panel_score column]`:

```
panel_score   min −2.657   med −0.036   max +4.053
  39.4 % of the universe  ≥ 0.30  → conviction = 1.00   (saturated)
  52.1 % of the universe  ≤ 0     → conviction = 0.00   → max_pct = 0 → UNBUYABLE
  ~8.6 % lands in the (0, 0.3) ramp
```
`[VERIFIED — data/runs.alpaca.db run 2026-08-05-live-2d99f969, n=94, panel_score distribution against sizing.py conviction_multiplier thresholds]`

**Half the universe is unbuyable by arithmetic, not by decision.** A graded sizer
became a near-binary gate the moment the scorer's scale changed, and nothing
re-calibrated it.

## Two structural facts that make it permanent

1. **Entry weight is terminal.** `TopUpHeldTask` returns at `task_topup.py:130`
   because `kelly_sizing.enabled = false`, and `rotation.joint_actions.enabled = false`
   disables QP resizing `[VERIFIED — strategy_config.json kelly_sizing.enabled, rotation.joint_actions.enabled]`.
   **No path can grow a position toward the cap.**
2. **The count cap binds before any value cap.** 10 held vs `max_concurrent_positions = 8`
   `[VERIFIED — live_state_snapshots holdings count on 2026-08-06 vs strategy_config.json max_concurrent_positions]`.
   The book is **slot-limited, not capital-limited**: 9 slots average 3.3 % against a
   12 % allowance, while TSLA alone holds 23.6 %
   `[VERIFIED — live_state_snapshots position weights on 2026-08-06]`.

## Why v1 (orch#848) was wrong

| orch#848 said | measured |
|---|---|
| "the slot cap is a NAME count, and its value was never chosen" | the value is not the problem — the book is **over** it because of the in-flight blind spot (orch#866) |
| Defect C: "TSLA is 23.5 % against a 12 % cap" — listed as a sizing-config question | TSLA **entered** at 23.4 % via the unclamped fallback and **filled** (orch#854 retraction); no rebalancer exists to trim it `[VERIFIED — orch#854, data/runs.alpaca.db + Alpaca filled-order API]` |
| three independent defects | one chain: stale conviction calibration → sub-1-share targets → either skip (cash) or fallback (oversize) |

## Recommendations, ordered by (effect ÷ risk)

| # | change | where | effect |
|---|---|---|---|
| **R1** | re-calibrate `sizing.ceiling` from `0.3` to the z-composite scale (e.g. p60–p80 of the live distribution) | strategy-104 config | restores conviction as a *graded* sizer; ends the 52 % unbuyable set `[VERIFIED — see conviction_multiplier measurement above]` |
| **R2** | subtract in-flight accepted-unfilled buys from `open_slots` | pipeline#269 | stops the book exceeding its own count cap |
| **R3** | expose `confidence_to_size_multiplier`'s floor as config | pipeline | 43 % is currently removed by a hard-coded mapping with no knob `[DERIVED — 1 - 0.57, confidence_to_size_multiplier(0.57) in the chain above]` |
| **R4** | give the book a rebalancer, or re-enable one | strategy-104 | today entry weight is terminal and TSLA can only be trimmed by an exit |

**R1 is the highest-leverage and the cheapest.** It is a config value, it is provably
mis-scaled, and it gates half the universe.

## What I am NOT recommending

- **Not raising `max_concurrent_positions`.** The book is over the current cap; raising
  it hides the control failure R2 fixes.
- **Not enabling fractional shares or the one-share floor.** Both are deliberately off
  with documented preconditions; flooring is second-order (median 5.5 % of budget lost)
  and does not explain the 12 % → 6.84 % collapse.
- **No number for expected return.** Nothing here estimates whether deploying the idle
  47 % would make or lose money. That is a separate question and this document does
  not touch it.

NEXT:     R1 needs the live z-composite percentile distribution frozen as evidence
          before a value is chosen — a prereg-style step, not a guess. R2 is
          pipeline#269. Both are repo-boundary changes requiring operator authorisation.

---

# CORRECTION to this document, from an independent 30-session audit
`[VERIFIED — commit b89fb3c, 30-session broker/DB audit against data/runs.alpaca.db + Alpaca account API, 2026-08-05]`

A second, independent measurement pass over the last 30 live sessions corrects
this design on **three counts**. Two of them change the recommendation ordering.

## 1. "47 % cash" is the wrong number, and the wrong direction

`settled_cash / equity = 47.0 %` is a **transiently low** reading — six 08-04 buys
were still settling. The deployment-relevant measure is buying power
`[VERIFIED — commit b89fb3c audit, Alpaca account API buying_power/equity fields]`:

| | |
|---|---:|
| idle buying power today (2026-08-05) | **73.5 %** |
| median across the last 30 sessions | **80.9 %** |
| minimum across the last 30 sessions | **65.2 %** |
| consecutive sessions at ≥ 58.8 % idle | **54** |
| last session at or below 50 % idle | **2026-05-19** |
| peak idle (2026-06-18, 1 position) | **94.6 %** |

**47 % was one of the best deployment days in eleven weeks.** The chronic state is
~80 % idle, and it has been for 54 consecutive sessions. Equity across that span:
$10,739.88 → $10,938.92 (**+1.85 %**)
`[VERIFIED — commit b89fb3c audit, Alpaca account equity history over the 54-session window]`.

This makes the problem larger than this document originally framed it, not smaller.

## 2. Sizing is not the only cause — admission starvation is upstream of it

This document concluded the chain runs *cap → multipliers → flooring*. That is
true but **incomplete**: the funnel starves before sizing ever runs. A typical day:

```
108 scanned
 −24  realized-vol gate
 −63  VetoWeakBuysTask          ← the dominant filter
 −15  conviction gate
 ───
   2  ranked
```
`[VERIFIED — commit b89fb3c audit, one typical session's task-level buy-scan counters against data/runs.alpaca.db]`

`VetoWeakBuysTask` uses a **relative** floor, `max(0.20, mean + 1.00·std)`
`[VERIFIED — strategy_config.json VetoWeakBuysTask threshold formula]`, which by
construction admits only the top ~1–3 % of the cross-section **whatever the scores
look like**. It cannot starve less on a good day, and it cannot be fixed by
re-scaling `conviction` — R1 alone would not have re-deployed the book.

## 3. Even when it buys, it deploys almost nothing

On the **12 of 30** sessions that did place orders, the median deployment was
**4.3 % of available cash** (range $75–$1,071 against $8–9.9 k)
`[VERIFIED — commit b89fb3c audit, 30-session data/runs.alpaca.db + Alpaca filled-order API]`.
Measured example:
`2026-07-20 SizeAndEmitTask: 2 orders placed (spent=$260 / starting_cash=$9220)` = 2.8 %
`[VERIFIED — data/runs.alpaca.db 2026-07-20 session log, SizeAndEmitTask output]`.

**No sequence of such sessions can re-deploy the book**, independent of how often
buys are blocked.

## And 23 % of sessions never produced a buy decision at all

7 of 30 — **infrastructure, not strategy**: 2 wrapper aborts (live checkout on a
feature branch), 1 session where daily-full never started, 3 sessions with an
empty buy-scan universe (`0 candidates from 0 tickers`), 1 gap
`[VERIFIED — commit b89fb3c audit, 30-session run-log survey]`.

## Revised recommendation ordering

| was | now | why |
|---|---|---|
| R1 re-calibrate `sizing.ceiling` | **R1b** | necessary, **not sufficient** — VetoWeakBuys starves the funnel upstream |
| — | **R0b (new, highest actionable)** | 23 % session-loss rate is an availability defect — proven `[VERIFIED — commit b89fb3c audit above]` and no experiment needed to fix it |
| — | **R0 (new, hypothesis — not yet a decided remedy)** | make `VetoWeakBuysTask`'s floor absolute-or-relative by choice, not relative by construction; NOT shown to improve the book rather than admit lower-quality names — see the experiment plan below before ranking this above R0b |
| R2 in-flight `open_slots` | R2 | unchanged — still a real control failure |

### R0 experiment plan (required before R0 can outrank R0b)

R0's evidence to date only establishes that `VetoWeakBuysTask`'s current relative
floor admits few names; it does **not** establish that a less-selective
absolute/relative policy improves the book rather than admitting lower-quality
names. Because this is an operator-authorizing design for a live capital-deployment
change, R0 stays labeled a **hypothesis to test**, not the highest-priority remedy,
until the following is run and its predeclared criteria are checked (§7.2/§7.4
sanity-and-promotion discipline):

- **Candidate rules** — (a) absolute floor `score >= X` OR the existing relative
  rule, whichever binds looser; (b) relative floor at a raised cross-section
  quantile, e.g. `mean + 0.5·std` instead of `mean + 1.00·std`; (c) hybrid
  absolute-OR-relative. `[ASSUMED — none of (a)/(b)/(c) has been backtested; listed
  as candidates only]`.
- **Windows** — a frozen in-sample calibration window and a disjoint holdout
  window, embargoed per the splitter invariant (§7.2); not yet selected.
- **Baseline** — the current relative-only floor (`max(0.20, mean + 1.00·std)`) on
  the same holdout window.
- **Risk constraints** — turnover delta, concentration/drawdown (max single-name %,
  correlation-guard trigger rate), gross/net exposure; none measured yet for any
  candidate.
- **Predeclared decision criteria** — a candidate promotes only if it improves
  admitted-name quality (realized selection IC of admitted names, not raw admission
  count) **and** does not worsen the risk constraints above, evaluated through the
  §7.4 3-tier promotion gate (Tier 3 required, not Tier 1/2).

**None of the above has been run yet.** Until it is, R0 is a candidate for the next
bounded experiment, not an authorized change, and R0b (proven, no experiment
required) is the higher-ranked actionable item.

## Method warnings this audit surfaced, recorded because they are load-bearing

- **`pipeline_runs.n_buys` and `n_exits` are literally 0 for all 1,536 live rows**
  since 2026-06-01. Dead, not low.
  `[VERIFIED — commit b89fb3c audit, data/runs.alpaca.db pipeline_runs table, all 1,536 rows since 2026-06-01]`
- **`trades.fill_status` is never `'filled'`** — only `NULL` (12,457) or
  `'submitted'` (32) across 12,489 rows. `filled_qty`, `fill_price`,
  `fill_updated_at` are all NULL.
  `[VERIFIED — commit b89fb3c audit, data/runs.alpaca.db trades table, all 12,489 rows]`
- `broker_order_id` NULL-despite-fill is confirmed independently: 2026-07-13
  FTNT/APH/ZM all NULL, all three accepted in the log, all three in the book 07-14.
  This is the same column that produced the orch#854 retraction.
  `[VERIFIED — orch#854, data/runs.alpaca.db 2026-07-13 FTNT/APH/ZM rows + Alpaca filled-order API]`
- **The `ntfy` DECISION headline mis-attributes the blocker.**
  `risk_gate_vol_dropped(N)` is a counter, never the binding constraint — on
  2026-08-05 it was the headline while the real blockers were `no open slots` and
  `correlation_guard`. Counting headlines yields a wrong root-cause histogram
  (already filed as orch#842).
  `[VERIFIED — orch#842, 2026-08-05 ntfy DECISION log vs task-level gate counters]`
- `live_state_snapshots … entry_dates` **values** are stale (GOOG shows 2026-04-20
  though bought 08-04); only the **key set** is trustworthy.
  `[VERIFIED — commit b89fb3c audit, live_state_snapshots GOOG row vs 2026-08-04 fill]`

**Not determined:** true long-market-value per session. Neither `cash` nor
`long_market_value` is logged, so every "idle %" above is a **buying-power ratio**,
confounded by pending-order reserves — not a positions-value ratio. Not estimated.
