# Scorer identity monitor — a receipt is evidence only for the transition it records

STATUS:    delivered. Closes a CONFIRMED fail-open. Strictly tightening: changes
           can move unexplained -> CRITICAL, never CRITICAL -> explained.

WHAT:      Shadow-lane changes are matched to promotion receipts by IDENTITY
           TRANSITION (`identity_before`/`identity_after`, which receipts already
           carried and the loader was throwing away) instead of by event kind
           alone. `PromoteEvent` gains the two fields; `_lane_events` takes the
           `LaneChange` so it can compare them.

WHY/DIR:   Receipts were built with `family=None` (:561) and `_lane_events`
           applied NO family filter to shadow lanes (:648) while family lanes at
           :645 do. Each half is harmless alone; together, EVERY receipt in a
           boundary window explained EVERY shadow lane change in it. The receipt
           directory is `logs/promote_shadow_patchtst`, so patchtst promotions
           were explaining momentum lanes. One lane's legitimate promotion
           laundered another lane's genuine silent swap.

EVIDENCE:  artifact:      probe against the real module — two shadow lanes
                          changing in one window, ONE receipt belonging to only
                          one of them
           prod or exp:   prod — the monitor as shipped; also the four real
                          receipts in RenQuant/logs/promote_shadow_patchtst/
           existing data: no prior measurement; the fan-out was found while
                          reading the receipt loader for an unrelated fix
           best-known?:   yes — first execution-confirmed statement of the
                          defect. It was DERIVED from two source lines first and
                          the tag was held at DERIVED until the probe ran.
           scope:         renquant-orchestrator only. No WF gate, no daily run,
                          no production config.

           probe output BEFORE the fix:
             shadow:momentum_fast    explained=True  events=1
             shadow:patchtst_shadow  explained=True  events=1   <- no receipt of its own

TWO MEASURED FACTS THAT SHAPED THE RULE (both would have produced a broken fix):

  1. Digests are TRUNCATED on one side. A run bundle stamps the full 64 hex
     (`sha256:1e644354e0981f470d13161a…`, runs.alpaca.db
     `pipeline_runs.run_bundle_json`, run 2026-08-03-live-2499e454) while the
     receipt stamps a 16-hex truncation of the SAME artifact
     (`sha256:1e644354e0981f47`). An `==` test matches nothing and turns every
     boundary CRITICAL — which fails the OTHER way, since an all-red alarm stops
     being read, landing exactly where silencing would.
     Comparison is on the shorter width, with `_MIN_DIGEST_PREFIX = 12` below
     which the comparison is REFUSED rather than loosened.

  2. A genesis receipt carries `identity_before: None`. Of the four real
     receipts, one records a lane being added (no "before") and one carries no
     identity at all. Requiring both sides to name a digest would have reported
     every legitimate lane ADDITION as unexplained forever. `_side_matches`
     treats "the lane was absent" and "the receipt names nothing" as the same
     claim; the converse never matches, and the identity-less receipt therefore
     explains nothing, which is the right answer for "something was promoted
     that day".

CHANGE:    `PromoteEvent` += `identity_before`/`identity_after` (+ `as_dict`).
           Receipt loader always parses the payload — it previously parsed only
           when the filename lacked a date, so the scoping data sat on disk
           unread. `_receipt_digest` requires a non-empty `str` with no `str()`
           coercion and no default: a malformed receipt reads as "no identity
           recorded", which keeps the boundary CRITICAL.

TESTS:     tests/test_scorer_identity_monitor.py 42 -> 47 passed.
             * receipt for another artifact does NOT explain this lane (the fail-open)
             * receipt with no identity block explains nothing
             * truncated 16-hex receipt digest STILL matches a full 64-hex lane digest
             * a prefix shorter than the floor is refused
             * genesis (before=None) matches an absent lane, and the converse does not
           One existing test was updated, not deleted: it wrote a receipt with no
           identity block and asserted OK. Under the new rule that receipt cannot
           say whose lane it was, so it now carries the identities it always
           implied. The case it guards (a real promotion IS explained) still holds.

NOT IN THIS PR:

  * Ledger-append receipts (2 of the 5 original alerts). An append-only ledger's
    whole-file digest changes on every append, and an append is neither a promote
    nor a rollback, so it can never assemble the event the detector demands. The
    append must emit its own receipt carrying the same identity fields. This PR
    was the prerequisite: emitting new receipts before it would have fed them
    straight into the fan-out.
  * What should authorise a lineup change (orch#908 item 3), still deliberately
    unanswered.
