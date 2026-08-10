# BEAR-exit prereg amendment B4 — GMM naming correction

STATUS:    freeze amendment (new dated doc per the prereg's own
           instrument); resolves orch#962 blocker B4.

WHAT:      doc/design/2026-08-10-bear-exit-prereg-amendment-b4.md —
           "production HMM" corrected to the production regime model
           (the pinned GMM, prod/spy-gmm-regime.json). Evidence: GMM
           argmax reproduces the prereg's own planning estimate (75/5
           measured vs ~77/~4 planned); the only on-machine HMM gives
           211/17, incompatible. No number, arm, or gate changes; B3
           (window scope) stays an operator ruling.

WHY/DIR:   orch#962 measured that the frozen text's words point at a
           model production does not run — a run under the literal
           reading (any HMM) could not reproduce the freeze's own
           planning numbers and would adjudicate a different policy
           than the one preregistered. Correcting the POINTER (not any
           number) through the prereg's own amendment instrument keeps
           the freeze executable and honest; leaving it would force
           either a silent runner-side reinterpretation (the exact
           failure class preregistration exists to prevent) or a dead
           prereg. Direction: with B1 (pipeline#282, merged) and B2
           (backtesting#111, merged) landed, B3 is the sole remaining
           blocker and is the operator's ruling.

EVIDENCE:  artifact:      the amendment doc
           prod or exp:   design text only
           existing data: orch#962's derivation + CSVs, NOW MERGED
                          to main and present ON THIS BRANCH
                          (doc/research/data/2026-08-10-bear-exit-
                          episode-derivation.py + …-episodes.csv);
                          verifier re-run ON THIS BRANCH 2026-08-10:
                          VERDICT REPRODUCED, exit 0 (75 BEAR days /
                          5 episodes / 2,412 trading days); GMM
                          artifact identity FROZEN in the amendment:
                          sha256 cb643e00…c851a07d under s104 pin
                          e00d9356 (lock == checkout HEAD verified)
           best-known?:   yes — what is NOT amended is enumerated
           scope:         one naming correction + this doc

TESTS:     none — design text.

NEXT:      review; then B4 drops from the orch#962 blocker set (B1 =
           pipeline#282 in review; B2 = backtesting PR in build; B3 =
           operator).
