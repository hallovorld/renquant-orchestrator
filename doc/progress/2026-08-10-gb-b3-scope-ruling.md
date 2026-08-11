# G-B B3 scope ruling — confirmatory run must cover the full BEAR set (backfill required)

STATUS:    freeze AMENDMENT (scope ruling only); design doc, nothing runs,
           nothing deployed. Records the operator-delegated B3 ruling that
           B4 (#965) left open. Changes no frozen value/estimand/threshold.

WHAT:      doc/design/2026-08-10-bear-exit-prereg-scope-ruling-b3.md — rules
           that the frozen BEAR-exit confirmatory evaluation MUST cover the
           full 5-episode/75-day frozen set, and REJECTS the sim-covered
           3-episode/32-day subset as a verdict basis. The 2018-12 +
           2020-COVID episodes (43/75 = 57% of BEAR days) are beyond all
           existing sim artifacts; running only the covered subset would
           silently narrow the frozen window AND omit the decisive bear
           (COVID, 41d). Until a backfill makes those episodes
           sim-reachable, the run stays blocked (no partial verdict).

WHY/DIR:   Operator delegated "proceed per your recommendation" 2026-08-10.
           B4 explicitly left the sim-artifact-reachable span as an operator
           ruling (#965 line 47). My recommendation: a BEAR-exit policy
           decision that never tests the COVID crash is not credible for its
           own thesis (exit timing matters most in the severe bear; the
           return-space estimand is dominated by that tail). The freeze
           forbids feasibility-driven sample selection. Power is
           policy-grade either way (n_eff ≈ 4), so the subset is weaker AND
           less representative — the worst of both.

EVIDENCE:  artifact:      doc/design/2026-08-10-bear-exit-prereg-scope-ruling-b3.md
                          [VERIFIED — episode inventory + sim coverage from
                          the committed orch#962 derivation (75d/5ep, GMM per
                          B4) and its §3 B3 blocker (39 cutoffs 2024-01..2026-03);
                          43/75=57% beyond sim coverage]
           prod or exp:   experiment/governance — design doc only; reads the
                          committed derivation, writes nothing to prod
           existing data: orch#962 episode CSV + eval-runnability §3 B3;
                          orch#965 B4 GMM ruling; the frozen 2026-08-08 prereg
           best-known?:   yes — the honest tradeoff (backfill cost vs a
                          non-credible minor-bear-only verdict) is stated, not
                          buried; the backfill's operator spend-gate is named
           scope:         one freeze-amendment design doc + this progress doc;
                          the backfill compute + any live change are OUT of
                          scope and separately gated

TESTS:     n/a (governance doc; no code path).

NEXT:      codex review + operator ratification. Then G-B is blocked on B2
           (simulator regime injection PR) + the B3 backfill (operator
           spend-gated compute campaign) — schedule the backfill, or G-B's
           verdict waits. Do NOT substitute a minor-bear-only run.
