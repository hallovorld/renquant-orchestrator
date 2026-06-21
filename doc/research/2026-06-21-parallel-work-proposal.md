# Parallel work while seed45 runs — proposal for discussion

**Purpose:** pick the next bounded work to do *while the seed45 experiment finishes*, without
touching the running experiment. For operator + Codex to prioritize before I sink time.
Nothing here is started yet — this PR is the discussion.

## The key finding that reframes priority

**`BULL_CALM` trade-monotonicity fails in EVERY experiment so far** — 60d-unpruned, 20d,
Exp A, Exp B — **independently of the placebo.** `[VERIFIED — patchtst_gate / patchtst_20d_gate
/ exp_A_gate / exp_B_gate logs all show "monotonicity failed in active regime(s): BULL_CALM"]`

Implication: **even if seed45 cleans the placebo, the gate will STILL block on monotonicity.**
So monotonicity is a *separate, parallel* blocker on the path to daily-full trading — and
diagnosing it needs no seed45 data.

## Candidates (bounded · falsifiable · don't need seed45 · don't touch the run)

| # | work | why | size | needs operator? |
|---|---|---|---|---|
| **P1** | **Diagnose the BULL_CALM monotonicity gate failure** — read-only: what does the gate check, why does it fail in this one regime across all models, is it model-side or a gate-threshold artifact? | **on the critical path** — blocks promotion even with a clean placebo | S–M | no (read-only diagnostic; any fix = its own PR) |
| **P2** | **Build the C1 prod-path write-guard hook** (pre-commit / fs guard rejecting writes to `data/*.parquet`, strategy configs, live artifacts) | the ONE mechanical control from the agent contract not yet built; would have *prevented* the rawlabel incident | M | sign-off on scope |
| **P3** | **Pre-design the feature-engineering escalation** (the next lever if pruning isn't enough: new features / regime-conditioning), ready to launch the moment seed45 verdict is in | turns the likely "pruning marginal" outcome into an immediate next step, not a stall | M (design) | direction decision |
| — | win-rate / payoff (#393 follow-up) | **parked** — needs live trading first; not actionable now | — | — |

## Recommendation
**Start with P1** (BULL_CALM monotonicity diagnostic). It is the only candidate that is *also*
on the daily-full critical path and fully parallel to seed45 — a clean placebo without clean
monotonicity still does not promote. P2 (write-guard) is the strongest standalone safety win.
P3 is worth pre-designing if the prior is that pruning ends marginal (it currently is).

**Ask:** which of P1/P2/P3 should I open as a worked PR next? (P1 as a read-only diagnostic
doc; P2 as a flag-gated hook; P3 as a design doc.)
