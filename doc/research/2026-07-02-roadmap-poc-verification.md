# POC verification of the roadmap's load-bearing claims (measured, reproducible)

STATUS: research evidence — four read-only POCs converting the #230 route document's
reasoned-tier claims into measured-tier claims (or correcting them). Operator directive
(2026-07-02): every claim needs theory or data support; POCs authorized; reproducibility
required. No production paths touched; all inputs read-only.
DATE: 2026-07-02
SCRIPTS: `scripts/poc_effective_breadth.py` · `scripts/poc_conviction_deployability.py` ·
`scripts/poc_entry_timing_cost.py` · `scripts/poc_factor_orthogonality.py`
EVIDENCE: `doc/research/evidence/2026-07-02-roadmap-pocs/*.json` (committed)
REPRO (all): `cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a &&
.venv/bin/python <orchestrator>/scripts/<script>.py` — deterministic, constants at top of each
script; POC-C leg 1 additionally reads the broker's closed-order history (read-only GET).

---

## POC-A — effective breadth (BR) of the 104 panel

**Claim tested** (#230 §7.1): nominal BR ≈ 600/yr; correlation-effective ~100–200/yr.
**Theory**: Grinold–Kahn BR = independent bets/yr; correlated bets reduced via (i) naive
equicorrelation `N/(1+(N−1)ρ̄)` and (ii) the eigenvalue participation ratio
`(Σλ)²/Σλ²` (effective rank).
**Method**: pivot `fwd_60d_excess` (142 tickers × 2,541 dates) to date×ticker; non-overlapping
windows at stride 60 (43 dates — **q = 142/43 ≈ 3.3 ⇒ rank-deficient corr matrix, PR biased
DOWN**); therefore also a well-conditioned proxy of the same cross-sectional structure:
`fwd_5d_excess` at stride 5 (509 windows, q ≈ 0.28).
**Result**: ρ̄ ≈ 0.001 (excess labels already remove the market mode); N_eff(PR, conditioned)
= **31.2 names** ⇒ **BR_eff ≈ 131/yr point estimate**, interval **[77, 500]** (60d-PR lower
bound; equicorr upper bound).
**Verdict**: the asserted 100–200 contains the point estimate — **claim SUPPORTED, now
measured**, with the honest interval attached.
**Roadmap impact**: current-universe active-IR arithmetic re-anchored: IC 0.03 × TC 0.7 ×
√131 ≈ **0.24** (was 0.3–0.45 on the asserted range); the 0.40 figure requires the M8 breadth
wave to succeed (≈400 quality names at the measured N_eff/N ratio ⇒ BR_eff ≈ 370 ⇒ IR ≈ 0.40).

## POC-B — conviction deployability (does lane A suffice, or does scarcity bind?)

**Claim tested** (#230 §8.1 S6 Plan-B premise): "conviction scarcity binds — only ~3 names
clear the floor — so lane B is required."
**Method**: for the last 6 daily FULL runs, count candidates with `mu ≥ 0.03` and compute the
deployment CEILING = Σ min(kelly_target, 12%) over floor-clearing, non-hard-blocked names
(veto/correlation/sector kept binding; top_n window + cash blocks removed).
**Result** (state-dependent, which is itself the finding):

| Run | names > floor | raw-Kelly ceiling |
|---|---|---|
| 07-01 (post-retrain) | 17 | **94.8%** |
| 06-30 (post-retrain) | 20 | **92.3%** |
| 06-25 / 06-26 (fail-closed days) | 6–22 | **0%** (hard blocks took all) |
| 06-22 / 06-23 (pre-retrain) | 8–9 | 59–73% |

**Verdict**: the scarcity claim as stated is **REFUTED for the current (post-retrain) state**
— the raw-Kelly ceiling is ~93–95%. However the ceiling uses UN-shrunk Kelly; the observed
shrinkage stack (kelly × conviction × σ-mult ≈ ×0.43 on the 07-01 fill) puts the realistic
lane-A ceiling at ≈ **40–43%** — still short of the 60% AC. **Corrected statement: lane A
gets ~40%, lane B covers the residual; and the ceiling is STATE-DEPENDENT (fail-closed days
zero it), so the sleeve also insures deployment against gate-state volatility.**
**Roadmap impact**: S6's AC stays; its Plan-B rationale is rewritten from "scarcity" to
"shrinkage + state-dependence" (measured).

## POC-C — entry-timing cost from REAL broker fills + overnight/intraday split

**Claims tested** (#230 §5 increment 1; #208 A4.1): (a) our fills are the open auction;
(b) the open is expensive vs the rest of day on our buy days; (c) returns on our names accrue
predominantly overnight.
**Method**: leg 1 — all closed filled buy orders from the live broker account (N = 41),
each compared to its day's open / OHLC4 (coarse VWAP proxy — stated limitation) / close.
Leg 2 — 142 panel names × last 756 trading days: mean close→open vs open→close returns;
plus the current top-quartile 12-1 momentum subset (PIT caveat stated in-script).
**Result**:
- (a) **CONFIRMED**: fill times 09:30:00–09:30:01; fill vs open median **0.0 bps** (mean −4.6).
- (b) **SUPPORTED in point estimate, NOT yet significant**: on buy days, open vs close
  **+48.6 bps mean / +58.1 median** (SE 47.5, t ≈ 1.0 at N=41); fill vs OHLC4 +23.0 bps
  (median +13.4). Direction and size are economically material (≫ the 10 bps threshold
  debated in #208), significance awaits the S10 full sample + collector corpus.
- (c) **REFINED**: unconditionally our panel splits **62/38 overnight/intraday**
  (7.7 vs 4.8 bps/day; top-momentum quartile 65/35) — NOT the "~100/0" of the deep-research
  citation; but **conditional on our buy days** the intraday leg is −49 bps (gap-up-and-fade),
  which is what the delayed-entry thesis actually needs.
**Verdict**: increment 1's mechanism is real on our own fills at point-estimate level; the
general overnight claim is corrected to 62/38.
**Roadmap impact**: S10 keeps its AC (CI required); #208's Stage-1/2 prize estimate gains a
measured anchor (~20–50 bps/entry point estimate); the memory-level "intraday ≈ 0" claim is
annotated with the measured split.

## POC-D — factor orthogonality (the stacking discount)

**Claim tested** (#230 §2.4 path 2): "3 orthogonal 0.02s ≈ 0.035."
**Theory**: for k standardized signals with equal IC and pairwise score correlation ρ,
`IC_comb = k·IC / √(k + k(k−1)ρ)`.
**Method**: month-end cross-sectional Spearman correlations over 36 months between
mom_12_1, reversal_20, low-vol_60 on the 142-name panel.
**Result**: ρ(mom,rev) = −0.05; ρ(mom,lowvol) = −0.20; ρ(rev,lowvol) = +0.07;
avg |ρ| = **0.217** ⇒ 3 × 0.02 stacks to **0.029** (not 0.035; −17%).
**Verdict**: the ideal-orthogonality figure was optimistic **within the price family**;
cross-data-family ρ (price vs revisions vs quality) is typically lower, so the corrected
planning range is **0.028–0.033** for the G106 combined-IC target — the G106 gate value
(combined ≥ 0.02) is unaffected.
**Roadmap impact**: §2.4 planning number updated; G106 threshold unchanged.

---

## Net effect on the route document

| # | Claim | Was | Now (measured) |
|---|---|---|---|
| 1 | BR_eff | asserted 100–200 | **131/yr point, [77, 500]** — current-universe IR anchor 0.24; 0.40 requires M8 |
| 2 | Lane-A sufficiency | "scarcity binds" | **refuted as stated**: raw ceiling 93–95% post-retrain; shrinkage-realistic ≈ 40–43%; state-dependent → sleeve still required, for corrected reasons |
| 3 | Open-entry prize | assumed material | **fills = open confirmed; +23–49 bps/entry point estimate, t≈1.0 at N=41** — economically large, statistically pending S10 |
| 4 | Overnight claim | "~100% overnight" | **62/38** unconditional; buy-day conditional intraday −49 bps |
| 5 | Stacking math | 3×0.02 → 0.035 | **0.029 at measured intra-family ρ=0.217**; plan on 0.028–0.033 |

All five updates are applied to `doc/research/2026-07-02-ic-ceiling-institutional-gap-107-route.md`
in the same revision. Scripts + JSON evidence are committed; every number above can be
regenerated with one command per script.

---

## POC-S-TC — the transfer coefficient, measured (addendum, task S-TC of #231)

**Claim tested** (#231 §0): TC ≈ 0.4 (the state vector's last reasoned-tier number).
**Theory**: Clarke–de Silva–Thorley (2002): IR = TC·IC·√BR with TC = corr(actual active
weights, unconstrained desired weights w* ∝ μ/σ² — the model's own `kelly_target_pct`).
**Method** (`scripts/poc_transfer_coefficient.py`): (1) FULL-BOOK TC — today's broker
positions (read-only /v2/positions) vs the latest full run's desired vector over all 89
scored names; (2) BUY-SIDE DECISION-TC — per historical full run, corr between desired
kelly and the actually-emitted buy target_pct among floor-clearing candidates.
**Result**:
- **Full-book TC = 0.438 Pearson / 0.481 Spearman** (n=89, deployed 43.1%) — the asserted
  0.4 was accurate; now measured.
- **Buy-side decision-TC ≈ 0.09 recent-mean, individual runs mostly 0.0** — even on runs
  that DID buy (6/8 eligible bought on 06-23), order sizes carry essentially none of the
  model's relative-conviction ordering: the top_n window + whole-share floor + uniformizing
  shrinkage stack flatten desired sizes into near-constant orders. The full-book 0.44 is
  inherited from historical position accumulation, not from the current decision path.
**Verdict**: state vector updated (TC row → measured 0.44 full-book / **0.09 buy-side**);
the buy-side number is the **strongest quantitative case for lane A + R4** yet: the
constraint stack does not merely shrink deployment (POC-B), it destroys the cross-sectional
ordering that IC is supposed to monetize — TC·IC is bounded by the SMALLER pipe.
**Limitation**: full-book is a same-day single pairing until the S5 ledger persists per-run
position values (then the series becomes routine). Target unchanged: **TC ≥ 0.6 on BOTH
readouts** after lane A + R4.
