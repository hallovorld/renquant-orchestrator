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

## Round 2 (review): backward-compatible verification

Codex correctly rejected the original "next export overwrites the bundle"
reasoning: `verify_bundle` is an audit/forensics surface (Codex #236), and
historical bundle verification is exactly the case that cannot rely on
overwrite — a bundle stamped under the old `canonical_hash` was genuinely
valid under the contract in force when it was written, and unifying the
writer must not retroactively reject it.

Fix: `_legacy_canonical_hash(obj)` preserves the pre-B4 implementation
verbatim (plain `hashlib.sha256(json.dumps(obj, sort_keys=True,
default=str))`, no compact separators, no volatile-key strip).
`verify_bundle` now tries the new hash first; on mismatch it falls back to
`_legacy_canonical_hash` before concluding failure. A bundle matching either
scheme is accepted (`"ok (legacy pre-B4 hash scheme)"` when the legacy path
is what matched, for observability); a bundle matching neither is still
correctly rejected as tampering. No version marker was added — there is no
reliable way to retrofit one onto already-persisted historical bundles, and
a bounded two-scheme try-both is sufficient since there are only ever two
schemes in play (pre-B4 and B4).

Went with the simpler fallback-verify approach (not metadata versioning)
since older bundles have no existing field that could serve as a natural
version discriminator, and the fallback is exact (byte-for-byte
reimplementation of the old algorithm), not an approximation.

New tests: `test_new_and_legacy_hash_schemes_genuinely_differ` (sanity check
the two schemes actually diverge — otherwise the fallback test proves
nothing), `test_verify_bundle_accepts_bundle_stamped_with_legacy_hash_scheme`
(a bundle re-stamped with the legacy hash is still accepted today),
`test_verify_bundle_still_rejects_genuine_tampering_under_either_scheme`
(the fallback does not turn verification into a rubber stamp — a score file
tampered with after being legacy-stamped is still rejected). 2009/2011
relevant tests pass (the 2 pre-existing `test_bundle_consistency_ci_gate.py`
failures reproduce identically on a clean `origin/main` checkout, unrelated
to this change).
