# Suppress the daily blend-readout shadow-comparison ntfy (default OFF)

STATUS:    delivered
WHAT:      Gate the daily "rq104 blend 假想前10" INFO ntfy (blend vs prod top-10,
           分歧 N/10, clf 覆盖 …) behind a new env switch
           `RQ104_BLEND_READOUT_NTFY`, DEFAULT OFF, in
           `ops/renquant104/rq104_blend_readout.py`. The notification SEND is now
           suppressed by default; the blend computation and the append-only
           ledger write / fwd_60d back-fill are unchanged.
WHY/DIR:   Operator directive 2026-08-11 "这个ntfy不用发了" (this ntfy no longer
           needs to be sent). It is a shadow/hypothetical accounting readout
           (陪跑记账, no orders), so suppressing the notification changes nothing
           on the trading path; the data collection continues so the shadow
           evidence keeps accumulating and can be read on demand.
EVIDENCE:  [VERIFIED] code + unit tests below; no model/data claim.
  artifact:      ops/renquant104/rq104_blend_readout.py
                 (+ tests/test_rq104_blend_readout.py)
  prod or exp:   prod (ops notification switch; shadow accounting only — no
                 model, no trading/order path)
  existing data: n/a — notification-gating change, not a model/data claim. The
                 SEND was `_notify_picks(row)` (called once per newly appended
                 session), which imports `liveness_common.alert`; the ledger
                 write is `append_ledger(...)`, which runs BEFORE `_notify_picks`
                 and is not gated.
  best-known?:   n/a (hygiene/ops change, not a variant under comparison)
  scope:         "this is rq104_blend_readout.py ops notification, prod — a
                 default-OFF ntfy send switch; shadow/hypothetical accounting
                 only, no trading path, ledger/back-fill untouched"
NEXT:      none required in this repo. To re-enable the notification, export
           `RQ104_BLEND_READOUT_NTFY=1` (also accepts true/yes/on,
           case-insensitive) in the job's launchd environment.

## Exactly what is now suppressed, and how to re-enable

Suppressed: the single per-session INFO ntfy POST emitted by `_notify_picks`
after a new session is appended to the ledger — the "blend: … / prod: … /
分歧 N/10: … / clf 覆盖 …（陪跑记账，仅假想，不下单）" message. When the flag is
OFF (the default) `_notify_picks` returns before importing/calling
`liveness_common.alert`, so **no ntfy POST is attempted** and it prints a
one-line "ntfy suppressed" note instead.

NOT suppressed (data path preserved):
- `latest_live_run` / `prod_scores` / `shadow_scores_for` / `zsum_blend` blend
  computation;
- `append_ledger(...)` append-only session write;
- `mature_fill(...)` realized fwd_60d back-fill;
- the GOAL-1 AC3 silent-shadow-feed ALARM (exit code 2 when a live run exists
  but no shadow comparison was recorded) — that is a fail-closed health signal,
  not the readout ntfy, and is intentionally left intact.

Re-enable: set `RQ104_BLEND_READOUT_NTFY=1` (or true/yes/on).

Tests (tests/test_rq104_blend_readout.py):
- `test_blend_readout_ntfy_suppressed_by_default` — flag unset: `alert` is never
  called (no POST), and the "suppressed" note is printed.
- `test_blend_readout_ntfy_sends_when_flag_on` — flag truthy: exactly one
  `alert` POST with the day's payload; verifies the truthy spellings + `0` = off.
- `test_blend_readout_ledger_write_independent_of_ntfy_flag` — with the ntfy OFF,
  `append_ledger` still writes the row (data path preserved) and no POST fires.
