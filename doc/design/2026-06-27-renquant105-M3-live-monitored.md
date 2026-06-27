# renquant105 milestone M3 — live (tiny, monitored)

2026-06-27. Part of the renquant105 suite.

> ## ⛔ STATUS — M3 (live H1 intraday-ALPHA) is **PARKED** (reversible)
> M3 is the live tip of the **parked** H1-alpha stack (M1 → M2 → M3). **Phase -1 (PR #199)
> measured the net edge negative at plausible IC**, so M3 is **not reached** and **no live
> intraday-alpha capital is contemplated** under the current evidence. The design below is
> retained for a future un-park (master §0 banner). It is **NOT** an authorized live milestone.
> (The active live-relevant work is H2 execution-timing, which has its own gated, non-alpha live
> path — see the H2 doc.)

**Only entered if the H1-alpha path is un-parked AND M2 passed AND the probabilistic PSR/DSR ≥
0.95 still holds on shadow-period realized returns.** Given the measured result, **this milestone
is currently unreachable** — the correct outcome when the edge isn't there.

## Objective + scope
Deliberately enable live intraday alpha trading at **tiny size**, with the daily-loss
circuit breaker armed and full monitoring, governed by live-vs-shadow tracking and hard
kill conditions. Decide the SIP feed. Scale up only if net-of-cost edge holds live.

## Requirements
**Functional:**
- F3.1 **Deliberate enable** — `intraday_buys_enabled=true` is a gated, human-authorized
  act (never a default); fail-closed everywhere else.
- F3.2 Tiny size cap (e.g. ≤ 1–2 names, ≤ 10–20% of book) — canary, not full book.
- F3.3 The **P&L daily-loss circuit breaker** (threshold **derived** from the §3.3b loss budget,
  re-derived for the current ladder step — NOT an asserted −5%) + pre-trade 15c3-5 hard limits
  armed + the **per-order/per-symbol/per-session exposure envelope** (reliability §3.3b) checked
  pre-submit + the per-failure-class trigger-latency budget (§3.10, MTTH ≤ `bar_interval`).
- F3.4 **SIP feed decision** ($99/mo Algo Trader Plus) for NBBO-accurate live fills — the
  IEX adverse-selection penalty is a meaningful fraction of the entire net edge. **A switch
  to SIP changes the observation/execution distribution (finding 5): it is a FRESH
  experiment** — SIP must pass parity + a re-measured cost gate **in shadow before any live
  use**, never swapped in after IEX-based validation.
- F3.5 Live-vs-shadow tracking + the kill conditions live; the full metric suite live.
- F3.6 Deploy 105 alongside 104 (new pinned `renquant-strategy-105` subrepo + plists; the
  bridge routes by `--strategy` — no orchestrator code change).
**Non-functional:** fail-closed; monitored; observable; one-call rollback (last-known-good champion).

## Deliverables
The live 105 strategy (pinned, deployed alongside 104); the monitoring/alerting wiring;
the go-live runbook + rollback procedure.

## Metrics / KPIs
Live net Sharpe vs shadow; realized slippage vs expected; daily PnL; max drawdown; the
full alpha/risk/cost/model-health suite, live.

## Acceptance / scale / kill
*Sample bars are **effective-independent observations** (block scheme), not raw run/day
counts (finding 3); `252d-equiv` Sharpe is a scaling convenience, not 252 days of evidence.*
| State | Condition |
|---|---|
| **Go-live precondition** | M2 green + **PSR/DSR ≥ 0.95** holds on shadow-period realized + **M0.5 broker contract encoded** (finding 8) + **the quantitative loss budget + exposure envelope + worst-case gap/stale stress + restart/reconciliation + fault-injection acceptance suite GREEN** (reliability §3.3b/§3.10, finding 7) — the −5%/−20% thresholds are **derived** from position caps × measured vol × gap risk, re-derived per ladder step, NOT asserted; safety MTTH = the **fastest decision cadence** (≤ `bar_interval`), not a generic 30 min |
| **Exposure schedule (PRE-REGISTERED, EXACT; per-step N from a POWER calc, sequential testing across looks — finding 6, Codex round-4)** | a fixed 4-step ladder pinned NOW: **S1** ≤ 1 name / ≤ 5% of book → **S2** ≤ 2 names / ≤ 10% → **S3** ≤ 3 names / ≤ 20% → **S4** ≤ 4 names / ≤ 33%. **Observation unit = a completed live open→close session (effective-independent, block scheme).** **Per-step N is DERIVED, not hardcoded 20:** N_step = the **live minimum-effect / power calculation** (target = the step's go effect Sharpe ≥ 1.0 vs the HOLD boundary, α=0.05, power=0.80, using the step's measured session-return variance) — the **20 was a placeholder and is REMOVED**; the computed N_step is published in the pre-registration artifact before the step starts (and if N_step exceeds the 6-month budget, the step is **UNDERPOWERED → do-not-advance / stop**, the M1 F1.7 fallback). **Repeated-looks control (4 promotion decisions = 4 looks):** the scale-up test is a **sequential / e-value (anytime-valid) test** with a pre-registered **confidence/e-process boundary** per step, and the **family of 4 looks is multiplicity-corrected** (alpha spent across the 4 steps via an alpha-spending schedule pinned now) — so 4 sequential promotions do NOT inflate the false-promotion probability. **Evidence transfer between exposure levels (pinned):** **only the model + cost-calibration carry forward**; the **per-step Sharpe/DD/killed-winner evidence does NOT transfer** (a larger book changes fills, impact, and the loss budget), so each step is re-powered and re-tested on ITS OWN sessions — no borrowing a lower step's significance. **Maximum calendar duration to clear the whole ladder = 6 months;** **stop outcome if not met:** if any step fails its (sequential, corrected) scale-up boundary within the duration, **do NOT advance — revert to last-known-good champion and STOP** (the edge did not hold live), never wait indefinitely or hand-tune the ladder. |
| **On track** | live Sharpe (pre-registered effective-N window = the step's DERIVED N_step sessions) within **±0.5** of shadow-period Sharpe |
| **SCALE-UP** | the step's **derived N_step effective-independent live sessions** completed AND the **sequential/e-value boundary** (multiplicity-corrected across the 4 looks) is crossed for net Sharpe ≥ **1.0** AND max-DD shallower than **−10%** AND killed-winner ≤ 15% → advance exactly one ladder step (S1→S2→S3→S4) |
| **HOLD / de-risk** | dd −12..−15% or live Sharpe < 0.5 → freeze sizing |
| **KILL (state machine, fail-closed; finding 7/8 — thresholds CONSUMED from `loss_budget.yaml`, not hardcoded)** | dd < **`dd_kill`** (the artifact's generated multi-session envelope, current ceiling **−20%**; reliability §3.3b) → **`NO_NEW_RISK` + controlled flatten / reduce-only** (a market-risk event — exits ALLOWED; `FULL_HALT` is reserved for untrustworthy order-state/account-identity, never a drawdown, which would trap exits) · single-session loss < **`session_loss_budget_step`** (the artifact's generated per-step value, current ceiling **−5%**) → **`NO_NEW_RISK`** (halt buys, **exits ALLOWED**) · OOS IC ≤ 0 over the effective-N window · calibration slope ≤ 0 (CI-bounded) · live-shadow ρ < 0.2 (CI-bounded) → revert to last-known-good champion |

## Expected outcome (预期)
A small, controlled, monitored live operation that **scales only if net-of-cost edge
holds live**, and that **kills itself** on any of the hard conditions. Honest expectation:
feasibility is **UNDETERMINED** — the unit-corrected open→close prior is *marginal* (it
clears cost at IC 0.03–0.05 / σ_oc~200 bps but the FL net-Sharpe lens is more pessimistic),
so the terminal state is decided by M1's MEASURED data, not assumed. Either outcome is a
success: a measured pass → a small monitored live book; a measured fail → "M1/M2 gate not
cleared → intraday alpha stays OFF; intraday data used for H2 execution-timing + risk on the
daily-104 book." Either way we did not deploy a cost-negative book on a prior.

## Dependencies / inputs
M2 pass; the SIP feed (optional but recommended for a fair live test); **operator
authorization to enable live intraday trading** (the enable is never autonomous).

## Risks (FMEA subset)
Live-vs-shadow divergence (one model broken → revert); slippage blowout (>30 bps → exits
only); runaway loss (daily-loss breaker); ghost IEX fills (→ SIP). All covered by the kill
conditions + the breaker; trade *availability* is explicitly a non-goal (fail-closed beats
trading through uncertainty).

## Effort
~2–4 weeks (deploy + monitoring + runbook) once M2 is green — small relative to M1/M2.
