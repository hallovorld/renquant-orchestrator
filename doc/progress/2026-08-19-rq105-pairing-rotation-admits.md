# rq105 pairing logger went blind on 2026-08-14: ROTATION entries were never admitted

STATUS:   fix implemented; unit tests green (60 passed in
          `tests/test_intraday_pairing_logger.py`) and verified READ-ONLY
          against the real live runs DB (`mode=ro`, no write, no live JSONL
          touched). Observe-only collector — no capital path, no config, no
          production state.
REVISION: r1

WHAT:     `paired_is.jsonl` last row was `2026-08-17` while the operator was
          looking at 2026-08-19, the second time this collector has been
          alarmed on for staleness. Per-day counters showed it is not a
          structural zero — 08-17 paired 1/1/1 — so it was condition-dependent:

            date        sessions  pairs  rows   prior-session entry?
            2026-08-14     0        0      0    —
            2026-08-17     1        1      1    yes (08-14 APH, NEW_BUY)
            2026-08-18     0        0      0    no 08-17 buy -> 0 is CORRECT
            2026-08-19     0        0      0    yes (08-18 CRWD) <- the miss

          ROOT CAUSE: `load_submitted_entries` filtered on an ENUMERATED
          allow-list of entry order types, `SUBMITTED_ENTRY_ORDER_TYPES =
          ("NEW_BUY", "TOP_UP")`. The pipeline began entering names by
          rotation, stamping `order_type = 'ROTATION'` — a real capital entry
          the allow-list matched nothing for. Full-history census of the live
          runs DB, `action IN ('buy_pending','buy')`:

            order_type  run_type  n      range
            NULL        sim       6327   2024-01-02 .. 2026-03-20
            NULL        live        75   2026-04-23 .. 2026-05-18
            NEW_BUY     live        61   2026-06-09 .. 2026-08-14
            TOP_UP      live         7   2026-06-24 .. 2026-07-22
            ROTATION    live         5   2026-08-10 .. 2026-08-19  <- never collected
            QP_BUY      live         3   2026-05-22 .. 2026-05-22

          NEW_BUY's LAST live firing is 2026-08-14 and ROTATION is now the
          book's only entry path, so the collector went blind on 2026-08-14
          while printing a healthy `sessions: 0` every day since.

          FIX: invert the predicate from an allow-list to an EXCLUDE-list.
          `action` already restricts to buys, so any stamped order type is an
          entry BY DEFAULT and only known non-entry rows are named
          (`NON_ENTRY_BUY_ORDER_TYPES = ("QP_BUY",)`, plus `order_type IS NOT
          NULL` for sim/legacy rows — stated explicitly because SQL `NOT IN`
          is UNKNOWN, not TRUE, against a NULL left-hand side). The failure
          mode becomes over-collection, which downstream censoring records and
          a reader can see, instead of silent under-collection, which is
          invisible by construction.

          BEHAVIOUR DELTA IS EXACTLY ONE THING: on every row in the live DB's
          full history the new predicate admits `{NEW_BUY, TOP_UP, ROTATION}`
          and excludes `{QP_BUY, NULL}` — identical to the old behaviour plus
          ROTATION. No historical pairing changes except the entries that were
          being dropped.

WHY/DIR:  Stage-1 pilot collection is DATA-BOUND (#208 §9, #231 N1), and the
          2026-07-02 fix for this same collector states the principle this
          violates: "a collector that structurally collects nothing is a silent
          failure of the whole stage." This is the intermittent version, which
          is worse — any single day's counters look plausible and only the
          JSONL's trailing date reveals the gap. Direction: the collector must
          fail toward collecting too much and censoring it, never toward
          silence. Both times this module has gone blind, the cause was an
          enumeration of what the pipeline stamps going stale with no test
          failing — so the regression test asserts the INVARIANT (an unknown
          order type is an entry) rather than the name `ROTATION`, which would
          go stale the same way.

EVIDENCE:
  artifact:      src/renquant_orchestrator/intraday_pairing_logger.py
                 (predicate + constants + docstring),
                 tests/test_intraday_pairing_logger.py (extended fixture +
                 `test_a_NEW_entry_order_type_is_admitted_without_editing_this_module`)
  prod or exp:   **exp** — branch off main `58cd53a6`+. Observe-only collector;
                 no capital path, no config, no live state. Live DB opened
                 `file:...?mode=ro` for verification only; nothing written.
  existing data: read by me from the live surfaces, not assumed —
                 - counters per day [VERIFIED — logs/rq105/intraday_pairing_logger_<date>.log]
                 - order_type census above [VERIFIED — data/runs.alpaca.db, mode=ro]
                 - 2026-08-18 rows: CRWD `buy_pending`/`ROTATION` AND
                   `sell_pending`/`SELL_ATTEMPT_model_protection`; APH
                   `sell_pending`/`SELL_ATTEMPT_rotation` [VERIFIED, same DB]
                 - session ran and was not empty: manifest 2026-08-19 has
                   `counters={entries_count: 3, deployed_notional: 678.3}`,
                   `errors=[]`, `kill_switch_engaged=false` [VERIFIED]
  best-known?:   yes. Verified read-only end to end against the live DB after
                 the change — T=08-17 -> [APH] (unchanged), T=08-18 -> []
                 (still correctly zero: there was no 08-17 buy), **T=08-19 ->
                 [CRWD]** and **T=08-20 -> [PANW]** (both previously dropped).
                 The correct zero is preserved and only the misses are recovered.
  scope:        the admit predicate only. Does not touch fill/tick/eligibility
                paths, the frozen §11b window, or the censoring rules.

NEXT:      Backfill is NOT included here and is NOT automatic: sessions
           2026-08-18..2026-08-19 have unpaired ROTATION entries whose ticks
           still exist, and re-running the collector for those dates would
           append rows for them. That is a write to the pilot JSONL and an
           append to a preregistered collection, so it is a separate,
           operator-visible step rather than a side effect of this fix.

REVIEW:    codex (haorensjtu-dev). Filed as orch#1012; this PR closes it.
