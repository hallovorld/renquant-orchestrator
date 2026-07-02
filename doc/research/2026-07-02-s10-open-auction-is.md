# S10: open-auction implementation-shortfall study — MATERIAL-BUT-UNPROVEN

STATUS: research evidence (read-only). Task S10 of the unified plan (#231, Term EXEC);
upgrades POC-C leg 1 from point estimate to a CI-backed formal verdict.
DATE: 2026-07-02
SCRIPT: `scripts/s10_open_auction_is_study.py` (one-command reproduce, constants at top).
EVIDENCE: `doc/research/evidence/2026-07-02-roadmap-pocs/s10_open_auction_is.json`.

## Upgrades over POC-C

1. **TRUE daily VWAP** where 10-minute bars exist (`data/intraday/<T>/10min.parquet`
   carries per-bar `vwap`; day VWAP = Σ(vwap·vol)/Σvol over RTH, DST-correct ET
   selection): 20/41 fills; the other 21 (post-2026-05-01, where 10min coverage ends)
   fall back to OHLC4 with an explicit `ref_kind` label.
2. **Date-clustered block bootstrap** (5,000 resamples of DAYS, seed fixed): fills on
   one day share the market move; i.i.d. CIs would overstate precision. N = 41 fills
   on **18 independent days**.

## Results

| Reference | mean bps | median bps | 95% CI (date-clustered) |
|---|---|---|---|
| fill vs open | −4.6 | 0.0 | [−23.0, +7.8] — **fills ARE the open auction** (re-confirmed) |
| **fill vs day VWAP** | **+40.1** | +16.2 | **[−15.6, +99.2]** |
| fill vs close | +43.4 | +27.4 | [−51.4, +122.9] |

## Verdict (per the #230 §8 S10 row)

- **Prize point estimate: ~+40 bps/entry vs same-day VWAP — 4× the 10 bps materiality
  bar** debated in #208. `material_gt_10bps = true`.
- **NOT yet significant**: both economic CIs include 0 at 18 independent days.
  Formal S10 verdict: **material-but-unproven** — increment 1's mechanism is real at
  point-estimate level; proof needs more independent days.
- **Days-to-significance arithmetic**: SE(mean vs VWAP) ≈ 29 bps at 18 days; for the CI
  to exclude 0 at the current mean, SE ≲ 20 bps ⇒ ≈ **38–40 independent fill-days**
  (≈2× the current corpus). The N1 collectors' paired data accrues exactly this — one
  more reason the #232/#233 install is the binding step.
- Consistency: the median (+16.2) is well below the mean (+40) — the prize is
  right-skewed (a few very expensive opens); a robust (median/trimmed) policy target
  is likely nearer 15–25 bps, still above the bar.

## Roadmap effects

- #230 §8 S10 row: outcome branch resolved to "material at point estimate; significance
  deferred to collector corpus" (P(material) was raised to 0.65 pre-study; the study
  supports it).
- #208 §9.4 prereg input: use the measured right-skew (median ≪ mean) when choosing the
  estimand (median-IS or trimmed-mean-IS may be the better pre-registered target).
- G105 kill-branch check: NOT triggered (prize is not immaterial).
