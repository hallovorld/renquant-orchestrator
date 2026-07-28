# Progress: shadow staleness horizon design memo (PR #588)

STATUS:   delivered (design memo only, no code change). Operator decision between
          Option A (two-axis, recommended) and Option B (single-axis) still pending.

WHAT:     Adds `doc/research/2026-07-28-shadow-staleness-horizon-design.md`. Documents that
          the shadow-health/sentinel staleness gate (`shadow_health.py::finalize_shadow_health`,
          28-calendar-day limit measured off `effective_train_cutoff_date`) cannot structurally
          be passed by any fwd60-label model: a 60-TRADING-day label horizon alone floors the
          calendar-day cutoff lag at ~82-91 days by construction, well above the 28d bar. Round 2
          of review corrected an imprecision in the first draft's Option A: the draft summed
          `label_horizon + embargo + slack` as three independent terms (-> 118d), but this
          codebase's own splitter (`kernel/walk_forward_splits.py:71,76`) sets its embargo window
          EQUAL to the label horizon, not additive on top of it — the draft was double-counting
          the same quantity under two names. Fixed to state units explicitly (label horizon is
          TRADING days per `infer_label_lookahead_days`; `staleness_days` is CALENDAR days per
          `shadow_health.py:324`), name the trading->calendar conversion call site
          (`pd.offsets.BDay`, matching `kernel/walk_forward_splits.py:95`), and relabel the
          worked total (~112d) as ILLUSTRATIVE ONLY, not an executable gate constant, pending an
          implementation PR that pins the exact stamped field and slack default.

WHY/DIR:  Two remediation options for a future renquant-pipeline implementation PR (this PR
          ships no code): Option A (recommended) — two-axis check, `trained_date` age AND
          horizon-aware `cutoff_lag`; Option B (minimal) — single `trained_date` axis, blind to
          frozen-cutoff regressions (the fund-freshness bug class already seen once). Until the
          operator decides, the `stale_91d` flag on the clf lane stays: correctly reported, known
          benign, documented here rather than silently suppressed.

EVIDENCE: `tail -5 backtesting/renquant_104/logs/shadow_scorer_health.jsonl` (read-only, checked
          2026-07-28) confirms the memo's central empirical claim: run_date 2026-07-28,
          `effective_train_cutoff_date=2026-04-28`, `staleness_days=91`,
          `reasons=["stale_91d_limit_28d"]`, `status=fault` for the topdecile_clf lane, and
          `staleness_days=622`, `reasons=["stale_622d_limit_28d"]` for the legacy lane (both
          numbers cited in the memo's table and Option A section match this log exactly)
          `[VERIFIED — direct log read]`. The memo's second table row (PatchTST fold cutoff
          2025-12-05) is asserted from the training corpus build record and was not
          independently re-verified against a live shadow-health record in this fix pass
          `[GUESS — not re-checked]`; no model/IC/Sharpe number is claimed anywhere in the memo,
          so the §4(b) sanity-triad block does not apply.

NEXT:     Operator picks Option A or Option B. If A: a follow-up renquant-pipeline PR reads the
          artifact's stamped `lookahead_days` (per-recipe precedent already shipped in
          `doc/progress/2026-07-02-per-recipe-freshness-horizon.md` — fail closed if
          absent/invalid, never hardcode 60), converts trading->calendar via `pd.offsets.BDay`,
          and implements the two-axis check with an explicit, reviewed slack constant — not the
          illustrative figure in this memo.
