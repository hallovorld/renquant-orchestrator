# Design: renquant105 — intraday trading system

2026-06-27. Status: **PROPOSAL for review** (no code). Grounded in 5 parallel
read-only research sweeps (regulatory/cost, 104→105 delta, intraday data/latency,
intraday model/GPU, stricter gating). For Codex discussion before any build.

## 0. Honest feasibility verdict (read first)
- **Regulation is no longer the blocker.** The FINRA $25k / "3 day-trades per 5
  days" PDT rule was eliminated **effective 2026-06-04** (SEC approved 2026-04-14,
  FINRA Notice 26-10); Alpaca implemented it. **Verified on the live account**:
  `pattern_day_trader=False`, `daytrade_count=0` (uncapped), 4× intraday buying
  power `$37,763`. Intraday day-trading is operationally clear at ~$10.6k.
- **The binding constraint is ECONOMICS, and the quantitative analysis says
  intraday-alpha trading is likely NOT VIABLE at this size on this data (§A).**
  Hard numbers: round-trip cost ≈ **11 bps** (7–17 bps; spread+slippage+IEX
  adverse-selection) vs the expected edge of a top-ranked name on a single 5-min
  bar ≈ **~1 bp** even at IC 0.05 — **underwater ~10×**. Clearing cost needs the
  hold stretched to **~2.5 days** (no longer intraday). Via the Fundamental Law,
  the cost drag (Sharpe −5 to −7 at 6 rebalances/day) **exceeds** the transferred
  gross IR — **honest net-of-cost Sharpe band ≈ −2.0 to +0.5, centered NEGATIVE**.
  The 104 daily book's own realized WF Sharpe is already sub-1; intraday strictly
  worsens the cost side with no demonstrated IC uplift.
- **So renquant105 is NOT a churn machine, and likely NOT a new-intraday-alpha
  machine either.** What survives the math: (a) a **measurement-grade, cost-charged
  SHADOW HARNESS** that *empirically tests* whether any intraday alpha clears cost
  (no real money) — the only scientifically honest first step; (b) intraday
  **execution-TIMING** to get better fills on the daily-104 book's *existing*
  trades (reduces cost, adds **no** round-trips); (c) intraday **risk management**
  (the existing sell-only exits on intraday signal decay). None of (b)/(c) needs an
  intraday alpha model to clear the cost hurdle.
- **GO/NO-GO is quantitative and the prior is NO-GO (§A.4).** Live intraday alpha
  capital is justified ONLY if a Phase-1 shadow run *empirically* delivers
  placebo-clean OOS IC ≥ **0.03** AND net-of-cost Sharpe ≥ **1.0** over ≥ **40–80
  clean dates** with Deflated-Sharpe > 0 — improbable given the ½-OOS-IC-decay prior
  + the leakage floor. **Default outcome = intraday alpha trading stays OFF.**
- **HARD DEFAULT (operator mandate): live intraday TRADING IS DISABLED at the
  start.** `intraday_buys_enabled=false` (and intraday live orders off) is the
  fail-closed default. Phases 0–2 place **zero live intraday orders** — they only
  build data, train, and run **shadow / observe-only**. Live intraday is **Phase 3
  only**, behind the validation gate + an armed kill-switch. The system must
  fail-closed to no-intraday-trading on any missing gate, stale data, or unproven
  edge — turning it on is a deliberate, gated act, never the default.

> **Suite index (this spec = the master; the full professional set):**
> - `…-intraday-system.md` — master spec + quantitative feasibility (§A)
> - `…-reliability-fmea-failsafe.md` — 43-row FMEA, fail-safe spec, SLOs
> - `…-performance.md` — latency / compute / storage budgets
> - `…-metrics-suite.md` — alpha/risk/cost/model-health metrics, per-phase acceptance, 每日复盘
> - `…-oss-champion-challenger-validation.md` — OSS leverage, shadow-model pattern, validation discipline
> - `…-M0-data-foundation.md` / `-M1-model-validation.md` / `-M2-gates-shadow.md` /
>   `-M3-live-monitored.md` — per-milestone detailed designs (requirements, metrics,
>   numeric acceptance, expected outcomes + kill conditions)

## A. Quantitative feasibility analysis (the make-or-break)
Account ~$10.6k, 4× intraday BP $37.7k; liquid >$6 large-caps; IEX data; 1–5 min bars.

**A.1 Round-trip cost.** `RT = 2·(half_spread + slippage + IEX_adverse_selection) +
impact`. Per-leg liquid large-cap on IEX = 3.5–9 bps; impact negligible (A.3).

| Scenario | per-leg | RT cost |
|---|---|---|
| Optimistic (mega-cap, tight) | 3.5 bps | **7 bps** |
| Base (liquid large-cap, IEX) | 5–6 bps | **~11 bps** |
| Conservative (IEX staleness) | 8–9 bps | **~17 bps** |

**A.2 Edge of the top pick vs cost.** `E[edge_top] = IC·σ_xs·factor`; for a top-decile
pick `factor≈1.75`, single-5-min-bar cross-sectional dispersion `σ_xs≈25 bps`:

| IC (OOS) | gross edge top-decile | − RT 11 bps | net | clears 1.75×cost (19 bps)? |
|---|---|---|---|---|
| 0.01 | 0.44 bps | −11 | −10.6 | NO |
| 0.02 | 0.88 bps | −11 | −10.1 | NO |
| 0.03 | 1.31 bps | −11 | −9.7 | NO |
| 0.05 | 2.19 bps | −11 | −8.8 | NO |

→ single-bar edge ≈1 bp, RT cost ≈11 bps — **underwater ~10×** at any plausible IC.
Clearing cost needs cumulative dispersion ~3.6% → **~2.5-day hold** (not intraday).

**A.3 Capacity / impact.** Square-root law `I=Y·σ·√(Q/ADV)`, Y≈1: at $1k–7.5k notional
vs $300M–$40B ADV → impact **<1 bp** — a non-constraint. But it can't rescue
economics: the binding cost is the **size-independent** spread/IEX floor.

**A.4 Net Sharpe (Fundamental Law) + GO/NO-GO.** OOS IC = ½ in-sample, minus the
leakage floor → honest band **0.01–0.03**; transfer coeff ≈0.5. At 6 rebal/day the
**cost drag ≈ Sharpe −5 to −7 exceeds the transferred gross IR (≈4–6)** → **net
Sharpe band ≈ −2.0 to +0.5, centered negative.** A live-capital GO requires Phase-1
to clear ALL of: net-of-cost Sharpe ≥ **1.0**; placebo-clean OOS IC ≥ **0.03** (above
the shuffled-label floor); hit-rate ≥ **54%** on the cost-clearing subset; max-DD ≤
**12%**; net-PnL block-bootstrap 95% CI lower bound **> 0**; **Deflated Sharpe > 0**
at the true trial count — over ≥ **40–80 clean dates** (overlapping intraday labels
deflate N_eff to ~3–6 independent bets/day). **Prior = NO-GO; default = intraday
alpha OFF.** (Full tables + sources in the feasibility research transcript.)

## 1. We are NOT starting from zero (the big de-risk)
The intraday subsystem is **already built and parked** (disabled 2026-05-04), not
greenfield:
- Alpaca-IEX intraday fetch (1Min–1Hour), `Hourly/MinuteBarStore` caches (~192
  symbols, now stale), `hourly_features.py`/`minute_features.py` (written +
  unit-tested), `training_resolution: daily|hourly` switch, per-(date,hour) z-score.
- The websocket consumer `live/stream_watchdog.py` (real `StockDataStream`, dark,
  behind a 5-clean-sessions gate), `IntradayGovernor` (cooldown/session-cap, off).
- The model harness is **config-swappable** (a sequence model drops in via
  `kind`+`artifact_path`, `requires_history` auto-routes); GBDT + PatchTSMixer both
  reusable.
- The full fail-closed **gate stack** (conviction, QP, WF-gate, regime, vol,
  meta-label-veto-on-exits, `AgentBreaker`, `GateRegistry`) is reusable.
- The 12-min intraday-sell cron is the literal scheduling seed.
105 = **re-activation + an intraday model + tighter gates + a buy path**, mostly
config/wiring, not new plumbing.

## 2. Data (要不要改: yes — re-enable, incremental, liquid universe)
- **Feed.** Alpaca **free = real-time but IEX-only** (~2–3% of volume, off-NBBO —
  the "15-min delay" myth only applies to SIP-over-REST). Free is **sufficient for
  TRAINING** (full 2016→ minute history). Live execution wanting NBBO-accurate
  fills → **$99/mo SIP (Algo Trader Plus)** — a decision, not a prerequisite.
- **Coverage gap (the real blocker).** ~50% of the 145-name daily universe lacks
  intraday history (the documented reason it was disabled). 105 needs a **liquid,
  coverage-gated universe** (~40–60 names with full intraday history), not 145.
- **Incremental ingestion.** The daily panel is a full from-scratch rebuild;
  intraday (~100× volume) requires **append-only** per-symbol/day ingestion (extend
  the `*Store` classes; touch all 3 triplicated copies: pipeline / base-data /
  umbrella).
- **No L2 depth** (top-of-book only) → only crude OFI proxies (signed/imbalance
  volume). Don't design around order-book microstructure we can't see.
- **Latency is NOT the bottleneck.** A few seconds end-to-end on 1–5 min bars is
  fine; no HFT/sub-second engineering. The "speed" work that matters is incremental
  ingestion + a fresh cache, not the wire.

## 3. Model (要不要改: reuse + intraday label; NO GPU)
- **Reuse, don't rebuild.** Primary = **GBDT on intraday technical/imbalance
  features** (matches the daily primary, literature workhorse at 5-min, trains in
  seconds). Shadow = the existing **PatchTSMixer cross-sectional ranker** on
  intraday bar sequences (`seq_len`/feature/label change only). Deep LOB models are
  **out of scope** (no depth data).
- **Label.** Triple-barrier (López de Prado): σ-scaled profit/stop barriers + a time
  barrier = the max hold; horizons **30min / 2hr / open→close** (NOT sub-5min —
  microstructure noise). Tie the horizon to the **cost hurdle**: expected edge must
  be ≥ ~2× round-trip cost or it's untradeable.
- **GPU verdict: NO.** Models stay small (≤ low-millions of params), universe is
  small; CPU/MPS nightly batch is minutes even at ~80–100× bars. GPU only pays off
  for deep LOB on full depth + large universe — impossible here. Rent cloud GPU if
  that ever changes; **don't buy hardware**.
- **Training cadence:** nightly batch (matches 104 discipline); optional incremental
  fine-tuning later, never bypassing the gates.
- **Anti-overfit is MANDATORY (intraday overfits easily) — and we own the tooling**
  (`renquant-common` purged WF + `PurgedKFold` + `CombinatorialPurgedCV`). The
  critical change: **resize the embargo to the intraday label horizon IN BARS** (not
  60 days), **purge the overnight gap**, report **CPCV distribution + PBO + Deflated
  Sharpe**, keep the **placebo** (shuffled-label/time-shift) gates, and judge
  **net-of-cost**, never gross. The biggest single edge lever is a **SIP feed**, not
  the model or a GPU.

## 4. Logic (要不要改: yes — a stricter, conjunctive, fail-closed gate stack)
Default action = **DON'T TRADE**; a trade fires only if **ALL** gates pass; any
missing/stale input ⇒ reject. (`FIRE ⟺ G1∧…∧G8`)
- **G1 cost-edge:** `net_alpha = ER − round_trip_cost > k·round_trip_cost` (k≈1.5–2),
  using **live intraday spread**, not a daily constant.
- **G2 confidence:** conformal **lower bound** of ER > cost hurdle — using **ACI /
  block-conformal** (intraday is non-exchangeable; vanilla conformal's coverage
  collapses in high-vol), replacing the bare `mu>0` floor.
- **G3 entry meta-label:** `P(trade_profitable | primary signal) ≥ τ` (≥0.5, raise
  toward 0.6+). **Highest-leverage new gate** — symmetric to the existing
  exit-veto; reuses the triple-barrier infra.
- **G4 regime:** `regime ∉ {BEAR, BULL_VOLATILE, CHOPPY}` AND confidence ≥ floor —
  add a **CHOPPY → no-trade** gate (ADX>20 / ATR% filter): the single best filter
  against intraday whipsaw.
- **G5 vol/data:** realized-vol < cap AND spread < cap AND **data fresh** (hard
  intraday staleness cutoff → no-trade).
- **G6 risk budget:** QP optimal (lower turnover + per-name caps intraday) AND the
  **P&L max-loss-per-day circuit breaker** not tripped (a **genuine gap** today —
  `AgentBreaker` only caps order-count/notional).
- **G7 quota:** intraday-margin budget available AND ranks **top-k by net_alpha/risk**
  (knapsack under scarcity — spend trades on the best setups).
- **G8 kill-switch:** `TRADING_OFF` absent AND `AgentBreaker.admit()` passes; +
  max-deviation slippage reject at order emission.

**Load-bearing caveat:** the cascade's precision gain assumes **independent** gates.
G1–G3 partly derive from related model internals, so (a) keep gates from *different
information sources* (model score vs microstructure cost vs realized-vol vs regime vs
broker-margin), (b) **verify with the placebo machinery** that the conjunction raises
*realized* precision rather than just shrinking coverage, (c) keep every suppressed
trade observable via the `GateRegistry` decision ledger and audit for killed winners
(the BULL_CALM panel-exit mis-fire, orch #195, is the cautionary precedent).

## 5. Trade count (会提高很多吧?)
Regulation now permits unlimited day-trades (verified). **Economics caps it**: each
round-trip must clear ~10–15 bps. So expect a **modest** rise in turnover (more
intraday entries/exits than the current ~weekly cadence), **not** 10× churn — and
only trades that clear the net-of-cost bar. "Permitted" ≠ "profitable".

## 6. Deploy (alongside 104, shadow-first)
New `renquant-strategy-105` subrepo (pinned) + `backtesting/renquant_105/`
(config/state/artifacts) + `scripts/intraday_105.sh` (buy+sell intraday) +
`com.renquant.*105.plist`. The bridge routes by `--strategy` → **no orchestrator
code change**. 104 keeps running unchanged. 105 runs **shadow (readonly-alpaca, no
orders)** until validated, then graduates. Repo boundaries: model→`renquant-model`,
decision/exits→`renquant-pipeline` kernel, config→`renquant-strategy-105`,
wiring/pins/bundles→orchestrator.

## 7. Phased rollout (validation-gated, with a kill condition)
- **Phase 0 — Data:** liquid coverage-gated universe; re-enable intraday cache +
  `hourly/minute` features; incremental ingestion + a refresh cron; build the
  intraday feature panel. (No model yet.)
- **Phase 1 — Model + the make-or-break gate:** train GBDT primary + PatchTST
  shadow on intraday triple-barrier labels; validate via **CPCV + PBO + DSR +
  placebo, net-of-cost**. **GATE:** net-of-cost Sharpe clears a pre-registered bar
  with placebo-clean evidence. **KILL CONDITION:** if intraday edge does not survive
  costs, **STOP** (the honest outcome may be "no tradable intraday edge at this
  size/data").
- **Phase 2 — Gates + shadow e2e:** build G1–G8 (entry meta-label, P&L breaker,
  conformal lower-bound, CHOPPY gate, cost hurdle, slippage/stale rejects); shadow-run
  105 end-to-end on live intraday data; confirm the conjunction raises realized
  precision (placebo) and doesn't kill winners (ledger audit).
- **Phase 3 — Live, tiny, monitored:** graduate with minimal size + the daily-loss
  breaker armed; decide the **$99 SIP** here (NBBO fills); scale only if net-of-cost
  edge holds live.

## 8. Decisions I need (let's discuss)
1. **Universe:** a liquid, coverage-gated **~40–60 names** (vs 145 daily)? Which
   selection rule (ADV / intraday-history completeness)?
2. **Label horizon:** 30min / 2hr / open→close — pick one (this anchors the whole
   design). Recommend starting at **open→close or 2hr** (cleaner signal, fewer
   round-trips, lower cost hurdle).
3. **SIP feed ($99/mo):** build+train on free IEX, decide SIP at Phase 3 (live)?
   (Recommended — training is free regardless.)
4. **Net-of-cost edge bar (k):** k≈1.5–2× round-trip cost as the admission hurdle?
5. **Scope:** single intraday horizon only (multi-horizon sleeves were rejected
   before — keep 105 single-horizon)?
6. **Kill condition:** agree that if Phase-1 net-of-cost edge is not placebo-clean,
   we STOP rather than ship a cost-negative intraday book?

Sources for the regulatory + cost + literature claims are catalogued in the
research transcripts; key ones: FINRA Notice 26-10 (PDT elimination), Bollerslev
et al. *J. Financial Econometrics* 2023 (intraday ML), López de Prado *AFML* 2018
(triple-barrier + meta-labeling), Angelopoulos & Bates 2021 + Gibbs & Candès 2021
(conformal / ACI), arXiv 1005.3535 (intraday cross-section net-negative after spread).
