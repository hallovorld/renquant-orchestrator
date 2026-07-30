# The jobs run from a checkout 110 commits behind, and no check could see it   (PR pending)

STATUS:    delivered
WHAT:      Adds `ops/referenced_checkout_freshness.py`: derives its subject from the paths
           the launchd jobs actually reference, and measures each against a **fetched**
           `origin/main`. Read-only.
WHY/DIR:   GOAL-5 / GOAL-1. `run_surface_drift_check.py` validates
           `.subrepo_runtime/repos/*` against `subrepos.lock.json` — internal consistency
           between two copies. It never asks whether the pin is current, so a stale pin
           reports clean forever, and it never looks at the checkout the jobs execute from.
EVIDENCE:  §1.
NEXT:      Syncing a live run checkout is a machine-landing action and needs operator
           authorization (orch#636). This PR only makes the gap visible.

## §1 EVIDENCE

`[VERIFIED — ops/referenced_checkout_freshness.py, 2026-07-30]`

| checkout | commits behind `origin/main` | jobs referencing it |
|---|---:|---:|
| `renquant-orchestrator-run` | **110** | **17** |
| `renquant-orchestrator` | 22 | 1 |
| `RenQuant` (umbrella) | skipped — git is never run inside it | 30 |

The copy the drift scan *does* check, `.subrepo_runtime/repos/renquant-orchestrator`, is
**195 commits behind** and is referenced by no launchd job at all
`[VERIFIED — git rev-list against a fetched reference]`.

So three orchestrator checkouts exist, the jobs run from the one nobody edits, and the
scan validates a fourth against a pin rather than against `origin/main`.

## §2 THE DEFECT THIS TOOL HAD, IN ITS FIRST VERSION

The first implementation ran `git rev-list --count HEAD..origin/main` **inside the
checkout being measured**. `renquant-orchestrator-run` reported **0 behind** — because a
deployment copy that has not fetched carries a stale `origin/main` ref and was being asked
to compare itself against its own outdated idea of the truth.

**That is precisely the defect this tool exists to catch, occurring inside the tool.** It
now resolves a *reference* checkout (`-run` → its dev sibling), fetches **only there**, and
counts the distance from that vantage. A source-level test pins that `rev-list` runs
against `ref_repo`, and `reference_repo_for` is unit-tested.

## §3 The one number that is not a measurement

`MAX_COMMITS_BEHIND = 20`, and the docstring says it is **chosen, not derived**. Alarming
on any drift fires on every merge and gets muted within a day; alarming only on a large
number lets a week of fixes sit unshipped. 20 is roughly two review cycles at this repo's
current cadence — a judgement call, labelled as one.

## §4 The umbrella is skipped, and says so

30 jobs run from the umbrella and it is **not** measured: `git` is never run inside that
shared live tree, where a sub-agent's `git reset --hard` once caused an incident. It is
reported as `SKIPPED_UMBRELLA` with the reason rather than omitted, because dropping it
would make the output read as *everything measured is fine*. A test asserts both the skip
and that no `git -C` in the source targets the umbrella.

## §5 Suite

| tree | result |
|---|---|
| `origin/main`, separate worktree | 7 failed, 4579 passed, 5 skipped, 27 warnings in 119.58s (0:01:59) |
| this branch | 7 failed, 4590 passed, 5 skipped, 27 warnings in 121.98s (0:02:01) |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`

## §6 Live-surface impact

None. The tool is read-only and not wired into any scheduled job. It runs `git fetch`
**only** in dev checkouts under the GitHub root, never in the umbrella and never in a
`-run` deployment copy.
