# shadow-lane-preflight: the momentum lane's permanent SKIP made ops-audit UNUSABLE — now a real check

**Date:** 2026-08-03 · `renquant-orchestrator` · GOAL-5 / ops-audit burn-down #769 item 2

STATUS:    code + tests; no machine action needed (the detector is invoked by
           the ops-audit aggregator already installed today).
WHAT:      `check_loadable` gains a momentum-ledger branch: a `.jsonl`
           artifact_path (the momentum lane's machine-produced ledger) is
           followed tail-row → dated artifact
           (`<dir>/<cutoff_date>/momentum_residual_v0.json`), which must
           parse, kind-match the row, and self-carry the row's pinned
           identity. Previously ANY non-`.json` artifact was a permanent
           SKIP → detector exit 3 → the whole ops-audit line UNUSABLE.
WHY:       Measured on the aggregator's FIRST scheduled run (2026-08-03):
           `[unusable] shadow-lane-preflight exit=3` over a HEALTHY lane. A
           permanent skip on a living lane is a blind spot, not caution.

EVIDENCE:

```
artifact:      ops/renquant104/shadow_lane_preflight.py,
               tests/test_shadow_lane_preflight.py (+7)
prod or exp:   ops detection surface; no trading behaviour
existing data: pre-fix real-machine run: momentum artifact_loads SKIP
               ("not a JSON artifact (momentum_artifact_ledger.jsonl)"),
               1 skipped → exit 3.  [VERIFIED — this session]
post-fix:      real-machine run: 8/8 PASS, 0 SKIP, rc=0; momentum note:
               "ledger tail (2026-08-02) resolves to
               momentum_residual_v0.json; kind + declared identity agree".
               tests 39/39; full suite 5488 passed + 1 EXPECTED red
               (test_declared_but_uninstalled_jobs_are_exactly_the_named_set
               — main still declares the three PENDING_INSTALL jobs that
               were installed tonight; PR #768 empties the set; this test is
               operator-machine-only and the red is the exact-equality
               design working).  [VERIFIED — this session]
scope:         "detector-only; deliberately does NOT recompute any digest —
                byte-level chain verification stays in the serving loader
                (renquant-pipeline); a hand-copied recompute here would be a
                fourth fingerprint implementation (the triple-impl class)."
```

## Deliberate non-goals

- No digest recomputation (see scope above); the check string-compares the
  ledger row's pin against the artifact's self-carried identity, which
  catches swapped/stale dated files without owning the recipe.
- The basename literal is pinned by a test against the pipeline scorer's
  convention (skips loudly where that checkout is absent).

## Revert

git revert; the detector returns to skipping the momentum lane and ops-audit
returns to UNUSABLE on that line.
