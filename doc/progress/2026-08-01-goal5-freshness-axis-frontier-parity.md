# GOAL-5 P0 — the chronic retrain refusal is two axes judged by different rules, and a per-ticker frontier

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-5 (daily-run reliability)

## Bottom line

`weekly-retrain-patchtst` has not promoted on 4 consecutive runs — GOAL-5's silent-refusal
sentinel still fires on it today `[本次实测 2026-08-01]`. Two measured causes, both
mechanical, neither of them the model.

## 1. Same run, same cutoff, two different rules

From the 2026-07-25 refusal block, verbatim `[本次实测]`:

```
source[fast] transformer_panel: cutoff=2026-04-28 raw-age=88d is fwd-label-clipped:
    achievable frontier=2026-07-21 (cutoff + 60 trading days, stamped lookahead_days);
    age-beyond-frontier=4d sla=28d OK
source[fast] rawlabel:          cutoff=2026-04-28 age=88d sla=28d OFF-SLA
```

**Identical cutoff. Identical raw age. One axis subtracts the forward-label frontier and
clears with 4 days to spare; the other does not and breaches by 60.**

A second, separable finding falls out of the same arithmetic: `frontier − cutoff = 84d` on
**both** 07-25 and 07-03, against a **28d** SLA. So `transformer_panel`'s stated SLA is
**unsatisfiable by construction** — it never passes on its own terms, only via the frontier
correction. The number being enforced is `age-beyond-frontier`; the `28d` is decorative on
that axis.

`ops/renquant104/freshness_axis_frontier_parity.py` measures both. It reads the frontier
**the log itself derived** — it never assumes a trading-day-to-calendar ratio — and it
refuses to claim the bare axis is *entitled* to the correction. It reports the sibling's
floor as a named conditional, because it cannot see either axis's label. On 07-03 the two
cutoffs differ (04-02 vs 02-11) and the parity finding correctly **does not fire**.

## 2. The 581 is 579 + 2, and the 2 are the interesting ones

The lockstep guard at `src/renquant_orchestrator/retrain_alpha158_fund.py:820` is
`if corpus_keys != panel_keys` — **strict set equality**, which cannot distinguish "shorter
than" from "different from". Measured directly on the live artifacts `[本次实测]`:

| | |
|---|---:|
| panel keys / max date | 725,696 / **2026-05-04** |
| rawlabel keys / max date | 725,115 / **2026-04-28** |
| `corpus-only` | **0** — a strict subset |
| `panel-only` | **581** |
| …beyond the rawlabel frontier (a **tail**) | **579** |
| …**inside** the shared span (a real **hole**) | **2** |

The 2 are `NXPI` on 2026-04-27 and 2026-04-28. And the reason is the finding:

```
panel     NXPI  max = 2026-05-01
rawlabel  NXPI  max = 2026-04-24
```

**NXPI's own rawlabel frontier is two sessions behind the corpus's.** So the residual is
not an anomaly of a different kind — it is the *same* defect at **per-ticker** granularity.

**Consequence, stated precisely:** a global frontier-aware comparison repairs 579 of 581
and still fails. The comparison has to be **per-ticker** frontier-aware, or the guard has
to stop asserting equality between two objects that are structurally different — the
panel's frontier is the bar frontier; the rawlabel's is the bar frontier minus a 60-day
forward horizon, **per ticker**.

This narrows the outstanding contract decision from *"frontier-aware vs upstream trim"* to
*"per-ticker frontier-aware vs upstream trim"*, and it removes the guesswork about the
residual 2 that blocked it.

## What is NOT claimed

That the rawlabel axis *should* receive the frontier correction — that is a claim about
its label which neither the log nor this tool establishes, and it is left as a named
conditional. That the fundamentals `STALE-COVERAGE worst=6q` leg would then pass; it is a
separate breach on 07-25 and is untouched here. Nothing was changed on any live surface:
this is read-only measurement plus one new detector.

## A defect in my own detector, found and fixed before the PR

The first version searched for a bare `OK` anywhere in the axis line and reported the
07-03 `fundamentals` axis — `(max=20d OK); QUARTERLY UNVERIFIABLE … fail-closed until it
exists` — as **OK**. The `OK` it matched belonged to a sub-clause about a different
sub-check. A detector that reads a fail-closed axis as passing is the defect it was written
to find. The verdict is now taken from the line's **terminal** state, any not-OK marker
wins, and both directions are pinned by tests.

## Tests

15. Exit codes distinguish finding (1) from clean (0) from **SKIPPED (3)** — a missing log
or a run that never reached the promote step is unmeasured, not healthy. Axis discovery is
not an allow-list, so an axis added later is watched rather than silently skipped.
