# GOAL-1 — the ops fleet merged this week is not on the machine that runs it

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-1 (shadow reliability gates)

## Bottom line

Every scheduled job executes out of `renquant-orchestrator-run`. Measured
`[本次实测 2026-08-01]`, that checkout is **158 commits behind `origin/main`**:

| | |
|---|--:|
| `ops/` files on `origin/main` | **80** |
| present in the deployed checkout | 60 |
| **entirely absent from the machine** | **20** |
| of the 60 present, **differing** | **11** |
| **total gap** | **31 of 80** |

**Absent includes `ops/ops_audit.py` — the aggregator itself** — plus `run_ops_audit.sh`,
its plist, and nine detectors it aggregates: `failclosed_env_check`, `gate_stamp_parity`,
`wf_cut_independence`, `shadow_lane_preflight`, `ack_ledger_audit`,
`strategy_config_primary_parity`, `booster_identity_census`, `booster_divergence_probe`,
`subrepo_pin_lag_check`, `blind_notifier_scan`, `evidence_census`.

## How I found it, and the mistake that nearly hid it

I ran the shadow sentinel and its lane-declared-but-unwatched check (orch#702, merged)
printed nothing. My first conclusion was that the functions did not exist — measured
against **my own working checkout, which was on a feature branch 131 commits behind
`origin/main`**. Checking the wrong object is a standing entry on my register; the
functions are on `origin/main` at lines 1072 and 1113.

Re-run correctly, the real answer was worse: the check exists, is wired, and runs only when
`--config` is passed — the installed plist passes none — **and the deployed file contains
`unwatched_config_lanes` zero times.** On every scheduled run it does not merely skip; it
is not there.

## Why a commit count was not enough

`run_surface_drift_check` already alarms on this: *"orchestrator-run: HEAD 6828b29cdc3c !=
expected 8a012988c5f3"*. That is correct and it fires. But a commit id does not say what
the drift **costs**, and 158 reads the same whether the gap is a docstring or the entire
audit fleet. `ops/deployed_ops_surface_gap.py` reports the contents: absent, divergent, and
**present-only-on-the-machine** kept separate, because a retired-but-installed tool is not
the same condition as a missing one and folding them together would describe a sync as
removing something it does not.

## Scope

Read-only. It **does not sync** — advancing the deployed checkout is a machine landing and
the operator's call; a test asserts the source contains no `pull`/`checkout`/`reset`/
`fetch`/`merge`/`clean`, because that class of action has clobbered uncommitted operational
fixes here before. No job was installed, edited or disabled.

## Not claimed

That every absent file *should* be deployed — some may be deliberately unscheduled, and
`ops_audit`'s own `UNSCHEDULABLE_YET` list exists for exactly that. That syncing is safe
right now; that judgement needs the diff read, which is what this produces. That 158 is the
relevant number — **31 of 80** is.

## Tests

9, on a synthetic upstream/deployed pair rather than the real machine: a test that asserts
against the live checkout passes or fails by how recently someone synced it. Absent,
divergent, unchanged and machine-only are each pinned separately, and a non-checkout or an
unresolvable ref **SKIPs with 3** rather than reporting a clean machine.

Suite: **5193 passed, 2 skipped**, run before the push.
