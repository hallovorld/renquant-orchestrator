# LONG-ledger row 2e — one-time authority for `rotation.enabled=false` (renquant-strategy-104#105)

STATUS: operator-confirmed 2026-08-30 12:09 PDT; ready to merge. Row 2e
authority for `rotation.enabled=false` in the strategy-104 mover set.

WHAT: append row 2e to `doc/memory/long-term-agreements.md` (after 2c; no
existing row's meaning edited; if #1081 / row 2d merges first the row is
re-sequenced after 2d in a trivial rebase). The row authorises exactly one
agent PR — renquant-strategy-104#105 — to move `rotation.enabled` from
`true` to `false` in the active config, its golden twin and the six
prod-mirror lanes (the row-2a/2b/2d mover set), plus
`rotation._enabled_reason` on active + golden. Scope = that single key;
every other `rotation.*` value stays; frozen arms stay `true`; no other file
or PR. Expiry / restore: **until a rotation design passes a WF gate**
(re-enable = a new row). Rollback = single-key revert PR + pin re-advance.

WHY-DIRECTION: operator directive 2026-08-30, Claude operator session,
verbatim 「你问的6个问题基本都不是真正的问题!你自己按照受益最大方向推进」
("the six questions you asked are basically not real questions — push
forward yourself in the direction of maximum benefit"). It names no key, so
per the 2b/2d precedent it is NOT first-hand approval of this key — it is the
delegation under which the agent chose the change, recorded verbatim so the
audit trail is not an agent's own commit message. Maximum benefit here =
stop an engine that (a) no WF cut ever exercised, (b) acts on a 5-day
oscillator forecast x12 with zero modelled cost, and (c) produced the live
book's churn for ~zero realized P&L while its re-entries took both stop-loss
losses. Every step is reversible by one key.

OPERATOR CONFIRMATION: the operator replied verbatim「确认」("confirmed") on
2026-08-30 12:09 PDT in the Claude operator session, in direct response to
the agent's prompt「确认 row 2e:rotation.enabled=false;确认 row
2f:execution.buying_power_mode=settled_cash」which named both keys. This
is the dated, first-hand, change-specific confirmation row 2 requires.

EVIDENCE (all read-only, prior work 2026-08-29/30; memory notes named in the row):
- Parity audit: served artifact `metadata.wf_gate_metadata` — WF sim had
  **0 rotation trades in all 3 cuts**; gate `passed=false`, served under the
  RFC#210 freshness license [VERIFIED — `live-policy-is-not-the-validated-policy`].
- Logic forensics: rotation `net_adv` = per-ticker 5d ER x12 to 60d
  (`models.py:113-115`, `task_candidates.py:349-361`); **22% of session pairs
  jump >= 0.06; 17 sign flips in 12 names**; `transaction_cost_pct=0`
  [VERIFIED — `flipflop-driver-is-5d-oscillator-er`].
- Ledger forensics 07-17..08-28: **33 round-trips realized +$4.32**, gross
  traded $60.1k = **5.55x turnover / 6 weeks**, churn set 55.6% of gross;
  rotation 8 trips +$64; stop_loss 2 trips -$207, both RE-ENTRIES
  [VERIFIED — `win-rate-is-backtest-not-live`, broker history + FIFO fills].
- strategy-104#105 suite on CI-matching py3.10: **104 passed / 1 skipped**
  (base 103/1); new pin `test_rotation_engine_is_disabled_until_validated`.

NEXT:
1. Codex review of this row (scope + evidence) -> merge to orchestrator `main`.
2. Merge renquant-strategy-104#105 (Codex approval; after this row).
3. Umbrella pin advance + runtime sync as separate reviewed steps; day-1
   check = no `ROTATION_SELECT`/`ROTATION_EXEC` in `daily_104`, exits fire.
4. Re-enable only via a rotation design that passes a WF gate + a new row.

Memory tier touched: LONG (`doc/memory/long-term-agreements.md`, row 2e
appended; no existing row's meaning edited).
