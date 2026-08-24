# GOAL-2 Stage 0: ESS measured — the frozen kill fires

STATUS:   delivered. Stage 1 is NOT run; per the approved design, the kill IS
          the finding.
WHAT:     meta-panel n_eff at h=60 = 0 (14 multi-leg dates, zero labeled;
          first label ~2026-10-27). Re-score-history ceiling = 11 < 12. The
          only viable unlock is a shorter-horizon RE-DESIGN (h=20 reference
          n_eff=34), which is a new estimand and goes back through review —
          not a quiet re-run at a friendlier horizon.
WHY/DIR:  the design ordered ESS before any screen so no result could tempt a
          rule into being frozen around it. A panel accrues ~4 independent 60d
          observations/year — that number decides everything downstream.
EVIDENCE:
  artifact:      doc/research/data/2026-08-24-goal2-stage0/ (script, JSON, log).
  prod or exp:   exp — read-only over the lane DBs.
  existing data: lane coverage enumerated from all runs.alpaca_shadow*.db;
                 labels from ticker_forward_returns [VERIFIED]. The 2024+
                 main-DB history is run_type='sim', single-scorer — it cannot
                 supply multi-leg X without per-leg re-scoring, hence
                 "ceiling", not "available".
  best-known?:   yes — the kill bar was frozen before this measurement ran.
  scope:        research artifact only. GOAL-2 implementation is now BLOCKED
                by design until an operator-visible horizon decision or new
                data; the loop moves to 105 (S3-P2) as the active build.
REVIEW:    codex (haorensjtu-dev).
