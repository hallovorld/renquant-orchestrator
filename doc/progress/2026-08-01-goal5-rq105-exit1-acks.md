# The two unacked rq105 exit-1 jobs enter the ledger with bindable clears-when (GOAL-5, orch#621)

## Measured `[本次实测 2026-08-01]`

`launchctl list`: 6 rq105 jobs — 4 exit 0, **2 exit 1 and UNACKED**:
`rq105-shadow-serving` and `rq105-liveness`. The freshest shadow-serving log shows the
structural root verbatim: `shadow-realtime-serving: error: the following arguments are
required: --feature-snapshot-json` — the Stage-3 producer (#221 chain) does not exist,
so the job has never been runnable; the bare exit 1 is indistinguishable from a crash
until #736's `EXIT_NOT_WIRED=4` deploys. `rq105-liveness` exit 1 is the DETECTOR's
honest finding on that dead lane.

## The entries

Both carry machine-bindable `clears_when` (qualified repo refs + a `launchctl` exit
condition), 14-day expiry, and self-invalidation clauses ("if the condition lands and
the exit stays 1, this ack is WRONG — remove it"). The liveness entry deliberately
records "detector working, subject down" so crash-vs-finding stays distinguishable in
the ledger — the #622 lesson applied to the ledger itself.

## Pins moved with the ledger (as the audit's own tests instruct)

`n_acks` 10 → 12; live rows 1 → 3; the fresh set gains both rows. The audit's designed
tripwires fired on this edit and are updated in the same PR — which is exactly their
contract ("a ledger edit SHOULD move these — update the pin with it").
