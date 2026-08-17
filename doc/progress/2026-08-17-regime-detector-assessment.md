# Regime detector assessment — research memo (doc only)

STATUS:    research memo for the record. Docs + committed derivation artifacts only —
           NO code / config / behavior change.

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
           after consolidation). Review round 1 (Codex, 2026-08-17): the derivation is
           now COMMITTED — three deterministic read-only scripts + JSON results +
           manifest (sources+sha256, date bounds, seeds, algorithms, commands) + the
           intermediate label/posterior series as CSV, all under
           `doc/research/data/2026-08-17-regime-detector-*`; every memo number carries
           a LONG-row-10 provenance tag keyed to those artifacts; corrections are in a
           visible memo section.

WHY/DIR:   Operator-directed 2026-08-17 ("regime detector有没有提升空间？我要的是科学的
           严谨的深入的research的结论"). Also load-bearing for G-I: the m=2 power-map
           collapse traces to the detector's one-blob geometry, making the detector the
           MoE's critical path.

EVIDENCE:
  artifact:      `doc/research/2026-08-17-regime-detector-assessment.md` +
                 `doc/research/data/2026-08-17-regime-detector-{measurements,
                 posteriors-ic,replication}.py` (deterministic derivation scripts),
                 their `.json` results, `…-manifest.json` (sha256 of every input,
                 date bounds, seeds, commands), and `…-{label,posterior}-series.csv`.
  prod or exp:   neither — read-only research; no live change, no production write
                 (scripts import serving code read-only; outputs land in
                 doc/research/data/ only).
  existing data: all numbers re-measured in-session 2026-08-17 by the committed
                 scripts from repo data pinned in the manifest: SPY 1d parquet
                 (clamped to 2026-08-14 — re-run after two newer bars landed
                 reproduced every original measurement key value-for-value), the
                 serving kernel + research library code, the prod GMM artifact
                 (as_of 2026-05-22), the served panel artifact's wf_gate_metadata,
                 the committed 2026-08-08 posterior snapshot, the local phase-A IC
                 corpus (path+sha256 in manifest; not committed).
  best-known?:   yes — replica validity double-anchored: serving-label counts over
                 the WF sanity window match the served artifact's per-regime n_dates
                 EXACTLY (454/41/41/55; R:wf_replay_counts.exact_match=true) and the
                 08-08 posterior snapshot within 1.42pp; the prereg plane re-derivation
                 reproduces 77 BEAR days / 9 episodes exactly from the committed CSV;
                 the Hurst null is seeded (42 → 84.6% of n=500; 20260817 → 89.0% of
                 n=300 with H>0.65). Corrections vs the first committed memo version
                 (P1 84.6% vs 86.2% unpreserved-seed original; P8 denominator fix
                 78.1%/54.5%) are listed visibly in the memo's Corrections section.
  scope:         "a research record. Authorizes no code, no config, no live change. The
                 improvement menu is ranked but NOT scheduled; item 2 (amending the
                 frozen BEAR-exit prereg data spec) explicitly requires operator
                 sign-off; every implementation item would be its own codex-gated PR."

REVIEW FIX (Codex round 2, 2026-08-17): P6's IC split and P7's η² comparison depend on
           the LOCAL, uncommitted phase-A corpus → DEMOTED to a marked "Exploratory
           observations" section, excluded from the ranked decision case (item 5
           re-anchored on P1 + P7's committed artifact-sanity half; the verdict line
           re-worded accordingly). The derivation script's phase-A section now GUARDS on
           corpus existence (clean checkout → reproducible core runs, `phase_a_ic.
           skipped=true`). NEW `tests/test_regime_research_reproducible_core.py`: the
           P3 prereg-plane 77/9 regenerates from the committed snapshot (stdlib-only);
           the phase-A guard's presence + fail-closed ordering; a seeded Hurst-null
           re-derivation that env-skips without the umbrella kernel. Absolute local
           paths in the manifest + result JSONs normalized to `<repo>:<relpath>`.

TESTS:     NEW smoke tests: 2 passed, 1 env-skip (Hurst-null; runs where the umbrella
           kernel is present). Derivation scripts re-run end-to-end in-session (exit 0);
           regenerated
           measurements JSON semantically identical to the original session values on
           every key; replication checks: wf_replay_counts.exact_match=true,
           snapshot max_abs_diff_pp=1.42, prereg 77/9 exact, hysteresis 253→138 /
           flicker −87.3% / BEAR 413→414, recovery days 93 (incl trough) / 88 (strict),
           BEAR IC split 0.575 (n=37) vs 0.032 (n=1). No repo test suite touched
           (docs + research-data artifacts only).

NEXT:      operator decisions: (a) whether to schedule improvement items 1/4/5 (plane
           consolidation, hysteresis, Hurst retirement — safe, high-value); (b) the P3
           prereg amendment (frozen-prereg change = operator gate). G-I: power-map
           re-derivation on the serving plane after consolidation, before any Stage-A
           batch.
