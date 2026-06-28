# renquant105 fundamentals scan — value/quality/growth (verdict: NULL / nothing to carry)

2026-06-28.

## STATUS
Read-only research scan. **Kind: current-vintage retrospective diagnostic on a
biased current-watchlist panel — NOT PIT-clean, NOT survivorship-corrected.**
Verdict: no fundamental factor is worth carrying as a long signal on this panel.
The strongest signal is value, and on this panel it is NEGATIVE (cheap large-caps
underperformed expensive, 2018–2026) — but only **softly** significant once the
forward-return overlap is respected, and it flips sign by regime. Quality/growth are
null. Conclusions are limited to this biased panel; we do not extrapolate to a clean
universe. No order, no canonical path written, no git in the live tree, no self-merge.

## WHAT
Same cheap screen as the prior orthogonal-lane scans — per-day cross-sectional
rank-IC vs forward 20/60/120/252d, vs a within-date label-shuffle floor. **NO
CPCV/FWER/DSR** (triage, not a gate). 9 canonical factors (value/quality/growth),
keyed to `acceptedDate` (filingDate fallback) + next-session + 1-day slack,
forward-filled to next filing; price-based value uses the live daily price.
Universe = 134-name large-cap bars panel (`/tmp/sighunt/bars.parquet`).
Fundamentals = a single one-shot FMP `/stable` annual harvest
(`data/fmp_harvest/*_291.parquet`, harvested 2026-06-25).
Reproduce: `python scripts/fundamentals_scan.py --as-of 2026-06-26 --out /tmp/fund_scan`
(emits `results.csv` + `manifest.json` with input hashes + harvest endpoint
manifests + params + kept-symbol hash, matching #202's standard).

## KEY RESULTS (dependence-aware)
- IC daily series has lag-1 autocorr ≈0.99 at 252d (252d-overlapping windows). The
  original 21-day block-t was overlap-INFLATED. Recomputed for EY-252d (IC −0.122):
  old block-t −7.9 → non-overlapping t −2.4 (n=8) → stationary-bootstrap t
  −6.2/−4.2/−3.8/−3.5 across blocks 21/63/126/252. So value is negative and stable
  in SIGN but only **softly** significant — NOT "strong, stable."
- B/P-252d: nonover_t −1.8; FCF-252d: nonover_t −2.0; EV/EBIT-252d: nonover_t −1.1.
  Value is the only lane with any signal, and it points negative (cheap
  underperformed → documented growth-led mega-cap regime).
- Sign is regime-conditional: value-EY 60d IC negative in 2018/2020/2023/2024 but
  POSITIVE in the 2021/2022 value rotation. A regime bet, not a durable factor.
- Quality/growth NULL: ROE/gross-margin/accruals/revenue-growth |nonover_t|<0.9,
  |sb_t|<2.3 at every horizon; EPS growth weakly negative at 252d.

## CAVEATS
- **Not PIT:** current one-shot vintage harvest; no as-filed snapshot; historical
  rows can carry later restatements. acceptedDate-keyed (filingDate fallback).
- **Dependence:** report non-overlapping t + stationary-bootstrap block-length sweep;
  the shuffle floor is deflated by overlap and NOT used for the verdict.
- **Survivorship (framing corrected):** today's watchlist projected backward removes
  failed/distressed names and shifts ranks+returns AMBIGUOUSLY — it does NOT cleanly
  harden the negative call. All conclusions limited to this biased panel.
- Annual-only data; ~9 filings/name in window; turnover ≈1 refresh/name/yr; EV/EBIT
  uses a stale period-end EV (weakest).

## ORTHOGONALITY TO PEAD
Mechanically orthogonal (slow level tilt vs fast surprise drift), but the only
survivable framing is value-as-a-short/avoid overlay — soft, sign-flipping,
large-cap-weak, and shorting cheap mega-caps hits the high shorting bar.
**Recommendation: carry nothing; at most log value-EY rank as a regime/context
feature, never a tradable score.**

## NEXT
Do NOT pitch a fundamental factor for the scorer. The lane comes up empty at this
panel/data resolution. Deliverables: `scripts/fundamentals_scan.py`,
`doc/research/2026-06-28-renquant105-fundamentals-scan.md`, this progress doc, the
reproducible run bundle (`results.csv` + `manifest.json`), and the open PR for
concrete discussion. DO NOT merge.
