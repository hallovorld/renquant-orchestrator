# renquant105 — Intraday (盘中) Real-Time Decisioning Architecture (RFC)

STATUS: design / RFC — the ENGINEERING DESIGN is the prerequisite; build is staged after review. Design first, do not rush to build.
DATE: 2026-06-30
REVISION: r5 (2026-06-30) — addresses the Codex round-4 review of `9365361` (2 experiment-design fixes: (1) **pre-register the §9.2b synthetic batch baseline** in a separate **frozen-before-canary** artifact `doc/design/2026-06-30-stage1-synthetic-baseline-prereg.md` — new §9.2c — freezing the opening reference field + timestamp, the fill-model formula + all parameter values, the calibration set + a pre-canary cutoff, per-component treatment (spread/auction-imbalance/latency/fees/rejects/no-quote), the uncertainty method + the CI-must-exclude-the-margin overlap PASS rule, and an immutable content sha stamped in every ledger row — until frozen, Stage 1 validates **operations only**, never a comparative execution-quality PASS; (2) **resolve the rollout-threshold inconsistency** (§9.3) with a two-tier reject gate — a small-sample **HARD** guard that is operative immediately and **CAN block** expansion at N≥20 (zero critical rejects + ≤1 non-critical in the first N), with the Clopper–Pearson rate test **reserved for scale-up** at M_reject=50, so thresholds are consistent across the N≥20→M_reject window). r4 addressed round-3 (`320b4fc`); r3 round-2 (`268c0af`); r2 round-1 (`c976ed8`). Point-by-point maps in §16 (r1), §17 (r2), §18 (r3), §19 (r4).
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
| 3 | **orchestrator** (this repo) | Scheduling (repoint the intraday loop to full-decisioning mode), session-boundary policy (§11b), run-bundle/provenance per tick, control-plane flag + canary allowlist + kill switch, intraday decision-ledger rows, the A/B + replay harness (§6, §9) | flag default-OFF; canary allowlist enforced; session-boundary unit tests; per-tick bundle persisted; four-class replay/no-leak test (§6); readonly-mode logs decisions without placing |

Boundary compliance (CLAUDE.md): orchestrator does **not** implement broker adapters (execution) or decision/sizing internals (pipeline) — it schedules, provenances, and gates rollout. The orchestrator change is inert (default-OFF / canary-only) until execution+pipeline are merged AND pinned.

---

## 9. Stage-1 measurement plan — operational gate, two separated estimands (answers Codex r1#3/#7, r2#3/#4/#5)

The Stage-1 gate is **operational/execution-quality**, pre-registered and falsifiable; the **alpha/timing-return estimand is explicitly deferred**. r2 wrongly folded the overnight market move into "execution cost"; r3 separates the two estimands cleanly and commits concrete pre-registration numbers.

### 9.1 Two distinct estimands (do not conflate)
- **Implementation shortfall (IS) — the Stage-1 execution-quality readout.** Per order, fill vs **its own arrival/reference quote at decision time** (the mid/NBBO when the path decided). Components: realized spread paid, fees, latency (decision→fill), reject rate, partial-fill rate. This is broker/microstructure cost and is path-internal — it does **not** include any market move between paths. **Observability constraint (fixes r3#2): only ONE path can place the real order** for a given `(signal_session, symbol, signal_version)` without double-buying, so only the **intraday** path yields a real fill/spread/latency/reject; the batch counterfactual is readonly and has **no** real broker fill. The comparison is therefore **real-intraday-IS vs a synthetic batch-IS model** (§9.2b) — a readonly shadow decision is explicitly **NOT** a fill-quality control.
- **Timing economics (timing P&L) — DEFERRED to Stage-2 scoping.** A counterfactual estimand on the **same frozen signal**: intraday-trigger entry vs the batch's next-open entry, evaluated over a **defined holding horizon** (e.g. close of T and the multi-day H-day mark). This is where "did acting intraday vs next-open help the return" lives. It is *not* execution cost, needs a larger N, is regime-confounded, and pre-registering it now would be over-engineering validation ahead of a demonstrated edge (operator lesson, 2026-06-28). It accrues passively in the ledger; it does **not** gate Stage 1.

### 9.2 Matched-pair construction (pre-treatment only — no post-treatment selection)
- The batch counterfactual is a **readonly shadow decision computed from the pre-treatment snapshot** (class-A frozen signal + class-B session-start gate inputs + the pre-order state), **not** from realized post-fill availability. The intraday path having already changed cash/holdings must never enter pair eligibility.
- **Pair key = `(signal_session, symbol, signal_version)`.** "Admitted by both paths" is decided from that pre-treatment snapshot.
- **Baseline fill = session-T open** (the fill the 104 batch would get acting on the same T-1-close signal); **intraday fill = during session T**. (Resolves the r2 "(symbol, session) vs next-day fill" ambiguity — both paths act on the *same* signal_session; only the fill *timing within T* differs.)

### 9.2b Observability of the execution-quality A/B — one real fill + a synthetic batch model (answers Codex r3#2)
The matched-pair IS comparison is **not** observable if both arms are expected to produce real fills: for the same `(signal_session, symbol, signal_version)` only one path may place the real order, so the batch arm — being a readonly shadow — has no actual fill, spread paid, latency, reject, or partial fill. A readonly shadow decision is **not** a fill-quality control. Three ways to make the comparison observable, with caveats:
- **(a) Live intraday fill vs a quote-based SYNTHETIC batch fill model — COMMITTED for Stage 1.** The intraday path places the **real** order and yields the real fill/spread/latency/reject. The batch arm's fill is **synthesized** from the **session-T open quote** (the fill the 104 batch would have gotten on the same frozen signal), modeled as `synthetic_fill = open-auction reference price ± slippage`, where the slippage term is **explicitly modeled and labeled as an estimate** — components: half-spread at the open, open-auction slippage, and a stated uncertainty band. Every synthetic batch fill is flagged **`synthetic = true`** in the ledger so it is never confused with a broker fill. Stage-1 acceptance compares **real intraday IS** vs **synthetic batch IS**, and the synthetic model's uncertainty band is reported alongside the point estimate (so a difference inside the band is read as "not distinguishable").
- **(b) Randomized live routing** between the intraday and batch paths across eligible pairs — gives two *real* fills, but never on the same pair, and both arms take **real positions** (doubling deployed risk on the control arm). Requires a pre-defined allocation rule and exposure controls. Deferred: heavier and spends real capital on the control.
- **(c) Non-concurrent historical batch controls** (past 104 next-open fills) — real fills, but **regime/time-confounded** vs the canary window. Useful only as a sanity cross-check, not the primary control.
Stage 1 commits to **(a)**; (b)/(c) are noted alternatives. The synthetic nature of the batch arm is stated plainly so the gate is read as *real intraday execution vs a modeled batch baseline*, not as two measured fills. **The full specification of the (a) synthetic model is not left to implementation — it is pinned in a pre-registration artifact frozen before any canary fill (§9.2c).**

### 9.2c Synthetic-baseline PRE-REGISTRATION artifact (freezes the §9.2b batch model — answers Codex r4#1)
The §9.2b synthetic batch fill carries researcher degrees of freedom — the opening reference field, the slippage parameters, the calibration window, and the uncertainty method — that can move the baseline by **more than the 10-bps gate**, and could be chosen *after* seeing canary fills. To remove that, the synthetic batch model is pinned in a **separate pre-registration artifact**, [`doc/design/2026-06-30-stage1-synthetic-baseline-prereg.md`](./2026-06-30-stage1-synthetic-baseline-prereg.md), which **MUST be frozen (status `FROZEN` + content sha computed) BEFORE the first canary fill is observed.** It freezes ALL of:
- **Opening reference + timestamp** — the official **primary-listing opening-auction print** (consolidated opening cross), `event_time` = the auction publication timestamp on session T; named fallback = the first consolidated **NBBO midpoint at/after 09:30:00 ET** when a symbol has no opening auction (`ref_source = nbbo_fallback`). One field, stated — not "an opening reference."
- **Fill-model formula + every parameter value** — `synthetic_batch_fill = P_open + side_sign · (k_spread · half_spread_open + k_auction · auction_slippage_proxy)`, `side_sign = +1` for buys (pay up); `half_spread_open = ½·(ask_open − bid_open)` from the open NBBO; `k_spread` (fraction of the open half-spread paid) and `k_auction` (auction-slippage coefficient) are **fit once on the calibration set and frozen** — their values are written into the artifact, not left open.
- **Calibration dataset + cutoff strictly before canary** — the trailing **60 trading sessions** of 104's *realized next-open batch fills* vs the same-session opening prints, conditioned on symbol liquidity bucket; **cutoff = the last session before the readonly phase begins** (strictly before canary). Coefficients are fit once on that window and **never re-fit** after canary data is observed.
- **Per-component treatment (each: how handled / censored)** — *spread*: charged via `k_spread · half_spread_open`. *Auction imbalance*: an `auction_slippage_proxy` (bps) from the published opening imbalance (imbalance share / auction size), per liquidity bucket; if the imbalance feed is unavailable → `0`, flagged `auction_imbalance = unavailable` — note this **understates** the batch cost and is therefore **conservative against** the intraday arm (makes the batch look better, raising the bar for an intraday PASS). *Latency*: the synthetic arm fills at the cross, so its modeled latency is **0** (a stated modeling choice); real decision→fill latency is measured only on the real intraday arm. *Fees*: the same commission schedule is applied to both arms (it nets out in the difference but is included). *Rejects*: the synthetic arm **cannot** reject (no real order); a real intraday reject removes that pair's intraday fill → the **pair is censored** (§9.3). *No-quote*: no valid open NBBO → **no synthetic fill is formed** → the pair is **censored**, flagged `synthetic_no_quote = true`, and **never imputed**.
- **Uncertainty-band method + overlap PASS rule** — the per-fill uncertainty is propagated from (i) the calibration standard errors of `k_spread`, `k_auction` and (ii) the residual dispersion of the calibration fit, into a confidence interval on the **matched-pair median IS difference** (intraday − synthetic batch). **PASS requires the one-sided upper confidence bound of that median difference to lie BELOW the +10-bps inferiority margin — i.e. the CI of the difference must EXCLUDE the margin, not merely the point estimate.** If the 10-bps margin **overlaps** the uncertainty interval, the result is "not distinguishable" → **NOT a PASS**.
- **Immutable model/version fingerprint** — on freeze the artifact content is hashed to `synthetic_baseline_prereg_sha`, stored in **every** ledger row that carries a synthetic batch fill (alongside `synthetic = true`); any later change to the model is detectable and **invalidates** the run.

**Until this artifact exists and is FROZEN, Stage 1 may validate OPERATIONS ONLY (no-leak + idempotency + reconciliation + session-boundary) — it MAY NOT claim a comparative execution-quality PASS.**

### 9.3 Pre-registered Stage-1 PASS gate (concrete values — frozen before any canary data is observed)
- **No-leak:** the §6 four-class replay invariant holds for every tick in every canary session.
- **Idempotency:** zero duplicate filled positions per `parent_intent_id`; `reserved_cash ≥ 0`; the §7 economic invariant `target_qty = cum_filled + open_qty + remaining_unsubmitted` and `cum_filled + open_qty ≤ target_qty` (retries never overfill) hold always; no order exceeds the §10 envelope.
- **Reconciliation:** at session close, broker state == ledger == run-bundle, every session.
- **Execution-quality (IS) acceptance (requires the §9.2c pre-registration to be FROZEN first):** the **one-sided upper confidence bound** of the (real intraday − synthetic batch) **median IS difference** must lie **below the +10-bps inferiority margin** — i.e. the uncertainty band of the *difference* must **exclude** the margin, not merely the point estimate (§9.2c). A point estimate inside the band, or a band that overlaps the 10-bps margin, reads as "not distinguishable" → **NOT a PASS**. The synthetic batch model used is exactly the one pinned in `2026-06-30-stage1-synthetic-baseline-prereg.md` (its `synthetic_baseline_prereg_sha` stamped in every synthetic ledger row). **Until that artifact is frozen, this acceptance cannot be evaluated and Stage 1 validates operations only.**
- **Denominators (each defined precisely — they are NOT interchangeable; answers Codex r3#3):**
  - **Reject rate = rejected submissions / ATTEMPTED submissions** — every submission attempt, accepted or not. *Not* accepted orders: a rejected order is by definition not accepted, so accepted-orders cannot be the denominator for rejects.
  - **Partial-fill rate = partially-filled accepted submissions / accepted submissions.**
  - **IS distribution = filled orders that have BOTH a valid arrival quote and a fill** — real fills for the intraday arm, modeled fills for the synthetic batch arm (§9.2b), kept in separate distributions.
  - **Matched-pair eligibility = pre-treatment eligible pairs** (§9.2), with **explicit no-fill / censoring handling**: a pair where one arm did not fill (intraday no-trigger, or no valid synthetic batch fill) is **censored and recorded as such** with reported censoring counts — never silently dropped, so the matched set cannot be cherry-picked.
- **Reject gate — two-tier: small-sample HARD guard now + Clopper–Pearson at scale-up (answers Codex r4#2):** a bare 2% rate is uninformative at canary N (one reject in `N = 20` already reads 5%), **but** reject behavior must still be able to **block** expansion in the small-sample window — so the gate is two tiers, and the small-sample tier is operative immediately:
  - **Tier 1 — small-sample HARD safety guard, OPERATIVE IMMEDIATELY (it CAN block):** from the first live submission through the `N ≥ 20 → M_reject` window, expansion is **halted** if EITHER (i) **any** *critical* reject occurs — a reject caused by an **invalid order / state / contract** (bad qty/price/side, stale or inconsistent position-cash snapshot, idempotency-key violation, contract/symbol mismatch): **zero tolerance, any single one halts**; OR (ii) the raw count of *non-critical* rejects (transient venue/throttle/no-quote) exceeds **`≤ 1` in the first `N`**. This guard is a **pre-registered PASS condition** and **can block or pass** expansion at `N ≥ 20` — it is **not** informational-only.
  - **Tier 2 — statistical reject-rate test, RESERVED for scale-up (`≥ M_reject = 50` attempted submissions):** once attempted submissions reach `M_reject = 50`, the *rate* gate **fails** when the **lower bound of a one-sided 95% binomial (Clopper–Pearson) CI on the observed reject rate exceeds the 2% ceiling** (≥ 95% confident the true rate is above 2%). This is the **scale-up** gate; it does **not** replace Tier 1, which keeps running underneath it.
  - The two tiers are **consistent across the `N ≥ 20 → M_reject = 50` window**: Tier 1 covers it and CAN halt, Tier 2 switches on at `M_reject`. There is **no** window in which reject behavior is unevaluable, and the prior "informational only / cannot block or pass" framing is removed.
- **Rollout discipline (concrete, thresholds now consistent — answers Codex r4#2):** **readonly** (decide + log, place nothing) for **K = 5 sessions** → **canary** = **1–2 allowlisted names** live → **expand only after N ≥ 20 matched admitted pairs** with clean ops (no-leak + idempotency + reconciliation all green) **AND the Tier-1 small-sample reject guard clean** (zero critical rejects + ≤ 1 non-critical reject in the first N). Because Tier 1 is operative from the first live submission, reject performance **is** evaluable at the `N ≥ 20` expansion point — this closes the prior inconsistency where the system could expand before any reject gate could pass or fail. The **Tier-2** Clopper–Pearson rate test then becomes the **scale-up** gate once attempted submissions reach `M_reject = 50`. K, N, the **10-bps IS inferiority margin + the §9.2c CI-excludes-the-margin PASS rule**, the denominators (above), the **Tier-1 guard** (critical = 0 / non-critical ≤ 1-in-N), and `M_reject = 50` are **the pre-registration**; changing any of them after canary data is observed invalidates the run. The synthetic-baseline parameters live in the separate **frozen** `2026-06-30-stage1-synthetic-baseline-prereg.md` (§9.2c), which must be frozen *before* canary starts; whether the K/N values also move into that file or a sibling `preregistration.md` is open question §15.4.

Stage 1 ships on operational correctness + non-worse IS; an alpha-null timing readout is an accepted, pre-stated outcome — the engineering scaffold is the deliverable.

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

**Interaction rules (which limit binds, and how the counters move) — answers Codex r2#6:**
- **Most-restrictive-wins:** an entry is blocked the moment *any* of {entries-count, deployment-notional, turnover} would be exceeded; they are not additive.
- **Deployment** (the 15% cap) counts **net new long notional including open/pending buy children** (a pending buy already consumes deployment headroom, consistent with `reserved_cash`). A partial fill keeps its **unfilled remainder reserved** against deployment until the child fills or is canceled.
- **Turnover** (the 25% cap) counts **gross** buys **and** sells; **sells consume turnover but not deployment** (a sell frees, not uses, long exposure).
- **Timer-driven pending cancel:** the max-pending-age (10 min) is enforced by a watchdog independent of the 12-min decision tick, so an overdue order is canceled+reconciled before the next tick reads state (otherwise the next tick would see an already-stale pending). On cancel, the unfilled remainder's reservation is released.

---

## 11. Dependencies & blockers (answers Codex r1#5, r2#7)

**Terminology fix (r3):** a *BLOCKER* prevents Stage 1 from **starting**; a *deferred dependency* is needed by a later stage. r2 mislabeled fractional shares a BLOCKER even though Stage 1 uses whole shares — corrected below.

**Stage-1 BLOCKERs (must clear before the canary):**
- **Live-quote data plane** — Alpaca live quote/last-trade entitlement + rate-limit headroom for per-tick reads across the watchlist.
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
3. Safety envelope (§10): are the proposed conservative defaults + interaction rules acceptable as starting values?
4. Pre-registration (§9.3): are the committed K=5 / N≥20 / 10-bps-IS-tolerance values right, and should they live inline or in a separate `preregistration.md` that must merge before canary?
5. Is the per-repo decomposition + merge order (§8) correct, and who owns each slice?
6. Session boundaries (§11b): confirm the open+5min / close−30min / DAY-only-no-carry defaults.

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

## 19. Review-response map — Codex round-4 review of `9365361`

| # | Codex point | Disposition | Where |
|---|---|---|---|
| 1 | Synthetic batch arm not specified / not pre-registered — its DOF (reference field, slippage params, calibration window, uncertainty method) can move the baseline by more than the 10-bps gate and could be chosen after seeing fills | **Accepted** — new **§9.2c** pins the model in a separate **frozen-before-canary** artifact `2026-06-30-stage1-synthetic-baseline-prereg.md`, freezing the opening reference field + timestamp (primary-listing opening-auction print, NBBO-midpoint fallback), the fill formula + all parameter values (`k_spread`, `k_auction`), the calibration set + a strictly-pre-canary cutoff, per-component treatment (spread / auction-imbalance / latency / fees / rejects / no-quote, each handled or censored), the uncertainty method + a **CI-must-exclude-the-margin** overlap PASS rule, and an immutable content sha stamped in every ledger row; **until frozen, Stage 1 validates operations only — no comparative execution-quality PASS** | §9.2c, §9.3, prereg artifact |
| 2 | Rollout thresholds inconsistent — expansion allowed at `N ≥ 20` but the Clopper–Pearson reject gate is non-operative until `M_reject = 50`, so the system could expand before reject performance is evaluable | **Accepted — option (b)** — two-tier reject gate: a small-sample **HARD** guard (zero critical rejects caused by invalid order/state/contract + ≤ 1 non-critical reject in the first N) that is **operative immediately and CAN block** expansion at `N ≥ 20`, with the Clopper–Pearson rate test **reserved for scale-up** at `M_reject = 50`; the "informational only / cannot block or pass" framing is removed and the thresholds are now consistent across the `N ≥ 20 → M_reject` window | §9.3 |

*Codex's additional round-4 note (no-fill / no-trigger pairs are not missing-at-random; counts alone are insufficient if a filled-only IS median drives promotion — wants an intent-to-treat outcome or a conservative penalty/sensitivity bound) is **acknowledged but out of this revision's operator-scoped two-fix mandate**. §9.3 already **censors and counts** no-fill pairs explicitly (never silently drops them); a conservative ITT / penalty-bound treatment is deferred to the next revision and is **not** claimed as resolved here.*
