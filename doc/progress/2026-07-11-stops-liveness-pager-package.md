# Software-stop liveness pager — complete landing package, staged dark

Date: 2026-07-11
PR: ops(stops): software-stop liveness pager package (#471 shortlist item 2)
Status: MERGE = NOTHING RUNS. Installing is a separately-granted operator
landing step.

## Bottom line

#471's evidence packet found the S-FRAC stage-3 pager **scheduled nowhere and
never test-fired** (the one missing ops half of the otherwise-verified
software-stops machinery). This PR ships the complete landing package —
launchd template + echo-first installer + test-fire SLA drill + 17 hermetic
tests — without installing anything.

**Landing one-liner (after operator grant):**

```
scripts/install_stops_pager.sh install --apply && scripts/install_stops_pager.sh test-fire STALE
```

then record page-delivery + operator response time vs the design §3.4 SLA
(page ≤15m of a missed sell-only pass; runbook response ≤60m of the page) —
#471 operator shortlist item 2.

## What ships

| File | Role |
|---|---|
| `deploy/com.renquant.stops-liveness.plist` | launchd template: 10-min `StartInterval`, calls the wrapper via `/bin/bash` (rq105 ops-wrapper convention), logs to umbrella `logs/stops_liveness/`, live ops topic pinned as explicit plist config |
| `scripts/stops_liveness_pager.sh` | wrapper: pinned-runtime `PYTHONPATH`, runs the umbrella checker, pages ntfy on STALE(1)/CORRUPT(2)/**crash(any other)**, exit 70 on page-delivery failure; `--test-fire STALE\|CORRUPT` emits one marked drill page, nonzero on delivery failure |
| `scripts/install_stops_pager.sh` | echo-first installer: `install`/`uninstall` are DRY-RUN unless `--apply`; `status` read-only; `test-fire` routes to the wrapper; idempotent (re-copy only on drift, bootout-then-bootstrap converges) |
| `tests/test_stops_liveness_pager.py` | 17 hermetic tests: plist shape + live-topic pin, page/no-page per checker exit class against a local ntfy recorder, delivery-failure exit codes, installer dry-run/apply/uninstall/status with a recording launchctl stub |

## Design facts (verified 2026-07-11, read-only)

- Checker: `RenQuant/scripts/check_software_stops_liveness.py` (umbrella ops
  tooling; watchdog arithmetic lives in the pinned
  `renquant_pipeline.software_stops` so checker and heartbeat-stamper share
  one implementation). Exit contract 0 OK / 1 STALE / 2 CORRUPT.
- `renquant_pipeline` is NOT installed in the umbrella venv — bare invocation
  is `ModuleNotFoundError` (this is precisely why "scheduled nowhere" also
  meant "would not have run"). The wrapper exports
  `.subrepo_runtime/repos/renquant-pipeline/src` + `renquant-common/src`;
  verified invocation returns exit 0,
  `OK: no software-stop registry … the layer has never armed a stop`.
- Live ops topic: `renquant` — same channel as the live sell-only loop
  (`intraday_sell_104.sh` `NTFY_TOPIC="renquant"`). Pinned in the plist env
  AND the wrapper default; test-asserted equal.
- Schedule: all-day 600s `StartInterval` (simplest robust schedule); the
  checker itself returns OK off-session via the canonical market calendar, so
  market-hours gating lives in exactly one place. Registry default:
  `RenQuant/data/rq105/software_stops.alpaca.json`.
- The wrapper — not the checker's best-effort `--ntfy-topic` — owns paging,
  so delivery failure is detectable (exit 70) and a checker *crash* pages
  instead of dying dark. No double-page: the checker is invoked without
  `--ntfy-topic`.

## Honest alert-latency envelope vs the §3.4 15m number

The staleness budget rides in the registry snapshot
(`max_staleness_minutes`, default 30; sell-loop heartbeat cadence 12m).
STALE therefore flips ~18m after the FIRST missed pass (i.e. on the second
consecutive miss), and this pager adds ≤10m detection cadence: **first page
lands ~18–28m after the first missed pass**. Meeting the literal §3.4
"page ≤15m of the scheduled pass" requires the ARMING side to stamp a
tighter `max_staleness_minutes` into the registry (pipeline-owned knob,
carried per-snapshot by design) or an operator sign-off accepting this
envelope — a policy decision recorded at stage-3 enablement, not something
this ops package can decide. The 60m response half of the SLA is exactly
what the test-fire drill measures.

## Landing sequence (operator grant required — landing-actions ask-first)

1. Operator grant.
2. `scripts/install_stops_pager.sh install` — review the echoed commands.
3. `scripts/install_stops_pager.sh install --apply`.
4. `scripts/install_stops_pager.sh test-fire STALE` — one marked synthetic
   page to the live topic; record page-delivery timestamp and operator
   response time vs the 15m/60m §3.4 SLA (#471 shortlist item 2's required
   demo). Nonzero exit = delivery failed = landing NOT done.
5. `scripts/install_stops_pager.sh status` on the next market day — confirm
   scheduled checks are logging.

## Discipline

Read-only on the umbrella and all primary checkouts (built from a scratchpad
clone); nothing installed, no launchd/live-tree mutation, no orders. The one
network action in this package (`test-fire`) runs only when the operator
invokes it.
