# The checkout-freshness probe was wired to nothing

STATUS: complete. Adds a check to an existing daily job; installs no job, changes no
schedule, touches no checkout. **Does not itself advance anything** — see Ordering.

WHAT: `run_surface_drift_check` now runs `ops/referenced_checkout_freshness.py` and
reports its findings, and the probe's failing-status list is defined once instead of
twice.

WHY/DIR: the drift scan's own docstring names this as invisible-divergence **class 1**
— *"run checkouts drifting from their reviewed refs — the renquant-orchestrator-run
checkout sat ~130 commits behind origin/main"*. Nothing scheduled measured it.

`check_checkout()` compares HEAD against a declared **pin**. A checkout with no pin,
or whose pin is itself old, passes that while being months stale. Lag was never
measured.

`ops/referenced_checkout_freshness.py` measures it, correctly, and was **wired to
nothing**: not to a launchd job, not named in `ops/launchd_manifest.json`. Run by hand
on 2026-08-05:

```
SKIPPED_UMBRELLA   RenQuant                     - behind   25 job(s)
STALE              renquant-orchestrator-run   36 behind   21 job(s)
                     36 commits behind origin/main (bound 20) —
                     anything merged in those commits is NOT what runs
```

[VERIFIED — `python ops/referenced_checkout_freshness.py`, rc=1, 2026-08-05]

**21 scheduled jobs run from a checkout 36 commits (≈4 hours) behind `main`.** It does
not carry orch#830 (`grep -c GATE_WINDOW_DAYS` → 0), so a fix merged that morning was
not what ran. A correct instrument that nobody runs is the same as no instrument —
`deployed-but-dark`.

## The trap the probe already documents, and which I walked into

Asked from inside the run checkout, `git rev-list --count HEAD..origin/main` returns
**0**: that checkout has not fetched, so its own `origin/main` ref points at its own
HEAD. It is comparing a copy against its own outdated idea of the truth, with total
confidence. The real figure, counted in a **fetched reference** checkout, is 36.

The probe counts distance in the reference tree, fetches **only** there (a dev tree we
own, never the run checkout), and **requires** that fetch to succeed — a failure yields
`UNMEASURABLE`, not `FRESH`. Its own comment records that its first version had this
exact bug and reported 0 behind against a true 110.

## One definition of "failing", not two

The probe's `main()` inlined `("STALE", "NOT_A_CHECKOUT", "UNMEASURABLE")`. Writing
that list again in the drift check is how one copy quietly stops covering a status the
other adds later, so it is now `FAILING_STATUSES` + `failing(report)`, used by both.
`UNMEASURABLE` is in the failing set deliberately: **could-not-check is not
checked-and-found-fresh.**

`test_the_failing_set_comes_from_the_PROBE_not_a_second_list` injects a probe that
calls a `STALE` result fine and asserts the drift check *defers* — it must not
re-derive the verdict on its own.

## Ordering, stated plainly

This check ships into a job that runs **from the stale checkout**, so it does not
execute until that checkout advances once. Advancing it is a live-surface sync and
belongs to the operator. The value here is that after one advance, silent drift cannot
recur unnoticed — not that this change fixes today's lag. Saying so rather than letting
the merge imply otherwise: **merged is not deployed.**

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| the probe was unwired | absent from every plist and from `launchd_manifest.json` | [VERIFIED — `grep` over `~/Library/LaunchAgents/*.plist` and the manifest] |
| current lag | **36 commits**, bound 20, **21 jobs** | [VERIFIED — probe run, and independently `git rev-list --count b1e325a1..origin/main` in the fetched dev tree] |
| the run checkout self-reports 0 behind | yes | [VERIFIED — `git -C …-run rev-list --count HEAD..origin/main` → 0, its `origin/main` = its own HEAD] |
| #830 absent from the run checkout | `grep -c GATE_WINDOW_DAYS` → 0 | [VERIFIED] |
| new tests | **6**, all injecting a fake probe — no network, no real checkout | [VERIFIED — `pytest -q tests/test_run_surface_drift_check.py`: 24 passed] |
| the new tests are load-bearing | all 6 fail against the pre-change module | [VERIFIED — `git stash push ops/…`, re-run: 6 failed] |
| the probe's own suite | 19 passed (refactor is behaviour-preserving) | [VERIFIED — `pytest -q tests/test_referenced_checkout_freshness.py`] |
| full suite | 5881 passed, 16 failed | [VERIFIED — `make test`; 15 are the standing host-environmental set and the 16th is the live-state test fixed in orch#849, not yet merged] |

artifact: none. The change adds a call into an existing daily check; it produces no
  artifact, and the probe it calls is read-only apart from a `git fetch` in the
  reference dev checkout (never in the checkout being measured).
prod or exp: production monitoring path — `run_surface_drift_check` runs from a
  scheduled job. No job is installed, no schedule changes, and no checkout is advanced
  by this PR; the check only reports.
existing data: yes — the finding was derived from checkouts and a manifest that already
  exist (`ops/launchd_manifest.json` for the referenced paths, the run checkout's HEAD,
  and `origin/main` in the fetched dev tree). Nothing was generated to support it.
best-known?: for the measurement, yes — counting distance in a fetched reference tree
  is the only method that survives the run checkout's own `origin/main` being stale,
  which is the defect being caught. For the WIRING there is a better end state: a
  reviewed launchd entry of its own, so the check does not depend on the staleness of
  the very checkout it measures. That needs an operator grant, so this ships the
  reviewable half.
scope: one new function in `run_surface_drift_check.py` plus its call site, and a
  two-line de-duplication in `referenced_checkout_freshness.py` (`FAILING_STATUSES` /
  `failing()`), which is behaviour-preserving — its own suite is unchanged and green.

NEXT: the operator grant. `renquant-orchestrator-run` is 36 commits behind with 21 jobs
running from it; advancing it is a live-surface sync and not mine to do. This check
begins executing only after that first advance — stated here rather than left for the
merge to imply.
