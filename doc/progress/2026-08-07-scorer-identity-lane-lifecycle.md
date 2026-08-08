# Scorer identity monitor — a retired/added lane is not a silent scorer swap

STATUS:    delivered. Behaviour change is wording + a new `lifecycle` field.
           NO severity changes: a lineup change with no recorded event is still
           CRITICAL. Nothing is silenced and no gate is loosened.

WHAT:      `scorer_identity_monitor.LaneChange` gains a `lifecycle` field
           ("added" | "retired" | None) derived from the existing `_ABSENT`
           sentinel. A lane leaving or joining the lineup now reports a
           distinct CRITICAL line naming the transition instead of the
           self-contradicting "swap ... (lane not stamped)" text; a genuine
           same-lane substitution keeps the original "silent scorer swap"
           wording unchanged.

WHY/DIR:   Five CRITICAL "silent scorer swap" alerts were open. Four of them are
           not swaps. Two are append-only ledger appends (a separate fix, see
           NOT IN THIS PR); the other two are a lane leaving the lineup and a
           lane joining it. The alert asserted "swap" while printing
           "(lane not stamped)" on the same line — the text contradicted itself,
           and reading the assertion instead of the value cost several rounds of
           investigation aimed at the wrong defect.

EVIDENCE:  artifact:      runs.alpaca.db `pipeline_runs.run_bundle_json`
                          (`artifact_hashes` + `artifact_paths`), runs
                          2026-07-31-live-0037fae6, 2026-08-03-live-00f1a826,
                          2026-08-04-live-016971fd
           prod or exp:   prod — the live runs DB the monitor itself reads
           existing data: the monitor has no notion of lineup membership; every
                          key() change has been reported as a substitution since
                          the detector shipped
           best-known?:   yes — first measurement of what those two boundaries
                          actually contain. The `_shadow_lane_name` docstring had
                          already described this shape from the same bundles;
                          this doc is the first to carry the digests.
           scope:         renquant-orchestrator only. Does not touch the WF gate,
                          the daily run, or any production config.

           keyed by artifact path, the way `_shadow_lane_name` names lanes:

             2026-07-31   [0] hf_patchtst_all_seed44_model.pt   sha256:07046963994d…
                          [1] panel-clf.top-decile.fwd60.json   sha256:1e644354e098…
             2026-08-03   [0] panel-clf.top-decile.fwd60.json   sha256:1e644354e098…
                          [1] momentum/…_ledger.jsonl           sha256:9aa2d8c9571b…

           so across that boundary:

             …hf_patchtst_all_seed44_model.pt   07046963994d -> ABSENT   RETIRED
             …panel-clf.top-decile.fwd60.json   unchanged, emits nothing
             …momentum/…_ledger.jsonl           ABSENT -> 9aa2d8c9571b   ADDED

           Both correspond to decided events: PatchTST retired 2026-08-02 and the
           momentum lanes activated the same week.

CHANGE:    `LaneChange.lifecycle` -> "added" | "retired" | None, derived from the
           `_ABSENT` sentinel on either side. `as_dict()` carries it so downstream
           consumers can distinguish the three cases. The report emits a distinct
           CRITICAL line for a lifecycle change naming the transition, and keeps
           the original wording for a genuine same-lane substitution.

TESTS:     tests/test_scorer_identity_monitor.py 38 -> 42 passed.
           The fourth test is the guard against over-reach: a real same-lane
           substitution must STILL read "silent scorer swap". Reclassifying
           lifecycle events must not weaken the case the detector exists for.
             PYTHONPATH=src:.:<renquant-common>/src .venv/bin/python -m pytest -q \
               tests/test_scorer_identity_monitor.py

NOT IN THIS PR (each is separately specified and separately gated):

  1. CONFIRMED FAIL-OPEN, shadow-receipt fan-out. Receipts are constructed with
     `family=None` (:561) and `_lane_events` applies no family filter to shadow
     lanes (:648), while family lanes at :645 do. Confirmed by execution, not by
     reading: with two shadow lanes changing in one window and ONE receipt
     belonging to only one of them, BOTH report explained=True. One lane's
     legitimate promotion currently launders another lane's genuine silent swap.
     The fix is identity-transition matching — receipts already carry
     `identity_before`/`identity_after` — and it must land BEFORE any new
     receipt writer, or the new receipts feed the hole.
     Measured trap for whoever implements it: the receipt digest is a 16-hex
     PREFIX ("sha256:1e644354e0981f47") of the lane's 64-hex digest
     ("sha256:1e644354e0981f470d13161a…"). A naive `==` matches nothing and turns
     every boundary CRITICAL — which fails the other way, since an all-red alarm
     stops being read.

  2. Ledger appends (the remaining two alerts). An append-only ledger's whole-file
     digest changes on every append, and an append is neither a promote nor a
     rollback, so it can never assemble the event the detector demands. The append
     must emit its own receipt. Blocked on (1).

  3. What SHOULD authorise a lineup change. This PR deliberately does not answer
     it: a retirement/addition stays CRITICAL. A lineup change is a real config
     event, and if nothing records it, that is a gap worth its own decision rather
     than an auto-INFO. Defaulting to "explained" here would have been the same
     mistake as silencing.

NEXT:      Fix the fail-open shadow-receipt fan-out (item 1 above) BEFORE any new
           receipt writer lands, since new receipts would otherwise feed the same
           hole. Ledger-append receipts (item 2) are blocked on that fix.
