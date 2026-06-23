# Drift-free (trend-scanning) label trial

STATUS:   merge-pending (PR #176). Bounded INTERIM research result; NOT a deploy decision.
WHAT:     a trend-scanning label through the per-regime + placebo WF gate (+ 3-seed robustness +
          label-shuffle control). Full numbers: doc/research/2026-06-23-trendscan-label-evidence.md.
WHY-DIR:  neutralization (rejected) left drift-free labels as the next cheap in-repo model lever.
EVIDENCE: trend-scan beats raw on BULL_CALM placebo-clean in 3/3 seeds and is more stable, BUT the
          label-shuffle control exposes a wide leaky null (a SHARED ~30d-embargo-gap floor, also in
          scripts/walk_forward_sanity.py) -> absolute IC NOT trustworthy; only the relative result +
          placebo-clean DIFFERENCE survive (see research doc). `[VERIFIED — gate+seed+shuffle]`
NEXT:     fix the gate embargo (>= label horizon) + multi-shuffle null, re-measure, then full WF
          sanity + a SIM before any retrain/deploy.
