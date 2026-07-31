# `OK — 44 pairs registered, 26 DIVERGED`: nine of them are what a scheduled job runs

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 · closes issue #656

STATUS:    fix + 7 tests. One existing test is RETARGETED, argued in §3 — not flipped.
WHAT:      `ops/umbrella_script_shadow_check.py` printed `OK` while 26 registered
           divergences stood, 9 of which are executed by a scheduled job. A
           scheduled-surface divergence is now a finding unless the registry
           justifies it.
WHY/DIR:   GOAL-5 — a detector that reports healthy forever is worse than no
           detector, because it is *counted* as coverage.

EVIDENCE:  §4(b) block. Model-specific fields are filled and marked, not omitted.

```
artifact:      ops/umbrella_script_shadow_check.py
               (+ ops/umbrella_script_shadows.json, read only)
prod or exp:   prod — this detector is a member of the ops-audit aggregator (#650)
existing data: On origin/main @ f59d4609 the tool printed
                 "umbrella-script-shadows OK — 44 pairs registered, 26 DIVERGED", exit 0.
               Splitting the registry's own `referenced_by_a_scheduled_surface`
               field: DIVERGED x scheduled = 9, DIVERGED x unscheduled = 17,
               IDENTICAL x scheduled = 3, IDENTICAL x unscheduled = 15.
               [VERIFIED — ran the tool and parsed its registry, this session]
best-known?:   NOT APPLICABLE as a model-variant comparison — no model, no score.
               As a fix: the default is INVERTED (unjustified => finding) rather
               than a list of known-bad names extended, which is the form that has
               recurred on this repo three times.
scope:         "this is ops/umbrella_script_shadow_check.py, PROD, a verdict-logic
               change; it alters no trading behaviour and no model output. Its whole
               effect is which exit code and which sentence a detector emits."
```

NEXT:      Dispose of the 9 — each is either drift to fix or a divergence to justify
           with `accepted_because`. That is 9 judgments, not a sweep, and is
           deliberately not in this PR.

## 1. The nine

| script | subrepo | umbrella Δ | bytes |
|---|---|---:|---|
| **`fit_calibrator_alpha158_fund.py`** | renquant-model | **+11,707 B** | 14,442 → 26,149 (**+81%**) |
| **`train_walkforward_panel.py`** | renquant-backtesting | **−5,556 B** | 25,806 → 20,250 (−22%) |
| `backfill_forward_returns.py` | renquant-backtesting | −3,362 B | 15,750 → 12,388 |
| **`preopen_cancel_gate.py`** | renquant-execution | **−3,180 B** | 21,122 → 17,942 |
| `stamp_walkforward_fingerprints.py` | renquant-backtesting | +2,487 B | 7,930 → 10,417 |
| `compute_portfolio_metrics.py` | renquant-backtesting | +339 B | 11,234 → 11,573 |
| `export_lean_watchlist.py` | renquant-backtesting | −329 B | 6,332 → 6,003 |
| `smoke_test_model.py` | renquant-backtesting | −100 B | 9,475 → 9,375 |
| `build_dashboard.py` | renquant-backtesting | −95 B | 15,244 → 15,149 |

Calibrator fitting, walk-forward training, and an execution pre-open gate.

**This does not claim the umbrella copies are wrong.** They may be ahead. It claims
nobody could tell from the check, because it said `OK`.

## 2. Why the old shape was a fail-open

`verify()` checks **drift from the registered baseline**, which is correct and
unchanged. But a registered `DIVERGED` is a **frozen baseline with no owner and no
expiry** — the ack-ledger failure one level up. Printing `OK` over it means a scheduled
run reports healthy forever, and the tool is *counted as coverage* while covering
nothing.

The fix **inverts the default** rather than extending a list: a scheduled-surface
divergence is a finding **unless** the registry carries `accepted_because`. A divergence
nobody anticipated is then loud by default instead of inheriting a pass.

## 3. The retargeted test — argued, not flipped

`test_clean_exits_0` asserted `sh.main([]) == 0` against the **live** registry. Under
this change it fails, because the rule fires on the nine. **That test encoded the very
assumption being challenged**, so silently editing it to green would have deleted the
challenge.

It is instead **retargeted to the property it actually existed for** —
*the committed registry still matches the live surface* — asserted directly on
`verify()`, where that property lives:

```python
def test_committed_registry_has_no_DRIFT_from_the_live_surface():
    reg = json.loads(Path(sh.REGISTRY).read_text(encoding="utf-8"))
    assert sh.verify(reg) == []
```

Nothing is weakened: drift detection is still asserted against the real surface. What
is removed is the *conflation* — "no drift" no longer silently means "exit 0", because
the exit code now has its own test, which asserts the live registry currently exits
**1** with the nine named.

## 4. Controls, and the mutation check

Two controls are load-bearing, because the obvious over-fix is worse than the bug:

- an **unscheduled** divergence must stay **silent** — else the check alarms on all 26
  and gets switched off wholesale;
- a **justified** scheduled divergence must stay **silent** — else the alarm is
  permanent, which ends the same way.

Mutation-checked rather than asserted `[VERIFIED — this session]`:

| mutation | tests that fail |
|---|---:|
| drop the `accepted_because` gate (everything exempt) | **4** |
| ignore `referenced_by_a_scheduled_surface` (everything scheduled) | **1** — and it is the unscheduled control |

## 5. Suite

`make test` → **1 failed, 4683 passed, 2 skipped**. The single failure is
`test_run_surface_drift_check::test_committed_manifest_matches_live_surface`,
**pre-existing and unrelated** — it compares the committed launchd manifest to this
machine's live surface, and fails identically on `origin/main`
`[VERIFIED — both runs this session]`.
