# Design v5 — Short Capability, Minimal (addresses codex review of #103)

**Status:** design / awaiting review (no code change). Supersedes #103.
**v5 changes vs v4 (all five codex findings):** (1) Phase-A dependencies named
and pinned; (2) execution-contract gate added (order taxonomy, shortability
preflight, negative-position state); (3) companion docs de-contradicted;
(4) E6 redesigned around hedge-vs-cash-de-risk with negative controls;
(5) stale PDT language replaced by the post-2026-06-04 intraday-margin
framework (FINRA Notice 26-10).

---

## 1. What shorting is for here (unchanged)
Insurance (Phase A) > efficiency (Phase B) > conviction shorts (shelved).
Basis: Drechsler & Drechsler (NBER w20282); Muravyev et al. (2025 JF);
Clarke–de Silva–Thorley (2002); Moreira–Muir (2017); Faber (2007). See the
literature-review doc.

## 2. Phase A — Index hedge. Four mechanisms.

1. **Trigger (ONE): `hard_bear`** — with the dependency made explicit:
   - **Pinned code:** `renquant-pipeline` ≥ #112 (merge `5b65f2a`,
     BEAROverrideTask guards) — the pre-#112 detector produced the
     2026-06-11 false-BEAR cascade and MUST NOT drive a hedge.
   - **Pinned config:** `renquant-strategy-104` ≥ #25 (merge `bdedbda`):
     `regime.bear_short_route_require_both=true`,
     `regime.bear_trend_filter={enabled:true, ma_window:200}`.
   - **Runtime requirement:** the umbrella `subrepos.lock.json` pin set must
     include both; Phase A implementation is blocked on a doctor check that
     verifies this at startup.
2. **Position:** short SPY, notional = 0.5 · β_book · NAV (β = 60d OLS),
   capped by the margin budget (operator Q2: 20% vs 10%).
3. **Exit:** trigger clear for 2 consecutive sessions → unwind.
4. **Account breaker:** intraday margin excess below broker threshold →
   unwind (see §5).

No hard stop, no profit lock — a hedge losing while the long book gains is
the product working.

### 2.1 Gate G-E6 (replay; PASS required before any implementation)
Three arms under the SAME trigger stream: (a) short-SPY hedge, (b) **cash
de-risk** (reduce gross exposure by the same notional), (c) do-nothing.
- **Windows:** 2022 bear; 2025-04 dip; 2025-10→2026-01 calm window; full
  validation year; **negative control: 2026-06-11** (the false-BEAR day —
  the post-#112 detector must not fire; if replay shows a fire, Phase A is
  blocked on detector work, not hedge tuning).
- **Metrics:** terminal wealth, Sharpe, Sortino, Calmar, MaxDD, upside
  capture, recovery lag, turnover, realized tax drag (hedge gains are
  short-term), margin utilization incl. intraday peaks.
- **PASS:** the hedge arm beats the cash-de-risk arm on risk-adjusted
  terminal wealth (Sortino AND Calmar) in stress windows without losing to
  it in bull windows by more than 1% NAV/yr. "Beats do-nothing on MaxDD"
  alone is NOT a pass.
- **Provenance:** the replay must stamp the strategy/pipeline config
  fingerprints + `subrepos.lock.json` digest used.

### 2.2 Gate G-EXEC (execution contract; blocks implementation, not design)
Current `renquant-execution` normalizes intents to BUY/SELL only and cannot
distinguish open-short from reduce-long nor cover from buy. Before Phase A
ships:
1. Order-intent taxonomy: `SELL_SHORT` / `BUY_TO_COVER` (or signed-intent
   equivalent) end-to-end (broker contract, adapters, audit records).
2. Account capability preflight: margin account, shorting enabled.
3. Order-time shortability validation: Alpaca asset `shortable` /
   `easy_to_borrow` flags checked at submission (Lean ShortableProvider
   pattern), fail-closed.
4. Negative-position persistence: live_state round-trips signed positions
   (mirroring the sell_streaks/protection_breaches pattern).
5. Intraday-margin preflight + broker pre-trade rejection handling (§5).
SPY is expected to be highly liquid/ETB, but item 3 still runs at order
time and fails closed if Alpaca reports otherwise — broker availability and
account restrictions are operational facts, not constants. The contract
work (1/2/4/5) is unavoidable and is Phase A's real cost.

## 3. Phase B — Efficiency extension (110/10). Four mechanisms.
Unchanged from v4: QP owns the sleeve (borrow cost in objective; short leg
≤10% NAV, per-name ≤3%, ETB only); per-name hard stop +15%; earnings veto;
shared account breaker. **Gate G-E8** (with/without-sleeve replay; net IR up,
MaxDD not worse, turnover ≤1.5×) runs only after the long-side WF gate is
green. G-EXEC applies in full (multi-name shortability checks).

## 4. Phase C — Conviction shorts: shelved, undesigned.
Policy only: reopen iff E5 (short-interest dynamics, post-FINRA-backfill)
passes its pre-registered bar; design then. Operator constraints recorded:
max 2 names, very high bar, default NO, no regime precondition.

## 5. Margin framework (replaces stale PDT language)
FINRA Notice 26-10 (effective 2026-06-04) retired the pattern-day-trader
rule; Alpaca now applies an **intraday margin framework**: real-time intraday
margin excess/deficit with broker pre-trade rejections. Consequences:
- No day-trade counting logic anywhere in this design.
- The runner must (a) compute pre-trade margin impact and skip orders the
  broker would reject, (b) poll intraday margin excess while any short is
  open (ride the existing ~12-min rail), (c) treat a broker rejection as a
  hard signal to de-risk, never retry-loop.
- The account breaker (§2 mechanism 4) keys off intraday margin excess, not
  end-of-day maintenance-margin numbers.

## 6. Operator questions (carried)
1. Phase-A instrument: short SPY (recommended) vs long SH?
2. Margin budget for v1: 10% (recommended) or 20% NAV?
3. Short-term-gains tax on hedge covers acceptable?

*Companions: experiment spec (E5/E6/E8 only) and literature review — both
updated to v5 (no stale references).*
