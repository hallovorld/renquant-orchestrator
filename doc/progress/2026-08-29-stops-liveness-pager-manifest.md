# Progress: PREPARATION — software-stop liveness pager: pinned-run plist + installer manifest guard (fractional chain, step 5; nothing declared, nothing installed)

2026-08-29, r2 after Codex review of orch#1077. Prepares — does NOT declare
on the manifest and does NOT install — the software-stop liveness pager.
Nothing here runs at merge time: no `launchctl`, no write to
`~/Library/LaunchAgents`, no live-tree or `-run` mutation, no daily page.

## Bottom line

- The pager plist now executes the wrapper from the **pinned `-run`
  checkout** — the checkout every other manifested `com.renquant.*` job runs
  from — instead of the dev working tree
  `[VERIFIED — deploy/com.renquant.stops-liveness.plist:52 before → :86 after]`.
- The installer refuses (exit 4) to arm a plist that is not in
  `ops/launchd_manifest.json` or disagrees with its entry (`scripts/install_stops_pager.sh:279-339`);
  the drift scan's resolver now inspects a manifested `scripts/` wrapper
  instead of reporting it as an unowned foreign path (`ops/run_surface_drift_check.py:977-987`).
- **The manifest entry is deferred** (Codex on #1077, agreeing with my own
  flag in r1): a manifested-but-uninstalled job makes the daily drift scan
  page the ops topic every day — a standing false positive on the channel
  that must carry real stop-liveness failures. The entry, the install and
  the test-fire land together in ONE landing PR, in one controlled window.
- **SLA: NOT SATISFIED — open decision item for the operator** (arithmetic
  below). Until one of the two compliance routes lands, this job is **not
  eligible to install and does not count as step-5 evidence** for the
  `software_stops` config row.

## Revision r2 — what changed vs r1 (visible corrections)

| r1 | r2 |
|---|---|
| `ops/launchd_manifest.json` +1 entry | REMOVED — deferred to the landing PR |
| `PENDING_INSTALL = {"com.renquant.stops-liveness"}` in `tests/test_run_surface_drift_check.py` | REMOVED — file untouched |
| tests asserting the committed manifest carries the entry / `check_launchd_surface` reports "manifested-but-missing" / not-loaded report classification | REMOVED (5 tests); replaced by a deferral test that pins the entry ABSENT and `install` refused, and tests that build the future entry via `scan_launchd_plists` on the fly |
| r1 bottom line said "18–28 min vs ≤15" as a flag | r2 states NOT SATISFIED with both routes as an OPEN decision, in the doc and the plist header |
| title "on the reviewed launchd surface" | "PREPARATION" |

## What the job does (unchanged by r2)

`deploy/com.renquant.stops-liveness.plist` → `/bin/bash
/Users/renhao/git/github/renquant-orchestrator-run/scripts/stops_liveness_pager.sh`.
The wrapper resolves the pinned `renquant-execution`/`-pipeline`/`-common`
checkouts through the R-PIN runtime inventory
(`~/.renquant/deploy/runtime-inventory.json`, read via
`renquant_orchestrator.deployment_manifest.load_runtime_inventory`;
`scripts/stops_liveness_pager.sh:165-236`) and runs the checker
`python -m renquant_execution.software_stops_liveness --data-root <root> --broker alpaca`
(`renquant-execution/src/renquant_execution/software_stops_liveness.py`,
`check()` :195, exit 0/1/2 = OK/STALE/CORRUPT). The wrapper pages the ops
ntfy topic on STALE, CORRUPT, checker crash or pin-resolution failure, and
exits 70 when the page itself cannot be delivered (`:250-276`).

| item | value | provenance |
|---|---|---|
| cadence | `StartInterval` 600 s (10 min), all day, `RunAtLoad` false | `[VERIFIED — plist :88-91]` |
| session gating | checker returns OK off-session; gating lives in ONE place | `[VERIFIED — software_stops_liveness.py:163-193, :233-237]` |
| registry the checker reads | `<RENQUANT_STOPS_PAGER_DATA_ROOT>/data/rq105/software_stops.alpaca.json`, data root `~/.renquant/runtime/software-stops` | `[VERIFIED — plist :132-133; software_stops_liveness.py:314-336; renquant-pipeline software_stops.py:121,141-154]` |
| staleness budget | `max_staleness_minutes: 30.0`, `enabled: false`, `registry_path: data/rq105/software_stops.json` in the pinned strategy-104 config | `[VERIFIED — RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json:700-705]` |
| ntfy topic | `renquant` via plist `EnvironmentVariables` (reviewed arming-time configuration, Codex r2 on #460) | `[VERIFIED — plist :106-107]` |
| topic parity with rq105 jobs | rq105 wrappers page through umbrella `scripts/notify.sh`: `$NTFY_TOPIC` env → `NTFY_TOPIC=` line in `RenQuant/.env` → default `renquant`; `.env` carries NO `NTFY_TOPIC` line and `intraday_sell_104.sh:26` hard-codes `renquant` — the fleet topic is the public default, not a secret | `[VERIFIED — RenQuant/scripts/notify.sh:14,35-42; .env probed for the key only, value not printed]` |
| stdout/stderr | `~/.renquant/ops/stops-liveness/launchd.{out,err}.log` | `[VERIFIED — plist :92-95]` |
| logs NOT under `RenQuant/logs/rq105/` | Codex review of the package's prior revision (2026-07-11): no new umbrella log path; pinned by `test_plist_parses_and_schedules_the_wrapper` | `[VERIFIED — tests/test_stops_liveness_pager.py:178-196; scripts/install_stops_pager.sh:41-46]` |

Deviations from the original brief, kept deliberately: cadence stays 600 s
(the `I` term below; shorter = tighter); logs stay under `~/.renquant/ops/`;
the plist stays at `deploy/` (`install_stops_pager.sh:30`); the topic is
plist configuration resolving to the same literal as the umbrella default.

## SLA — NOT SATISFIED (open decision item)

Design: `doc/design/2026-07-02-s-frac-fractional-v2.md:268-281` — "a missed
pass must page within 15 minutes of the scheduled pass; the runbook response
... within 60 minutes of the page"; scorecard row "Pager/SLA proof" MISSING in
`doc/research/2026-07-11-enablement-evidence-floor-stops-fractional.md:272`.

Worst-case page latency after a pass missed at T0
`[DERIVED — formula doc/progress/2026-07-11-stops-liveness-pager-package.md:654-664; inputs re-read 2026-08-29]`:

```
page_time = T0 + (B − C) + I + D
  B = 30 min  max_staleness_minutes (pinned config :703)
  C = 12 min  sell-only loop cadence (com.renquant.intraday104; pipeline software_stops.py:123-126)
  I = 10 min  this plist's StartInterval (:89)
  D           page delivery — measured by the test-fire drill
→ STALE flips 18 min after the first missed pass; first page lands 18–28 min + D.
   Design target: ≤ 15 min.  Status: NOT MET.
```

Two ways to comply — **neither is chosen here; the operator decides**:

- **(a) config change** lowering `execution.software_stops.max_staleness_minutes`
  in the strategy-104 config — a production-config write, so it needs its own
  LONG-ledger row (as rows 2a–2c did). Bound: `B − C + I ≤ 15` ⇒ **B ≤ 17 at
  the current 10-min interval**, or **B ≤ 22 if `StartInterval` is shortened
  to 300 s (5 min)** `[DERIVED — same formula; D not included]`. Note the
  trade-off is arithmetic, not a recommendation: at B ≤ 22 a single pass more
  than 10 min late trips STALE.
- **(b) explicit operator exception** accepting the measured 18–28 min + D
  envelope, per the design's sign-off clause (`design :273`).

Until (a) or (b) lands: **not eligible to install; not step-5 evidence.**

## Landing PR (separate; NOT this PR)

One PR, one controlled window, after (1) the registry writer stamps the
neutral data root (orchestrator seeder PR in flight) — today neither
`~/.renquant/runtime/software-stops/…` nor `RenQuant/data/rq105/software_stops.json`
exists `[VERIFIED — ls, 2026-08-29]`, so `install --apply` would be refused by
the registry guard (`install_stops_pager.sh:213-277`) anyway; (2) the `-run`
checkout synced to a main containing the pinned-run plist; (3) the SLA
decision above. Contents of that PR:

- `ops/launchd_manifest.json` entry for `com.renquant.stops-liveness`,
  emitted by `run_surface_drift_check.scan_launchd_plists` (never typed);
  the exact-equality allow-list in `tests/test_run_surface_drift_check.py`
  (`PENDING_INSTALL`) is NOT used — the plist is installed in the same window;
- deletion of `test_committed_manifest_does_not_declare_the_job_yet_so_install_is_refused`
  (it goes red the moment the entry lands — by design);
- the install and the drill, executed under the landing grant:

```
cd /Users/renhao/git/github/renquant-orchestrator-run
scripts/install_stops_pager.sh install            # dry-run: manifest guard + registry-guard note + exact commands
scripts/install_stops_pager.sh install --apply    # manifest guard → registry guard → cp plist → bootout || true → bootstrap gui/$UID
scripts/install_stops_pager.sh status
scripts/install_stops_pager.sh test-fire STALE    # one marked page to the live topic
```

Test-fire record (in a dated `doc/progress/<date>-stops-pager-drill.md`):
`T_send` = the wrapper's `page DELIVERED at <stamp>` stdout line
(`scripts/stops_liveness_pager.sh:123-141`); `T_receive` = device
notification timestamp; `T_ack` = operator acknowledgement;
`D = T_receive − T_send` (feeds the envelope), `R = T_ack − T_receive`
(respond ≤ 60 min). The drill body itself states the 18–28 min gap
(pinned by `test_test_fire_emits_one_marked_page_and_exits_zero`).
Recording format `[ASSUMED — no prior drill record exists]`.

## Revert

Reverting this PR restores the dev-tree `ProgramArguments`, drops the
installer guard and the resolver rule; there is no manifest entry and no
machine state to undo. (The landing PR's revert: `scripts/install_stops_pager.sh
uninstall --apply` = bootout + rm plist, plus a PR removing its manifest entry.)

## Place in the chain

Staged plan item 2(b) of `doc/research/2026-08-24-goal1-closeout.md:93-97`
("software-stops stage-3 arming per its own packet (liveness pager +
operator sign-off)"). This PR = preparation of the scheduling surface;
landing PR = manifest entry + install + test-fire, gated on writer migration
+ SLA decision; then operator sign-off of the machine-death bound; then
`execution.software_stops.enabled: true` under its own LONG-ledger row.
Step numbering "5" follows the parent session's chain
`[ASSUMED — the numbered chain is not in a merged doc]`.

## Files

- `deploy/com.renquant.stops-liveness.plist` — ProgramArguments → `-run`; header: deferral + SLA NOT SATISFIED + open decision.
- `ops/run_surface_drift_check.py` `_scheduled_wrappers` — `/scripts/` resolves like `/ops/`.
- `scripts/install_stops_pager.sh` — `guard_manifest_agreement` (exit 4), before the registry guard; `RENQUANT_STOPS_PAGER_MANIFEST` test-only override; `PYTHONDONTWRITEBYTECODE=1`.
- `tests/test_stops_liveness_pager.py` (+8 tests, all against temp manifests produced by the scanner or fake fixtures; one deferral test), `tests/test_wrapper_pythonpath_roots.py` (+1).
- `doc/memory/mid-term/fractional-enablement-chain.md` — MID proposal (new workstream file).
- NOT touched: `ops/launchd_manifest.json`, `tests/test_run_surface_drift_check.py`.

## Tests

CI collection: `make test` = `python -m pytest -q` with `testpaths = ["tests"]`
(`Makefile:22-23`, `pyproject.toml:42-54`); `ci.yml:92-97` runs `make test`
in the "Full multirepo test" job, so tests added to existing files under
`tests/` are collected without naming them anywhere.

Runner: `PYTHONPATH=src:<sibling src roots as pyproject lists them> RenQuant/.venv/bin/python -m pytest -q -p no:cacheprovider -o addopts=""`
in an isolated worktree of origin/main `75274096` (so the two round-8
real-sibling tests skip by design — no siblings at the worktree's parent).

| set | result | provenance |
|---|---|---|
| `tests/test_stops_liveness_pager.py` | 37 passed, 2 skipped (was 29 + 2 skipped: +8) | `[VERIFIED — run 2026-08-29, r2]` |
| `tests/test_run_surface_drift_check.py` (untouched) | 31 passed | `[VERIFIED — run 2026-08-29, r2]` |
| `tests/test_wrapper_pythonpath_roots.py` | 21 passed (+1) | `[VERIFIED — run 2026-08-29, r2]` |
| `tests/test_manifested_not_loaded_report.py` (untouched) | 7 passed | `[VERIFIED — run 2026-08-29, r2]` |
| the four files together | 96 passed, 2 skipped | `[VERIFIED — run 2026-08-29, r2]` |
| full suite, clean `origin/main` baseline | 17 failed, 6757 passed, 10 skipped (3:05) | `[VERIFIED — detached worktree run 2026-08-29]` |
| full suite, this branch r2 | 17 failed, 6766 passed, 10 skipped (3:10); failure set IDENTICAL to baseline (`diff` of sorted FAILED lines empty) | `[VERIFIED — run 2026-08-29, r2]` |

The 17 pre-existing failures are `test_shadow_ab_daily_script.py` (13),
`test_shadow_serving_skips_leave_evidence.py` (2), `test_cli.py` (1),
`test_goal3_public_export_resolution.py` (1) — untouched by this change.
No test in this PR passes because the committed manifest carries the entry:
it does not, and `test_committed_manifest_does_not_declare_the_job_yet_so_install_is_refused`
pins that (the landing PR deletes it).
