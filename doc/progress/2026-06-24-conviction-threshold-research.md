# 2026-06-24 — Conviction-threshold / calibration-intercept research

STATUS: research synthesis landed; minimal-first-step code shipped separately
(renquant-pipeline #145, default OFF).

WHAT: `doc/research/2026-06-24-conviction-threshold-and-calibration-intercept.md`
— an adversarially-verified deep-research synthesis (16 cited claims) on how to
set a principled, non-overfit trade-admission rule for a low-IC LTR model with
an intercepted calibration. Recommends: (A) Grinold `α = IC·σ·z(score)` to
remove the intercept by construction, (B) a per-name cost-derived floor
(~0.1–0.5%, not 3%), (C) cost-aware construction at low IC — NOT a curve-fit
mu_floor.

WHY-DIR: operator rejected raising mu_floor to 0.045 to exclude NFLX/ZM as
data-snooping and asked for researched, evidence-based options. The intercept
(+0.0245) means the 0.03 floor gates a constant, not conviction.

EVIDENCE:
- `[VERIFIED]` deep-research workflow returned 16 adversarially-verified
  (3-0/2-0) claims with sources (MSCI Grinold, arXiv 2211.01494, J. Finance
  jofi.13467, BlackRock, Qian/JPM, AQR). Synthesis step hit a spend limit;
  claims synthesized manually.
- `[VERIFIED]` minimal-first-step code (cross-sectional de-mean, default OFF)
  shipped + tested in renquant-pipeline #145 (10 tests pass).

NEXT: validate the de-mean placebo-clean through the per-regime WF gate before
any enable; then evaluate the full Grinold reconstruction (A) + cost-derived
floor (B). The durable answer is better calibration + cost-aware construction +
the P1 analyst-revision alpha, not a threshold.
