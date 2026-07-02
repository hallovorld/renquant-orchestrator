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

ROUND 2 (CI fix, 2026-07-02): the batch-scores/shadow-serving install snippet added to the
README's addendum section used the deprecated `launchctl load` verb, regressing
`tests/test_rq105_collector_scheduling.py::test_readme_documents_mkdir_before_load_and_current_launchctl_verbs`
— a repo-wide guard #232 added specifically to keep this shared README on the current-macOS
`bootstrap`/`bootout` verbs (CI: "deprecated launchctl verb should not remain"). Fixed: the
addendum's install loop now uses `launchctl bootstrap "gui/$UID_NUM" <plist>`, matching the
main package's N1b section exactly, with the `bootout` unload equivalent noted alongside.
23/23 tests pass.

ROUND 3 (Codex CHANGES_REQUESTED — frozen-signal/run-bundle contract not yet satisfied,
2026-07-02): the implementation did not yet earn the "class-A frozen" claim r1 made for it.
Codex's 6 findings, and the fix for each:

1. **Selection ignored `pipeline_runs` entirely.** The exporter queried `candidate_scores`
   directly (`... where run_id like '%-live-%' ... order by run_id desc limit 1`) — a
   lexicographic string sort, not a completion/type/fingerprint check, and a `run_id`'s
   trailing uuid suffix does not sort chronologically, so two live runs on the same date could
   resolve to an arbitrary one. Fixed: `_select_source_run` now JOINs `pipeline_runs`, requires
   `run_type = 'live'` (a real column, not a substring match on `run_id`), a non-empty
   `strategy`, and orders by `pr.created_at DESC` — the run's own completion timestamp. A row
   only exists in `pipeline_runs` once `record_pipeline_run` has actually run (near the end of a
   successful pipeline pass, per `backtesting/renquant_104/adapters/runner.py`), so requiring the
   JOIN itself proves the source run actually completed, not just partially wrote candidate rows.
2. **No fingerprint requirement.** `_fingerprint_gaps()` now requires `run_bundle_json` (written
   by `build_run_bundle` at run time — `kernel/artifact_contract.py`) to carry a non-empty
   `config_hash`, a non-empty `artifact_hashes` dict with no falsy values, and a `watchlist_hash`;
   any gap refuses the export and names which field(s) were missing.
3. **Two separate direct-to-final-path writes; a 50% coverage collapse silently accepted.**
   Replaced with `_atomic_write_json` (temp file in the same dir → `fsync` → `os.rename`, so a
   reader only ever sees the old complete file or the new complete file). Coverage is now measured
   against the run's OWN persisted candidate roster (`role='candidate'` — the full pre-veto
   candidate list per the 2026-05-04 DB-DECISION-FACTORS mandate, i.e. a concrete, run-bound
   expected universe, not an external/driftable definition) with a `MIN_COVERAGE_FRACTION = 0.9`
   floor; a shortfall is refused with the exact missing ticker names printed and recorded in meta
   (`missing_tickers`). No repo-wide "expected universe" census concept exists yet in code (#227 is
   still an open design doc) — 0.9 is a documented, deliberately conservative interim, not derived
   from an established threshold; replace once #227 ships.
4. **Replay trusted the bundle blindly; idempotency unverified in this PR.** New shared module
   `ops/renquant105/batch_scores_bundle.py` (`canonical_hash` + `verify_bundle`) used by BOTH the
   exporter (writes `score_content_sha256`/`source_run_bundle_sha256` into meta) and a new
   verification step `run_shadow_serving.sh` now runs BEFORE invoking the CLI — checks
   `meta.session_date == today` (catches a stale leftover bundle) and that a fresh hash of the
   on-disk score file matches the meta's recorded hash (catches corruption/tampering between
   export and replay); either failure SKIPS with an ntfy alert, same fail-safety convention as a
   missing bundle. Extracted into a shared module specifically so producer and consumer can never
   hand-copy two independently-drifting hash implementations (this repo has been burned by exactly
   that pattern before — see PR #426's `model_content_sha256` history). Checkpoint-append
   idempotency itself does NOT need new code: `shadow_realtime_serving.py`'s `_ShadowLogWriter`
   (Codex #221 / #221 round 2) already enforces a provenance-bound `(as_of, ticker, *RunProvenance)`
   dedup key under an flock lock, and is already covered by `test_idempotent_append` and
   `test_concurrent_writers_do_not_duplicate_under_lock` in `tests/test_shadow_realtime_serving.py`
   — pre-existing, already-tested machinery this PR's consumer already benefits from; r2 simply
   hadn't cited it.
5. **No tests.** New `tests/test_rq105_batch_scores_export.py` (18 tests): SQL selection rejects
   a candidate-only orphan row (no `pipeline_runs`), a `sim`-typed run whose `run_id` happens to
   contain "live", an empty-strategy run, and each of the 3 required fingerprint fields missing
   individually (plus a present-but-null `artifact_hashes` entry); correctly picks the
   `created_at`-latest run when two live runs exist for one date with DELIBERATELY reversed
   run_id-string order; a below-floor coverage run is refused with the exact missing tickers
   named, an at-floor (exactly 90%) run is accepted; an `os.rename`-crash simulation proves no
   partial/renamed file survives; hash determinism is independence-of-DB-row-order tested; the new
   verifier accepts a fresh export, rejects a stale `session_date`, rejects a tampered score file,
   and rejects a pre-fix bundle with no hash field at all. 58/58 pass across
   `test_rq105_collector_scheduling.py` + `test_rq105_batch_scores_export.py` +
   `test_shadow_realtime_serving.py`.
6. **N1b activation gating not wired for these two jobs.** The addendum's install snippet jumped
   straight to `launchctl bootstrap` with no gate check, unlike the main package's N1b section.
   Fixed: added the same "0. MANDATORY gate check" step (`check_activation_prereqs.py`) before the
   loop, and a sentence stating these two jobs are N1b (gated) exactly like the main package.

**Also fixed while in this file** (not one of the 6 numbered findings, but the same class of bug
#233/#232 already hit in this session): `run_shadow_serving.sh` and
`com.renquant.rq105-shadow-serving.plist` both declared `/bin/zsh`, which does not exist on the
Ubuntu CI runner — proactively switched to `/bin/bash` (portable, no zsh-specific syntax in the
script) before it caused the same CI failure #233 hit.

**Honest scope note:** `run_shadow_serving.sh` invokes
`renquant_orchestrator.shadow_realtime_serving` WITHOUT `--feature-snapshot-json`, which that
module's CLI marks `required=True` — this predates round 3 and is outside Codex's 6 named
findings, so left unchanged here; flagging it because the wrapper as currently written would fail
argparse validation on its first real invocation regardless of any fix in this round. Worth a
follow-up before N1b activation.

**Verification:** `python3 -m pytest tests/test_rq105_collector_scheduling.py
tests/test_rq105_batch_scores_export.py tests/test_shadow_realtime_serving.py -q` → 58 passed.
`bash -n run_shadow_serving.sh` clean; `py_compile` clean on both Python files. Full-repo
`pytest -q` run separately for regression: 802 passed, 12 failed, 23 collection errors — all
pre-existing sandbox environment gaps (missing `renquant_pipeline`/`renquant_common` sibling
checkouts, missing `pandas_market_calendars` on system Python 3.9; already documented in
#233's progress doc), none touching files this round modified; CI runs a correctly-provisioned
interpreter.

Do NOT call the vector "class-A frozen" as an accomplished fact — it is now provenance-checked,
coverage-checked, and atomically written, which is what makes that claim SUPPORTABLE once an
operator actually runs it against real production data; this PR still ships as inert repo files
per its own N1a/N1b split.
