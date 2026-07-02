# S10 open-auction IS study — research PR

STATUS:   research evidence (read-only; script + JSON + memo; no code/config/broker change).
REVISION: r1.
WHAT:     task S10 (#231 Term EXEC): `scripts/s10_open_auction_is_study.py` upgrades POC-C to
          a formal verdict — TRUE 10-min VWAP references where coverage exists (20/41 fills;
          OHLC4-labeled fallback after 2026-05-01), date-clustered block bootstrap (5,000
          resamples, 18 independent days), and an explicit verdict block.
WHY/DIR:  the #230 §8 S10 row required the prize to be CI'd, not asserted. Result:
          fill≈open re-confirmed (−4.6 bps, median 0.0); prize vs same-day VWAP **+40.1 bps
          mean / +16.2 median, CI95 [−15.6, +99.2]** → **MATERIAL-BUT-UNPROVEN** (4× the
          10 bps bar at point estimate; CI includes 0 at N_days=18). Days-to-significance
          ≈38–40 → the N1 collector corpus is the binding step. Right-skew (median ≪ mean)
          feeds the §9.4 estimand choice (median/trimmed IS). G105 kill branch NOT triggered.
EVIDENCE: committed JSON with per-fill rows + ref_kind labels; reproduce with one command
          (script docstring). Read-only inputs: Alpaca closed orders, data/ohlcv,
          data/intraday 10min bars.
NEXT:     Codex review; collector corpus accrues N_days; the §9.4 prereg consumes the skew
          finding; re-run the script monthly (same command) as the standing EXEC-term metric.
