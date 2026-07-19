# Progress: deployed-landing active verification (2026-07-18)

Date: 2026-07-18

## What

`doc/research/2026-07-18-deployed-landing-active-verification.md` — records
four active-verification runs against the DEPLOYED runtime (not waiting for
scheduled firings, per operator "主动跑起来验证").

## Why (direction)

Operator directive: actively run verification of the landed changes NOW rather
than wait for scheduled daily/weekly/monthly firings. Proves the 2026-07-18
landing (umbrella 576ee30, runtime base-data 021ca64 + orch ade07dd7) is healthy
end-to-end on real deployed code.

## Evidence (4/4 VERIFIED)

- meta-label monthly job: exit 0 in 0.031s, "consumer dark — skipped by design",
  no artifacts, no ntfy (chronic alarm fixed on deployed code).
- daily-contract sim: exit 0, AAPL BUY intent (no zero-buy regression), 18-key
  run_bundle, small-n guard INERT in prod (bit-identical status quo).
- G4 shadow job (#551): immutable 0o444 write-once records, job_id/decision_digest
  recompute-match, series_eligible=False (unregistered), byte-identical re-run no-op.
- sentinel: fires rc=1 on real 07-17 small-n all-veto (5/5 @ n=5<12) + 3 synthetic
  controls, skips Saturday. Healthy.

Two operator observations surfaced (not defects): orch pin advanced to ade07dd7
during verification (concurrent deploy, now authoritative); run-surface-drift LOUD
was the pin-reconciliation window, since self-cleared ("drift scan OK" rc=0).

## Next

Calendar-bound only: next Saturday's live green weekly retrain confirms the sidecar
deadlock fix; small-n shadow evidence accrues over the trading week.
