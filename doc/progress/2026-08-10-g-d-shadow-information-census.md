# G-D (task #23): shadow-fleet information census — 13 lane-identities, 7 redundant, zero outcome-measurable

STATUS:    census of EXISTING records only (operator directive: records +
           backtest, no future accrual). Read-only over every production DB
           (sqlite `mode=ro` URIs); no run surface touched. This PR adds the
           derivation script, its verbatim CSV outputs, and the research note.
           REV 2 addresses the codex MED: the sink/surface population is now
           DERIVED (runner tags + pinned configs + pipeline module sink
           registry) and ASSERTED against the disk — a new/renamed lane fails
           the run loudly instead of being silently omitted.

WHAT:      doc/research/2026-08-10-g-d-shadow-information-census.md — the
           claim "the shadow fleet carries less information than it appears
           to" is [VERIFIED] on every measurable axis: 9 shadow configs, 6
           recording DB sinks (+2 configured-but-recordless), 6 file surfaces
           and 3 MLflow experiments reduce to 13 recorded lane-identities, of
           which 7 are >0.95-redundant under the task's frozen rule;
           blend_mom (S1) duplicates the served primary (median rho 0.9998,
           n=4); blend_rb_fast (F3) emitted BIT-IDENTICAL scores to
           blend_mom_fast (F2) on all 4 of its recorded days while declaring a
           third clf component that the sibling slow pair (F1 vs S1)
           demonstrably applies (85-87/120 names moved); the frozen corpus
           (labels end 2026-05-07) overlaps ZERO shadow lane-days (first
           shadow record 2026-05-19; first broad primary panel 2026-05-08);
           the 08-04 fleet has zero accrued outcome days; hf_patchtst (the
           only long-lived independent ranking, rho −0.09 vs primary, retired
           08-03) shows noise-level auxiliary outcomes (mean +0.31 / median
           −0.11, 20 days). 43% of the shared sink's rows (9,242/21,679)
           carry no scorer identity stamp.
           REV-2 AUDIT VERDICT (stated per review): the DB-sink list rev 1
           hard-coded WAS complete — all seven measurement CSVs re-derived
           bit-unchanged. The FILE-surface list was INCOMPLETE: the derivation
           surfaced logs/shadow_scorer_health.jsonl (82 rec, names FOUR in-run
           shadow models whose per-ticker scores are recorded nowhere),
           logs/admission_shadow.jsonl (136 rec, 8 broker identities incl.
           alpaca_shadow_a which has NO runs DB), logs/parking_sleeve_shadow
           .jsonl (37 rec), 3 MLflow shadow experiments (47,740 runs total,
           aggregate metrics only), and the recordless shadow_a/shadow_b
           sinks — all metadata, no per-ticker cross-section, so no
           measurement number moved; note §2b reports it visibly.

WHY/DIR:   G-D asks for a quantified information census of the shadow fleet
           to inform fleet pruning / MoE routing decisions; this is the
           decision input, not a gate verdict. Census discipline: day counts
           on every number, no significance theater on single-digit n.

EVIDENCE:  artifact:      doc/research/data/2026-08-10-shadow-census_{inventory,
                          pairwise_spearman,median_spearman_matrix,redundancy,
                          bit_identity,corpus_outcome_census,
                          aux_recorded_fwd5d_top5_census,primary_daily_scorer,
                          enumeration_audit}.csv [VERIFIED — verbatim outputs
                          of the committed script, rev-2 run 2026-08-10 with
                          the enumeration audit PASS; the seven measurement
                          CSVs diffed bit-identical to rev 1]
           prod or exp:   read-only measurement (mode=ro URIs); writes only
                          CSVs under doc/research/data
           existing data: runs.alpaca.db + 6 runs.alpaca_shadow*.db,
                          daily_104.sh lane registry, pinned strategy-104
                          shadow configs, pipeline module sink constants
                          (shadow_health / task_admission_shadow /
                          task_parking_sleeve), strategy logs jsonls, mlruns
                          experiment metadata, qp-live-shadow.jsonl,
                          shadow_predictions.json, shadow_analyst/ artifacts,
                          frozen corpus parquet (labels end 2026-05-07); no
                          new runs, no future accrual
           best-known?:   yes — note §7 lists 9 not-measurable items with
                          reasons; §2b states the audit verdict BOTH ways
                          (DB list complete / file list incomplete) with a
                          positive control (injected fake
                          runs.alpaca_shadow_RENAMED_LANE.db → exit 1 naming
                          the file); F3/F2 duplication verified at run level
                          (all time-adjacent pairs bit-identical, cross-time
                          drift identical in both lanes)
           scope:         1 script + 9 CSVs + research note + this doc; no
                          config, pin, or live-surface change; follow-ups are
                          NEXT items, not part of this PR

TESTS:     make test on the branch at rev 1: 6231 passed, 2 skipped, 1
           pre-existing failure (twin-parity alerts.py live-tree drift — the
           known pending sync, measured on the operator's live tree,
           untouched by this diff; script+docs only, nothing imported by
           src/). Rev 2 adds no importable surface; the census script's
           enumeration audit carries its own positive control (exit-1 on an
           injected unknown lane, run 2026-08-10).

NEXT:      (a) file the F3 (blend_rb_fast) declared-but-inert clf component
           finding with the pipeline/strategy-104 owners — one of F2/F3 is
           not what its manifest declares (bit-identity evidence committed);
           (b) fleet-pruning recommendation: S1 duplicates the promoted
           primary and F3 duplicates F2 — two of five recording lanes buy no
           information; (c) the zero-corpus-overlap fact means any future
           lane verdict needs either label refresh authorization or a
           prospective window declared in advance; (d) the four in-run shadow
           models score daily with no per-ticker sink — if their information
           is ever to be adjudicated, a cross-sectional record must exist
           first (pipeline-side decision, not taken here).
