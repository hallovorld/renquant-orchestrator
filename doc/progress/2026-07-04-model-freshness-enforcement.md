# Model freshness enforcement — read-only recommendation engine

Date: 2026-07-04
PR: (this PR)
RFC: doc/design/2026-06-30-model-freshness-governance.md (#210)

## What

Added `model_freshness_enforcer.py` — a read-only enforcement module that extends the
existing observe-only `model_freshness_monitor.py` with actionable fallback
recommendations when the current prod panel is stale (>28d data-cutoff age).

## Why

The freshness monitor (Phase 1, already shipped) observes and alerts. This enforcer
adds the recommendation surface that governance §4 Pillar 1 and the (DEFERRED) Pillar 3
best-of-recent fallback both need: check current model age, scan recent candidates,
classify gate failures (infra vs substance per §4.3.1), and recommend the best option.

The module is OBSERVE-ONLY — it never retrains, promotes, or mutates any artifact. The
recommendation output feeds into `model_bundle.promote()` when an operator (or a future
Pillar-3 automation) chooses to act on it.

## Changes

- **`src/renquant_orchestrator/model_freshness_enforcer.py`** (new, ~310 lines)
  - `enforce()` — check prod panel freshness, scan candidates, recommend action
  - `scan_candidates()` — find recent `panel-ltr*.json` artifacts within a time window
  - `_classify_gate_failure()` — §4.3.1 infra/substance taxonomy on WF-gate metadata
  - `EnforcementResult` / `CandidateResult` — structured output dataclasses
  - CLI via `main()` with `--json`, `--as-of`, `--search-dir`, `--window-days`
  - Pipeline/Job/Task composition (same pattern as the monitor)

- **`tests/test_model_freshness_enforcer.py`** (new, 30 tests)
  - Gate failure classification (9 tests): passed, infra keywords, substance, unknown
  - Candidate scanning (5 tests): recent filter, gate classification, sorting, dedup
  - Enforcement logic (8 tests): healthy, stale+passing, stale+infra, stale+substance,
    no candidates, preference ordering, missing panel, unknown cutoff
  - Serialization (2 tests)
  - CLI (6 tests): JSON/text output, exit codes, window-days filter

- **`src/renquant_orchestrator/cli.py`** — added `model-freshness-enforce` subcommand

## Design notes

- Data-cutoff-keyed freshness (never `trained_date`), consistent with the monitor
- Gate failure classification uses keyword matching against §4.3.1's enumerated list:
  timeout/ParallelTimeoutError, FileNotFoundError/artifact-not-found, scorer-kind parity
- Action hierarchy: `promote_passing` > `promote_freshest` (infra-only) > `none`
- Pillar 3 (auto-promotion of infra-only failures) is DEFERRED — the enforcer only
  recommends; the `promote_freshest` action is tagged `[Pillar 3 DEFERRED]`
- Exit codes: 0 = healthy, 1 = stale but candidate available, 2 = stale no candidates

## Round 2 (review)

Codex flagged a real API-contract bug: `enforce()` accepted a standalone `breach_days`
argument that was used ONLY for the `detail` display string — the actual staleness
tiering read `policy.breach_days` (defaulting to `PROD_FAST_POLICY`'s 28d), which never
picked up a caller-supplied `breach_days` unless the caller ALSO separately constructed
a matching `FreshnessPolicy`. `build_context()` (the CLI path) happened to do this
correctly, masking the bug for every existing test (all of which only exercised the
default 28d path).

Fixed: `enforce()` now derives its effective policy via
`policy = replace(policy, breach_days=breach_days)` at the top of the function, making
`breach_days` the single authoritative source for the breach threshold while preserving
`policy`'s other fields (name/warn_days/escalate_days/require_validated_promote). This
flows through to both the prod-panel freshness read and `scan_candidates()`'s internal
per-candidate reads (both take the same `policy` object). `build_context()`'s existing
behavior is unchanged (it already passed a matching policy, so the derive is a no-op
there).

Added `test_enforce_breach_days_is_authoritative_over_default_policy`: an artifact aged
100d (lag-widened effective thresholds: 14d→96d, 28d→110d) reads BREACH at
`breach_days=14` and HEALTHY at `breach_days=28` — this test fails against the pre-fix
code (asserted `stale=True`, got `stale=False, tier='warn'`) and passes after. 31/31
enforcer tests pass; 2014/2014 relevant repo tests pass (2 pre-existing, unrelated
`test_bundle_consistency_ci_gate.py` failures reproduce identically on clean
`origin/main`).

## Round 3 (Codex — left as PLAIN PR COMMENTS, not formal reviews)

Codex left two findings as plain PR comments (2026-07-04T20:16 and 22:06 — the second
explicitly noting "I do not see a substantive change" after an intervening
merge-from-main commit that did not touch the actual issue) plus a CI-status note
(22:39). None of these were formal review submissions, so earlier sweep passes that
only checked the reviews API missed them. This round fixes both — the 22:06 comment
was re-confirming the SAME still-unfixed issue from 20:16, not a repeat of a failed
fix attempt; this is the first actual fix for it.

**Core issue — `scan_candidates()`'s window bound to the wrong clock.** The window
(`window_days`, default 10) was compared directly against `freshness.age_days` — the
candidate's binding `label_observation_cutoff` age. For fwd_60d panel artifacts this
axis is *always* ~60-90d+ old by construction (a forward-60-day label cannot be fully
observed until 60 days after the row date), even for a candidate trained TODAY. So the
window silently excluded every genuinely fresh fwd_60d candidate from ever being
scanned — the enforcer could report zero recent candidates while fresh, healthy
retrains actually existed.

Fixed: `scan_candidates()` now binds `window_days` to the candidate's own stamped
`trained_date` (its production/registration timestamp) instead of `freshness.age_days`
(its data-cutoff freshness axis). These are deliberately different questions: "was
this candidate recently produced" (scan admission, now `trained_date`-keyed) vs. "is
its underlying training data fresh enough to trust" (already correctly computed via
`freshness.tier`, which lag-widens its thresholds by the artifact's own stamped
`lookahead_days` per #423 — unchanged by this fix, still used for classification on
the admitted `CandidateResult`). `trained_date` is read via the same `_parse_date`
helper already used elsewhere in `model_freshness_monitor.py`; a missing/unparseable
`trained_date` fails closed (excluded), consistent with this module's existing
fail-closed philosophy.

Two existing tests (`test_scan_candidates_finds_recent`'s `panel-ltr.old.json` case,
`test_cli_window_days`) encoded the OLD (buggy) semantics implicitly, since their
fixture artifacts had no explicit `trained_date` override and so defaulted to a
recent stamped value — meaning they'd now pass for the wrong reason under the new
binding. Updated both to set explicit old `trained_date` values so they still
correctly test genuine exclusion. Added
`test_scan_candidates_window_binds_to_trained_date_not_cutoff_age`, which
constructs exactly Codex's described scenario (cutoff ~85d old, `trained_date` 1 day
old) and asserts the candidate IS scanned — confirmed this test fails against the
pre-fix code (`age_days`-based filter excludes it) and passes after.

**CI-red snapshot (comment 3).** `tests/test_doc_alignment.py::test_snapshot_not_stale`
failed because the committed `data/strategy_snapshot.json` baseline didn't include the
new `model-freshness-enforce` CLI subcommand this PR adds (added by
`renquant-orchestrator#329`'s M9 doc/impl alignment check, merged after this PR's
original commit). Reproduced the exact failure locally, then regenerated the snapshot
via `python scripts/generate_strategy_snapshot.py --update` per the test's own
instruction.

33 enforcer tests pass (32 + the new one); 2113/2113 relevant repo tests pass (2
pre-existing, unrelated `test_bundle_consistency_ci_gate.py` failures reproduce
identically on clean `origin/main`).
