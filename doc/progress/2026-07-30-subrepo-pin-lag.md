# Two surfaces, two baselines — and the weaker one reads like the stronger

**Date:** 2026-07-30 · GOAL-5 · orchestrator

**Bottom line:** `run_surface_drift_check.py` checks the runtime subrepo checkouts
against **`subrepos.lock.json`'s pinned commit** — *"does runtime match what we
pinned"* — and, a few lines later, checks `orchestrator-run` against its fetched
**`origin/main`** — *"is it current"*. **A pin frozen for months passes the first
check clean forever**, and every fix merged behind it is invisible on the run path.

## 1. The number nobody had seen

`[VERIFIED — ops/subrepo_pin_lag_check.py, 2026-07-30]`

| subrepo | pin behind its own `origin/main` |
|---|---:|
| **renquant-model** | **240** |
| **renquant-orchestrator** | **213** |
| renquant-backtesting | 50 |
| renquant-artifacts | 38 |
| renquant-pipeline | 34 |
| renquant-base-data | 20 |
| renquant-execution | 15 |
| renquant-common | 5 |
| renquant-strategy-104 | 2 |
| **total** | **617** |

## 2. What it explains

Four fixes merged during 2026-07-30 and **none reached the running code**
`[VERIFIED — direct grep of the runtime copies]`: orch#620's cutoff stamp,
pipeline#233's unknown-kind rail, `renquant-common`'s latin-1 title fix, and
pipeline#231's twin registry (whose file does not exist in the runtime copy at all).

Those had looked like four separate problems. They are **one** number, per repo.

## 3. A pin being behind is NOT automatically wrong

Pins are deliberate. The artifacts pin is frozen at a canonical snapshot by standing
decision, and freezing a pin during an investigation is a legitimate act. The point
is that **the distance should be a number somebody chose, not a number nobody has
seen.** `--max-lag` is an ALARM threshold, not a policy.

## 4. Read-only, and never inside the live tree

It reads `subrepos.lock.json` as a file, then measures the lag inside the
**development** checkout of each subrepo. It never runs `git` under `RenQuant/`,
which is forbidden on this programme.

## 5. Two fail-open cases review found in the measurement itself

**(a) A behind-count is only a behind-count for an ANCESTOR pin.**
`rev-list pin..origin/main` is defined for *divergent* pairs too and returns a
number there — taking it as "behind" silently hides a non-fast-forward state.
Ancestry is now **proved** with `merge-base --is-ancestor` before any count is
taken; a non-ancestor is `DIVERGED` with the pin-only / main-only pair and **no
behind number at all**.

Measured after the change: **all 9 pins are genuine ancestors**, so the table above
stands — but it is now a proved behind-count rather than an assumed one.

**(b) The denominator was silently shrinking.** `scan` dropped lock entries missing
`name` or `commit`, so a partially malformed lock would reduce the population being
checked **while still reporting success** — the same shape this tool exists to
expose, one level up. Every entry is now a row; a malformed one is `MALFORMED`,
counted, and makes the CLI exit non-zero on its own. The summary line reports
against `lock_entries`, not against the measurable subset.

## 6. Suite — 15 tests

The real distance is counted; a pin **at** `origin/main` is **0** (anti-vacuity — if
everything reported a lag the number would carry nothing); a missing dev checkout
and an unreachable pin are **UNMEASURABLE, never 0** (that conflation is how a
fail-open guard reports green); unmeasurable rows are counted separately from
measured ones; an **empty lock is an ERROR**, since a lock listing nothing would
make every other assertion vacuous; and the CLI exits non-zero on an unmeasurable
row even when the lag threshold is not exceeded.

One test of mine was **deleted rather than shipped**: it asserted only that the
result dict had a `status` key, which is decorative.
