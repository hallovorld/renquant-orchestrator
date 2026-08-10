# rq105 pairing liveness — buy-halt reclassification (the false-stale page)

STATUS:    reviewed code fix; sentinel-only, read-only; NO change to the
           pairing logger, its output, or any live data.

WHAT:      ops/renquant105/rq105_liveness_check.py — the pairing
           collector's stale output is no longer PAGED when it is empty
           BECAUSE the live P-WF-GATE is refusing all new buys. rq105
           pairs ENTRY submissions (fb2e08de "pair from live-path
           submissions"); with buys blocked at admission there is
           nothing to pair — an empty output is correct, not a fault.
           New `_wf_gate_blocks_buys` + pure
           `_pairing_buyhalt_reclassify`. The stale pairing is
           DOWNGRADED from the PAGING `stale_or_missing` to a
           NON-PAGING, still-printed `info_buy_halt` — never a healthy
           `ok`. `check_collector_data_outputs`'s documented contract
           now includes the `info_buy_halt` status; `main()` prints
           INFO lines and never pages on them.

           DESIGN EVOLUTION (visible correction — this doc reconciles
           the whole change, not any single draft):

           (1) An early revision grounded the downgrade in a
           trades-ledger proof (`buy_pending` counts). ABANDONED: the
           trades ledger cannot self-certify buy-write completeness — a
           writer dropping buys while recording sells is
           indistinguishable, from any query on it, from a genuine
           no-buy session.

           (2) The next revision read the served artifact's WF stamp
           directly (`wf_gate_metadata.passed is False`). ALSO WRONG
           (review r7): `passed=False` ALONE is NOT proof buys were
           blocked. RFC#210 licenses a FRESH governance-served artifact
           to serve with `passed=False` BY DESIGN, and the live
           P-WF-GATE ADMITS buys in that state (the 2026-08-04 incident;
           `doc/arch/e2e-pipeline-map.md` §Serving). Reading the stamp
           as "blocked" would have SUPPRESSED a real missing-output page
           on exactly those sessions — a fail-OPEN defect.

           SHIPPED: `_wf_gate_blocks_buys` consumes the SINGLE admission
           authority `check_model_bundle_consistency.wf_gate_admits_buys`
           — the same function the pre-deploy bundle check uses, now
           extracted so the policy lives in ONE place. It reads the
           CANONICAL `metadata.wf_gate_metadata` first (legacy top-level
           only as fallback) AND applies the full RFC#210 license
           (basis string, ISO trained_date, age 0..28d, fail-closed).
           The sentinel does NOT reimplement any admission policy; it
           returns `not admits`, and only a positive authoritative
           "blocked" verdict downgrades the page.

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

EVIDENCE:  artifact:      ops/renquant105/rq105_liveness_check.py
                          (sentinel) + scripts/check_model_bundle_
                          consistency.py (shared `wf_gate_admits_buys`
                          authority, extracted) +
                          tests/test_rq105_pairing_buyhalt_exemption.py
                          [VERIFIED — pytest 38 passed across the
                          reclassify decision table, the gate reader
                          incl. the r7 RFC#210-licensed-passed=false
                          regression, the existing liveness suite, and
                          the check_model_bundle_consistency suite
                          (extraction confirmed behavior-invariant)]
           prod or exp:   read-only sentinel; no live write, no deploy
                          in this PR (pin sync is a separate operator
                          grant). The checker refactor is behaviour-
                          invariant (its own suite + CI-gate suite green)
           existing data: the served panel artifact's wf_gate_metadata,
                          read through the authoritative admission
                          verdict (RFC#210 license included), NOT the
                          raw `passed` flag; the P-WF-GATE buy-halt
           best-known?:   yes — the downgrade never claims health; it
                          removes only the false PAGE and stays visible;
                          every non-blocked or undeterminable case keeps
                          paging (fail-closed)
           scope:         sentinel + the extracted shared authority +
                          tests + this doc

TESTS:     pytest tests/test_rq105_pairing_buyhalt_exemption.py
           tests/test_rq105_liveness.py
           tests/test_check_model_bundle_consistency.py
           tests/test_bundle_consistency_ci_gate.py — 45 passed
           (reclassify decision table; gate reader via the shared
           authority: canonical-first, RFC#210 licensed passed=false →
           NOT blocked [r7 regression], RFC#210 stale → blocked, missing
           numerics → blocked, absent stamp → blocked, missing artifact
           → None; checker extraction behavior-invariant).

NEXT:      review; the pairing resumes on its own when buys resume
           (the P-WF-GATE decision / the wf_fail override) — no 105
           action needed.
