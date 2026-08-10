# rq105 pairing liveness — buy-halt reclassification (the false-stale page)

STATUS:    reviewed code fix; sentinel-only, read-only; NO change to the
           pairing logger, its output, or any live data.

WHAT:      ops/renquant105/rq105_liveness_check.py — the pairing
           collector's stale output is no longer PAGED when it is empty
           BECAUSE the served artifact's WF gate is refusing all new
           buys (P-WF-GATE). rq105 pairs ENTRY submissions
           (fb2e08de "pair from live-path submissions"); with buys
           blocked at admission there is nothing to pair — an empty
           output is correct, not a fault. New `_wf_gate_blocks_buys`
           (reads the served artifact's WF verdict) + pure
           `_pairing_buyhalt_reclassify`. The stale pairing is
           DOWNGRADED from the PAGING `stale_or_missing` to a
           NON-PAGING, still-printed `info_buy_halt` — never a healthy
           `ok`. `check_collector_data_outputs`'s documented contract
           now includes the `info_buy_halt` status; `main()` prints
           INFO lines and never pages on them.

           DESIGN EVOLUTION (visible correction — this doc reconciles
           the whole change, not just the first draft): an earlier
           revision grounded the downgrade in a trades-ledger proof
           (`buy_pending` counts). That was ABANDONED after review: the
           trades ledger cannot self-certify buy-write completeness — a
           writer dropping buys while recording sells is
           indistinguishable, from any query on it, from a genuine
           no-buy session. The shipped proof is INDEPENDENT and
           session-current: the served artifact's own WF verdict
           (`metadata.wf_gate_metadata.passed is False` — the CANONICAL
           nested key, twin-registry-designated; the legacy top-level
           copy is a stale-prone fallback, and a canonical/legacy
           `passed` DISAGREEMENT yields None → the page stands).

WHY/DIR:   Root-caused the 08-06+ paired_is.jsonl staleness: it is the
           EXACT downstream shadow of the P-WF-GATE buy halt — last buy
           submission 2026-08-04, paired_is last row 08-05 (T+1),
           sell-only sessions since. Nothing in 105 broke (tick feed
           817MB fresh, quote logger + 86/86 batch export healthy). The
           one real defect was the sentinel answering "did a row arrive
           today" instead of "should one have" — the G-F class.
           FAIL-CLOSED: the page is downgraded ONLY on a positive
           buy-blocked proof (WF passed=False); gate-admits-buys
           (passed=True), an inconsistent artifact, or an
           undeterminable read all KEEP the page.

EVIDENCE:  artifact:      ops/renquant105/rq105_liveness_check.py +
                          tests/test_rq105_pairing_buyhalt_exemption.py
                          [VERIFIED — pytest 19 passed incl. the
                          existing liveness suite; the served artifact's
                          canonical WF stamp reads passed=False today,
                          so the downgrade fires on real data]
           prod or exp:   read-only sentinel; no live write, no deploy
                          in this PR (pin sync is a separate operator
                          grant)
           existing data: the served panel artifact's wf_gate_metadata;
                          the P-WF-GATE buy-halt (last buy 08-04)
           best-known?:   yes — the downgrade never claims health; it
                          removes only the false PAGE and stays visible;
                          every non-proven case keeps paging
           scope:         one sentinel file + tests + this doc

TESTS:     pytest tests/test_rq105_pairing_buyhalt_exemption.py
           tests/test_rq105_liveness.py — 19 passed (reclassify decision
           table + canonical/legacy precedence + disagreement→None +
           missing/no-stamp→None).

NEXT:      review; the pairing resumes on its own when buys resume
           (the P-WF-GATE decision / the wf_fail override) — no 105
           action needed.
