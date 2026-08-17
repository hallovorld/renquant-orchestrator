# Regime detector assessment — research memo (doc only)

STATUS:    research memo for the record. Docs only — NO code / config / behavior change.

WHAT:      Commit `doc/research/2026-08-17-regime-detector-assessment.md`: a measured
           assessment of the regime detector against its three decision-relevant jobs
           (MoE routing, regime_admission, the BEAR exit line): as-built architecture
           (no HMM in production; Hurst→CUSUM→GMM→BEAR-override chain), 8 measured
           pathologies (P1 noise-Hurst deciding 63% of days; P2 four label planes at
           25–70% agreement; P3 BEAR-exit prereg plane 5.4× off its runtime trigger
           plane; P4 flicker; P5 +22td BEAR exit overhang; P7 bull-split adds nothing
           over one vol threshold), what is GOOD (BEAR entry: zero misses, mean +8td),
           a ranked zero-new-data improvement menu, an explicit do-not-change list, and
           the MoE (#984) implication (power map keyed to the research plane; re-derive
           after consolidation).

WHY/DIR:   Operator-directed 2026-08-17 ("regime detector有没有提升空间？我要的是科学的
           严谨的深入的research的结论"). Also load-bearing for G-I: the m=2 power-map
           collapse traces to the detector's one-blob geometry, making the detector the
           MoE's critical path.

EVIDENCE:
  artifact:      `doc/research/2026-08-17-regime-detector-assessment.md` + this doc.
  prod or exp:   neither — read-only research; no live change, no production write.
  existing data: all numbers measured in-session from repo data (SPY 1d parquet, the
                 serving kernel + research library code, the prod GMM artifact, the WF
                 sanity artifacts, the 08-08 posterior snapshot). Replica validity:
                 reproduces the WF gate's production-chain replay counts EXACTLY and
                 the 08-08 posterior occupancy within 1.4pp.
  best-known?:   yes — the two most damning numbers were DOUBLE-AUDITED by independent
                 re-derivation before writing (Hurst-on-white-noise: 86.2% claimed,
                 89.0% reproduced with a fresh seed; prereg plane: 77 BEAR days / 9
                 episodes reproduced exactly from the committed CSV). Named gaps are
                 declared rather than guessed (fold manifests not on disk; no
                 look-ahead-free per-day IC corpus; GMM refit surface "not found").
  scope:         "a research record. Authorizes no code, no config, no live change. The
                 improvement menu is ranked but NOT scheduled; item 2 (amending the
                 frozen BEAR-exit prereg data spec) explicitly requires operator
                 sign-off; every implementation item would be its own codex-gated PR."

TESTS:     none — doc-only PR.

NEXT:      operator decisions: (a) whether to schedule improvement items 1/4/5 (plane
           consolidation, hysteresis, Hurst retirement — safe, high-value); (b) the P3
           prereg amendment (frozen-prereg change = operator gate). G-I: power-map
           re-derivation on the serving plane after consolidation, before any Stage-A
           batch.
