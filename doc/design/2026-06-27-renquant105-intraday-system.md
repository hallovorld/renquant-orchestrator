# Design: renquant105 — intraday trading system

2026-06-27. Status: **PROPOSAL for review** (no code). Grounded in 5 parallel
read-only research sweeps (regulatory/cost, 104→105 delta, intraday data/latency,
intraday model/GPU, stricter gating). For Codex discussion before any build.

## 0. Honest feasibility verdict (read first)
- **Regulation is no longer the headline blocker, but the account is NOT yet
  "operationally clear" (finding 8).** The FINRA $25k / "3 day-trades per 5 days" PDT
  rule was replaced **effective 2026-06-04** (SEC order 34-105226; FINRA Notice 26-10 +
  new intraday-margin guidance; Alpaca's June-4 migration). The new regime replaces PDT
  with **real-time intraday-margin deficits + broker pre-trade checks**, and FINRA permits
  a firm transition period. **Verified on the live account**: `pattern_day_trader=False`,
  `daytrade_count=0`, 4× intraday BP `$37,763` — but those flags (Alpaca is **deprecating**
  the old PDT/day-trade fields) do **NOT** prove all 105 order sequences are admissible.
  The real check is encoded in the **M0.5 broker-contract milestone** (current
  `buying_power`/intraday-margin fields, rejection + deficit handling tested in
  paper/shadow, leverage caps independent of the broker max, fail-closed on field
  migration). Until M0.5 passes, "operationally clear" is not claimed.
- **The binding constraint is ECONOMICS, and the quantitative analysis says
  intraday-alpha trading is likely NOT VIABLE at this size on this data (§A) —
  demonstrated by the committed, runnable `scripts/research_intraday_feasibility.py`,
  not asserted.** Hard numbers (every one derived by the script with units): round-trip
  cost ≈ **11 bps** (placeholder, band 7–17, to be replaced by a *measured* cost
  distribution at M1) vs the expected edge of a top-ranked name over a single
  open→close horizon ≈ **~1 bp** even at IC 0.05 — **underwater ~10×**. Clearing the
  admission hurdle at the honest-band IC needs a **multi-day hold** (e.g. the IC=0.03,
  k=1.75 cell = 3.67% cumulative dispersion / **2.76 days** under the explicit
  `σ_cum(h)=σ_xs·√h` random-walk model — no longer intraday). Via the Fundamental Law,
  at the **primary open→close horizon** the cost drag (Sharpe ≈ −1.46 at 1 round-trip/day;
  −8.73 at the rejected 6-rebalance churn) **exceeds** the transferred gross IR
  (0.16–0.48) → **honest net-of-cost Sharpe band ≈ −1.3 to −0.7, centered NEGATIVE**.
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
  capital is justified ONLY if a Phase-1 run *empirically* delivers placebo-clean
  OOS IC ≥ **0.03** at the open→close horizon AND net-of-cost Sharpe ≥ **1.0** AND a
  **probabilistic PSR/DSR ≥ 0.95** (Deflated Sharpe per Bailey & López de Prado, fed
  the full trial universe — §3 / finding 3), over a **power/MinTRL-derived minimum
  aged sample sized in effective-independent observations** (not a raw date count) —
  improbable given the ½-OOS-IC-decay prior + the leakage floor. **Default outcome =
  intraday alpha trading stays OFF.**
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
**Primary horizon = open→close (intraday-only)** — the single horizon the whole suite
is standardized on (§3 + M1); every number below is at that horizon.

**This section is REPRODUCIBLE, not asserted.** Every number is derived from explicit
formulas with units by the committed, read-only, runnable artifact
`scripts/research_intraday_feasibility.py` (no network, no DB, no model — a transparent
cost-vs-edge accounting identity). Reproduce:

```
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/research_intraday_feasibility.py
```

The script prints the tables below and the verdict, sweeps a sensitivity grid, and
exposes a block-bootstrap CI for use once a **measured** cost/dispersion sample is
committed (M0/M1). Until then every input is an **ASSUMPTION** (band noted), NOT a
measurement — the verdict is a demonstrated *hypothesis*, and the script is built so it
flips to GO if (and only if) the inputs justify it (a unit test proves both branches).
The committed `11 bps` is a **placeholder** to be replaced by the M1 measured
arrival/quote/fill distribution (finding 5); the conclusion must survive that swap.

**A.1 Round-trip cost** (`round_trip_cost_bps`). `RT = 2·(half_spread + slippage +
IEX_adverse_selection) + impact`. Per-leg liquid large-cap on IEX = 3.5–9 bps; impact
negligible (A.3). Committed base placeholder = **11 bps** (band 7–17).

| Scenario | per-leg | RT cost |
|---|---|---|
| Optimistic (mega-cap, tight) | 3.5 bps | **7 bps** |
| Base (liquid large-cap, IEX) | 5.5 bps | **~11 bps** |
| Conservative (IEX staleness) | 8.5 bps | **~17 bps** |

**A.2 Edge of the top pick vs cost** (`expected_top_edge_bps`). `E[edge_top] =
IC·σ_xs·factor`; top-bucket `factor≈1.75` (= E[Z | Z>1.28] for a top-decile truncated
standard normal), single-open→close-horizon cross-sectional dispersion `σ_xs≈25 bps`:

| IC (OOS) | gross edge top-decile | − RT 11 bps | net | clears 1.75×cost? |
|---|---|---|---|---|
| 0.01 | 0.44 bps | −11 | −10.56 | NO |
| 0.02 | 0.88 bps | −11 | −10.12 | NO |
| 0.03 | 1.31 bps | −11 | −9.69 | NO |
| 0.05 | 2.19 bps | −11 | −8.81 | NO |

→ single-horizon edge ≈1 bp, RT cost ≈11 bps — **underwater ~10×** at any plausible IC.

**A.2b Cost-clearing horizon (the corrected arithmetic)** (`cost_clearing_horizon_bars`).
Codex correctly flagged the old "~3.6%/2.5-day" as under-derived: `11/(0.05·1.75) =
125.7 bps` is the **required cumulative dispersion** to break even at IC 0.05, not 3.6%.
The horizon is derived from an **explicit scaling model with its independence assumption
made explicit**: assume per-bar signed return increments are serially **uncorrelated**,
so cumulative cross-sectional dispersion grows like a random walk `σ_cum(h)=σ_xs·√h`;
hold the rank-IC of the cumulative-h label roughly constant (conservative — IC usually
*decays* with horizon, lengthening the hold). Break-even (k=1) / hurdle (k=1.75):
`ic·factor·σ_xs·√h ≥ k·RT ⇒ h ≥ [k·RT/(ic·factor·σ_xs)]²`.

| IC | k | req. cumulative dispersion | horizon (bars) | horizon (days, 78 bars/sess) |
|---|---|---|---|---|
| 0.03 | 1.0 | 209.5 bps | 70.2 | 0.90 |
| 0.03 | 1.75 | **366.7 bps (≈3.67%)** | 215.1 | **2.76** |
| 0.05 | 1.0 | 125.7 bps | 25.3 | 0.32 |
| 0.05 | 1.75 | 220.0 bps | 77.4 | 0.99 |

The old "~3.6% / ~2.5-day" is precisely the **IC=0.03, k=1.75 cell** (3.67% cumulative
dispersion, 2.76 days) — now cleanly derived. A single open→close horizon is **1 session
= 78 bars = 1.0 day**; clearing the admission hurdle at the honest-band IC requires a
**multi-day hold — i.e. it is no longer intraday.**

**A.3 Capacity / impact** (`square_root_impact_bps`). Square-root law `I=Y·σ·√(Q/ADV)`,
Y≈1: at $1k–7.5k notional vs $300M–$40B ADV → impact **<1 bp** (script: 0.32 bps at
$5k/$2B/2%) — a non-constraint. The binding cost is the **size-independent** spread/IEX
floor, which capacity cannot rescue.

**A.4 Net Sharpe (Fundamental Law) + GO/NO-GO** (`fundamental_law_gross_ir` +
`cost_drag_sharpe`). OOS IC = ½ in-sample minus the leakage floor → honest band
**0.01–0.03**; transfer coeff ≈0.5; **effective** breadth = 4 *independent* bets/day ×
252 = 1008/yr (NOT names×rebalances — overlapping labels + same-time-of-day
autocorrelation deflate N_eff to ~3–6/day). Transferred gross IR (TC·IC·√breadth) =
**0.16–0.48** over the band. Cost drag (annualized) = `−(RT·rebal·turnover/1e4)/vol·√252`:

| cost regime | rebalances/day | cost drag (Sharpe) |
|---|---|---|
| **PRIMARY open→close** | 1 | **−1.46** |
| rejected intra-session churn | 6 | −8.73 |

→ at the **primary open→close horizon** the **net-Sharpe band ≈ −1.3 to −0.7, centered
NEGATIVE** (the intra-session churn variant's drag alone is catastrophic, which is why
105 is single-horizon, §3 / finding 2). A live-capital GO requires M1 to clear ALL of
the pre-registered bar in M1/§3 (placebo-clean OOS IC, net Sharpe ≥1.0, **PSR/DSR
probability ≥0.95**, PBO <20%, net-PnL block-bootstrap 95% CI lower bound >0) over a
**power/MinTRL-derived minimum aged sample** (finding 3) on **measured** cost+dispersion
(finding 5). **Prior = NO-GO; default = intraday alpha OFF.**

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
- **Feed + cost provenance (finding 5 — fingerprint, don't conflate).** Alpaca **free =
  real-time but IEX-only** (~2–3% of volume, off-NBBO — the "15-min delay" myth only
  applies to SIP-over-REST). Free *may* be sufficient for TRAINING, but **the historical
  training bars must be proven to share the live scoring path's IEX-only microstructure**
  before that claim holds. M0/M1 therefore **fingerprint per dataset**: feed (IEX vs SIP),
  subscription tier, venue coverage, adjustment basis (split/div), bar-construction rule
  (consolidation, mid vs last), and retrieval timestamp — stored in the dataset manifest.
  The cost model is **calibrated from MEASURED arrival/quote/fill data** (by ticker ×
  time-of-day × order type), **not a fixed 11 bps** (the 11 bps in §A is an explicit
  placeholder the M1 measurement must replace). If live execution later wants NBBO-accurate
  fills via **$99/mo SIP (Algo Trader Plus)**, that **switches the observation/execution
  distribution** and is treated as a **fresh experiment**: SIP must pass parity + a
  re-measured cost gate **in shadow before any live use** (see M3 / finding 5), never
  swapped in post-validation.
- **Coverage gap (the real blocker).** ~50% of the 145-name daily universe lacks
  intraday history (the documented reason it was disabled). 105 needs a **liquid,
  point-in-time, coverage-gated universe** (~40–60 names), constructed only from
  information available at each decision date (M0 / finding 4) — never "names that have
  complete history over the whole window" (that is look-ahead/survivorship).
- **Incremental ingestion (pinned-subrepo ownership, NOT triplication — finding 6).** The
  daily panel is a full from-scratch rebuild; intraday (~100× volume) requires
  **append-only** per-symbol/day ingestion. The new primitive is **owned by
  `renquant-base-data`** (the canonical data layer); `renquant-pipeline` consumes it via
  the canonical contract; the umbrella only **pins + wires**. We do **NOT** "touch all 3
  copies" — that reproduces the exact drift the split removes. Ownership/paired-PR matrix
  + contract tests + pin order are in §6 and M0.
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
- **Label — SINGLE PRIMARY HORIZON = open→close (finding 2).** The whole suite is
  standardized on **open→close (intraday-only)** as the one primary horizon: it has the
  cleanest signal, the lowest cost hurdle (1 round-trip/day, not churn), and it cleanly
  **separates overnight** (the close→open gap is excluded from label + features + PnL,
  Lou-Polk-Skouras). Label = triple-barrier (López de Prado): σ-scaled profit/stop
  barriers + a time barrier = the session close. Returns are **bar-timestamped and
  session-aware** (not daily `fwd_5d`); a per-name `ticker_forward_returns(fwd_1/5/…d)`
  daily surface is **insufficient** — M0 must build a **session-horizon forward-return
  surface** (open→close per name per session). 30min / 2hr are *secondary* diagnostics
  only; they do not drive any contract. Tie the horizon to the **cost hurdle**: expected
  edge must clear ~1.75× round-trip cost or it's untradeable.
- **GPU verdict: NO.** Models stay small (≤ low-millions of params), universe is
  small; CPU/MPS nightly batch is minutes even at ~80–100× bars. GPU only pays off
  for deep LOB on full depth + large universe — impossible here. Rent cloud GPU if
  that ever changes; **don't buy hardware**.
- **Training cadence:** nightly batch (matches 104 discipline); optional incremental
  fine-tuning later, never bypassing the gates.
- **Anti-overfit is MANDATORY (intraday overfits easily) — and we own the tooling**
  (`renquant-common` purged WF + `PurgedKFold` + `CombinatorialPurgedCV`). The
  critical change: **resize the embargo to the open→close label horizon IN BARS, rounded
  to a session boundary** (not 60 days; session-aware), **purge the overnight gap**,
  report the **CPCV OOS-Sharpe distribution + PBO + probabilistic PSR/DSR ≥ 0.95** (fed
  the full trial universe — §A.4 / finding 3), keep the **placebo** (shuffled-label /
  time-shift) gates, and judge **net-of-cost on a measured cost model**, never gross.
  Block scheme for the overlapping labels: effective-independent observations, not raw
  date counts (finding 3). The biggest single edge lever is a **measured-cost-validated
  SIP feed**, not the model or a GPU.

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
- **G8 kill-switch (state machine, NOT a single `TRADING_OFF` flag — finding 7):** admit
  a buy only in the `NORMAL` state. Distinct states + precedence (reliability §3.2):
  `NO_NEW_RISK` (blocks new buys, **allows** reduce-only/cancel exits — this is where the
  daily-loss breaker maps, so liquidation is never blocked), `CANCEL_OPEN_ORDERS`, and
  `FULL_HALT` (broker/account-integrity only, e.g. unreconciled state). Plus
  `AgentBreaker.admit()` and a max-deviation slippage reject at order emission.

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

## 6. Deploy (alongside 104, shadow-first) — pinned-subrepo ownership (finding 6)
**No triplication.** Each new capability has ONE owning repo; consumers use the canonical
contract; the umbrella only pins/wires. Ownership / paired-PR matrix:

| Capability | Owner repo | Consumer | Umbrella role |
|---|---|---|---|
| intraday bar ingestion + `*Store` (incremental, append-only) | **`renquant-base-data`** | pipeline reads via canonical loader | pin base-data; no logic |
| intraday features (`hourly/minute_features`), session-horizon return surface | **`renquant-base-data`** (data) → contract consumed by **`renquant-pipeline`** | model/decision | pin both |
| intraday label (triple-barrier, open→close), CPCV/embargo-in-bars | **`renquant-model`** | — | pin model |
| G1–G8 gate stack, decision ledger wiring | **`renquant-pipeline`** kernel | — | pin pipeline |
| 105 config / universe manifest / fingerprints | **`renquant-strategy-105`** (NEW, see below) | bridge | pin strategy-105 |
| broker-contract checks (M0.5) | **`renquant-execution`** | pipeline | pin execution |
| pins, bundles, run-orchestration, `--strategy` routing | **orchestrator** | — | the wiring layer |

**Where `renquant-strategy-105` is created:** a NEW pinned subrepo (mirrors
`renquant-strategy-104`), created at M0; holds the config skeleton, the point-in-time
universe manifest (one frozen + fingerprinted universe per decision date, finding 4), and
the strategy config-fingerprint. **Manifest/fingerprint flow:** strategy-105 emits the
universe + config fingerprint → orchestrator stamps it into the run bundle + the model
bundle (same `config_fingerprint` contract 104 uses) → pipeline preflight asserts the
live feature space + universe match the 105 artifact (F12/F16), fail-closed on mismatch.
**Contract tests + pin order:** base-data merges the loader contract first (with a contract
test the pipeline imports); pipeline merges against the pinned base-data; model against the
pinned data contract; strategy-105 + orchestrator pin last. **Retirement plan for umbrella
compat shims:** any temporary umbrella-side shim is tagged `# COMPAT-105-SHIM` with a
removal ticket and deleted once the owning repo's pin lands — never left as a third copy.

Deploy artifacts: `backtesting/renquant_105/` (config/state/artifacts) +
`scripts/intraday_105.sh` (buy+sell intraday) + `com.renquant.*105.plist`. The bridge
routes by `--strategy` → **no orchestrator code change**. 104 keeps running unchanged.
105 runs **shadow (readonly-alpaca, no orders)** until validated, then graduates.

## 7. Phased rollout (validation-gated, with a kill condition)
**Two INDEPENDENT hypotheses, separated (execution-plan gap).** The pivot bundles two
distinct claims that need distinct experiments and acceptance criteria:
- **H1 — intraday ALPHA** (a new cost-clearing intraday signal). Prior = NO-GO (§A).
  Tested in M1; STOP at M1 if it fails.
- **H2 — execution TIMING / RISK for the existing 104 book** (better fills + intraday
  exits on 104's *existing* trades; adds **no** new round-trips). This does NOT depend on
  H1 and has its OWN acceptance criterion: realized implementation-shortfall reduction vs
  the current next-open execution (measured, CI-bounded), with zero added turnover. An H1
  NO-GO leaves H2 as a clean, independently-validated deliverable — not a consolation.

- **M0 — Data:** point-in-time, coverage-gated universe (finding 4); re-enable intraday
  cache + `hourly/minute` features; incremental ingestion (base-data-owned) + refresh
  cron; the **session-horizon (open→close) forward-return surface**; feed/cost
  fingerprints (finding 5). (No model yet.)
- **M0.5 — Broker contract (finding 8):** encode the post-PDT broker contract before any
  size assumption — use current `buying_power`/intraday-margin fields, test rejection +
  margin-deficit handling in paper/shadow, define **leverage caps independent of the
  broker max**, fail closed on Alpaca field migration/deprecation. Until M0.5 passes, the
  account is NOT treated as "operationally clear".
- **M1 — Model + the make-or-break gate (H1):** train GBDT primary + PatchTST shadow on
  open→close triple-barrier labels; validate via **CPCV + PBO + probabilistic PSR/DSR
  ≥0.95 + placebo, net-of-cost on a MEASURED cost model**, over a power/MinTRL-derived
  aged sample (finding 3). **KILL:** if the intraday edge does not survive costs, **STOP**
  (the honest outcome may be "no tradable intraday edge at this size/data"); H2 continues.
- **M2 — Gates + shadow e2e:** build G1–G8 (entry meta-label, P&L breaker→NO_NEW_RISK,
  conformal lower-bound, CHOPPY gate, cost hurdle, slippage/stale rejects); shadow-run 105
  end-to-end on live intraday data; confirm the conjunction raises *realized* precision
  (placebo) and doesn't kill winners (ledger audit). **Gate proliferation ≠ validation
  (execution-plan gap):** G1–G3 are correlated transforms of the model/cost output, so
  M2 requires **per-gate ablations + marginal-contribution with multiplicity correction**,
  not only a conjunction-level placebo. Separate **pipeline parity** (champion vs itself,
  order-intent agreement ≥90%) from **strategy lift** (challenger vs champion) — the two
  are different comparators (execution-plan gap).
- **M3 — Live, tiny, monitored:** graduate with minimal size + the daily-loss
  breaker armed (→NO_NEW_RISK, exits allowed); the **$99 SIP** decision is a **fresh
  shadow parity+cost experiment** before any live SIP use (finding 5). Scale only on a
  **minimum live sample + exposure schedule** with precise risk limits (execution-plan
  gap), not "+1 gross step / 10–20% of book" alone.

## 8. Decisions I need (let's discuss)
Several of these are now **resolved in this revision** (Codex review) and stated as the
design's position, not open questions:
1. **Label horizon — RESOLVED: open→close (intraday-only), single primary horizon**
   (finding 2). 30min/2hr are secondary diagnostics only. (Confirm.)
2. **Universe — RESOLVED: point-in-time, coverage-gated** (finding 4): lagged 20d ADV +
   listing eligibility + halt/delist treatment + IPO seasoning + fail-closed missingness,
   frozen + fingerprinted per decision date. NO "complete history over the window" rule.
   (Confirm the ~40–60 size + the ADV/eligibility thresholds.)
3. **SIP feed ($99/mo):** build+train on free IEX (with feed fingerprints), and treat any
   live SIP switch as a **fresh shadow parity+cost experiment** (finding 5), decided at M3.
4. **Net-of-cost edge bar (k):** k≈1.75× round-trip cost as the admission hurdle?
5. **Scope:** single intraday horizon only (multi-horizon sleeves were rejected before).
6. **Kill condition:** agree that if M1 net-of-cost edge is not placebo-clean
   (PSR/DSR≥0.95), we STOP H1 rather than ship a cost-negative intraday book (H2 continues)?
7. **Broker contract (M0.5):** agree the account is not "operationally clear" until the
   M0.5 broker-contract checks are encoded + shadow-tested (finding 8)?

**Sources / auditable inputs (finding 1 + execution-plan gap).** The feasibility
numbers are reproduced by the committed `scripts/research_intraday_feasibility.py`
(the single auditable design input — *not* an off-PR "research transcript"); its inputs
are explicit assumptions to be replaced by M0/M1 measurements. Primary references:
- **Regulatory:** SEC order **34-105226** (Rule 4210 PDT-replacement approval), **FINRA
  Notice 26-10** + new intraday-margin guidance, Alpaca **June-4 migration/deprecation**
  docs — to be linked as primary citations (a `pattern_day_trader=False` screenshot is
  NOT a design input; the broker-contract milestone M0.5 encodes the real check, finding 8).
- **Methodology:** López de Prado *AFML* 2018 (triple-barrier, meta-labeling, CPCV,
  embargo/purge), Bailey & López de Prado 2014 (PSR/**DSR**/MinTRL), Bailey-Borwein-LdP-Zhu
  2016 (PBO/CSCV), Harvey-Liu-Zhu 2016 (t≈3 multiple-testing), Grinold-Kahn (Fundamental
  Law), Perold 1988 / Kissell (implementation shortfall), Heston-Korajczyk-Sadka 2010
  (same-time-of-day autocorrelation), Lou-Polk-Skouras 2019 (overnight vs intraday),
  Angelopoulos & Bates 2021 + Gibbs & Candès 2021 (conformal / ACI), arXiv 1005.3535
  (intraday cross-section net-negative after spread).
