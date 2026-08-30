# Retrain freshness guard: presumed-delisted non-watchlist names are excluded with an alert, not a veto (AVB, the IAC pattern)   (PR #TBD)

STATUS:    delivered (code + tests; NOT deployed — the `-run`/pin advance is the deploy step, see "Deploy")
WHAT:      `PanelUniverseFreshnessGuardTask` now classifies a stale panel name as
           `presumed_delisted` when its newest bar is more than 3 exchange sessions
           behind the expected session AND it is not in the served watchlist; such
           names are excluded from the freshness-guarded universe with a WARNING,
           a non-fatal ntfy alert and a persisted report line instead of vetoing
           the retrain. Served names keep the strict 0.0 rule; >2% presumed is
           refused as a mass outage; the report is persisted to disk.
WHY/DIR:   The strict 0.0 stale fraction assumed delistings reach the versioned
           inventory, but the inventory ships NO `delisted_tickers` channel
           (gitignored, generated 2026-05-05). Every real delisting therefore
           vetoed the weekly promote until an operator hand-edited an exclude list
           (IAC in July; AVB now), and the served panel model could not be
           refreshed inside the RFC#210 28-day SLA. This closes the
           "unsatisfiable gate" class for delistings (serving-reliability AC1).
EVIDENCE:  see §4(b) block below.
NEXT:      deploy = advance the orchestrator pin / sync the `-run` checkout after
           merge (operator-authorized landing action); the next weekly promote
           then proceeds past AVB. Regenerating the inventory with a
           `delisted_tickers` channel (base-data) remains the versioned fix.

## Bottom line

- The 2026-08-29/30 weekly promote FAILED at the freshness guard:
  `PANEL-FREEZE 1/293 stale` — the one name is AVB (Equity Residential merger
  closed 2026-08-17, last bar 2026-08-24) `[VERIFIED — prior work, caller's
  findings for this task; promote log]`. AVB is in `tier_A_tickers` of the live
  inventory and NOT in the served watchlist
  `[VERIFIED — python json read of data/transformer_universe_inventory.json
  (nA=258, nB=36, generated 2026-05-05) and renquant-strategy-104/configs/
  strategy_config.json (watchlist n=145), 2026-08-30]`.
- Same pattern as IAC (bars ceased 2026-05-12): the umbrella's
  `scripts/weekly_wf_promote.sh:404` hard-codes
  `RETRAIN_EXCLUDE_TICKERS="${RENQUANT_RETRAIN_EXCLUDE_TICKERS:-IAC}"`
  `[VERIFIED — read-only grep of the umbrella script]`. The inventory has no
  `delisted_tickers` / `inactive_tickers` / `retired_tickers` key, so the
  guard's designed exclusion channel (`_INVENTORY_DELISTED_KEYS`) is empty
  `[VERIFIED — same json read; keys listed]`.
- Consequence without this PR: the served panel model (trained 2026-08-02)
  lapses the 28-day RFC#210 SLA on Mon 2026-08-31 `[DERIVED — 08-02 + 28d;
  training date from the caller's findings]`.

## What changed (`src/renquant_orchestrator/retrain_alpha158_fund.py`)

1. **Classification** (`PanelUniverseFreshnessGuardTask.run`): after the
   existing stale/missing/future bucketing and BEFORE the fraction gate, a
   stale name is `presumed_delisted` iff
   `lag > max(presumed_delisted_after_sessions, freshness_stale_after_days)`
   (default 3; a name must already be stale — a widened per-run stale
   tolerance can never make a lagging name look delisted) AND the name is not
   in the served watchlist. Missing-file and future-dated bars are never
   presumed delisted (integrity failures stay integrity failures).
2. **Served watchlist** (`_resolve_served_watchlist`): `ctx.served_watchlist`
   (explicit, tests/pins) else the `watchlist` array of
   `ctx.served_watchlist_path` — default `ctx.strategy_config`, the SAME
   config this retrain passes to `train_gbdt` (`TrainGbdtScorerTask`), i.e.
   the config the produced artifact is fingerprinted against. Unavailable /
   unreadable / empty watchlist ⇒ classification DISABLED (fail-closed: with
   no served set, "not served" would match every stale name) and the strict
   rule applies to everything, exactly as before.
3. **Mass-outage refusal**: presumed fraction > `presumed_delisted_max_fraction`
   (default 0.02 ≈ 5 of 293) ⇒ nothing is excluded, the names stay stale, the
   strict gate trips with `presumed-delisted REFUSED as mass outage` in the
   PANEL-FREEZE alert, and the refusal (names, fraction, cap) is in the report.
4. **Not a veto**: excluded names leave the guarded universe
   (`n_active_universe`); the stale fraction is computed over the active set.
   A WARNING line (`freshness guard PRESUMED-DELISTED: …`), the run-summary
   `freshness guard OK … presumed_delisted=N [names]` line, and an ntfy
   alert titled `RenQuant retrain PRESUMED-DELISTED` (via the module's
   existing `post_ntfy` = `renquant_common.notify.send`, suppressed by
   `--quiet` like the other alerts) tell the operator to make it versioned
   (inventory `delisted_tickers` or `RENQUANT_RETRAIN_EXCLUDE_TICKERS`).
5. **Persistence** (`_persist_freshness_report`): the full `freshness_report`
   is written atomically to `<repo_dir>/logs/daily_retrain_alpha158_fund/
   freshness_report.<expected_session>.json` plus `freshness_report.latest.json`
   (the wrapper's own log dir) BEFORE the verdict, so a vetoed run leaves a
   record too and the next run / the ops drift scan can read the
   presumed-delisted set without parsing a log. `--freshness-report-out`
   overrides (directory, or a `.json` path used as `latest`). Unwritable ⇒
   raises (fail-closed). New report fields: `n_active_universe`,
   `n_presumed_delisted`, `presumed_delisted_fraction`,
   `presumed_delisted_names` (`{ticker: {lag_sessions, last_bar}}`),
   `presumed_delisted_after_sessions[_effective]`,
   `presumed_delisted_max_fraction`, `presumed_delisted_refused`,
   `served_watchlist` (source/status/n), `persisted_to`. `ctx.presumed_delisted`
   and `panel_universe_provenance["presumed_delisted_excluded"]` carry the set
   in-process. Non-default knobs land in `overrides` like the existing ones.
6. **CLI**: `--presumed-delisted-after-sessions` (3),
   `--presumed-delisted-max-fraction` (0.02), `--served-watchlist-file`
   (object with `watchlist` or a plain list), `--freshness-report-out`.
   `--exclude-tickers` (the IAC bridge) is unchanged and still prunes BEFORE
   classification.

Scope honesty: "excluded from the training universe" means excluded from the
freshness-GUARDED universe — the same effect `--exclude-tickers IAC` has
today. The panel build is base-data's (`alpha158_qlib_panel.LoadUniverseJob`
reads `tier_A|tier_B` from the inventory itself and ignores delisted keys
`[VERIFIED — grep renquant-base-data/src/renquant_base_data/alpha158_qlib_panel.py:246]`),
so a presumed-delisted name still contributes its last bars to the panel, as
IAC has since July. Removing it from the panel is the inventory regeneration.

## §4(b) evidence

- Tests (`tests/test_retrain_ohlcv_coverage.py`, new section
  "presumed-delisted"): AVB-like (4 sessions behind, not served) ⇒ excluded +
  WARNING + one `PRESUMED-DELISTED` alert + run proceeds; lag 2 and lag 3
  (boundary) not served ⇒ still stale ⇒ FAIL; lag 1 ⇒ neither; served name 10
  behind ⇒ FAIL; 3/100 presumed (3% > 2%) ⇒ refused ⇒ FAIL with the refusal
  recorded; 2/102 under the cap ⇒ both excluded; missing file alongside a
  presumed name ⇒ FAIL (missing never presumed); unavailable / empty served
  watchlist ⇒ classification disabled ⇒ FAIL; watchlist read from a strategy
  config file (served stale name vetoes, non-served excluded); plain-list
  file; effective horizon = max(stale, delisted); `--exclude-tickers IAC`
  still prunes alongside a presumed AVB; overrides recorded; report persisted
  (dated + latest, no `.incoming` left) incl. on a veto; `--freshness-report-out`
  as `.json` and as a directory; CLI defaults/flags.
  Pre-existing guard tests keep their semantics: `_ctx` now defaults
  `served_watchlist=[]` (explicitly empty ⇒ disabled) so they stay
  deterministic instead of reading the operator's live strategy config.
- Targeted run: `tests/test_retrain_ohlcv_coverage.py tests/test_retrain_alpha158_fund.py
  tests/test_market_calendar_repoint.py tests/test_retrain_sigma_head_rawlabel.py
  tests/test_scheduled_jobs.py` ⇒ **159 passed** `[VERIFIED — pytest, 2026-08-30]`.
- Full `make test` (sibling-src PYTHONPATH, umbrella venv):
  clean `origin/main` (b76a5b25) worktree ⇒ **6 failed / 7066 passed / 10 skipped**;
  this branch ⇒ **6 failed / 7085 passed / 10 skipped** (+19 = the new tests;
  the SAME 6 failures: `test_cli::test_parking_sleeve_cli_computes_allocation`,
  2× `test_g2v3_stage_i2_binding`, `test_goal3_public_export_resolution`,
  2× `test_shadow_serving_skips_leave_evidence` — pre-existing, unrelated,
  they read paths/records on the operator's disk)
  `[VERIFIED — scratchpad baseline_test.log / branch_test.log, 2026-08-30]`.
  `ruff check` on the two changed files reports the same 2 pre-existing
  unused-import findings as origin/main; none introduced.

## Deploy

- Nothing here touches a live path: the change is in the orchestrator's
  pinned module. `weekly_wf_promote.sh` (umbrella) needs NO change once this
  lands in the pinned orchestrator — it already calls
  `daily_retrain_alpha158_fund.sh` → `retrain_alpha158_fund` with defaults;
  the new flags default on. Its `RETRAIN_EXCLUDE_TICKERS=IAC` keeps working
  and can be dropped later (IAC would then be presumed delisted instead).
- The deploy step is the `-run` checkout sync / orchestrator pin advance
  (landing action ⇒ operator authorization per the LONG ledger). Until then
  the live weekly promote still runs the old guard and still vetoes on AVB.
  Interim operator bridge, if needed before the pin advance:
  `RENQUANT_RETRAIN_EXCLUDE_TICKERS=IAC,AVB` on the promote invocation (the
  existing designed bridge; no code change).

## Memory tier

MID `doc/memory/mid-term/serving-reliability.md`: addendum under AC1
("no unsatisfiable gate") recording the delisting class and this fix.
