# GOAL-5: the gate that admits live buys certifies freshness from the one field the freshness policy forbids

**Date:** 2026-08-05
**Lane:** GOAL-5 (daily-run reliability P0)

## Bottom line

Two in-repo implementations both cite RFC #210 and reach **opposite conclusions
about the same served artifact** `[VERIFIED — this session]`.

| | verdict on `artifacts/prod/panel-ltr.alpha158_fund.json` |
|---|---|
| **freshness monitor** (`model_freshness_monitor.py`) | `[unknown] prod-panel: binding data cutoff unknown (fail-closed); trained_date=2026-08-02 is informational only, not a freshness axis` → **exit 3** |
| **buy-admission license** (pinned `kernel/rfc210_license.py`) | `governance-served under RFC#210: trained 2026-08-02, 3d old <= 28d serving SLA` → **served=True** |

Today's live run acted on the second: `preflight ✓ P-WF-GATE [HARD] … — buys
admitted while the freshness license holds` (`logs/daily_104/2026-08-05.log:371`).

## The artifact carries no binding cutoff at all

The monitor's six binding data-cutoff axes, read off the served artifact:

| field | value |
|---|---|
| `label_observation_cutoff` | **ABSENT** |
| `effective_selection_cutoff_date` | **ABSENT** |
| `effective_train_cutoff_date` | **ABSENT** |
| `data_cutoff_date` | **ABSENT** |
| `live_train_end` | **ABSENT** |
| `cutoff_date` | **ABSENT** |
| `trained_date` | `2026-08-02` |
| `promotion_basis` | `freshness_fallback_rfc210` |

`rfc210_license.py:86-88` ages `trained_date` and nothing else. The monitor's own
comment says why that is the wrong axis:

> `trained_date` (run time) is also deliberately NOT in this list: it is not a
> data-freshness axis (design §2) and never certifies freshness — a missing
> binding cutoff fails closed to `unknown` instead of falling back to it.

So the licence certifies freshness with the exact field the governance it names
says can never certify freshness, on an artifact whose WF gate **failed**
(`wf_sharpe_mean=0.602, benchmark_ok=False, regime_ok=False`).

## What this does NOT establish

**It does not establish that the model is stale.** The binding cutoff is absent,
so the vintage is unknown **in both directions** — the served panel may be
perfectly fresh. The finding is that **nothing in the system can tell you which**,
while a HARD gate reports that it can.

A conclusion of "the model is stale" here would be inventing the number this
probe exists to report as missing. The probe carries that refusal as a field
(`does_NOT_establish`) and a test pins it.

## Delivered

`ops/renquant104/freshness_axis_agreement_probe.py` + 17 tests. Three states:
`CONTRADICTION` (licensed, no binding axis), `AGREE` (licensed, at least one
binding axis readable — agreement on **axis**, not on value), `NOT_UNDER_LICENSE`.

Two design points a reviewer should check:

- The probe reads **top-level first, then `metadata`**, the same order the
  license uses. Reading only top-level would report `CONTRADICTION` for an
  artifact the license resolves from metadata — a false finding in the direction
  of my own thesis. Pinned by test.
- `DATA_CUTOFF_FIELDS` is **mirrored**, not imported, so the probe still reports
  when the monitor cannot be loaded — and a test asserts the mirror still equals
  the monitor's list, because a mirror that drifts is worse than none. A second
  test pins that `trained_date` never enters that list, so the contradiction
  cannot be resolved by redefinition instead of by fix.

Live: **`CONTRADICTION`**, exit 1.

## Anchor corrections

- **AC6 / orch#564 is CLOSED**, not `未开工`.
- The nonzero-exit set is still **14 unacked** (+3 acked as INFO = 17 lines). I
  read 17 from a raw grep first and nearly reported growth 14→17; the alarm line
  itself lists 14.

## Next

1. The fix is upstream (renquant-pipeline / whatever writes the panel artifact):
   **stamp a binding data cutoff into the artifact**, then make the license age
   *that*, falling back to refusal rather than to `trained_date`.
2. Until then the licence's `served=True` should be read as *"a fit ran 3 days
   ago"*, not *"the model saw recent data"*.
