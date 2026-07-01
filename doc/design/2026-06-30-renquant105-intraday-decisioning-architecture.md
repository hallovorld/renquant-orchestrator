# renquant105 — Intraday (盘中) Real-Time Decisioning Architecture (RFC)

STATUS: design / RFC — the ENGINEERING DESIGN is the prerequisite; build is staged after review. Design first, do not rush to build.
DATE: 2026-06-30
REVISION: r9 (2026-06-30) — addresses Codex **round-8** CHANGES_REQUESTED on `b30dd7a4` (**one** blocking point; **DESIGN docs only, no code**). Codex confirmed the r8 **joint calibration+evaluation bootstrap** is materially addressed, but found the **evaluability floor arbitrary and far too weak** for a one-sided 95% bootstrap non-inferiority decision about a 10-bps margin: `M_admit_min=10` pairs / `S_eval_min=3` sessions treat **session-clustered fills as independent**, a percentile bootstrap over ~3 clusters has **no credible tail resolution / coverage**, and **discarding/redrawing low-diversity resamples** conditions away valid sampling variability (**anti-conservative**). Fixed by **rewriting the prereg §5/§7 evaluability logic**: (1) **derive gate readiness upfront from the independent-session count + a pre-canary precision/power calculation** on the calibration **session-level cluster variance** — pre-registered target one-sided CI half-width `HW_target = 4 bps`, minimum independent sessions `S_ready = max(20, ⌈(1.645·σ̂_sess/HW_target)²⌉)`; the gate stays **NON-EVALUABLE until `S_distinct ≥ S_ready` AND the achieved half-width ≤ `HW_target`**, with a pre-registered not-met response (stays non-evaluable → operations-only; extend the canary under the frozen procedure or fix the cause; **never force PASS/FAIL from underpowered data**); (2) **REMOVE the discard+redraw of low-diversity resamples** as the evaluability mechanism and confine any discard to **pure numerical degeneracy** (undefined `Δ*` only; tiny `M_admit_min=2`; low-diversity-but-computable resamples **retained**); (3) **justify OR replace the 1-session block** via a pre-canary **serial-dependence diagnostic** (Ljung–Box lags 1…5 + Wald–Wolfowitz runs test at `α_dep=0.10`; fail → **stationary block bootstrap** with a data-driven mean block length `L*` from Politis–White 2004). Joint bootstrap / disjoint universes / `B=10000` / `rng_seed=20260630` / one-sided-95% stay frozen; only `k_spread`/`k_auction`/`σ̂²_sess`/`S_ready`/diagnostic-outcome+block-length/caps remain to be populated. Point-by-point map in **§23**. **CI note:** the PR's required checks are independently red on **two pre-existing weekly-APY tests** — the fix is tracked in the separate **PR #211** (weekly-APY look-ahead / injectable as-of) — this docs-only diff did not cause it, but those shared checks must go **green before merge**. Prior: **r8** (2026-06-30) — addresses Codex **round-7** CHANGES_REQUESTED on `9f03becc` (**one** blocking point; **DESIGN docs only, no code**). Codex confirmed the r7 freeze / detached-fingerprint / frozen-procedure / honest-sensitivity-label fixes are materially addressed, but found the Stage-1 uncertainty gate still invalid: **prereg §5 bootstrapped calibration-coefficient uncertainty but NOT evaluation-sample uncertainty** — it re-fit the synthetic model on resampled calibration sessions yet computed every `Δ*` over the **FIXED** canary/admitted set, so the one-sided 95% upper CB captured coefficient error only and was **too narrow to support the +10-bps gate**. Fixed by pre-registering a **joint (nested) session-block bootstrap** that propagates **both** sources over **two disjoint universes split at the readonly/canary boundary**: an **outer** resample of the pre-readonly calibration sessions re-fits `(k_spread,k_auction)`, paired with an **independently drawn** (separate RNG substream, never index-coupled) **inner** block-resample of the **canary** sessions; the matched-**pair** block structure is preserved, and the **exact cross-fit rule** is stated (disjoint universes → **no canary session ever enters a calibration fit**; independent draws). A **degenerate-resample rule** is pre-registered (`M_admit_min=10` admitted pairs / `S_eval_min=3` distinct sessions per evaluation resample → discard + redraw up to `R_redraw_max=100`; base set below `M_admit_min` or redraws exhausted → gate **NON-EVALUABLE**, operations-only, as with `c_max`). Block length (1 session), `B=10000`, `rng_seed=20260630` (spawned into 2 child streams), and one-sided-95% stay frozen; only `k_spread`/`k_auction`/caps remain to be populated. Point-by-point map in **§22**. **CI note:** the PR's required checks are independently red on **two pre-existing weekly-APY tests** (553 pass / 2 fail) — this docs-only diff did not cause it, but those checks must go green before merge. Prior: **r7** (2026-06-30) — addressed Codex **round-6** CHANGES_REQUESTED on `2e5e438e` (four blocking points on the Stage-1 pre-registration; **DESIGN docs only, no code**): (1) the synthetic-baseline artifact + the frozen caps must be **FROZEN before READONLY starts, not just before canary** — readonly already reveals pair composition, opening references, missingness and modeled outcomes, so post-readonly tuning is a leak; the freeze PR must MERGE before readonly and readonly/canary run-creation now **fail closed** on an unfrozen or fingerprint-mismatched artifact, and the artifact is relabeled a **FREEZE TEMPLATE** (§9.2c / prereg §0). (2) the fingerprint is made **detached + single-algorithm** — SHA-256 of the file bytes, stored in a committed sidecar (never inside the hashed file) and stamped in the ledger, with fail-closed verification — removing the self-referential hash and the "sha256 / git-blob" ambiguity (prereg §6). (3) the **calibration + uncertainty PROCEDURE is frozen now** (estimator = constrained Huber through the origin, box constraints, 3 dollar-ADV liquidity buckets + pooling rule, sparse-bucket `N_bucket_min`, winsorize outlier policy, imbalance→price transform, one-sided 95% level, **session-block** bootstrap `B=10000` seed `20260630`, coefficients re-fit per replication) — only the fitted numbers remain to be populated (prereg §3/§5). (4) the §9.2d gate is **renamed** from a "worst-case (Manski-style) bound" to a **chosen adversarial censoring-sensitivity scenario** (5% of observed outcomes lie beyond each cap; the pre-canary batch distribution need not bound intraday outcomes), a **required sensitivity grid + tipping-point** is added, and prereg §4's "never imputed" no-quote wording is **reconciled** with the §7 imputation. Point-by-point map in **§21**. Prior: **r6** (2026-06-30) resolved the Codex round-4 **censoring note** that r5 had acknowledged-but-DEFERRED (the old §19 footnote): no-fill / no-trigger pairs are **not** missing-at-random, so reporting censoring counts alone is insufficient when a filled-only IS median drives promotion. New **§9.2d** reframes the execution-quality estimand as **intent-to-treat (ITT) over the admitted pre-treatment pair set** — no admitted pair is ever dropped — and **replaces the filled-only median with an adversarial censoring-sensitivity bound**: every censored *intraday* cell is imputed to a frozen adversarial cap `IS_cap_hi`, every censored *batch* cell to a frozen favorable cap `IS_cap_lo`, so the imputed median-IS-difference Δ is maximised **against** PASS; PASS requires the **adversarial-scenario** one-sided upper CB of Δ to stay below the +10-bps inferiority margin (the worst intraday executions can no longer disappear from the distribution). The **complete-case** Δ is reported alongside and must agree (a complete-case-PASS / adversarial-FAIL split is the cherry-pick the gate catches → NOT a PASS), and a pre-registered **max-censoring precondition `c_max`** makes the IS gate *non-evaluable* (operations-only) above it. `IS_cap_hi` / `IS_cap_lo` / `c_max` are added to the frozen synthetic-baseline pre-registration (new artifact §7) — they are researcher DOF and are frozen from the pre-canary calibration distribution, never from canary data. Map in §20. r5 (`6f117fd7`) pre-registered the §9.2c synthetic baseline in a frozen-before-canary artifact + resolved the rollout-threshold inconsistency with a two-tier reject gate (small-sample HARD guard that CAN block at N≥20 + Clopper–Pearson reserved for M_reject=50); r4 round-3 (`320b4fc`); r3 round-2 (`268c0af`); r2 round-1 (`c976ed8`). Point-by-point maps §16 (r1), §17 (r2), §18 (r3), §19 (r4), §20 (r6), §21 (r7 / round-6), §22 (r8 / round-7), §23 (r9 / round-8).
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
- **Implementation shortfall (IS) — the Stage-1 execution-quality readout.** Per order, fill vs **its own arrival/reference quote at decision time** (the mid/NBBO when the path decided). Components: realized spread paid, fees, latency (decision→fill), reject rate, partial-fill rate. This is broker/microstructure cost and is path-internal — it does **not** include any market move between paths. **Observability constraint (fixes r3#2): only ONE path can place the real order** for a given `(signal_session, symbol, signal_version)` without double-buying, so only the **intraday** path yields a real fill/spread/latency/reject; the batch counterfactual is readonly and has **no** real broker fill. The comparison is therefore **real-intraday-IS vs a synthetic batch-IS model** (§9.2b) — a readonly shadow decision is explicitly **NOT** a fill-quality control. The IS estimand is defined **over the admitted (pre-treatment) pair set, intent-to-treat** — no admitted pair is dropped for an arm's no-fill; the no-missing-at-random handling is §9.2d.
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

### 9.2c Synthetic-baseline PRE-REGISTRATION artifact (freezes the §9.2b batch model — answers Codex r4#1, hardened r7)
The §9.2b synthetic batch fill carries researcher degrees of freedom — the opening reference field, the slippage parameters, the calibration window, the **estimator/loss/constraints/buckets/outlier policy**, and the uncertainty method — that can move the baseline by **more than the 10-bps gate**, and could be chosen *after* seeing readonly or canary evidence. To remove that, the synthetic batch model is pinned in a **separate pre-registration artifact**, [`doc/design/2026-06-30-stage1-synthetic-baseline-prereg.md`](./2026-06-30-stage1-synthetic-baseline-prereg.md). **That file is a FREEZE TEMPLATE:** its *procedure* (calibration + uncertainty) is pinned by this RFC now, but its fitted *numbers* are placeholders, so it does not yet freeze all values. **A separate calibration/freeze PR must MERGE — flipping status to `FROZEN`, writing the fitted numbers, and committing the detached fingerprint sidecar — BEFORE the READONLY phase begins, not merely before canary** (readonly already reveals pair composition, opening references, missingness and modeled synthetic outcomes, so any post-readonly tuning of coefficients/caps is a leak). **Readonly and canary run-creation FAIL CLOSED** on a non-`FROZEN` status or a fingerprint mismatch (prereg §0.5 / §6). When frozen it pins ALL of:
- **Opening reference + timestamp** — the official **primary-listing opening-auction print** (consolidated opening cross), `event_time` = the auction publication timestamp on session T; named fallback = the first consolidated **NBBO midpoint at/after 09:30:00 ET** when a symbol has no opening auction (`ref_source = nbbo_fallback`). One field, stated — not "an opening reference."
- **Fill-model formula + every parameter value** — `synthetic_batch_fill = P_open + side_sign · (k_spread · half_spread_open + k_auction · auction_slippage_proxy)`, `side_sign = +1` for buys (pay up); `half_spread_open = ½·(ask_open − bid_open)` from the open NBBO; `k_spread` (fraction of the open half-spread paid) and `k_auction` (auction-slippage coefficient) are **fit once on the calibration set and frozen** — their values are written into the artifact, not left open.
- **Calibration dataset + cutoff strictly before readonly** — the trailing **60 trading sessions** of 104's *realized next-open batch fills* vs the same-session opening prints; **cutoff = the last session strictly before the readonly phase begins** (hence strictly before canary). Coefficients are fit once on that window and **never re-fit** after readonly/canary data is observed.
- **Calibration + uncertainty PROCEDURE — frozen now, only the numbers are populated later (answers Codex r6#3)** — the prereg pins every fitting DOF, not just "estimate": response `IS_obs = side_sign·(fill_price − P_open)` regressed **through the origin** on `half_spread_open` and `auction_slippage_proxy`; estimator = **constrained Huber M-estimator** (tuning `c = 1.345·s`, projected IRLS) under box constraints `0 ≤ k_spread ≤ 1`, `k_auction ≥ 0`; **3 liquidity buckets** by trailing 20-session dollar-ADV tercile with a **sparse-bucket pooling rule** (`N_bucket_min = 200`, pool up); **winsorize** calibration IS at the bucket 1st/99th pct; the **imbalance→price transform** `auction_slippage_proxy = (paired_imbalance / total_paired)·P_open`; and the uncertainty method (next bullet). Only the fitted `k_spread` / `k_auction` / caps remain `<<FROZEN AT CALIBRATION>>` (prereg §3).
- **Per-component treatment (each: how handled / censored)** — *spread*: charged via `k_spread · half_spread_open`. *Auction imbalance*: an `auction_slippage_proxy` (bps) from the published opening imbalance (imbalance share / auction size), per liquidity bucket; if the imbalance feed is unavailable → `0`, flagged `auction_imbalance = unavailable` — note this **understates** the batch cost and is therefore **conservative against** the intraday arm (makes the batch look better, raising the bar for an intraday PASS). *Latency*: the synthetic arm fills at the cross, so its modeled latency is **0** (a stated modeling choice); real decision→fill latency is measured only on the real intraday arm. *Fees*: the same commission schedule is applied to both arms (it nets out in the difference but is included). *Rejects*: the synthetic arm **cannot** reject (no real order); a real intraday reject removes that pair's intraday fill → the **pair is censored** (§9.3) and the intraday cell is imputed under §9.2d (`IS_cap_hi`). *No-quote*: no valid open NBBO → **no synthetic fill is formed** → the pair is **censored**, flagged `synthetic_no_quote = true`, and the censored **batch** cell is **imputed under §9.2d** (`IS_cap_lo`) — the earlier "never imputed" wording is reconciled with the §9.2d ITT scheme.
- **Uncertainty-band method + overlap PASS rule (frozen resampling DOF, JOINT calibration+evaluation bootstrap — answers Codex r7)** — a **joint (nested) session-level block bootstrap** propagating **BOTH** calibration-coefficient and evaluation-sample uncertainty over **two disjoint universes split at the readonly/canary boundary**: per replication (i) an **outer** resample of the pre-readonly **calibration** sessions **re-fits** `(k_spread, k_auction)` by the full constrained-Huber procedure (coefficient uncertainty, not an assumed Gaussian), and (ii) an **independently drawn** (separate RNG substream, never index-paired) **inner** block-resample of the **canary** sessions (evaluation-sample uncertainty), with `Δ*` recomputed on the §9.2d imputed-complete admitted set using that replication's coefficients. **Exact cross-fit rule:** the two universes are disjoint (**no canary session ever enters a calibration fit**) and the two draws are independent. `B = 10000`; `rng_seed = 20260630` spawned into two child streams; **one-sided 95%**. **Block length = 1 session UNLESS the pre-canary §5.4 serial-dependence diagnostic (Ljung–Box lags 1…5 + runs test at `α_dep = 0.10`) rejects → a stationary (Politis–Romano) block bootstrap with a data-driven mean block length `L*` (Politis–White 2004), frozen at calibration.** **Gate readiness (rewritten in r9, answers Codex round-8):** the r8 evaluability floor (`M_admit_min=10` pairs / `S_eval_min=3` sessions) was arbitrary and far too weak — session-clustered fills are not independent, a percentile bootstrap over ~3 clusters has no credible tail resolution, and discarding/redrawing low-diversity resamples is anti-conservative — so it is **replaced by a pre-canary power/precision readiness rule**: readiness is fixed **upfront from the independent-session count + a precision calculation** on the calibration session-level cluster variance. The gate is **NON-EVALUABLE** until the canary accrues **`S_ready = max(20, ⌈(1.645·σ̂_sess/HW_target)²⌉)`** distinct **independent** sessions (`HW_target = 4 bps`; `S_floor = 20`; `σ̂_sess` = frozen calibration cluster SD) **AND** the **achieved** one-sided 95% CI half-width `≤ HW_target`; if unmet by end-of-canary the gate **stays non-evaluable → operations-only** (extend the canary under the frozen procedure, or fix the dispersion cause — **never** force a PASS/FAIL from underpowered data). The r8 **discard+redraw of low-diversity resamples is REMOVED**; any discard is now confined to **pure numerical degeneracy** (undefined `Δ*` only; tiny `M_admit_min = 2`; low-diversity-but-computable resamples are **retained**). The r7 procedure block-resampled the calibration window **only** and held the canary set fixed, so its upper CB was too narrow to support the +10-bps gate — fixed in r8. The **one-sided upper 95% CB** of the **matched-pair median IS difference** Δ (intraday − synthetic batch) = the 95th pct of the joint bootstrap `{Δ*}` (computed at gate-evaluation over canary, not at freeze). **PASS requires that upper CB to lie BELOW the +10-bps inferiority margin — i.e. the CI of the difference must EXCLUDE the margin, not merely the point estimate.** If +10 bps **overlaps** the interval, the result is "not distinguishable" → **NOT a PASS** (prereg §5).
- **Immutable fingerprint — detached + single canonical algorithm (answers Codex r6#2)** — one algorithm only: `synthetic_baseline_prereg_sha` = **SHA-256** (lowercase hex) of the file's exact committed bytes (the "sha256 / git-blob" ambiguity is removed). The hash is **stored OUTSIDE the file** — in a committed sidecar `2026-06-30-stage1-synthetic-baseline-prereg.sha256` and stamped in every synthetic ledger row (alongside `synthetic = true`) — so recording it does **not** change the hashed content (no self-reference). Run-creation recomputes it over the file bytes and requires equality with both the sidecar and the ledger stamp plus `STATUS == FROZEN`; any mismatch/missing sidecar/non-FROZEN → run-creation **aborts** and any post-freeze edit **invalidates** the run (prereg §6).

**Until this artifact is FROZEN and its freeze PR has merged (which MUST happen before readonly starts), Stage 1 may validate OPERATIONS ONLY (no-leak + idempotency + reconciliation + session-boundary) — it MAY NOT claim a comparative execution-quality PASS.** Because the freeze precedes readonly and run-creation fails closed on a non-FROZEN/mismatched artifact, no readonly or canary evidence can inform the frozen coefficients or caps.

### 9.2d No-fill / censoring handling — ITT estimand + adversarial censoring-sensitivity bound (answers Codex r4 censoring note; relabeled r7)
The r4 review's closing note: pairs with an intraday no-fill / no-trigger are **not missing-at-random**, so reporting censoring **counts** alone (the r5 state) is insufficient when a **filled-only IS median** drives promotion — an intraday name that failed class-D staleness or whose marketable order did not complete is systematically a *worse* execution context, so dropping it lets the **worst intraday executions disappear** and inflates the filled-only median. Resolution: the execution-quality estimand is **intent-to-treat (ITT) over the admitted (§9.2 pre-treatment) pair set**, and the gating statistic is a frozen **adversarial censoring-sensitivity bound** — never a complete-case median.

**Honest labeling (answers Codex r6#4):** this is a **CHOSEN adversarial SENSITIVITY SCENARIO, NOT a Manski/worst-case support bound.** The caps are the empirical **95th/5th percentiles** of a *pre-canary batch* IS distribution — by construction **~5% of observed calibration outcomes already lie beyond each cap**, and that batch distribution is **not** guaranteed to bound the (unobserved) intraday execution outcomes. So the caps do not define the mathematical support and the prior "worst-case (Manski-style) bound" label is dropped. The gate is this frozen adversarial scenario **plus** a required **sensitivity grid + tipping point** (below) so the fragility of a PASS to the cap choice is explicit.

**Censoring taxonomy + adversarial-against-PASS imputation direction** (every admitted pair stays in the denominator; a censored *cell* — one arm of one pair — is imputed, never the pair dropped):

| Censoring cause | Arm censored | Imputation (adversarial vs PASS) | Also |
|---|---|---|---|
| Intraday **no-trigger** (class-D staleness skip at the tick) | intraday | `IS_cap_hi` (push intraday cost UP) | — |
| Intraday reject — **critical** (invalid order/state/contract) | intraday | `IS_cap_hi` | **+ Tier-1 HARD halt** (§9.3); never just censored |
| Intraday reject — **non-critical** (venue/throttle/no-quote) | intraday | `IS_cap_hi` | counts to the Tier-1 `≤1-in-N` budget (§9.3) |
| Intraday **DAY order unfilled** at close-cancel | intraday | `IS_cap_hi` | — |
| **Synthetic no-quote** (no valid open NBBO) | batch | `IS_cap_lo` (push batch cost DOWN) | flagged `synthetic_no_quote` (§9.2c) |
| **Both arms** censored | both | (`IS_cap_hi`, `IS_cap_lo`) | counts toward `c_max` |

A censored **intraday** cell is imputed to `IS_cap_hi` (assume the missing intraday execution was as *bad* as the frozen cap) and a censored **batch** cell to `IS_cap_lo` (assume the missing batch execution was as *good* as the frozen cap). Both directions **enlarge** `Δ = IS_intraday − IS_batch`, so the imputed Δ is the **most adversarial within the frozen scenario**: if the gate still passes when every censored cell is pushed maximally against it *within this scenario*, censoring within the scenario cannot have manufactured the PASS.

**Gating statistic — adversarial-scenario bound (replaces the filled-only median):** complete both arms over the admitted set with the table's adversarial imputation, then apply the §9.2c / prereg-§5 one-sided **upper confidence bound of Δ** to that imputed-complete admitted set. **PASS requires that adversarial-scenario upper CB of Δ to remain BELOW the +10-bps inferiority margin** (CI excludes the margin, per §9.2c). This is the only IS gate; the filled-only ("complete-case") median is **not** a gate.

**Frozen caps (researcher DOF → pre-registered, never set from canary data):** `IS_cap_hi` and `IS_cap_lo` are pinned in the synthetic-baseline pre-registration artifact (§7 there), computed from the **pre-canary calibration distribution** (§9.2c §3): `IS_cap_hi` = the **95th percentile** and `IS_cap_lo` = the **5th percentile** of the calibration-window realized 104 next-open IS — a deliberately conservative, frozen **scenario** proxy (NOT a support bound; the only IS distribution that exists strictly before canary). They are frozen with the rest of the artifact (before readonly, §9.2c) and stamped via `synthetic_baseline_prereg_sha`.

**Sensitivity grid + tipping point (REQUIRED report, answers Codex r6#4):** because the caps are a chosen scenario and not a hard support bound, the freeze report and **every** session-window report MUST recompute the upper-CB gate over a **cap-severity grid** — intraday cap at the **{90, 95, 97.5, 99}th** percentile with the batch cap mirrored to **{10, 5, 2.5, 1}th** (95/5 is the frozen gate row; severity increases across the grid) — and report per-grid-point PASS/FAIL plus the **tipping-point percentile** at which the gate flips PASS↔FAIL, so a PASS that holds only at the frozen point is flagged **fragile** (prereg §7.2). Also reported each window: (i) the **complete-case** Δ (drop censored — the optimistic naive readout), (ii) the **adversarial-scenario** Δ (the gate), and (iii) the **censoring fraction by cause**. A **complete-case PASS with an adversarial-scenario FAIL is exactly the cherry-pick the gate exists to catch → NOT a PASS** (the gate is the adversarial-scenario bound; complete-case is descriptive only).

**Max-censoring precondition (evaluability):** if the censored fraction of admitted pairs exceeds the pre-registered `c_max` (frozen; **proposed 10%**), the IS gate is **NOT evaluable** — a high censoring rate is a data-plane / quote defect, not an execution-quality result. Stage 1 then validates **operations only**, the censoring cause is fixed, and the window is re-run. (Critical-cause intraday rejects independently trigger the Tier-1 HARD halt regardless of `c_max`.)

### 9.3 Pre-registered Stage-1 PASS gate (concrete values — the synthetic-baseline artifact + caps frozen before READONLY, the K/N/margin values frozen before canary)
- **No-leak:** the §6 four-class replay invariant holds for every tick in every canary session.
- **Idempotency:** zero duplicate filled positions per `parent_intent_id`; `reserved_cash ≥ 0`; the §7 economic invariant `target_qty = cum_filled + open_qty + remaining_unsubmitted` and `cum_filled + open_qty ≤ target_qty` (retries never overfill) hold always; no order exceeds the §10 envelope.
- **Reconciliation:** at session close, broker state == ledger == run-bundle, every session.
- **Execution-quality (IS) acceptance (requires the §9.2c pre-registration to be FROZEN — and its freeze PR merged before readonly — first):** the **one-sided upper confidence bound** of the (real intraday − synthetic batch) **median IS difference** Δ — computed over the **admitted (ITT) pair set with §9.2d adversarial-scenario imputation of every censored cell** (NOT a filled-only median) — must lie **below the +10-bps inferiority margin**, i.e. the uncertainty band of the *difference* must **exclude** the margin, not merely the point estimate (§9.2c). A point estimate inside the band, or a band that overlaps the 10-bps margin, reads as "not distinguishable" → **NOT a PASS**. The **complete-case** Δ and the §9.2d **sensitivity grid + tipping point** are reported alongside and must agree; a complete-case-PASS / adversarial-scenario-FAIL split → **NOT a PASS** (§9.2d). The gate is **not evaluable** if the censored fraction exceeds `c_max` (§9.2d), **or if the prereg-§5.2 pre-canary power/precision readiness is not met** — fewer than `S_ready` distinct independent canary sessions, or an achieved one-sided 95% CI half-width above `HW_target = 4 bps`; an underpowered canary stays **operations-only** and yields no execution-quality verdict (never a forced PASS/FAIL). The synthetic batch model used is exactly the one pinned in `2026-06-30-stage1-synthetic-baseline-prereg.md` (its detached `synthetic_baseline_prereg_sha` stamped in every synthetic ledger row; run-creation fails closed on a non-FROZEN/mismatched artifact). **Until that artifact is frozen and merged before readonly, this acceptance cannot be evaluated and Stage 1 validates operations only.**
- **Denominators (each defined precisely — they are NOT interchangeable; answers Codex r3#3):**
  - **Reject rate = rejected submissions / ATTEMPTED submissions** — every submission attempt, accepted or not. *Not* accepted orders: a rejected order is by definition not accepted, so accepted-orders cannot be the denominator for rejects.
  - **Partial-fill rate = partially-filled accepted submissions / accepted submissions.**
  - **IS distribution = filled orders that have BOTH a valid arrival quote and a fill** — real fills for the intraday arm, modeled fills for the synthetic batch arm (§9.2b), kept in separate distributions.
  - **Matched-pair eligibility = pre-treatment eligible pairs** (§9.2), analyzed **intent-to-treat**: a pair where one arm did not fill (intraday no-trigger / reject / unfilled-at-close, or no valid synthetic batch fill) is **censored, recorded by cause, AND carried into the IS gate via the §9.2d adversarial-scenario imputation** (counts alone are insufficient — no admitted pair is dropped, so the worst executions cannot be cherry-picked out of the median).
- **Reject gate — two-tier: small-sample HARD guard now + Clopper–Pearson at scale-up (answers Codex r4#2):** a bare 2% rate is uninformative at canary N (one reject in `N = 20` already reads 5%), **but** reject behavior must still be able to **block** expansion in the small-sample window — so the gate is two tiers, and the small-sample tier is operative immediately:
  - **Tier 1 — small-sample HARD safety guard, OPERATIVE IMMEDIATELY (it CAN block):** from the first live submission through the `N ≥ 20 → M_reject` window, expansion is **halted** if EITHER (i) **any** *critical* reject occurs — a reject caused by an **invalid order / state / contract** (bad qty/price/side, stale or inconsistent position-cash snapshot, idempotency-key violation, contract/symbol mismatch): **zero tolerance, any single one halts**; OR (ii) the raw count of *non-critical* rejects (transient venue/throttle/no-quote) exceeds **`≤ 1` in the first `N`**. This guard is a **pre-registered PASS condition** and **can block or pass** expansion at `N ≥ 20` — it is **not** informational-only.
  - **Tier 2 — statistical reject-rate test, RESERVED for scale-up (`≥ M_reject = 50` attempted submissions):** once attempted submissions reach `M_reject = 50`, the *rate* gate **fails** when the **lower bound of a one-sided 95% binomial (Clopper–Pearson) CI on the observed reject rate exceeds the 2% ceiling** (≥ 95% confident the true rate is above 2%). This is the **scale-up** gate; it does **not** replace Tier 1, which keeps running underneath it.
  - The two tiers are **consistent across the `N ≥ 20 → M_reject = 50` window**: Tier 1 covers it and CAN halt, Tier 2 switches on at `M_reject`. There is **no** window in which reject behavior is unevaluable, and the prior "informational only / cannot block or pass" framing is removed.
- **Rollout discipline (concrete, thresholds now consistent — answers Codex r4#2):** **readonly** (decide + log, place nothing) for **K = 5 sessions** → **canary** = **1–2 allowlisted names** live → **expand only after N ≥ 20 matched admitted pairs** with clean ops (no-leak + idempotency + reconciliation all green) **AND the Tier-1 small-sample reject guard clean** (zero critical rejects + ≤ 1 non-critical reject in the first N). Because Tier 1 is operative from the first live submission, reject performance **is** evaluable at the `N ≥ 20` expansion point — this closes the prior inconsistency where the system could expand before any reject gate could pass or fail. The **Tier-2** Clopper–Pearson rate test then becomes the **scale-up** gate once attempted submissions reach `M_reject = 50`. K, N, the **10-bps IS inferiority margin + the §9.2c CI-excludes-the-margin PASS rule**, the **§9.2d ITT adversarial censoring-sensitivity gate + the frozen caps `IS_cap_hi` / `IS_cap_lo` + the §7.2 sensitivity grid + the `c_max` evaluability precondition**, the **prereg-§5.2 power/precision readiness rule (`HW_target = 4 bps`, `S_ready` / `S_floor = 20`, achieved-half-width evaluability) + the §5.4 serial-dependence-diagnostic block-length branch**, the denominators (above), the **Tier-1 guard** (critical = 0 / non-critical ≤ 1-in-N), and `M_reject = 50` are **the pre-registration**; changing any of them after canary data is observed invalidates the run. The synthetic-baseline model, its calibration/uncertainty **procedure**, and the caps live in the separate `2026-06-30-stage1-synthetic-baseline-prereg.md` (§9.2c); that artifact's freeze PR must **merge before readonly starts** (stricter than the K/N values, which are frozen before canary), and run-creation fails closed on a non-FROZEN/mismatched artifact. Whether the K/N values also move into that file or a sibling `preregistration.md` is open question §15.4.

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

*Codex's additional round-4 note (no-fill / no-trigger pairs are not missing-at-random; counts alone are insufficient if a filled-only IS median drives promotion — wants an intent-to-treat outcome or a conservative penalty/sensitivity bound) was acknowledged-but-deferred in r5. It is **now RESOLVED in r6** — see §9.2d (ITT estimand + the frozen `IS_cap_hi` / `IS_cap_lo` caps + `c_max` evaluability precondition; the bound was called "worst-case/Manski" in r6 and **relabeled an adversarial censoring-sensitivity scenario in r7**, §21#4) and the §20 map below. It is no longer deferred.*

---

## 20. Review-response map — Codex round-4 **censoring note** resolved in r6 (`6f117fd7` → this revision)

| # | Codex point (round-4 closing note) | Disposition | Where |
|---|---|---|---|
| 1 | No-fill / no-trigger pairs are **not missing-at-random**; reporting censoring **counts** is not enough if a **filled-only IS median** drives promotion — the worst executions can disappear. Define an **intent-to-treat operational outcome OR a conservative penalty/sensitivity bound** for no-fill pairs. | **Resolved** — IS estimand is now **ITT over the admitted pre-treatment set** (no admitted pair dropped); the gate is a frozen **adversarial censoring-sensitivity bound** (called "worst-case/Manski" in r6, **relabeled honestly in r7** — §21#4) — censored *intraday* cells imputed to a frozen adversarial cap `IS_cap_hi`, censored *batch* cells to a frozen favorable cap `IS_cap_lo`, so Δ is maximised against PASS; **PASS = adversarial-scenario upper CB of Δ below +10 bps** (not a filled-only median). Complete-case Δ + the r7 sensitivity grid are reported alongside and must agree (complete-case-PASS / adversarial-scenario-FAIL → NOT a PASS). A frozen **`c_max`** makes the gate non-evaluable (operations-only) above it. Caps + `c_max` are pre-registered (artifact §7), frozen from the **pre-canary** calibration distribution — never canary data. | §9.1, §9.2d, §9.3, prereg §7 |

*Note on the two r4 blockers: both were resolved in **r5** (`6f117fd7`) — blocker-1 (synthetic baseline not pre-registered) → §9.2c + the frozen artifact; blocker-2 (rollout thresholds inconsistent) → the §9.3 two-tier reject gate. r6 changes neither; it adds only the censoring resolution above. r6 carries **no genuinely-deferred item** — the previously-deferred censoring note is closed.*

---

## 21. Review-response map — Codex round-6 review of `2e5e438e` (r6→r7; DESIGN docs only)

Codex agreed r6's censoring resolution is correct (ITT over the admitted set; the filled-only statistic is no longer the gate) but left **four blocking findings** on the Stage-1 pre-registration. All four are addressed here — no code, design docs only.

| # | Codex round-6 point | Disposition | Where |
|---|---|---|---|
| 1 | The artifact may still be **tuned after readonly evidence is observed** — it is `DRAFT — UNFROZEN`, requires freeze only before *canary*, and uses placeholders. Readonly reveals pair composition, opening references, missingness and modeled outcomes. Require the calibration/freeze PR to **merge before readonly**, **fail readonly run-creation on an unfrozen/mismatched fingerprint**, and call the current file a **freeze template**, not a file that currently freezes all values. | **Accepted** — the artifact is relabeled a **FREEZE TEMPLATE**; the freeze PR MUST merge **before readonly starts**; readonly *and* canary run-creation **fail closed** on `STATUS ≠ FROZEN` or a fingerprint mismatch. §9.3 header + rollout discipline split the two freeze deadlines (artifact+caps before readonly; K/N/margin before canary). | §9.2c, §9.3, prereg §0 (STATUS + §0.5 guard), prereg Gate-readiness |
| 2 | The fingerprint is **self-referential and ambiguous** — hashing the file and recording that hash inside the same file changes the hashed content; "sha256 / git-blob sha" permits different algorithms. Specify one canonical **detached** fingerprint (or a serialization excluding the field) and define verification. | **Accepted** — one algorithm only (**SHA-256** of the file's exact committed bytes; "git-blob" removed); the hash is **detached** — stored in a committed sidecar `…-prereg.sha256`, **never inside the hashed file** — and stamped in every ledger row; run-creation recomputes it and requires equality with sidecar + ledger stamp + `STATUS == FROZEN`, else aborts. | §9.2c fingerprint bullet, prereg §6, prereg §0 step 3/5 |
| 3 | **Calibration & uncertainty under-specified** — "estimate" / "e.g. bootstrap" leave the estimator/loss, constraints, weights, buckets/pooling, sparse-bucket + outlier policy, imbalance→price transform, confidence level, resampling unit/blocking, repetitions, seed, and parameter-draw distribution open (material DOF vs the 10-bps margin). Freeze the procedure now; only fitted numbers may remain. | **Accepted** — the **procedure is frozen now**: origin regression of signed IS on half-spread + auction-slippage; **constrained Huber** estimator (box `0≤k_spread≤1`, `k_auction≥0`, projected IRLS); **3 dollar-ADV liquidity buckets** + `N_bucket_min=200` pooling; **winsorize** 1/99 pct outlier policy; explicit **imbalance→price transform**; **one-sided 95%**; **session-block bootstrap**, `B=10000`, seed `20260630`, coefficients **re-fit per replication** (no assumed-Gaussian draw). Only `k_spread`/`k_auction`/caps remain `<<FROZEN AT CALIBRATION>>`. | §9.2c (2 new bullets), prereg §3 (§3.1–§3.6), prereg §4 transform, prereg §5 |
| 4 | The "**worst-case bound**" is **mislabeled** (imputing to empirical 95th/5th pct is a chosen sensitivity scenario, not a Manski support bound — 5% of observed outcomes lie beyond each cap; the pre-canary batch distribution need not bound intraday outcomes) and prereg §4 still says censored pairs are "**never imputed**," contradicting the new §7. Rename honestly + add a sensitivity grid / tipping-point (or define hard support bounds); reconcile §4↔§7. | **Accepted** — relabeled a **chosen adversarial censoring-sensitivity scenario** (not Manski / not a support bound) with the "5% beyond each cap" caveat stated; added a **required cap-severity grid {90/95/97.5/99}↔{10/5/2.5/1} + tipping-point** report each window (fragile PASS flagged); prereg §4 no-quote row changed from "never imputed" to **imputed under §7 (`IS_cap_lo`)**, reconciling §4↔§7. | §9.2d (honest-labeling + grid), §9.2c per-component, prereg §7 (§7.1/§7.2), prereg §4 |

*Not merged / not approved by the author. Round-6 findings are design-completeness of the governing RFC; the operational-only build remains separately scopable per Codex's closing note.*

## 22. Review-response map — Codex round-7 review of `9f03becc` (r7→r8; DESIGN docs only)

Codex confirmed the r7 freeze / detached-fingerprint / frozen-procedure / honest-sensitivity-label fixes are **materially addressed**, and left **one blocking finding** — the Stage-1 uncertainty gate. Addressed here — no code, design docs only.

| # | Codex round-7 point | Disposition | Where |
|---|---|---|---|
| 1 | **§5 bootstraps calibration-coefficient uncertainty but NOT evaluation-sample uncertainty.** The procedure resamples the 60 calibration sessions + re-fits the synthetic model, then computes each `Δ*` over the **fixed** canary/admitted set — capturing coefficient uncertainty only. It does **not** resample the canary sessions/pairs whose median intraday and synthetic IS define the estimand, so the one-sided 95% upper CB is **too narrow** and cannot support the +10-bps gate. Pre-register a **joint** procedure: preserve pair structure, block-resample evaluation sessions, propagate calibration-model uncertainty **without leaking canary data** (e.g. nested calibration + evaluation bootstrap, with the exact independence/cross-fitting rule stated), and define what happens when a resample has **too few uncensored/admitted pairs**. | **Accepted** — prereg §5 rewritten as a **joint (nested) session-block bootstrap** over **two disjoint universes split at the readonly/canary boundary**: (i) an **outer** calibration-session resample **re-fits** `(k_spread,k_auction)` (coefficient uncertainty); (ii) an **independently drawn** inner block-resample of the **canary** sessions (evaluation-sample uncertainty); `Δ*` recomputed per replication on the §9.2d imputed-complete admitted set with that replication's coefficients. **Matched-pair/session block structure preserved** (block length = 1 session). **Exact cross-fit rule stated:** the calibration (pre-readonly) and evaluation (canary) universes are **disjoint**, the two draws use **independent RNG substreams** (never index-paired), coefficients are only ever fit on calibration resamples and applied to evaluation resamples → **no canary session ever enters a calibration fit**. **Degenerate-resample rule pre-registered:** `M_admit_min = 10` admitted pairs (≥1 uncensored arm) / `S_eval_min = 3` distinct sessions per evaluation resample → **discard + redraw** up to `R_redraw_max = 100`; base admitted set below `M_admit_min` or redraws exhausted → gate **NON-EVALUABLE** (operations-only, same handling as `c_max`). The joint upper 95% CB now reflects **both** sources; block length / `B=10000` / `rng_seed=20260630` (2 spawned streams) / one-sided-95% stay frozen; only `k_spread`/`k_auction`/caps remain `<<FROZEN AT CALIBRATION>>`. | prereg §5 (rewritten) + §2 / §3.6 / §7.1 cross-refs; RFC §9.2c uncertainty bullet |

*CI is independently **red on two pre-existing weekly-APY tests** (553 pass / 2 fail). This docs-only diff (three `.md` files, no code) did not cause the failure, but the shared required checks must be **green before merge** — the progress doc records the dependency.*

*Not merged / not approved by the author.*

## 23. Review-response map — Codex round-8 review of `b30dd7a4` (r8→r9; DESIGN docs only)

Codex confirmed the r8 **joint calibration+evaluation bootstrap** (disjoint calibration/evaluation universes, preserved within-session pairing) is materially addressed, and left **one blocking finding** — the evaluability floor. Addressed here — no code, design docs only.

| # | Codex round-8 point | Disposition | Where |
|---|---|---|---|
| 1 | **The evaluability floor (`M_admit_min=10` pairs, `S_eval_min=3` sessions) is arbitrary and far too weak** for a one-sided 95% bootstrap non-inferiority decision about a 10-bps margin. Ten fills clustered by session are **not** ten independent observations; a percentile bootstrap over ~3 session clusters has **no credible tail resolution or coverage guarantee**; **discarding/redrawing low-diversity resamples does not create information** — it conditions away valid sampling variability and can make the interval **anti-conservative**. Define gate readiness from the **independent session count + a pre-canary precision/power calculation** using calibration/pilot cluster variance (pre-register target CI half-width or power at +10 bps, minimum independent sessions, and the not-met response); keep the gate **non-evaluable** until that threshold is reached. Also **justify the one-session block** with a pre-canary serial-dependence diagnostic or use a pre-registered moving/stationary block procedure with a data-driven block length. | **Accepted** — prereg **§5/§7 evaluability logic rewritten**. **(1) Readiness from independent sessions + pre-canary precision:** new **§5.2** pre-registers a target one-sided **`HW_target = 4 bps`** CI half-width (with its ≥~0.8-power equivalent at true `Δ=0`) and a **minimum-independent-session** count `S_ready = max(S_floor=20, ⌈(1.645·σ̂_sess/HW_target)²⌉)` computed from the **calibration session-level cluster variance `σ̂²_sess`**; the gate is **NON-EVALUABLE** until `S_distinct ≥ S_ready` **AND** the **achieved** half-width `≤ HW_target`. **(2) Not-met response pre-registered:** stays non-evaluable → operations-only; extend the canary **under the frozen procedure** or fix the dispersion cause — **never force a PASS/FAIL from underpowered data**. **(3) Discard+redraw REMOVED** as the evaluability mechanism (§5.3) — any discard is confined to **pure numerical degeneracy** (undefined `Δ*` only; tiny `M_admit_min=2`; low-diversity-but-computable resamples **retained**, since censoring them is the anti-conservative move). **(4) 1-session block justified/replaced** (§5.4): a pre-canary **Ljung–Box (lags 1…5) + Wald–Wolfowitz runs** diagnostic at `α_dep=0.10` on the calibration session series → **pass ⇒ block=1**; **fail ⇒ stationary (Politis–Romano) block bootstrap** with a **data-driven `L*`** (Politis–White 2004), with a gate-time canary re-check as a fragility flag. Everything else stays frozen; the new fitted numbers (`σ̂²_sess`, `S_ready`, diagnostic outcome + block length) join `k_spread`/`k_auction`/caps as `<<FROZEN AT CALIBRATION>>`. | prereg §5 (§5.1–§5.6, rewritten) + §0 step 1 / §3.6 / §7.1 cross-refs; RFC §9.2c uncertainty bullet, §9.3 |

*The r8 `M_admit_min=10` / `S_eval_min=3` / `R_redraw_max=100` degenerate-resample mechanism is **superseded** — readiness is now the §5.2 independent-session/precision rule, and `M_admit_min` is retained only as a tiny (=2) numerical-degeneracy guard that is **not** an evidence threshold.*

*CI is independently **red on two pre-existing weekly-APY tests** (553 pass / 2 fail) — the fix is tracked in the separate **PR #211** (weekly-APY look-ahead / injectable as-of). This docs-only diff (three `.md` files, no code) did not cause the failure, but the shared required checks must be **green before merge** — the progress doc records the dependency.*

*Not merged / not approved by the author.*
