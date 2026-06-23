# Drift-free (trend-scanning) label trial — REJECTED

STATUS:   merge-pending (PR #176). Research result; trend-scanning REJECTED on the decisive (P&L) test.
WHAT:     a trend-scanning label through the per-regime + placebo WF gate, + 3-seed robustness, a
          label-shuffle/embargo control, and a portfolio-P&L backtest. Full numbers:
          doc/research/2026-06-23-trendscan-label-evidence.md.
WHY-DIR:  neutralization (rejected) left drift-free labels as the next cheap in-repo model lever; triage it.
EVIDENCE: trend-scan beat raw on BULL_CALM placebo-clean IC (3/3 seeds) — BUT that metric is
          untrustworthy (wide shuffled null +0.036±0.046; embargo-gap hypothesis tested & REFUTED).
          The leakage-robust portfolio-P&L test REVERSES it: top-20% selected by trend-scan realizes
          LOWER fwd_60d_excess than raw in EVERY regime incl BULL_CALM (raw +0.134/Sh1.22 vs
          trend-scan +0.099/Sh0.94). `[VERIFIED — gate+seed+shuffle+embargo+portfolio sim]`
NEXT:     drop the cheap-relabeling axis (all 3 levers — neutralization, fundamental-momentum,
          trend-scanning — now fail on P&L). Reallocate model effort to cost/capacity-aware
          CONSTRUCTION (QP sizing by conviction; the 06-23 book was 78% cash, sized backwards), then
          expensive new-data/architecture. NOT a deploy.
