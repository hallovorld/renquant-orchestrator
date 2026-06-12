# Design — Short-Selling Capability for RenQuant 104

**Status:** design / awaiting review (no code change)
**Scope:** enable the 104 book to profit from declines — phased, gated, account-aware.

---

## 1. Constraints that shape everything (account reality first)

| Constraint | Value | Consequence |
|---|---|---|
| Account equity | ~$10.4k < **$25k PDT** | ≤3 day-trades/5d; shorts must be multi-day holds, never intraday scalps |
| Margin budget | operator cap: **≤20% of Alpaca margin** | short book notional cap ≈ 20% NAV initially |
| Reg T initial / maintenance on shorts | 150% / 130% (broker may set higher per-name) | sizing must reserve margin headroom; a 2× adverse move forces liquidation — hard caps required |
| Alpaca mechanics | margin account; **ETB list only** (no manual locates); borrow fees accrue daily; forced **buy-ins** possible; short proceeds don't reduce buying power | universe = ETB ∩ watchlist, checked at order time; buy-in handling in the runner |
| Short-specific liabilities | unlimited loss, **dividend liability** (shorts pay dividends), gap/squeeze risk | mandatory hard stops, ex-div calendar veto, squeeze guard |

## 2. What our evidence says (no wishful thinking)

- The ranker's **short-side skill is real but thin**: bottom-half within-rank IC **+0.023 (t=2.8)** (capability doc §1.1) — about 2/3 of the long side.
- **In the validation bull year, every prediction decile had positive mean fwd-60d z-label** — naked single-name shorts fight beta almost all the time. Short alpha must therefore be harvested **relative** (hedge/overlay), or **conditioned on regime**.
- We now collect point-in-time short interest (days-to-cover, % float) — the natural **squeeze-guard input**, usable as a *risk veto* before it ever becomes an alpha feature.

## 2.5 Operator mandate (2026-06-12 — binding constraints)

1. **Very high bar:** no short is opened unless the evidence is *especially
   compelling* — quantified as ALL of: bottom-5% of the cross-sectional rank
   (not bottom decile), μ < −τ_strong on N consecutive evaluations (the
   protection state machine inverted, N≥3), regime confirmed BEAR, and every
   §3 Phase-1 veto passing. Default answer is NO SHORT.
2. **Max 2 concurrent single-name shorts** (`risk.short.max_positions = 2`),
   regardless of margin headroom. Index hedge (Phase 0) is exempt from the
   2-name cap but still bounded by the 20%-NAV budget.

## 3. Phased design (each phase independently gated)

### Phase 0 — Portfolio hedge via index short (cheapest, safest, fastest)
Short **SPY** (or buy SH as a long-only fallback) as a *portfolio-level* hedge when the book is risk-off: regime ∈ {BEAR confirmed} or drawdown breaker armed. ETB-trivial, no squeeze, tiny borrow, no dividend surprise timing (known calendar), one instrument.
- Size: hedge ratio h·β_portfolio, h ∈ [0, 0.5] by regime confidence; notional ≤ 20% NAV.
- This replaces "sit in cash and wait" with "monetize confirmed bears" — and it is the only phase that needs almost no new alpha evidence.

### Phase 1 — Conditioned single-name shorts (bottom-of-rank, BEAR/CHOPPY only)
Short candidates = bottom **5%** of the cross-sectional rank (operator bar), **max 2 names**, **only when**:
1. regime ∈ {BEAR, CHOPPY-confirmed} (short alpha must not fight a bull tape);
2. name ∈ Alpaca **ETB** at order time;
3. **squeeze guard**: days-to-cover < τ_dtc AND short %float < τ_si (from our PIT collector);
4. no earnings within ±3d (event gap risk — reuse the existing earnings blackout);
5. borrow-fee estimate < τ_fee.
Sizing: Kelly with the **same σ source**, but per-name cap ≤ 4% NAV and short-book cap ≤ 20% NAV; **hard stop mandatory** (no σ-stop-only shorts): stop at +15% adverse move or 2.5σ, whichever tighter; max-hold = 60d vertical barrier (symmetric thesis horizon).
Exits mirror longs: model protection (μ ≥ +τ N-consecutive → cover), trailing on profit, rank-exit when the name leaves the bottom quintile.

### Phase 2 — Dollar-neutral sleeve (only if Phase 1 passes its gate)
A small long-short extension (e.g. 110/10 → 120/20) targeting rank spread capture with reduced beta. Decide on Phase-1 evidence; not designed in detail here.

## 4. Plumbing inventory (what actually has to change)

| Layer | Change |
|---|---|
| **Pipeline kernel** | positions with signed qty (`shares < 0`); `HoldingState` invariants audited (hwm→low-watermark for shorts; stop/SDL/trailing logic mirrored); Kelly sizing sign-aware; QP constraints extended (gross/net exposure, short cap) |
| **Sell/buy jobs** | new `CoverJob` / short-entry path; exit priority chain mirrored for shorts; wash-sale logic: short covers create their own constructive-sale considerations (simplest: apply the same 30d re-entry block symmetric) |
| **Execution (alpaca adapter)** | `side=sell` short orders + ETB check + buy-in event handling + margin headroom preflight |
| **live_state** | signed positions, short-specific fields (borrow context, low-watermark), round-trips (mirror the sell_streaks/protection_breaches pattern) |
| **Risk gates** | margin-usage gate (≤20%), squeeze veto, ex-dividend veto, per-name/book caps, regime conditioning |
| **WF gate** | short-side evidence REQUIRED before Phase 1 promotion: bottom-decile net-of-borrow-cost alpha in BEAR/CHOPPY replay windows + the standard 3-cut + sanity battery; Phase 0 needs only hedge-effectiveness replay (drawdown reduction vs cost) |

## 5. Risk register (top 6)

1. **Squeeze** — guard: DTC/%float veto + ETB-only + 4% caps + hard stop.
2. **Buy-in** — handle broker-initiated covers in the runner (treat as forced exit, stamp state, alert).
3. **Margin spiral** — 20% book cap + preflight margin headroom + breaker that covers all shorts if maintenance margin utilization > 70%.
4. **Dividend liability** — ex-div calendar veto (cover before ex-date unless spread justifies).
5. **PDT breach** — shorts are multi-day by design; runner must never same-day cover except stop events; count day-trades.
6. **Bull-tape bleed** — regime conditioning is the primary control; Phase-1 inactive in BULL_*.

## 6. Rollout & gating

1. This design review → operator approval.
2. Phase 0 implementation behind `risk.short.enabled` + `mode: "index_hedge"` (default OFF), paper-broker shadow ≥ 2 weeks, replay evidence (2022 bear + 2025-04 dip): drawdown reduction vs hedge cost.
3. Phase 1 only after Phase 0 lives cleanly AND the WF gate shows net short alpha. Same review→PR→pin discipline as everything else; experiments on the epic branch.

## 7. Open questions for the operator
1. Phase 0 instrument preference: short SPY vs long SH (inverse ETF avoids margin/borrow entirely at the cost of daily-reset drag)?
2. Is the 20%-NAV short cap the right initial budget, or smaller (10%)?
3. Tax tolerance: short-term gains treatment on covers is unavoidable — acceptable?
