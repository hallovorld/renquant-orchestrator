# 2026-08-04 — the σ-head sidecar gets a living host: invoke the sole writer in lockstep (orch#798)

## The orphan, measured tonight

base-data#48 correctly made `renquant_base_data.rawlabel_sidecar` the SOLE
writer of the canonical σ-head `_rawlabel` sidecar and retired
`RefreshSigmaHeadRawLabelTask`'s self-build (two writers with contradictory
recipes had deadlocked the weekly corpus refresh). But the writer's only
SCHEDULED invocation lived inside `weekly_retrain_patchtst.sh` — retired
2026-08-02/03. The side-product was orphaned: its last write was Sat 08-01
05:30, three panel refreshes later the consume check correctly refused
(`panel-only=288`, invalidation receipt written), and with RenQuant#427 merged
σ-head training was BLOCKED with no living path back. Tonight's republish was
by hand.

## The fix

`RefreshSigmaHeadRawLabelTask` already sits in the right place — immediately
after the fund-panel merge, before anything consumes the sidecar. It now
INVOKES the sole writer there:

```
panel rebuild → fund merge → [publish via sole writer] → verify lockstep →
certify (provenance stamp + receipt clear) → GBDT retrain → calibrator
```

Calling the writer is not a second implementation — it is the amendment's own
contract, invoked from the one place that can guarantee lockstep: same
process, immediately after the panel it must match was rebuilt. The daily
retrain is also the correct CADENCE: the panel refreshes daily, so a weekly
sidecar host would leave it out of lockstep six days out of seven.

Safety: staging path + `os.replace`, so the served sidecar is never opened for
write in place and a failed build cannot leave torn bytes; a non-zero writer
exit, or an exit-0 that produced no file, raises `RawlabelValidationError` and
falls to the existing except-path that writes the invalidation receipt —
fail-closed exactly as before.

## Tests

- the sole writer MODULE is invoked (never a reimplementation) and its info is
  recorded in the task summary;
- a writer that half-writes then fails leaves the PREVIOUS served bytes intact
  and cleans up the staging file;
- exit 0 with no output is still a failure;
- the horizon is passed through, not defaulted.

Suite: 21 passed.

## Not covered here

The one-off republish already done tonight (grants-logged) and the Saturday
playbook's obligation F remain as they are until this deploys; after deploy,
obligation F becomes automatic and #795 should drop it.
