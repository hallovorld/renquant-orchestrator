# Software-stop liveness pager — complete landing package, staged dark

Date: 2026-07-11 (round 2 — ownership + SLA-honesty correction)
PR: ops(stops): software-stop liveness pager package (#471 shortlist item 2)
Status: MERGE = NOTHING RUNS. Installing is a separately-granted operator
landing step. **Staged dark, NOT stage-3-ready** (see the SLA section below —
this is the load-bearing correction in this revision).

## Bottom line

#471's evidence packet found the S-FRAC stage-3 pager **scheduled nowhere and
never test-fired** (the one missing ops half of the otherwise-verified
software-stops machinery). This PR ships the complete landing package —
launchd template + echo-first installer + test-fire drill + hermetic tests —
without installing anything.

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

## What ships (this repo)

| File | Role |
|---|---|
| `deploy/com.renquant.stops-liveness.plist` | launchd template: 10-min `StartInterval`, calls the wrapper via `/bin/bash`, logs to the neutral `~/.renquant/ops/stops-liveness/` root, explicit `RENQUANT_STOPS_PAGER_PYTHON` / `RENQUANT_STOPS_PAGER_DATA_ROOT` / `RENQUANT_STOPS_PAGER_NTFY_TOPIC` configuration (never a script default) |
| `scripts/stops_liveness_pager.sh` | wrapper: resolves the pinned execution/pipeline/common checkouts through the R-PIN runtime inventory (`deployment_manifest.load_runtime_inventory`), runs `python -m renquant_execution.software_stops_liveness`, pages ntfy on STALE(1)/CORRUPT(2)/**crash or inventory-resolution failure (any other code)**, exit 70 on page-delivery failure; `--test-fire STALE\|CORRUPT` emits one marked drill page, nonzero on delivery failure |
| `scripts/install_stops_pager.sh` | echo-first installer: `install`/`uninstall` are DRY-RUN unless `--apply`; `status` read-only; `test-fire` routes to the wrapper; idempotent; log dir now the neutral ops root |
| `tests/test_stops_liveness_pager.py` | 22 hermetic tests: plist shape + live-topic pin + explicit-python/data-root pin (no umbrella `.venv` reference) + neutral log root, page/no-page per checker exit class against a local ntfy recorder, delivery-failure exit codes, RUNTIME-CONTRACT fail-closed check, a REAL (non-faked) exercise of the runtime-inventory resolution path — success against a schema-valid fake inventory + stub execution checkout, and failure against an empty state root proving a resolution failure pages rather than dying dark — installer dry-run/apply/uninstall/status with a recording launchctl stub |

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
  — migrating THAT anchor is R-PIN scope, out of bounds for this ops-tooling
  package. `RENQUANT_STOPS_PAGER_DATA_ROOT` is explicit plist configuration
  reflecting that current fact, not a wrapper-script default.
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

## Discipline

Read-only on the umbrella and all primary checkouts (built from a scratchpad
clone); nothing installed, no launchd/live-tree mutation, no orders. The one
network action in this package (`test-fire`) runs only when the operator
invokes it.
