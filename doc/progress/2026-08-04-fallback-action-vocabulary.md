# Sentinel + emitter contract learn the FALLBACK-PROMOTED action (paired with RenQuant#559)

**Date:** 2026-08-04 · `renquant-orchestrator` · backtesting#101/#102 arc

STATUS:    MERGE AFTER RenQuant#559 lands on the live tree — the skip-loud
           local drift test reads the LIVE wrapper and the new contract line
           is only emitted post-#559 (measured: exactly that one test red
           locally, 5499 green otherwise; CI unaffected — it skips off the
           operator machine).
WHAT:      weekly-wf-promote lane action_re gains
           "weekly_wf_promote FALLBACK-PROMOTED"; emitter_contract.json
           gains the verbatim template (source scripts/weekly_wf_promote.sh:511
           post-#559, wrapper sha e4bb41eb53dd7fef computed from the #559
           branch content) with capture date bumped.
WHY:       An RFC#210 fallback promotion CHANGES the served artifact — it is
           an ACTION. Without this, the sentinel would keep alarming a lane
           that just acted (and the retrain-panel104 delegator clears
           automatically via its PASS echo on exit 0).

EVIDENCE:

```
tests:  5499 passed; the ONE red is the designed ordering guard
        (test_local_wrapper_still_emits_the_contracted_lines) reading the
        pre-#559 live wrapper — goes green the moment #559 lands and the
        live tree pulls.  [本次实测]
scope:  "sentinel action_re + emitter contract + this doc; no classification
         semantics change for any existing line."
```

## Revert

git revert; the fallback line would then classify as undecided (skip), never
as refusal — safe either way.
