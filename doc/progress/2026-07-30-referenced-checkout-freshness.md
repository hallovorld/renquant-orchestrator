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

## §2a CORRECTION — the fetch path had the same defect, one layer deeper

Review: the fetch subprocess return code was discarded, so a network or authentication
failure left the reference checkout's own `origin/main` stale and the later `rev-list`
reported a confident **FRESH** against an old ref. **That is the exact stale-reference
failure this tool exists to detect, recreated on the fetch path.**

Third layer of the same shape in one tool: first the subject was measured against its own
stale ref; then the reference was fetched but the fetch was not required to succeed. Both
times the failure mode was *a verdict produced from an input that was never confirmed*.

Now: a non-zero fetch returns **UNMEASURABLE** with the git error attached; `origin/main`
is re-verified **after** a successful fetch, because a fetch can succeed against a remote
that has no `main`, which would leave `rev-list` comparing against nothing; and neither
path can emit `commits_behind`. Six tests cover it — three fetch return codes, the
post-fetch resolve failure, a non-zero process exit, and
`test_the_unmocked_path_still_measures` so the refusals are attributable to the mocks
rather than to `measure()` having become unconditionally UNMEASURABLE.

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
| this branch | 7 failed, 4597 passed, 5 skipped, 27 warnings in 117.09s (0:01:57) |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`

## §6 Live-surface impact

None. The tool is read-only and not wired into any scheduled job. It runs `git fetch`
**only** in dev checkouts under the GitHub root, never in the umbrella and never in a
`-run` deployment copy.

## CI fix — three tests measured the operator's disk

CI failed on `test_a_failed_fetch_yields_UNMEASURABLE_not_FRESH`,
`test_origin_main_missing_after_a_SUCCESSFUL_fetch_is_also_UNMEASURABLE` and
`test_the_unmocked_path_still_measures`. All three called
`fr.measure("renquant-orchestrator")`, which resolves under `GITHUB` =
`/Users/renhao/git/github`. That path is not a checkout on a runner, so every one of
them got `NOT_A_CHECKOUT` instead of the verdict it was asserting.

The worst of the three is `test_the_unmocked_path_still_measures`, whose entire job is
**anti-vacuity** — proving the refusals above it come from the mocks rather than from
`measure()` having become unconditionally UNMEASURABLE. A test that can only measure on
one machine cannot make that promise anywhere else, so the guarantee it was written to
provide did not exist in CI.

Fixed with a `github_root` fixture that builds a **real** git world in `tmp_path` — a
bare upstream with a seeded `main`, cloned into `<root>/renquant-orchestrator` so
`origin/main` genuinely resolves — and points `fr.GITHUB` at it. Nothing about git is
mocked; the code paths exercised are exactly the production ones.

`test_the_fixture_really_is_a_measurable_checkout` guards the fixture itself: if it ever
stops producing a measurable repo, every test using it would silently degrade to
asserting `NOT_A_CHECKOUT` — passing while checking nothing.

**Scoped deliberately.** Only the three genuinely-broken tests moved onto the fixture.
My first pass also applied it to `test_a_failed_fetch_makes_the_run_exit_nonzero`, which
**passes in CI** — the fixture root holds one checkout, so `scan()` finds no results and
`main()` returns 2 rather than 1. Reverted. Over-applying a fixture to tests that were
already correct is how a green suite starts testing the fixture instead of the code.

`[VERIFIED — this session]` 19 passed; the three CI-failing tests also pass with
`RQ_GITHUB_ROOT` pointing at a nonexistent path.
