# G1 (cash-drag / capital deployment) — ABANDONED dossier

**Status: ABANDONED by operator decision, 2026-07-20** ("我认为你没有能力解决 g1
… 放弃 g1"). This document preserves all research + data so the work is not lost
if anyone re-opens it. Written honestly, including the many wrong turns.

## 1. What G1 was
Reduce CASH DRAG / deploy more capital. The live book (Alpaca paper, renquant-104)
sits at **~87% cash, 3 holdings (APH/AVGO/FTNT), ~$10,654, flat** and has not
grown its invested % for weeks. The operator's framing (2026-07-19): *"g1 不是每支
买一样多钱，是买更多钱来解决 cash 太多效率太低"* — a capital-deployment /
sizing / execution problem, NOT the equal-weight prereg I originally (wrongly)
chased. (The equal-weight prereg lineage v3→v7 concluded INFEASIBLE-at-horizon —
true but irrelevant to the real G1.)

## 2. Facts about the "no-buy" state (locators in §7; ALL claims derived from
`runs.alpaca.db` or live state files are POINT-IN-TIME OBSERVATIONS, not
immutable ground truth — the DB/state mutate and were not snapshotted. Observed
during the 2026-07-20 investigation session; the exact query timestamp within
that session was not separately logged, so treat "as of 2026-07-20" as the
precision bound, not a specific minute. Re-running the same queries today may
return different rows.)
- **The decision engine WAS deciding to buy, as of the observation above.**
  `runs.alpaca.db trades`, queried 2026-07-20: **37 buy-side orders placed
  across 12 days 2026-06-22→07-20** (e.g. 06-23 had 10) — a point-in-time
  query result, not a durable count. So at observation time this was NOT a
  decision/gate freeze — the engine wanted to buy and placed orders.
- **104 places orders POST-CLOSE (盘后下单) by design** (operator, 2026-07-20).
  Buys are `entry_order_type="limit"`, +10 bps marketable limit, TIF=DAY
  (renquant-execution alpaca broker port — this is a code/config fact, durable,
  not point-in-time). So an order showing `accepted / buy_pending` when
  inspected is NORMAL post-close timing — it is queued for the next open, not
  a stuck order. The 07-20 limit prices were at/above market (ZM limit ≈91.00
  vs close 90.91) — NOT a bad-limit-price problem.
- **`trades.fill_status` showed 0 'filled' among the 37, as of the same
  2026-07-20 point-in-time query** (32 None + 5 'submitted'). This is the
  PLACEMENT record; the fill reconciliation (next-open) was NOT cleanly
  verified — do NOT conclude "orders never fill" from this alone (I did, and
  it was premature). The account being stuck at 87% cash / 3 holdings is the
  real signal that invested-% is not growing; whether that is (a) fills not
  happening, (b) buys too small (1-share ~$90–170 orders barely move a $10.6k
  book's cash%), or (c) sells offsetting buys, was NOT resolved.
- **SHADOW vs LIVE diverge.** The 07-20 SHADOW leg (PatchTST scorer, shadow book)
  showed `no trade` with funnel-integrity `STRUCTURAL_BLOCK / wash_sale_mass_block`
  — a MASS of names (GE/EQIX/META/DUK/GILD/GM) stamped `last_sell_dates=2026-06-26`
  with "P/L unknown — binary block" in `live_state.alpaca_shadow.json`. This
  matches the known [wash-sale STATE-EXT-SELL date bug] (GE/EQIX 06-26 recurrence).
  BUT the LIVE state has NO 06-26 cluster and the LIVE leg on 07-20 reached
  `ECONOMIC_TRADE` and placed BWXT + ZM buys. So the wash-sale mass block is a
  SHADOW-book artifact, not the live freeze.

## 3. What the freeze was NOT (ruled out, honestly — my wrong turns)
Every one of these I asserted as "the root cause" then had to retract:
- **Per-ticker tournament staleness** — real (63 models stale from a 600-vs-2400
  retrain-timeout config drift); fixed + verified via RenQuant#518 (141/141
  models retrained today). But the retrain did NOT change n_candidates (still 0),
  so it was NOT the freeze cause.
- **panel config-fingerprint mismatch** — I compared the UMBRELLA config against
  the runtime scorer (wrong pairing). `assert_consistent(RUNTIME_config, panel-ltr)`
  PASSES. Not the cause. (Re-stamping would have BROKEN the passing runtime match.)
- **panel `missing_panel_score`** — that was the SMOKE contract harness
  (subrepo-smoke-gbdt / smoke data), invalid. The REAL panel scores fine (70/70).
- **stale fundamentals** — the alpha158 TRAINING dataset is April-stale, but the
  SERVING feed (`sec_fundamentals_daily.parquet`) is FRESH (07-17). Not the cause.
- **a "fleet of failing scheduled jobs"** — over-claimed; most recent nonzero
  exits are DETECTION jobs signaling by design, and the work-job nonzeros are
  STALE statuses (retrain-panel104 last ran 04-26). Not a live fleet failure.

## 4. Work delivered during the G1 investigation (valid, kept)
- **RenQuant#518** (MERGED): mirror retrain-timeout 600→2400 into the umbrella
  working-copy config; deployed + verified (141/141 trainable watchlist models
  retrained 2026-07-20). A real reliability fix (unblocks the weekly tournament
  retrain), independent of the freeze.
- **RenQuant#519** (MERGED): GOAL-5 AC5 — daily-entrypoint import check in the pin
  sweep (catches the g5-class non-aliased cross-repo import break). Real GOAL-5 win.
- **Job-health monitor** (branch `feat/g5-job-health-scan`, orch, 20 tests green,
  NOT pushed): `check_launchd_job_health()` in ops/run_surface_drift_check.py.
  Has 3 false-positive classes (detection-jobs, stale-statuses, no-recency) — needs
  a proper WORK-vs-DETECTION + last-SUCCESS-recency redesign before it is useful.

## 5. Honest post-mortem (why G1 was abandoned)
I thrashed for a full day: asserted ~6 different "root causes" and retracted each
after deeper checking. Root failure: **I diagnosed decision-gates before
establishing the basic operating model** — that 104 places orders POST-CLOSE,
that SHADOW and LIVE legs differ, that `n_buys` counts FILLED (not placed) buys,
that `trades.fill_status` is the first thing to read. Repeated instances of the
recorded lesson "verify ground truth before asserting." The operator correctly
judged I was not converging.

## 6. If re-opened — where to actually start
1. Read `trades.fill_status` + the next-open fill reconciliation FIRST: do the
   post-close orders actually fill at open, or not?
2. If they fill: the cash-drag is a SIZING problem (1-share orders don't deploy a
   $10.6k book) → size up (Kelly target %, min-notional, conviction).
3. If they do NOT fill: an execution/reconciliation problem at the post-close→open
   handoff — investigate the broker order lifecycle, not the decision gates.
4. Keep SHADOW (wash_sale_mass_block, PatchTST) strictly separate from LIVE.
Do NOT re-run the decision-gate diagnosis; it is a dead end for this problem.

## 7. Evidence & locators (per material claim)
Each claim in §2 with a durable/recoverable locator, so a restart reproduces the
evidence rather than trusting the narrative. Machine paths are relative to the
umbrella `/Users/renhao/git/github/RenQuant`. **DBs and state files MUTATE and
were NOT snapshotted** — every claim derived only from `runs.alpaca.db` or a
live state JSON file is a POINT-IN-TIME OPERATOR OBSERVATION as-of the
2026-07-20 investigation session, not a durable/reproducible fact; re-running
the same query later can return different rows (downgraded from "verified
ground truth" / "reproducible via query" per review — neither framing is
accurate for an unsnapshotted, mutable source). Only the dated log-file and
code/commit locators below are durable/reproducible as stated.

| Claim | Locator | Class |
|---|---|---|
| 37 buy orders / 12 days, 0 filled; fill_status {32 None, 5 submitted} | `sqlite3 data/runs.alpaca.db` → `SELECT trade_date,action,fill_status FROM trades WHERE trade_date>='2026-06-15' AND action LIKE '%buy%'` (all `buy_pending`) | **POINT-IN-TIME** observation, queried during the 2026-07-20 investigation session (exact minute not separately logged); DB not snapshotted, rows can change on re-run |
| 07-20 LIVE leg ECONOMIC_TRADE, placed BWXT+ZM | `logs/daily_104/2026-07-20.log` @ 14:06–14:07 UTC ("funnel integrity: verdict=ECONOMIC_TRADE … buys=2"; "Order 4c2d9013 … BUY BWXT … ACCEPTED"); run_id `2026-07-20-live-54ea6604` | dated log path + timestamp |
| 104 places orders post-close; buy=limit +10bps DAY | operator statement 2026-07-20 + `renquant-execution` alpaca broker port (`entry_order_type="limit"`, `limit_price_offset_bps=10`, `TimeInForce.DAY`) | code + operator |
| 07-20 SHADOW no-trade = wash_sale_mass_block, 06-26 cluster | `logs/daily_104/2026-07-20_shadow.log` @ 14:33–14:34 ("funnel_integrity … STRUCTURAL_BLOCK … fired=['wash_sale_mass_block']"; `DROP_WashSaleFilter [GE/EQIX/…] sold 24d ago`) | dated log path + timestamp |
| SHADOW state 06-26 last_sell cluster; LIVE state has none | `backtesting/renquant_104/live_state.alpaca_shadow.json` vs `live_state.alpaca.json` `last_sell_dates` | **POINT-IN-TIME observation** (state mutates; no snapshot) |
| 70/70 panel scoring | `logs/daily_104/2026-07-20_shadow.log` @ 14:34:36 ("scored 70/70") | dated log path + timestamp |
| 141/141 trainable watchlist models retrained 07-20 | `backtesting/renquant_104/models/*/*-policy-metadata.json` `trained_date=2026-07-20`; marker `models/.last_tournament_retrain.json` (exit_code 0) | **POINT-IN-TIME** (models/ mutates on next retrain) |
| retrain-timeout config fix 600→2400 | RenQuant#518 (MERGED, umbrella `2333959`); `backtesting/renquant_104/strategy_config.json` | commit / PR (durable) |
| GOAL-5 AC5 daily-entrypoint check | RenQuant#519 (MERGED) | commit / PR (durable) |
