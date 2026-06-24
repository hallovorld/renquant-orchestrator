# Conviction threshold & the calibration intercept — research synthesis

2026-06-24. Adversarially-verified deep-research pass (16 claims, 3-0/2-0 votes)
on: how to set a **principled, non-overfit** rule for which model-ranked names
to actually buy, given our low-IC LTR model with an intercepted calibration.

## The problem (ground truth)
- Calibrated `mu ≈ 0.091·raw_panel + 0.0245` — a **+2.45% constant intercept**.
- The ranker is centered below zero (panel mean raw ≈ −0.206).
- So the live `mu_floor=0.03` mostly gates the **constant**, not conviction:
  NFLX/ZM (mu 0.031–0.033, *below* the cross-sectional mean) cleared it.
- OOS IC ≈ 0.05, within our ~0.036 leakage-floor noise.
- Tempting "fix": raise `mu_floor` to 0.045 to exclude NFLX/ZM → **rejected as
  data-snooping** (no forward validity).

## What the research says (well-established)
1. **Remove the intercept by construction — Grinold/MSCI.** Turn a raw score
   into a trustworthy alpha via `α = IC · σ · z(score)`, where `z()` is
   cross-sectional standardization so the **consensus / unconditional mean → 0
   alpha**; a constant carries no conviction and doesn't move the book off
   benchmark. Raw LTR scores are *not* scale-calibrated by design.
   — MSCI "Converting Scores into Alphas"; arXiv 2211.01494.
2. **A real admission floor is the cost hurdle, ~0.1–0.5% round-trip, not 3%.**
   Retail round-trip cost ≈ 0.07–0.46% (execution-quality dependent); the
   canonical rule is "trade only when E[return] > E[cost]"; cost = spread +
   impact + fees (commissions alone are incomplete). Our 0.03 is ~6–40× the
   cost hurdle — it's an arbitrary conviction number, not a cost floor.
   — J. Finance (jofi.13467); BlackRock transaction-costs viewpoint.
3. **At low IC, constrain turnover / shrink to benchmark — don't trade a weak
   signal harder.** The lower the IC, the more the optimum shifts to lower
   turnover and cost-aware construction; the max-gross-IR portfolio is
   suboptimal after costs; trade admission is intrinsically *cost-relative*,
   not an absolute scalar floor; alpha decay/persistence matter jointly.
   — Qian/JPM; AQR Gârleanu–Pedersen "Dynamic Trading".
4. **IC ≈ 0.05 is a usable ("good") level in general** — so the problem is the
   alpha *scaling* (intercept + arbitrary slope), not "no signal". CAVEAT: our
   0.05 sits inside our own ~0.036 leakage-floor noise, so we stay more
   conservative than the generic claim.

## Recommendation (prioritized, name-agnostic)
| # | Change | Basis | Status |
|---|--------|-------|--------|
| A | Replace the intercepted calibration with Grinold `α = IC·σ·z(raw)` | claims 11–13,15 | the real fix; needs WF validation |
| B | Admission floor = per-name round-trip cost (`α > cost`), ~0.1–0.5% | claims 1,2,9,10 | well-established |
| C | Push the decision into the cost-aware QP (shrink/turnover at low IC) | claims 3–8 | well-established |

**Minimal first step (shipped, default OFF):** cross-sectional de-mean of `mu`
in `ConvictionGateTask` (`demean_cross_sectional`) — removes the intercept so
the floor gates *relative* conviction. renquant-pipeline #145. MUST pass
placebo-clean through the per-regime WF gate before any production enable.

## Contested / our-caveat
- Generic "0.05 IC is good" vs our internal leakage-floor: trust placebo-clean
  DIFFERENCES, not absolute IC (see the WF-gate embargo note).
- Whether a conviction THRESHOLD is even the right tool: the research leans
  **no** — better calibration + cost-aware construction + stronger orthogonal
  alpha (analyst estimate revisions, the P1 track) is the durable answer.

## Sources
- MSCI, *Converting Scores into Alphas* — grinold α=IC·σ·score, standardize.
- arXiv:2211.01494 — LTR scores not scale-calibrated.
- Wiley J. Finance 10.1111/jofi.13467 — retail round-trip cost 0.07–0.46%.
- BlackRock — disclosing transaction costs (E[return] > E[cost]).
- Qian/JPM — endogenous cost-aware construction; low IC → constrain turnover.
- AQR Gârleanu–Pedersen — dynamic trading with predictable returns & costs.
