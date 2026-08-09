# L3 classifier prereg — relocated to renquant-model; this PR keeps the dataset contract

STATUS:    design only. No training has been run; that is the point. The
           experiment executes only as specified or not at all.

WHAT:      doc/design/2026-08-09-l3-classifier-prereg.md is now the
           DATASET-CONTRACT POINTER: the full preregistration (logistic L2
           C=1.0; frozen features; expanding walk-forward + 20-trading-day
           embargo; τ ∈ {0.5, 0.6}; expectancy uplift primary; within-date
           placebo ×200; 64-row once-only external test; four-leg
           PASS/KILL; shadow-only stakes) moved to **renquant-model PR
           #207** (`doc/design/2026-08-09-l3-classifier-prereg.md` there),
           the repo that owns model-experiment contracts. This repo records
           what it serves: schema `l3_candidate_dataset.v2` (v1 carried the
           regime fields; v2 removes them for causality), the canonical
           manifest, and the REGIME EXCLUSION (no causal score-time source
           exists; see the r3 CORRECTION).

WHY/DIR:   The dataset (orch#928) is merged; the classifier experiment must
           be frozen before results exist to steer it — the same window
           discipline as orch#912 §10 and the BEAR exit prereg. Review
           round 2 relocated the prereg (P1, ownership); review round 3
           replaced the r2 regime gate with a full exclusion (the producer
           trace refuted the run-identity join) — see CORRECTIONS below.

EVIDENCE:  artifact:      orch#928 dataset manifest (7,167 rows / 523 dates /
                          1,275 excluded / selected 135 / base rate 0.6307 /
                          live 2,189 vs sim 4,978)
                          [VERIFIED — re-measured this session: read-only
                          module rebuild, DB mode=ro, output under /tmp,
                          figures from module stdout; identical to the
                          canonical post-r1/r3 record in
                          doc/progress/2026-08-09-l3-candidate-dataset.md;
                          re-confirmed unchanged on the #930 regime-removal
                          head — columns only, never row selection].
           prod or exp:   experiment — design docs only
           existing data: no meta-label entry classifier has ever been
                          trained in this system; the exit-side foundation
                          (meta-label-exit.json) is a different surface
           best-known?:   yes — first entry-filter prereg; anticipated
                          failure modes are frozen in the renquant-model doc
                          so they cannot be discovered as surprises
           scope:         design only; the experiment run follows the
                          renquant-model prereg verbatim after both PRs
                          merge.

TESTS:     none — prose contracts; the prereg's test is that the run can be
           judged entirely from its §2/§3 with zero live choices. The
           dataset-side exclusion is pinned by a regression test on the
           orch#930 branch (no regime-derived column may surface).

CORRECTION (review r1, Codex MED): the frozen evidence block cited the
           superseded pre-tie-break base rate 0.6311 from before orch#928's
           r1 correction (canonical: selected 135 / base rate 0.6307). The
           prereg is now re-frozen against a manifest re-measured this
           session by a read-only rebuild [VERIFIED — module stdout]; rows /
           dates / exclusions / run_type split unchanged (7,167 / 523 /
           1,275 / live 2,189 vs sim 4,978). Same review round: every number
           in the design doc now carries its LONG-row-10 provenance tag
           ([VERIFIED]/[DERIVED]/[ASSUMED — frozen here]), with the 64
           trade_evaluations rows and the 1,240-of-2,388 bull_calm days
           re-measured this session rather than recalled.

CORRECTION (review r2, Codex P0 + P1): (a) the r1 doc froze regime +
           regime_confidence against the merged #928 date-join, which is not
           causal — a later same-day snapshot postdates the scoring; and a
           committed doc saying "execute exactly as frozen" could be
           followed verbatim against that leaky source. The regime block is
           now GATED on orch#930 (run-identity causal join) in the frozen
           contract itself: admitted only if #930 is merged when the run
           starts, else excluded — resolved once, no mid-run choice.
           (b) the full prereg was orchestrator-resident, crossing the
           producer/consumer ownership boundary; it moved to renquant-model
           PR #207 and this PR shrank to the dataset-contract pointer.

CORRECTION (review r3, Codex BLOCKER — visible per LONG row 10): the r2
           "gate on orch#930" was itself wrong, because #930's run-identity
           join is NOT causal. The producer trace, re-verified read-only
           this session: live_state_snapshots is documented as a
           close-of-run audit row (RenQuant backtesting/renquant_104/
           kernel/persistence.py:189-205) and RunnerAdapter.commit() writes
           record_candidate_scores (adapters/runner.py:2179) BEFORE
           record_live_state_snapshot (adapters/runner.py:2342), from
           post-run state — so same-run identity proves attribution, never
           availability at candidate-score time, and a merge-state gate
           built on it would license leakage. The pointer now records
           regime as EXCLUDED entirely; orch#930 was rewritten to remove
           the regime columns from the dataset. The r2 measurement (2,184
           live rows same_run_snapshot / all sim rows absent) described the
           withdrawn construction and no longer appears as evidence for any
           frozen feature. Readmission = producer-side score-time stamp
           (regime/confidence into candidate_scores at scoring time, or an
           immutable score-time artifact) with provenance + ordering tests,
           then a NEW dated prereg.

NEXT:      merge alongside orch#930 (regime removal) and renquant-model#207
           (6 base features); then execute the experiment exactly as frozen
           there (derivation + committed artifacts at the #913/#926
           reproducibility standard), report PASS/KILL; on PASS, propose
           the shadow lane as its own granted batch.
