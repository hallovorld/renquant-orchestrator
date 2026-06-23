# Drift-free (trend-scanning) label trial

STATUS:   merge-pending (PR #176). Bounded INTERIM research result; NOT a deploy decision.
WHAT:     a trend-scanning label through the per-regime + placebo WF gate (+ 3-seed robustness +
          label-shuffle control). Full numbers: doc/research/2026-06-23-trendscan-label-evidence.md.
WHY-DIR:  neutralization (rejected) left drift-free labels as the next cheap in-repo model lever.
EVIDENCE: trend-scan beats raw on BULL_CALM placebo-clean in 3/3 seeds and is more stable, BUT the
          label-shuffle control exposes a SHARED wide+mildly-positive null (shuffled ALL-IC +0.036
          ± 0.046; my embargo-gap hypothesis was TESTED and REFUTED — a 90d embargo leaves it at
          +0.0367, cause undetermined) -> absolute IC NOT trustworthy; only the relative result +
          placebo-clean DIFFERENCE survive (see research doc). `[VERIFIED — gate+seed+shuffle+embargo-test]`
NEXT:     establish the empirical multi-shuffle null + re-measure against it; run full production WF
          sanity; then a SIM (the decisive test — P&L doesn't depend on the IC null). NOT a deploy.
