# S3-b: wire the pinned production blend into the observe-only shadow collector

STATUS: implementation PR (GOAL-105 ladder; design orch#1026/#1030). The
collector (#221) has refused with "no scorer wired" rc=2 on every session
since 2026-08-12; today's S3-a snapshot landed (first self-produced
`feature_snapshot_2026-08-24.json`, 90×172, function-verified), which makes
this the last missing stage before shadow serving actually serves.

## What

- `src/renquant_orchestrator/shadow_serving_pinned.py` — loads the SAME
  composite production ranks on, via the pinned pipeline's
  `load_blend_scorer` (which pin-verifies each component fail-closed:
  content sha abbrev-tolerant, config fingerprint verbatim, momentum ledger
  chain). ONE shared definition — no pin check re-implemented here; a
  refusal propagates. Adapts it to the ShadowScorer protocol:
  `artifact_digest` = the blend's composite config fingerprint (refused if
  empty), `feature_digest` = the served snapshot's digest (so
  `_resolve_provenance` rejects a swapped file), matrix = fresh rows'
  served values VERBATIM reindexed to the artifact's `feature_cols`
  (no re-normalization — the snapshot bridges `ctx._panel_matrix`, already
  post-preprocessing; the replay-vs-served lesson).
- Refusals at the seam: zero fresh rows → named ProvenanceError (not an
  empty matrix handed onward — the first draft fail-opened here and the
  REAL smoke test caught it); artifact columns absent from the snapshot →
  named ProvenanceError listing them.
- `ops/renquant105/run_shadow_serving.sh` — pinned pipeline joins
  PYTHONPATH; the strategy config resolves through
  `rq105_pinned_common.py --verify-file` (lock+HEAD+bytes, orch#1041 —
  same contract as the session scheduler; refusal pages and exits 1, never
  the calm skip); invocation switches to
  `-m renquant_orchestrator.shadow_serving_pinned`.
- `tests/test_shadow_serving_pinned.py` — 8 tests, fakes injected via
  sys.modules (the pipeline's own pin logic is tested in pipeline; only
  THIS module's contract is tested here): refusal propagation, empty
  fingerprint refusal, verbatim matrix from fresh rows, censored-row
  exclusion, missing-ref refusal, NaN-drop/uppercase, end-to-end main()
  with provenance-bound rows, required-arg refusal. Covered by CI: this
  repo's token-ful job runs `make test` = whole `tests/`.

## Evidence (§4b)

- Unit: `tests/test_shadow_serving_pinned.py` + the collector's existing
  suite: **25 passed** on CI-matching python 3.10 [VERIFIED — local run
  2026-08-24].
- **Real-artifact end-to-end smoke** [VERIFIED — 2026-08-24, umbrella venv,
  read-only inputs, output to scratchpad]: pinned config resolved via
  `--verify-file`; real blend loaded pin-verified; scored today's REAL
  self-produced snapshot at `as_of=19:59:50Z` against the real frozen batch
  export: `n_rows=90, n_shadow=75, n_paired=70, coverage=0.83`; every row
  carries `artifact_digest=sha256:555094ee…` (composite) and
  `feature_snapshot_digest=sha256:8f563bcf…` (today's snapshot).
  n_shadow<n_rows is the blend's designed intersection semantics (momentum
  leg NaNs unscored names; NaN propagates).
- The smoke's first run FAILED (all 172 columns "missing") and that failure
  was the fix: zero fresh rows at a stale `as_of` produced an empty matrix
  that my seam passed through fail-open. Now a named refusal.

## Not in this PR

- No live entries, no orders — OBSERVE-ONLY throughout (S3-c live flip
  remains the operator's explicit act).
- No scheduler/launchd change: the same 13:45 job now reaches serving
  instead of the rc=2 refusal, with its existing notify-on-fail paths.

## Deploy

Merge → orch-run ff sync (wrapper + module travel together) → tomorrow's
13:45 job is the first real served session; its log should show the
`[OBSERVE-ONLY]` summary instead of "no scorer wired", and
`data/rq105/shadow_scores/…` rows bind to the composite digest.
