# renquant105 alpha-discovery plan — progress

2026-06-28.

## STATUS
PROPOSAL doc + reproducible signal-scan scripts. READ-ONLY product: the scan
pulls Alpaca daily bars, computes 5 canonical price factors, measures
cross-sectional rank-IC vs a within-date shuffle floor. No orders, no git in the
live tree, no canonical writes.

## WHAT
- `doc/design/2026-06-28-renquant105-alpha-discovery.md` — the plan, reorganized
  around an alpha-candidate table with MEASURED results, then an honest verdict,
  then forward leads, then ONE proportionate-validation paragraph.
- `scripts/sighunt.py` — the cross-sectional rank-IC scan + shuffle placebo floor.
- `scripts/robustness.py` — Newey-West HAC t-stat + half-sample + yearly IC.

## WHY (the rewrite)
Supersedes the **closed** RFC #201, which led with a heavyweight validation
framework (CPCV / nested-CV / FWER-Holm / PBO / Deflated-Sharpe /
pre-registration / governance gates) **before a single signal had been
measured**. Operator and Codex both demanded a rewrite reorganized around
*finding* alpha, not vetoing it. This doc puts the measured candidate table
first and shrinks validation to one proportionate paragraph.

## KEY FINDINGS (from the scan, 8y panel 2018-05-30→2026-06-26, 127 names)
- Canonical price-trend factors have **no stable multi-day (20/60d) edge** on
  this universe.
- mom_12_1 is the only pulse and clears the floor **only at h=5** (IC +0.0274,
  t 1.88, 2.73× floor, +31 bps net), then **fails at the target h=20** (0.74×
  floor).
- The 2021–26 h20 momentum "edge" (1.24× floor) was a **bull-momentum regime
  artifact** — it collapsed to 0.74× once the panel was extended to 8 years.
  mom_12_1 IC sign-flips yearly (positive 22/23/24/26, negative 19/21/25).
- A minutes-of-compute screen caught this → proportionate validation is
  sufficient; the heavyweight rig was never needed.

## FORWARD LEADS
1. Regime-conditioned momentum (gate the tilt on existing HMM regime labels;
   cheap test = split IC by regime).
2. Orthogonal signals — analyst-revision / fundamentals — but only after a
   point-in-time data audit (publication timestamps, revision history, coverage,
   lag, survivorship).

## NOT DONE / OUT OF SCOPE
No CPCV/FWER/DSR framework, no pre-registration schema, no governance gates.
Validation is one paragraph by design. No retraining recommendation, no order,
no live-tree mutation.
