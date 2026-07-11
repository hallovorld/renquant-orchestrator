# R5 persistence guard on the native live path (completes #107 to production grade)

DATE: 2026-07-10
SCOPE: orchestrator only; flag-gated, zero behavior change for existing callers
REFS: #107 (the audited PR), doc/design/2026-07-10-architecture-compliance-registry.md
(T6 / D6-F3 / R5), #460+#456 (the reused verification primitives), #443 (§2a digest)

## Why

PR #107 gave `native-live-run --execute-live` a `--commit-persistence` hook that
writes live-state / trade-journal / runs-DB / lifecycle-journal artifacts. The
2026-07-10 architecture audit (T6, audit-D F3) found this same module has **no
strategy/data/artifact fingerprint gate at all** — a direct violation of the
orchestrator CLAUDE.md hard rule ("do not silently continue without
strategy/data/artifact fingerprints") on the one native path that can mutate
live state. The approved remediation shape is R5: fail-closed verification with
an **expiring operator incident token** as the only override (a standing
override env was explicitly rejected in Codex review of the registry).

## Audit of the merged #107 flow (gap list, `native_live_run.py` @ 40c51d33)

1. `run_native_live_candidate` (`:246-265` pre-change): the only pre-mutation
   validations were structural arg checks (flag exclusivity, explicit output
   paths, run-id/runs-db presence). No pin, artifact, config, or data identity
   was verified anywhere.
2. `:266` loaded the inference JSON — the order intents — from an arbitrary
   file with no binding to any verified model/config/input-world identity;
   `:282-286` submitted them to the broker and `:292-301` committed the
   persistence mutations on that unverified basis.
3. `:312-314` copied `persistence_audit` verbatim from the execution payload
   into bundle metadata: the audit recorded THAT a mutation happened, but bound
   it to no verified identity (no pins, no model sha, no config sha, no digest).
4. No pin-drift check at all on this path (the bridge path at least has the
   fail-open `runtime_paths.enforce_or_warn`; `native_live_run` imported
   nothing) and no override governance to make a future fail-closed default
   operable during real incidents.

## What this PR adds

New module `src/renquant_orchestrator/native_persistence_guard.py` +
`native_live_run.py` wiring. Reused primitives only — **no new hash or
verification implementations**:

- pins: `shadow_ab_runner.load_run_manifest` / `verify_run_manifest` (#460
  Codex r2) — every manifest repo must exist, sit at the manifest commit, and
  be clean; fail-closed;
- artifacts: `native_live_context.verify_config_artifact_shas` (#456) — the
  strategy config's resolved model/calibrator must fingerprint (via the ONE
  unified `renquant_common.model_fingerprint` impl) to the frozen shas;
- input world (optional): the inference payload's metadata must carry the
  frozen `decision_snapshot_digest` with `decision_snapshot_verified: true`
  (stamped by the digest-verified `native-live-context` step, #456/#460).

Semantics:

- **Arming**: pass `--run-manifest-json --strategy-config-json
  --model-content-sha256` (plus optional `--calibrator-content-sha256`,
  `--decision-snapshot-digest`, `--incident-token-json`, `--repo-root`) on the
  module main. Partial arming fails closed. The top-level `cli.py`
  `native-live-run` subparser is deliberately untouched (it is the
  readonly-only §2a arm surface; the guard flags live with the live-commit
  flags on the module main).
- **Ordering**: verification runs BEFORE the live-state contract write, BEFORE
  broker submission, and BEFORE any persistence mutation; a guard failure
  means nothing was touched.
- **Override**: an expiring operator incident token (JSON file) — named
  incident + operator + reason, `issued_at`/`expires_at` (UTC-offset ISO-8601,
  max lifetime 24h — no standing overrides by construction), `scope.run_id`
  equal to THIS run (single-run; reuse requires re-authorization), optional
  `scope.checks` restricting which failure categories it may override.
  Expired/malformed/mis-scoped tokens never unblock; every override is stamped
  in full into the audit (logged, never silent). Issuing tokens is an operator
  action; the guard only validates.
- **Audit binding**: the bundle metadata `persistence_audit` now carries a
  `persistence_guard` block with the verified identities (resolved repo
  commits, model/calibrator shas, canonical strategy-config sha, digest,
  verdict, override record). An UNGUARDED persistence commit is visibly
  stamped `persistence_guard.armed: false` (R5 telemetry: unverified mutation
  must be observable per run, not assumed).
- **Soak support**: on readonly invocations an armed guard records
  `would_have_blocked: true` instead of raising — the R5 pre-registration
  path ("shadow the fail-closed verdicts for N sessions, then flip").

## Arming path (documented, not executed here)

1. Operator/wrapper captures the manifest at arming time
   (`build_run_manifest_payload` is the existing #460 authority) against the
   pinned checkouts, and freezes the model/calibrator shas with the unified
   fingerprint.
2. The `--execute-live --commit-persistence` invocation gains the three guard
   flags. Readonly daily paths can arm earlier for the soak.
3. After the soak, flipping the default (guard REQUIRED for
   `--commit-persistence`) is the R5 behavior-change step and goes through its
   own pre-registered gate — deliberately NOT in this PR.

## Tests

`tests/test_native_persistence_guard.py` (17): happy path stamps identities;
fail-closed on pin drift / dirty checkout / artifact-sha mismatch /
digest-binding mismatch; readonly soak records `would_have_blocked`; valid
token overrides and is fully logged; expired / over-TTL / wrong-run /
uncovered-scope / malformed / future-dated / naive-timestamp tokens all
rejected; unreadable manifest or config is a hard error even WITH a valid
token; unused token noted.

`tests/test_native_live_run.py` (+9): guarded commit binds verified identities
into `persistence_audit`; guard blocks BEFORE any side effect (broker stub
unreached, no files written); valid-token override stamped; expired token
blocks; partial arming rejected; readonly soak stamp; legacy readonly
invocation byte-identical (no guard key anywhere); unguarded persistence
commit visibly marked; module CLI threads all guard flags.

Full suite: see PR body for the count.
