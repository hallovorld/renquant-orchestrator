# Software-stop liveness pager — landing package

Date: 2026-07-11, updated 2026-07-12 (round 5 — envelope schema removed, install-time fail-closed guard)
PR: ops(stops): software-stop liveness pager package (#471 shortlist item 2)

**STATUS: MERGEABLE as a staged DARK template.** No umbrella dependency
remains in committed configuration. Merging installs nothing; arming is a
separately-granted operator landing step.

## Enablement prerequisites (arming-time, not merge-time)

1. **Writer migration**: the sell-only loop must stamp the registry file at
   `~/.renquant/runtime/software-stops/` (the neutral root this plist now
   configures). Until then, the checker finds no file → STALE → page. Since
   the plist is not installed, no false alarm fires.
2. **SLA drill**: alert-latency envelope is ~18-28 min (see below). Before
   arming, run the test-fire drill and either tighten `max_staleness_minutes`
   to meet 15 min, or obtain explicit operator acceptance of the measured
   envelope.

Neither prerequisite blocks merging — both block arming/installing.

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
| `scripts/install_stops_pager.sh` | echo-first installer: `install`/`uninstall` are DRY-RUN unless `--apply`; `status` read-only; `test-fire` routes to the wrapper; idempotent; log dir now the neutral ops root. **Round 5**: `install --apply` now runs a fail-closed pre-install guard (resolves the same data root/interpreter, resolves pins the same way as the wrapper, and calls the REAL `renquant_execution.software_stops_liveness` validators) that refuses to proceed on a missing or corrupt registry — see "Correction (round 5)" |
| `src/renquant_orchestrator/software_stops_registry_contract.py` | the READ-side registry-file **LOCATION** contract — neutral runtime-state-root convention (mirrors `deployment_manifest.deploy_state_root`) + fail-closed `classify_data_root`/`describe_data_root`. **Round 5**: the round-3 versioned CONTENT envelope (`classify_registry_file` and friends) was removed — content validity now delegates entirely to `renquant_execution.software_stops_liveness` |
| `tests/test_stops_liveness_pager.py` | 28 hermetic tests: plist shape + live-topic pin + explicit-python/data-root pin (no umbrella `.venv` reference) + neutral log root, page/no-page per checker exit class against a local ntfy recorder, delivery-failure exit codes, RUNTIME-CONTRACT fail-closed check, a REAL (non-faked) exercise of the runtime-inventory resolution path, the legacy-data-root WARNING and its absence-when-neutral, installer dry-run/apply/uninstall/status with a recording launchctl stub, and (**round 5**) the install `--apply` registry guard: missing-registry refusal, corrupt-registry refusal, zero-armed-stops-but-valid pass, dry-run non-hard-fail |
| `tests/test_software_stops_registry_contract.py` | 9 unit tests for the LOCATION-only contract module above (was 18 pre-round-5; the 9 removed were envelope-machinery tests for the deleted code) |

## Companion PR (renquant-execution)

[renquant-execution#29](https://github.com/hallovorld/renquant-execution/pull/29)
adds `src/renquant_execution/software_stops_liveness.py` + 21 tests. Ownership
split (unchanged by this round, restated for clarity):

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
