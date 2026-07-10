# Progress — first systematic evaluation of the 105 Stage-1 shadow data

**Date:** 2026-07-10
**PR:** research memo only (no code, no config, no live-path change). EXPLORATORY.

## What

First systematic read of the renquant105 Stage-1 observe-only shadow corpus
(quote logger + entry-timing shadow arms + paired-arrival records, 2026-07-02 →
07-10) against roadmap P4 (execution-quality residual). Deliverable:
`doc/research/2026-07-10-105-shadow-execution-timing-first-eval.md` + evidence
JSONs and the analysis script under `doc/research/evidence/rq105_first_eval/`.

## Headlines

- Inventory: 6 sessions, 271,904 accepted quote samples, 145 tickers, stable 60 s
  cadence, no intra-session outages.
- DQ-1: clock-skew censoring (`future_quote`, median skew −0.054 s) discards 12.7%
  of samples, concentrated in the MOST liquid names (~72% of SPY). Cheap fix
  recommended (negative-age tolerance).
- DQ-2: IEX top-of-book spread is not NBBO for 95/145 names (median "spreads"
  50–1,012 bps); spread-cost work restricted to a 45-name tight subset, where
  half-spread is 4.7 bps (first 25 min) vs 1.4–1.6 bps midday/close.
- No stable entry-window edge vs the current next-open-fill convention:
  SPY-adjusted window medians −26…+7 bps, IQR ~±100 bps, per-session sign flips.
  Recent 21 actual buys: overnight slip mean −49.5 bps (favorable) — no bleeding
  entry in this window; consistent with the S10 memo.
- Honest bound: 10 bps/entry ≈ $124/yr at current sizes (mean buy $496,
  ~250 entries/yr).
- P4-critical gap: `paired_is.jsonl` has 0 both-arm fills (all censored
  `no_batch_fill`) — batch-arm fill capture must be wired before any
  execution-quality verdict.

## Memory tier touched

SHORT-tier finding only (exploratory memo + VERDICTS.md FINDING row); no LONG
agreement changed.
