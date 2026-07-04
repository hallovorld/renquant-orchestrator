# B4: score_content_sha256 unification

DATE: 2026-07-04
PR: this PR
CAMPAIGN: compliance fix campaign (doc/design/2026-07-04-compliance-fix-campaign.md), Wave 2

## Problem

Two incompatible hash implementations for `score_content_sha256`:

| Site | Implementation | JSON separators |
|---|---|---|
| `ops/renquant105/batch_scores_bundle.py::canonical_hash` | local `json.dumps(obj, sort_keys=True, default=str)` | default (`, `, `: ` with spaces) |
| `renquant_artifacts.contracts::hash_jsonable` (used by `intraday_session_inputs`, `intraday_replay_audit`, `daily`, `intraday_live_executor`, pipeline `model_admission`, pipeline `intraday_decisioning`) | `json.dumps(_strip_volatile(obj), sort_keys=True, separators=(",", ":"), default=str)` | compact (no spaces) |

The same `{ticker: score}` dict hashed by both produces different SHA256 digests.
If scores were exported via `export_batch_scores.py` (canonical_hash) and later
verified by the orchestrator's `intraday_replay_audit` (hash_jsonable), the hash
would not match.

## Fix

- `canonical_hash` now delegates to `hash_jsonable` from `renquant_artifacts`
- Added `_ensure_subrepo_importable` bootstrap (generalized from the B5
  `_ensure_common_importable` pattern) to make `renquant_artifacts` importable
  from the bare-script launchd context
- 2 pinning tests: `test_canonical_hash_matches_hash_jsonable` and
  `test_canonical_hash_delegates_to_hash_jsonable`

## Behavior change

Hashes produced by `canonical_hash` will differ from pre-fix hashes on the
same input. Existing persisted bundles (data/rq105/) will fail verification
on their next `verify_bundle` call. This is the correct behavior: the next
`export_batch_scores.py` run overwrites the bundle with a correctly-hashed
version. No manual intervention needed.
