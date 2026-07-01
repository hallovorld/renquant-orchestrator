# model freshness monitor — Phase-1 (observe-only)

STATUS:   shipped for review, round-3 CORRECTED (2026-07-01). Observe-only code (no promotion, no trading impact, no pin
          change). 58 unit tests green on `RenQuant/.venv` python 3.10. Implements Phase-1 (Pillar-1 monitor) of the
          merged design `doc/design/2026-06-30-model-freshness-governance.md` (#210).
          Round-3 note: this module's own round-2 fix keyed the prod panel's freshness axis on
          `max_feature_anchor_date` (the raw feature/data frontier). Codex's round-3 review on umbrella #423 established
          that is WRONG — `max_feature_anchor_date` is data-pipeline-HEALTH provenance only (it can advance by merely
          appending fresh UNLABELED rows, without the labeled training frame / model digest changing at all), so keying
          freshness on it lets a model look fresher with zero actual retraining. This round re-keys the panel axis onto
          `label_observation_cutoff` (the fwd_60d-clipped max LABELED row — the latest information that actually
          affected fitting) and WIDENS the panel fast-axis tiering thresholds by the EXPECTED ~60 business-day
          fwd-label horizon so a genuinely fresh retrain still reads HEALTHY instead of born-BREACH.
          `max_feature_anchor_date` is now captured + echoed as informational/health provenance only, never tiered.

WHAT:     new `src/renquant_orchestrator/model_freshness_monitor.py`, mirroring `weekly_apy_monitor.py`
          (Context dataclass + Pipeline/Job/Task + `main()` + argparse + `--json`). It reports fast-axis freshness for the
          THREE model populations, each keyed on the BINDING DATA CUTOFF (never `trained_date` alone — design §2):
          1. per-ticker tournament `models/<TICKER>/<TICKER>-policy-metadata.json` (binds on `live_train_end`, else
             `trained_date`) — a COVERAGE decision: min/median/max age + missing tickers (missing = fail-closed);
          2. prod panel `artifacts/prod/panel-ltr.alpha158_fund.json` (XGB) — binds on `label_observation_cutoff` (the
             MODEL-FRESHNESS axis, umbrella #423 round-3) if present, else the other `effective_*_cutoff_date` /
             `data_cutoff_date` / `trained_date` fallbacks; the panel policy widens its tiering thresholds by the
             EXPECTED ~60 BD label-horizon lag when that axis binds. `max_feature_anchor_date` (the raw feature/data
             frontier) is captured + echoed as data-pipeline-health provenance only and is NEVER used to tier;
          3. shadow panel (PatchTST) — the artifact referenced by `strategy_config.shadow.json`
             `ranking.panel_scoring.artifact_path`; a `.pt` blob resolves to its `<path>.metadata.json` sidecar and binds
             on `effective_selection_cutoff_date`.
          Fast-axis tiers (design §1/§4): healthy <=14d, warn 14-21d, escalate 21-28d, breach >28d (widened by the
          label-horizon lag when `label_observation_cutoff` binds). Missing / unreadable / cutoff-less artifacts FAIL
          CLOSED to breach. Exit code = worst tier (healthy 0 / warn 1 / escalate 2 / breach 3), mirroring
          `weekly_apy_monitor`'s convention. An ntfy alert fires behind `--notify` (suppressed by `--quiet`).

WHY:      staleness is silent today until the universe zeroes to "0 candidates" (design §1). This makes it OBSERVABLE and
          keys it on the data axis so a fresh retrain against stale data cannot reset the clock. It is deliberately the
          observe-only slice: lowering `model_staleness_days` 60->28 and the best-of-recent fallback stay DEFERRED behind
          the §5 shadow experiment — tightening a gate before a validated remediation path exists is strictly worse.

DESIGN:   PR-#211 lesson applied — "now" is INJECTABLE via `--as-of` (+ a `now` context field) and every window is bounded
          on both sides, so tests are deterministic and never wall-clock-dependent. Shadow `artifact_path` is resolved
          against multiple base dirs (the pinned subrepo config stores it `../../artifacts/...` relative to the DEPLOYED
          umbrella `backtesting/renquant_104/`, not the subrepo `configs/`); first existing freshness JSON wins, else it
          fails closed on a concrete path.

EVIDENCE: `RenQuant/.venv/bin/python -m pytest tests/test_model_freshness_monitor.py -q` -> 58 passed (healthy/warn/
          escalate/breach boundaries, data-cutoff-binds-over-fresh-trained_date, trained_date fallback, missing/no-path/
          cutoff-less fail-closed, blob->sidecar + json shadow resolution, tournament coverage + median + missing,
          full-pipeline healthy/breach, `--json` determinism, `--as-of` bounded both sides, promote-receipt gate matrix,
          and the round-3 panel axis correction: `label_observation_cutoff` binds + tiers with the widened
          label-horizon threshold, `max_feature_anchor_date` no longer binds and is provenance-only, and appending a
          fresher `max_feature_anchor_date` to an otherwise-frozen panel does NOT improve the reported freshness
          (`test_fresh_unlabeled_rows_do_not_improve_panel_freshness`, mirroring umbrella #423's own regression test).
          Read-only smoke against the live umbrella tree (`--as-of 2026-06-30`, pre-#423 stamping — the live prod
          artifact has not yet acquired `label_observation_cutoff` / `max_feature_anchor_date` via a retrain), exit 3 /
          worst=BREACH:
          - tournament: 142/142 present, age min/med/max = 7/7/7d  -> healthy (post emergency retrain);
          - prod-panel: `trained_date=2026-05-18` age 43d (trained_date fallback — no data-cutoff field yet) -> breach;
          - shadow-panel: `effective_selection_cutoff_date=2026-02-10` age 140d -> breach.
          The monitor only READS the umbrella tree; it never writes/git it.

SCOPE:    observe-only. NOT wired into `scheduled_jobs.py` or `job_runner.py` (no install). No change to any model, pin,
          config, or the daily run. Slow-axis quarterly-fundamentals SLA (design §2, already covered by the pipeline's
          `P-FUND-FRESHNESS`) is intentionally out of this Phase-1 fast-axis slice.

NEXT:     (proposal — do NOT install here) once reviewed, register a DAILY invocation:
          - add to `job_runner.py` `_MODULE_JOBS`:
            `"daily_model_freshness_monitor": "renquant_orchestrator.model_freshness_monitor"`
          - add a `ScheduledJob(job_id="daily_model_freshness_monitor", kind="ops", cadence="daily",
            command=["renquant-orchestrator", "run-job", "daily_model_freshness_monitor", "--", "--notify"],
            owner_repo="renquant-orchestrator", production_safe=True,
            umbrella_state_dependency="RenQuant renquant_104 model artifacts")` in `scheduled_jobs.py`.
          Follow-ons (separate PRs, per design): Pillar-2 tournament-timeout cadence repair; WF-gate repair so the strict
          path re-validates the active primary; then the §5 shadow experiment that authorizes the 28d/10d ceiling and the
          best-of-recent fallback.
