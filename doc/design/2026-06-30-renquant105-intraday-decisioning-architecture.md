# renquant105 — Intraday (盘中) Real-Time Decisioning Architecture (RFC)

STATUS: design / RFC — the ENGINEERING DESIGN is the prerequisite; build is staged after review. Design first, do not rush to build.
DATE: 2026-06-30
SCOPE: orchestrator-owned pipeline/control-plane design. Model rework is explicitly downstream (§8).

---

## 1. Framing — what 105 actually is (operator, 2026-06-30)

renquant105 is an **engineering-capability evolution**, not an alpha hunt:

- **104 = 盘后 (after-close batch):** decide ONCE after the close (`daily_104.sh`, 13:55 PT), place orders for the next open; the intraday loop is **sell-only** (risk exits). The buy decision is a once-a-day, next-bar event.
- **105 = 盘中 (real-time, during-session decisioning):** during market hours, watch the tape + the model's live read and make **full enter / adjust / exit** decisions in real time — catch the trend **entry as it forms** intraday instead of waiting for the next-day batch. Hold for the multi-day trend.

Prerequisite ordering (operator's exact framing):
1. Model capability matters — **but it is NOT the prerequisite.**
2. 105's core = 盘中 real-time decisioning = an engineering evolution.
3. The model needs a big rework eventually to fully exploit 盘中 — **downstream, not the gate.**
4. **The prerequisite is THIS engineering design.**

Explicitly **NOT**: high-frequency, day-trading, or scalping. The holding period stays multi-day; only the **decision/entry timing** moves from next-day-batch to same-session real-time.

---

## 2. Reuse-first principle — repoint, don't rewrite (don't waste prior work)

This is "option A" from the 105 direction decision: **reuse the methodology spine and infrastructure; evolve the batch pipeline to run in real-time.** Inventory of what 105 BUILDS ON (nothing here is rebuilt from scratch):

| Existing asset | Role in 105 |
|---|---|
| **Intraday loop** (`com.renquant.intraday`, 12-min, today `--sell-only`) | The real-time loop already exists — repoint it from sell-only to FULL decisioning. |
| **InferencePipeline** (preflight → score → gates → rotation → emit) | The decision engine — run it intraday, not just after close. |
| **Gate-stack** (P-FUND-FRESHNESS, P-WF-GATE, RealizedVolGate, VetoWeakBuys, ConvictionGate, correlation, sector, QP) — fixed/validated this cycle | Reused verbatim; must be evaluated on live state intraday. |
| **Model serving** (panel scorer: PatchTST primary / XGB) + daily scores | Daily ranking = the conviction-ordered watchlist the intraday loop acts on (§5). |
| **Decision-ledger** (`candidate_scores`, `decision_outcomes` view) + **decision-tree-review skill** | Per-decision audit + forensic review, now at intraday cadence. |
| **Safety** (run-locks, dedup, daily-loss breaker, broker reconciliation, recovery-plan disaster guards, fractional-shares) | Extended to intraday cadence (§7). |
| **Methodology spine** (M1 purged-CV/embargo/triple-barrier/meta-label; M2 gate-stack/champion-challenger/daily retrospective; recall-precision metrics) | The validation discipline carries over unchanged. |

---

## 3. Current architecture (104, 盘后)

```
13:55 PT (after close)  daily_104.sh:
  lock → NYSE guard → pin-align → smoke test → LEAN export → backfill
  → InferencePipeline: preflight(gates) → score(XGB+PatchTST) → vol/veto/conviction/corr gates
     → rotation/QP → SizeAndEmit → place orders (Alpaca, fill next open)
  → audit + dashboard + shadow(PatchTST readonly)

every 12 min (market hours)  intraday loop:
  runner --sell-only  → exits / risk only.  NO new entries.
```

The **buy decision and its timing are coupled to the once-daily batch.** Decoupling them is the whole of 105 Stage 1.

---

## 4. Target architecture (105, 盘中) — the six engineering pieces

| # | Piece | Today | 105 target | Reuses |
|---|---|---|---|---|
| 1 | **Real-time decision loop** | batch once + intraday sell-only | full enter/adjust/exit on a session cadence | the intraday loop + the runner |
| 2 | **Real-time data plane** | daily bars (stale mid-session) | live quotes/last-trade during the session | Alpaca live broker conn |
| 3 | **Live model serving** | score once after close | daily conviction ranking served as the live watchlist; intraday confirmation on price | panel scorer + daily scores |
| 4 | **State + gate consistency** | batch snapshot | positions/cash/pending-orders/gates evaluated on LIVE state each tick | gate-stack + live_state + ledger |
| 5 | **Entry-timing logic** | next-day open | act when the trend confirms intraday (NEW logic, small) | candidate/rotation framework |
| 6 | **Safety / idempotency** | day-level locks | dedup vs pending orders, intraday breakers, partial-fill handling, max intraday turnover | run-locks, breaker, reconciliation |

**Design stance on the model (key):** in Stage 1–2 the **model signal stays daily** (which names + conviction, computed pre-market/after prior close); the 盘中 engineering decides **WHEN to act** on that daily signal using live data (entry timing). Intraday *re-scoring* of the model is Stage 3 = the downstream model rework. This keeps 105's prerequisite purely engineering, exactly as specified.

---

## 5. The hard design decisions (need review)

1. **Cadence.** Fixed interval (reuse the 12-min tick; simplest) vs event-driven (on tape moves / level breaks) vs hybrid. Proposal: **Stage 1 = fixed 12-min tick** (reuse existing loop), event-driven deferred to Stage 2.
2. **Signal source.** Daily ranking + intraday price timing (Stage 1–2) vs intraday re-scoring (Stage 3, model rework). Proposal: **daily ranking + timing first.**
3. **Entry-timing policy.** Immediate-on-conviction vs intraday-trend-confirmation (e.g. above VWAP / prior-day-high break with volume) vs pullback-to-level. Proposal: **start immediate-on-conviction at the tick** (equivalent to "trade the daily signal intraday instead of next-day"), then layer confirmation in Stage 2 — so Stage 1 is a clean, measurable A/B vs the batch baseline.
4. **State consistency.** How to avoid double-acting across ticks: a per-name in-flight lock keyed on pending broker orders + the decision-ledger; idempotent emit. Reuse broker_reconciliation.
5. **Safety envelope.** Max intraday entries/turnover per day; intraday daily-loss breaker; halt-on-anomaly (stale quotes, reconciliation mismatch); fractional + min-notional already covered.

---

## 6. Staged evolution path

- **Stage 1 — Decouple entry timing from the batch (THE prerequisite build).** Repoint the intraday loop from `--sell-only` to **full decisioning**: read the daily conviction-ranked watchlist, evaluate the full gate-stack on live state each tick, and enter admitted names intraday (same gates, same sizing, same safety) instead of queuing for next-day open. Minimal new code (mostly removing the sell-only restriction + wiring the buy path + dedup-vs-pending). Immediately measurable: does same-session entry beat next-day-batch entry on the same signal? (A/B via the decision-ledger.)
- **Stage 2 — Entry-timing intelligence.** Add intraday trend-confirmation / pullback logic so entries fire at better intraday points, not just at the tick.
- **Stage 3 — Real-time re-scoring (DOWNSTREAM, needs model rework).** The model reacts to intraday developments (event-driven, intraday-aware features). This is where the "big model rework" lives — after the engineering scaffold exists.

Each stage is independently shippable and A/B-measurable against the prior one via the decision-ledger + decision-tree-review.

---

## 7. Engineering contracts + risks (per piece, reusing existing safety)

- **Loop:** at-most-one decisioning run in flight (reuse run-lock at intraday cadence); a tick that overruns its budget is skipped, not queued.
- **Data plane:** every decision stamps the quote age; stale quotes (> threshold) → skip entries (fail-safe), exits still allowed.
- **State/gates:** the gate-stack must read LIVE positions/cash/pending orders, not a batch snapshot; conviction/vol/corr/sector evaluated per tick; idempotent emit keyed on the ledger.
- **Idempotency:** never enter a name with a pending/unsettled order for it (dedup vs broker open orders + ledger) — the #1 intraday failure mode.
- **Breakers:** intraday daily-loss breaker; max intraday turnover/entries; halt on reconciliation mismatch. Reuse the recovery-plan disaster guards.
- **Provenance:** every intraday decision writes a decision-ledger row (same schema) so the daily retrospective + decision-tree-review work unchanged.

---

## 8. Explicitly DOWNSTREAM (not the prerequisite)

- **Model rework** (intraday-aware features, real-time re-scoring, the "big model change") = Stage 3, after the engineering scaffold.
- **Alpha / signal-quality search** (directional / analyst / breadth — all honest NULLs this cycle) = a separate track, NOT the 105 engineering prerequisite. Parked.

---

## 9. Open questions for the operator / Codex

1. Cadence: confirm fixed 12-min tick for Stage 1, or do you want event-driven from the start?
2. Entry-timing: confirm "trade the daily signal intraday" as the Stage-1 measurable baseline (cleanest A/B), with confirmation logic in Stage 2?
3. Safety envelope numbers: max intraday entries/day, intraday turnover cap, stale-quote threshold.
4. Is Stage 1 (decouple entry timing, reuse the loop) the right minimal prerequisite to build first?
