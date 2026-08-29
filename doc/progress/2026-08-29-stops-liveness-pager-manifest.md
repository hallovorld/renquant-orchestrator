# Progress: software-stop liveness pager on the reviewed launchd surface (fractional chain, step 5)

2026-08-29. Prepares — does NOT install — the scheduling surface for the
software-stop liveness pager. Nothing here runs at merge time: no `launchctl`,
no write to `~/Library/LaunchAgents`, no live-tree or `-run` mutation. Arming
is a separately granted landing step (landing-actions ask-first).

## Bottom line

- `com.renquant.stops-liveness` is now a first-class entry of the reviewed
  launchd surface (`ops/launchd_manifest.json`) and its plist executes the
  wrapper from the PINNED run checkout — the same checkout every other
  manifested `com.renquant.*` job runs from — instead of the dev working tree
  the 2026-07-11 template pointed at
  `[VERIFIED — deploy/com.renquant.stops-liveness.plist:52 before → :74 after this change]`.
- The installer refuses to arm a plist that disagrees with the manifest
  (exit 4, both modes; `--apply` additionally requires the program target to
  exist here). Without this, the first drift-scan firing after an install
  from a stale checkout would page "silent containment / job swap?".
- **Decision the operator still owns**: the alert-latency envelope is
  ~18–28 min after the first missed sell-only pass, which does NOT meet the
  design's page ≤15 min. Step 5 makes the page *schedulable and measurable*;
  it does not close that gap (see "SLA" below).
- **What this changes on the run host after merge**: the daily
  `com.renquant.run-surface-drift` scan will report
  `launchd: manifested job com.renquant.stops-liveness missing from disk`
  as a PROBLEM (and page the ops topic with it) every day until
  `install --apply` lands. That is the CONTAINMENT PROTOCOL's designed
  reminder (CLAUDE.md rule 5c; precedent `com.renquant.rq104-silent-refusal`,
  `tests/test_run_surface_drift_check.py:307-332`), and the declared-but-
  uninstalled allow-list names it explicitly
  (`tests/test_run_surface_drift_check.py` `PENDING_INSTALL`). If the operator
  prefers silence until the writer migration lands, the manifest hunk can be
  split into the install PR — flagged, not decided here.

## What the job does

`deploy/com.renquant.stops-liveness.plist` → `/bin/bash
/Users/renhao/git/github/renquant-orchestrator-run/scripts/stops_liveness_pager.sh`.
The wrapper resolves the pinned `renquant-execution`/`-pipeline`/`-common`
checkouts through the R-PIN runtime inventory
(`~/.renquant/deploy/runtime-inventory.json`, read via
`renquant_orchestrator.deployment_manifest.load_runtime_inventory`;
`scripts/stops_liveness_pager.sh:165-236`) and runs the checker
`python -m renquant_execution.software_stops_liveness --data-root <root> --broker alpaca`
(`renquant-execution/src/renquant_execution/software_stops_liveness.py`,
`check()` at :195, exit 0/1/2 = OK/STALE/CORRUPT). The wrapper pages the ops
ntfy topic on STALE, CORRUPT, checker crash, or pin-resolution failure, and
exits 70 when the page itself cannot be delivered (`:250-276`).

| item | value | provenance |
|---|---|---|
| cadence | `StartInterval` 600 s (10 min), all day, `RunAtLoad` false | `[VERIFIED — deploy/com.renquant.stops-liveness.plist:76-79]` |
| session gating | checker returns OK off-session ("market session closed — armed stop(s) cannot be evaluated off-session by design"); gating lives in ONE place | `[VERIFIED — software_stops_liveness.py:163-193, :233-237]` |
| registry the checker reads | `<RENQUANT_STOPS_PAGER_DATA_ROOT>/data/rq105/software_stops.alpaca.json`, data root `~/.renquant/runtime/software-stops` | `[VERIFIED — plist :120-121; software_stops_liveness.py:314-336; renquant-pipeline software_stops.py:121,141-154]` |
| staleness budget | `max_staleness_minutes: 30.0`, `enabled: false`, `registry_path: data/rq105/software_stops.json` in the pinned strategy-104 config | `[VERIFIED — RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json:700-705]` |
| ntfy topic | `renquant` via plist `EnvironmentVariables` (reviewed arming-time configuration, Codex r2 on #460) | `[VERIFIED — plist :94-95]` |
| topic parity with rq105 jobs | rq105 wrappers page through umbrella `scripts/notify.sh`: `$NTFY_TOPIC` env → `NTFY_TOPIC=` line in `RenQuant/.env` → default `renquant`; `.env` carries NO `NTFY_TOPIC` line and `intraday_sell_104.sh:26` hard-codes `renquant` — the fleet topic is the public default, not a secret | `[VERIFIED — RenQuant/scripts/notify.sh:14,35-42; .env probed for the key only, value not printed]` |
| stdout/stderr | `~/.renquant/ops/stops-liveness/launchd.{out,err}.log` | `[VERIFIED — plist :80-83]` |
| logs NOT under `RenQuant/logs/rq105/` | Codex review of the package's prior revision (2026-07-11): no new umbrella log path; pinned by `test_plist_parses_and_schedules_the_wrapper` | `[VERIFIED — tests/test_stops_liveness_pager.py:178-196; scripts/install_stops_pager.sh:41-46]` |

Deviations from the task brief, kept deliberately: (i) cadence stays 600 s
rather than ~12 min — it is the `I` term of the envelope below, and the test
suite pins it; (ii) logs stay under the neutral `~/.renquant/ops/` root per
the Codex-reviewed contract, not `RenQuant/logs/rq105/`; (iii) the plist stays
at `deploy/` because that is the path `install_stops_pager.sh:30` consumes;
(iv) the topic is plist configuration, resolved exactly as the umbrella's
fleet default resolves (same literal), not read from `.env` at run time —
the round-6 rule forbids the armed job depending on anything outside the
copied plist.

## SLA (design: page ≤15 min, respond ≤60 min)

Design source: `doc/design/2026-07-02-s-frac-fractional-v2.md:268-281`
("a missed pass must page within 15 minutes of the scheduled pass; the runbook
response ... within 60 minutes of the page"); scorecard row "Pager/SLA proof"
MISSING in `doc/research/2026-07-11-enablement-evidence-floor-stops-fractional.md:272`.

Worst-case page latency after a pass missed at T0
`[DERIVED — formula doc/progress/2026-07-11-stops-liveness-pager-package.md:655-664; inputs re-read 2026-08-29]`:

```
page_time = T0 + (B − C) + I + D
  B = 30 min  max_staleness_minutes (pinned config :703)
  C = 12 min  sell-only loop cadence (com.renquant.intraday104; pipeline software_stops.py:123-126)
  I = 10 min  this plist's StartInterval (:77)
  D           page delivery — measured by the test-fire drill
→ STALE flips 18 min after the first missed pass; first page lands 18–28 min + D.
```

Meeting "page ≤15 min" requires B ≤ 17 with I = 10 (B − C + I ≤ 15), i.e. a
`max_staleness_minutes` change on the ARMING side (strategy-104 config, its
own reviewed PR) — or an explicit operator acceptance of the 18–28 min
envelope. Step 5 records this; it does not choose.

## Install (after merge; ask-first landing grant; the agent does not run it unasked)

Preconditions: (1) the `-run` checkout synced to a main that contains this
change (the plist's target is `-run/scripts/stops_liveness_pager.sh` — today
identical to main's copy `[VERIFIED — diff -q, 2026-08-29]`, but the manifest
guard checks the file the operator's checkout carries); (2) a VALID registry
at `~/.renquant/runtime/software-stops/data/rq105/software_stops.alpaca.json`
— the registry guard refuses otherwise (`install_stops_pager.sh:213-277`);
today neither that path nor `RenQuant/data/rq105/software_stops.json` exists
`[VERIFIED — ls, 2026-08-29]`, so `--apply` is refused until the writer lands.

```
cd /Users/renhao/git/github/renquant-orchestrator-run
scripts/install_stops_pager.sh install            # dry-run: manifest guard + exact commands, changes nothing
scripts/install_stops_pager.sh install --apply    # manifest guard → registry guard → cp plist → bootout || true → bootstrap gui/$UID
scripts/install_stops_pager.sh status             # plist in sync? job loaded? last 3 log lines
```

After `--apply`, the drift scan's "missing from disk" line stops; the
`PENDING_INSTALL` entry in `tests/test_run_surface_drift_check.py` then goes
red on the operator machine by design and must be removed in the next PR.

## Test-fire procedure (STALE page) and latency record

```
scripts/install_stops_pager.sh test-fire STALE
```
posts ONE clearly marked synthetic page to the live topic
(`scripts/stops_liveness_pager.sh:123-141`, body begins `[TEST-FIRE STALE]`,
exit 0 delivered / 70 not delivered). Record, in a dated
`doc/progress/<date>-stops-pager-drill.md`:

1. `T_send` — the wrapper's `page DELIVERED at <stamp>` line (stdout);
2. `T_receive` — the notification timestamp on the operator's device;
3. `T_ack` — when the operator acknowledged (reply on the topic or a note);
4. `D = T_receive − T_send` (feeds the envelope), `R = T_ack − T_receive`
   (the respond ≤60 min half of the SLA).

The drill message itself states the 18–28 min envelope and that it does not
meet the 15-min target (pinned by `test_test_fire_emits_one_marked_page_and_exits_zero`).
This procedure's recording format is my proposal `[ASSUMED — no prior drill record exists]`.

## Revert

1. `scripts/install_stops_pager.sh uninstall --apply` — `launchctl bootout
   gui/$UID/com.renquant.stops-liveness || true`, then `rm -f
   ~/Library/LaunchAgents/com.renquant.stops-liveness.plist`
   (`install_stops_pager.sh` `uninstall` branch).
2. A reviewed PR removing the `com.renquant.stops-liveness` entry from
   `ops/launchd_manifest.json` and the label from `PENDING_INSTALL` — until it
   merges the drift scan reports "manifested job ... missing from disk" (the
   protocol's reminder, again by design).
3. Reverting only this PR (before any install) restores the dev-tree
   `ProgramArguments`, drops the manifest entry and the installer guard; no
   machine state to undo.

## Place in the chain

Staged plan item 2(b) of `doc/research/2026-08-24-goal1-closeout.md`
("software-stops stage-3 arming per its own packet (liveness pager +
operator sign-off)"). The 2026-07-11 packet left "pager scheduled nowhere,
page never test-fired" (`doc/research/2026-07-11-...:272`). This change is
the *scheduled on the reviewed surface* half; the evidence row for the
`software_stops` config flip still needs: writer migration → `install
--apply` → drill record (D, R) → operator sign-off of the envelope or a
`max_staleness_minutes` PR → then `execution.software_stops.enabled: true`
under its own LONG-ledger row. Step numbering "5" follows the parent
session's chain `[ASSUMED — the numbered chain is not in a merged doc]`.

## Files

- `deploy/com.renquant.stops-liveness.plist` — ProgramArguments → `-run`; header note.
- `ops/launchd_manifest.json` — +1 job (41), entry emitted by `scan_launchd_plists`.
- `ops/run_surface_drift_check.py` `_scheduled_wrappers` — resolves a manifested
  `/scripts/` wrapper of this repo like `/ops/` (otherwise the pythonpath scan
  reported the job as an unowned foreign path — a PROBLEM measured before the fix).
- `scripts/install_stops_pager.sh` — `guard_manifest_agreement` (exit 4), runs
  before the registry guard; `RENQUANT_STOPS_PAGER_MANIFEST` test-only override.
- `tests/test_stops_liveness_pager.py` (+11 tests), `tests/test_wrapper_pythonpath_roots.py`
  (+1), `tests/test_run_surface_drift_check.py` (`PENDING_INSTALL`).
- `doc/memory/mid-term/fractional-enablement-chain.md` — MID proposal (new workstream file).

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
| `tests/test_stops_liveness_pager.py` | 40 passed, 2 skipped (was 29 + 2 skipped: +11) | `[VERIFIED — run 2026-08-29]` |
| `tests/test_run_surface_drift_check.py` | 31 passed | `[VERIFIED — run 2026-08-29]` |
| `tests/test_wrapper_pythonpath_roots.py` | 21 passed (+1) | `[VERIFIED — run 2026-08-29]` |
| `tests/test_manifested_not_loaded_report.py` | 7 passed | `[VERIFIED — run 2026-08-29]` |
| every test file that reads `ops/launchd_manifest.json` (18 files) | 438 passed, 2 skipped, 1 failed → fixed (`PENDING_INSTALL`), then 99 passed / 2 skipped on the four files above | `[VERIFIED — run 2026-08-29]` |
| full suite, clean `origin/main` baseline | 17 failed, 6757 passed, 10 skipped (3:05) | `[VERIFIED — detached worktree run 2026-08-29]` |
| full suite, this branch | 17 failed, 6769 passed, 10 skipped (3:04); failure set IDENTICAL to baseline (`diff` of sorted FAILED lines empty) | `[VERIFIED — run 2026-08-29]` |

The 17 pre-existing failures are `test_shadow_ab_daily_script.py` (13),
`test_shadow_serving_skips_leave_evidence.py` (2), `test_cli.py` (1),
`test_goal3_public_export_resolution.py` (1) — untouched by this change.
The one failure this change introduced and then fixed was the designed one:
`test_declared_but_uninstalled_jobs_are_exactly_the_named_set` requires a
declared-but-uninstalled job to be NAMED in `PENDING_INSTALL`.
