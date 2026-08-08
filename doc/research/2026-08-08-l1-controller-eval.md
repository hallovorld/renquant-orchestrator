# L1 deployment controller — frozen-parameter evaluation on 2412 days

First measured deliverable of the allocation machine (design orch#918, L1).
Parameters were frozen in the derivation script header BEFORE any output was
seen: `λ=0.94 (EWMA), σ*=0.15, κ_bear=0.5, κ_vol=0.25, E_min=0.3, E_max=1.0,
cost=10bps per unit |ΔE|`. No other parameter set was run.

Controller: `exposure(t) = clip((σ*/σ̂(t))·g(π(t)), E_min, E_max)` with
`g = 1 − κ_bear·π_bear − κ_vol·π_bull_volatile`, vol and posteriors lagged one
day (no lookahead). Underlying = universe EW (investable proxy; the accidental
live book has only ~63 observable days and is compared on its own window
below). Regime posteriors = the production HMM series.

Reproducibility (the #913 standard): `data/2026-08-08-l1-eval-daily.csv`
(2412 daily rows) + `data/2026-08-08-l1-eval-verify.py` (recomputes every
headline number from the CSV alone) + `data/2026-08-08-l1-eval-derivation.py`,
which is now REPO-RELATIVE: it reads the committed
`data/2026-08-08-regime-posteriors.csv` (production-HMM snapshot, 2388 rows,
written %.17g / read round_trip so the float64 values are bit-exact — the
same snapshot and contract as #916's cube derivation) and regenerates the
committed daily CSV **byte-identically** in place; only the OHLCV tree remains
machine-local (stated provenance).

## Results `[VERIFIED — verifier output from the committed CSV]`

| arm | ann | vol | Sharpe | maxDD |
|---|---|---|---|---|
| fully-invested universe EW | +25.5% | 21.1% | 1.21 | −34.6% |
| **L1 controller (net)** | **+17.1%** | **12.4%** | **1.38** | **−17.4%** |
| full-invest 2024.. | +36.3% | 18.4% | 1.97 | −21.7% |
| controller 2024.. | +23.8% | 13.2% | 1.81 | −13.1% |
| full-invest 2022.. | +22.7% | 21.2% | 1.07 | −27.9% |
| controller 2022.. | +16.0% | 12.8% | 1.25 | −14.1% |

Mean exposure 76%; turnover 4.6×/yr (cost drag negligible at 10 bps/unit).

**The BEAR dial — risk claim only, and a visible correction.** The first
draft selected "bear days" with a future-aligned mask (`shift(-1)`: tomorrow's
posterior), which picked the crash days themselves and made the controller
look like it saves money in crashes (−37.3% → −14.1% pace). Codex caught the
timing; recomputed with the SAME lagged signal the controller acts on
(`shift(1)`), the segment flips `[VERIFIED — derivation output, corrected
timing]`: lagged-bear-signal days in this history were REBOUND-heavy — the
fully-invested arm ran at a +222.1% annualized pace there with −25.2%
within-segment drawdown, and the de-risked controller captured only +47.8%
while capping the segment drawdown at **−7.8%**. So the honest statement is:
**the dial reliably cuts risk on bear-signal days (−25.2% → −7.8% segment
DD), and in this rebound-heavy history it PAID an upside cost for that
protection.** The full-period numbers above already include that cost — the
controller's overall +17.1% / 1.38 Sharpe / −17.4% maxDD is net of it. G-B's
size-dial route functions as PROTECTION, not as a return enhancer, and any
promotion argument must rest on the risk-adjusted whole, not the segment.

## The three-way decision picture

| | ann (approx) | maxDD |
|---|---|---|
| today's accidental book (~22% exposure) | ~+5.6% `[DERIVED — 0.22 × universe ann]` | small, because barely invested |
| **L1 controller** | **+17.1%** | **−17.4%** |
| fully invested | +25.5% | −34.6% |

On the $10,961.59 book: controller ≈ **+$1,875/yr vs ≈ +$600/yr accidental —
≈ $1,275/yr recovered** with drawdown designed to −17%. Note this is smaller
than the $4,820/yr drag figure — that number benchmarks against FULL
investment at the hot window's rate, which the controller deliberately does
not target. Both numbers are true; they answer different questions.

## Honest limits

* Universe-EW proxy: the live book holds the panel's top-N, not the EW
  universe; a panel-book replay under the controller is the next fidelity
  step once the served matrix covers sizing.
* σ* = 0.15 is a frozen CANDIDATE. It maps to −17.4% historical maxDD; the
  operator's realized tolerance (−7.5%, achieved while 78% cash) may prefer
  a lower σ*. **Calibrating σ* to the operator's stated drawdown appetite is
  a policy input named in the design — changing it is setting policy, not
  sweeping parameters — but it must be set ONCE, before any live proposal,
  not tuned against this backtest.**
* Single frozen parameter set: no sensitivity surface was run, deliberately
  (the no-sweep discipline). The cost is not knowing robustness to λ/κ; the
  benefit is that this number cannot have been selected. If the operator
  wants a sensitivity map before deciding, that is a NEW preregistered run
  with the grid frozen first.
* No significance claim is made: the Sharpe/maxDD improvements are the
  measured history of one path. The promotion decision is policy-grade,
  like every exposure decision.

## Next

1. Operator inputs: drawdown appetite (sets σ*), and whether to proceed to
   the shadow phase (controller computes and LOGS target exposure daily
   alongside the live run — no order impact, a grant-free observability step).
2. Panel-book fidelity replay when sizing data allows.
3. Any live wiring is a production change: operator grant, one batch.
