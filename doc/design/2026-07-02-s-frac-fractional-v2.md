# S-FRAC — fractional shares v2: sizing fidelity, active-path-first (design RFC)

STATUS: design / RFC for review — docs only, no code. The operator formally REOPENED
fractional on 2026-07-02 ("fraction重新讨论设计和实现，计入短期计划") and slotted it into the
SHORT tier. This is the v2 re-discussion design, built on the recorded v1 lessons (three
subrepo PRs closed 2026-06-30 with review threads preserved), NOT a rebuild-from-scratch.
The unified plan (`doc/design/2026-07-02-unified-107-master-plan.md`) currently has no
fractional row; §8 of this doc proposes the exact S-FRAC row for its SHORT tier.
DATE: 2026-07-02

---

## 0. Provenance — what v1 was, why it closed, what changed since

### 0.1 The v1 chain (all CLOSED 2026-06-30, branches `feat/fractional-shares` preserved)

| PR | What it built | Terminal review state |
|---|---|---|
| `renquant-execution#19` | `is_fractionable` broker guard, fail-closed lookup, no-submit classification, `supports_broker_side_stops(symbol, qty)`, fail-closed `place_stop_order` on fractional qty | CHANGES_REQUESTED ×2. Round-1: red CI, broker-stop hazard, silent-floor lookup mutation, skipped-counted-as-submitted. Round-2 (post-fix): the fractional stop capability was **not consumed by the real Z9 caller** (which calls `supports_broker_side_stops()` with no args), and the full buy→sell→zero-residual lifecycle E2E was missing |
| `renquant-pipeline#153` (keystone) | `compute_position_size(fractional=True)` float sizing + `min_notional` dust guard; backend capability negotiation (`supports_fractional`, `resolve_fill_quantity`); fractional Fake/Sim lifecycle; float-preserving exits/trims/rotations | CHANGES_REQUESTED ×2. Terminal blocker: **all evidence exercised `ExecutionPipeline`/`FakeBackend` — a non-active path.** The ACTIVE live path is the umbrella `RunnerAdapter.commit`, which still int-truncates fractional fills; no live `ExecutionBackend` bridges `AlpacaBroker` into the new capability contract |
| `renquant-strategy-104#36` | `execution.fractional_shares.{enabled:true, min_notional:1.0}` in active+golden + pinning test | CHANGES_REQUESTED ×3. Blockers: dependencies unmergeable; **dependency gate was prose-only** (no machine-verifiable capability contract — merged/pinned out of order it activates unsupported behavior); rollback guarantee (disable flag without stranding an existing fractional holding) never proven |

Closure record (same text on all three, 2026-06-30): *"Real remaining blocker = umbrella
RunnerAdapter.commit live-path wiring + software-stop routing + capability gate — a larger
live-decisioning-path change not worth it for the uncertain-EV benefit (deploying idle cash
into a near-noise-IC signal) right now."* Operator priority went to 105.

### 0.2 What changed between the 06-30 close and the 07-02 reopen

1. **Deployment now has an owner that is not fractional.** S7 / lane B parking sleeve
   (`renquant-pipeline#157`, shadow, default-OFF) sweeps idle cash into a β-budgeted
   SPY/SGOV split. "Deploy the 75% idle cash" is the sleeve's AC, not fractional's.
2. **Participation now has an owner that is not fractional.** S6 A-3 one-share floor
   (`renquant-pipeline#156`, default-OFF) removes the selection-by-share-price artifact by
   rounding a whole-share-zeroed high-price name UP to exactly one share, under the regime
   cap and headroom checks.
3. **The artifact kept firing and was measured twice more.** `size_insufficient_cash` =
   `int(target_notional/price) == 0`: BLK dropped in run `2026-07-01-live-01c54b39`;
   BLK **and** AVGO dropped in run `2026-07-02-live-85496d1c` (runs.alpaca.db,
   `candidate_scores.blocked_by`). The 07-01 OXY forensics established the mechanism:
   Kelly × conviction × σ-mult × PV compounded BLK's target to ~$324 < 1 share (~$950–1.1k),
   so which name fills a slot is decided by share price, not score.
4. **A-3's fix has a known cost that only fractional can remove.** Rounding $324 UP to one
   ~$950 BLK share deploys ≈2.9× the risk-budget notional into that name. A-3 buys
   participation at the price of sizing error; fractional buys both at once.

---

## 1. Narrowed scope — v2 ≠ v1

v1 was pitched as "the real cash-drag lever." That framing is dead: deployment belongs to
the sleeve (S7) and participation to A-3 (S6). What is left is exactly what neither of
those can do:

### 1.1 Residual value (a): SIZING FIDELITY

One mechanism kills both remaining sizing errors on high-price names:

- the **int() zero-drop** — `compute_position_size` returns `(0.0, 0)` when
  `target_notional < price` (`renquant-pipeline src/renquant_pipeline/kernel/sizing.py`,
  `compute_position_size`), producing `size_insufficient_cash` (§0.2.3);
- the **A-3 round-up overshoot** — one share of a ~$950 name against a ~$324 target is a
  ~2.9× overshoot of the per-name risk budget (§0.2.4).

With fractional sizing the realized entry notional equals the risk-budget target notional
to within `min_notional` dust and intraday price drift — for cheap names too (a $48 OXY
target of $324 currently floors to 6 shares = $288, an 11% undershoot; fractional makes it
exact). Sizing fidelity is a **TC-term** contribution in the plan's value equation: it
changes HOW MUCH of an already-admitted name is bought, never WHICH names are admitted.

### 1.2 Residual value (b): sweeping residual cash slivers

Whole-share rounding leaves per-name slivers (`target − floor(target/price)·price`) and
leaves the sleeve itself unable to park the last `< 1 SPY share` (~$560) of idle cash —
`#157`'s shadow sweep is whole-share and its `min_trade_notional` is $50. Fractional
sizing shrinks per-name slivers to ~$0, and (as an explicit interaction contract, §7.1)
the sleeve's SPY/SGOV legs are themselves fractionable — sleeve sweeps down to $1 notional
become possible, taking structural idle to ≈0 without touching sleeve policy.

### 1.3 What v2 does NOT chase (explicit)

- **NOT deployment.** The ≥60% deployed AC belongs to S6+S7 (lane A/B). v2 adds no new
  capital to the book and does not compete for that AC.
- **NOT participation/admission.** Which names are admitted is upstream of sizing and
  stays untouched (pinned by test in every stage). A-3 owns the participation fix and
  remains the fallback (§7.2).
- **NOT alpha, and NOT "more size into the signal."** The 06-30 uncertain-EV objection —
  deploying more idle cash into a near-noise-IC signal — is *accepted, not relitigated*:
  v2 never increases a name's target notional beyond what the sizing stack already
  decided (fractional realizes the target *exactly*; A-3's round-up is the path that
  overshoots it). D1's model verdict is unaffected either way.
- **NOT intraday trading, NOT new order types, NOT broker adapters beyond the preserved
  #19 scope.**

---

## 2. The v1 fatal lesson → stage 0 is the umbrella active path

v1 died because capability was built and tested on a NON-ACTIVE path. The recorded
lesson (fractional-cash-drag close-out, 2026-06-30; also the operator's 2026-06-24
deployed-but-dark rebuke): *scope the active-path (umbrella) wiring + the safety envelope
BEFORE building subrepo capabilities.* v2 therefore inverts v1's build order.

### 2.1 The measured active-path facts (as of 2026-07-02, live tree)

- The live daily and intraday entry points (`scripts/daily_104.sh`,
  `scripts/intraday_sell_104.sh` → `live_multirepo.py`) execute through the umbrella
  `RunnerAdapter.commit` (`backtesting/renquant_104/adapters/runner.py`), NOT through
  `renquant-pipeline`'s `ExecutionPipeline` (its own module docstring says it is
  "test-backed but not yet the active adapter execution path").
- `runner.py:1372`: `shares = int(execution["filled_qty"] or shares)` — a broker fill of
  0.435578 becomes **0 shares** in `orders_placed`, live_state, trade journal, cash
  accounting, and the Z9 stop quantity. This is the exact line Codex cited to block #153.
- The Z9 stop caller (`adapters/z9_stops.py`) checks
  `broker.supports_broker_side_stops()` **with no arguments** and documents the invariant
  "broker-resident GTC stops are the only protection that survives this machine dying."
  #19's per-quantity capability signature is never consumed.

### 2.2 Stage 0 deliverable: a fractional-capable commit contract on the ACTIVE path

Umbrella PR (the live decisioning core — smallest possible diff, default-inert):

1. **Quantity contract.** `RunnerAdapter.commit` preserves broker `filled_qty` as a float
   end-to-end: `orders_placed`, `live_state.json` positions, trade journal, cash
   accounting (`invest = filled_qty × filled_avg_price` at float precision), top-up and
   full-exit reconciliation, and STATE-EXT-SELL fill normalization. Whole-share fills are
   unchanged bytes (an integral float formats/compares identically where it matters;
   regression-pinned).
2. **Stop routing contract.** The Z9 call sites pass the held quantity:
   `supports_broker_side_stops(symbol, qty)`. Fractional holdings route to the software
   stop registry (stage 3); until stage 3 exists, a fractional holding with no software
   stop layer is a **fail-closed condition at entry** — the buy is not submitted (this is
   the machine-verifiable ordering guard: stage-2 sizing cannot activate ahead of stage-3
   protection).
3. **Capability gate (the #36 blocker, closed).** A machine-verifiable preflight:
   `execution.fractional_shares.enabled=true` requires (a) the broker adapter to expose
   the fractional contract (`is_fractionable` + no-submit classification, from #19), and
   (b) the software-stop layer to report itself armed (stage 3). Either missing ⇒
   fail-closed before any order is emitted, with a dedicated ledger/audit reason. Prose
   merge-ordering is never the gate again.

### 2.3 Stage 0 verification — the active-path audit test

Enumerated, all in the umbrella test suite (the repo that owns the runner):

- **E2E through the real commit path**: drive `RunnerAdapter.commit` with a fake broker
  returning `filled_qty=0.435578` → assert `orders_placed[0]["shares"] == 0.435578`,
  live_state position is fractional, journal `filled_qty` fractional, cash decremented by
  the exact fractional notional, and stop routing selected software (or fail-closed while
  stage 3 is absent). Then the reverse: fractional SELL → position removed → **zero
  residual dust** in live_state (the #19 round-2 lifecycle demand, now on the real path).
- **Truncation audit**: a static test asserting no `int(...)` cast is applied to fill
  quantities anywhere on the commit path (`runner.py`, `runner_execmath.py`,
  `runner_ext_sell.py`, `broker_sync.py`) unless guarded by the whole-share branch —
  the same check-script pattern as `scripts/check_model_bundle_consistency.py`.
- **Active-path liveness proof**: an audit test that walks the live entry points
  (`daily_104.sh` / `intraday_sell_104.sh` → `live_multirepo.py`) and asserts the
  executed commit implementation is the one carrying the fractional contract (e.g. the
  run bundle records a `commit_path_fingerprint`), so "the live runner exercises the new
  path" is a recorded fact per run, not an assumption. This is the direct anti-regression
  for merged-is-not-deployed / deployed-but-dark.
- **Flag-off regression**: with the flag absent/false, byte-identical behavior
  (order dicts gain no new fields; whole-share truncation semantics preserved).

Stage 0 merges **before any subrepo capability work restarts**. It is safe standalone: it
only widens what the commit path can represent and fail-closes what it cannot protect.

---

## 3. The software-stops design (the #19 hazard, closed by design not by hope)

### 3.1 Why broker-native stops don't cover fractional positions

Verified 2026-07-02 (§4): Alpaca fractional orders — including the newer fractional
stop/stop-limit support — are **TIF=DAY only**. The Z9 invariant requires a **GTC**
broker-resident "dead-box" stop that survives this machine dying. No GTC = the invariant
is structurally unsatisfiable for a fractional quantity at this broker today.
`AlpacaBroker.place_stop_order` submits `TimeInForce.GTC`
(`renquant-execution src/renquant_execution/alpaca_broker.py:183`) — the broker would
reject a fractional qty on that request; #19 made this fail closed at preflight, which
prevents the doomed order but leaves the position **unprotected**. v2 must supply the
protection, not just refuse the broken order.

### 3.2 Where the software stop lives

The **intraday sell-only loop** is the natural host and already exists:
`scripts/intraday_sell_104.sh` runs on a 12-minute launchd cadence during market hours
(`com.renquant.intraday104.plist`; the script header's "~30 min" comment is stale) and
already evaluates stop-loss / trailing-stop / SDL / max-hold / model-sell against fresh
5-min bars via `SellOnlyPipeline`, never placing buys.

**Delta needed for fractional quantities** (small by design):

1. Exit quantity plumbing accepts floats (the preserved #153 work already float-safes
   `ExecuteExitsTask`, trims, and full-liquidation in the pipeline repo; stage 0 float-safes
   the umbrella commit/exit path).
2. A **software-stop registry** entry per fractional holding: `{ticker, qty, stop_price,
   armed_at, kind: "software"}`, persisted in live_state next to `_stop_orders` (Z9's
   broker-stop bookkeeping), written at entry commit, never-loosen on top-up (same
   invariant as `_z9_place_or_replace_stop`).
3. The sell-only loop evaluates registry entries each pass exactly like its existing
   stop-loss rule and emits a fractional market SELL (DAY) on breach; full-liquidation
   clamps fp dust to exactly 0.0 so the position is reaped with zero residual.
4. **Belt-and-braces (optional, flagged)**: additionally place a broker-side fractional
   stop as a DAY order re-armed each morning by the pre-open pass — broker-resident
   protection *during* market hours even if this machine dies mid-session, at the cost of
   a daily re-arm dependency. Default OFF in v2 stage 3; measured before enabling.

### 3.3 Failure-mode analysis: gap-down through a software stop vs a native stop

| Scenario | Native GTC stop (whole-share status quo) | Software stop (fractional v2) | Delta / mitigation |
|---|---|---|---|
| Intraday decline through stop | Broker fires at touch; market-order slippage only | Fires at next loop pass: worst case ≈12 min detection + slippage | Bounded extra slippage ≈ 12-min move; acceptable for multi-day holds; belt-and-braces DAY stop (§3.2.4) removes it |
| Overnight gap-down through stop | GTC fires at open (still gaps — a native stop does NOT price-protect a gap, it fills at the open print) | Loop's first pass after open fires; fill ≈ same open-gap print + ≤12 min | Near-parity: gap risk is dominated by the gap itself, not the trigger mechanism. This is the honest core: **a native stop's advantage in a gap is minutes, not the gap** |
| This machine dead, market open | Protected (broker-resident) | UNPROTECTED until machine returns | The real regression. Mitigations: (a) belt-and-braces DAY stop covers the current session; (b) hard cap on total fractional-sized exposure (§6 stage 3 AC) so worst-case unprotected notional is budgeted; (c) existing backup/liveness alerting (launchd backup plist monitors intraday writes) pages the operator |
| Machine dead multi-day | Protected | Unprotected beyond session | Same cap + operator page; kill condition if liveness alerting is not in place |
| Broker rejects the software-stop SELL (halted stock etc.) | Same risk for native (stop can't fill in a halt) | Same | Parity |

Recorded risk statement (what enabling stage 3 accepts): fractional positions trade
broker-resident dead-box protection for loop-resident protection with a ≤12-minute
evaluation cadence plus a machine-liveness dependency, in exchange for exact risk-budget
sizing; the unprotected-notional worst case is capped by config
(`fractional_max_book_pct`, proposed default 10% of PV) and covered intraday by the
optional DAY-stop belt.

---

## 4. Broker order semantics inventory (verified via WebSearch, 2026-07-02)

Facts, per Alpaca's current docs
([Fractional Trading](https://docs.alpaca.markets/us/docs/fractional-trading),
[Orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca),
[changelog: fractional stop/stop-limit](https://docs.alpaca.markets/changelog/support-for-fractional-usd-stop-stop-limit-lct-stop-stop-limit-limit-with-extended-hours-orders)):

- An order carries **either** fractional `qty` **or** `notional` (dollars) — both set ⇒
  HTTP 400. Both accept up to 9 decimal places. Minimum ≈ $1 notional.
- Fractional supports **market, limit, stop, and stop-limit** order types — but **all with
  TIF=DAY only**. No GTC on any fractional order. (This is *wider* than the v1
  assumption of "market+DAY only" — the limit/stop widening is a 2025+ change — but the
  no-GTC constraint that matters for Z9 is unchanged.)
- Fractionability is a **per-asset flag** (`get_asset(symbol).fractionable`, ~2,000+ US
  equities); non-fractionable symbols must remain whole-share (the #19 guard).
- Fractional orders can execute in extended/overnight sessions per the changelog; v2 does
  not use this (live path is RTH market orders, unchanged).

### Consequences for the order state machine

- **DAY-only ⇒ a fractional order can expire unfilled at close.** The commit path's
  `pending` branch (order accepted, not filled) must treat end-of-day expiry as a
  terminal no-fill, not a resting order — same-day reconciliation only, no GTC carryover
  bookkeeping. (Market-DAY in RTH effectively always fills; the state must still be
  modeled.)
- **Partial fills of fractional qty are floats** — `filled_qty` accumulates in fractions;
  `broker_order_execution`'s requested-vs-filled comparison and the pending/filled
  classification must compare floats with a dust epsilon, and persisted quantity must be
  the broker's float verbatim (never re-derived from notional/price).
- **`notional` vs `qty` choice (design decision, §6 stage 1/2):** v2 sizes and submits by
  **fractional `qty`** computed from the target notional (floored at 6dp, as #153 built),
  NOT by `notional` orders. Rationale: (a) the whole downstream contract (positions,
  stops, journal, wash-sale lots) is quantity-denominated; (b) a `notional` order returns
  a broker-computed qty anyway, adding one more derived quantity to reconcile; (c) 6dp
  floor keeps realized ≤ target (never rounds up past a cap). The ≤$1-per-name dust this
  leaves is accepted and measured. `notional` submission is kept as an open question
  (§9.4) for the sliver-sweep use case only.
- **Min notional $1** aligns with #153/#36's `min_notional: 1.0` dust guard — orders
  below it are never emitted.

### Consequences for the paired-IS collectors (105 / #227 measurement pins)

Collector and paired-IS schemas must carry `qty` as float and record
`requested_notional` / `filled_notional` explicitly; IS comparisons for fractional
entries are notional-denominated (per-share bps × fractional shares misleads at N<1).
The N1 collectors should accept this from day one (schema-level float, no int casts) so
fractional's later arrival is not a collector migration.

---

## 5. Reuse inventory — the preserved `feat/fractional-shares` branches

| Asset | Verdict | Notes |
|---|---|---|
| **execution#19**: `is_fractionable` cached lookup, fail-closed `_FractionableLookupError` (no failure caching), explicit `rejected_non_fractionable` / no-submit statuses, `classify_broker_result` + `is_no_submit_status`, audit `n_skipped` | **Salvageable as-is** | All four round-1 hazards were fixed and re-reviewed; CI green at close (95 passed). Rebase onto current main; keep |
| **execution#19**: `supports_broker_side_stops(symbol, qty)` signature + fail-closed `place_stop_order` on fractional qty | **Salvageable as-is**, but only lands with its consumer | Round-2 blocker was the unconsumed capability — stage 0 (§2.2.2) is the consumer; merge exec-side + umbrella-side together |
| **execution#19**: E2E tests through `execute_live_commit` | **Needs rework** | They prove the execution-repo path; stage 0's audit tests on `RunnerAdapter.commit` are the ones that carry the burden now. Keep as execution-repo regression, do not re-cite as active-path evidence |
| **pipeline#153**: `compute_position_size(fractional=, min_notional=)` float sizing, floor-not-round, dust guard, `fractional_sizing_cfg` fail-closed config reader | **Salvageable as-is** | The sizing math survived review; rebase. One addition: the A-3 supersession seam (§7.2) now exists in `SizeAndEmitTask` (#156) and the flag-priority logic is new work |
| **pipeline#153**: backend capability negotiation (`supports_fractional`, `resolve_fill_quantity`, fail-fast `PrepareExecutionTask`), fractional Fake/Sim lifecycle, float-preserving exits/trims/rotation/QP-sell reads | **Salvageable with rework** | The abstractions are sound and reviewed; rework = bridge them to the ACTIVE path (stage 0 contract) instead of `ExecutionPipeline`-only, and re-point the sim-parity tests at whatever backend the shadow replay actually uses (§6 stage 3) |
| **pipeline#153**: "LEAN stays whole-share, fails fast on fractional intent" | **Salvageable as-is** | Correct boundary; LEAN backtest parity is explicitly out of v2 scope (whole-share sim remains the backtest convention; sim parity for the SHADOW path is stage 3) |
| **strategy#36**: `execution.fractional_shares` block + pinning test | **Obsolete as shaped** | It set `enabled:true` in active+golden — v2 flag discipline is default-OFF with staged enable; and its prose merge-order gate is replaced by the stage-0 machine-verifiable capability gate. Rewrite as a default-`false` key + capability-contract test; the `_provenance` documentation pattern is worth keeping |
| **v1's framing: "fractional = the cash-drag real lever"** | **Obsolete** | Superseded by #156 (participation) + #157 (deployment); v2 scope is §1 |

---

## 6. Staged implementation plan — S-FRAC in the SHORT tier

Global flag discipline: every stage default-OFF; nothing live-enables until stage 3's
shadow evidence clears; **buy-side fractional can never activate without the stop layer
armed** (machine-checked, §2.2.3). Global kill condition: if D1's verdict (S4) FAILs and
the routed response shrinks live trading, S-FRAC stages 1–3 pause (capability without a
book to size is motion, not impact) — stage 0 still merges (it is a correctness fix to
the commit contract regardless).

### Stage 0 — umbrella active-path contract + audit (the v1 lesson, first)

- **What**: §2.2 (float-preserving commit, qty-aware stop routing + fail-closed entry,
  machine-verifiable capability gate) + §2.3's four audit tests.
- **AC**: all §2.3 tests green in the umbrella suite; flag-off byte-identical pin green;
  a daily-full run bundle records `commit_path_fingerprint`; no behavior change live
  (flag absent).
- **Tests**: §2.3 enumeration.
- **Flags**: none live; contract is inert until `fractional_shares.enabled`.
- **Kill/defer**: if the commit-path diff cannot stay small/reviewable (the 06-30 "larger,
  higher-risk undertaking" concern re-materializes), STOP and re-scope — that outcome
  re-validates the v1 close and is reported honestly, not powered through.

### Stage 1 — execution-repo fractional order support (rebase #19, hazards fixed)

- **What**: rebase the preserved #19 branch; keep the fail-closed lookup / no-submit
  classification / stop preflight; add DAY-expiry terminal handling + float
  requested-vs-filled comparison (§4).
- **AC**: execution CI green with the `alpaca` extra installed (the round-1 lesson —
  never ship the broker boundary untested against real `alpaca-py`); the
  `supports_broker_side_stops(symbol, qty)` capability is consumed by the stage-0
  umbrella caller in the same pin-advance; no-submit statuses never counted submitted.
- **Tests**: #19's suite (rebased) + DAY-expiry state test + float partial-fill test.
- **Flags**: broker guard is unconditional safety (active even when fractional is off —
  it also protects against any future fractional qty reaching the broker by accident).
- **Kill/defer**: broker semantics drift (re-verify §4 at implementation time; if Alpaca
  has changed fractional TIF/type rules, re-run the §4 inventory before merging).

### Stage 2 — pipeline sizing: notional-exact fractional under a flag, superseding A-3's round-up when enabled

- **What**: rebase #153's sizing core; replace the `int()` clamp with 6dp-floored
  fractional qty when `execution.fractional_shares.enabled` (per-symbol fallback to
  whole-share + A-3 floor when `fractionable=False`); supersession seam per §7.2
  (fractional check runs BEFORE the one-share floor; the floor's round-up branch becomes
  unreachable for fractionable names while the flag is on; A-3 remains the fallback).
  Ledger fields: `sizing_mode ∈ {whole_share, one_share_floor, fractional}` +
  `target_notional` + `realized_notional` on every order (feeds the §7.4 KPI).
- **AC**: name selection provably unchanged (admission-set equality test across flag
  states on fixed fixtures — sizing fidelity must not admit or drop anyone); realized ≤
  target per name (floor semantics); dust < `min_notional` never emitted; A-3
  supersession + fallback both pinned by test; full pipeline suite green.
- **Tests**: #153's rebased suite + supersession/fallback tests + admission-invariance
  pin + BLK/AVGO/OXY fixture reproducing the §0.2.3 runs (target $324 @ $950 ⇒ 0.341052
  shares, not 0, not 1).
- **Flags**: default OFF in strategy-104 (the #36 rewrite adds the key as `false`);
  turning it on requires the stage-0 capability gate to pass.
- **Kill/defer**: if the shadow replay (stage 3) shows fractional sizing altering
  admission/selection in ANY session, that is a bug class, not a tuning question — halt
  until root-caused.

### Stage 3 — software stops + sim parity + shadow evidence (the enablement gate)

- **What**: §3.2's registry + sell-only-loop delta + optional DAY-stop belt (own flag,
  default OFF); `fractional_max_book_pct` cap (default 10%); sim parity = the shadow
  replay backend models fractional quantities (from #153's Fake/Sim work) so
  shadow-vs-live compare requested/submitted/filled qty, notional, caps, stop coverage,
  and residual-after-exit — the exact comparison Codex prescribed on #153.
- **AC (pre-enable evidence, per the #36 review shape)**: ≥10-session shadow with frozen
  session list (RS-2 discipline: plumbing validation, explicitly NOT an economic
  verdict), showing for BLK/AVGO-class names: fractional qty sized & would-submit,
  cap/notional honored, software stop armed at entry, clean full liquidation, zero
  residual dust; plus one live-tree drill of the rollback invariant — flag OFF with an
  existing fractional holding ⇒ position remains fully exitable and stop-covered until
  naturally closed (the #36 round-3 demand).
- **Tests**: registry never-loosen invariant; breach ⇒ SELL emitted on next loop pass
  (fixture clock); machine-death cap arithmetic; parity suite.
- **Flags**: `fractional_shares.enabled` (sizing), `fractional_stops.day_belt_enabled`
  (belt), `fractional_max_book_pct`. Live enable = a recorded operator decision on the
  shadow packet, per house rules.
- **Kill/defer**: if liveness alerting for the sell-only loop cannot be demonstrated
  (test-fired page on a missed pass), fractional stays shadow — the §3.3 machine-death
  row is the accepted-risk boundary and it is only acceptable WITH the pager. If the
  measured shadow slippage delta of loop-resident stops exceeds the sizing-fidelity gain
  (§7.4 metric) on realistic fixtures, defer stage-3 enable and keep A-3 as the
  participation mechanism.

Stage ordering is strict: 0 → 1 → 2 → 3; pins advance per stage; #36's rewritten
config-enable PR merges last, after the stage-3 packet.

---

## 7. Interaction contracts

### 7.1 With the parking sleeve (S7, pipeline#157)

The sleeve currently plans **whole-share** SPY sweeps (min_trade_notional $50) and
tolerates SGOV qty-null in shadow. Contract: the sleeve is a CONSUMER of fractional
sizing, never a driver — when `fractional_shares.enabled`, the sleeve's sweep planner MAY
size SPY/SGOV legs fractionally (both are fractionable), shrinking structural idle from
"< 1 SPY share" (~$560) to `< min_notional` (~$1). This is a one-line sizing-mode read in
the sleeve planner, gated behind BOTH flags, and is stage-3+ follow-up work — noted here
so the sleeve's live-mode implementation (its own follow-up PR) reserves the seam. The
sleeve's whole-share shadow AC is not blocked on fractional in any way.

### 7.2 With A-3 (S6, pipeline#156) — supersession + fallback

- Flag precedence in `SizeAndEmitTask`: `fractional` (exact) → `one_share_floor`
  (round-up) → whole-share drop. When fractional is ON and the symbol is fractionable,
  the A-3 round-up branch is unreachable (its `one_share_floor_roundups` counter goes to
  0 for those names — itself a monitorable supersession signal).
- A-3 remains live fallback for: fractional flag OFF (all of v2's staging), symbol
  non-fractionable, broker fractional preflight fail-closed.
- A-3's shadow protocol (RS-2) proceeds independently and first; v2 does not block, gate,
  or reuse its evidence. If A-3's preregistered gate clears and it live-enables before
  S-FRAC stage 3, the ~2.9× overshoot is the KNOWN, ledger-visible cost
  (`size_floor_reason` field) that S-FRAC later removes — that ledger series is the
  before/after for the §7.4 metric.

### 7.3 With wash-sale / anti-churn (fractional lots)

- Wash-sale state (`last_sell_dates`, STATE-EXT-SELL stamping) is per-ticker, not
  per-lot — fractional changes quantities, not the stamp mechanics. Contract: a
  fractional SELL is a SELL for wash-sale purposes regardless of size; a $3 dust
  liquidation therefore wash-sale-blocks re-entry exactly like a full exit. To avoid
  manufacturing blocks, the sliver-sweep/dust path must NOT emit micro-sells of names the
  model may re-enter: full-liquidation dust is clamped to 0.0 in the same order (never a
  separate later micro-sell), and no standalone dust-harvest sell pass is introduced.
- Anti-churn: `min_notional` ($1 broker floor) is too low as a churn guard; v2 adopts a
  separate `min_fractional_trade_notional` (proposed $25) for any INCREMENTAL fractional
  order (top-ups, trims), while entry/exit orders follow the sizing stack unfiltered.
  Prevents 12-min-loop trims from degenerating into fee-less-but-taxable micro-churn.

### 7.4 With the KPI scorecard — the sizing-fidelity metric (defined)

Add to the daily KPI scorecard (`doc/research/evidence/kpi_scorecards/`):

```
sizing_fidelity_gap (per accepted entry order):
    gap_i = |realized_notional_i − target_notional_i| / target_notional_i
      where target_notional_i = the sizing stack's risk-budget notional
      (post Kelly/conviction/σ/PV, pre share-quantization), stamped on the
      order by stage 2; realized_notional_i = filled_qty × filled_avg_price.
scorecard aggregates (daily):
    median_gap, p90_gap, n_entries;
    n_size_insufficient_cash (the zero-drop count — from candidate_scores.blocked_by);
    n_one_share_floor_roundups + their summed |overshoot| notional (A-3 cost, §7.2);
    fractional_book_pct (Σ fractional-sized position notional / PV, vs the cap).
```

Baselines already measurable today: whole-share BLK-class gap = 100% (drop) or ≈190%
(A-3 round-up: |950−324|/324); OXY-class ≈11% (floor undershoot). Stage-2 target:
median_gap ≤ 1% for fractional-sized entries; n_size_insufficient_cash → 0 on
fractionable names. The scorecard row is what makes "sizing fidelity" a standing metric
of the plan's TC term rather than a one-off forensic.

---

## 8. The proposed S-FRAC row (unified plan, SHORT tier)

| ID | Task | Δ / basis | Guidance | AC | P | Plan B → downstream |
|---|---|---|---|---|---|---|
| S-FRAC (NEW) | Fractional shares v2: sizing fidelity + sliver sweep, active-path-first (this doc) | TC-term: kills the measured `size_insufficient_cash` zero-drop (BLK 07-01, BLK+AVGO 07-02) AND A-3's ≈2.9× round-up overshoot in one mechanism; §7.4 metric | stages 0→3 per §6; stage 0 (umbrella commit contract) FIRST; default-OFF throughout; live enable only on the stage-3 shadow packet | §6 per-stage ACs; scorecard: median sizing_fidelity_gap ≤1%, n_size_insufficient_cash → 0 | stage 0–2: 0.85 (rebased, reviewed code); stage 3 enable: 0.6 (stop-layer risk acceptance is an operator call) | A-3 remains the participation fallback (already built, #156); defer re-validates the 06-30 close, book continues on A-3 + sleeve |

Capacity note: S-FRAC slots BEHIND the existing S1–S5 > S8–S10 > S6–S7 > S11–S12 priority
(the PROCESS core and the lane-A/B shadows it depends on come first); its stage 0 can
proceed in parallel as a small, standalone-safe umbrella PR.

## 9. Open questions for review

1. **Stage-0 blast radius.** Is a float-preserving `RunnerAdapter.commit` acceptable as
   ONE PR, or should the operator require the §2.3 truncation audit to land first as a
   read-only inventory (how many int-cast sites actually exist on the commit path) before
   authorizing the mutation PR?
2. **Machine-death risk acceptance.** Is `fractional_max_book_pct = 10%` the right
   worst-case unprotected-notional budget, and is the DAY-stop belt (§3.2.4) worth its
   daily re-arm dependency, or is loop+pager+cap sufficient?
3. **Does stage 3 gate on N1 liveness alerting?** §6 stage 3's kill condition requires a
   demonstrated pager on a missed sell-only pass — should that alerting be built inside
   S-FRAC or claimed from N1 (105 collectors liveness) as a dependency?
4. **`notional` orders for the sliver sweep.** §4 chooses qty-denominated orders for the
   main path; should the sleeve's future fractional sweep (§7.1) use `notional` orders
   instead (exact-dollar parking, no qty reconciliation), accepting a second order-shape
   in the state machine?
5. **Dust threshold.** Is `min_fractional_trade_notional = $25` (§7.3) the right
   anti-churn floor, and should it also apply to sleeve fractional sweeps?
6. **A-3 evidence interaction.** If A-3's shadow gate clears first and live-enables, do we
   let it run live long enough to measure the round-up overshoot cost in the ledger
   (§7.2) before superseding it — i.e., is there value in a deliberate A-3-live window as
   the fractional before/after baseline, or should supersession happen at the earliest
   safe point?
