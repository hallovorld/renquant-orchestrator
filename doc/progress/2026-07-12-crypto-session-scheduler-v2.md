# D-C11 v2: crypto session scheduler — codex review fixes

**Date:** 2026-07-12
**PR:** supersedes #497
**Review:** codex review on #497 (5 items)

## What

Addressed all 5 items from codex's review of PR #497:

1. **Watermark validation** — `validate_watermark()` rejects snapshots whose
   `bar_watermark_utc > session_date 00:00 UTC` (catches future-bar leakage)
2. **Digest verification** — `validate_digest()` compares snapshot digest
   against an expected artifact-path digest; entries fail-closed on mismatch
3. **Shadow mode gate** — `config.mode != "live"` blocks entries (shadow
   produces observation records only, never real orders)
4. **Configured quiet interval** — `SessionWindow.for_date()` accepts
   `quiet_minutes` from `CryptoSessionConfig.quiet_interval_minutes`
5. **Stop coverage** — `stop_coverage_ok` parameter gates entries; fail-closed
   when None or False

## Gate chain (7 gates)

1. Triple gate (config + env + kill switch)
2. Mode must be `live`
3. Quiet interval (`[D 00:00, D + quiet_minutes) UTC`)
4. Signal snapshot present + session date match
5. Watermark validation (no future bars)
6. Digest verification (fail-closed on missing expected_digest)
7. Stop coverage ready (fail-closed on None/False)

## Tests

39 tests covering all review items explicitly:
- `TestWatermarkValidation` (4 tests)
- `TestDigestVerification` (4 tests)
- `TestShadowModeNonAdmission` (2 tests)
- `TestConfiguredQuietInterval` (2 tests)
- `TestStopCoverage` (2 tests)
- Plus existing 25 tests for v1 functionality

## Revision note (round 3→5, pre-Codex-review self-fix, with a mid-flight branch race)

**Context:** after this doc was written, the branch was rewritten once more
(commit `ab4c4821`, "typed artifact provenance + stop coverage + watermark
staleness") to *also* claim it addressed Codex's **round 2** review of #497
(`SignalArtifactRef`/`StopCoverageReport` typed dataclasses, watermark
staleness). That claim was independently re-verified by the coordinating
agent before Codex ever reviewed PR #501 itself, and found to overclaim: the
round-2 gaps were re-typed with prettier dataclasses but not structurally
closed. This revision is the self-found-and-fixed follow-up, done before
requesting Codex's review of #501.

**Mid-flight complication:** while this follow-up was being built, a
**second, concurrent Claude session** (same PR, `Claude-Session:
session_01DV6yNCNn64pEgDn325os3i` — the original PR author's session)
pushed two more commits directly to this branch: `9aaa8b35` ("field
validation + bundle provenance + adversarial tests, round 3") and
`86eb13b3` ("trust-boundary tests + progress doc, round 4"). Its own commit
message for `9aaa8b35` is explicit: *"Addresses codex review items 4-5 on
PR #501; items 1-3 flagged as cross-repo architecture work"* — i.e. it
explicitly did not attempt the artifact-ref/stop-coverage tautology fix or
the fingerprint-placeholder fix, the two hardest and most important gaps.
What it *did* add: `__post_init__` construction-time validation (non-empty
fields, non-negative ints, `schema_version >= 1`) and a `.validate()`
method on both `SignalArtifactRef` and `StopCoverageReport`, a new
`account_id` field on `StopCoverageReport`, a `validate_signal_contract()`
function (plain truthiness check on the three fingerprint fields + a
watermark-tzinfo check), and `build_session_bundle` schema-v2 serialization
of `artifact_ref`/`stop_coverage`.

Direct inspection of that diff (not just its commit message) confirmed the
concurrent session's `.validate()` additions do **not** close the
trust-boundary gap: its own test `test_valid_ref` writes an **empty `{}`
JSON file** and has `SignalArtifactRef.validate()` pass because it only
checks `Path(artifact_path).exists()` — never the file's *content*. The
`expected_digest` is still set directly on the in-memory object by the test
helper, identical to the round-2 tautology. Likewise `validate_signal_contract`
only checks truthiness (`if not snapshot.universe_hash`), so `"MISSING"`
would pass — it does not implement a placeholder blocklist.

**Reconciliation, not a clobber:** rather than force-push over the
concurrent session's commits or silently discard its work, this revision
was rebased onto the concurrent session's tip (`86eb13b3`) and its
genuinely-useful additions were **kept and built on top of**, while the
insufficient trust-boundary mechanism was **replaced** (not left
running in parallel, which would have been actively misleading — a
`.validate()` method that looks like the real check but isn't is worse than
no method at all):

- **Kept, wired into the new loaders as defense-in-depth:**
  `SignalArtifactRef.__post_init__`/`.validate()` and
  `StopCoverageReport.__post_init__`/`.validate()` are still present and are
  now genuinely exercised — `load_signal_artifact_ref`/
  `load_stop_coverage_report` construct the dataclass (running
  `__post_init__`) and then call `.validate()` before returning, raising on
  failure. `.validate()`'s existence-check now does real work: it catches a
  *dangling* `artifact_path` (sidecar file is well-formed, but the
  informational artifact file it references has been moved/deleted) —
  layered on top of, not instead of, the digest cryptographic check.
- **Kept:** `StopCoverageReport.account_id` field — genuine audit-trail
  value, validated as a non-placeholder fingerprint in the loader.
- **Kept, strengthened:** `validate_signal_contract` — same name (not
  renamed to avoid the appearance of an unrelated parallel function), but
  the body now uses the placeholder blocklist (`_is_valid_fingerprint`)
  instead of a plain truthiness check, so `"MISSING"`/`"UNKNOWN"`/etc. are
  now actually rejected, not just `""`.
- **Kept, extended:** `build_session_bundle` schema-v2 fields
  (`environment`, `quiet_interval_minutes`, `artifact_ref`, `stop_coverage`
  summaries) — extended with this revision's own `gate_audit` per-gate
  rollup, still under `schema_version: 2`.
- **Tightened as a direct consequence of taking `.validate()` seriously:**
  `StopCoverageReport.validate()`'s "timestamp must be timezone-aware" check
  is now actually enforced by the loader too — `load_stop_coverage_report`
  previously *silently coerced* a naive timestamp to UTC; it now rejects it
  (`StopCoverageError`), matching the fail-closed philosophy ("never default
  an unverifiable input to assume it's fine") and making `.validate()`'s
  check non-vacuous. `_KNOWN_ENVIRONMENTS` for stop coverage was tightened
  from `{live, paper, shadow}` to `{live, paper}` to match `.validate()`'s
  policy (a stop-coverage report is only ever consulted for live/paper
  ticks — shadow is blocked earlier at the mode gate, so a "shadow"
  environment report is never meaningful).
- **Replaced (not left in parallel):** the trust boundary itself. Neither
  `.validate()` method, on its own, can detect a caller who fabricates
  `expected_digest`/report fields directly on the in-memory dataclass —
  that is precisely round-2's unfixed gap. The fix is `evaluate_tick`
  accepting a **path**, not an object, and going through the real,
  file-reading loaders described below.

Going through the coordinating agent's five original findings in order:

### 1. Fingerprint validation — GENUINE FIX, was previously absent (now merged with the concurrent session's `validate_signal_contract`)

Before this revision, `universe_hash` / `model_content_sha256` /
`calibrator_content_sha256` were plain `str` fields with zero validation —
`""`, `"MISSING"`, or any placeholder flowed straight into `digest()`. Added
`_is_valid_fingerprint()` (exact-match, case-insensitive, against a
placeholder blocklist: `missing/unknown/todo/tbd/n-a/na/none/null/nil/
fixme/changeme/placeholder/xxx/unset`), used by `validate_signal_contract()`
(the concurrent session's function name, kept; its truthiness-only body
replaced with the placeholder blocklist) and a new
`FingerprintValidationGateJob` in the gate pipeline, positioned right after
watermark validation and before digest verification, per the coordinating
agent's requested gate order. Deliberately **exact-match, not substring**
— a substring blocklist would have wrongly rejected legitimate hashes like
the test fixture `"test_hash"`. The naive-datetime check for
`bar_watermark_utc` lives in `validate_watermark` instead (it must run
before the watermark comparison, which otherwise raises a bare `TypeError`
on a naive-vs-aware comparison — checking order matters here, not just
presence). `TestSignalContract` (11 tests) + `test_naive_watermark_rejected`
under `TestWatermarkValidation` cover both.

### 2. Real persisted artifact-ref verification — GENUINE FIX

This was the sharpest of the five gaps: `evaluate_tick` previously took a
caller-supplied `artifact_ref: SignalArtifactRef` in-memory object, and the
round-2 test helper (`_make_artifact_ref(snap)`) — and the concurrent
session's round-3 equivalent — literally set `expected_digest=snap.digest()`
— comparing the snapshot to itself. The typed dataclass, and now the
`.validate()` method, were real; the digest verification was not.

Fixed by changing `evaluate_tick`'s parameter from `artifact_ref:
SignalArtifactRef | None` to **`artifact_ref_path: Path | None`** — a path,
not an object. `load_signal_artifact_ref(path)` is the new sole entry
point: it reads a real JSON sidecar file, and fail-closes (raises
`ArtifactRefError`) on: missing file, unreadable file, malformed JSON,
non-dict body, `schema_version != 1`, missing/placeholder
`producer_run_id`, missing/non-64-hex `expected_digest`, and (via
`SignalArtifactRef.validate()`, now called by the loader) a dangling
`artifact_path`. `evaluate_tick` catches `ArtifactRefError` inside
`DigestVerificationGateTask` and fail-closes the tick (never crashes the
caller). There is now no code path by which a caller can hand
`evaluate_tick` a digest value and have it "verify" against itself — the
value MUST come from a real file on disk.

This is a genuinely bounded fix, not a full producer-side contract:
nothing in this repo yet *writes* these sidecar files — that's a future
producer-side integration (the actual signal-emitting code), out of scope
here, same as it was out of scope in round 1/2/3. `TestArtifactRefLoader`
(9 tests, including the dangling-path case) + `TestSignalArtifactRefConstruction`
(7 tests, adversarial `__post_init__`/`.validate()` construction) exercise
the loader and the dataclass against real `tmp_path` files. `TestDigestVerification`
was rewritten so every "blocks entry" test writes a real file via
`_write_artifact_ref()` (a thin JSON-writing helper, NOT a shortcut that
constructs `SignalArtifactRef` and hands it to `evaluate_tick` directly)
and passes the *path* to `evaluate_tick`.

### 3. Real persisted stop-coverage verification — GENUINE FIX, same pattern

Same shape of problem, same fix. `evaluate_tick`'s `stop_coverage:
StopCoverageReport | None` parameter became **`stop_coverage_path: Path |
None`**. `load_stop_coverage_report(path)` reads a real JSON file and
fail-closes (`StopCoverageError`) on: missing/unreadable file, malformed
JSON, non-dict body, `schema_version != 1`, unparseable OR timezone-naive
`timestamp_utc`, `environment` not in `{live, paper}`, missing/placeholder
`account_id`, negative/non-int `positions_covered` or `violations`,
missing/placeholder `source_version`, and (via `StopCoverageReport.validate()`,
now called by the loader) the same environment/tzinfo checks again as a
final belt-and-suspenders pass. Freshness (`is_fresh(now_utc)`) and the
`environment == config.mode` check still happen at the gate level (using
the tick's own `now_utc`), matching existing behavior — the loader has no
"now" of its own.

This module still does **not** import `renquant_execution` anywhere — the
contract is a pure file boundary, as required. `DEFAULT_STOP_COVERAGE_RELPATH
= "data/crypto/stop_coverage_report.json"` is defined as a documented
convention constant only; it is **not** auto-applied as a fallback inside
`evaluate_tick` when `stop_coverage_path` is omitted — a deliberate choice
to avoid CWD-relative fallback fragility (the existing
`CRYPTO_KILL_SWITCH_RELPATH`/`kill_switch_path` fallback already has this
property from round 1, out of scope to fix here; noting it so it isn't
mistaken for newly introduced). `TestStopCoverageLoader` (11 tests,
including the naive-timestamp rejection) + `TestStopCoverageReportConstruction`
(8 tests) exercise the loader/dataclass directly against real files;
`TestStopCoverage` (evaluate_tick integration, 5 tests) rewritten to write
real files via `_write_stop_coverage()` and pass paths.

**Judgment call — did NOT add:** Codex's original round-2 finding #2 also
said "reject ... unknown/error/cleanup-failed results," implying a
`status` enum on the report. Neither the coordinating agent's point-3 spec
nor the concurrent session added a `status` field, only schema/field
validation. Adding one now would be a bigger, uninstructed schema change
beyond what either agent asked for, so it was left out — flagged here
explicitly. If "the execution-side report can be in an error/cleanup-failed
state" becomes a real scenario, that's a follow-up schema addition to
`StopCoverageReport` (the `environment` allowlist rejecting an unrecognized
environment string, and the account_id/source_version placeholder checks,
are the pieces of that concern this revision does cover).

### 4. Separate live-mode authorization — GENUINE FIX, new capability (not touched by the concurrent session)

Previously `config.mode in ("live", "paper")` was checked identically for
both — live was exactly as easy to reach as paper. Added
`CryptoSessionConfig.live_authorization_path: Path | None = None` and
`check_live_authorization(path, now_utc)`, wired in as a new
`LiveAuthorizationGateJob` immediately after the mode gate. It is a no-op
(`return True`) whenever `config.mode != "live"` — paper is unaffected and
still needs no extra file, matching Codex's original "paper... stays behind
a distinct environment=paper evidence chain" framing (already satisfied by
the stop-coverage environment-match check).

The authorization file schema requires `schema_version`, `authorized: true`
(exactly `True`, not truthy), `authorized_at`, and **`expires_at`** —
`expires_at` is REQUIRED, not optional, by design: a stale grant must not
silently persist forever, and requiring an explicit bound was judged safer
than an optional/permanent authorization for capital-risk live entries.
Missing path / missing file / malformed JSON / schema mismatch /
`authorized != true` / not-yet-active / expired all fail-closed with a
reason prefixed `"live mode blocked — ..."`, distinguishable from ordinary
triple-gate/mode-gate reasons. 13 tests: 9 direct
(`TestLiveAuthorizationDirect`) + 4 gate-integration
(`TestLiveModeGateIntegration`, including an explicit "paper mode does NOT
require this file" regression test).

Given execution PR #34 (the stage-0 paper battery) is still open/unmerged,
there is today no real producer of this authorization file either — same
caveat as points 2/3: this closes the *gate*, not the operational process
of who signs an authorization and when. That process is intentionally left
for a future decision, not invented here.

### 5. Pipeline-primitive integration — GENUINE FIX, with one documented deviation (not touched by the concurrent session)

Confirmed `renquant-common>=0.10.0` is already a declared dependency
(`pyproject.toml`) and `renquant_common.pipeline.{Task,Job,Pipeline,
PipelineStepRecord,PipelineResult}` is already used elsewhere in this repo
(`anomaly_triggers.py`, `daily.py`, `model_freshness_enforcer.py`,
`build_wf_manifest.py`, `weekly_apy_monitor.py`, etc.) — no new cross-repo
dependency was introduced, and the "no external dependencies beyond
stdlib" line in the old module docstring has been corrected (removed
implicitly by the rewritten docstring, which now names the pipeline
integration explicitly).

The gate chain is now 9 `Task` subclasses (one per gate: triple, mode,
live-authorization, quiet-interval, snapshot-presence, watermark,
fingerprint-validation, digest-verification, stop-coverage), each wrapped
in its own tiny `Job` subclass, sharing one mutable `TickContext` dataclass
(`config`, `now_utc`, `signal_snapshot`, `artifact_ref_path`,
`stop_coverage_path`, plus mutable `entries_allowed`/`reason`/`is_quiet`/
`is_kill_switched`/`signal_snapshot_digest`/`blocked`), all run through one
`Pipeline` (`_GATE_PIPELINE`, built once at import time and reused —
stateless). `evaluate_tick` is now a thin wrapper: build `TickContext`, run
the pipeline, translate into the unchanged public `TickResult` shape.
`TickResult` gained one **additive** field, `pipeline_steps: tuple[dict,
...]`, surfaced in `to_jsonable()` — every other existing field/behavior of
`TickResult` is unchanged, so any future external consumer reading the
known keys is unaffected. `build_session_bundle` now includes a
`gate_audit` rollup (`{job_name: {ran, skipped}}` counts across the
session's ticks), on top of the concurrent session's schema-v2 fields
(`environment`, `quiet_interval_minutes`, `artifact_ref`, `stop_coverage`
summaries) — genuine per-gate audit trail, not just booleans.

**Judgment call — deliberate deviation from a literal reading of the
ask:** the task said "composed into **one Job**, run via one Pipeline."
Implemented instead as **one Job per gate**, all in one Pipeline. Reason:
`renquant_common.pipeline.Pipeline.run()` records exactly one
`PipelineStepRecord` (`job_name`, `skipped`, `elapsed_sec`) **per Job**, not
per Task — `Job.run()` just iterates its Tasks internally with no
per-Task audit hook. A single Job holding all 9 Tasks would produce exactly
ONE audit record for the entire gate chain, which cannot be "a genuine
per-gate audit trail" (the explicit ask for `build_session_bundle`). Making
each gate its own Job — using the primitive's existing `should_skip(ctx)`
hook (`_GateJob.should_skip` returns `ctx.blocked`) so every gate after the
first failure shows up as `skipped: True` rather than silently absent — is
the only way to get real per-gate visibility out of this primitive as
designed. This was judged as fulfilling the *intent* (per-gate Task +
shared context + Pipeline-driven audit trail) rather than the literal
letter, and is called out here explicitly rather than silently reinterpreted.

### Test count

115 tests in `tests/test_crypto_session.py` (up from 39 at the start of
this doc, 68 after the concurrent session's round 3/4), all passing. Full
repo suite: 3826 passed / 6 skipped when the 18 pre-existing,
environment-only failures (sibling-repo git-path resolution breaking when
tests run from an out-of-place worktree — confirmed present on the
pre-revision commit too, unrelated to this module) are excluded; 20
deselected for that reason. `test_crypto_session.py` itself: 115/115 green.

## Revision note (round 6, 2026-07-13) — trust-anchor gate, shadow-only for now

Both Codex (00:08:27Z, re-reviewing this branch) and the operator
independently reached the same conclusion: round 5's file-based
`load_signal_artifact_ref`/`load_stop_coverage_report` closed the
in-memory-tautology gap (a caller can no longer construct a matching
object directly in Python and hand it to `evaluate_tick`), but not the
deeper one — nothing ties the FILES THEMSELVES to a genuine,
tamper-evident producer. A caller with write access to the configured
paths can still write `{"expected_digest": snapshot.digest(), ...}` /
`{"violations": 0, ...}` and pass every check.

Codex proposed a concrete release boundary: this PR may merge now only if
`entries_allowed` is structurally impossible for every mode (to exercise
the bundle/report plumbing), with paper-entry enablement deferred until
execution#34's final safety contract merges, the coverage report is
execution-owned (execution#37), and the signal digest is derived from a
genuinely immutable producer artifact (model#52).

Implemented that boundary: added `ENTRY_AUTHORIZATION_TRUST_ANCHOR_READY`
(module-level flag, currently `False`) and `TrustAnchorGateTask`/
`TrustAnchorGateJob` as the 10th and FINAL gate in `_GATE_PIPELINE`. It
runs after all 9 existing gates (so every one of them still fully
evaluates and is recorded in `TickResult.pipeline_steps` — the plumbing
Codex wants exercised is genuinely exercised, only the final admit
decision is forced closed) and unconditionally blocks entries in every
mode while the flag is `False`. Flip the flag to `True` only once
model#52 and execution#37 land their fixes and this module's
`DigestVerificationGateTask`/`StopCoverageGateTask` are rewired to consume
them (tracked separately — model#52/execution#37 are both in progress as
of this note).

8 existing tests that asserted `entries_allowed=True` for an
otherwise-fully-passing tick were updated to monkeypatch the flag to
`True` for the duration of the test (proving the other 9 gates' pass-
through logic is still correct, independent of this restriction) via a
shared `_assume_trust_anchor_ready(monkeypatch)` helper. 4 new tests added:
default blocks entries in paper mode despite every other gate passing;
default blocks entries in live mode too; the other 9 gates are still
recorded as `skipped=False` when only the trust-anchor gate blocks
(proving the restriction doesn't hide the rest of the pipeline); lifting
the flag restores `entries_allowed=True` (a sanity check on the test
helper itself).

`test_crypto_session.py`: 119/119 green (115 + 4 new). Full repo suite:
3847 passed, 5 skipped, same 4 pre-existing unrelated failures (Python 3.9
vs PEP-604 syntax in a sibling `renquant-pipeline` module, confirmed via
`git stash` to pre-date this change).
