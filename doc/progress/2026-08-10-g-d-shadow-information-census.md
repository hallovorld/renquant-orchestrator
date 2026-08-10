# G-D (task #23): shadow-fleet information census — 13 lane-identities, 7 redundant, zero outcome-measurable

STATUS:    census of EXISTING records only (operator directive: records +
           backtest, no future accrual). Read-only over every production DB
           (sqlite `mode=ro` URIs); no run surface touched. This PR adds the
           derivation script, its verbatim CSV outputs, and the research note.

WHAT:      doc/research/2026-08-10-g-d-shadow-information-census.md — the
           claim "the shadow fleet carries less information than it appears
           to" is [VERIFIED] on every measurable axis: 9 shadow configs / 6 DB
           sinks / 3 file surfaces reduce to 13 recorded lane-identities, of
           which 7 are >0.95-redundant under the task's frozen rule;
           blend_mom (S1) duplicates the served primary (median rho 0.9998,
           n=4); blend_rb_fast (F3) emitted BIT-IDENTICAL scores to
           blend_mom_fast (F2) on all 4 of its recorded days while declaring a
           third clf component that the sibling slow pair (F1 vs S1)
           demonstrably applies (85-87/120 names moved); the frozen corpus
           (labels end 2026-05-07) overlaps ZERO shadow lane-days (first
           shadow record 2026-05-19; first broad primary panel 2026-05-08);
           the 08-04 fleet has zero accrued outcome days; the only long-lived
           independent lane (hf_patchtst, rho −0.09 vs primary) shows
           noise-level auxiliary outcomes (mean +0.31 / median −0.11, 20 days,
           45% positive) and was retired 08-03. 43% of the shared sink's rows
           (9,242/21,679) carry no scorer identity stamp.

WHY/DIR:   G-D asks for a quantified information census of the shadow fleet
           to inform fleet pruning / MoE routing decisions; this is the
           decision input, not a gate verdict. Census discipline: day counts
           on every number, no significance theater on single-digit n.

EVIDENCE:  artifact:      doc/research/data/2026-08-10-shadow-census_{inventory,
                          pairwise_spearman,median_spearman_matrix,redundancy,
                          bit_identity,corpus_outcome_census,
                          aux_recorded_fwd5d_top5_census,primary_daily_scorer}.csv
                          [VERIFIED — verbatim outputs of the committed script,
                          run 2026-08-10, exit 0]
           prod or exp:   read-only measurement (mode=ro URIs); writes only
                          CSVs under doc/research/data
           existing data: runs.alpaca.db + 6 runs.alpaca_shadow*.db,
                          qp-live-shadow.jsonl, shadow_predictions.json,
                          shadow_analyst/ artifacts, pinned strategy-104
                          shadow configs, frozen corpus parquet (labels end
                          2026-05-07); no new runs, no future accrual
           best-known?:   yes — §7 of the note lists what is NOT measurable
                          and why (7 items, incl. zero corpus overlap and the
                          F3 mechanism being outside this repo's boundary);
                          F3/F2 duplication verified at run level against the
                          canonical-pick artifact hypothesis (all time-adjacent
                          run pairs bit-identical, cross-time drift identical
                          in both lanes)
           scope:         1 script + 8 CSVs + research note + this doc; no
                          config, pin, or live-surface change; follow-ups are
                          NEXT items, not part of this PR

TESTS:     make test run on the branch; result reported in the PR body.
           The script itself is a read-only CLI (not imported by src/); its
           reproduction command is §8 of the note.

NEXT:      (a) file the F3 (blend_rb_fast) declared-but-inert clf component
           finding with the pipeline/strategy-104 owners — one of F2/F3 is
           not what its manifest declares (bit-identity evidence committed);
           (b) fleet-pruning recommendation: S1 duplicates the promoted
           primary and F3 duplicates F2 — two of five recording lanes buy no
           information; (c) the zero-corpus-overlap fact means any future
           lane verdict needs either label refresh authorization or a
           prospective window declared in advance.
