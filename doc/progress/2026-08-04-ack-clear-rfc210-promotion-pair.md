# 2026-08-04 — ack ledger: clear the two rows whose named event happened

## What

`com.renquant.retrain-panel104` and `com.renquant.weekly-wf-promote` leave
`ops/renquant104/sentinel_acks.json` (7 → 5). Guard suites updated in the same
change (counts, fresh-set, kind/scope inventories, anti-vacuity floor);
`tests/test_ack_ledger_audit.py` + `tests/test_ack_names_the_exit_code.py`
= 64 passed.

## Why now (the clears_when event was measured today)

Both rows carried the same clearing condition, written down before the event:

- retrain-panel104: *"a staged model passes the WF gate, OR an RFC#210
  freshness-fallback promotion lands (renquant-backtesting#101) — same event as
  weekly-wf-promote"*
- weekly-wf-promote: *"weekly_wf_promote PASSES, or an RFC#210
  freshness-fallback promotion lands (renquant-backtesting#101)"*

The named event happened 2026-08-04 11:31 PT: the operator-authorized manual
RFC#210 promotion swapped the ACTIVE pair, and the ACTIVE artifact now carries
`promotion_basis=freshness_fallback_rfc210` with `trained_date=2026-08-02`
[measured today, artifact read-back]. The retrain-panel104 row's own reason text
even anticipated this: "A stamped freshness-fallback promotion ALSO clears this
row — it is an action, not a refusal."

This is a clears_when clear, not an expiry: the diagnosis in both rows (chronic
gate-v2 REJECT under the embargo-leakage floor) remains true and lives on in
`wf-promote-chronic-reject` + backtesting#101; what changed is that the refusal
is no longer the only thing the jobs ever do. Today's 13:00 scheduled run also
exercised the full chain end-to-end (gate FAIL → RFC#210 REFUSE on a fresh
prod, exit as designed), so the next weekly exits carry information again.

## Remaining ledger (5)

conditional-retrain104 · monthly-meta-label-retrain · rq104-degradation-sentinel
· rq105-batch-scores-export · shadow-ab-daily — each still bound to its own
clears_when/expiry.

## Note: PatchTST retirement state (operator grant 2026-08-04, measured)

The operator granted the PatchTST retirement execution today. Measured state:
the landing had already fully executed in the 08-02/03 batches — no
`weekly-retrain-patchtst` plist installed, job not loaded, launchd manifest
carries no entry and no PENDING_UNINSTALL marker (commit `ae41d7dc`), the
pinned strategy-104 config carries the retirement note, and the silent-refusal
sentinel's founding lane was retired 2026-08-02 (source comment at
`rq104_silent_refusal_sentinel.py:103`). The grant found nothing left to
execute; this ledger clear is the last residue found by the post-grant sweep.
