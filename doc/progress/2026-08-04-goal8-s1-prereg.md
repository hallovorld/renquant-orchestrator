# 2026-08-04 — GOAL-8 S1 preregistration (doc-only)

STATUS:    prereg doc for the S1 z-blend shadow lane; freezes on merge
WHAT:      doc/research/2026-08-04-goal8-s1-zblend-prereg.md — components
           + identity pins (momentum recipe fp measured this morning from
           the live genesis ledger: momentum-v0-fd65161a20b29314, tail
           cutoff 2026-08-02, artifact a824c480…, n_scored 144), frozen
           blend semantics (intersection via NaN propagation, degraded =
           not green), the 20-session ≥19-green AC1 criterion with a
           precise definition of "green", the named prod-repin operational
           risk with a frozen resolution (accept fail-close + re-pin
           cadence), prerequisites (pipeline#261 pinned; profile PR wires
           its consumer in the same batch; sentinel watch), and rollback.
WHY/DIR:   GOAL-8's ladder discipline: every rung preregistered BEFORE its
           outcome exists. S1 is operational-only; S2 (returns comparison)
           gets its own prereg frozen before unblinding. Sequencing this
           doc before the s104 profile PR means the profile review can be
           checked AGAINST the frozen prereg instead of defining the bar
           while shipping it.
EVIDENCE:  fingerprint + ledger facts measured read-only from the live
           tree this morning (commands in the session log); no run
           surfaces touched; doc-only change.
NEXT:      after pipeline#261 merges + pins: s104 blend-momentum profile
           PR (delta-6 pattern + both pins + lane wiring + sentinel watch)
           reviewed against this prereg; the 20-session clock starts at
           the first scheduled session after the deployment boundary
           (the pin-batch merge timestamp, recorded verbatim in the
           profile PR), counting load-failed and record-less sessions.
