# rq105 pairing liveness — buy-halt exemption (the false-stale alarm)

STATUS:    reviewed code fix; sentinel-only, read-only DB; NO change to
           the pairing logger, its output, or any live data.

WHAT:      ops/renquant105/rq105_liveness_check.py — the pairing
           collector's freshness check no longer reports "stale" when
           its output is empty BECAUSE there were zero live buy
           submissions to pair. rq105 pairs ENTRY submissions
           (buy_pending, per fb2e08de "pair from live-path
           submissions"); a sell-only / buy-gated session produces zero
           entry-pairs — correct, not a fault. New `_pairing_buyhalt_
           exempt` (pure) + `_live_buy_submissions_since` (read-only
           runs.alpaca.db).

WHY/DIR:   Root-caused the 08-06+ paired_is.jsonl staleness: it is the
           EXACT downstream shadow of the P-WF-GATE buy halt — last
           buy submission 2026-08-04 (buy_pending); paired_is last row
           2026-08-05 (T+1); sell-only 08-06/08-10 → zero entry-pairs.
           Nothing in 105 broke; the tick feed (817MB, fresh),
           quote logger, and 86/86 batch score export are all healthy.
           The one real defect was the sentinel answering "did a row
           arrive today" instead of "should one have" — the G-F class.
           FAIL-CLOSED: the exemption is granted ONLY on a positive
           proof of zero buys; a stale pairing WITH buys, or an
           undeterminable count, keeps the alarm.

EVIDENCE:  artifact:      ops/renquant105/rq105_liveness_check.py +
                          tests/test_rq105_pairing_buyhalt_exemption.py
                          [VERIFIED — pytest 14 passed incl. the
                          existing liveness suite; the exemption fires
                          on real data: 0 buy submissions after 08-05
                          through 08-10]
           prod or exp:   read-only sentinel; no live write, no deploy
                          in this PR (pin sync is a separate operator
                          grant)
           existing data: trades table (buy_pending stamps); the
                          P-WF-GATE buy-halt (last buy 08-04)
           best-known?:   yes — fail-closed scope stated; the exemption
                          cannot hide a real break (buys+stale FAILs)
           scope:         one sentinel file + tests + this doc

TESTS:     pytest tests/test_rq105_pairing_buyhalt_exemption.py
           tests/test_rq105_liveness.py — 14 passed.

NEXT:      review; the pairing resumes on its own when buys resume
           (the P-WF-GATE decision, #954 item 3) — no 105 action needed.
