# Enablement evidence packet: floor / stops / fractional (s104 #55/#56)

STATUS:    complete (evidence packet; no code, no config, no production writes)
WHAT:      Assembles the evidence Codex demanded before approving strategy-104 #55
           (one-share floor + software_stops enable) and #56 (fractional enable):
           an offline prod-ledger floor ON-vs-OFF replay, the software-stop
           registry-freshness operational test (12/12 vs the pinned runtime code),
           a stage-3/RS-2 gap scorecard, and the exact operator-action shortlist.
WHY/DIR:   Codex CHANGES_REQUESTED both PRs; the approved cash-drag sequence is
           design/evidence first. D7 (#444) + RS-2 define the gates; this packet
           measures what already passes them and names what cannot pass yet.
EVIDENCE:  doc/research/2026-07-11-enablement-evidence-floor-stops-fractional.md
           (+ doc/research/evidence/2026-07-11-enablement/ scripts + result JSONs).
           Key numbers: floor replay 7/28 sessions rescued, Δ$392–$1,356/session
           (07-02 replay $1,356.18 cross-validates the recorded $1,355); ASML
           correctly cap-refused; shadow floor observations since arming: 0;
           two-arm A/B valid sessions: 0 (pinned s104 runtime dirty — logs/);
           stops operational test 12/12 PASS, pager scheduled: NO; fractional
           enable today would fail-close ALL buys (live broker adapter lacks the
           capability-gate methods).
NEXT:      Codex re-review of the packet; operator executes the 7-item shortlist
           (§6 of the research doc) — floor gate decision, pager arming + SLA
           demo, machine-death signature, broker wiring PR, read-only broker
           verification, two-arm dirt fix, pin bump past s104 #54. #55/#56 stay
           un-merged until then.

## Notes

- READ-ONLY discipline: ledger queried from a scratchpad copy of the runs DBs;
  registry tests ran against a scratchpad registry importing the pinned runtime
  module; the only prod-path CLI invocation was the liveness checker in its
  read-only "no registry" branch. No git commands in the umbrella or primary
  checkouts; this PR was produced from a scratchpad clone.
- The replay is the packet's central instrument because the armed shadow cannot
  express the RS-2 §A-3 estimand as written (ops shadow + both two-arm configs run
  hf_patchtst; prod runs xgb; both two-arm configs already carry floor=ON).
