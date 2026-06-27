# renquant105 milestone M3 — live (tiny, monitored)

2026-06-27. Part of the renquant105 suite. **Only entered if M2 passed AND the
probabilistic PSR/DSR ≥ 0.95 still holds on the shadow-period realized returns.** Given the
feasibility prior, **this milestone may never be reached** — and that is the correct outcome
if the edge isn't there.

## Objective + scope
Deliberately enable live intraday alpha trading at **tiny size**, with the daily-loss
circuit breaker armed and full monitoring, governed by live-vs-shadow tracking and hard
kill conditions. Decide the SIP feed. Scale up only if net-of-cost edge holds live.

## Requirements
**Functional:**
- F3.1 **Deliberate enable** — `intraday_buys_enabled=true` is a gated, human-authorized
  act (never a default); fail-closed everywhere else.
- F3.2 Tiny size cap (e.g. ≤ 1–2 names, ≤ 10–20% of book) — canary, not full book.
- F3.3 The **P&L daily-loss circuit breaker** + pre-trade 15c3-5 hard limits armed.
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
| **Go-live precondition** | M2 green + **PSR/DSR ≥ 0.95** holds on shadow-period realized + **M0.5 broker contract encoded** (finding 8) |
| **Exposure schedule** | pre-registered step-up ladder (e.g. canary ≤1 name → fixed minimum live sample at each step before the next), NOT ad-hoc |
| **On track** | live Sharpe (pre-registered effective-N window) within **±0.5** of shadow-period Sharpe |
| **SCALE-UP** | a **defined minimum live sample at the current step** AND net Sharpe ≥ **1.0** AND max-DD shallower than **−10%** AND killed-winner ≤ 15% → advance one ladder step (precise limits, not "+1 gross step / 10–20% of book") |
| **HOLD / de-risk** | dd −12..−15% or live Sharpe < 0.5 → freeze sizing |
| **KILL (state machine, fail-closed; finding 7)** | dd < **−20%** → **FULL_HALT** · single-session loss < **−5%** (the consistent threshold) → **`NO_NEW_RISK`** (halt buys, **exits ALLOWED**) · OOS IC ≤ 0 over the effective-N window · calibration slope ≤ 0 (CI-bounded) · live-shadow ρ < 0.2 (CI-bounded) → revert to last-known-good champion |

## Expected outcome (预期)
A small, controlled, monitored live operation that **scales only if net-of-cost edge
holds live**, and that **kills itself** on any of the hard conditions. Honest expectation:
the feasibility prior says the edge likely isn't there, so the most probable terminal
state of the whole project is "M1/M2 gate not cleared → intraday alpha stays OFF; intraday
data used for execution-timing + risk on the daily-104 book." That is success, not failure
— it means we didn't deploy a cost-negative book.

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
