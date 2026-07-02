# A-1 λ dose-response sweep — research PR (valuable NULL)

STATUS:   research evidence (read-only; script + JSON + memo).
REVISION: r1.
WHAT:     pre-enable evidence for RS-2's A-1: drive the real pipeline QP solver on the
          latest two full runs' (mu, σ) with cash_drag_lambda ∈ {0…0.10}. RESULT: solutions
          IDENTICAL at every λ — turnover pinned at exactly the 0.30 cap; the turnover
          constraint binds before the cash-drag penalty can act.
WHY/DIR:  revises #231 S6's Δ-expectation: A-1's deployment contribution ≈ 0 (enable stays
          harmless per RS-2); the deployment AC rests entirely on lane B. New design finding
          flagged for the S6/S7 implementation PR: the QP turnover cap counts CASH-DEPLOYMENT
          as churn, so a 75%-cash book needs multiple sessions to redeploy regardless of
          conviction/top_n/λ — whether deployment legs should be cap-exempt is a risk-gate
          design question (not decided here; the sleeve makes loosening unnecessary).
EVIDENCE: committed JSON; one-command reproduce; caveats stated (w_current approximation,
          simplified constraints; the flat-at-every-λ + cap-exactly-binding pattern is
          structural).
NEXT:     Codex review; the S6/S7 implementation PR cites the turnover-cap finding; the
          in-pipeline shadow sweep (S6 AC) remains the decisive enable gate.
