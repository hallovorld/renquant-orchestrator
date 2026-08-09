# L2 paper bandit — the routing table starts breathing

STATUS:    code delivered for review. Shadow phase: publishes weights and
           logs only; allocates nothing; touches no live surface. No job
           installation in this PR (that will be its own granted batch, as
           L1's was).

WHAT:      src/renquant_orchestrator/l2_paper_bandit.py + 7 tests. Hedge/EG
           weights over the expert paper books the lane infrastructure
           already marks daily. Frozen: eta 0.25 [DERIVED — sqrt(8·lnN/T),
           N=5, T≈252], clip 5%/day, champion floor 0.5. Arm registry frozen
           in-module: champion = the live book's own construction, plus the
           three marked shadow profile books.

           THE §2 CONTRACT, IMPLEMENTED ITEM BY ITEM (each tested):
           1 bounded transform — clip ±5%, clip events recorded on the row;
           2 timing — rows labelled effective_from next_trading_day;
           3 eligible-arm rule — no honest mark = no update, weight carried,
             exclusion recorded;
           4 costs — shadow allocates paper only (doc: live phase must charge
             costs inside the return before the transform);
           5 the claim is a regret bound on the transformed series, never
             profitability.

           SELF-VERIFYING LOG: every run deterministically replays the FULL
           weight history from the arm DBs, verifies every existing log row
           against the replay (divergence = REFUSED — a tampered/drifted log
           is never appended to), then appends new dates only.

WHY/DIR:   orch#918 L2: the routing table stops being a frozen artifact and
           becomes a published daily state with guarantees conditional on the
           contract above. The champion floor is "panel 最好就继续用 panel"
           as a constraint in the optimizer.

EVIDENCE:  artifact:      dry-run against the real lane DBs (read-only, log
                          to session scratch): 77 rows replayed, latest
                          weights champion 0.5054 / profiles ~0.164-0.166,
                          zero exclusions, zero clips
                          [VERIFIED — module stdout, 2026-08-08]
           prod or exp:   experiment — read-only over the lane DBs
           existing data: lane paper marks exist (live book 77-day calendar;
                          profile books since 07-28/08-04); no allocator ever
                          consumed them
           best-known?:   yes — first live weight state of the routing table
           scope:         orchestrator module + tests. Canonical path
                          resolution (default_data_root) from the start — the
                          #920 review lesson applied at authoring time.

TESTS:     7 passed — floor holds + renormalises proportionally; clip applied
           and recorded; missing mark carries weight and is recorded;
           replay-verify-append idempotent; tampered log REFUSED; missing arm
           DB REFUSED; a persistently better arm accumulates weight while the
           floor binds (the containment picture in one test).

NEXT:      after merge: a granted batch installs the daily job (manifest same
           batch, tracker issue like #921); weights line joins the ops
           report; two weeks of live weight history before any proposal, per
           the design.
