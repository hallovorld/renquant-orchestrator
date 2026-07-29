# Progress: breadth does not buy evaluation precision; depth does, and it is gated on Stage 1

STATUS:   delivered (committed verifier + research memo). NOT a proposal; asks
          for no decision. Revised after codex review (2 MED): added the
          reviewable derivation, and restamped every quantity with a provenance
          tag rather than a blanket tail note.

WHAT:     `tools/breadth_precision_verify.py` — reproduces every number in the
          memo from sha256-pinned inputs, aborting on mismatch, with each
          subsample draw seeded off (date, N, replicate) so the tables are
          bit-reproducible. Plus
          `doc/research/2026-07-29-breadth-does-not-buy-evaluation-precision.md`.

          Findings: at N=292 names/date, 91% of per-date IC variance is
          breadth-proof; 292 -> 830 buys -2.9% on the per-date IC sd, and an
          infinite cross-section caps at -4.4%. The binding constraint is TIME
          (11 blocks). The production panel holds 43 blocks over 10.3 years, so
          24% of available history is scored — but that history has ZERO ticker
          exits, i.e. it is the current universe backfilled. Depth is the lever
          that works, and depth requires the PIT panel Stage 1 builds.

WHY/DIR:  GOAL-6 sequences Stage 1 (830-name PIT panel) into Stage 2 "breadth
          retraining", partly on the premise that width improves measurement.
          That link was inherited intuition, never measured, and is off by
          about an order of magnitude. The same measurement identifies what
          DOES move the interval and shows Stage 1 is its precondition — so
          this strengthens Stage 1's case rather than weakening the programme.

EVIDENCE: artifact: `tools/breadth_precision_verify.py` (committed, this PR);
                    inputs pinned `clf_wf_scores.parquet`
                    sha256 `1da3fcfa…5bc4efe4` and `clf_wf_manifest.json`
                    sha256 `c1cb22e2…7bd092086`; production panel
                    `RenQuant/data/transformer_v4_wl200_clean.parquet`, READ-ONLY.
  prod or exp:      EXPERIMENT/measurement + a committed verifier. No
                    production data, config, or artifact written; the panel was
                    opened for read only.
  existing data:    Yes — re-measured this session THROUGH the committed
                    verifier, which changed what is publishable. The first
                    revision's ladder came from an unseeded run and differs in
                    the third decimal at small N (N=80: 0.04832 then, 0.04619
                    now). Only the seeded output is published; the fit, the
                    91%, and the -2.9% / -4.4% deltas are unchanged. A visible
                    correction note records this in the memo rather than a
                    silent overwrite.
  best-known?:      Yes for this corpus, and now independently checkable from
                    the branch. Explicitly NOT claimed: that breadth fails to
                    improve the MODEL, or that the 830-name panel should not be
                    built. This measures evaluation precision only.
  scope:            `renquant-orchestrator` docs + one tool. No pin advanced,
                    no umbrella change, no live surface touched.

SCOPE/LIMITS:
          The `a + b/N` form is fitted, not derived, so N=2000 and N=inf are
          extrapolations. The 11 -> 43 block projection assumes 1/sqrt scaling
          AND a stationary effect across 2016-2026; neither holds exactly
          (COVID, the 2022 rate shock), so more blocks from more heterogeneous
          regimes may raise `a` as well as the block count. Both are tagged
          [DERIVED] / [ASSUMED] in the memo at the point of use.

VERIFICATION:
          `python3 tools/breadth_precision_verify.py --clf-corpus <path> --panel <path>`
          -> PIN OK on both inputs; ladder, fit, and survivorship probe as
          published. Progress-doc contract checker: 0 findings.

NEXT:     Cost the depth lever (rescoring 2016-2023) alongside Stage 2's
          breadth work, and note it cannot start before Stage 1 delivers a PIT
          panel — scoring the existing backfilled history would buy blocks and
          import survivorship bias into the statistic those blocks were bought
          to sharpen.
