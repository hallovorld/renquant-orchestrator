# renquant105 trend-signal recall/precision baseline — model-vs-gate bottleneck

2026-06-27.

## STATUS
Read-only baseline measured. **Primary horizon (fwd_20d/60d) is data-INSUFFICIENT on the
faithful LIVE ledger** — directional only, NOT validated. No canonical path written, no order
placed, no git in the live tree.

## WHAT
renquant105's real goal = catch MORE (recall) + MORE-ACCURATE (precision) multi-period TREND
signals; question = is the bottleneck the MODEL (weak signal) or the GATE (kills recall)?
Measured it READ-ONLY off the now-wired decision ledger `data/runs.alpaca.db` (opened
`mode=ro`, analysed against a `/tmp` copy).

## WHY-DIR
Data-sufficiency gated FIRST, no fabrication. The faithful production cross-section is the
**LIVE** ledger; the **SIM** ledger is NOT faithful (NULL `model_type`/`active_scorer` on every
row, `raw_score` to +270 vs PatchTST's intrinsically-negative scale, 170 distinct mu for 35
names) so it is reference-only. Aged by TRADING SESSIONS (an fwd_Nd label is a shift(-N) bar
label, N sessions ≠ N calendar days).

## EVIDENCE
- **Sufficiency:** live fwd_20d = **11 aged dates** (need ≥30), all in one ~5-week window
  (overlapping 20-session windows ⇒ ~1–2 effective obs); fwd_60d = **0**; fwd_5/10d = 18 each.
  The faithful live ledger began ~2026-05-04 (#133 wiring). → INSUFFICIENT_LIVE_HISTORY.
- **Rank-IC (LIVE, directional) vs 0.036 floor:** fwd_5d +0.017 (BELOW floor), fwd_10d +0.051
  (just above), fwd_20d +0.173 mu / +0.014 raw. The +0.176 headline from the existing
  validator is ~100% SIM-driven (0 live fwd_60d dates).
- **Trend (fwd_20d, book=8, LIVE):** recall_topk **0.245**, recall_quintile 0.326,
  recall_gate 0.183; model-top-8 precision **0.75** positive / 0.44 top-tercile.
- **Gate:** demean `(mu−mean)≥0.03` admits 5.5/54 names/date, **0 admits on 44% of dates**,
  ~15% of mu>0 names. **Killed-winner decomp: missed_by_model 0.755 vs killed_by_gate 0.209**
  ⇒ **MODEL is the dominant bottleneck (~3.6×), GATE secondary.**
- **Staleness:** older IC +0.244 → recent +0.113 (Δ −0.130) — decay sign matches the stale
  train-cutoff, sample too thin to size.
- **Highest-leverage move:** improve MODEL trend RANKING via a fresher-data retrain on a
  multi-day trend label (recall), NOT gate redesign (caps at the 21% slice) nor orthogonal
  alpha. [VERIFIED — `scripts/research_trend_signal_baseline.py` + `validate_conviction_gate.py`
  run read-only over `data/runs.alpaca.db` (mtime 2026-06-26 14:07) at 2026-06-27 ~13:10 PDT;
  5/5 new tests pass.]

## NEXT
Re-run this script once the live ledger ages to ≥30 fwd_20d dates (~mid-Aug-2026) and/or
faithful per-name PatchTST score history with scorer provenance is wired (#133 follow-through),
to convert the directional baseline into a validated one and size the retrain lever. No
production change on this evidence.
