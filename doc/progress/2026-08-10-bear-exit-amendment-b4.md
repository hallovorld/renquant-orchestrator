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

EVIDENCE:  artifact:      the amendment doc
           prod or exp:   design text only
           existing data: orch#962's committed derivation + CSVs
                          (verifier exit 0; full-field check after its
                          review r2)
           best-known?:   yes — what is NOT amended is enumerated
           scope:         one naming correction + this doc

TESTS:     none — design text.

NEXT:      review; then B4 drops from the orch#962 blocker set (B1 =
           pipeline#282 in review; B2 = backtesting PR in build; B3 =
           operator).
