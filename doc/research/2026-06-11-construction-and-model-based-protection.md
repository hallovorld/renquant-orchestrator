# Portfolio construction & model-based position protection — a design study

**Version 2 (rewrite).** Supersedes the withdrawn v1 (#86). This is a research/design RFC, not a change order: every quantitative claim is tagged with its theoretical basis and what must be measured before any live change. It is written against the **real account constraints** the operator specified, which dominate the design at small capital.

**Account & instrument constraints (the binding lens):**
- Capital **$10,000** (not the $100k a prior analysis assumed).
- Margin available **≤ 20%** → gross exposure ≤ **1.2×**.
- Broker **Alpaca**; US equities; **wash-sale §1091** applies; **Pattern-Day-Trader (PDT)** rule applies because equity < $25k.
- Signal: **PatchTST cross-sectional ranker, label `fwd_60d_excess` (60 trading-day horizon), OOS IC ≈ 0.13, 142-name universe.** The **60-day horizon is the single most important number** for everything below.

---

## 1. The governing principle: trade at the signal's speed, not faster

The core question — "are the turnover / rotation / hold settings reasonable?" — is answered by one result.

**Gârleanu & Pedersen (2013), "Dynamic Trading with Predictable Returns and Transaction Costs," *Journal of Finance*.** With predictable returns and quadratic trading costs, the optimal policy is **not** to jump to the Markowitz portfolio each period; it is to trade a **constant fraction of the way toward an "aim" portfolio** every period, where that fraction rises with the signal's **mean-reversion (decay) speed** and falls with **trading cost**. Fast-decaying signals justify fast trading; slow signals do not — trading a slow signal quickly just pays cost to chase noise between signal updates.

Operationalized for our signal:
- A 60-day-horizon signal has an information **half-life on the order of the horizon**, so the *natural* daily turnover is **≈ 1/60 ≈ 1.7%/day** and the natural holding period is ~**60 days**.
- The current settings permit a **~7-day** full-book turnover (`qp_turnover_max = 0.15/day` ⇒ implied holding ≈ 1/0.15 ≈ 6.7 days) and rotate on **any** positive score edge (`rotation_advantage = 0`), i.e. the construction layer is tuned **≈ 9× faster** than the signal.
- This is the *same horizon-mismatch class* as the Kelly σ-bug we just fixed (σ@252 vs μ@60), and it is exactly what Gârleanu–Pedersen warn against. **Net effect: a real (IC 0.13) signal is eroded by transaction-cost, tax, and wash-sale drag.** (Magnitude is an empirical question — see §5.)

Supporting literature: **Almgren & Chriss (2000)** for the cost/turnover frontier; **Novy-Marx & Velikov (2016), "A Taxonomy of Anomalies and Their Trading Costs," *RFS*** and **Frazzini, Israel & Moskowitz (2018), "Trading Costs"** for how quickly turnover eats gross alpha in practice (many published anomalies are not profitable net of realistic costs above modest turnover).

---

## 2. Per-setting analysis

Notation: `N` = `max_concurrent_positions`, `IC` ≈ 0.13, `BR` = breadth.

### 2.1 Concentration `N = 8` — *reasonable at $10k* (this reverses the v1 conclusion)

- **Theory (for more names):** the **Fundamental Law of Active Management** — Grinold (1989), Grinold & Kahn (2000), with the transfer-coefficient extension Clarke–de Silva–Thorley (2002): `IR ≈ IC · √BR · TC`. More independent bets (higher `BR`) raise IR; 8 of 142 names harvests only a slice of breadth and concentrates idiosyncratic risk (~12%/name at the cap ⇒ one −50% name ≈ −6% book).
- **But at $10k the constraint binds the other way (this is the correction to v1, which assumed $100k):**
  - *Lot indivisibility.* With $10k and a 12% cap, each slot ≈ **$1,200**. Spreading to 25 names ⇒ ~**$400/slot**; a $400 share (e.g. CRWD-like) is then 1 indivisible share = 100% of its slot, a $170 share quantizes ±15%, and any **share priced above the slot is unbuyable**. The integer-lot problem (a mixed-integer portfolio program; see e.g. the cardinality-constrained Markowitz literature) makes fine diversification infeasible at small capital with whole shares.
  - *PDT + per-trade frictions* (see §3) make a 25-name book operationally heavier than $10k supports.
  - **Fractional shares (Alpaca supports them) largely dissolve the indivisibility argument** — *if* the execution layer uses notional/fractional orders. **Action item: confirm whether live orders are whole-share or fractional** (paper_broker handles share rounding); the right `N` depends on the answer.
- **Assessment:** at $10k with whole shares, **8 names is a defensible practical concentration**, not under-diversification. If fractional shares are on, **15–20 names** becomes feasible and the FLAM breadth argument applies — worth a backtest. Either way, the previous "use 15–25" recommendation was a $100k artifact and is withdrawn.

### 2.2 `rotation_advantage = 0` — **too low** (highest-priority)

- A zero barrier rotates a holding out whenever a candidate's score is an epsilon higher — i.e. on daily score **noise**. Gârleanu–Pedersen's aim-portfolio logic and a simple cost argument both say a rotation should clear a **hurdle ≈ round-trip cost + the score's own noise**.
- **Proposed hurdle (to validate):** require the candidate's **calibrated μ to beat the holding's by a margin** `Δμ* ≈ 2·(c_roundtrip) + k·σ_score`, where `c_roundtrip` is round-trip cost (spread + commission + half-spread impact; for retail liquid US equities O(5–15 bps)) and `k·σ_score` covers a few σ of daily score noise. Concretely this lands around a **~1–2% expected-return edge** for a 60-day signal — far above 0.

### 2.3 `qp_turnover_max = 0.15/day` — **too loose for a 60-day signal**

- A daily cap permitting a 7-day full turnover is ~9× the signal pace. **Tie it to the horizon:** roughly `turnover_cap ≈ (deployment / target_holding_days)`; for a ~30–60 day target this is **~0.02–0.04/day** in steady state. Caveat: the cap also throttles **initial deployment from cash** (already ~3–4 days at 0.15). A better design separates **build-up** (allow faster initial deployment) from **steady-state churn** (slow), which is exactly the Gârleanu–Pedersen "trade toward aim" shape.

### 2.4 `min_hold_days = 5` — fine as a *floor*; real discipline is the 60-day soft guard

- 5 days is an anti-whipsaw floor, not thesis-respecting. The horizon-aligned control is the soft-exit thesis-age guard `min_holding_days_by_regime: {BULL_CALM: 60}` — which we just found was silently OFF outside BULL_CALM / for seeded positions (pipeline #100). Keep 5 as the floor; **activate the 60-day soft guard's `default`** so a 60-day thesis is actually protected.

### 2.5 Reasonable as-is

- `qp_min_dw_pct = 0.02` (no-trade band): a sensible cost filter (suppresses sub-2% Δw). Keep.
- `top_up_threshold = 0.05`: avoids dribbling top-ups. Keep.
- `min_reentry_days = 5`: anti-churn — **but see §3.3, it is shorter than the 30-day wash-sale window**, which matters at a taxable small account.

---

## 3. Small-account reality: $10k + margin + wash-sale + PDT

These four interact and are *more* binding than any single knob.

### 3.1 Lot indivisibility & an implicit price ceiling
At $10k / 8 slots / 12% cap, a name priced above ~$1,200 can't be held at target with one share; quantization error grows as price/slot rises. **Fractional shares remove this** — confirm execution mode. Otherwise the universe should carry an effective **max-share-price filter** at this capital.

### 3.2 Margin (≤20% → 1.2× gross)
- Current config deploys at most `8 × 12% = 96%` (cash_reserve 0) — **margin is currently unused.** The 20% is available headroom.
- Using it raises gross to 1.2× → ~**+20% to both expected return and volatility/drawdown**, plus **margin interest** (Alpaca charges ~ base + spread; a real carrying cost that must enter the net-return calc). Leverage on a 60-day signal with IC 0.13 is only justified if net-of-interest, net-of-cost expected return clears the hurdle. **Recommendation:** treat margin as a *deliberate* lever (e.g. only when the cross-sectional μ is strongly positive), not a default; model interest as carry in the backtest.

### 3.3 Wash-sale §1091 (the cost the operator flagged)
- Selling at a **loss** and rebuying the same/substantially-identical security **within 30 days** disallows the loss deduction (it is added to the new lot's basis). The book already has `wash_sale_days = 30` and an `is_wash_sale_blocked_with_cost` gate — good.
- **The tension:** `min_reentry_days = 5 < 30`, and `rotation_advantage = 0` drives frequent sells. A high-turnover policy on a taxable account **manufactures wash sales**, deferring/forfeiting the tax value of realized losses. This is a *direct, quantifiable* reinforcement of §1's "slow down" thesis. **Recommendation:** for *loss* exits specifically, lengthen the effective re-entry/avoid window toward 30 days, and have rotation's cost hurdle (§2.2) include the **expected wash-sale tax drag**, not just commissions/spread.

### 3.4 Pattern-Day-Trader rule (the hard one for intraday protection)
- **FINRA PDT:** an account **< $25,000** may place **at most 3 day-trades per rolling 5 business days**. A "day trade" = buy and sell (or sell and buy) the same security the **same day**.
- **Implication for any intraday protection mechanism (§4):** if the mechanism sells intraday and the strategy would re-enter same-day, that's a day trade — **3 per 5 days is a hard ceiling at $10k.** This forces an intraday protection design to be **exit-biased and same-day-reentry-averse** (or to live within a tiny day-trade budget). This is the single biggest constraint the $10k assumption imposes on the operator's "every-12-minutes" idea.

---

## 4. Model-based position protection (replacing the naive stop-loss)

The operator's directive: holdings need a protection mechanism; a simple stop-loss is unreliable, but there must be **at least a model-based** one — e.g. *"every ~12 minutes, re-evaluate the holding with the model on the latest price; after the threshold is breached 3 times, sell."* Below is a professional formalization, its theoretical basis, and the caveats that decide whether it is sound.

### 4.1 Why price-only stops fail (and our own evidence)
A stop-loss conditions on **price alone**, with no view on whether the **thesis** still holds. It therefore sells winners on noise (our live evidence: NVTS exited via `single_day_loss` at **+113%**; `single_day_loss` exits averaged **+9% pnl**) and sells losers at local bottoms (ORCL). The fix is to condition the exit on the **model's current view of the name**, not on price moves per se. This is the **meta-labeling / triple-barrier** idea of **López de Prado (2018), *Advances in Financial Machine Learning*, ch. 3 & ch. 20** — a second-stage model decides whether an open bet is still favorable. We already have `MetaLabelVetoTask` (AFML ch. 20) wired, so the infrastructure exists.

### 4.2 Proposed design — thesis re-valuation + sequential N-strikes exit

**(a) Re-score on the latest price, *in-distribution*.** The production model is trained on **daily** bars for a **60-day** horizon; **feeding it raw 12-minute bars is out-of-distribution and statistically unsound** (its features and calibrator were never fit on intraday data). The correct trick: form a **provisional daily bar** = today's OHLC-so-far with `close = latest price`, recompute the **price-dependent alpha158 features** (momentum, distance-from-MA, vol, etc.) on that provisional bar, and re-run the existing daily model + calibrator to get an **updated μ / rank / P** for each holding. This keeps the model in its training distribution; only the as-of close is provisional.

**(b) Breach definition.** A *breach* = the holding's **updated calibrated μ falls below an exit threshold** `τ` (candidates: `μ < 0`, i.e. below the calibrator's neutral; or `μ` below a regime floor; or the name's **rank falls out of the top-`M`**). Conditioning on μ (not price) means: a price drop that the model still likes (μ stays > 0) is treated as *opportunity, not danger* — the opposite of a stop-loss.

**(c) Sequential debouncing — the "3 strikes."** Acting on a single noisy intraday reading is a false-positive machine. Require **N consecutive breaches** before exit. This is a **sequential hypothesis test**: it trades detection latency for far fewer false exits, formalized by **Page (1954), "Continuous Inspection Schemes" (CUSUM)** and **Wald (1945), SPRT**. `N = 3` is a reasonable starting point; `N` and `τ` jointly set the **false-exit vs missed-break** operating point (a Neyman–Pearson / ROC tradeoff to calibrate from data, §5).

**(d) Cadence — prefer event-driven over a fixed 12 minutes.** Re-evaluate when **new information arrives**, i.e. on a price move exceeding `k·σ_intraday` (or at a few fixed intraday checkpoints), rather than every 12 minutes regardless. This concentrates compute and decisions on informative moves and reduces noise sampling. (Fixed 12-min is acceptable as a v0; event-driven is the better v1.)

**(e) The PDT governor (mandatory at $10k).** Per §3.4, an intraday exit that the book would re-enter same-day is a day trade, capped at **3 / 5 days**. So at $10k the mechanism must be **exit-biased** (protection only) and **same-day-reentry-blocked**, or run on an explicit small day-trade budget. A cleaner alternative at this capital: run the re-valuation intraday but **execute the exit at/near the close** (end-of-day), capturing most of the protection while sidestepping PDT and intraday noise. **This is the recommended default at $10k.**

**(f) Loss-exit wash-sale governor.** If an exit realizes a loss, suppress re-entry for the wash-sale window (§3.3) or carry the disallowed-loss cost into the decision.

### 4.3 What this is, in one line
A **meta-labeling exit**: keep a position while the model's *calibrated expected return for it remains positive*; exit when the thesis flips negative on a **noise-robust (N-of-M)** basis — executed in a way that respects PDT and wash-sale at $10k.

### 4.4 Honest risks / open questions for this mechanism
1. **OOD validity:** does the provisional-bar re-score produce a *meaningful* intraday μ for a 60-day daily model? Must be validated (compare provisional-bar μ at 15:55 to next-day's actual μ).
2. **PDT feasibility:** at $10k the intraday-execution variant is largely infeasible; the end-of-day-execution variant is the realistic one. Confirm the operator wants protection *speed* (intraday, PDT-limited) vs protection *coverage* (daily, unlimited).
3. **Does it beat the alternatives on NET Sharpe/drawdown?** vs (i) no exit, (ii) the existing path-stops, (iii) the H-2 "SDL-defers-to-trailing" fix already shipped.

---

## 5. Validation protocol (nothing live without this)

1. **Cost/tax-aware backtest** on the WF replay manifold: measure **net** (post commission+spread+impact, post tax, **post wash-sale**) Sharpe / IR and **realized turnover** under current vs proposed settings. Confirm the §1 hypothesis (realized churn ≫ 60-day pace) directly.
2. **Per-change A/B** (isolate then combine) through the step-4g harness so each earns a promotion verdict, not a hand-wave — same gate discipline as the allocator work (note the manifold's known constraint-fidelity gaps; a turnover/cost study is more robust to those than an allocator promotion).
3. **Protection-mechanism A/B:** thesis-aware exit vs no-exit vs path-stops, on net Sharpe **and** max drawdown **and** PDT-trade-count feasibility at $10k.
4. **Small-account realism in the sim:** integer/fractional lots per the live execution mode, margin interest as carry, PDT counter, wash-sale tax accounting. A backtest that assumes infinite divisibility and ignores PDT/wash-sale will overstate every result at $10k.

---

## 6. Literature & open-source to read (map, with why)

**Papers**
- Gârleanu & Pedersen (2013), *Dynamic Trading with Predictable Returns and Transaction Costs* — the optimal trade-toward-aim rate; the spine of §1.
- Grinold (1989) & Grinold–Kahn (2000), *Active Portfolio Management*; Clarke–de Silva–Thorley (2002) — FLAM / breadth / transfer coefficient (§2.1).
- Almgren & Chriss (2000) — execution cost/turnover frontier.
- Novy-Marx & Velikov (2016); Frazzini–Israel–Moskowitz (2018) — anomaly returns net of real trading costs.
- López de Prado (2018), *Advances in Financial Machine Learning* — triple-barrier, meta-labeling, bet sizing (§4).
- Page (1954) CUSUM; Wald (1945) SPRT — the N-strikes sequential test (§4c).
- Kelly (1956); MacLean–Thorp–Ziemba (2011), *The Kelly Capital Growth Investment Criterion* — sizing context for the existing half-Kelly.
- Jegadeesh–Titman (1993, 2001) — momentum horizon structure (our signal is net-momentum, ρ≈+0.19; relevant to holding period).

**Open-source / practice**
- **Qlib** (Microsoft) — origin of the alpha158 features; study its **online serving / rolling-retrain** for the re-score loop.
- **mlfinlab** (Hudson & Thames) — reference implementations of triple-barrier & meta-labeling for §4.
- **vectorbt** / **backtrader** / **zipline-reloaded** — fast intraday-exit backtesting to prototype §4 + the cost/PDT/wash-sale accounting of §5.
- Alpaca docs — fractional-share / notional orders (§2.1, §3.1) and PDT handling (§3.4).

---

## 7. Recommendations & open questions

| item | current | proposed (to validate) | basis | priority |
|---|---|---|---|---|
| `rotation_advantage` | 0 | μ-edge hurdle ≈ round-trip cost + k·σ_score (~1–2% ER) | Gârleanu–Pedersen, Almgren–Chriss | **HIGH** |
| `qp_turnover_max` (BULL_CALM) | 0.15/day | ~0.02–0.04/day steady-state; faster build-up | Gârleanu–Pedersen | **HIGH** |
| position protection | path stops only | thesis-aware meta-label exit, N-of-M, EOD-exec at $10k | de Prado, Page/Wald | **HIGH** |
| `N` (concentration) | 8 | confirm fractional vs whole-share; 8 OK whole-share, 15–20 if fractional | FLAM vs lot indivisibility | MED |
| `min_hold` + 60d soft guard | 5 / silently-off | 5 floor + activate 60d `default` | horizon alignment | MED (guard fixed #100) |
| margin use | unused (96%) | deliberate lever, interest as carry | leverage cost/benefit | MED |
| `min_reentry_days` (loss exits) | 5 | → ~30 for loss positions | §1091 wash-sale | MED |
| no-trade band / top-up | 0.02 / 0.05 | keep | — | — |

**Open questions for the operator:**
1. **Whole-share or fractional execution live?** Decides `N` and the §3.1 price ceiling.
2. **Protection: intraday-fast (PDT-limited to 3/5d) or daily-coverage (EOD-exec)?** At $10k I recommend EOD-exec.
3. **Trade the 60-day signal *as* 60-day (low turnover) or as a faster momentum proxy (higher turnover, accept costs)?** The label says the former; the current settings imply the latter.
4. Appetite for margin (1.2×) given the interest carry and amplified drawdown?

**Bottom line:** the *anti-churn* guards are fine. The *turnover-enabling* settings (`rotation_advantage=0`, `qp_turnover_max=0.15`) are mis-aligned with the 60-day signal and, at a **taxable $10k account with PDT and wash-sale**, that misalignment is more expensive than at $100k. The protection mechanism the operator wants is sound **if** built as a thesis-aware (not price-only) meta-label exit with sequential debouncing and a PDT/wash-sale governor — and **only** after the cost/tax-aware validation in §5.

Agent-Origin: Claude
