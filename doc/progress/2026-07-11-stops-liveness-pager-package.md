# Software-stop liveness pager — landing package, BLOCKED (data-root authority)

Date: 2026-07-11 (round 3 — data-root authority contract + observability;
STILL BLOCKED, do not read this as "complete")
PR: ops(stops): software-stop liveness pager package (#471 shortlist item 2)

**STATUS: BLOCKED. This package must stay changes-requested/blocked and
must NOT be described as complete, merged-as-done, or stage-3-ready — even
though everything IN it is correct.** Merging this PR runs nothing
(installing is a separately-granted operator landing step regardless), but
that is not the same as this package being finished. Two independent gaps
remain, neither closed by this revision: (1) the registry **data root**
Codex flagged is still, as a matter of fact, the deprecated umbrella path —
closing that requires a SEPARATE, explicitly-authorized, live-tree R-PIN PR
this revision does not make (see "BLOCKING FOLLOW-UP" immediately below);
(2) the alert-latency **SLA** still does not meet the design's 15-minute
target. Neither this package nor its merge may be cited to support
`strategy-104#55`/`#56` software-stop enablement.

## BLOCKING FOLLOW-UP (read this first)

Codex's round-3 review (2026-07-11) held, correctly, that round 2's fix
(resolving CODE — which checkouts run the checker — through the R-PIN
Stage-1 runtime inventory) does not close the **DATA-root authority** gap:
`deploy/com.renquant.stops-liveness.plist`'s `RENQUANT_STOPS_PAGER_DATA_ROOT`
is still, today, `/Users/renhao/git/github/RenQuant` — the deprecated
umbrella. An explicit umbrella data root is a real production dependency
regardless of how the checker code itself is resolved.

**What THIS revision does** (concrete, testable, orchestrator-owned; see
"Round 3" below for detail): defines the neutral registry-file contract
(`renquant_orchestrator.software_stops_registry_contract` — an exact mirror
of `deployment_manifest.deploy_state_root`'s neutral-root convention, plus a
fail-closed, versioned envelope validator) and makes the wrapper WARN, on
every run, when the resolved data root is not that neutral root — which it
is not, today, so every run currently warns. This makes the interim state
OBSERVABLE. It does **not** migrate anything.

**What remains — the actual BLOCKING FOLLOW-UP, not made here and not
authorized for this task**: migrate (or bridge) the software-stop registry
file's WRITER — the live sell-only loop, a currently-running production
script under the umbrella (likely `scripts/intraday_sell_104.sh` or wherever
it invokes/stamps `renquant_pipeline.software_stops`) — off the
umbrella-anchored path onto the neutral runtime-state-root contract this PR
now defines. That is a live-tree, production-writer change:
out of scope for an orchestrator-only PR, requires its own explicit
operator ask-first authorization, and is NOT part of this task. Until a
separate, named PR lands that migration and re-points
`RENQUANT_STOPS_PAGER_DATA_ROOT` at the neutral root, this package:

- stays in changes-requested/blocked status;
- must not be merged with any claim of completeness;
- must not be cited as supporting `strategy-104#55`/`#56` enablement.

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

## Round 3: Codex CHANGES_REQUESTED (data-root authority) and what changed

Codex reviewed round 2 (`e46acbe`) and held that moving CODE resolution to
the R-PIN runtime inventory did not close the requested DATA-authority
issue: `RENQUANT_STOPS_PAGER_DATA_ROOT` is still, in the committed plist, the
deprecated umbrella path — confirmed, not disputed (see "BLOCKING
FOLLOW-UP" above for the exact quote and status). Codex's required fix: an
execution-owned, versioned registry-file contract at a neutral runtime
path, with the writer migrated/bridged under a separate audited R-PIN
landing, consumed by the pager.

**What changed in round 3** (the writer migration itself is explicitly OUT
OF SCOPE — see "BLOCKING FOLLOW-UP"):

- New module `src/renquant_orchestrator/software_stops_registry_contract.py`
  — the READ/validation half of the contract Codex asked for, scoped down
  to what this repo can own (the canonical registry DATA schema stays
  renquant-pipeline/renquant-execution's; CLAUDE.md hard boundary — no
  signal/decision-tree internals here):
  - `runtime_state_root()` — an EXACT mirror of
    `deployment_manifest.deploy_state_root`: override →
    `RENQUANT_RUNTIME_STATE_ROOT` env → default `~/.renquant/runtime`,
    sibling to R-PIN's own `~/.renquant/deploy/` (design doc §5.2). This is
    where a migrated writer should land the registry file
    (`~/.renquant/runtime/software-stops/<broker>.json`); this module does
    not create it or write to it.
  - A versioned envelope contract (`schema_version` +
    `kind: "software-stops-registry"`) and `classify_registry_file` — a
    fail-closed reader returning an explicit `missing` / `unversioned` /
    `invalid` / `valid` verdict, never a silent pass. Every registry file
    written before the writer migration lands is, correctly, `unversioned`.
  - `classify_data_root` / `describe_data_root` — classifies a configured
    data root as NEUTRAL or LEGACY against the neutral root, without
    depending on the writer's internal relative-path layout (another
    repo's concern).
  - 18 unit tests in `tests/test_software_stops_registry_contract.py`
    (state-root default/override, path composition, neutral/legacy
    classification including the exact production value
    `/Users/renhao/git/github/RenQuant`, envelope-problems validation,
    and all four `classify_registry_file` verdict classes).
- `scripts/stops_liveness_pager.sh` now classifies its resolved
  `RENQUANT_STOPS_PAGER_DATA_ROOT` against the neutral contract on every
  real-resolution run (not the test-override path) and emits a CLEARLY
  LABELED `WARNING: LEGACY/UNVERSIONED ...` line to stderr whenever it is
  not the neutral root — informational only, never a gate; it does not
  change the paging decision. 2 new hermetic tests prove both the warning
  (legacy data root) and its absence (a data root actually under the
  neutral root) — 24 hermetic tests total in
  `tests/test_stops_liveness_pager.py` (was 22).
- `deploy/com.renquant.stops-liveness.plist`'s comments now state the
  BLOCKED status as the headline (not a footnote), confirm the umbrella
  value is accurate rather than disputing it, and point at this doc's
  "BLOCKING FOLLOW-UP" section. The `RENQUANT_STOPS_PAGER_DATA_ROOT` value
  itself is UNCHANGED — still the real, current, umbrella path — labeled
  explicitly as an INTERIM/bridge value, not silently accepted.
- This doc and the PR body are rewritten so the BLOCKED status leads,
  per Codex's explicit point that the prior framing undersold how blocking
  the gap is.

## What ships (this repo)

| File | Role |
|---|---|
| `deploy/com.renquant.stops-liveness.plist` | launchd template: 10-min `StartInterval`, calls the wrapper via `/bin/bash`, logs to the neutral `~/.renquant/ops/stops-liveness/` root, explicit `RENQUANT_STOPS_PAGER_PYTHON` / `RENQUANT_STOPS_PAGER_DATA_ROOT` / `RENQUANT_STOPS_PAGER_NTFY_TOPIC` configuration (never a script default) |
| `scripts/stops_liveness_pager.sh` | wrapper: resolves the pinned execution/pipeline/common checkouts through the R-PIN runtime inventory (`deployment_manifest.load_runtime_inventory`), runs `python -m renquant_execution.software_stops_liveness`, pages ntfy on STALE(1)/CORRUPT(2)/**crash or inventory-resolution failure (any other code)**, exit 70 on page-delivery failure; `--test-fire STALE\|CORRUPT` emits one marked drill page, nonzero on delivery failure |
| `scripts/install_stops_pager.sh` | echo-first installer: `install`/`uninstall` are DRY-RUN unless `--apply`; `status` read-only; `test-fire` routes to the wrapper; idempotent; log dir now the neutral ops root |
| `src/renquant_orchestrator/software_stops_registry_contract.py` | **NEW, round 3**: the READ-side registry-file contract — neutral runtime-state-root convention (mirrors `deployment_manifest.deploy_state_root`) + versioned envelope + fail-closed `classify_registry_file` / `classify_data_root`. Does NOT define the registry's business schema (renquant-pipeline/renquant-execution's) and does NOT migrate the writer (see "BLOCKING FOLLOW-UP") |
| `tests/test_stops_liveness_pager.py` | 24 hermetic tests (was 22, +2 round 3): plist shape + live-topic pin + explicit-python/data-root pin (no umbrella `.venv` reference) + neutral log root, page/no-page per checker exit class against a local ntfy recorder, delivery-failure exit codes, RUNTIME-CONTRACT fail-closed check, a REAL (non-faked) exercise of the runtime-inventory resolution path — success against a schema-valid fake inventory + stub execution checkout, and failure against an empty state root proving a resolution failure pages rather than dying dark — installer dry-run/apply/uninstall/status with a recording launchctl stub — plus the round-3 legacy-data-root WARNING and its absence-when-neutral |
| `tests/test_software_stops_registry_contract.py` | **NEW, round 3**: 18 unit tests for the registry contract module above |

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
- Registry data location: the software-stop registry file itself
  (`data/rq105/software_stops.alpaca.json`) is still written by the live
  sell-only loop under the (still umbrella-anchored) runtime data root today
  — migrating THAT writer is a SEPARATE, out-of-scope, live-tree R-PIN
  landing change (see "BLOCKING FOLLOW-UP" above). `RENQUANT_STOPS_PAGER_DATA_ROOT`
  is explicit plist configuration reflecting that current fact, not a
  wrapper-script default — round 3 adds the neutral contract the eventual
  writer should satisfy
  (`renquant_orchestrator.software_stops_registry_contract`) and a WARNING
  when the resolved root is not that contract's neutral root (today, every
  run).
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

**Landing this package (steps 1-5) does NOT close the BLOCKING FOLLOW-UP**
above — it installs the schedule/notification consumer with the data root
still pointed at the umbrella, exactly as documented, and the wrapper will
warn on every run until the separate writer-migration PR lands and
`RENQUANT_STOPS_PAGER_DATA_ROOT` is re-pointed at the neutral root.

## Discipline

Read-only on the umbrella and all primary checkouts (built from a scratchpad
clone); nothing installed, no launchd/live-tree mutation, no orders. The one
network action in this package (`test-fire`) runs only when the operator
invokes it.
