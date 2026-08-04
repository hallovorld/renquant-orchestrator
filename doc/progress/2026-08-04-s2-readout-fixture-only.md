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
ROUND 2 (codex on #783, all three): (1) the two-phase coverage rule is
           implemented — extension_used input; first 20-session coverage
           miss = EXTEND, miss with the extension used = INSUFFICIENT
           (both phases positive-controlled, incl. a winning blend never
           promoting through a miss in either phase); (2) the readout
           carries NO chain/artifact logic — the momentum arm calls
           pipeline#262's load_momentum_artifact_as_of at the provider
           boundary (fixtures build REAL package artifacts and reseal
           timestamps via ledger.row_sha256_of; the suite importorskips
           the model distro, so hosted CI skips and the operator machine
           runs); (3) canonical per-session run selection frozen from
           measurement (21-35 runs/session live, exactly one carrying
           candidate rows): candidate-carrying runs only, lexicographic-
           last run_id, role='candidate', MAX-score duplicate resolution
           — decoy fixtures include holding-only runs AND a candidate-
           carrying lower run_id decoy. Branch rebased onto main so the
           AMENDMENT 1 dependency is merge-enforced. Note: the real prod
           record surface is runs.alpaca.db (tag-routed; data/runs.db is
           an empty shell) — the readout takes explicit paths, so this is
           an invocation fact, not a code change.
ROUND 3 (codex): the decision suite now runs on HOSTED CI — the
           provider loader is injected behind run_readout's
           momentum_loader seam; a _FakeLoader asserts the seam contract
           (one call per session with the exact (session, cutoff) pair;
           the supplied identity recorded verbatim) and drives the
           extension/coverage/canonical-run controls without any distro;
           the REAL provider remains the default and keeps one optional
           integration test (importorskip THIS TEST ONLY). CI-sim run:
           6 passed 1 skipped; operator machine: 7 passed (pipeline#262
           now merged and pulled).
NEXT:      merge (pipeline#262 landed); at session 20: one real run,
           report published with the per-session identity triplets.
