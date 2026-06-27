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
- **The binding constraint is ECONOMICS, and feasibility is UNDETERMINED (§A) — the
  numbers in §A are SUGGESTIVE PARAMETRIC PRIORS, not measurement-grade evidence, and do
  NOT "demonstrate" a verdict.** The committed, runnable
  `scripts/research_intraday_feasibility.py` computes a *parametric prior*: the edge
  identity `E[edge]=IC·σ_xs·factor` treats a Spearman rank-IC as a Pearson linear-forecast
  coefficient under Gaussian assumptions — scenario arithmetic, not an accounting identity,
  and the script holds **no measured sample**. The honest, unit-corrected split (finding 1):
  - **HIGH-frequency churn** (many round-trips/session) is **unfavorable** — paying ~11 bps
    round-trip several times a session swamps any plausible per-trade edge; multi-rebalance
    intraday is rejected outright.
  - **LOW-turnover open→close** (enter once, exit at the close, ≤1 round-trip/name/session)
    is **marginal-to-plausibly-viable** at a realistic IC (0.03–0.05) and a realistic
    open→close cross-sectional dispersion (~150–250 bps): there the top pick's gross edge is
    **≈ or above** the ~11 bps round-trip cost (e.g. IC 0.05, σ_oc 200 bps → 17.5 bps gross,
    +6.5 bps net). **This is the variant worth MEASURING.**
  Round-trip cost ≈ **11 bps** is a **placeholder** (band 7–17) that M0/M0.5 must replace
  with a *measured* distribution (finding 5) — it cannot gate H1. Note the round-1 "edge
  ~1 bp / multi-day hold / 0-of-36-negative-grid" conclusion was a **unit bug** (a single
  25-bps number used as BOTH a 5-min-bar AND an open→close dispersion, which differ by
  ~√78≈9×); the corrected open→close grid is **14/48 positive**.
- **So renquant105 is NOT a churn machine.** The defensible program: (a) **MEASURE** the
  low-turnover open→close variant in a cost-charged SHADOW HARNESS (no real money) — the
  only thing that can settle the UNDETERMINED prior; (b) intraday **execution-TIMING** for
  better fills on the daily-104 book's *existing* trades (reduces cost, adds **no**
  round-trips — **H2**); (c) intraday **risk management** (sell-only exits on intraday
  signal decay). H2/(c) do not depend on an intraday alpha model clearing the cost hurdle.
- **GO/NO-GO is quantitative and DEFERRED TO MEASURED DATA (§A.4 / M1).** The §A priors are
  suggestive, not a license; only an M1 run on **measured** cost+dispersion settles it. Live
  intraday alpha capital is justified ONLY if M1 *empirically* delivers placebo-clean OOS IC
  ≥ **0.03** at the open→close horizon AND net-of-cost Sharpe ≥ **1.0** AND a **probabilistic
  PSR/DSR ≥ 0.95** (Deflated Sharpe per Bailey & López de Prado, fed the full trial universe —
  §3 / finding 3), over a **power/MinTRL-derived minimum aged sample sized in
  effective-independent observations** (not a raw date count). **Default outcome = intraday
  alpha trading stays OFF until measured to clear the bar.**
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
>   `-M3-live-monitored.md` — per-milestone detailed designs for **H1 (intraday alpha)**
>   (requirements, metrics, numeric acceptance, expected outcomes + kill conditions)
> - `…-H2-execution-timing.md` — the INDEPENDENT **H2 (execution-timing/risk)** milestone
>   (data contract, comparator, arrival-price capture, paired-block inference, promotion/kill)

## A. Quantitative feasibility analysis — PARAMETRIC PRIORS (UNDETERMINED, not a verdict)
Account ~$10.6k, 4× intraday BP $37.7k; liquid >$6 large-caps; IEX data; 1–5 min bars.
**Primary horizon/policy = open→close, bounded turnover** (enter on any gated bar, exit at
the close, ≤1 open position per name per session; overnight excluded — pinned in §4/§7).
Every number below is at that horizon.

**This section is REPRODUCIBLE but it is NOT measurement.** The numbers are computed by the
committed, read-only `scripts/research_intraday_feasibility.py` (no network, no DB, no
model). **They are PARAMETRIC PRIORS, not measurement-grade evidence:** the central identity
`E[edge]=IC·σ_xs·factor` treats a **Spearman rank-IC as if it were a Pearson linear-forecast
coefficient** under Gaussian assumptions (standardized scores/returns, a stable top-bucket
conditional mean). That is suggestive **scenario arithmetic, NOT an accounting identity**, and
it **cannot "demonstrate" a verdict**. The script holds **no measured sample** (its
block-bootstrap CI is wired for use *once* a measured sample exists). **Feasibility is
therefore UNDETERMINED — only M0/M1 measured OOS data settles it** (a purged-OOS
`E[return | score quantile]` on a measured cost model, deferred to M1; finding 3). Reproduce:

```
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/research_intraday_feasibility.py
```

Every input is an **ASSUMPTION** (band noted). The committed `11 bps` cost is a
**placeholder** the M0/M0.5 measurement must replace (finding 5) — it cannot gate H1.

**A.1 Round-trip cost** (`round_trip_cost_bps`). `RT = 2·(half_spread + slippage +
IEX_adverse_selection) + impact`. Per-leg liquid large-cap on IEX = 3.5–9 bps; impact
negligible (A.3). Committed base placeholder = **11 bps** (band 7–17).

| Scenario | per-leg | RT cost |
|---|---|---|
| Optimistic (mega-cap, tight) | 3.5 bps | **7 bps** |
| Base (liquid large-cap, IEX) | 5.5 bps | **~11 bps** |
| Conservative (IEX staleness) | 8.5 bps | **~17 bps** |

**A.2 Open→close edge of the top pick vs cost — the UNIT FIX** (`expected_top_edge_bps`).
`E[edge_top] = IC·σ_oc·factor`; top-bucket `factor≈1.75` (= E[Z | Z>1.28] for a top-decile
truncated standard normal, a Gaussian PRIOR). **Codex finding 1 (verdict-changing):** the
round-1 script used a single `σ_xs=25 bps` as BOTH a single-5-min-bar dispersion AND the
open→close dispersion — but those differ by ~√78≈9× (78 five-minute bars/session). The two
are now **distinct fields**: `σ_xs_5m≈25 bps` (single bar; churn comparison only) vs
**`σ_xs_open→close≈200 bps`** (whole session; band 150–250, to be MEASURED at M0). For the
open→close policy the edge uses `σ_oc` **directly — NO √78 scaling**:

| IC (OOS) | gross edge (σ_oc=200) | − RT 11 bps | net | clears RT? |
|---|---|---|---|---|
| 0.01 | 3.50 bps | −11 | −7.50 | no |
| 0.02 | 7.00 bps | −11 | −4.00 | no |
| 0.03 | 10.50 bps | −11 | −0.50 | ≈ break-even |
| 0.05 | 17.50 bps | −11 | **+6.50** | **YES** |

→ at a realistic open→close dispersion (~200 bps) and IC 0.03–0.05 the top pick's gross edge
is **≈ or above** the ~11 bps round-trip cost. **NOT "underwater ~10×".** The round-1 ~1 bp /
"0 of 36" result was the unit bug; corrected, the open→close variant is **marginal-to-viable**.

**A.2b Required open→close dispersion to clear cost** (`required_dispersion_to_clear_bps`).
`σ_oc ≥ k·RT/(IC·factor)`. The honest question is not "how many bars to hold" (the round-1
"multi-day hold" was an artifact of mis-scaling a 5-min dispersion across 78 bars) but
**"is the single open→close dispersion large enough"**:

| IC | k | required σ_oc | measured prior (~200 bps) clears? |
|---|---|---|---|
| 0.03 | 1.0 | 209.5 bps | ≈ (just under) |
| 0.05 | 1.0 | **125.7 bps** | **YES** (well inside the 150–250 band) |
| 0.05 | 1.75 | 220.0 bps | ≈ |

Break-even at IC 0.05 needs only ~126 bps of open→close dispersion — **inside the plausible
band**. (`11/(0.05·1.75)=125.7 bps` is exactly that break-even dispersion, the number Codex
flagged.)

**A.3 Sensitivity grid (the corrected result — NOT 0/36).** Sweeping
IC × σ_open→close × RT over the **plausible measured open→close range** (σ_oc ∈ {120, 150,
200, 250}, IC ∈ {0.01, 0.02, 0.03, 0.05}, RT ∈ {7, 11, 17}) gives **14/48 cells with positive
net open→close edge** — concentrated at IC 0.03–0.05 and σ_oc ≥ 150 bps (e.g. IC 0.05/σ_oc
200/RT 11 → **+6.5 bps**; IC 0.03/σ_oc 250/RT 11 → +2.1 bps). Capacity/impact
(`square_root_impact_bps`, `I=Y·σ·√(Q/ADV)`) is **<1 bp** at this size — a non-constraint.

**A.4 Net Sharpe (Fundamental Law) — the more pessimistic lens** (`fundamental_law_gross_ir`
+ `cost_drag_sharpe`). OOS IC honest band **0.01–0.03** (0.05 ref); transfer coeff ≈0.5;
**effective** breadth = 4 *independent* bets/day × 252 = 1008/yr (NOT names×rebalances).
Transferred gross IR (TC·IC·√breadth) = **0.16–0.48** (0.79 at IC 0.05). Cost drag is charged
on the **stateful book turnover** from the pinned H1 policy (one full rotation of a 4-name
book = **1.0 book turnover/day**, NOT a `rebalances_per_day=1` assertion nor 4× the book):

| cost regime | book turnover/day | cost drag (Sharpe) |
|---|---|---|
| **PRIMARY open→close** (1 rotation) | 1.0 | **−1.46** |
| rejected intra-session churn | 1.5 | −2.18 |

→ the FL net-Sharpe band ≈ **−1.3 to −0.66** over the honest IC band. This is the
**more pessimistic lens** (it charges a full rotation's cost against the *honest-band* IR;
at the 0.05 reference the IR 0.79 roughly offsets the −1.46 drag). The cleaner per-trade test
(A.2) clears cost at IC 0.05/σ_oc 200. **Both agree the open→close variant is MARGINAL —
UNDETERMINED, worth MEASURING — not refuted; and high-frequency churn is rejected.** A
live-capital GO requires M1 to clear ALL of the pre-registered bar (placebo-clean OOS IC, net
Sharpe ≥1.0, **PSR/DSR probability ≥0.95**, PBO <20%, net-PnL block-bootstrap 95% CI lower
bound >0) over a **power/MinTRL-derived minimum aged sample** (finding 3) on **measured**
cost+dispersion (finding 5). **Prior = UNDETERMINED (marginal); default = intraday alpha OFF
until measured to clear the bar.**

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
- **H1 — intraday ALPHA** (a new cost-clearing intraday signal). Prior = **UNDETERMINED /
  marginal** (§A) — measured in M1; STOP at M1 if it fails the bar.
- **H2 — execution TIMING / RISK for the existing 104 book** (better fills + intraday
  exits on 104's *existing* trades; adds **no** new round-trips). This does NOT depend on
  H1 and has its OWN acceptance criterion + its OWN milestone doc
  (`…-H2-execution-timing.md`): realized implementation-shortfall reduction vs the current
  next-open execution on the SAME order intents (measured, paired-block CI-bounded), with
  zero added turnover and no change to selection/size. An H1 stop leaves H2 as a clean,
  independently-validated deliverable — not a consolation.

**H1 trading policy (PINNED — finding 4).** The §A economics, M1 replay, and live path all
charge cost from THIS stateful policy, never `rebalances_per_day=1` by assertion:
- **Decision timestamps:** the gate stack is evaluated at each closed-bar boundary in the
  session (e.g. every 5/30 min); a name is **entered on the first bar it is gated-admitted**.
- **Holding rule / exit:** the triple-barrier **time barrier = the session close**; positions
  exit at the close (or earlier on a σ-scaled profit/stop or a protective exit).
- **≤1 open position per name per session; max replacements/session = 0** — once a name is
  exited it is NOT re-entered the same session (bounded turnover, no churn).
- **Max entries/session** = a small cap (e.g. ≤6 distinct names) under the G7 scarcity knapsack.
- **Overnight boundary:** every position is flat by the close; the close→open gap is **excluded**
  from label, features, and PnL (overnight is a separate book).
- **Turnover accounting:** each entered name incurs **exactly one round trip**; total
  round-trips/session = names-entered; book turnover/day = one rotation (≈1.0). The feasibility
  script (`H1Policy`) and the M1 replay compute cost from this path, per-decision-timestamp.
- **Per-decision label construction:** the open→close (session-aware, bar-timestamped) forward
  return from the entry bar to the session close, off the M0 session-horizon surface.

- **M0 — Data + COST INSTRUMENTATION (finding 5 — breaks the circular dependency):**
  point-in-time, coverage-gated universe (finding 4); re-enable intraday cache +
  `hourly/minute` features; incremental ingestion (base-data-owned) + refresh cron; the
  **session-horizon (open→close) forward-return surface**; feed/cost fingerprints. **M0 also
  CAPTURES the measured arrival/quote/fill sample AND CALIBRATES the cost model** (from the
  existing 104 fills + paper-order probes with explicit no-live-risk semantics), with a
  defined minimum sample by ticker × time-of-day × order type + a CI requirement — so the
  measured cost model is an M0 artifact that **exists before M1 gates on it** (the 11 bps
  placeholder cannot gate H1). (No alpha model in M0.)
- **M0.5 — Broker contract (finding 8):** encode the post-PDT broker contract before any
  size assumption — use current `buying_power`/intraday-margin fields, test rejection +
  margin-deficit handling in paper/shadow, define **leverage caps independent of the
  broker max**, fail closed on Alpaca field migration/deprecation. Until M0.5 passes, the
  account is NOT treated as "operationally clear".
- **M1 — Model + the make-or-break gate (H1):** train GBDT primary + PatchTST shadow on
  open→close triple-barrier labels; validate via **CPCV + PBO + probabilistic PSR/DSR
  ≥0.95 + placebo, net-of-cost on the M0-calibrated MEASURED cost model** (consumed, not
  produced, here — finding 5), over a power/MinTRL-derived aged sample (finding 3). M1 also
  estimates `E[return | score quantile]` **directly** from purged-OOS predictions (replacing
  the §A Gaussian edge prior with measurement). **KILL:** if the intraday edge does not
  survive costs, **STOP** (the honest outcome may be "no tradable intraday edge at this
  size/data"); H2 continues.
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

**Sources / auditable inputs (finding 1 + execution-plan gap).** The §A feasibility numbers
are reproduced by the committed `scripts/research_intraday_feasibility.py` (the single
auditable design input — *not* an off-PR "research transcript"). They are **parametric
PRIORS, not measurement** (the edge identity is a Gaussian scenario approximation, not an
accounting identity); their inputs are explicit assumptions to be **replaced by M0/M1
measurements** before any GO. Primary references:
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
