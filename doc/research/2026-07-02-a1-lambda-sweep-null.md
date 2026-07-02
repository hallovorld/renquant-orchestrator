# A-1 λ dose-response: NOT a NULL — the round-1 harness never enabled the mechanism

STATUS: research evidence (read-only sensitivity study; the in-pipeline 10-session shadow
sweep remains the S6 enable-gating AC). Task: pre-enable evidence for RS-2's A-1 lane.
DATE: 2026-07-02 (round 2 — round 1's "NULL" result retracted, see below)
SCRIPT: `scripts/poc_lambda_sweep.py` · EVIDENCE: `doc/research/evidence/2026-07-02-roadmap-pocs/poc_lambda_sweep.json`

## What was wrong with round 1

The solver only adds the cash-drag objective term when **both**
`min_invested_pct > 0` **and** `cash_drag_lambda > 0` (`qp_solver.py:468`). Round 1's
script swept `cash_drag_lambda` but never passed `min_invested_pct`, so the wrapper
default (`0.0`) silently disabled the entire mechanism — identical solutions at every λ
were **guaranteed by construction**, regardless of whether the turnover cap binds. That
was an experiment-harness artifact, not evidence about the turnover cap.

Separately: the **live production config** (`strategy_config.json` →
`rotation.joint_actions`) currently has **both** `qp_min_invested_pct=0` and
`qp_cash_drag_lambda=0` set explicitly — the cash-drag mechanism is fully disabled on
both axes right now, not just on λ. This means **A-1 as literally scoped in RS-2**
(`qp_cash_drag_lambda 0 → 0.05`, leaving `min_invested_pct` untouched) has **zero
possible effect under current production settings** — a direct, mechanical consequence
of the gate condition. That is a real, useful fact, but it is not new empirical
evidence; it follows immediately from reading `qp_solver.py:468`.

## What round 2 actually tested

Three scenarios, driving the real solver on the latest two full runs (2026-06-30,
2026-07-01), with `w_current` now reconstructed per holding from that ticker's most
recent `trades.target_pct` as of the run date (not an equal-weight approximation — all
13 held-ticker positions across both runs had real trade history to reconstruct from):

1. **Production reality** (`min_invested_pct=0`, current `qp_turnover_max=0.15`):
   confirms the mechanical NULL — deployed fraction flat at 0.275 (07-01) / 0.314
   (06-30) across all five λ values. Expected; not new evidence.
2. **"Un-disabled" 2D sweep** (`min_invested_pct=0.7` — the value this same config
   carried before it was zeroed out, see `strategy_config.json.pre-meta-label-deploy`)
   × turnover cap ∈ {0.15 production, 0.20 global, 0.30 round-1's value, 0.50
   deliberately non-binding}.
3. **Positive control**: non-binding turnover (0.50) at `min_invested_pct=0.7`, sweeping
   λ alone — proves the harness can detect a λ effect when the mechanism is genuinely
   active.

## Result: λ has a large, real, monotonic effect once the mechanism is enabled

At the production turnover cap (0.15, BULL_CALM) with `min_invested_pct` restored to
0.7:

| λ | deployed_frac (07-01) | deployed_frac (06-30) |
|---|---|---|
| 0.00 | 0.275 | 0.314 |
| 0.01 | 0.331 | 0.370 |
| 0.02 | 0.371 | 0.408 |
| **0.05 (A-1's proposed target)** | **0.435** | **0.471** |
| 0.10 | 0.465 | 0.503 |

**A-1's proposed move (λ 0 → 0.05) adds ~16–19 percentage points of deployed fraction
in a single session, at the CURRENT turnover cap** — this is not a harmless, ≈0-impact
change once the mechanism is actually enabled. The effect is monotonic and consistent
across both runs and at every turnover cap tested (0.15/0.20/0.30/0.50) — λ genuinely
moves the solution everywhere, it does not vanish at any of the tested caps.

The turnover cap does limit the *maximum achievable* deployment per session (e.g. at
turnover=0.15, deployed fraction tops out around 0.47–0.50 even at λ=0.10; at
turnover=0.50 it saturates near the 0.70 target by λ=0.02) — so the ORIGINAL "turnover
cap constrains deployment speed" intuition has a real kernel of truth. But "constrains
the ceiling" and "makes λ have zero effect" are different claims — round 1 conflated
them because its harness could not distinguish "no effect" from "gate never fired."

## Reading (revised)

1. **A-1's expected deployment contribution is NOT ≈0** — it is the opposite:
   substantial, IF `min_invested_pct` is also un-disabled alongside `cash_drag_lambda`.
   As scoped in RS-2 today (λ alone), A-1 does nothing; as a genuine "un-disable the
   shipped mechanism" change (both parameters), it has real, monotonic, multi-run-
   consistent effect. **RS-2's A-1 definition needs a follow-up correction**: either
   broaden A-1 to cover both parameters (which is what "un-disabling a shipped
   control" actually requires, mechanically), or explicitly document that A-1 as
   currently scoped is a no-op and rename/retire it.
2. **Turnover-cap-as-churn-counter remains a real design question** (unchanged from
   round 1): the QP turnover cap counts cash-deployment the same as position-swapping,
   so a heavily-cash book needs multiple sessions to redeploy regardless of λ, once λ
   is actually enabled. Still flagged for the S6/S7 implementation PR, not decided
   here — same guardrail as before (never loosen a risk gate to force trades).
3. **This is a sensitivity study, not the enable-gating evidence.** The S6 in-pipeline
   10-session shadow sweep (RS-2's own preregistered protocol) remains the actual gate
   before any live enable of either parameter — this result changes what that shadow
   sweep should expect to see (a real, substantial deployment shift, not a null), not
   whether it's required.
4. **Caveats**: simplified constraints (no sector/correlation groups, no wash-sale
   mask); `min_invested_pct=0.7` is a historical value chosen because it is real and
   previously used in this exact config, not because it is the "right" target for a
   future re-enable — that number is a separate, undecided design/risk question.
