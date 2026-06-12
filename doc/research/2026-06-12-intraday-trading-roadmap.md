# From After-Close to Intraday: Research & Roadmap

Status: RESEARCH / ROADMAP (operator-requested 2026-06-12, idle-track).
Owner: claude. Reviewers: codex, operator.
Companion plans: `2026-06-12-engineering-architecture-deep-plan.md` (#108),
`2026-06-12-model-capability-roadmap.md` (#106). This roadmap CONSUMES
their infrastructure (DRPH, GateRegistry, LiveStateV2, provenance) and
does not reorder their milestones — decision #110 sequencing stands.

---

## 0. The claim being evaluated

> "RenQuant decides after the close and only polls intraday — it should
> watch and trade DURING the session."

The claim is half-right. Decomposed, "intraday" is four different
capabilities with wildly different cost/benefit:

| Layer | What it means | Alpha source | Risk of self-harm |
|---|---|---|---|
| **I. Intraday risk reaction** | stops/exits fire in seconds, not 12-min polls | none (loss avoidance) | low |
| **II. Intraday execution** | the SAME daily decisions, executed at better prices | none (cost reduction) | low–medium |
| **III. Intraday signal overlay** | timing entries/exits within the day using intraday features | new, unproven | high |
| **IV. Intraday alpha (HFT-lite)** | decisions FROM intraday data at intraday horizons | new, expensive | very high |

The measured problem this week was **transfer-coefficient loss, not
missing intraday alpha** (eng plan §6: "none of this raises IC; all of
it raises the transfer coefficient — which this week proved is where
the money was being lost"). Layers I–II attack exactly that. Layers
III–IV are research programs with negative priors at our scale
(142-ticker watchlist, ~$10.4k account, panel ESS ≈ 5,901 — the label
ESS measurement says we cannot even feed daily models generously, and
intraday labels are noisier still).

**Recommendation up front: do I now, II next, gate III behind stored
intraday data + a dedicated WF-gate-equivalent, and explicitly shelve
IV** (same discipline as the ensemble shelving, with written reopening
triggers).

## 1. Current state, measured (2026-06-12)

- **Decision run**: `daily104` launchd at 13:55 PT — five minutes
  BEFORE the 13:00 PT close? No: 13:55 PT = 16:55 ET, **25 minutes
  after the NYSE close**. Decisions consume the completed daily bar;
  orders execute at the NEXT session (market orders, `TimeInForce.DAY`).
- **Intraday pass**: `intraday104` launchd, **12-minute cadence** during
  RTH, exit-only (`intraday_sell_104.sh`, Alpaca 5-min bars, IEX feed).
  The NVTS post-mortem measured the cost of this design: a −12% move
  fit entirely between two polls.
- **Broker-side protection**: G1 (RenQuant#308 + strategy#28) just
  armed GTC catastrophe stops at 20% — the first protection that does
  NOT depend on our process being awake.
- **Data**: daily OHLCV parquet store (yfinance/LEAN, restatement
  events observed — KLAC 2026-06-12); `data/intraday/` already holds
  10min/1h parquet for the watchlist; Alpaca free tier = **IEX feed
  only** (~2–3% of consolidated volume; quotes can be stale several
  seconds vs SIP).
- **Clock discipline**: the 2026-06 audit found **217 naive time
  sources**; next DST transition 2026-11-01. Any event-driven intraday
  system multiplies the blast radius of this debt.
- **Account/regulatory**: ~$10.4k. FINRA retired the PDT rule
  (effective 2026-06-04, Notice 26-10) in favor of an intraday-margin
  framework — the old "no 4+ day-trades under $25k" cliff no longer
  binds, but broker-level intraday margin requirements DO. Alpaca's
  implementation of 26-10 must be confirmed before any same-day
  round-trip logic ships (action P2.0 below).

## 2. What the literature actually supports at our scale

- **Execution cost is the reliable edge.** Almgren–Chriss (2001) and
  the entire optimal-execution literature treat arrival-price slippage
  as a minimizable cost, not a forecastable alpha. Perold (1988)
  implementation-shortfall framing: our daily decisions already pay a
  full overnight gap + open-auction spread by trading "market, next
  day". Measuring and halving that cost is bankable without any new
  model. Grinold–Kahn: at fixed IC, PnL scales with the transfer
  coefficient — same money, less risk than new alpha.
- **Intraday alpha decays fast and needs breadth + infrastructure.**
  Intraday reversal/momentum effects (e.g., Heston–Korajczyk–Sadka
  2010 on intraday periodicity) are real but thin per-name; harvesting
  them is a breadth game (hundreds of names, sub-minute data, queue
  modeling). With 142 names and IEX-only data, expected capacity is
  near zero. This matches our own breadth experiment's negative prior
  (#106: E5/E17/E34/E45).
- **Risk reaction is a solved engineering problem.** Broker-resident
  orders (GTC stops, OCO brackets) + a watchdog stream is industry
  standard precisely because cron-polling loses races (our NVTS
  evidence independently rediscovered this).

## 3. Gap analysis by dimension

### 3.1 Data acquisition
| Need | Today | Gap |
|---|---|---|
| Real-time price stream | 5-min IEX bars, polled | Alpaca websocket (`wss://stream.data.alpaca.markets`), IEX free tier streams trades/quotes/bars per-symbol; SIP requires paid plan (~$99/mo, decision point P1.2) |
| Historical minute bars for research | partial 10min/1h parquet | systematic capture job + PIT manifest (publication-lag aware, eng plan §III.3); store BEFORE researching layer III — no data, no experiment |
| Corporate-action awareness intraday | daily restatement only | halts/LULD pauses come over the stream's trading-status channel; must be consumed (a halted name must veto orders) |
| Clock discipline | 217 naive sources | the tz audit's fix list becomes a BLOCKER for any event-driven loop (P0.3) |

### 3.2 Model capability
- Layer I–II need **zero model changes** — the daily PatchTST decision
  stands; only its execution improves.
- Layer III needs: minute-bar feature store, intraday-horizon labels
  (and their ESS will be brutal — uniqueness overlap within a day is
  near total), a separate gated promotion path (an intraday WF gate),
  and honest baselines (VWAP-timing heuristics before any neural
  model). Per #106 discipline: acceptance contracts written BEFORE
  training, DLinear-class baselines required, DSR/PBO controls.
- The current model's staleness (P-MODEL-STALENESS fired: train cutoff
  576d) is a louder problem than intraday timing; #106's retrain rail
  outranks layer III.

### 3.3 Engineering capability
The jump from "cron scripts" to "a process that is alive during the
session" is the real cost:

1. **Process model**: a supervised long-running session daemon
   (launchd KeepAlive) with an event loop consuming the Alpaca stream;
   NOT more frequent cron. Reconnect with jittered backoff, sequence-gap
   detection, heartbeat to the L6 sidecar.
2. **Order state machine**: the broker-reconciliation SM prototype
   (EXT_SELL / QUARANTINE / ADOPT_QTY / FORCED_COVER, idempotent
   client_order_id) graduates from prototype to production — partial
   fills and replaces are the normal case intraday, not the exception.
3. **Safety inversion**: today's G2 caps (25 orders/$5k notional per
   day) were sized for one daily batch; an intraday loop needs
   per-hour AND per-day caps, plus a dead-man switch (no heartbeat ⇒
   TRADING_OFF). The GateRegistry lattice extends naturally: a
   `halted`, `spread_too_wide`, `stream_stale` gate each submit
   verdicts; the same max-join aggregate decides.
4. **State**: LiveStateV2's atomic write is necessary but no longer
   sufficient — concurrent writers (session daemon + daily run) need
   the DB-canonical migration (eng plan S3 + errata E) DONE first.
   **Hard dependency: S3 state-out-of-repo precedes any layer-III
   write path.**

### 3.4 Engineering quality
- **DRPH extension**: today's harness replays a daily bar. Intraday
  needs **event-log replay**: capture the inbound stream (trades,
  quotes, order updates) to an append-only log; replay = feed the log
  back through the decision loop and byte-compare emitted orders. Same
  canonicalization, new transport. This is the layer-I/II gate.
- **Sim fidelity**: the sim fills at bar prices; intraday execution
  claims (slippage halved) must be measured against recorded quote
  data, not assumed. KPI harness before optimization (P1.1).
- **Testing market-hours logic**: half-days, DST, halts, auction
  windows — table-driven tests against the exchange calendar (the
  `_is_nyse_trading_day` helper already exists; extend to sessions).

## 4. Roadmap (phased, each phase independently valuable & abortable)

### P0 — Risk reaction in seconds (1 week, ~5 PRs) — DO NOW
- P0.1 Stream watchdog daemon (read-only): subscribe trades for held
  names + SPY; persist last-tick; alert (ntfy) on >X% adverse moves;
  heartbeat to L6. NO order authority. *Gate: 5 sessions of clean logs.*
- P0.2 OCO/bracket upgrade: replace the polled trailing logic's
  catastrophe leg with broker-resident brackets where Alpaca supports
  them; keep G1 GTC stops as the backstop. *Gate: order-book census
  shows every held name protected broker-side.*
- P0.3 TZ debt burn-down for the session path (the 217-source list,
  filtered to live/ + kernel data paths). *Gate: clock_tz_audit clean
  on the session-critical set.*
- P0.4 Event-log capture (append-only stream log) — feeds DRPH-intraday
  later; zero decision authority.
- P0.5 Dead-man switch: watchdog heartbeat absent ⇒ TRADING_OFF file
  (reuses G2 mechanism).

### P1 — Execution upgrade for the SAME daily decisions (2–3 weeks, ~6 PRs)
- P1.1 **Implementation-shortfall KPI first**: for the last 60 days of
  fills, measure realized price vs (a) decision-time close, (b) next
  open, (c) day VWAP. This is the baseline every later claim is
  audited against. (Data exists in runs.alpaca.db + Alpaca fill
  history.)
- P1.2 Data-plan decision (operator): stay IEX-free vs SIP paid. IEX
  is acceptable for P1 (we are not queue-sensitive); revisit at P2.
- P1.3 Spread-aware marketable-limit orders replacing bare market
  orders (limit at NBBO ± k·spread, cancel-replace ladder, timeout to
  market). *Gate: DRPH-intraday parity + 20-session A/B on shortfall
  KPI, halve-or-revert.*
- P1.4 Entry-time study: current next-open execution vs 10:00 ET vs
  close-auction for OUR decisions (open auctions are the most
  expensive window for retail-size market orders; measured, not
  assumed). Config knob, default unchanged until A/B verdict.
- P1.5 Session daemon gains order authority for EXITS ONLY (the
  intraday_sell pass moves from 12-min cron into the event loop; same
  decision logic, latency 12min → seconds). *Gate: shadow week (log
  intended orders, compare to cron pass), then cutover; cron pass
  retained as fallback.*

### P2 — Intraday signal overlay (gated EXPERIMENT, epic branch only)
- P2.0 Confirm Alpaca's FINRA 26-10 intraday-margin implementation and
  our account's effective limits (written memo, blocker for any
  same-day round-trip).
- P2.1 Six months of captured minute data + PIT manifest before any
  training (the capture from P0.4/P1 accumulates this for free).
- P2.2 Acceptance contract written first (#106 style): baseline =
  VWAP/time-of-day heuristics; intraday ESS computed honestly; DSR/PBO
  controls; promotion only through a dedicated intraday gate.
- Negative prior stated now: at 142 names on IEX data, expected edge
  net of spread is likely ≤ 0. The experiment must beat P1's execution
  baseline, not zero.

### P3 — Intraday alpha: SHELVED
Reopening triggers (all required): P2 overlay shows ≥1 year live
shadow advantage; account ≥ $100k (capacity + data costs); SIP data
funded; breadth ≥ 400 names. Mirrors the ensemble-shelving discipline.

## 5. Cost & dependency summary

| Phase | New infra | Hard dependencies | Est. |
|---|---|---|---|
| P0 | watchdog daemon, event log, dead-man | TZ fixes (P0.3); L6 sidecar | ~5 PRs / 1 wk |
| P1 | KPI harness, limit-order ladder, exit loop | reconciliation SM production; DRPH-intraday | ~6 PRs / 2–3 wk |
| P2 | minute store + intraday gate | S3 state-out-of-repo (errata E); 26-10 memo; 6 mo data | research track |
| P3 | — | shelved | — |

Sequencing vs the mainline: P0 slots into the current S2 window (it
reuses G2/L6/GateRegistry work directly); P1 starts after the umbrella
gate-retirement + reconciliation SM land; P2 is strictly behind S3.
Nothing here reorders #108/#110 — it extends them.

## 6. Honest counter-arguments (anticipating challenge)

1. *"Watching the market all day invites overtrading."* — Layers I–II
   add ZERO new decision authority; the daily model still decides.
   Every intraday order type is either protective or a cheaper
   implementation of an existing decision. The GateRegistry ledger
   makes any drift auditable.
2. *"The 12-min poll is cheap and works."* — NVTS measured its cost.
   And the poll DEPENDS on our box being awake; broker-resident orders
   don't. P0 is mostly about removing single-process risk, which the
   2026-06 incident week showed is our dominant failure mode.
3. *"Why not jump to intraday alpha?"* — ESS ≈ 5,901 on DAILY panels
   already constrains model size; intraday labels at our breadth are
   noise-harvesting. The execution layer pays first and funds the data
   that would make layer III testable at all.

## References
Almgren & Chriss (2001) *Optimal Execution of Portfolio Transactions* ·
Perold (1988) *The Implementation Shortfall* · Grinold & Kahn, *Active
Portfolio Management* (transfer coefficient) · Heston, Korajczyk &
Sadka (2010) *Intraday Patterns in the Cross-Section of Stock Returns* ·
FINRA Regulatory Notice 26-10 (intraday margin; PDT retirement
2026-06-04) · Alpaca Market Data API docs (IEX vs SIP feeds; websocket
streams) · internal: NVTS post-mortem; 2026-06 incident week; label-ESS
measurement; three-point staleness decay; eng plan #108 §III/§IV/S2-S3;
model roadmap #106 acceptance contracts.
