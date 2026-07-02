# renquant105 — Intraday (盘中) Real-Time Decisioning Architecture (RFC)

STATUS: design / RFC — the ENGINEERING DESIGN is the prerequisite; build is staged after review. Design first, do not rush to build.
DATE: 2026-06-30
REVISION: r13 (2026-07-02) — **measurement-integrity pins (amendment A5.1-A5.3, `doc/design/2026-07-01-104-105-design-review-amendments.md`): a gate-input census requirement, a pre-declared entry order type, and a named quote-feed-quality blocker.** These close three ways Stage-1's own no-leak proof and pilot-data corpus could otherwise be silently unenforceable or contaminated: (1) §6's four-class no-leak replay test can only check inputs someone classified — the regime detector, earnings-blackout calendar, and (the STATE-EXT-SELL-adjacent one) mid-session-mutating wash-sale `last_sell_dates` were not named; a required gate-input census artifact + replay-test assertion against it closes the gap. (2) §10 now pre-declares the Stage-1 entry order type (market vs. marketable-limit at a pre-declared NBBO±x bps) so the pilot corpus is not a silent mixture across order types, which would dominate and contaminate the future §9.4 experiment's implementation-shortfall measurement. (3) §11's live-quote-data-plane blocker now explicitly requires either a SIP/consolidated feed subscription or a recorded, quantified acceptance of IEX bias — Alpaca's free-tier "NBBO" is IEX-local and does not even carry the §9.2c synthetic batch reference's required primary-listing opening-auction print. NOTE: a separate, parallel amendment-integration (A2, broker-regulatory/settlement envelope) may also be landing as its own "r13" on a different branch at review time — if both merge, a human renumbers one of them; the two touch disjoint parts of §7/§10/§11 and do not conflict in substance. Integration map in **§22**. Prior: r12 (2026-06-30) — **rollout-boundary fix (Codex r11 review): freeze Stage-1 live exposure at the pre-declared canary envelope, solely for data collection.** Operational correctness (orders emitted safely) gates whether the canary may **run at all**; it does **NOT** authorize **expansion** or general **go-live**, because moving entries intraday can be operationally clean yet economically unacceptable — expanding the canary would deploy an unvalidated timing policy to more capital, not merely collect bounded pilot data. So the "expand cautiously on continued clean ops" language is **removed**: Stage-1 live exposure is **FROZEN** at the pre-declared allowlist + notional cap; **NO expansion** beyond that envelope and **NO general go-live** until EITHER the deferred simplified experiment-prereg PR (§9.4) uses the collected pilot data to supply an **EXPLICIT AUTHORIZING decision**, OR the operator explicitly **accepts the economic risk in a SEPARATE RECORDED decision**. The canary envelope is now bounded explicitly — a maximum **DURATION**, a cumulative **LOSS BUDGET**, and a **STOP CONDITION** — so "extend to collect data" cannot become indefinite production by inertia: hitting the duration/loss-budget without an authorizing decision → **HARD halt (revert to 盘后 batch)**, never silent continuation. Response map in **§21**. Prior: r11 (2026-06-30) — **convergence: split out the Stage-1 statistics; Stage-1 downgraded to operations-only** per an agreed decision between the operator, this author, and Codex to STOP the statistics-patch loop (r6->r10, all on the Stage-1 synthetic-baseline non-inferiority protocol). The agreement: the synthetic batch fill is a **diagnostic reference, not a real control group**; there are **not yet enough independent trading sessions** to estimate the paired variance; and the **10-bps threshold / required sample size cannot be settled on paper before data exists**. So this RFC now keeps ONLY the settled **ENGINEERING** — the 盘中 real-time decision loop, real-time data plane, live model serving, real-time state/gate consistency, entry-timing logic, and the **SAFETY envelope** (idempotency, reconciliation, quantity accounting, kill-switch). The over-designed statistical protocol is **removed**: the separate pre-registration file `doc/design/2026-06-30-stage1-synthetic-baseline-prereg.md` is **deleted from this PR** (git history preserves it) and will be re-submitted later as a **separate, SIMPLIFIED experiment-prereg PR finalized against real pilot data**. Stage-1 now runs **SHADOW / READONLY, operations-only**, to accumulate real paired-session execution data; it **may not claim an execution-quality PASS**; the synthetic baseline is a **diagnostic reference only, never the sole causal evidence for going live**; and go-live / rollout criteria **do not depend on any paper-designed statistical gate**. The bootstrap / power / variance machinery is **not carried in this RFC** — it is deferred to the future simplified experiment-prereg PR that will use REAL pilot variance. Convergence map in **§20**; split-out record in **§19**. Prior revisions: r1–r3 settled the engineering contract (§16–§18 maps); r4–r10 iterated the now-split-out Stage-1 statistical protocol — preserved in git history, summarized in §19.
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

## 6. Data-time / point-in-time contract (answers Codex r1#1, r2#2)

**Correction from r2:** it is wrong to say "no input later than T-1 close except the live quote" — pre-market fundamentals/analyst revisions are legitimately later than T-1 close, and proving score-equality only freezes the *model score*, not every gate input. So the contract is split into **four input classes**, each with its own cutoff and intraday mutability, and the replay proof inspects **all** of them (not just the score):

| Class | Examples | `event_time` | `observed_at` / `available_at` | Cutoff | Fingerprint | May change **intraday**? |
|---|---|---|---|---|---|---|
| **A. Frozen signal** | PatchTST/XGB rank + conviction, `signal_version` | ≤ T-1 close | T-1 EOD build | **T-1 close** | `signal_version` hash | **No** — frozen for the session |
| **B. Session-start PIT gate inputs** | fundamentals, sentiment, analyst (P-FUND-FRESHNESS inputs) | vendor as-of date | vendor snapshot pull | **pre-open snapshot** (a pre-market revision IS allowed; it is later than T-1 close *by design*) | `gate_input_fingerprint` over the snapshot | **No** — snapshotted + fingerprinted at first eligible tick, then frozen for the session |
| **C. Live-state inputs** | cash, positions, pending/open orders | broker event ts | tick-start snapshot | per tick | reconciliation hash vs broker | **Yes** — changes every tick *by design* (§7) |
| **D. Timing-only quote** | last-trade / NBBO used for the entry trigger | exchange ts | tick read | `age ≤ quote_staleness_entry` (§10) | n/a (never enters model/gate) | **Yes** — but feeds the *timing trigger only*, never class A/B |

- **Current-day partial OHLCV** is **barred from classes A and B** in Stage 1 (within-bar look-ahead, unvalidated); a code path that feeds a partial bar into a model/gate input must **hard-fail (assertion)**, not silently proceed. Partial-bar price/VWAP/volume is class D only (Stage-2 timing trigger).
- **Stale behavior:** A missing/older-than-1-day → no intraday entries (sell-only fallback). B fails P-FUND-FRESHNESS → name not admitted. C reconciliation mismatch → halt new entries, reconcile. D over staleness threshold → skip entry (exits allowed looser).

**No-leak proof obligation (test over all four classes, not just the score):** a replay test asserts, for every tick in a session, that (i) class-A `signal_version` is constant and equals the T-1 EOD build; (ii) class-B `gate_input_fingerprint` is constant after the first eligible tick and its `available_at ≤ pre-open cutoff`; (iii) the only inputs whose values differ across ticks are class C (state) and class D (timing quote); (iv) no class-A/B input has `available_at` later than its cutoff. Thus a 10:00 vs 12:00 decision differs **only** in live state + whether the timing quote cleared the trigger — there is no after-the-cutoff data path into the scored/gated decision. *(Stage 3 intraday re-scoring will require a full PIT feature contract; Stages 1–2 deliberately keep class A frozen.)*

**Gate-input census — REQUIRED before the replay test has any enforcement surface (amendment A5.1, 2026-07-02, §22).** The no-leak proof above can only check inputs someone actually classified into A/B/C/D — and the gate-stack has non-obvious temporal inputs this RFC does not yet name a class for: the **regime detector**'s daily-bar state (is a same-day regime read class A, frozen with the signal, or class B, snapshotted at the first eligible tick? — ambiguous as written above), the **earnings-blackout calendar**, and **wash-sale `last_sell_dates`** — which an intraday *sell* mutates **mid-session**, making it a class-C-like input with a subtlety the batch (104) system never had to handle (this is the same bug family as this repo's own STATE-EXT-SELL incident: a stamped-vs-actual state mismatch silently mis-gating a decision — get the classification of this one right). Without an exhaustive, closed-world enumeration, "hard-fail on partial-bar-into-A/B" (above) is aspirational, not enforced: an input nobody classified cannot be checked. **The §8 pipeline slice's deliverables therefore include a gate-input census artifact** — a mapping of every gate's every input to a class (A/B/C/D) — **and the §6 replay test must assert against that census**, failing any tick that reads an input absent from it. This artifact and its wiring into the replay test do not exist yet; they are a named, required deliverable of the pipeline-repo build (§8), not optional polish.

---

## 7. Order lifecycle / idempotency state machine (answers Codex #2)

"Dedup vs pending" is the #1 failure mode; here is the concrete machine. Lifecycle states per (account, symbol, session):

```
NONE → INTENDED → SUBMITTED → ACCEPTED → PARTIALLY_FILLED → FILLED
                       │            │              │
                       ├→ REJECTED  ├→ CANCELED    └→ (remainder) CANCELED
                       └→ STALE_PENDING (age > max_pending_age) → reconcile → CANCELED/FILLED
```

- **Two-level id (fixes the r2 contradiction):** a single client-order-id cannot both be unique-per-order *and* be reused for a remainder. So:
  - **`parent_intent_id = hash(account, symbol, trading_day, side, signal_version)`** — stable, identifies the *decision* (one INTENDED row). This is the dedup key, **not** a broker id.
  - **`child_order_id = parent_intent_id + ":" + attempt_n`** (monotonic `attempt_n`) — this is the broker **client-order-id**; every actual submission (initial + each remainder) gets a fresh, unique one, so the broker never duplicate-rejects.
- **Cumulative-quantity invariants — split the economic target from submission attempts (fixes the r3 cancel/retry bug).** Counting *gross attempts* against `target_qty` is mathematically wrong: with `target_qty = 10`, if child 1 requests 10, fills 4, then cancels the open 6, and child 2 then requests the remainder 6, the gross requested sums to 16 > 10. The economic target and the audit of attempts are therefore **two distinct invariants**, tracked per `parent_intent_id`:
  - **Economic invariant (caps total economic exposure at the target):**
    `target_qty = cum_filled + open_qty + remaining_unsubmitted`, with `remaining_unsubmitted = target_qty − cum_filled − open_qty ≥ 0`.
    A remainder child requests exactly `remaining_unsubmitted`. Because (i) a new child is sized to `remaining_unsubmitted` and (ii) it is emitted only when there is **no OPEN child** (`open_qty = 0`), the worst case is `cum_filled(old) + fill(new child) ≤ cum_filled + remaining_unsubmitted = target_qty`. So **retries can NEVER make total filled exceed `target_qty`** — enforced as a hard assertion (`cum_filled + open_qty ≤ target_qty`) before every submit.
  - **Attempt / audit invariant (counts gross submitted quantity; MAY exceed target due to canceled/rejected retries):**
    `gross_submitted_qty = cum_filled + open_qty + cum_canceled + cum_rejected + cum_expired`.
    This is monotone non-decreasing and is *allowed* to exceed `target_qty` (16 in the example) — it is the audit trail of attempts, not economic exposure. `cum_rejected` (broker reject) and `cum_expired` (DAY-order expiry) are now tracked explicitly; in Stage 1 expiry is pre-empted by the close−cancel (§11b), but the counter still exists for reconciliation.
  - **Canceled-remainder eligibility (explicit policy):** a canceled partial remainder **is** eligible for a NEW child within the same session **iff** `cum_filled < target_qty`, there is no OPEN child, and the name is still admitted by the full gate-stack (the §7 re-emit rule). The canceled quantity does **not** reduce `target_qty`; it is recovered through `remaining_unsubmitted`. (Re-entry after the parent has *reached* `target_qty` and then exited remains a Stage-2 question.)
- **Re-emit rule (Stage 1):** a parent is eligible to emit a *remainder child* **only** when it has **no OPEN child** and `cum_filled < target_qty` **and** the name is still admitted by the full gate-stack. → **at most one OPEN child per parent at a time**, **at most one filled position per name per session** (a parent reaches its target then stops). Re-entry after a same-session exit is a Stage-2 question, deliberately excluded.
- **Cash reservation:** `reserved_cash = Σ notional(open children of buy parents, at limit/marketable price) + unsettled buys`. Sizing uses `available = broker_cash − reserved_cash`, never raw broker cash — prevents two overlapping ticks from spending the "same" dollar; the unfilled remainder of a partial stays reserved until its child is filled or canceled.
- **Partial fills:** if conviction/gates have dropped, **cancel the open child** (no remainder chase; the canceled remainder stays eligible only under the canceled-remainder policy above); else, once the prior child is no longer OPEN, the next tick opens a new remainder child (`attempt_n+1`) sized to `remaining_unsubmitted = target_qty − cum_filled − open_qty`.
- **Duplicate prevention across overlapping ticks / restarts:** the intraday run-lock guarantees at-most-one tick in flight; on process restart the loop **rebuilds the in-flight set from broker open-orders + the ledger and reconciles BEFORE any emit** (reconcile-before-emit). Dedup is on `parent_intent_id` (no second open child); each `child_order_id` is unique so a double-fire cannot double-submit the same child.
- **Reconciliation mismatch** (broker open-orders ≠ ledger) → halt new entries for the session, alert, exits still allowed.

---

## 8. Per-repo build decomposition + merge order (answers Codex #6)

Per the subrepo operating model, no single repo owns this. Stage 1 splits into three PRs with their own acceptance tests, and a **strict merge order** (orchestrator flips last and stays default-OFF until the other two are pinned):

| Order | Repo | Owns | Acceptance tests |
|---|---|---|---|
| 1 | **execution** (broker adapter) | Order-lifecycle state machine (§7), `child_order_id` as client-order-id (unique per attempt), `parent_intent_id` dedup, cumulative-qty invariants, reserved-cash accounting, reconcile-before-emit on restart, timer-driven stale-pending cancel (§10) | state-machine unit tests; duplicate child-id rejected; partial-fill + remainder accounting; restart reconcile; watchdog cancel fires between ticks |
| 2 | **pipeline** (renquant-common runtime) | Runtime decision logic — gate-stack on **live** state, sizing against `available` (§7), idempotent emit keyed on `parent_intent_id`, partial-fill remainder sizing, dedup-vs-pending, envelope interaction rules (§10) | **sim-parity**: intraday-mode emits *identical* decisions to batch-mode given identical (frozen-signal, snapshot-state) inputs; dedup unit tests; reserved-cash never negative; envelope most-restrictive-wins tests |
| 3 | **orchestrator** (this repo) | Scheduling (repoint the intraday loop to full-decisioning mode), session-boundary policy (§11b), run-bundle/provenance per tick, control-plane flag + canary allowlist + kill switch, intraday decision-ledger rows, the replay + shadow data-collection harness (§6, §9) | flag default-OFF; canary allowlist enforced; session-boundary unit tests; per-tick bundle persisted; four-class replay/no-leak test (§6); readonly-mode logs decisions without placing |

Boundary compliance (CLAUDE.md): orchestrator does **not** implement broker adapters (execution) or decision/sizing internals (pipeline) — it schedules, provenances, and gates rollout. The orchestrator change is inert (default-OFF / canary-only) until execution+pipeline are merged AND pinned.

---

## 9. Stage-1 measurement plan — OPERATIONS-ONLY shadow data collection (converged r11)

Stage 1 is **operations-only**. It runs **shadow / readonly, then a cautious canary**, to (a) prove operational correctness and (b) **accumulate real paired-session execution data** for a later, separate experiment. It **does NOT** render an execution-quality verdict, and **go-live / rollout does not depend on any paper-designed statistical gate** (operator + Codex + author convergence, §20). The formal execution-quality A/B is **deferred** to a future **simplified experiment-prereg PR** finalized against real pilot data (§9.4). (r2 wrongly folded the overnight market move into "execution cost"; r3 separated the two estimands; **r11 removes the paper statistical gate entirely** and downgrades Stage 1 to operations-only.)

### 9.1 Two readouts (neither gates Stage 1)
- **Implementation shortfall (IS) — a DIAGNOSTIC readout, not a gate.** Per order, fill vs **its own arrival/reference quote at decision time** (the mid/NBBO when the path decided): realized spread paid, fees, latency (decision→fill), reject rate, partial-fill rate. This is broker/microstructure cost, path-internal — it does **not** include any market move between paths. Only the **intraday** path places the real order for a given `(signal_session, symbol, signal_version)` (you cannot double-buy the same name), so only it yields a real fill/spread/latency/reject; the batch counterfactual is readonly. IS accrues in the decision-ledger for the future formal analysis; **Stage 1 renders no PASS/FAIL from it.**
- **Timing economics (timing P&L) — DEFERRED.** A counterfactual on the **same frozen signal** — intraday-trigger entry vs the batch's next-open entry over a defined holding horizon. It is not execution cost, needs a larger N, is regime-confounded, and accrues **passively** in the ledger; it does **not** gate Stage 1 (and never did).

### 9.2 Matched-pair construction (how paired data is accumulated — pre-treatment only)
- The batch counterfactual is a **readonly shadow decision computed from the pre-treatment snapshot** (class-A frozen signal + class-B session-start gate inputs + the pre-order state), **not** from realized post-fill availability. The intraday path having already changed cash/holdings must never enter pair eligibility.
- **Pair key = `(signal_session, symbol, signal_version)`;** "admitted by both paths" is decided from that pre-treatment snapshot.
- **Baseline fill = session-T open** (what the 104 batch would get on the same T-1-close signal); **intraday fill = during session T.** Both paths act on the *same* signal_session; only the fill *timing within T* differs. This pairing is the **data-collection structure** the future experiment (§9.4) will consume — it is not, by itself, a Stage-1 gate.

### 9.2b Observability — one real fill + a synthetic batch DIAGNOSTIC reference
For the same `(signal_session, symbol, signal_version)` only one path may place the real order, so the batch arm — a readonly shadow — has **no** actual fill, spread, latency, reject, or partial fill. A readonly shadow decision is **not** a fill-quality control. Stage 1 therefore records the **real intraday fill** and, alongside it, a **quote-based SYNTHETIC batch reference** synthesized from the **session-T open quote** (`synthetic_fill = open-auction reference price ± modeled slippage`, carrying an explicit uncertainty band), flagged **`synthetic = true`** in the ledger so it is never confused with a broker fill. This synthetic reference is a **DIAGNOSTIC only** (§9.2c) — it is **not** a control group and **not** causal evidence. (Two real fills would require randomized live routing across pairs — real capital on the control arm — or non-concurrent, regime-confounded historical controls; both are out of Stage-1 scope. The future experiment PR chooses the control design against real data, §9.4.)

### 9.2c Synthetic batch reference — DIAGNOSTIC ONLY, no pre-registration gate (converged r11)
The synthetic batch model is a **diagnostic reference**: a rough modeled batch baseline to eyeball against real intraday IS as data accumulates. It is **NOT** a control group, **NOT** a promotion / non-inferiority gate, and **NEVER** the sole causal evidence for going live. Because Stage 1 renders no execution-quality verdict, the model is **not** pinned in a blocking pre-registration artifact and there is **no freeze-before-readonly / fingerprint / ±10-bps gate**. The only durable requirements are (i) the batch reference field is the **primary-listing opening-auction print** (consolidated opening cross), with the first consolidated **NBBO midpoint at/after 09:30:00 ET** as the named fallback, and (ii) every synthetic reference row is flagged `synthetic = true` so it is never mistaken for a broker fill.

> **Split-out (r11):** the earlier separate file `doc/design/2026-06-30-stage1-synthetic-baseline-prereg.md` — the over-designed statistical protocol (frozen coefficients, adversarial censoring caps, joint calibration+evaluation bootstrap, power/precision readiness, estimand-matched variance) — is **deleted from this PR** (git history preserves it). Its simplified successor will be pre-registered in the **future experiment-prereg PR against real pilot variance** (§9.4), not on paper here.

### 9.2d No-fill / censoring — recorded, not imputed (converged r11)
No-fill / no-trigger pairs (intraday no-trigger / reject / unfilled-at-close; synthetic no-quote) are **recorded by cause** in the ledger. Stage 1 applies **no imputation and no adversarial bound**, because it renders no verdict — the not-missing-at-random handling belongs to the future formal analysis and will be designed against real pilot data (§9.4). The **only** Stage-1 action on a no-fill is operational: a **critical-cause** intraday reject (invalid order / state / contract) triggers the **Tier-1 HARD safety halt** (§9.3) — a safety guard, not a statistic.

### 9.3 Stage-1 acceptance — OPERATIONS ONLY (no execution-quality verdict)
Stage-1 "PASS" is **operational correctness only**:
- **No-leak:** the §6 four-class replay invariant holds for every tick in every canary session.
- **Idempotency:** zero duplicate filled positions per `parent_intent_id`; `reserved_cash ≥ 0`; the §7 economic invariant `target_qty = cum_filled + open_qty + remaining_unsubmitted` and `cum_filled + open_qty ≤ target_qty` (retries never overfill) hold always; no order exceeds the §10 envelope.
- **Reconciliation:** at session close, broker state == ledger == run-bundle, every session.
- **Reject SAFETY guard (Tier-1 — a safety halt, NOT a statistical gate):** **any** *critical* reject (invalid order/state/contract: bad qty/price/side, stale/inconsistent position-cash snapshot, idempotency-key violation, contract/symbol mismatch) → **HARD halt**, zero tolerance; transient non-critical rejects (venue/throttle/no-quote) are counted for the ledger. There is **no** Clopper–Pearson / reject-rate statistical gate in Stage 1 — reject-rate inference is a future-experiment question (§9.4).
- **Session boundaries:** the §11b policy holds (first eligible tick, close cutoff, halt/LULD, DAY-only no-carry).
- **Execution-quality (IS) is a DIAGNOSTIC readout, explicitly NOT a Stage-1 gate.** Real intraday IS vs the synthetic batch reference (§9.2c) is accumulated and inspected, but a difference proves nothing at canary N and **gates nothing**. The §9.1 timing P&L likewise only accrues.
- **Denominators (for the accumulated diagnostics — defined precisely so the future experiment inherits clean data):** reject rate = rejected / **attempted** submissions; partial-fill rate = partially-filled / **accepted** submissions; IS distribution = filled orders with **both** a valid arrival quote and a fill (real fills for intraday, synthetic-reference fills for batch, kept in separate distributions); matched-pair set = pre-treatment eligible pairs (§9.2), with no-fill pairs **recorded by cause** (§9.2d).

**Rollout discipline (operations-only, exposure FROZEN at the pre-declared canary envelope):** **readonly** (decide + log, place nothing) for **K = 5 sessions** → **canary = the pre-declared allowlist (1–2 names) at the pre-declared notional cap**, live **solely to accumulate real paired-session execution data** under clean ops (no-leak + idempotency + reconciliation green **and** the Tier-1 critical-reject safety guard clean). **Stage-1 live exposure is FROZEN at that envelope. There is NO cautious expansion, NO widening of the allowlist or notional cap, and NO general go-live on "continued clean ops" alone.** Operational correctness proves orders are emitted safely; it does **not** prove that moving entries intraday is economically acceptable, so it can **never** authorize putting more capital behind an unvalidated timing policy — an *expanded* canary is no longer bounded pilot data, it is production deployment of an unproven timing policy. Any expansion or go-live requires the **economic authorization** of §9.3a. Until then, the safety envelope (§10), the Tier-1 critical-reject HARD halt, and the operational invariants above decide **only** whether the frozen canary may **run at all** — never how far it may grow. K, the allowlist, and the notional cap are **operational** parameters, not a statistical pre-registration; **no** paper-designed statistical threshold gates anything in Stage 1.

Stage 1 ships on **operational correctness alone**, with live exposure **frozen at the canary envelope**; the execution-quality / economic question — and therefore any expansion or go-live — is deferred to the §9.3a authorization path (§9.4). The engineering scaffold **plus** a clean corpus of real paired-session execution data collected **within the bounded envelope** are the deliverables.

### 9.3a Canary envelope + economic authorization — what it takes to expand or go live (converged r12)
**Operational-correctness acceptance (§9.3: safety / idempotency / reconciliation / Tier-1 halt) gates whether the frozen canary may RUN AT ALL; it NEVER authorizes expansion or go-live.** The two are kept deliberately separate so the engineering RFC stays shippable without reviving the (deferred) statistics.

**No expansion beyond the frozen canary envelope, and no general go-live, until EITHER:**
- the deferred **simplified experiment-prereg PR (§9.4)** consumes the collected pilot data and supplies an **EXPLICIT AUTHORIZING decision** (its execution-quality / economic read clears its own pre-registered bar, decided against real pilot variance), **OR**
- the **operator explicitly accepts the economic risk in a SEPARATE, RECORDED decision** — a distinct decision artifact, **not** implied by Stage-1's operational PASS.

**Bounded canary envelope — so "extend to collect data" cannot become indefinite production by inertia** (proposed Stage-1 defaults, sized to the ~$10.5k book; operational, debatable — see open question §15.7):

| Bound | Proposed default | Meaning |
|---|---|---|
| Canary allowlist | **1–2 pre-declared names** | frozen; not widened without §9.3a authorization |
| Canary notional cap | **pre-declared, within §10's 15%-of-equity deployment cap** | frozen; not raised without §9.3a authorization |
| **Maximum canary DURATION** | **20 live canary sessions** (≈ one month) | a hard clock on the data-collection window |
| **Cumulative LOSS BUDGET** | **1.5% of equity**, canary-attributable realized + unrealized | a hard loss cap on the data-collection window |
| **STOP CONDITION** | duration cap reached **or** loss budget breached, with **no §9.3a authorizing decision recorded** | → **HARD halt: kill switch default-OFF, revert to 盘后 batch** |

Reaching the duration cap or the loss budget **without** a recorded §9.3a authorizing decision → **HARD halt and revert to the 盘后 batch path (kill switch default-OFF)** — **never** silent continuation, and **never** an automatic extension. Extending the window to keep collecting data is itself a decision that requires an explicit recorded authorization; the default on envelope-exhaustion is to **stop**, not to drift into production.

### 9.4 DEFERRED — the formal execution-quality experiment (future SIMPLIFIED prereg PR)
The synthetic batch fill is a **diagnostic reference, not a real control group**; there are **not yet enough independent trading sessions** to estimate the paired variance; and the **10-bps threshold / required sample size cannot be settled on paper before data exists.** Therefore, after a **preset minimum number of real independent sessions** has been collected through the Stage-1 shadow/operations phase, a **separate, SIMPLIFIED experiment-prereg PR** will be submitted. That PR will use **REAL pilot variance** to decide the **sample size**, the **block length**, and **whether a 10-bps effect is even identifiable at this account scale** — none of which this RFC attempts. This RFC deliberately **does not carry** the bootstrap / power / variance machinery; the in-place attempts to fix it (r6→r10) are exactly the statistics-patch loop the r11 convergence stops (§20).

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
| Max pending-order age | **10 min**, **timer-driven** (not next-tick) | < the 12-min cadence, so a watchdog timer cancels+reconciles *between* ticks; a tick must never inherit an already-overdue order |
| Intraday daily-loss breaker | **reuse 104's threshold** → halts NEW entries for the session; exits allowed | reuse existing guard |
| Global kill switch | env flag `RENQUANT_INTRADAY_DECISIONING` default **off**; canary allowlist required | nothing live until explicitly enabled |
| Entry order type (amendment A5.2, 2026-07-02, §22) | **pre-declared for all of Stage 1** — market vs. marketable-limit at a pre-declared NBBO±x bps — never left free per-order | order type dominates implementation-shortfall (IS) measurement more than any other envelope parameter; a Stage-1 pilot corpus mixing order types across entries would contaminate the future §9.4 experiment's data with an unrecorded confound |

**Interaction rules (which limit binds, and how the counters move) — answers Codex r2#6:**
- **Most-restrictive-wins:** an entry is blocked the moment *any* of {entries-count, deployment-notional, turnover} would be exceeded; they are not additive.
- **Deployment** (the 15% cap) counts **net new long notional including open/pending buy children** (a pending buy already consumes deployment headroom, consistent with `reserved_cash`). A partial fill keeps its **unfilled remainder reserved** against deployment until the child fills or is canceled.
- **Turnover** (the 25% cap) counts **gross** buys **and** sells; **sells consume turnover but not deployment** (a sell frees, not uses, long exposure).
- **Timer-driven pending cancel:** the max-pending-age (10 min) is enforced by a watchdog independent of the 12-min decision tick, so an overdue order is canceled+reconciled before the next tick reads state (otherwise the next tick would see an already-stale pending). On cancel, the unfilled remainder's reservation is released.

---

## 11. Dependencies & blockers (answers Codex r1#5, r2#7)

**Terminology fix (r3):** a *BLOCKER* prevents Stage 1 from **starting**; a *deferred dependency* is needed by a later stage. r2 mislabeled fractional shares a BLOCKER even though Stage 1 uses whole shares — corrected below.

**Stage-1 BLOCKERs (must clear before the canary):**
- **Live-quote data plane — quote-feed QUALITY is a named blocker, not an entitlement checkbox (amendment A5.3, 2026-07-02, §22).** Alpaca live quote/last-trade entitlement + rate-limit headroom for per-tick reads across the watchlist, **AND** either a **SIP/consolidated feed subscription**, **OR** a **recorded acceptance of quantified IEX bias** covering BOTH the class-D arrival quote (§6) and the §9.2c synthetic batch reference. On Alpaca's free tier, "NBBO" is IEX-local (single-venue, ~2-3% of consolidated volume): arrival mids are systematically wider/staler than a true consolidated NBBO, and the §9.2c synthetic batch reference's required field — the **primary-listing opening-auction print** (consolidated opening cross) — is **not present in the IEX feed at all**, only its named fallback (first consolidated NBBO midpoint at/after 09:30:00 ET) would even be approximable, and even that approximation is IEX-local unless a SIP subscription is in place. This cannot silently pass as "we have *a* quote feed" — the canary may start on either a real SIP subscription or an explicit, recorded decision naming and quantifying the accepted IEX bias, never on an unexamined default.
- **Broker open-orders API** — required for §7 dedup-vs-pending and reconcile-before-emit.
- **Intraday decision-ledger cadence** — the ledger must accept intraday-cadence rows (schema unchanged) for the §9 A/B + daily retrospective.

**Deferred dependencies (not Stage-1 blockers):**
- **Fractional shares — Stage-2 dependency, NOT a Stage-1 blocker.** Stage 1 sizes in **whole shares + the existing min-notional guard**, so the fractional chain does not gate Stage 1. It *is* needed for Stage 2; that chain is currently un-mergeable (per Codex 2026-06-30: execution **#19** red CI + broker stop/classification hazards; pipeline **#153** lacks fractional lifecycle / sim parity; strategy **#36** blocked behind both). Tracked as a Stage-2 prerequisite, to verify independently before Stage 2 — not assumed available.

---

## 11b. Session-boundary & market-state policy (answers Codex r2#8)

Intraday control-plane correctness needs explicit boundary behavior; the NYSE calendar guard 104 already uses is reused for the calendar parts.

| Condition | Stage-1 policy |
|---|---|
| **First eligible tick after open** | No entries in the **first 5 min** after open (spread/auction settling); first eligible decision tick at **open + 5 min**. Class-B gate inputs are snapshotted + fingerprinted at this first eligible tick (§6). |
| **No-entry cutoff before close** | **No new entries in the last 30 min**; exits remain allowed to the bell. |
| **Early-close days** | NYSE calendar guard detects half-days; the open+5min and close−30min cutoffs scale to the actual session; no hard-coded clock times. |
| **Halted / LULD symbol** | Skip **entries** for that symbol while halted/limit-locked; exits follow the existing risk rules; resume entries only after a normal two-sided quote returns and passes class-D staleness. |
| **Market closed / delayed or stale feed** | Fail-safe: **no entries**; if the feed is delayed/stale beyond class-D threshold the loop degrades to sell-only (the 104 behavior). |
| **Pending DAY orders at session end** | Stage 1 uses **DAY** orders only (no GTC carry). Any unfilled child is **canceled before the close** and reconciled; nothing crosses the session boundary. |

---

## 12. Staged evolution path

- **Stage 1 — Decouple entry timing from the batch (THE prerequisite build).** Repoint the intraday loop from `--sell-only` to **full decisioning**: read the frozen daily conviction-ranked watchlist (§6), evaluate the full gate-stack on live state each tick (§7), and enter admitted names intraday (same gates, same sizing, same safety) instead of queuing for next-day open. Built as three ordered per-repo PRs (§8); default-OFF → readonly → **canary FROZEN at the pre-declared envelope (§9.3)**. Gate = **operational correctness** (§9.3), which decides only whether the frozen canary may **run at all**; **expansion / go-live needs the separate economic authorization of §9.3a** (deferred-experiment PASS or an explicit recorded operator decision). Execution-quality accrues as a **diagnostic** readout for a future, separate simplified experiment-prereg PR (§9.4), **not** a Stage-1 pass/fail.
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
3. Safety envelope (§10): are the proposed conservative defaults + interaction rules acceptable as starting values?
4. Rollout (§9.3): are the **operations-only** readonly `K=5` / frozen-canary defaults right? Live exposure stays **frozen at the pre-declared envelope**; expansion / go-live needs the separate §9.3a economic authorization. (The formal execution-quality gate — sample size, block length, and whether a 10-bps effect is even identifiable at this account scale — is **deferred** to a separate **simplified experiment-prereg PR** finalized against **real pilot data**, §9.4.)
5. Is the per-repo decomposition + merge order (§8) correct, and who owns each slice?
6. Session boundaries (§11b): confirm the open+5min / close−30min / DAY-only-no-carry defaults.
7. Canary envelope (§9.3a): confirm the bounded-canary defaults — **maximum duration** (proposed 20 live sessions), **cumulative loss budget** (proposed 1.5% of equity), and the **stop condition** (envelope-exhaustion without a §9.3a authorizing decision → HARD halt, revert to 盘后 batch).

---

## 16. Review-response map — Codex round-1 review of `c976ed8`

| # | Codex point | Disposition | Where |
|---|---|---|---|
| 1 | Data-time contract underspecified | **Accepted** | §6 + replay no-leak test |
| 2 | Order lifecycle/idempotency too high-level | **Accepted** | §7 state machine, ids, reserved-cash |
| 3 | Stage-1 A/B not a valid experiment | **Accepted with refinement** — pre-registered operational/execution-quality gate; alpha estimand explicitly deferred | §9 |
| 4 | Safety envelope numbers can't stay open | **Accepted** | §10 defaults |
| 5 | Dependency reality (fractional chain) | **Accepted** | §11 |
| 6 | Repo ownership boundaries | **Accepted** | §8 per-repo slices + merge order + acceptance tests |
| 7 | Entry-timing baseline too naive | **Accepted** | §5.3 + §9 — plumbing baseline, readonly/canary first |

---

## 17. Review-response map — Codex round-2 review of `268c0af`

| # | Codex point | Disposition | Where |
|---|---|---|---|
| 1 | Idempotency key can't support partial-fill (one client-order-id can't be unique *and* reused) | **Accepted** — split `parent_intent_id` (dedup) vs `child_order_id = parent:attempt_n` (broker id); cumulative-qty invariants | §7 |
| 2 | No-leak claim internally inconsistent (pre-market revisions are later than T-1 close; score-equality ≠ all inputs frozen) | **Accepted** — four input classes (frozen-signal / session-start-PIT / live-state / timing-quote), each with cutoff + fingerprint; replay inspects all four | §6 |
| 3 | A/B conflates execution quality with timing return | **Accepted** — IS measured vs each path's own arrival quote; timing P&L is a separate, deferred counterfactual estimand | §9.1 |
| 4 | Gate not actually pre-registered (K, tolerance, denominator unspecified) | **Accepted** — committed K=5, N≥20, 10-bps IS tolerance, denominators (matched pairs / accepted orders); optional `preregistration.md` | §9.3 |
| 5 | Matched-pair selects on post-treatment outcomes | **Accepted** — pairs from pre-treatment snapshot only; key `(signal_session, symbol, signal_version)`; baseline = session-T open | §9.2 |
| 6 | Safety defaults need interaction rules | **Accepted** — most-restrictive-wins, pending counts vs deployment, sells consume turnover-not-deployment, partials reserve remainder, timer-driven cancel | §10 |
| 7 | Fractional mislabeled BLOCKER | **Accepted** — relabeled deferred Stage-2 dependency; true Stage-1 BLOCKERs = quote entitlement / open-orders API / ledger cadence | §11 |
| 8 | Missing session-boundary policy | **Accepted** — new §11b (first-tick, close cutoff, early-close, halt/LULD, stale-feed, DAY-only no-carry) | §11b |

---

## 18. Review-response map — Codex round-3 review of `320b4fc`

| # | Codex point | Disposition | Where |
|---|---|---|---|
| 1 | Cumulative-qty invariant wrong under cancel/retry (gross attempts sum to 16 > target 10) | **Accepted** — split the economic invariant `target_qty = cum_filled + open_qty + remaining_unsubmitted` from the attempt/audit invariant `gross_submitted_qty = cum_filled + open_qty + cum_canceled + cum_rejected + cum_expired`; explicit canceled-remainder eligibility; retries provably can't overfill (`cum_filled + open_qty ≤ target_qty` assertion); rejected/expired now tracked | §7, §9.3 |
| 2 | Matched-pair execution-quality A/B not operationally observable (only one path places the real order; readonly shadow has no fill) | **Accepted** — committed **option (a)**: real intraday fill vs a quote-based **synthetic** batch fill model with labeled uncertainty (half-spread + open-auction slippage + band, `synthetic=true`); (b) randomized routing / (c) historical controls noted with caveats; readonly shadow stated to be NOT a fill-quality control | §9.1, §9.2b |
| 3 | Inconsistent denominators; bare 2% reject gate uninformative at small N | **Accepted** — reject = rejected/attempted, partial = partial/accepted, IS = filled-with-valid-arrival-quote-and-fill, matched-pair = pre-treatment eligible with explicit censoring; reject gate now min-count (`M_reject=50`) + one-sided 95% binomial (Clopper–Pearson) bound vs 2% | §9.3 |

---

## 19. Stage-1 statistical protocol (Codex rounds 4–9) — SPLIT OUT in r11

Codex rounds 4 through 9 (revisions **r4 → r10**) iterated the Stage-1 **execution-quality statistical non-inferiority protocol** — the synthetic-baseline pre-registration and its detached fingerprint, the ITT / censoring-sensitivity treatment, the joint calibration+evaluation bootstrap, the pre-canary power/precision readiness rule, and the estimand-matched (blinded-internal-pilot) variance. Per the **r11 convergence** (operator + Codex + author, §20), that entire protocol — and its round-by-round revision maps — is **removed from this RFC** and **deferred to a future simplified experiment-prereg PR finalized against real pilot data** (§9.4). The detailed r4–r10 maps and the deleted `2026-06-30-stage1-synthetic-baseline-prereg.md` are **preserved in git history**; they are **not** re-derived here, because carrying that machinery is precisely the statistics-patch loop the convergence stops.

Only the **operational / safety** outcomes of those rounds survive in the RFC body:
- the split economic-vs-audit **order-quantity accounting** (§7, from rounds 3–4);
- the **Tier-1 critical-reject HARD safety halt** — a safety guard, **not** the split-out statistical reject-rate test (§9.3, from round 4);
- the **session-boundary** policy (§11b);
- the honest statement that a readonly shadow is **not** a fill-quality control and that the synthetic batch fill is a **diagnostic reference only** (§9.2b / §9.2c).

---

## 20. Review-response map — r11 CONVERGENCE (operator + Codex + author)

The RFC had spun into a statistics-patch loop (r6→r10, all on the Stage-1 synthetic-baseline non-inferiority protocol). The operator, this author, and Codex agreed to **stop** it. The agreed **6-point convergence**, implemented in this revision (DESIGN docs only, no code):

| # | Convergence point | Implemented |
|---|---|---|
| 1 | The RFC keeps ONLY the settled **ENGINEERING** — the 盘中 real-time decision loop, real-time data plane, live model serving, real-time state/gate consistency, entry-timing logic, and the **SAFETY envelope** (idempotency, reconciliation, quantity accounting, kill-switch). | §1–§8, §10, §11b, §7 preserved |
| 2 | **DELETE** the over-designed statistical protocol file `2026-06-30-stage1-synthetic-baseline-prereg.md` from this PR (git history preserves it); remove all references that treated it as a **blocking** artifact. | `git rm`; §9.2c split-out note; §19 |
| 3 | Reframe Stage-1 as **OPERATIONS-ONLY**: shadow/readonly to accumulate real paired-session execution data; MAY NOT claim an execution-quality PASS; the synthetic baseline is a **DIAGNOSTIC REFERENCE ONLY**, never sole causal evidence for going live; go-live/rollout does **not** depend on any paper-designed statistical gate. | §9 (rewritten), §9.2c, §9.3 |
| 4 | **Defer the formal experiment**: after a preset minimum of real independent sessions from the shadow phase, a **separate, SIMPLIFIED** experiment-prereg PR uses **REAL pilot variance** to decide sample size, block length, and whether a 10-bps effect is even identifiable at this account scale. No bootstrap/power/variance machinery in THIS RFC. | §9.4 |
| 5 | Keep the **phased rollout**, but Phase-1/Stage-1 = operations-only shadow data collection (no execution-quality verdict); the formal A/B is future work gated on real data. | §9.3 rollout discipline, §12 |
| 6 | The synthetic batch fill is **not** a real control group; there are **not** enough independent sessions yet to estimate the paired variance; and the 10-bps threshold / sample size **cannot** be settled on paper before data exists. | §9.2c, §9.4 |

*DESIGN docs only, no code. Not merged / not approved — re-request review from `haorensjtu-dev`.*

---

## 21. Review-response map — r12 (Codex r11 review: one rollout-boundary blocker)

Codex's r11 review acknowledged the r11 convergence (statistics split out, Stage-1 downgraded to operations-only) and raised **one remaining blocker**: §9.3 let the live canary "expand cautiously on continued clean ops" and stated go-live does not depend on execution-quality / economic evidence — but operational correctness (orders emitted safely) does **not** prove that moving entries intraday is economically acceptable, so once the canary **expands** it stops merely collecting bounded pilot data and starts deploying an **unvalidated timing policy to more capital**.

| # | Codex point (r11) | Disposition | Where |
|---|---|---|---|
| 1 | Freeze Stage-1 live exposure at the pre-declared canary allowlist + notional cap, **solely for data collection**; remove the "expand cautiously on continued clean ops" language. | **Accepted** — exposure **FROZEN** at the pre-declared envelope; the "expand cautiously" language removed. | §9.3 rollout discipline (rewritten) |
| 2 | **No expansion** beyond the envelope and **no general go-live** until either the deferred simplified experiment-prereg PR authorizes it on pilot data, or the operator explicitly accepts the economic risk in a **separate recorded decision**. | **Accepted** — the two-path **economic authorization** requirement added. | §9.3a, §9.4 |
| 3 | Define the canary envelope explicitly — **maximum duration, loss budget, stop condition** — so "extend to collect data" cannot become indefinite production by inertia; hitting duration/loss-budget without an authorizing decision → **halt (revert to 盘后 batch)**, not silent continuation. | **Accepted** — bounded-envelope table (duration, loss budget, stop condition) + explicit HARD-halt-to-batch default; open question §15.7 for the bounds. | §9.3a envelope table |
| 4 | Keep the distinction crisp: operational-correctness acceptance gates whether the canary may **RUN AT ALL**; it **never** authorizes expansion or go-live. | **Accepted** — stated explicitly: operational PASS gates run-at-all; economic authorization (§9.3a) gates expansion / go-live. | §9.3, §9.3a |

This keeps the engineering RFC separable from the (deferred) statistics without reviving the stats loop.

---

## 22. Amendment integration map — A5.1-A5.3 measurement-integrity pins (2026-07-02)

`doc/design/2026-07-01-104-105-design-review-amendments.md` ("## A5. Measurement-integrity pins for Stage-1 pilot data") identified engineering-integrity gaps in what this RFC already commits to collecting: the no-leak proof (§6) and the pilot-data corpus (§9) are only as clean as their unstated assumptions. This integration folds sub-points 1-3 into the canonical sections below; A5.4-A5.7 (loss-budget sensitivity scenario, identifiability/power-prereg requirements list, batch-rotation churn diagnostic, active-path verification) are **not** addressed here — out of this integration's scope, left for a separate round.

| # | Amendment point (A5.x) | Integration | Where |
|---|---|---|---|
| 1 | Gate-input census: §6's no-leak replay test can only check inputs someone classified (A/B/C/D); the regime detector, earnings-blackout calendar, and mid-session-mutating wash-sale `last_sell_dates` were not explicitly named, so "hard-fail on partial-bar-into-A/B" has no real enforcement surface without an exhaustive census. | **Accepted** — a gate-input census artifact + a §6 replay-test assertion against it is now a named, required deliverable of the §8 pipeline-repo slice; not built yet (no code exists for the §6 replay itself yet), correctly scoped as future work here. | §6 |
| 2 | Pre-declare the entry order type (market vs. marketable-limit at NBBO±x bps) for Stage 1 — it dominates implementation-shortfall measurement more than any envelope parameter and, left free, would mix order types into the pilot corpus. | **Accepted** — added as a named §10 envelope row. | §10 |
| 3 | Quote-feed quality is a named blocker, not an entitlement checkbox: Alpaca's free-tier feed is IEX-local, does not carry the §9.2c synthetic-reference's required primary-listing opening-auction print, and arrival mids are systematically biased vs. a true consolidated NBBO. | **Accepted** — §11's live-quote-data-plane blocker now requires a SIP/consolidated subscription **or** a recorded, quantified IEX-bias acceptance, explicitly, rather than passing on bare entitlement + rate-limit headroom alone. | §11 |

None of these three touch order-placement, broker-call, or margin/account-state code — this RFC coordinates the cross-repo build (§8) and none of the "execution"/"pipeline" repo pieces these deliverables belong to are built yet; this integration only makes the eventual implementer's contract explicit and complete, per the RFC's own SCOPE line.

*DESIGN docs only, no code. Not merged / not approved — re-request review from `haorensjtu-dev`.*
