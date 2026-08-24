# GOAL-2 Stage 0: ESS measured — the frozen kill fires

STATUS:   delivered. Stage 1 is NOT run; per the approved design, the kill IS
          the finding.
WHAT:     meta-panel n_eff at h=60 = 0 (14 multi-leg dates, zero labeled;
          first label ~2026-10-27). Re-score-history ceiling = 1 < 12.

          REVISED 2026-08-24 (codex review): the ceiling was first computed on
          EVERY candidate_scores row with a panel score, which counted 560 SIM
          dates from runs.alpaca.db alongside its 90 live ones and reported the
          result as a 104 re-score history. It was not one. score_dates() now
          filters run_type='live' AND non-empty strategy — the same selection
          intraday_session_inputs and export_batch_scores.py already use — and
          the artifact records what was rejected (74 selected / 560 excluded /
          634 before filter), the run_id count, and a digest of the selected
          (run_date, run_id) rows so the number survives a growing DB.

          Corrected ceilings, live-only: h=60 -> 1 (was 11), h=20 -> 4 (was
          34). The direction was always conservative — filtering removes rows,
          so an audited ceiling can only fall — but the magnitude changes how
          the result reads, and it removes the exit the first revision named:
          h=20 is now ALSO below the bar, so a shorter-horizon re-design is
          still a new estimand needing its own review AND no longer a ready
          unlock on audited data.
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
