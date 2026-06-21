# Fix time-dependent weekly-apy test (red CI blocking all PRs)

STATUS:   in-progress (bug fix; awaiting Codex review)
WHAT:     makes test_pipeline_alerts_on_persistent_drawdown deterministic — replaces
          hard-coded calendar dates (2026-05-2x) with dates relative to now(), so the
          5-day drawdown fixture always stays inside read_recent_rows' rolling window.
WHY/DIR:  the test ROTTED: read_recent_rows cuts at now-(window_days+1); once wall-clock
          advanced ~31d past the fixed fixture dates, the boundary row dropped (5→4 rows),
          the streak fell below drawdown_days=5, no alert fired, exit_code 0≠3 → red CI on
          EVERY PR (incl. docs-only #158). Pre-existing, unrelated to the model work.
EVIDENCE: fails on origin/main too (assert 0==3, "4 rows / dd_streak=4d"); CI run
          27893674441 job 82541439129. After fix: 7/7 pass locally.
          `[VERIFIED — pytest on origin/main (fail) + on fix branch (7 passed)]`
NEXT:     unblocks repo CI so #158 (and others) can go green; no production code changed.
