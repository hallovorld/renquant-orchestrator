# renquant105 fundamentals scan — value/quality/growth (verdict: NULL / nothing to carry)

2026-06-28.

## STATUS
Read-only research scan. **Verdict: no fundamental factor is worth carrying as a
long signal on this universe.** The only statistically strong, stable result is
**value, and it is robustly NEGATIVE** (cheap large-caps underperformed expensive
ones, 2018–2026) — and even that flips sign by regime. Quality/growth are null
(|t|<1.4). This is the last untested cheap PIT-clean orthogonal lane; it comes up
empty, which hardens the DATA+UNIVERSE-constraint conclusion. No order, no canonical
path written, no git in the live tree, no self-merge.

## WHAT
Same cheap screen as the prior orthogonal-lane scans — per-day cross-sectional
rank-IC vs forward 20/60/120/252d, vs a within-date label-shuffle floor, block-
bootstrap t. **NO CPCV/FWER/DSR** (triage, not a gate). 9 canonical factors
(value/quality/growth), built PIT-careful off annual FMP filings keyed to
`filingDate` + 2-day lag, forward-filled to next filing; price-based value uses the
live daily price. Universe = 134-name large-cap bars panel (`/tmp/sighunt/bars.parquet`).

## KEY RESULTS
- **Value (EY, B/P, FCF-yield, EV/EBIT): strong NEGATIVE IC**, monotone in horizon,
  high-t (EY-252d IC −0.124, block-t −7.9; B/P-252d t −7.2). Sign verified vs the
  latest cross-section (high-EY = GS/TSM/KLAC; low = SNOW/RBLX/MDB/CRWD). Cheap
  underperformed → the documented growth-led mega-cap regime. A long-value tilt
  would have bled.
- **Sign is regime-conditional**: value-EY 60d IC negative in 2018/2020/2023/2024
  but POSITIVE in the 2021/2022 value rotation. A regime bet, not a durable factor.
- **Quality/growth null**: ROE weakly negative (glamour); gross margin, accruals,
  revenue growth all |t|<1.4; EPS growth negative at 252d (growth mean-reverts).

## CAVEATS
- Shuffle floor is **deflated** by overlapping forward windows (IC lag-1 autocorr
  ≈0.98) → IC/floor ratios inflated, NOT used for the verdict; block-t is load-
  bearing (same embargo/overlap-floor artifact as the WF gate).
- **Survivorship**: 134-name = today's watchlist projected backward → a "value works"
  reading would be OPTIMISTIC, yet value still came out negative (hardens the call).
- Annual-only data; ~9 filings/name in window; turnover ≈1 refresh/name/yr; EV/EBIT
  uses a stale period-end EV (weakest PIT). PIT: filingDate-keyed +2d lag.

## ORTHOGONALITY TO PEAD
Mechanically orthogonal (slow level tilt vs fast surprise drift), but the only
survivable framing is value-as-a-short/avoid overlay — sign-flipping, large-cap-weak,
and shorting cheap mega-caps hits the high shorting bar. **Recommendation: carry
nothing; at most log value-EY rank as a regime/context feature, never a tradable score.**

## NEXT
Do NOT pitch a fundamental factor for the scorer. The lane is exhausted at this
universe/data resolution. Deliverables: `scripts/fundamentals_scan.py`,
`doc/research/2026-06-28-renquant105-fundamentals-scan.md`, this progress doc, and
the open PR for concrete discussion. DO NOT merge.
