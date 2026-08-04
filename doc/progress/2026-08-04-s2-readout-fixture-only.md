# 2026-08-04 — the S2 readout, built BEFORE the window with fixtures only

STATUS:    implementation of the frozen S2 prereg (+AMENDMENT 1 in
           review, orch#782); real-record runs remain FORBIDDEN until
           session 20 — the script has NO default paths and the fixture
           suite is the only permitted harness
WHAT:      ops/renquant104/s2_readout.py — every frozen constant cited:
           top-3 baskets (tie rule), fwd_1d shared join with
           exclude-not-impute, blend-missing<=1, matched-pair coverage
           >=19/20 on BOTH pairs, ordinal verdict incl. INSUFFICIENT
           RECORD, seeded shuffled-basket placebo, and AMENDMENT 1's
           time-safe momentum selection (last chain-verified row with
           cutoff_date<=D and appended_at_utc<=cutoff; serving identity
           triplet recorded per session). tests/test_s2_readout.py: 6
           positive controls — PROMOTE fires on a constructed winner,
           INSUFFICIENT beats a winning blend when momentum coverage
           dies, the time-safe rule ignores late-appended rows (identity
           triplet asserted per session), placebo determinism, window
           size enforcement.
WHY/DIR:   the prereg's written-during-run-after discipline, executed
           before the window even starts: implementation choices are
           locked while zero real outcomes exist. Building these
           fixtures against REAL record shapes is what exposed the
           momentum-arm gap that became AMENDMENT 1.
EVIDENCE:  fixture suite 6 passed; no real surface touched (script takes
           only explicit paths).
NEXT:      merge after orch#782; at session 20: one real run, report
           published with the per-session identity triplets.
