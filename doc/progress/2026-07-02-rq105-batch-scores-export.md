# rq105 batch-scores export + shadow-serving scheduling — ops PR

STATUS:   ops scaffolding for review (repo files only; nothing installed/executed by this PR —
          landing stays with the operator/lander per the direction-loop charter).
REVISION: r1.
WHAT:     resolves #232's open item #1 — the missing producer for
          `shadow_realtime_serving --batch-scores-json`. Adds to `ops/renquant105/`:
          `export_batch_scores.py` (06:15 PT: latest pre-session FULL run's panel_score
          vector from runs.alpaca.db → `data/rq105/batch_scores_<date>.json` + meta with
          run_id/score_kind; refuses <40 scored names; writes only the dedicated data/rq105/
          path), `run_shadow_serving.sh` (13:45 PT: deterministic post-close replay at 4
          fixed ET checkpoints, DST-correct via zoneinfo; SKIPS with ntfy if no export —
          never serves a stale vector silently), two launchd plists, README addendum.
WHY/DIR:  #231 N1 / Term EXEC — the 4th Stage-1 collector (#221 shadow real-time serving)
          was unschedulable without a frozen-batch-score producer; the frozen (class-A, #208
          §6) signal for session T is the prior session's 13:55 PT full run, which is exactly
          what the exporter selects (run date strictly < today, ≥80 candidate rows).
EVIDENCE: shadow_realtime_serving CLI verified (--batch-scores-json flat map +
          --batch-run-id + single as-of with tick-feed censoring); candidate_scores carries
          panel_score per full run; #232 merged (ops dir + install pattern established).
NEXT:     Codex review; lander installs the two plists (README addendum); with all four
          collectors scheduled, the N1 AC clock covers the full Stage-1 corpus.
