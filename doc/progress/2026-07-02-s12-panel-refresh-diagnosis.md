# S12 shadow panel-refresh root-cause diagnosis (docs-only)

STATUS:   diagnosis complete, read-only — no code/config/data/scheduler change,
          no builder or training run. This PR is the memo the merged #212
          design (§3.1/§4) and the #231/H2-roadmap S12 row demand BEFORE any
          shadow retrain/promote work ("diagnosis FIRST: builder-not-run vs
          dropna clip").
REVISION: r1
WHAT:     doc/research/2026-07-02-s12-panel-refresh-diagnosis.md — why the
          PatchTST shadow training corpus `transformer_v4_wl200_clean.parquet`
          ends 2026-02-10. ROOT CAUSE: a ONE-OFF research snapshot — built once
          (embedded bar frontier 2026-05-07; file written 2026-05-18) by a
          recipe that is NOT committed anywhere (no script writes that file;
          the content is an alpha158+fund-family panel — 148 alpha158 + FUND/
          PEAD/SUE/SENT cols — restricted to the 142-name live watchlist with
          labels dropna'd, NOT `transformer_dataset_builder.py`'s raw-OHLCV
          292-ticker output), on NO cadence, never rebuilt since. The fwd_60d
          label-dropna clip is PRESENT but CORRECT (training axis; the trainer
          re-drops NaN labels anyway) — it sets the structural floor, not the
          freeze; this is NOT the #26 serving-axis bug. Gap split as of
          2026-07-01: 141 calendar days total staleness = 86 structural
          (fwd_60d ⇒ achievable frontier 2026-04-06; the daily-refreshed prod
          twin panel demonstrates 2026-04-02) + 55 non-structural (= exactly
          the age of the last build's bar frontier, 2026-05-07 → 2026-07-01).
WHY:      #212 r2 (Codex blocker) makes point-in-time panel refresh the
          PREREQUISITE of the shadow retrain/promote; retraining on the frozen
          panel re-mints 2026-02-10 information under a new trained_date. The
          diagnosis also found THREE binds under which the just-merged chain
          (RenQuant #424 refresh + #419 validated promote, both 2026-07-01)
          STILL cannot unfreeze anything: (B1) the refresh's default builder_fn
          rebuilds the wrong recipe, so its own schema/coverage swap gate
          fail-closes forever; (B2) the promote puts a raw 28d calendar SLA on
          the label-clipped panel axis (structurally ≥ ~86d behind) ⇒
          RC_NOT_FRESH forever even on a fresh rebuild — the #26 failure
          PATTERN recurring inside the new freshness gate, and inconsistent
          with the merged orchestrator #213 monitor which horizon-adjusts by
          the stamped lookahead_days; (B3) the weekly retrain cutoff is pinned
          to the static 2026-06-02 WF source manifest (latest cutoff
          2026-03-09) ⇒ advance-once-then-refreeze. Plus the
          weekly-retrain-patchtst launchd job is still not installed.
DIR:      ownership per #212 §5 — none of the defects is orchestrator-owned
          (orchestrator's build_patchtst_wf_manifest is faithful to its
          source-manifest input; #213's monitor semantics are already correct),
          so this PR is memo-only. Follow-ups scoped in the memo §5, in order:
          (1) base-data/model: commit the TRUE corpus recipe (cheapest correct:
          derive from the daily-refreshed prod alpha158_291 fund panel —
          watchlist subset + label dropna) and point #424's builder_fn at it;
          (2) backtesting/model: horizon-adjust the promote's transformer_panel
          SLA (max(date) + lookahead_days trading days, mirroring #213);
          (3) umbrella ops: derive the weekly LATEST_CUT from the refreshed
          corpus frontier, not the frozen manifest tail; (4) umbrella ops:
          install the launchd plist — cadence last, per §3.1. Landing loop then
          runs `bash scripts/weekly_retrain_patchtst.sh` (umbrella-ops action,
          not an agent's) ⇒ expected served frontier 2026-02-10 → ~2026-04-06
          with the documented ~86d structural lag (the S12 fallback ledge).
EVIDENCE: all read-only, 2026-07-02, enumerated in the memo §6 — corpus scan
          (346,022 rows / 142 tickers / all per-ticker max dates = 2026-02-10 /
          fwd_60d NaN rate 0.0), labels-file scan (bar frontier 2026-05-05,
          max labeled 2026-02-06), prod-twin frontier 2026-04-02 (mtime
          06-30), OHLCV frontiers (142 served names fresh to 07-02; 139/152
          research names frozen at 05-12), NYSE trading-day arithmetic
          (02-10 + 60td = 05-07; 07-01 − 60td = 04-06), launchctl + plist
          listing (no weekly-retrain-patchtst), retrain logs (3 manual runs,
          last 06-16, trained 2024-01-01→2026-03-09 on the 02-10 panel),
          promote source list + source_sla_verdict (28d, no horizon
          adjustment), served pin metadata (trained 2026-05-22, selection
          cutoff 2026-02-10, lookahead_days 60).
NEXT:     open the three follow-up tickets/PRs per DIR (umbrella + base-data/
          model owners); after 1–3 land, umbrella ops runs the landing loop and
          verifies the #213 monitor reads the shadow population healthy with
          the documented structural lag; then install the cadence (#212 §4.3).
