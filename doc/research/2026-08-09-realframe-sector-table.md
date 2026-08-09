# The sector table, real frame — live blend scores × forward returns

Phase-2 step ⑦ (operator re-planning). The replay-frame table (orch#936)
answered "which sector likes which model" inside the replay construction;
orch#937 then measured that the replay panel and the LIVE blend pick
different names (0/15). This note re-asks the sector question with the
REAL system's own scores — `ticker_daily_state` live rows (43 score dates,
2026-05-20..08-07) joined to OHLCV forward total returns.

**What this table is: a short-window descriptive ranking, nothing more.**
37 usable dates; fwd-5d windows overlap heavily (≈7 non-overlapping 5-day
blocks of independent information); six correlated sector contrasts are
inspected with no prespecified test, no uncertainty calculation, and no
multiplicity control. Neither the SIGN of the pooled edge nor the sector
ordering is statistically confirmed. The per-sector k tiers are borrowed
from #934 as a **declared descriptive lens only** — the L2-S run that
produced them recorded RECORD-ONLY, so they are a slicing convention here,
not a validated allocation or routing mechanism, and nothing in this note
validates one.

## The table `[VERIFIED — doc/research/data/2026-08-09-realframe-sector-derivation.py, rerun clean this session]`

Frozen derivation contract (source rows, as-of rule, sector map, tie
handling, return formula, admission rule, pooled weights) is stated in
full in the derivation script's docstring; per-name and per-sector-day
rows are committed beside it
(`2026-08-09-realframe-sector-rows.csv`, 2081 rows;
`2026-08-09-realframe-sector-days.csv`, 195 sector-days).

| sector | days | top-k mean fwd5 | sector-EW mean fwd5 | selection edge (bp/5d) |
|---|---|---|---|---|
| consumer | 35 | +2.26% | +0.60% | +166.0 |
| industrial | 35 | +1.47% | +0.94% | +52.8 |
| software | 30 | +2.39% | +1.93% | +45.2 |
| finance | 33 | +1.57% | +1.46% | +11.7 |
| datacenter_hw | 27 | −0.42% | −0.19% | −22.6 |
| ai_chip | 35 | −0.85% | +0.09% | −93.6 |

Pooled: **+28.3 bp/5d** across 195 sector-days (each weighted 1), of which
13 contribute a zero edge by construction (n_priced == k). On this window
the live blend's top-k beat their sector average in 4 of 6 sectors — a
descriptive observation whose persistence is untested.

## Reading — frame-dependence, descriptively

1. **The real frame's ranking is roughly opposite the replay frame's**: the
   replay panel was strongest in ai_chip/datacenter (Sharpe 1.96/2.49) and
   dead in consumer; on this window the LIVE blend's top-k trail the chip
   average (−93.6 bp) and lead the consumer average (+166.0 bp). With
   #937's 0/15 pick overlap, the two systems agree in neither picks nor
   sector ordering — conclusions do not transfer between them.
2. **The pooled edge is positive on this window** (+28.3 bp/5d). Whether
   that reflects real within-sector selection or 37 days of overlapping-
   window noise is exactly what this note cannot decide.
3. **ai_chip is flagged in both frames, for what that is worth**: the
   replay champion was never traded (#937), and on this window the traded
   blend's chip picks sit below the chip average. A 35-day negative edge
   is not evidence of harm — it is a flag for the converged comparison.

## Corrections (visible, per ledger rule 10)

The first push of this note published a table (consumer +150.8 /
industrial +53.4 / software +34.5 / finance +6.4 / datacenter_hw −12.4 /
ai_chip −84.7; pooled +25.1 bp/5d; 38 usable dates; "~92 scored
names/day") derived in an uncommitted scratch session. Codex review could
not reproduce that surface, and neither could this session — the exact
window/dedup/admission combination was not recorded. Those numbers are
**withdrawn**, replaced by the frozen-contract numbers above (same
qualitative shape: consumer/industrial/software positive, ai_chip
negative, pooled positive). The scored-names count is 73.1/day mean
(range 5..94) — the "~92" described full-pass days only.

## What this does not show

37 days cannot support Sharpe-grade claims, a routing decision, or any
statement about selection skill; the horizon is 5d, not the 60d thesis.
This is the real-frame seed table for the converged (decision-C)
comparison once orch#939 lands.
