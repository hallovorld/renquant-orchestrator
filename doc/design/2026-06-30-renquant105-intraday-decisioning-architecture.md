# renquant105 — Intraday (盘中) Real-Time Decisioning Architecture (RFC)

STATUS: design / RFC — the ENGINEERING DESIGN is the prerequisite; build is staged after review. Design first, do not rush to build.
DATE: 2026-06-30
REVISION: r2 (2026-06-30) — addresses the Codex review of `c976ed8`. The seven blocking points are answered by new contract sections (§6 data-time, §7 order lifecycle, §8 per-repo slices + merge order, §9 measurement plan, §10 safety defaults, §11 dependencies); the point-by-point map is §16.
SCOPE: orchestrator-owned control-plane design that *coordinates* a cross-repo build. The runtime decision logic (pipeline) and broker order lifecycle (execution) live in their own repos per the operating model — this RFC defines the contracts and merge order, it does NOT authorize cross-repo behavior changes from orchestrator alone (§8). Model rework is explicitly downstream (§14).

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
| **Safety** (run-locks, dedup, daily-loss breaker, broker reconciliation, recovery-plan disaster guards) | Extended to intraday cadence (§7, §10). |
| **Methodology spine** (M1 purged-CV/embargo/triple-barrier/meta-label; M2 gate-stack/champion-challenger/daily retrospective; recall-precision metrics) | The validation discipline carries over unchanged. |

> **NOT yet a reusable primitive:** fractional shares. The fractional-share chain is currently un-mergeable (§11) — Stage 1 must NOT assume it. Stage 1 sizes in **whole shares** with the existing min-notional guard.

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

**Design stance on the model (key, and it makes leakage trivially provable — see §6):** in Stage 1–2 the **model signal stays daily** — the score vector is computed pre-market / after the prior close and is **frozen for the whole session**. The 盘中 engineering decides **WHEN to act** on that frozen daily signal using live price (entry timing). Intraday *re-scoring* of the model is Stage 3 = the downstream model rework. This keeps 105's prerequisite purely engineering, exactly as specified.

---

## 5. The hard design decisions (proposals — need review)

1. **Cadence.** Fixed interval (reuse the 12-min tick; simplest) vs event-driven (on tape moves / level breaks) vs hybrid. Proposal: **Stage 1 = fixed 12-min tick** (reuse existing loop), event-driven deferred to Stage 2.
2. **Signal source.** Daily ranking + intraday price timing (Stage 1–2) vs intraday re-scoring (Stage 3, model rework). Proposal: **daily ranking + timing first** (score frozen at T-1 close — §6).
3. **Entry-timing policy.** Immediate-on-conviction vs intraday-trend-confirmation (e.g. above VWAP / prior-day-high break with volume) vs pullback-to-level. Proposal: **Stage 1 = immediate-on-conviction at the tick as a *plumbing/operational-correctness baseline*, explicitly NOT an alpha claim** (§9, §7-point); intraday confirmation (the part that could add information) is Stage 2.
4. **State consistency.** Avoid double-acting across ticks via a per-name in-flight lock keyed on pending broker orders + the decision-ledger; idempotent emit. Full state machine in §7.
5. **Safety envelope.** Proposed conservative defaults in §10 (no longer left open).

---

## 6. Data-time / as-of contract (answers Codex #1)

Stage 1's safety case rests on one invariant: **the model/gate inputs are frozen at the prior close; the only live input is price, used for *timing*, never fed back into the model or the freshness gates.** Per-input as-of rules:

| Input | As-of / freshness rule | Stale / violation behavior |
|---|---|---|
| **Daily model score (PatchTST/XGB rank + conviction)** | Frozen as-of **T-1 close** (or pre-market build); **never** recomputed intraday in Stage 1 | If the frozen vector is missing/older than 1 trading day → no intraday entries this session (sell-only fallback) |
| **Fundamentals / sentiment / analyst** | Vendor snapshot date, evaluated **once at session start** by the existing P-FUND-FRESHNESS gate (they do not change intraday) | Same as 104: fails the freshness gate → name not admitted |
| **Quote / last-trade (live)** | `age = now − exchange_ts`; entries require `age ≤ quote_staleness_entry` (§10) | age over threshold → **skip entry** (fail-safe); exits still allowed up to a looser bound |
| **Current-day partial OHLCV** | **NOT admitted into any model input or freshness gate** in Stage 1 (within-bar look-ahead, unvalidated). Partial-bar price/VWAP/volume may be read **only** by the Stage-2 entry-timing trigger, which is outside the model | If a Stage-1 code path tries to feed a partial bar into the model/gates → hard fail (assertion), not silent |
| **Cash / positions / pending orders** | Live broker state snapshotted at **tick start**; pending orders included in the reserved-cash ledger (§7) | snapshot older than the tick, or reconciliation mismatch → halt new entries, reconcile |

**No-leak proof obligation (test, not prose):** a replay test asserts `score_vector(tick T) == score_vector(T-1 EOD)` for every tick in a session, and that no gate/model input reads a timestamp `> T-1 close` except the live quote used purely for the timing trigger. Because the decision content is frozen at T-1 close, a 10:00 vs 12:00 decision differ **only** in whether the live price cleared the timing trigger — there is structurally no close/after-close data path into the decision. (When Stage 3 introduces intraday re-scoring, this section must be rewritten with a point-in-time feature contract; Stage 1/2 deliberately sidestep it.)

---

## 7. Order lifecycle / idempotency state machine (answers Codex #2)

"Dedup vs pending" is the #1 failure mode; here is the concrete machine. Lifecycle states per (account, symbol, session):

```
NONE → INTENDED → SUBMITTED → ACCEPTED → PARTIALLY_FILLED → FILLED
                       │            │              │
                       ├→ REJECTED  ├→ CANCELED    └→ (remainder) CANCELED
                       └→ STALE_PENDING (age > max_pending_age) → reconcile → CANCELED/FILLED
```

- **Idempotency key:** `intent_id = hash(account, symbol, trading_day, side, daily_signal_version)`. One INTENDED row per intent; the broker submit carries `intent_id` as the client order id so a double-submit is rejected at the broker, not just locally.
- **Re-emit rule (Stage 1):** a name is re-emittable **only** when it has *no* open/pending order and *no* fill for the same `intent_id` this session → **at most one entry per name per session**. (Re-entry after a same-session exit is a Stage-2 question, deliberately excluded.)
- **Cash reservation:** maintain `reserved_cash = Σ notional(pending + unsettled buys)`. Sizing uses `available = broker_cash − reserved_cash`, never raw broker cash — this is what prevents two overlapping ticks from each spending the "same" dollar.
- **Partial fills:** next tick sizes the **remainder only** *if still admitted by the full gate-stack*; if conviction/gates have dropped, **cancel the remainder** rather than chase.
- **Duplicate prevention across overlapping ticks / restarts:** the intraday run-lock guarantees at-most-one tick in flight; on process restart the loop **rebuilds the in-flight set from broker open-orders + the ledger and reconciles BEFORE any emit** (reconcile-before-emit). The `intent_id` client-order-id dedups even if a tick double-fires.
- **Reconciliation mismatch** (broker open-orders ≠ ledger) → halt new entries for the session, alert, exits still allowed.

---

## 8. Per-repo build decomposition + merge order (answers Codex #6)

Per the subrepo operating model, no single repo owns this. Stage 1 splits into three PRs with their own acceptance tests, and a **strict merge order** (orchestrator flips last and stays default-OFF until the other two are pinned):

| Order | Repo | Owns | Acceptance tests |
|---|---|---|---|
| 1 | **execution** (broker adapter) | Order-lifecycle state machine (§7), `intent_id` client-order-id honored at submit, reserved-cash accounting, reconcile-before-emit on restart, stale-pending cancel | state-machine unit tests; duplicate-submit rejected; partial-fill accounting; restart reconcile |
| 2 | **pipeline** (renquant-common runtime) | Runtime decision logic — gate-stack on **live** state, sizing against `available` (§7), idempotent emit keyed on `intent_id`, partial-fill remainder sizing, dedup-vs-pending | **sim-parity**: intraday-mode emits *identical* decisions to batch-mode given identical (frozen-score, snapshot-state) inputs; dedup unit tests; reserved-cash never negative |
| 3 | **orchestrator** (this repo) | Scheduling (repoint the intraday loop to full-decisioning mode), run-bundle/provenance per tick, control-plane flag + canary allowlist + kill switch, intraday decision-ledger rows, the A/B + replay harness (§6, §9) | flag default-OFF; canary allowlist enforced; per-tick bundle persisted; replay/no-leak test (§6); readonly-mode logs decisions without placing |

Boundary compliance (CLAUDE.md): orchestrator does **not** implement broker adapters (execution) or decision/sizing internals (pipeline) — it schedules, provenances, and gates rollout. The orchestrator change is inert (default-OFF / canary-only) until execution+pipeline are merged AND pinned.

---

## 9. Stage-1 measurement plan — operational-correctness gate, alpha deferred (answers Codex #3 & #7)

Codex #3 (valid experiment, not a deployment-driven one) and #7 (Stage 1 is plumbing, not an alpha claim) point the same way; the resolution is to make the **Stage-1 gate operational/execution-quality**, pre-registered and falsifiable, and to **explicitly defer the alpha estimand** rather than pre-register a heavyweight alpha trial for a stage whose alpha may be null by design.

**Stage-1 PASS gate (pre-registered, all required):**
- **No-leak:** the §6 replay invariant holds for every tick in every canary session.
- **Idempotency:** zero duplicate entries across the canary window; `reserved_cash ≥ 0` always; no order exceeds the §10 envelope.
- **Reconciliation:** at session close, broker state == ledger == run-bundle, every session.
- **Execution-quality A/B (matched pairs):** unit of observation = `(symbol, session)` admitted by **both** paths. Baseline = the next-day open 104 actually used. Measure the **fill/slippage distribution** (intraday-trigger fill vs next-open), turnover, exposure, rejected/partial counts. Stage-1 success requires execution cost **not worse** than the batch baseline within a pre-set tolerance — this is an *execution* readout (entry fill), not a return readout.
- **Rollout discipline:** **readonly** (decide + log, place nothing) for ≥ K sessions → **canary** 1–2 allowlisted names live → expand only after ≥ N (pre-set, e.g. ≥ 20) clean matched live entries. The minimum sample is fixed *before* the canary starts.

**Explicitly DEFERRED (not a Stage-1 gate):** the **alpha estimand** — "does same-session entry add *return*-alpha vs the next-day batch over the multi-day hold?" — needs a much larger matched panel, is regime-confounded, and is exactly the kind of pre-registered alpha trial that would be **over-engineering validation ahead of a demonstrated edge** (operator lesson, 2026-06-28). It accrues passively as a secondary, larger-N readout in the decision-ledger and is judged at **Stage-2 scoping**, not used to gate Stage 1. Stage 1 ships on operational correctness + non-worse execution cost; if it turns out alpha-null, that is an accepted, pre-stated outcome — the engineering scaffold is the deliverable.

---

## 10. Safety envelope — proposed conservative defaults (answers Codex #4)

Starting values, debatable, but no longer blank — so the first build PR cannot invent policy while coding. Sized for the current ~$10.5k live book:

| Control | Proposed Stage-1 default | Rationale |
|---|---|---|
| Max intraday new entries / day | **3** | ≤ the typical 104 batch count; conservative |
| Max intraday notional deployed / day | **15% of equity** | caps a bad-signal day |
| Max intraday turnover / day | **25% of equity** | discourages churn; this is multi-day hold, not day-trading |
| Quote-staleness threshold (entries) | **5 s** soft / **15 s** hard-skip | entries need a fresh tape |
| Quote-staleness threshold (exits) | **60 s** | exits favor action over freshness |
| Max per-tick run duration | **90 s** | well under the 12-min cadence; overrun → skip, don't queue |
| Max pending-order age | **10 min** (< 1 tick) | force cancel + reconcile before re-emit |
| Intraday daily-loss breaker | **reuse 104's threshold** → halts NEW entries for the session; exits allowed | reuse existing guard |
| Global kill switch | env flag `RENQUANT_INTRADAY_DECISIONING` default **off**; canary allowlist required | nothing live until explicitly enabled |

---

## 11. Dependencies & blockers (answers Codex #5)

- **Fractional shares — BLOCKER, do not assume available.** Per Codex (2026-06-30) the chain is un-mergeable: execution **#19** has red CI + broker stop/classification hazards; pipeline **#153** lacks full fractional lifecycle / sim parity; strategy **#36** is blocked behind both. → Stage 1 sizes in **whole shares with the existing min-notional guard**; fractional is a **Stage-2 dependency**, tracked against that chain, and is NOT cited as a Stage-1 safety primitive. *(To verify independently before the build PR; carried here as a stated dependency, not an assumption.)*
- **Live-quote data plane** — Alpaca live quote/last-trade entitlement + rate-limit headroom for per-tick reads across the watchlist. Must be confirmed before Stage-1 execution-quality testing.
- **Broker open-orders API** — required for §7 dedup-vs-pending and reconcile-before-emit.
- **Intraday decision-ledger write path** — the ledger must accept intraday-cadence rows (schema unchanged) for the §9 A/B and the daily retrospective.

---

## 12. Staged evolution path

- **Stage 1 — Decouple entry timing from the batch (THE prerequisite build).** Repoint the intraday loop from `--sell-only` to **full decisioning**: read the frozen daily conviction-ranked watchlist (§6), evaluate the full gate-stack on live state each tick (§7), and enter admitted names intraday (same gates, same sizing, same safety) instead of queuing for next-day open. Built as three ordered per-repo PRs (§8); default-OFF → readonly → canary (§9). Gate = operational correctness + non-worse execution cost (§9), not alpha.
- **Stage 2 — Entry-timing intelligence.** Add intraday trend-confirmation / pullback logic (the part that can add information) so entries fire at better intraday points; this is where the alpha question is first legitimately asked. Fractional-share dependency unblocks here.
- **Stage 3 — Real-time re-scoring (DOWNSTREAM, needs model rework).** The model reacts to intraday developments (event-driven, intraday-aware features). The "big model rework" lives here — after the engineering scaffold exists. Rewrites the §6 contract with a point-in-time feature spec.

Each stage is independently shippable and measurable against the prior one via the decision-ledger + decision-tree-review.

---

## 13. Engineering contracts + risks (per piece) — index

These now live in dedicated sections: loop run-lock/skip-on-overrun (§10), data plane / quote-age (§6, §10), state+gate live evaluation & idempotency (§7), breakers & envelope (§10), provenance (every intraday decision writes a decision-ledger row, same schema — §9). The #1 risk remains dedup-vs-pending (§7).

---

## 14. Explicitly DOWNSTREAM (not the prerequisite)

- **Model rework** (intraday-aware features, real-time re-scoring, the "big model change") = Stage 3, after the engineering scaffold.
- **Alpha / signal-quality search** (directional / analyst / breadth — all honest NULLs this cycle) = a separate track, NOT the 105 engineering prerequisite. Parked.

---

## 15. Open questions for the operator / Codex

1. Cadence: confirm fixed 12-min tick for Stage 1, or event-driven from the start?
2. Entry-timing: confirm Stage-1 immediate-on-conviction as the **plumbing/operational-correctness baseline** (not an alpha claim), with confirmation logic in Stage 2?
3. Safety envelope (§10): are the proposed conservative defaults acceptable as starting values?
4. Measurement (§9): is the operational-correctness gate + deferred-alpha framing the right Stage-1 bar, or do you want an alpha pre-registration up front?
5. Is the per-repo decomposition + merge order (§8) correct, and who owns each slice?

---

## 16. Review-response map — Codex review of `c976ed8`

| # | Codex point | Disposition | Where |
|---|---|---|---|
| 1 | Data-time contract underspecified | **Accepted** | §6 + replay no-leak test |
| 2 | Order lifecycle/idempotency too high-level | **Accepted** | §7 state machine, intent_id, reserved-cash |
| 3 | Stage-1 A/B not a valid experiment | **Accepted with refinement** — pre-registered operational/execution-quality gate; alpha estimand explicitly deferred (not a Stage-1 gate) to avoid over-engineering validation ahead of a demonstrated edge | §9 |
| 4 | Safety envelope numbers can't stay open | **Accepted** | §10 defaults |
| 5 | Dependency reality (fractional chain) | **Accepted** | §11; §2 note — fractional removed from available primitives |
| 6 | Repo ownership boundaries | **Accepted** | §8 per-repo slices + merge order + acceptance tests |
| 7 | Entry-timing baseline too naive | **Accepted** | §5.3 + §9 — Stage 1 is a plumbing baseline, readonly/canary first, success even if alpha-null |
