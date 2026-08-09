# L3 dataset — regime EXCLUDED: no causal score-time source exists   (PR #930)

STATUS:    delivered for review (orch#930), r3. The r1 "causal join by run
           identity" construction is WITHDRAWN (see CORRECTION below); this
           PR now removes regime from the dataset entirely.

WHAT:      src/renquant_orchestrator/l3_candidate_dataset.py — the regime
           join is REMOVED: no regime / regime_confidence /
           regime_snapshot_created_at / regime_source columns in rows or
           manifest. A regression guard pins the exclusion: snapshot rows,
           even the same run's own, must not surface in any output column.
           SCHEMA bumped v1 -> v2 (r4, codex P1): merged #928 published v1
           WITH the regime fields, so the regime-free export is
           l3_candidate_dataset.v2 — documented in the module, pinned by
           test, and enforced by a fail-closed build assertion that refuses
           any export in which a regime-derived column reappears.

WHY/DIR:   codex's r2/r3 producer trace refuted the run-identity premise,
           and this session re-verified it read-only in RenQuant:
           * live_state_snapshots is documented as an append-only audit
             trail — "what did live_state look like at the close of run
             R?" — backtesting/renquant_104/kernel/persistence.py:189-205
             [VERIFIED — read this session];
           * RunnerAdapter.commit() calls record_candidate_scores at
             adapters/runner.py:2179 BEFORE record_live_state_snapshot at
             adapters/runner.py:2342, and the snapshot is built from the
             post-run state [VERIFIED — read this session].
           Same-run identity therefore proves ATTRIBUTION, not availability
           at candidate-score time. With date-latest (leaks), timestamp
           inequality (voids the field), and run identity (attribution
           only) all refuted, NO consumer-side join is causal — exclusion
           is the only honest construction; anything else licenses leakage
           into a 20-day-label experiment.
           Readmission path (producer-side, out of this PR's scope): stamp
           regime/confidence into candidate_scores at scoring time — or an
           immutable score-time feature artifact — with score-time
           provenance and producer-side ordering tests; admitting the block
           is then a NEW dated prereg.

EVIDENCE:  artifact:      src/renquant_orchestrator/l3_candidate_dataset.py
                          (this branch); read-only rebuild against
                          RenQuant/data/runs.alpaca.db (mode=ro, CSV +
                          manifest under /tmp) this session
           prod or exp:   experiment — read-only over prod data
           existing data: merged orch#928 emits regime via the leaky
                          date-latest join; r1 of this PR replaced it with
                          the run-identity join, now also refuted
           best-known?:   yes — manifest after exclusion: 7,167 rows / 523
                          dates / 1,275 excluded / 135 selected / win rate
                          0.6307 / live 2,189 vs sim 4,978, schema
                          l3_candidate_dataset.v2 [VERIFIED — module
                          stdout, this session], identical row figures to
                          the canonical #928 record: the removal changes
                          columns only, never row selection. CSV header
                          carries no regime-derived column [VERIFIED —
                          head -1 of the rebuilt CSV, this session].
           scope:         one module + tests; no production surface. The
                          prereg (renquant-model#207) freezes the 6 base
                          features with regime excluded; orch#929's pointer
                          doc carries the same exclusion.

TESTS:     pytest -q tests/test_l3_candidate_dataset.py → 6 passed [this
           session], incl. the exclusion regression guard
           (test_regime_is_excluded_even_when_snapshots_exist).

NEXT:      merge; the producer-side score-time stamp is the only path that
           readmits regime, under a new dated prereg.

## CORRECTION (r3, 2026-08-09 — visible per LONG row 10, no silent overwrite)

r1 of this doc claimed the same-run snapshot was "the only causal
construction" and told the classifier prereg to gate its regime block on
this PR merging. That claim was WRONG: the producer trace above shows the
snapshot row is written after the run's candidate scores, from post-run
state — run identity proves which run wrote the row, not that its fields
existed at score time. The r1 evidence figures (regime_source
{same_run_snapshot: 2184, absent: 4983}) were accurate measurements of the
withdrawn construction and remain in git history; they do not describe this
PR's output, which carries no regime columns at all.
