# Deployment-knob sweep — REVISED: only the turnover cap binds in this frame

STATUS:    measurement; read-only; conclusion REVISED in review r2 (the
           r1 "λ is dead; min_invested × turnover cap are the levers"
           headline is WITHDRAWN — this doc agrees with the research
           note's final §, not the r1 story preserved there as trail).

WHAT:      doc/research/2026-08-09-deployment-knob-sweep.md — four
           scenarios on real run inputs. The constructed λ-sensitivity
           case (min_invested=0.5 floor, loose turnover cap) deploys
           1.000 at EVERY λ including 0: the simplified objective already
           wants full deployment; among modeled constraints ONLY the
           turnover cap binds (0.706/0.755/0.856/1.000 at cap
           0.15/0.2/0.3/0.5); λ's general role is UNRESOLVED (no tested
           configuration isolates a must-act case) and min_invested shows
           no effect beyond what the cap permits.

WHY/DIR:   The live book's non-deployment therefore does NOT live in the
           λ/min_invested knobs: it lives in what this replica does not
           model — the upstream admission floors (rank-score veto 2,390
           events, mu conviction 277; orch#943 merged) and the full
           in-pipeline QP's not_selected stage. The unlock path
           redirects there; the 2026-05-23 re-enable condition (WF alpha
           evidence) governs any relaxation unchanged.

EVIDENCE:  artifact:      doc/research/data/2026-08-09-deployment-knob-sweep.json
                          [VERIFIED — 4 usable runs 2026-05-18..21 × 4
                          scenarios × 5 λ; every later run unusable per
                          orch#931] + the committed derivation with its
                          repairs stated in-header.
           prod or exp:   read-only; DB mode=ro
           existing data: the reviewed scripts/poc_lambda_sweep.py + its
                          test suite; the merged funnel Pareto (#943)
                          this note now redirects to
           best-known?:   yes — the r1 overclaim is preserved in the
                          research note as an audit trail, not erased
           scope:         no config PR proposed; upstream-floor work is
                          the successor line, behind the 05-23 evidence
                          condition via task #26.

TESTS:     none — measurement; derivation re-runnable read-only.

NEXT:      the successor evidence line targets the upstream floors and
           the full in-pipeline QP (the enable-gating AC per the script
           scope note); nothing activates without the 05-23 condition.
