# Software-stop liveness pager — landing package

Date: 2026-07-11, updated 2026-07-12 (round 8 — pipeline publishes its own public schema contract + a non-skipped real-sibling integration test; round 7 — guard now calls the public execution `--validate-registry` CLI instead of a private import; round 5 — envelope schema removed, install-time fail-closed guard)
PR: ops(stops): software-stop liveness pager package (#471 shortlist item 2)

**STATUS: BLOCKED on cross-repo public-API chain.** Code shape is correct
(reviewer-acknowledged round 7). Blocked on the dependency sequence below
completing before this PR can merge.

## Merge-blocking dependency sequence

Codex review (round 8, 2026-07-12T12:10:01Z / 2026-07-12T11:57:53Z on
execution#30 — same finding, both PRs): the installer guard shells
out to `renquant-execution --validate-registry`, which internally calls
`renquant_pipeline.software_stops._validate_snapshot` — a private name.
Until the full chain is public, this PR cannot merge:

1. **renquant-pipeline** exposes and tests a public `software-stops-v1`
   snapshot-validation contract (replacing `_validate_snapshot`) — **DONE,
   PR OPEN**: [renquant-pipeline#192](https://github.com/hallovorld/renquant-pipeline/pull/192)
   (`validate_software_stop_snapshot`), unmerged.
2. **renquant-execution#30** consumes that public API and exposes the
   `--validate-registry` CLI mode — **DONE, PUSHED**: follow-up commit on
   the same open PR, unmerged (depends on step 1 merging first — the
   deferred import is expected to raise `ImportError` until then).
3. **renquant-execution#30 merges** — not yet; both PR 1 and PR 2 above are
   still open for review.
4. **R-PIN advance** + end-to-end multirepo test of this guard against the
   pinned real CLI for valid, missing, and corrupt registries — the
   non-skipped test itself is **DONE, this PR**
   (`test_install_apply_guard_against_real_pinned_execution_and_pipeline`
   + `_malformed`); the R-PIN advance is not yet done (depends on 1-3
   merging first). See "Correction (round 8)" below for full detail,
   the exact Codex quote, and what was actually observed running these
   tests locally.

**Status of this PR itself**: still BLOCKED — steps 1-2 above are done as
*separate, not-yet-merged* PRs; this PR cannot merge until they do and the
R-PIN advances past them (same "arming-time not merge-time" discipline as
every prior round, just now gated on two additional repos' PRs instead of
one).

## Additional enablement prerequisites (arming-time, post-merge)

1. **Writer migration**: the sell-only loop must stamp the registry file at
   `~/.renquant/runtime/software-stops/` (the neutral root this plist now
   configures). Until then, the checker finds no file → STALE → page. Since
   the plist is not installed, no false alarm fires.
2. **SLA drill**: alert-latency envelope is ~18-28 min (see below). Before
   arming, run the test-fire drill and either tighten `max_staleness_minutes`
   to meet 15 min, or obtain explicit operator acceptance of the measured
   envelope.

(The execution/pipeline R-PIN advance is a MERGE-blocking item, not an
arming-time one — see "Merge-blocking dependency sequence" above, whose
steps 1/2 status is updated in "Correction (round 8)" below, not restated
here to avoid duplication.)

## Round 4: data-root resolved (this revision)

Codex's round-3 review correctly held that an explicit umbrella data root
in the committed plist is a production dependency regardless of how code
imports resolve. Round 3 added the neutral contract module and a
per-run warning but left the plist value unchanged.

**This revision completes the fix**: `RENQUANT_STOPS_PAGER_DATA_ROOT` now
points to `~/.renquant/runtime/software-stops` — the neutral runtime-state
root defined by `software_stops_registry_contract.runtime_state_root()`. No
reference to `/Users/renhao/git/github/RenQuant` remains anywhere in the
committed plist, wrapper script, or module code.

The trade-off is explicit: the pager cannot find registry data at this path
until the writer migration lands. This is correct — the plist is a DARK
template, not an armed service. Fail-closed (STALE on missing file) is the
right posture for an uninstalled template pointing at its target-state path.

## Correction (round 5 — envelope schema removed, install-time fail-closed guard)

Codex blocked round-4 HEAD (`a83ca971`) with review timestamp
2026-07-12T04:32:57Z, on two independent grounds:

1. **Ownership.** Round 3's `software_stops_registry_contract.py` did not
   just define the neutral runtime-state-root LOCATION convention (legitimate
   orchestrator territory, mirroring `deployment_manifest.deploy_state_root`)
   — it also invented a versioned "envelope" CONTENT schema
   (`schema_version`/`kind` keys, `classify_registry_file`) that this repo
   does not own and that never corresponded to anything the real writer
   (`renquant_pipeline.software_stops`) actually produces (confirmed by
   grep: that machinery was never called from either script — dead,
   speculative code). Codex: the canonical registry envelope belongs to the
   producing/liveness-owning subsystem (`renquant-pipeline`/
   `renquant-execution`), not orchestrator, which should schedule and
   consume a versioned execution CLI/record rather than define a parallel
   read-side schema.
2. **Fail-open install.** The DARK template points at a directory with no
   migrated writer, and the only documented consequence was a STALE page —
   but darkness is not itself a runtime safety control: `install_stops_pager.sh
   --apply` did zero verification before bootstrapping the launchd job, so an
   operator could run `install --apply` before the writer migration and get a
   false critical alarm (or, if the registry file simply never existed, a
   pager that could never detect anything).

**What changed:**

- `software_stops_registry_contract.py`: the envelope machinery
  (`REGISTRY_ENVELOPE_SCHEMA_VERSION`, `REGISTRY_ENVELOPE_KIND`,
  `VERDICT_MISSING`/`UNVERSIONED`/`INVALID`/`VALID`, `RegistryFileVerdict`,
  `registry_envelope_problems`, `classify_registry_file`) is deleted
  entirely. The module now owns LOCATION only —
  `runtime_state_root`/`software_stops_registry_root`/
  `software_stops_registry_path`/`classify_data_root`/`describe_data_root`
  are unchanged. Registry CONTENT validity is delegated entirely to
  `renquant_execution.software_stops_liveness.check()` (in turn backed by
  `renquant_pipeline.software_stops._validate_snapshot`, the real,
  already-existing schema owned by the producing repo) — the module
  docstring cites this review and states the ownership split explicitly.
- `scripts/install_stops_pager.sh`: `install --apply` now runs a fail-closed
  pre-install guard *before* any `mkdir`/`cp`/`launchctl bootstrap` step. It
  resolves `RENQUANT_STOPS_PAGER_DATA_ROOT`/`RENQUANT_STOPS_PAGER_PYTHON`
  ~~from the environment (test/operator override) or, falling back, parses
  them out of the committed plist's `EnvironmentVariables`~~ — **superseded,
  see "Correction (round 6)" below: this env-preferring resolution let an
  ambient shell variable diverge from what actually gets armed and was
  removed; the guard now reads exclusively from the plist** — via
  `python3 -c`+`plistlib` (robust XML parsing, not grep/sed — Python is
  already a hard runtime dependency of this script). It resolves the pinned
  `renquant-pipeline`/`renquant-execution` checkouts through the same R-PIN
  Stage-1 runtime-inventory approach `stops_liveness_pager.sh` already uses,
  then calls the REAL `renquant_execution.software_stops_liveness.resolve_registry_path`
  + `_pipeline_stops_api().validate_snapshot` against the resolved path.
  Missing or corrupt/unparseable registry ⇒ refuse with a specific error and
  exit nonzero (3), before touching the filesystem or launchd. A registry
  that exists and parses cleanly — including zero armed stops, a legitimate
  empty-but-valid state — passes. The guard only gates `install --apply`;
  `uninstall`/`status`/`test-fire` are untouched, and a plain `install`
  dry-run prints an informational one-liner instead of hard-failing.
  `scripts/stops_liveness_pager.sh` itself was not modified (its existing
  tests were re-run unchanged, before and after, to confirm no regression).
- Tests: `tests/test_software_stops_registry_contract.py` drops every
  envelope-machinery test (9 remain, all LOCATION-side).
  `tests/test_stops_liveness_pager.py` gains a regression suite for the new
  guard — missing-registry refusal, corrupt-registry refusal, and the
  legitimate zero-armed-stops-but-valid pass — reusing the existing
  `_fake_state_root` runtime-inventory fixture machinery with a new stub
  module content parameter (`_STUB_REGISTRY_MODULE`) rather than inventing
  a new fixture. The existing happy-path install test now supplies a valid
  registry fixture, since it would otherwise correctly be refused by the
  new guard.

**Unchanged, still tracked, still blocking:** the writer migration itself
(the sell-only loop stamping the registry at the neutral runtime-state root)
and the SLA/authorization gates (see "Honest alert-latency envelope" below)
remain separately-authorized follow-ups, exactly as before. This package is
still staged **DARK** and `strategy-104#55`/`#56` remain **blocked** on
those — this round closes the "false critical alarm from an unmigrated
writer path" gap Codex flagged, nothing more.

## Correction (round 6 — guard could validate a different path than it armed)

Codex blocked round-5 HEAD (`d0bfeefb`) with review timestamp
2026-07-12T10:57:11Z, on the guard implementation itself: `install --apply`
"can validate a different runtime contract than the launchd job it
installs." `resolve_pager_env_var` deliberately preferred an already-exported
`RENQUANT_STOPS_PAGER_DATA_ROOT`/`_PYTHON` over the plist value — but launchd
does not inherit the interactive shell environment; it executes the *copied
plist's* `EnvironmentVariables` only. An operator with either variable set
ambiently (leftover shell state, a different tool, anything) could pass the
guard against a *valid* registry while installing a job pointed at the
plist's own (missing or corrupt) path — reproducing exactly the false
critical-alarm risk the guard exists to prevent. Codex: derive data root and
interpreter exclusively from the plist that will be copied, and add a
regression test proving an ambient override pointing at a valid registry
does not let a plist-pointed-at-a-bad-path installation through.

**What changed:**

- `scripts/install_stops_pager.sh`: `PLIST_SRC` is now itself overridable via
  `RENQUANT_STOPS_PAGER_PLIST_SRC` (test-only — production always uses the
  committed plist, so this never differs from the default outside tests).
  `resolve_pager_env_var` (renamed `plist_env_var`) no longer checks the
  ambient environment at all for the guard's inputs — it parses
  `RENQUANT_STOPS_PAGER_DATA_ROOT`/`_PYTHON`/`_BROKER` from `$PLIST_SRC`
  exclusively, unconditionally. The guard therefore now validates the exact
  same file it is about to `cp` into `$PLIST_DST` and bootstrap — there is no
  longer any path by which the guard's answer can diverge from what actually
  gets armed.
- `tests/test_stops_liveness_pager.py`: the guard tests (missing/corrupt/
  zero-armed-stops-valid/happy-path) now point `RENQUANT_STOPS_PAGER_PLIST_SRC`
  at a throwaway plist (`_write_fake_plist`) carrying a controlled
  `EnvironmentVariables` dict, rather than setting
  `RENQUANT_STOPS_PAGER_DATA_ROOT`/`_PYTHON` directly in the subprocess
  environment (that would now be a no-op, correctly). New regression test
  `test_install_apply_ignores_ambient_env_and_uses_plist_value_only`: an
  ambient decoy points at a *valid* registry while the fake plist's own data
  root has none — install must refuse, and the refusal message must name the
  plist's data root, not the decoy. **Verified this test actually catches the
  round-5 bug**: run against the pre-fix `d0bfeefb` script, it fails with
  `GUARD OK` against the decoy and a successful install (returncode 0); run
  against the round-6 fix, it passes.

No change to the ownership correction from round 5 (still holds — no
registry content schema defined in orchestrator, validation still delegates
to `renquant_execution`/`renquant_pipeline`). Package remains staged DARK;
writer migration and SLA/authorization gates unchanged; `strategy-104#55`/
`#56` stay blocked.

## Correction (round 7 — guard now calls the public execution CLI, not a private import)

Codex left a third round of CHANGES_REQUESTED, review timestamp
2026-07-12T11:33:56Z, blocking round-6 HEAD (`6cde1c89`) despite the green
rerun:

> Blocking current head despite the green rerun: `install_stops_pager.sh`
> imports and calls `renquant_execution.software_stops_liveness._pipeline_stops_api()`.
> The leading underscore is an execution-private implementation detail, not
> a versioned cross-repo contract. The guard therefore depends on execution
> internals that can be refactored without a compatibility guarantee; a
> future pin advance can turn an arming-time safety check into an import
> failure or change its validation semantics.
>
> Keep schema and liveness ownership in execution/pipeline, but expose a
> public, narrow validation boundary in `renquant-execution` first:
> preferably a documented CLI mode such as `python -m
> renquant_execution.software_stops_liveness --validate-registry
> --data-root ... --broker ...`, with stable verdict/exit semantics and
> tests. Then advance the execution R-PIN and have this installer invoke
> that public interface. Alternatively publish an explicitly public
> `validate_registry_snapshot` API with a compatibility contract. Do not
> reach through `_pipeline_stops_api` from orchestrator.
>
> The normal liveness wrapper already uses the execution module CLI
> correctly; make the pre-install guard obey the same ownership boundary.

**What changed:**

- **renquant-execution** (companion PR,
  [renquant-execution#30](https://github.com/hallovorld/renquant-execution/pull/30)):
  adds `validate_registry(registry_path) -> (int, str)` and a
  `--validate-registry` CLI mode to
  `src/renquant_execution/software_stops_liveness.py`, with its own
  `REGISTRY_VALID/REGISTRY_MISSING/REGISTRY_CORRUPT = 0/1/2` verdict space
  — deliberately kept separate from `check()`'s `OK/STALE/CORRUPT`, since
  this mode only answers "does a real, schema-valid registry exist here"
  and never evaluates staleness or market session. Purely additive: the
  existing (no-flag) CLI behavior is byte-for-byte unchanged. 29 new/passing
  tests (`tests/test_software_stops_liveness.py`, 29 passed + 1 skipped).
- `scripts/install_stops_pager.sh`: `guard_registry_before_apply()` no
  longer imports `_pipeline_stops_api`/`resolve_registry_path` in-process.
  It now (a) resolves PYTHONPATH only — a new `resolve_pinned_pythonpath()`
  helper that reads the R-PIN Stage-1 runtime inventory and validates the
  pinned checkouts (missing repos / absent src dirs / the same
  stale-pin module-file tripwire `stops_liveness_pager.sh` already applies
  to `software_stops_liveness.py` specifically) — this step imports
  **nothing** from `renquant_execution`/`renquant_pipeline`, it only reads
  paths off disk; then (b) shells out, as a plain subprocess, to
  `"$python_bin" -m renquant_execution.software_stops_liveness
  --validate-registry --data-root "$data_root" --broker "$broker"` with
  that PYTHONPATH exported, and interprets ONLY its exit code
  (0=VALID/1=MISSING/2=CORRUPT, anything else = crash/resolution-failure —
  all non-zero outcomes fail the guard) and combined stdout+stderr message.
  This mirrors exactly how `stops_liveness_pager.sh`'s own liveness check
  already invokes the execution module — the ownership boundary Codex asked
  for. `scripts/stops_liveness_pager.sh` itself was **not modified**
  (0-line diff, re-verified).
- `tests/test_stops_liveness_pager.py`: `_STUB_REGISTRY_MODULE` (used by
  the install-guard tests via `_fake_state_root`'s
  `exec_module_content=` parameter) changed from a module of importable
  names (`resolve_registry_path`, `_FakeStopsApi`/`_pipeline_stops_api`) to
  a minimal argparse-driven CLI script (`--validate-registry`,
  `--data-root`, `--registry`, `--broker`) invoked via `python3 -m
  renquant_execution.software_stops_liveness --validate-registry ...`
  through the same stub-pinned-checkout machinery — mirroring
  `validate_registry()`'s real exit-code/message contract
  (0/1/2, VALID/MISSING/CORRUPT prefixes) against the same fake schema
  check (`version == 1` and `stops` is a dict) the old stub used. Only the
  MECHANISM changed (shell-out vs. import); the guard's actual safety
  assertions — refuse on missing/corrupt registry, no plist copy, no
  `launchctl` call on refusal — are unchanged and re-verified:
  `test_install_apply_refuses_when_registry_missing`,
  `test_install_apply_refuses_when_registry_corrupt`,
  `test_install_apply_passes_with_zero_armed_stops`,
  `test_install_apply_ignores_ambient_env_and_uses_plist_value_only`, and
  `test_install_apply_copies_plist_and_bootstraps` all pass unmodified in
  their assertions (29/29 in `test_stops_liveness_pager.py`; 38/38
  combined with `test_software_stops_registry_contract.py`).

**Additional blocking prerequisite (stated honestly, does not change
anything operationally today):** this orchestrator-side guard rewrite is
only FUNCTIONAL — i.e. capable of actually running `--validate-registry`
against a real pinned checkout — once **(a)**
[renquant-execution#30](https://github.com/hallovorld/renquant-execution/pull/30)
merges, and **(b)** this host's R-PIN `renquant-execution` runtime-inventory
pin advances to a commit that includes it (the same "stale-pin"
class of gap already tracked for `renquant-execution#29` in the Landing
sequence's step 0 prerequisite below). Until both land, `install --apply`
on this host would hit the `resolve_pinned_pythonpath()` module-file
tripwire or a `--validate-registry: unrecognized arguments` failure from an
un-advanced pin — a resolution-failure class, correctly fail-closed, not a
false pass. This package is already staged **DARK** regardless (writer
migration + SLA/authorization gates below are unresolved), so this does
not change today's operational posture — it is tracked here as a THIRD
named blocking prerequisite, alongside the writer migration and the SLA
drill, so it is not glossed over at the next landing attempt.

## Correction (round 8 — public pipeline contract + real-sibling integration test)

Codex reviewed round 7's fix on renquant-execution#30, review timestamp
2026-07-12T11:57:53Z, and found the boundary still wasn't fully closed:

> Directionally correct and in the right repo: orchestrator should consume
> an execution-owned CLI, and the separate structural verdict space is the
> right shape. However, this does not yet create the claimed stable
> cross-repo boundary. `renquant_execution.software_stops_liveness._pipeline_stops_api()`
> still imports pipeline's private `renquant_pipeline.software_stops._validate_snapshot`.
> The new public execution CLI therefore inherits an undocumented
> execution-to-pipeline private dependency. A pipeline refactor can change
> or remove the schema validator while the execution CLI continues to
> advertise stable 0/1/2 semantics.
>
> The schema is pipeline-owned. First expose an explicitly public pipeline
> contract, for example `validate_software_stop_snapshot(raw)`, with
> documented `software-stops-v1` compatibility/error semantics and
> pipeline-owned tests. Then update execution to use that public API
> internally, while retaining this execution-owned `--validate-registry`
> CLI for orchestrator. This preserves the intended direction:
> orchestrator -> execution public CLI -> pipeline public schema API; no
> consumer reaches through a private boundary.
>
> The current tests validate only a fake injected adapter; the real-pipeline
> contract test is optional/skipped. Add a non-skipped integration
> compatibility check in the R-PIN/multirepo validation lane, exercising
> this exact CLI against a valid registry and malformed fixture with the
> pinned pipeline implementation. Do not declare a stable public exit
> contract until that path is continuously verified.
>
> This is not a request to move schema ownership into execution. It is a
> request to make the owning pipeline contract explicit before execution
> republishes it. #481 should remain DARK and blocked until this sequence
> lands and the execution pin advances normally.

**What changed, three repos, three parts:**

- **Part A — renquant-pipeline**
  ([renquant-pipeline#192](https://github.com/hallovorld/renquant-pipeline/pull/192)):
  adds `validate_software_stop_snapshot(raw) -> dict` to
  `src/renquant_pipeline/software_stops.py`, immediately after the existing
  private `_validate_snapshot`. A thin, documented wrapper — identical
  behavior, but now a stable public name with a versioned compatibility
  contract (`software-stops-v1` / `REGISTRY_VERSION=1`) recorded in its own
  docstring as the source of truth for v1 semantics. `_validate_snapshot`
  and its existing internal callers (`SoftwareStopRegistry._load`, etc.)
  are untouched — purely additive. New `TestPublicValidateSoftwareStopSnapshot`
  test class in `tests/test_software_stops.py`: valid empty/one-stop
  registries, one `ValueError` case per schema violation, and two identity
  tests proving it is a genuine wrapper, not a divergent reimplementation
  (41/41 passed in pipeline's own suite, 12 new).
- **Part B — renquant-execution#30 (follow-up commit on the same open PR)**:
  `_pipeline_stops_api()` in `src/renquant_execution/software_stops_liveness.py`
  now imports and binds pipeline's public `validate_software_stop_snapshot`
  (Part A) instead of the private `_validate_snapshot`. The
  `_PipelineStopsAPI.validate_snapshot` field NAME is unchanged (execution's
  own internal naming choice) — only what it is bound to changed. Module
  docstring's cross-repo-dependency paragraph updated to name the public
  contract explicitly and cite this review chain. This deferred import
  raises `ImportError` until renquant-pipeline#192 merges to the pinned
  checkout — expected and documented, not papered over with a
  fallback/try-except (would defeat the point of a clean public-boundary
  dependency). The hermetic tests (fake `_PipelineStopsAPI` injection)
  don't exercise the real import path and are unaffected: 29 passed, 1
  skipped (`test_pipeline_stops_api_contract_if_pipeline_installed`,
  unchanged — pipeline still isn't installed in execution's own CI).
- **Part C — renquant-orchestrator (this PR)**: the non-skipped integration
  check Codex explicitly asked for. Two new tests in
  `tests/test_stops_liveness_pager.py`:
  `test_install_apply_guard_against_real_pinned_execution_and_pipeline`
  (valid-registry case) and its `_malformed` counterpart (invalid-JSON
  case), both exercising `install_stops_pager.sh`'s registry guard against
  the REAL `renquant_execution`/`renquant_pipeline` packages via a REAL
  runtime inventory pointing at their real sibling checkout paths
  (`Path(__file__).resolve().parents[2]`) — not the hermetic
  `_STUB_REGISTRY_MODULE` fake the existing tests above use. This is the
  "R-PIN/multirepo validation lane" Codex means: this repo's own existing
  "Full multirepo test" CI job (which checks out every sibling, including
  pipeline with cvxpy, as a real directory), not a new CI job. On an
  isolated worktree (no sibling directories at the resolved parent) both
  tests correctly skip; on a normal dev machine at `.../git/github/` or in
  that CI job they run for real.
  - **Design correction made while building this**: ~~the initial approach
    used `pytest.importorskip("renquant_pipeline")` /
    `pytest.importorskip("renquant_execution")` followed by a bare
    `from renquant_execution.software_stops_liveness import validate_registry`
    as an "import-time proof the function exists" check... Fixed by using a
    dotted-path `pytest.importorskip("renquant_execution.software_stops_liveness.validate_registry")`
    instead... This is the mechanism that actually delivers "skip if the
    function doesn't exist yet."~~ — **superseded, see "Correction (round
    9)" below: that dotted-path mechanism does NOT work as claimed here.
    It was never independently re-verified against a real passing case
    before this claim was written.**
  - **Two distinct "not ready" states, handled differently on purpose**: if
    `renquant_execution.software_stops_liveness.validate_registry` itself
    doesn't exist (sibling checkout predates renquant-execution#30, round
    7), the test SKIPS — the feature under test doesn't exist in that
    checkout at all. If `validate_registry` exists but the pinned
    `renquant-pipeline` checkout predates renquant-pipeline#192 (Part A),
    the CLI's deferred import of `validate_software_stop_snapshot` raises
    inside the subprocess these tests invoke, the subprocess exits
    crash-class, and the test genuinely FAILS (not skips) — a real,
    actionable "pipeline sibling is stale relative to this contract"
    signal, not an infra gap to hide.
  - Updated the "Enablement prerequisites" list above (item 3) to name the
    now-three-repo dependency chain explicitly.

**Observed in this environment (isolated worktrees under the scratchpad, as
required for this round's work — never the shared live checkouts):** both
new orchestrator tests **SKIPPED**, not ran — `pytest.importorskip` reported
`could not import 'renquant_execution.software_stops_liveness.validate_registry'`
against this scratchpad's separately-checked-out sibling clones of
renquant-execution/renquant-pipeline (leftovers from earlier, unrelated
session work, sitting at `main`, which predates even renquant-execution#30 /
round 7 — not `/Users/renhao/git/github/`'s real siblings, and not this
session's own Part A/B worktrees). This is the correctly-skipped outcome the
test's docstring documents for a checkout predating round 7. **Separately
verified the full chain works end-to-end** by manually running
`install_stops_pager.sh install --apply`'s guard (outside pytest, as a
one-off sanity check, not committed) against a runtime inventory pointing at
this round's own Part A (`r8-pipeline`) and Part B (`r8-execution`)
worktrees plus the scratchpad's other real siblings: the valid-registry case
produced `GUARD OK: VALID ...` and exit 0 with the plist copied and
launchctl invoked; the malformed-registry case produced
`GUARD FAIL: CORRUPT: ... JSONDecodeError ...` and exit 3 with no plist
copied and no launchctl call — proving orchestrator -> execution public CLI
-> pipeline public schema API works correctly with real code in both
directions once all three repos carry this round's changes. This ad hoc
verification is not itself the committed non-skipped test; it confirms the
committed test's mechanism is sound and will pass for real once Part A/B
merge and the R-PINs advance in this repo's own CI or on a machine with
real, up-to-date sibling checkouts.

## Correction (round 9 — the round-8 skip mechanism never actually ran; fixed and independently re-verified passing for real)

Independent re-verification (not a Codex review this time — caught while
verifying round 8's work before trusting it) found that round 8's two new
integration tests, as committed, could **never run for real, under any
circumstances** — they always skip, even against a fully up-to-date,
correctly-pinned sibling checkout with the real `validate_registry`
function present. That is a materially worse gap than round 8's own
"observed SKIPPED in this environment" note implied: round 8 attributed the
skip to stale local sibling checkouts (a real, transient reason); the
actual cause is a mechanism bug that would keep skipping even in this
repo's own "Full multirepo test" CI job once Part A/B merge — i.e. Codex's
explicit "non-skipped integration compatibility check" ask would still not
be satisfied post-merge.

Root cause: `pytest.importorskip("pkg.mod.attr")` calls
`importlib.import_module("pkg.mod.attr")`, which treats every dot-separated
segment as a **submodule** to import, not `getattr(module, "attr")`. Since
`renquant_execution.software_stops_liveness` is a plain module (not a
package), Python cannot even attempt to look for a submodule named
`validate_registry` inside it, and raises
`ModuleNotFoundError: ...software_stops_liveness' is not a package`
**unconditionally** — regardless of whether the `validate_registry`
function exists as an attribute. Verified empirically both directions: (a)
against a stub module exposing only `OK = 0` (no `validate_registry`) and
(b) against the real, current `renquant_execution.software_stops_liveness`
(with `validate_registry` genuinely present, from a fresh
`origin/feat/software-stops-registry-validate-cli` worktree) — **both cases
skip identically**, proving the dotted-path check cannot distinguish
"exists" from "doesn't exist."

**Fix**: replaced both occurrences with a plain attribute import wrapped in
`try/except ImportError: pytest.skip(...)` — the standard, correct pattern
for "skip if this name doesn't exist yet, run for real if it does."
Verified empirically both directions with the SAME method as above: a
`from X import name_that_does_not_exist` raises a catchable `ImportError`
(not silently-wrong submodule-machinery behavior), while
`from X import name_that_exists` succeeds and execution falls through to
the real test body.

**Independently re-verified passing for real** (not just "should work"):
built a complete, genuine sibling-worktree layout under a scratch directory
— `renquant-common`/`renquant-base-data`/`renquant-artifacts`/`renquant-model`
at `origin/main`, `renquant-pipeline` at Part A's
`feat/public-validate-software-stop-snapshot`, `renquant-execution` at Part
B's `feat/software-stops-registry-validate-cli`, and this repo at this PR's
head with the round-9 test fix — installed `cvxpy`/`pydantic`/etc. into an
isolated venv (so package resolution doesn't depend on the ambient `HOME`
the tests deliberately sandbox), and ran
`tests/test_stops_liveness_pager.py` from within that layout:
**`test_install_apply_guard_against_real_pinned_execution_and_pipeline` and
its `_malformed` counterpart both PASSED** (not skipped) — 40/40 in the
full touched-suite run. This is the first time this exact chain
(orchestrator's install guard → execution's real `--validate-registry` CLI
→ pipeline's real `validate_software_stop_snapshot`) has been proven to
work end-to-end with real code and a real, passing (not just non-crashing)
assertion, closing Codex's "non-skipped integration compatibility check"
ask for real rather than in design intent only.

## Bottom line

#471's evidence packet found the S-FRAC stage-3 pager **scheduled nowhere and
never test-fired** (the one missing ops half of the otherwise-verified
software-stops machinery). This PR ships the orchestrator-owned landing
package — launchd template + echo-first installer + test-fire drill +
hermetic tests — without installing anything. It is **not** the complete
fix for #471's underlying gap: see "BLOCKING FOLLOW-UP" above for what
still has to land separately before this is done.

**Landing one-liner (after operator grant):**

```
scripts/install_stops_pager.sh install --apply && scripts/install_stops_pager.sh test-fire STALE
```

then record ACTUAL page-delivery latency + operator response time (see the
honest SLA section — this drill is evidence for a sign-off decision, not a
demonstration that the design's 15-minute target is met).

## Round 2: Codex CHANGES_REQUESTED and what changed

Codex reviewed the round-1 head commit (`3ee232d`) and requested changes on
two independent grounds:

1. **Ownership.** The round-1 wrapper invoked
   `RenQuant/scripts/check_software_stops_liveness.py` through
   `RenQuant/.venv`, writing logs under the umbrella `logs/` tree — a new
   production scheduling/runtime dependency on the deprecated umbrella,
   despite this package living in orchestrator.
2. **SLA honesty.** The round-1 doc already disclosed an ~18-28 minute
   alert-latency envelope against the design's 15-minute target, but the PR
   framing ("landing one-liner... vs the design §3.4 SLA") read as though
   this package satisfied or was ready to satisfy that SLA. Codex ruled that
   DARK packaging may document the gap but must not call the landing package
   stage-3-ready or claim it supports `strategy-104#55` enablement.

**What changed in round 2:**

- The liveness **checker** moved to `renquant-execution` —
  [renquant-execution#29](https://github.com/hallovorld/renquant-execution/pull/29)
  (`src/renquant_execution/software_stops_liveness.py` + 21 tests). It is a
  faithful port of the umbrella script's watchdog logic (market-session gate
  + staleness computation delegating to `renquant_pipeline.software_stops` +
  the 0/1/2 exit contract) — not a re-derivation. See that PR / its progress
  doc for why the `renquant_pipeline` import is lazy and why that repo's CI
  does not need to install pipeline's dependency chain (cvxpy /
  renquant-base-data / renquant-artifacts) for this thin wrapper.
- `scripts/stops_liveness_pager.sh` now resolves the pinned
  `renquant-execution` / `renquant-pipeline` / `renquant-common` checkouts
  through the **R-PIN Stage-1 runtime inventory**
  (`~/.renquant/deploy/runtime-inventory.json`, override
  `RENQUANT_DEPLOY_STATE_ROOT`) read via this repo's own reader API
  (`renquant_orchestrator.deployment_manifest.deploy_state_root` /
  `state_root_paths` / `load_runtime_inventory` — one reader implementation,
  never ad-hoc JSON parsing; the calibrator-fingerprint triple-impl lesson)
  and invokes `python -m renquant_execution.software_stops_liveness`. No
  umbrella path, no umbrella venv, and no umbrella lock-file dependency: the
  inventory is the NEUTRAL per-host repo-name → checkout-path map, consumed
  exactly as that (R-PIN Stage 1 defines no pin-authority semantics and this
  job uses none; `deployment_manifest.py` is stdlib-only so resolution runs
  before any pinned `PYTHONPATH` exists). The interpreter and registry data
  root are still explicit, reviewed arming-time plist configuration (RUNTIME
  CONTRACT, same discipline as `shadow_ab_daily.sh`) — the wrapper script
  itself has no default pointing at any repo. A
  `RENQUANT_STOPS_PAGER_CHECKER_CMD` test-only override lets the hermetic
  tests substitute a fake checker; a second, non-faked test exercises the
  REAL inventory resolution against a schema-valid fake inventory pointing
  at a stub execution checkout.
- Logs/state moved to the **neutral, orchestrator-owned operational root**
  `~/.renquant/ops/stops-liveness/` — sibling to R-PIN's
  `~/.renquant/deploy/` neutral machine-state root
  (`doc/design/2026-07-11-deployment-pin-authority-migration.md` §5.2) —
  replacing the umbrella `logs/stops_liveness/` path. The plist's
  `WorkingDirectory` key (previously the umbrella root) was dropped; the
  wrapper never depends on cwd.
- The SLA language is corrected everywhere (plist comment, wrapper
  `--test-fire` message, this doc): the package states plainly that it is
  **not stage-3-ready** and does **not** support `strategy-104#55/#56`
  enablement by itself. See the SLA section below for the full framing,
  unchanged in substance from round 1's honest disclosure but no longer
  paired with language that could be read as claiming readiness.
- `max_staleness_minutes` (the pipeline-owned arming-time knob) is
  UNCHANGED — tightening it is explicitly out of scope for this ops-tooling
  package, called out as the first of two possible paths to closing the SLA
  gap (see below).

## Round 3: data-root authority contract + observability

Codex reviewed round 2 and held that CODE resolution through R-PIN did not
close the DATA-authority issue. Round 3 added the neutral contract module
(`software_stops_registry_contract.py` — runtime_state_root, versioned
envelope, classify_data_root) and per-run WARNING in the wrapper, but left
the plist value at the umbrella path. See round 4 (above) for the data-root
resolution, and round 5 (above) for the removal of round 3's versioned
envelope (Codex correctly held it was an unowned, unused, invented content
schema — see "Correction (round 5)").

## What ships (this repo)

| File | Role |
|---|---|
| `deploy/com.renquant.stops-liveness.plist` | launchd template: 10-min `StartInterval`, calls the wrapper via `/bin/bash`, logs to the neutral `~/.renquant/ops/stops-liveness/` root, `RENQUANT_STOPS_PAGER_DATA_ROOT` = neutral runtime-state root (`~/.renquant/runtime/software-stops`), explicit `RENQUANT_STOPS_PAGER_PYTHON` / `RENQUANT_STOPS_PAGER_NTFY_TOPIC` (never a script default, no umbrella reference) |
| `scripts/stops_liveness_pager.sh` | wrapper: resolves the pinned execution/pipeline/common checkouts through the R-PIN runtime inventory (`deployment_manifest.load_runtime_inventory`), runs `python -m renquant_execution.software_stops_liveness`, pages ntfy on STALE(1)/CORRUPT(2)/**crash or inventory-resolution failure (any other code)**, exit 70 on page-delivery failure; `--test-fire STALE\|CORRUPT` emits one marked drill page, nonzero on delivery failure. Unchanged in round 5. |
| `scripts/install_stops_pager.sh` | echo-first installer: `install`/`uninstall` are DRY-RUN unless `--apply`; `status` read-only; `test-fire` routes to the wrapper; idempotent; log dir now the neutral ops root. **Round 5**: `install --apply` runs a fail-closed pre-install guard that refuses to proceed on a missing or corrupt registry. **Round 7**: the guard no longer imports `renquant_execution` private names in-process — it resolves PYTHONPATH only, then shells out to the pinned `renquant_execution`'s public `--validate-registry` CLI mode and interprets its exit code — see "Correction (round 7)" |
| `src/renquant_orchestrator/software_stops_registry_contract.py` | the READ-side registry-file **LOCATION** contract — neutral runtime-state-root convention (mirrors `deployment_manifest.deploy_state_root`) + fail-closed `classify_data_root`/`describe_data_root`. **Round 5**: the round-3 versioned CONTENT envelope (`classify_registry_file` and friends) was removed — content validity now delegates entirely to `renquant_execution.software_stops_liveness` |
| `tests/test_stops_liveness_pager.py` | 28 hermetic tests: plist shape + live-topic pin + explicit-python/data-root pin (no umbrella `.venv` reference) + neutral log root, page/no-page per checker exit class against a local ntfy recorder, delivery-failure exit codes, RUNTIME-CONTRACT fail-closed check, a REAL (non-faked) exercise of the runtime-inventory resolution path, the legacy-data-root WARNING and its absence-when-neutral, installer dry-run/apply/uninstall/status with a recording launchctl stub, and (**round 5**) the install `--apply` registry guard: missing-registry refusal, corrupt-registry refusal, zero-armed-stops-but-valid pass, dry-run non-hard-fail |
| `tests/test_software_stops_registry_contract.py` | 9 unit tests for the LOCATION-only contract module above (was 18 pre-round-5; the 9 removed were envelope-machinery tests for the deleted code) |

## Companion PRs (renquant-execution)

[renquant-execution#29](https://github.com/hallovorld/renquant-execution/pull/29)
adds `src/renquant_execution/software_stops_liveness.py` + 21 tests.

[renquant-execution#30](https://github.com/hallovorld/renquant-execution/pull/30)
(round 7, open, not yet merged) adds the public `validate_registry()` /
`--validate-registry` CLI mode `install_stops_pager.sh`'s guard now consumes
— see "Correction (round 7)" above.

Ownership split (unchanged by this round, restated for clarity):

- `renquant-pipeline` — registry data model + staleness arithmetic
  (`software_stops.py`, RenQuant#440, 2026-07-04) + the decision-time arming
  task (`kernel/pipeline/task_software_stops.py`). Untouched.
- `renquant-execution` — the liveness CHECKER (new).
- `renquant-orchestrator` (this repo) — pinned schedule + notification
  consumer wrapper. Does not reimplement checker logic.

## Design facts

- Checker: `renquant_execution.software_stops_liveness` (moved from the
  umbrella's `RenQuant/scripts/check_software_stops_liveness.py`; watchdog
  arithmetic still delegates to the pinned `renquant_pipeline.software_stops`
  so checker and heartbeat-stamper share one implementation). Exit contract
  unchanged: 0 OK / 1 STALE / 2 CORRUPT.
- Live ops topic: `renquant` — same channel as the live sell-only loop
  (`intraday_sell_104.sh` `NTFY_TOPIC="renquant"`). Pinned in the plist env
  AND the wrapper default; test-asserted equal.
- Schedule: all-day 600s `StartInterval` (simplest robust schedule); the
  checker itself returns OK off-session via the canonical market calendar, so
  market-hours gating lives in exactly one place.
- Registry data location: the plist configures `RENQUANT_STOPS_PAGER_DATA_ROOT`
  to the neutral runtime-state root (`~/.renquant/runtime/software-stops`).
  The checker finds the registry file there once the writer migration lands.
  Until then, the checker sees no file and exits STALE (correct fail-closed
  for an uninstalled template). The writer migration (sell-only loop → neutral
  root) is a separate R-PIN landing change (see "Enablement prerequisites").
- The wrapper — not the checker's best-effort `--ntfy-topic` — owns paging,
  so delivery failure is detectable (exit 70) and a checker *crash or
  pin-resolution failure* pages instead of dying dark. No double-page: the
  checker is invoked without `--ntfy-topic`.

## Honest alert-latency envelope — NOT stage-3-ready

The worst-case page latency after a pass missed at T0 is mechanical:

```
page_time = T0 + (B − C) + I + D
  C = 12m   sell-only loop heartbeat cadence (com.renquant.intraday104)
  B = max_staleness_minutes — rides in the registry SNAPSHOT, stamped by
      the ARMING side (pipeline default 30)
  I = this plist's StartInterval (600s = 10m)
  D = page delivery time (seconds; measured by the test-fire drill)
```

With today's values (B=30, C=12, I=10): STALE flips 18m after the FIRST
missed pass (i.e. on the second consecutive miss) and the **first page lands
18–28m (+D) after the first missed pass**. This does **not** meet the
design's "page ≤15m of the scheduled pass" target.

**This package must not be described as stage-3-ready and does not by
itself support `strategy-104#55`/`#56` software-stop enablement.** Closing
the gap needs ONE of:

1. An **arming-side + interval change — the exact values that mathematically
   satisfy 15m**: `max_staleness_minutes = 20` (pipeline arming-side; out of
   scope here, not made in this PR — a production risk-parameter decision)
   together with `StartInterval = 300` (a one-line change to this plist at
   decision time). Worst case: (20 − 12) + 5 + D = **13m + D ≤ 15m for any
   D ≤ 2m**, keeping B − C = 8m of tolerance for a slow-but-alive loop pass
   before a false page. (B=20 with the current I=10 gives 18m+D and still
   fails; B below ~17 starts false-paging on ordinary pass jitter — both
   knobs must move together.)
2. A **separately-signed operator acceptance** of the current 18–28m (+D)
   envelope, recorded explicitly at stage-3 enablement time — not implied by
   merging or landing this package. This doc states the bound; it does not
   accept it.

The `--test-fire` drill (the "define an explicit experiment: test-fire plus
measured page delivery and operator acknowledgement" Codex asked for) is the
landing-step experiment that produces the ACTUAL numbers needed for either
decision above — measured D (page delivery) and measured operator
acknowledgement time against the 60m response half of the SLA. It runs only
after operator grant, per the landing sequence below — this PR does not run
it and does not claim its outcome.

## Landing sequence (operator grant required — landing-actions ask-first)

0. **Prerequisite — pin advance**: the runtime inventory's
   `renquant-execution` checkout must contain the checker (merged
   renquant-execution#29). Verified live 2026-07-11 that today's pinned
   checkout predates #29; the wrapper's resolver detects this and pages
   "PIN RESOLUTION FAILED" (the pin-not-advanced detail goes to the launchd
   stderr log) rather than a false STALE, but landing before the pin
   advance just produces that page every 10 minutes.
0b. **Prerequisite (round 7) — a SECOND pin advance for `install --apply`
   specifically**: the registry guard's `--validate-registry` subprocess
   call requires the pinned `renquant-execution` checkout to additionally
   contain [renquant-execution#30](https://github.com/hallovorld/renquant-execution/pull/30)
   (not yet merged as of this doc). Until both #30 merges and the pin
   advances past it, `install --apply` fails closed at the guard step
   (resolution/CLI failure, not a false pass) — see "Correction (round 7)".
1. Operator grant.
2. `scripts/install_stops_pager.sh install` — review the echoed commands.
3. `scripts/install_stops_pager.sh install --apply`.
4. `scripts/install_stops_pager.sh test-fire STALE` — one marked synthetic
   page to the live topic; record the ACTUAL page-delivery latency and
   operator response time. This is evidence for the stage-3 sign-off
   decision (tighten `max_staleness_minutes`, or accept the ~18-28m
   envelope) — not a claim that either decision is already made.
5. `scripts/install_stops_pager.sh status` on the next market day — confirm
   scheduled checks are logging under `~/.renquant/ops/stops-liveness/`.
6. `strategy-104#55`/`#56` software-stop enablement stays OFF regardless of
   this landing — that is a separate, later decision gated on the SLA
   resolution above.

**Landing this package (steps 1-5) installs the schedule/notification
consumer.** The plist already points at the neutral data root. Enablement
of software stops (`strategy-104#55`/`#56`) is a separate decision gated on
the writer migration and SLA drill above.

## Discipline

Read-only on the umbrella and all primary checkouts (built from a scratchpad
clone); nothing installed, no launchd/live-tree mutation, no orders. The one
network action in this package (`test-fire`) runs only when the operator
invokes it.
