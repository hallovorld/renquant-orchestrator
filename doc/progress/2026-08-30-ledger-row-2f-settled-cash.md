# LONG-ledger row 2f — one-time authority for `execution.buying_power_mode=settled_cash` (renquant-strategy-104#106)

STATUS: operator-confirmed 2026-08-30 12:09 PDT; ready to merge. Row 2f
authority for `execution.buying_power_mode=settled_cash` in the strategy-104
mover set.

WHAT: append row 2f to `doc/memory/long-term-agreements.md` (after 2c; no
existing row's meaning edited). Rows 2d (#1081) and 2e (#1095) are unmerged
at preparation, so 2f sits directly after 2c on this branch; whichever of
#1095 / this PR merges second rebases and re-sequences its row after the
other in a trivial rebase. The row authorises exactly one agent PR —
renquant-strategy-104#106 (commit 8abbf89) — to move
`execution.buying_power_mode` from `non_marginable_buying_power` to
`settled_cash` in the active config, its golden twin and the six prod-mirror
lanes (the row-2a/2b/2d/2e mover set), plus
`execution._buying_power_mode_reason` on active + golden. Scope = that single
key + its reason; every other `execution.*` value stays; frozen arms stay
`non_marginable_buying_power`; no other file or PR. Expiry / restore:
**until the operator authorizes margin use by a new row**. Rollback =
single-key revert PR + pin re-advance.

WHY-DIRECTION: the live book was sized on margin twice in two sessions.
The live adapter never read this key (umbrella `live/alpaca_broker.py::get_cash`
returned `non_marginable_buying_power` unconditionally, P0-9 2026-05-20).
RenQuant#624 fixes the adapter to HONOUR the key; the pinned config declares
`non_marginable_buying_power`, so the live number does not move until the
config says `settled_cash` — #106 is the second half of the fix, and this row
is its authority. No operator directive names this key; the 2026-08-30
max-benefit directive is NOT claimed as authority (codex's #1095 review: a
directive naming no key is not first-hand approval, and a rollback path is
not prior authorization). The row is prepared so the operator has one dated
slot to fill.

OPERATOR CONFIRMATION: the operator replied verbatim「确认」("confirmed") on
2026-08-30 12:09 PDT in the Claude operator session, in direct response to
the agent's prompt「确认 row 2e:rotation.enabled=false;确认 row
2f:execution.buying_power_mode=settled_cash」which named both keys. This
is the dated, first-hand, change-specific confirmation row 2 requires.

EVIDENCE (all read-only, 2026-08-30):
- Source audit of the order path (`daily_104.sh` -> `daily-bridge` ->
  umbrella `live/alpaca_broker.py` + `backtesting/renquant_104/adapters/runner.py`):
  the key was never read on live; the sim reads it [VERIFIED — RenQuant#624].
- Ledger forensics: 08-27 HPE $1,034 bought with settled cash **$33**;
  08-28 WELL $1,904 + NET with settled cash **-$1,140** -> account
  **1.11x on margin** at the 08-28 close (`account.cash` -$1,139.70)
  [VERIFIED — operator findings 2026-08-30 as recorded in RenQuant#624; not
  re-read from the broker here].
- RenQuant#624: vocabulary `settled_cash | non_marginable_buying_power |
  buying_power`, default `settled_cash` when absent, <= 0 -> `no_settled_cash`
  and no BUY, same-bar unsettled proceeds not credited, `runner: buy-sizing
  cash=... nmbp=... mode=...` logged [VERIFIED — #624 diff; CI green at e0729f4].
- Pinned config d3c8026a: `configs/strategy_config.json:691` and every
  shadow config declare `non_marginable_buying_power` [VERIFIED — `git show`].
- strategy-104#106 suite under the RenQuant venv (py3.10): **103 passed /
  1 skipped / 1 failed** (base 102/1/1; the failure
  `test_config_drift_cli_exposes_repo_root` is pre-existing and
  environmental); new pin `test_buys_are_sized_on_settled_cash_never_margin`.
- This repo: `tests/test_require_progress_doc.py` — see PR body for the count.

NEXT:
1. Codex review of this row (scope + evidence) -> merge to orchestrator `main`.
2. Merge renquant-strategy-104#106 (Codex approval; after this row).
3. RenQuant#624 merge + live fast-forward FIRST or TOGETHER with the umbrella
   pin advance + runtime sync (separate reviewed steps); day-1 check =
   `runner: buy-sizing ... mode=settled_cash` in `daily_104`; <= 0 cash ->
   `no_settled_cash`, no BUY, sells fire.
4. Margin use only via a new authority row.

Memory tier touched: LONG (`doc/memory/long-term-agreements.md`, row 2f
appended; no existing row's meaning edited).
