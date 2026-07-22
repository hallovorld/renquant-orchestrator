# GOAL-5 AC1: rq104 shadow-scorer sentinel

STATUS: delivered (monitor + tests + reviewed manifest/plist; operator installs)

WHAT: `ops/renquant104/rq104_shadow_scorer_sentinel.py` — a scheduled sentinel
that watches the SHADOW panel scorer (PatchTST / `hf_patchtst`) for the silent
fail-soft death no gate catches. Mirrors `rq104_degradation_sentinel.py`:
`liveness_common.alert` ntfy path, NYSE session-day gating, read-only DB access
(`mode=ro&immutable=1`), whole-past-session anchoring (no after-hours
false-positive window). Alarms on three silent-degradation conditions, each
anchored to `>= N` (default 2) consecutive session days and MUTUALLY EXCLUSIVE
(at most one fires per window):

  a. LOAD FAILURE — live runs happened and shadow health signal exists, but the
     shadow scorer did not load / produced 0 scores (and the pipeline did not
     flag the non-load as by-design). The incident class.
  b. NOT ACTIONABLE / DEGRADED — the shadow loaded and scored, but its output is
     not trustworthy: the pipeline health record flags `actionable=false` (stale
     train-cutoff, low coverage, missing provenance), or — on the DB fallback —
     the derived staleness / coverage breach the same thresholds. Also catches a
     MIXED window (e.g. one load-fail + one stale day) so there is no silent gap.
  c. FEED DARK — live runs happened but NO shadow health signal exists at all
     from EITHER source (no record AND no collected scores): the whole feed went
     dark; nothing is being persisted to evaluate.

Thresholds are env-configurable and default to the pipeline record's own
(`RQ104_SHADOW_STALENESS_MAX_DAYS`=28, `RQ104_SHADOW_COVERAGE_FLOOR`=0.80,
`RQ104_SHADOW_STREAK_N`=2, plus `RQ104_SHADOW_NAME`, `RQ104_SHADOW_DB`,
`RQ104_SHADOW_HEALTH_JSONL`, `RQ104_STRATEGY_DIR`).

WHY/DIR: GOAL-5 P0 week-1 (silence != health / deployed-but-dark). The shadow
PatchTST scorer — a G4-critical data feed — silently could not load its artifact
and nothing alarmed, because shadow-scorer failure is fail-soft (a log warning,
not a gate). The liveness checkers prove the job ran; the degradation sentinel
watches the LIVE buy path. Neither looks at whether the SHADOW scorer loaded and
scored. This one looks; AC1 target = detection within one session.

READER — pluggable, and WIRED to the concrete pipeline sink (renquant-pipeline#211):
  * PRIMARY `_read_from_pipeline_sink` — the structured `shadow_scorer_health.v1`
    record: append-only JSONL sidecar at
    `<strategy_dir>/logs/shadow_scorer_health.jsonl` (on this machine
    `/Users/renhao/git/github/RenQuant/backtesting/renquant_104/logs/shadow_scorer_health.jsonl`;
    override key `config["shadow_health"]["path"]`), one object per (run_date,
    shadow_name). Fields consumed: status, state, loaded, load_error,
    artifact_resolved, effective_train_cutoff_date, staleness_days,
    config_fingerprint, content_sha256, n_candidates, n_scored, coverage_frac,
    skip_reason, actionable, reasons, run_date, run_id. Every line is STRICTLY
    validated (`is_valid_v1_record`): the schema must equal the EXACT
    `shadow_scorer_health.v1`; the core decision fields must be present and
    correctly typed (`shadow_name`:str, `run_date`:parseable ISO,
    `loaded`/`actionable`:bool, `n_scored`:int, `status` in the canonical set,
    nullable numerics/`reasons`/`state` typed when present; a bool is not
    accepted where an int is required); and the producer invariant `actionable
    == (status != "fault")` must hold. A record with a missing/unknown schema
    (`…v2`/`…v10`/typo), a malformed boolean, a missing core field, an
    unparseable date, an unknown status, or a broken invariant is IGNORED — never
    best-effort parsed — so a producer emitting an unrecognised shape cannot
    silently flip the verdict; the DB fallback stays authoritative for that day
    until a parser for the new version is added. A DB-table sink or a new schema
    version is a one-branch addition here — the downstream checks do not change.

CONTRACT CONSTANTS ARE IMPORTED FROM THE PRODUCER (not hardcoded). The schema,
statuses, and state sets come from
`renquant_pipeline.kernel.panel_pipeline.shadow_health`
(`SHADOW_HEALTH_SCHEMA`, `STATUS_OK/EXPECTED_SKIP/FAULT`, `FAULT_STATES`,
`EXPECTED_SKIP_STATES`) — orchestrator depends on pipeline, so the import is
legal. It is done defensively (try/except) because a minimal launchd runtime may
lack renquant_pipeline; the local fallback literals are the EXACT same values,
and `test_fallback_literals_match_producer` asserts they equal the exports
(running wherever pipeline is importable, i.e. CI), so any drift is caught
mechanically rather than diverging silently.
  * FALLBACK `_read_from_shadow_db` — DERIVES the same record from the shadow
    runs DB (`data/runs.alpaca_shadow.db` candidate_scores: shadow rows =
    `active_scorer == shadow_name OR model_type == shadow_name`; staleness from
    `pipeline_runs.training_cutoff`). Covers dates BEFORE the sink is deployed on
    this machine — PR-landed != deployed — so the sentinel is useful the day it
    ships. Primary wins per-day; gaps fall through to the fallback.

PRODUCER/CONSUMER CONTRACT (with renquant-pipeline#211, LANDED). `status` is the
single authoritative fault axis (invariant `actionable == (status != "fault")`):
  * STATUS_OK / STATUS_EXPECTED_SKIP -> QUIET. expected_skip is #211's explicit
    by-design non-fault (states: disabled / no_shadow_models / no_candidates) —
    `loaded` may be false, but it is NOT a fault.
  * STATUS_FAULT -> the alarm axis (states: unresolved_artifact / load_failed /
    not_scored / degraded). Alarm iff the latest record for the shadow is
    `status=="fault"` (or NO record at all) for >= N consecutive sessions.
`state` / `loaded` / `n_scored` only pick the message (a non-load/not-scored
fault reads LOAD FAILURE; a scored-but-untrusted `degraded` reads DEGRADED); the
alarm decision is `status`. The DB fallback has no status (None) and derives
fault from load / staleness / coverage only. A day with NO live runs at all is
never counted — the liveness checker's domain (mirrors the degradation
sentinel's "missing rows are not a degradation"). This is the naive "0-scores =>
alarm" false-positive guard: an expected_skip never pages. `content_sha256` is
captured on the record for a future OPTIONAL, non-alarming drift advisory (a
content change without a config change) — deliberately NOT a hard alarm.

FEED DARK is deliberately conservative — it fires only when NEITHER the JSONL
nor the DB has any shadow signal for a day that had runs. A JSONL-only gap while
the DB score feed is alive is NOT alarmed: that is exactly the bootstrap window
before the pipeline sink is deployed here, and paging through it would be the
deployed-but-dark anti-pattern in reverse.

EVIDENCE: 47 injection/negative/unit tests (`tests/test_rq104_shadow_scorer_sentinel.py`),
both reader paths — each degraded state alarms; healthy day, single bad day,
missing-runs day, `expected_skip` (disabled / no_candidates) streak,
raised-threshold frozen shadow, JSONL-absent-but-DB-alive bootstrap all stay
silent. Strict-schema unit + integration tests: missing/unknown schema
(`…v2`/`…v10`), malformed booleans, bool-as-int, missing core fields (incl.
`status`), unparseable date, invalid status, and a broken `actionable == (status
!= "fault")` invariant are all rejected, and invalid records fall through to a DB
fallback that then ALARMS (fallback stays authoritative). Status-contract tests:
`STATUS_EXPECTED_SKIP` quiet vs `STATUS_FAULT` alarm (load states -> LOAD
FAILURE, degraded -> DEGRADED), an expected_skip day breaking a fault streak,
and status driving over `loaded`. Constant-match tests assert the local fallback
literals equal the producer's exports and that the module imports the producer
when available (both RUN in the canonical sibling layout / CI). Real-data drill
(prod shadow DB, read-only; sink not yet present so fallback drives):
  * `--as-of 2026-07-16 RQ104_SHADOW_STREAK_N=1` -> LOAD FAILURE fires (07-16 had
    18 collected scores, 0 from `hf_patchtst` — the real silent death).
  * `--as-of 2026-07-21` (default 28d ceiling) -> DEGRADED fires (effective
    cutoff frozen at 2024-11-13, 614/615d over the last two sessions).
  * Default 2-day window ending 07-16 stays silent (07-15 healthy) — single-day
    death does not page, by design.

DEPLOY (operator-gated landing, NOT machine-landed here):
  * `deploy/com.renquant.rq104-shadow-scorer-sentinel.plist` — TEMPLATE, 15:10 PT
    (after the degradation sentinel at 15:00).
  * `ops/launchd_manifest.json` is DELIBERATELY NOT edited in this PR. That file
    is the enforced LIVE-surface pin: `check_launchd_surface` (and the daily
    07:00 `com.renquant.run-surface-drift` scan +
    `test_committed_manifest_matches_live_surface`) require every manifested job
    to be an INSTALLED plist on disk. Committing an entry for a not-yet-installed
    job fails red on the operator machine and false-alarms the drift scan every
    day until install — the exact alarm-fatigue footgun AC2/CONTAINMENT guards
    against ("update the reviewed surface in the SAME batch as the surface
    change"). So the entry is PROPOSED here, to be pasted in the same reviewed
    batch as `launchctl load`:

        "com.renquant.rq104-shadow-scorer-sentinel": {
          "program_args": [
            "/Users/renhao/git/github/RenQuant/.venv/bin/python",
            "/Users/renhao/git/github/renquant-orchestrator-run/ops/renquant104/rq104_shadow_scorer_sentinel.py"
          ],
          "program_args_sha256": "57c92a2e445b009a466522419b2997889609ccebee4846f082e4a8d8eeeda549"
        }

    (sha256 verified == the deploy plist's ProgramArguments digest.)

ORDERED DEPLOYMENT SEQUENCE (do NOT reorder — the sentinel is only trustworthy
once its authoritative producer is real):
  1. PRODUCER: renquant-pipeline#211 has LANDED its canonical contract
     (status=ok/expected_skip/fault, invariant `actionable == (status !=
     "fault")`, exported constants). This sentinel imports those constants, so
     no further producer work is required for correctness.
  2. Pin + DEPLOY #211 on this machine so the sink JSONL actually appears under
     `backtesting/renquant_104/logs/shadow_scorer_health.jsonl` (PR-landed !=
     deployed). Until then the sentinel runs on the DB fallback — safe and
     useful, but the primary path is unexercised.
  3. CONFIRM the sentinel reads a REAL record: run `--as-of <session>` and verify
     the printed `source=pipeline_health_record` and that the fault verdict
     matches the DB-derived drill for the same day (no divergence).
  4. THEN install the launchd entry: copy the plist to `~/Library/LaunchAgents/`,
     `launchctl load` it, and add the manifest block above to
     `ops/launchd_manifest.json` in the SAME landing commit (keeps the drift
     scan's reviewed-surface pin honest).

NEXT: after step 2, the PRIMARY reader takes over automatically — no code change.
AC1 drill after one live scheduled firing. Consider folding a
knowingly-frozen-shadow staleness ack into `sentinel_acks.json` if a review-gated
suppression is preferred over the `RQ104_SHADOW_STALENESS_MAX_DAYS` override.
