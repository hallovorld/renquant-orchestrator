# The sector table, real frame — live blend scores × forward returns

Phase-2 step ⑦ (operator re-planning). The replay-frame table (orch#936)
answered "which sector likes which model" inside the replay construction;
orch#937 then measured that the replay panel and the LIVE blend pick
different names (0/15). This note re-asks the sector question with the
REAL system's own scores — `ticker_daily_state` live rows (43 dates,
2026-05-20..08-07, ~92 scored names/day) joined to OHLCV forward total
returns. Descriptive only: 38 usable dates, fwd-5d horizon (the 60d thesis
horizon is unreachable on a 2.5-month window), overlapping windows, no
multiplicity control.

## The table `[VERIFIED — tds × OHLCV, this session; ELIG tiers = the #934 frozen k]`

| sector | days | top-k mean fwd5 | sector-EW mean fwd5 | selection edge (bp/5d) |
|---|---|---|---|---|
| consumer | 38 | +2.18% | +0.67% | **+150.8** |
| industrial | 36 | +1.74% | +1.20% | **+53.4** |
| software | 38 | +2.34% | +2.00% | **+34.5** |
| finance | 34 | +1.45% | +1.39% | +6.4 |
| datacenter_hw | 36 | −0.62% | −0.50% | −12.4 |
| ai_chip | 38 | −0.57% | +0.27% | **−84.7** |

Pooled: **+25.1 bp/5d** — the live blend has genuine positive within-sector
selection on this window.

## Reading — three facts, all frame-dependence lessons

1. **The real frame nearly INVERTS the replay frame**: the replay panel was
   strongest in ai_chip/datacenter (Sharpe 1.96/2.49) and dead in consumer;
   the LIVE blend is worst in ai_chip (−84.7bp) and best in consumer
   (+150.8bp). With #937's 0/15 pick overlap, this is the same lesson from
   the outcome side: conclusions do not transfer between the two systems,
   in either direction.
2. **The live system's selection skill is real but lives elsewhere than
   assumed** — the pooled +25.1bp/5d is the first positive real-frame
   selection measurement on this window.
3. **ai_chip is now flagged BOTH ways**: the replay champion was never
   traded (#937), and the traded blend picks below the chip average.
   Whatever serves chips today, no evidence supports it.

## What this does not show

38 days cannot support Sharpe-grade claims or a routing decision; the
horizon is 5d, not the 60d thesis. This is the honest real-frame seed for
the converged (decision-C) comparison once orch#939 lands.
