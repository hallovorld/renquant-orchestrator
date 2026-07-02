# A-1 λ dose-response: harness bug fixed; one CONFIRMED mechanical finding, one CONDITIONAL sensitivity result

STATUS: research evidence (read-only sensitivity study; the in-pipeline 10-session shadow
sweep remains the S6 enable-gating AC). Task: pre-enable evidence for RS-2's A-1 lane.
DATE: 2026-07-02 (round 3 — round 1's "NULL" result retracted; round 2 fixed the harness
but overstated `w_current` precision and left stale "NULL" language in the PR surface,
both corrected in this round)
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
2026-07-01), with `w_current` approximated per holding from that ticker's most recent
`trades.target_pct` as of the run date (an improvement on round 1's equal-weight
approximation, but still an approximation — see the "w_current caveat" section below
for exactly what this does and does not capture):

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

## CONFIRMED (mechanical, not a sensitivity claim): A-1 as scoped in RS-2 is a no-op in production

Read directly from `qp_solver.py:468` and the live `strategy_config.json` — **A-1 as
currently scoped (`qp_cash_drag_lambda: 0 → 0.05` alone, per RS-2/#238) has zero
possible effect under current production settings**, because production also has
`qp_min_invested_pct=0`, which disables the entire cash-drag objective term regardless
of λ's value. This is a mechanical consequence of the gate condition (both parameters
must be `> 0` for the term to activate at all) — not an empirical/statistical claim, and
not subject to the caveats below. This is the PR's primary, load-bearing finding.

## CONDITIONAL SENSITIVITY (not a production-effect estimate): what happens if `min_invested_pct` is also un-disabled

At the production turnover cap (0.15, BULL_CALM) with `min_invested_pct` restored to
0.7 (a historical value this config carried before it was zeroed — see caveats):

| λ | deployed_frac (07-01) | deployed_frac (06-30) |
|---|---|---|
| 0.00 | 0.275 | 0.314 |
| 0.01 | 0.331 | 0.370 |
| 0.02 | 0.371 | 0.408 |
| **0.05 (A-1's proposed target)** | **0.435** | **0.471** |
| 0.10 | 0.465 | 0.503 |

Under this *conditional* scenario (both parameters un-disabled together, not A-1 as
literally scoped), λ 0 → 0.05 adds ~16–19 percentage points of deployed fraction in a
single session, monotonically and consistently across both runs and every turnover cap
tested (0.15/0.20/0.30/0.50) — the solver is genuinely responsive to λ once the
mechanism is active, it does not vanish at any tested cap. This is **SOLVER SENSITIVITY
under a target-weight approximation of `w_current`** (see caveat below) — it quantifies
how the optimizer *would* respond to this input combination, not a validated estimate of
what a live deployment would actually realize.

The turnover cap does limit the *maximum achievable* deployment per session (e.g. at
turnover=0.15, deployed fraction tops out around 0.47–0.50 even at λ=0.10; at
turnover=0.50 it saturates near the 0.70 target by λ=0.02) — so the ORIGINAL "turnover
cap constrains deployment speed" intuition has a real kernel of truth. But "constrains
the ceiling" and "makes λ have zero effect" are different claims — round 1 conflated
them because its harness could not distinguish "no effect" from "gate never fired."

## `w_current` caveat: target-weight approximation, not a true as-of reconstruction

`w_current` is built from each held ticker's most recent `trades.target_pct` as of the
run date (`_reconstruct_w_current` in the script). **This is an improvement on round 1's
equal-weight approximation, but it is still an approximation, not a genuine point-in-time
reconstruction**: `trades.target_pct` records the INTENDED target at trade time, not the
actual delivered/as-of weight — it misses price drift since the trade, partial/unfilled
orders, subsequent sells/exits, corporate actions (splits/dividends), and cash/NAV
normalization. The reported +16–19pp figure above CANNOT be called "the expected
production contribution" — it is solver behavior under this approximation, not a
validated real-world effect size.

**Reconstruction coverage (computed, from the current evidence JSON)**: 6/6 held
positions reconstructed for 2026-07-01, 7/7 for 2026-06-30 — 100% coverage in both runs
(no ticker lacked trade history to approximate from). **`sum(w_current)`** (the total
approximated starting weight, computed): **0.3951** (07-01), **0.4278** (06-30) — both
comfortably below 1.0, consistent with a cash-heavy book, but the gap between this
number and a true fully-normalized current weight vector is unknown (that gap is exactly
what the missing price-drift/fills/exits/corporate-actions/NAV-normalization factors
would close or widen). Both values are now stamped in
`doc/research/evidence/2026-07-02-roadmap-pocs/poc_lambda_sweep.json` per run as
`sum_w_current_target_pct_approx`.

## What a real effect-size claim requires

A genuine, defensible effect-size estimate for "what happens if both `min_invested_pct`
and `cash_drag_lambda` are changed together" requires a FULL run-bound replay/shadow
test using actual reconstructed state (not the `trades.target_pct` approximation) and
actual production constraints (sector/correlation groups, wash-sale mask — both
simplified away here) — not this standalone sensitivity script. The correct vehicle for
that follow-up is the same one-change-at-a-time preregistered experiment structure
`#228` established (baseline, immutable sessions, estimand, non-inferiority/risk
thresholds, stop rule, rollback) — this PR's conditional sensitivity result should
inform what that shadow sweep is powered to detect, not substitute for it.

## Reading (revised)

1. **A-1 as literally scoped in RS-2/#238 (λ alone) is CONFIRMED to be a no-op in
   production** (see CONFIRMED section above) — a mechanical fact, not a sensitivity
   claim. **RS-2's A-1 definition needs a follow-up correction**: either broaden A-1 to
   cover both parameters (what "un-disabling a shipped control" actually requires,
   mechanically), or explicitly document that A-1 as currently scoped is a no-op and
   rename/retire it.
2. **If both parameters are un-disabled together, the CONDITIONAL sensitivity result
   suggests a real, substantial, monotonic effect** — but this is solver behavior under
   an approximated `w_current`, not a validated production effect size (see caveat
   above). Do not cite "+16-19pp" as an expected production outcome without the full
   replay/shadow from the "what a real effect-size claim requires" section above.
3. **Turnover-cap-as-churn-counter remains a real design question** (unchanged from
   round 1): the QP turnover cap counts cash-deployment the same as position-swapping,
   so a heavily-cash book needs multiple sessions to redeploy regardless of λ, once λ
   is actually enabled. Still flagged for the S6/S7 implementation PR, not decided
   here — same guardrail as before (never loosen a risk gate to force trades).
4. **This is a sensitivity study, not the enable-gating evidence.** The S6 in-pipeline
   10-session shadow sweep (RS-2's own preregistered protocol) remains the actual gate
   before any live enable of either parameter — this result changes what that shadow
   sweep should expect to see (a real, substantial deployment shift under the
   conditional scenario, not a null), not whether it's required.
5. **Other caveats**: simplified constraints (no sector/correlation groups, no
   wash-sale mask); `min_invested_pct=0.7` is a historical value chosen because it is
   real and previously used in this exact config, not because it is the "right" target
   for a future re-enable — that number is a separate, undecided design/risk question.
