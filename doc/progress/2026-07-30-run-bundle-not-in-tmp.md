# Run bundles were pointed at /tmp — evidence designed to disappear   (PR pending)

STATUS:    delivered
WHAT:      The two bridge jobs' `--bridge-bundle-output` targeted `/tmp/…`. Moved
           under the umbrella's `logs/` root, and added a guard that no scheduled job
           may persist a run bundle to `/tmp`.
WHY/DIR:   GOAL-5. This programme already has the exact failure: the live WF-gate
           incumbent's `sanity_manifest_path` is `/tmp/gbdt_manifest_abs.json` and
           **the file no longer exists**, so its PASS cannot be re-derived from its own
           record. A run bundle in `/tmp` reproduces that by construction — cleared on
           reboot, and overwritten every session because the flag takes a fixed path.
EVIDENCE:  §1.
NEXT:      Separate and larger: no production run bundle has been written since
           2026-07-21 (orch#631). This PR makes the destination durable; it does not
           make the daily run write one.

## §1 EVIDENCE

Changed, both in `src/renquant_orchestrator/scheduled_jobs.py`:

| job | before | after |
|---|---|---|
| `daily_live_runner_bridge` | `/tmp/renquant-daily-bridge-bundle.json` | `{root}/logs/daily_104/bridge_run_bundle.json` |
| `live_runner_bridge` | `/tmp/renquant-live-bridge-bundle.json` | `{root}/logs/live_104/bridge_run_bundle.json` |

`{root}` is `default_repo_root()` — the same substitution the launchd stdout/stderr
paths in this file already use, so the destination sits beside the session logs it
describes.

**Scope is deliberately narrow: run bundles only.** The rehearsal intermediates under
`/tmp/renquant-live-rehearsal/` are scratch by design and are untouched.

## §2 The guard, and the test that caught my guard checking nothing

5 tests. The load-bearing one asserts no scheduled job passes a `/tmp` path to
`--bridge-bundle-output`, paired with
`test_the_bundle_flag_is_still_present_so_the_guard_is_not_vacuous` — and **that
anti-vacuity test failed on my first version.**

I had scanned only `command` and `native_cutover_command`. The bridge jobs declare the
flag in **`rehearsal_command`**, so the guard iterated an empty set and would have
passed forever over nothing. The vacuity test is the only reason I noticed. Fifth time
tonight that a check of mine read a different object than the one I assumed; first time
one of my own guards caught it before the PR.

`test_the_guard_actually_fires_on_a_tmp_path` proves the detection logic rejects an
obvious `/tmp` bundle path, so the passing state means something.

## §3 A claim of mine this REFUTES

In orch#631 I wrote that the reviewed inventory *"says the daily run should persist a
bundle"* while `daily_104.sh` does not, and called it two records disagreeing.
**That was wrong.** The flag lives in `rehearsal_command`, not `command`
`[VERIFIED — inventory_payload() key inspection, this session]`. The inventory's
**production** command does not declare a bundle output either, so there is no
disagreement between the records — the flag is simply absent from both production
paths. Corrected on the issue rather than left standing.

## §4 Suite

| tree | result |
|---|---|
| `origin/main`, separate worktree |  |
| this branch |  |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`

## §5 Live-surface impact

None. `scheduled_jobs.py` is an inventory; the running daily job invokes
`scripts/daily_104.sh`, which passes no bundle flag at all. This changes what the
inventory *declares*, so that when the flag is eventually wired the destination is
already durable rather than `/tmp`.
