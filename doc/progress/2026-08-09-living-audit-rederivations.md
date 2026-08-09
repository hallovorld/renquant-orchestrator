# Four living-audit tripwires fired over one weekend — each re-derived, none inherited

STATUS:    9 of 10 red tests resolved by re-derivation; the 10th (twin
           parity, alerts.py) stays red BY DESIGN pending an operator grant.

WHAT:      make test went 10-red after the weekend's merges and jobs moved
           four live surfaces. One batch, four re-derivations:
           (1) umbrella-shadow registry: wf_sanity_paired.py IDENTICAL →
               DIVERGED (subrepo cae05e8, the orch#905 served-matrix
               emitter, 2026-08-08; umbrella copy 2026-06-01 lags the pin);
               accepted_because cites orch#932 with the restore condition;
               shape pins 26/18 → 27/17.
           (2) GOAL-7 accrual probe: rebound from the genesis snapshot
               (n_rows==1) to the decision boundary — the Saturday job's
               08-08 append is designed behaviour; tripwires stay on
               n_primary_matured==0 and projection absent.
           (3) GOAL-3 record: re-derived at pipeline 69bf71169cab —
               20/19/0 UNCHANGED, differing-bodies holds; VERIFIED-AT line
               appended.
           (4) GOAL-1 ops-audit record: dispositioning BEGAN 2026-08-06
               (1 ack, reason recorded, INFO still printed); record carries
               DISPOSITION-FIRST-OBSERVED marker; the live test now binds
               the record to the transition, not the ack count (acks expire
               after 14 days — a zero-ack window recurs by design).

WHY/DIR:   All four are the same class: a committed record bound to a live
           surface, and the surface moved. The discipline is re-derive,
           never inherit — and where the binding itself was brittle (genesis
           snapshot, ack count), rebind to the decision-relevant invariant.

EVIDENCE:  artifact:      suite run under the make-equivalent PYTHONPATH
                          [VERIFIED — pytest, this session]: the five
                          affected files went 10 failed → 1 failed /
                          109 passed. Ledger [VERIFIED — read, this
                          session]: 2 rows, cutoffs 2026-08-02 /
                          2026-08-08. resolve_exports at 69bf71169cab
                          [VERIFIED — live run]: 20/19/0. ops-audit window
                          08-03..08-07 5/5 parsed, max_acks 1 [VERIFIED —
                          summarize() live].
           prod or exp:   records/tests/registry only; no production
                          surface written
           existing data: the four standing records these amend
           best-known?:   yes — each amendment states why the previous
                          binding broke and what the durable one is
           scope:         the remaining red (alerts.py twin) is a REAL
                          missing production fix: execution 71d4c65 encoded
                          the ntfy Title header; umbrella live/alerts.py
                          lacks it. Preflight done: the PINNED common has
                          encode_header (notify.py:97), so the sync is
                          import-safe. Landing it is a live-tree write =
                          operator grant; the red test is the reminder.

TESTS:     targeted five-file run 109 passed / 1 designed-red; full make
           test expected 1 red (from 10).

NEXT:      ask the operator for the alerts.py umbrella sync grant (one-line
           batch, revert = restore the 2026-05-24 copy); on grant, sync +
           re-run twin parity + close the loop in this doc.
