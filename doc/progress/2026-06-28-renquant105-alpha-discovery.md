# renquant105 alpha-discovery plan — progress

2026-06-28.

## STATUS
PROPOSAL doc + reproducible signal-scan scripts. READ-ONLY product: the scan
pulls Alpaca daily bars, computes 5 canonical price factors, measures
cross-sectional rank-IC vs a within-date shuffle floor. No orders, no git in the
live tree, no canonical writes. Forward lead #1 (regime-conditioned momentum) now
TESTED → NO; the orthogonal-signals pivot is pending operator/Codex review.

## WHAT
- `doc/design/2026-06-28-renquant105-alpha-discovery.md` — the plan, reorganized
  around an alpha-candidate table with MEASURED results, then an honest verdict,
  a structural large-cap insight (§2b), then forward leads (lead #1 now TESTED →
  NO), then ONE proportionate-validation paragraph.
- `scripts/sighunt.py` — the cross-sectional rank-IC scan + shuffle placebo floor.
- `scripts/robustness.py` — Newey-West HAC t-stat + half-sample + yearly IC.
- `scripts/regimemom.py` — forward-lead-#1 probe: mom_12_1 conditional IC by PIT
  SPY trend×vol regime + per-regime shuffle floor + run-length actionability.

## WHY (the rewrite)
Supersedes the **closed** RFC #201, which led with a heavyweight validation
framework (CPCV / nested-CV / FWER-Holm / PBO / Deflated-Sharpe /
pre-registration / governance gates) **before a single signal had been
measured**. Operator and Codex both demanded a rewrite reorganized around
*finding* alpha, not vetoing it. This doc puts the measured candidate table
first and shrinks validation to one proportionate paragraph.

## KEY FINDINGS (from the scan, 8y panel 2018-05-30→2026-06-26, 134 names, cov>0.55)
**Scope caveat (Codex #4/#2):** this is a current-watchlist, coverage-filtered,
price-only **survivorship-biased RETROSPECTIVE DIAGNOSTIC** — it cannot prove the
absence of edge. Every finding below is "under this diagnostic," not a general
no-edge verdict.
- These five canonical price-trend factors **did not show a robust unconditional
  20/60d cross-sectional edge UNDER THIS diagnostic** (not "price-trend is
  exhausted").
- mom_12_1 is the only pulse and clears the floor **only at h=5** (IC +0.0274,
  t 1.88, 2.73× floor, +31 bps net). At the target **h=20** it has positive net
  L/S (+87 bps) but its IC (+0.0130) **does not clear the floor** (0.74×, NW
  t≈0.95) — "positive net L/S, IC not above floor," not "no signal."
- The 2021–26 h20 momentum signal (1.24× floor) was a **bull-momentum regime
  artifact under this screen** — it fell to 0.74× once the panel was extended to
  8 years. mom_12_1 IC sign-flips yearly (positive 22/23/24/26, negative 19/21/25).
- A minutes-of-compute screen caught this → proportionate validation is
  sufficient for triage; the heavyweight rig was never needed.
- **Lead #1 (regime-conditioned momentum) TESTED → NO** (`regimemom.py`, PIT
  SPY trend×vol regime). UP-trend IC 0.0184 / NW t 0.87 = the unconditional
  average. The yearly sign-flip **survives inside UP-trend** (2021 100% UP yet IC
  −0.065), so trend does not isolate the momentum-paying state. The only live 20d
  cell, UP_CALM (IC 0.051 / +262 bps), is unusable: NW t 1.86 (1 of ~7 cells, no
  multiplicity control) and mean run-length 15.4d < the 20d holding horizon.
- **Structural HYPOTHESIS (not proven):** ~134 liquid large-caps + documented
  large-cap weakness of price-trend anomalies → a *plausible* reason this is an
  inhospitable place to look — consistent with the literature, but a biased
  retrospective screen cannot prove the price-trend family is "exhausted." Honest
  statement: two direct diagnostic tests (canonical factors + regime-conditioning)
  did not surface a price-trend edge here.
- **Reproducibility (Codex #1/#3/#5):** `sighunt.py` / `robustness.py` now take
  `--as-of / --out / --bars-cache / --refresh / --coverage`, read the cache
  WITHOUT Alpaca credentials when present, share ONE coverage threshold, and
  write `manifest.json` (as-of, universe + bar-cache hashes, kept-symbol list +
  hash, params, code commit). One-command repro + artifact paths are in design §5.

## FORWARD LEADS
1. ~~Regime-conditioned momentum~~ — **TESTED → NO** (see above; flip survives
   inside UP-trend, UP_CALM fails persistence).
2. **Orthogonal signals** (the live lead) — analyst-revision / earnings-surprise
   PEAD / fundamentals — work in large-caps, low-correlation to price-trend.
   **Pending operator/Codex review.** Prerequisite: a cheap point-in-time data
   audit of the FMP/analyst harvest (publication timestamps, revision history,
   coverage-by-date, lag, survivorship) BEFORE any IC claim.

## NOT DONE / OUT OF SCOPE
No CPCV/FWER/DSR framework, no pre-registration schema, no governance gates.
Validation is one paragraph by design. No retraining recommendation, no order,
no live-tree mutation.
