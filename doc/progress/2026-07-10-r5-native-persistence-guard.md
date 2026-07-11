# R5 persistence guard for the native live path — SHADOW-SOAK STAGE (audits #107)

DATE: 2026-07-10 (revised same-day per Codex review r1 on #465)
SCOPE: orchestrator only; opt-in observability + opt-in enforcement; ZERO
behavior change for existing callers; NOT enforcement of the path
REFS: #107 (the audited PR), doc/design/2026-07-10-architecture-compliance-registry.md
(T6 / D6-F3 / R5), #460+#456 (the reused verification primitives), #443 (§2a digest)

## Honest scope statement (Codex r1 correction)

This PR does **NOT** protect `--execute-live --commit-persistence`. Guard
arming is optional, so the unsafe legacy path remains fully available; a
mutation that runs unarmed is merely stamped `persistence_guard.armed: false`
in the audit — that is telemetry, not protection. What this stage ships is:

1. the complete guard implementation (fail-closed when armed, before any
   side effect),
2. `would_have_blocked` recording on readonly invocations (the soak signal),
3. visible marking of every unverified persistence commit, and
4. the signed-override machinery the enforcement stage requires.

No unverified broker submit or persistence mutation is, or may be described
as, guarded. Enforcement is the preregistered default-flip below.

## Why

PR #107 gave `native-live-run --execute-live` a `--commit-persistence` hook that
writes live-state / trade-journal / runs-DB / lifecycle-journal artifacts. The
2026-07-10 architecture audit (T6, audit-D F3) found this same module has **no
strategy/data/artifact fingerprint gate at all** — a direct violation of the
orchestrator CLAUDE.md hard rule ("do not silently continue without
strategy/data/artifact fingerprints") on the one native path that can mutate
live state. The approved remediation shape is R5: fail-closed verification with
an **expiring operator incident token** as the only override (a standing
override env was explicitly rejected in Codex review of the registry; an
unsigned token file was explicitly rejected in Codex review of #465).

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
`native_live_run.py` wiring + `security/persistence_guard_allowed_signers`.
Reused verification primitives only — **no new hash implementations**:

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

- **Arming (opt-in)**: pass `--run-manifest-json --strategy-config-json
  --model-content-sha256` (plus optional `--calibrator-content-sha256`,
  `--decision-snapshot-digest`, `--incident-token-json`
  [`--incident-token-signature`], `--repo-root`) on the module main. Partial
  arming fails closed. The top-level `cli.py` `native-live-run` subparser is
  deliberately untouched (it is the readonly-only §2a arm surface; the guard
  flags live with the live-commit flags on the module main).
- **Ordering (when armed)**: verification runs BEFORE the live-state contract
  write, BEFORE broker submission, and BEFORE any persistence mutation; a
  guard failure means nothing was touched.
- **Override = SIGNED operator incident token** (Codex r1: an unsigned JSON
  any caller could fabricate is not an authorization). The token payload
  names the incident, operator, reason, `issued_at`/`expires_at`
  (UTC-offset ISO-8601, max lifetime 24h — no standing overrides by
  construction) and a scope binding the exact `run_id` (single-run; reuse
  requires re-authorization), the REQUIRED specific failed `checks` being
  overridden, and the REQUIRED identities being overridden
  (`model_content_sha256` + `strategy_config_sha256`) — a token cannot be
  replayed against a different run, failure, model, or config. The token
  file carries a detached OpenSSH signature (`ssh-keygen -Y sign`,
  namespace `renquant-persistence-guard`) verified with
  `ssh-keygen -Y verify` against the COMMITTED
  `security/persistence_guard_allowed_signers`, with the token's `operator`
  as principal. `ssh-keygen` ships with macOS/OpenSSH — zero new runtime
  dependencies. Unsigned, forged, tampered, wrong-key, wrong-principal,
  expired, over-TTL, or mis-scoped tokens NEVER unblock; unreadable
  manifest/config is a hard error even WITH a valid token. Every override is
  stamped in full (payload + signature provenance) into the audit. Issuing
  tokens is an operator action; the guard only validates.
- **Key custody**: the operator's private key never exists in any
  agent-accessible location. The as-committed allowed_signers entry is a
  clearly labeled PLACEHOLDER generated from a throwaway keypair whose
  private half is deliberately committed at
  `tests/fixtures/persistence_guard_test_key` so CI exercises the real
  sign/verify path — because that key is public, a signature from it proves
  nothing in production, and the operator MUST replace the entry before the
  enforcement flip (tracked rollout step below). A meta-test pins the
  placeholder labeling and that the entry matches the test key.
- **Audit binding**: the bundle metadata `persistence_audit` carries a
  `persistence_guard` block with the verified identities (resolved repo
  commits, model/calibrator shas, canonical strategy-config sha, digest,
  verdict, full override record). An UNGUARDED persistence commit is visibly
  stamped `persistence_guard.armed: false` (telemetry only — see the honest
  scope statement).
- **Soak support**: on readonly invocations an armed guard records
  `would_have_blocked: true` instead of raising.

## Preregistered rollout plan to enforcement (the R5 default-flip)

Stage numbering is frozen here; the flip itself is a separate design-gated PR.

- **Stage 0 (THIS PR)** — shadow-soak: guard code + signed-override machinery
  merged; arming opt-in; unguarded mutations remain possible and are visibly
  stamped. No protection claimed.
- **Stage 1 — armed soak**: the wrapper/scheduler that invokes
  `--execute-live --commit-persistence` (and the readonly daily native path)
  passes the guard inputs on EVERY invocation. Manifest captured at arming
  time with the existing #460 `build_run_manifest_payload` authority; shas
  frozen with the unified fingerprint.
  **Soak criteria (preregistered)**: N = 10 consecutive armed sessions with
  (a) `would_have_blocked = 0` on the readonly path, (b) zero guard
  hard-errors on the execute path, and (c) every would-have-blocked day (if
  any) investigated and dispositioned as a real incident or a guard bug
  before the counter restarts.
- **Stage 2 — operator key replacement (operator action, prerequisite to
  stage 3)**: replace the PLACEHOLDER allowed_signers entry with the
  operator's real public key (private key generated and held outside any
  agent-accessible location); the test key stays test-only in fixtures. Add
  the orchestrator repo itself to the run manifest (self-pin) so the
  allowed_signers file consumed at verification time is itself pin-verified —
  this closes the residual risk of a locally edited checkout supplying its
  own registry.
- **Stage 3 — the flip (behavior change, own PR through the registry's R5
  pre-registration gate)**: `--commit-persistence` REQUIRES the guard inputs
  (fail-closed default; a missing manifest/sha is a block, not a warning);
  readonly path keeps soak mode; overrides only via signed tokens. The
  temporary-mechanism governance fields (owner/expiry/telemetry/fail-closed
  retirement) attach per the registry's shim-governance section.

## Tests

`tests/test_native_persistence_guard.py` (24): happy path stamps identities;
fail-closed on pin drift / dirty checkout / artifact-sha mismatch /
digest-binding mismatch; readonly soak records `would_have_blocked`;
SIGNED-token override passes with full logging (signature provenance,
principal, scope); unsigned / forged-after-signing / wrong-key /
wrong-principal / expired / over-TTL / wrong-run / uncovered-scope /
missing-identity-binding / malformed / future-dated / naive-timestamp tokens
all fail closed; unreadable manifest or config is a hard error even WITH a
valid signed token; unused token noted; committed allowed_signers meta-pinned
(PLACEHOLDER label, namespace, single entry matching the test key,
default-path identity).

`tests/test_native_live_run.py` (+10): guarded commit binds verified
identities into `persistence_audit`; guard blocks BEFORE any side effect
(broker stub unreached, no files written); signed-token override stamped
(signature provenance included); expired signed token blocks; unsigned token
blocks; partial arming rejected; readonly soak stamp; legacy readonly
invocation byte-identical (no guard key anywhere); unguarded persistence
commit visibly marked; module CLI threads all guard flags incl.
`--incident-token-signature`.

Full suite: see PR body for the count.
