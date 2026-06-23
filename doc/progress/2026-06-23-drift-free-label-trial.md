# Drift-free (trend-scanning) label trial — INCONCLUSIVE (harness underpowered)

STATUS:   merge-pending (PR #176). Research result: no demonstrable cheap in-repo edge; harness can't decide.
WHAT:     a trend-scanning label through the per-regime gate + 3-seed robustness + label-shuffle/embargo
          controls + naive AND hardened (embargo+non-overlap+cost) portfolio-P&L. Full record:
          doc/research/2026-06-23-trendscan-label-evidence.md.
WHY-DIR:  neutralization (rejected) left drift-free labels as the next cheap in-repo lever; triage it.
EVIDENCE: every metric disagrees — placebo-IC → trend-scan better (but null is leaky +0.036±0.046,
          embargo hypothesis REFUTED); naive P&L → raw better; HARDENED P&L (90d embargo + non-overlap
          60d rebal + 10bps cost) → a WASH (BULL_CALM raw +0.162/Sh1.80 vs trend-scan +0.114/Sh2.21,
          n=10; ALL tied). With n≈10 + the leakage floor the two are statistically indistinguishable.
          `[VERIFIED — gate+seed+shuffle+embargo+naive&hardened P&L]`
NEXT:     stop adjudicating marginal model levers with this underpowered harness (need the real
          production pipeline + a powered costed backtest). The 3 cheap relabel levers show no
          measurable payoff -> reallocate to CONSTRUCTION (QP sizing by conviction; 06-23 book 78% cash,
          sized backwards = the unambiguous, larger live loss). NOT a deploy.
