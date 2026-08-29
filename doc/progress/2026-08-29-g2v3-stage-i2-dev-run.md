# Progress: GOAL-2v3 Stage I-2 DEV RUN — FAIL-B (M_xgb block-t −1.1058; M0 4.0471; best base B3 4.26); the line pauses for an operator decision

STATUS:    delivered. Descriptive record of one preregistered `--dev-run`; the
           bundle is committed unchanged; nothing rerun, nothing refit, nothing
           recommended, no production path written (two docs + the bundle
           directory only). The line is PAUSED per the prereg §4.4 register.

WHAT:      Commits the Stage I-2 development-run bundle (`report.json` +
           `g2v3_stage_i2_audit.json.gz`) and records what it says against the
           prereg text as written: the stacked meta-learner M_xgb scores block-t
           −1.1058 on the common sample (P1 false on the life bar; BEAR
           n_eff_adj 98.0 ≥ 30 is true), below every base (best B3 4.26; P2
           margin −5.3658) and below s₀ 2.8854 (P3 margin −3.9912); the
           unweighted M0 diagnostic scores 4.0471. Outcome register row quoted
           verbatim: "| FAIL-B | ¬(P1 ∧ P2) | record as a failed attempt; line
           pauses for an operator decision |". The determinism guard reproduced
           the I-1 bundle exactly (B0 3.5042/622, B1 3.1837/511, B2 3.5915/622,
           B3 3.2394/619, s₀ 4.1861/622).

WHY/DIR:   GOAL-2v3 intraday-granularity line: prereg #1076 → I-0 gate #1083 →
           I-1 harness #1084 → I-1 dev run #1088 (trigger fired by 0.087) → I-2
           prereg #1089 (frozen before any fit) → I-2 harness #1090 → this ONE
           `--dev-run`. The prereg's execution plan §7.3 requires "record PR
           with the bundle + descriptive research doc; the outcome register row
           is quoted, the margins are stated as numbers". This is that record.
           The register's FAIL-B consequence is an operator decision, so the
           research doc ends with the options the prereg anticipates, phrased
           as questions, not recommendations.

EVIDENCE:  §4(b) block — this PR makes a model/data claim.
           artifact:      `doc/research/data/2026-08-29-g2v3-i2/i2-dev-20260829T132528Z-5269e593/report.json`
                          (sha256 `8a2804fd0df7de3665c6f568b6dfe9ff3db91b5643096ddedc4addfcb8ac0a87`,
                          66,036 B) + `g2v3_stage_i2_audit.json.gz` (sha256
                          `6629d29a7b071342a20b188e15cf40c9c6c219ebabb4a4eafbd85921ecd9d128`,
                          529,055 B; uncompressed sha256
                          `ca3e6dc3d1333c3cd8b3f41b72bb785fb72fb72637da6328b107f8ae325b14be`,
                          1,529,481 B) — run_id `i2-dev-20260829T132528Z-5269e593`,
                          commit 5269e593, `clean_tree: true`, UTC 13:25:28–13:33:39.
                          Nothing exceeds 5 MB; no file re-packed.
           prod or exp:   experiment — `run_status: DEV_RUN`, meta-OOF period
                          2022-07-01..2024-06-30 (`frozen.meta_oof_period`) on bases
                          fitted OOF inside 2020-08-01..2024-06-30; the evaluation
                          window 2024-07..2026-06 stays sealed; no live path read or
                          written, no artifact promoted.
           existing data: no prior Stage I-2 number exists — this is the first and
                          only `--dev-run`. #1090 ran a synthetic smoke only (planted
                          signal, not comparable). Upstream: I-1 dev run #1088
                          (B0 3.5042 / B1 3.1837 / B2 3.5915 / B3 3.2394, s₀ 4.1861
                          on the full base-OOF rows); I-0 gate #1083 PASS.
           best-known?:   the only variant of Stage I-2 (the prereg forbids a second
                          meta-learner or a bar change after the run). On the common
                          sample the highest series is the base B3 (4.26), then the
                          M0 diagnostic (4.0471), B1 (3.8038), s₀ (2.8854), B0
                          (2.5681), B2 (2.3995); M_xgb is last (−1.1058).
           scope:         "this is the Stage I-2 dev-run bundle, experiment,
                          development window, common sample 5,305,250 rows / 472
                          blocks (excluded 0.048993); block-t @ h=13 M_xgb −1.1058
                          (full meta-OOF diag −0.8043) / M0 4.0471 / B0 2.5681 /
                          B1 3.8038 / B2 2.3995 / B3 4.26 / s₀ 2.8854; P1 false,
                          P2 false, P3 false → FAIL-B, binding true; vs existing
                          best: none (first run)"
                          `[VERIFIED — report.json outcome, pass_bar.P1/P2/P3,
                          series.*.overall.block_t, common_sample,
                          base_refit.determinism_guard; re-read 2026-08-29]`.
           checks:        `validate_i2_provenance(report, audit, repo_root)` → `[]`;
                          `tests/test_g2v3_stage_i2_binding.py` +
                          `tests/test_g2v3_stage_i2_harness.py` → 82 passed
                          `[VERIFIED — pytest, 2026-08-29]`. The audit's block series
                          for all 8 series, re-run through the I-1 harness's own
                          `episodes_of` + `ess_stats`, reproduce every overall and
                          per-regime report value to 4 dp; the per-meta-fold table
                          in the research doc is that recomputation `[DERIVED]`.
           Per meta-fold M_xgb block-t: M1 0.2205, M2 0.6849, M3 −1.3536,
           M4 −2.2206; M0: 1.5431 / 1.1806 / 3.2144 / 2.4270; B3: 1.9065 /
           1.3338 / 2.3260 / 2.6689 `[DERIVED audit block_series + harness ESS]`.

NEXT:      per the register: "line pauses for an operator decision". This PR
           is the record; nothing else is unblocked, no rerun is planned, the
           sealed window stays untouched. The operator's options, as the prereg
           anticipates them and as the research doc §9 phrases them (questions,
           not recommendations): (1) a second I-2 attempt = a new prereg with
           its own number; (2) promoting a single base or the unweighted M0 to
           a confirmatory prereg on the sealed window; (3) closing the line.
           S3-c remains an explicit operator ask regardless.


2026-08-29. Bottom line: the preregistered Stage I-2 development run
(`--dev-run`, clean main commit 5269e593, bound to the I-1 bundle
`i1-dev-20260829T113813Z-666484a7` and the I-0 gate `i0-gate-20260829-f3d5bf7b`)
scored the stacked meta-learner **M_xgb at block-t −1.1058** on the common
sample of 5,305,250 meta-OOF rows (472 blocks), against **B3 4.26 (best base),
B1 3.8038, s₀ 2.8854, B0 2.5681, B2 2.3995** and the unweighted diagnostic
**M0 4.0471** `[VERIFIED report.json series.*.overall.block_t]`. P1 false
(life bar; BEAR n_eff_adj 98.0 ≥ 30 holds), P2 false (margin −5.3658), P3 false
(margin −3.9912) `[VERIFIED report.json pass_bar]`. The prereg §4.4 row, quoted:
*"| FAIL-B | ¬(P1 ∧ P2) | record as a failed attempt; line pauses for an
operator decision |"* `[VERIFIED report.json outcome.register_row]`. The
determinism guard reproduced I-1 exactly before any meta fit. Nothing was
rerun; nothing is recommended.

Full descriptive record: `doc/research/2026-08-29-g2v3-stage-i2-dev-run.md`
(outcome row and P1/P2/P3 with numbers, the guard, the stack as fitted, the
common sample, overall / per-regime / per-meta-fold tables, the plainly stated
facts, the 14 interpretations as applied, provenance, what the run does not
show, and the operator's questions). Prereg:
`doc/design/2026-08-29-goal2v3-stage-i2-prereg.md` (#1089). Harness +
interpretations: `doc/progress/2026-08-29-g2v3-stage-i2-harness.md` (#1090).
I-1 record: `doc/research/2026-08-29-g2v3-stage-i1-dev-run.md` (#1088).

## Bundle (immutable, its own directory)

`doc/research/data/2026-08-29-g2v3-i2/i2-dev-20260829T132528Z-5269e593/`:
`report.json` (sha256 `8a2804fd…`, 66,036 B) + `g2v3_stage_i2_audit.json.gz`
(sha256 `6629d29a…`, 529,055 B; uncompressed sha256 `ca3e6dc3…`, 1,529,481 B).
`validate_i2_provenance` → no problems; I-2 binding + harness tests → 82 passed
`[VERIFIED 2026-08-29]`. Commit 5269e593, `clean_tree: true`, UTC
13:25:28–13:33:39, store manifest 1,508 hashed == gate audit, consumed-bar
aggregate `4addcbe2…` (1,508 files) == the I-1 bundle's, I-1 harness sha256
`13c31d12…` == the blob at 666484a7.

## Descriptive facts recorded (not adjudicated)

- M_xgb's block-t is NEGATIVE on the common sample (−1.1058) and on all
  meta-OOF rows (−0.8043): the fitted stack is anti-predictive out of sample
  on 2022-07..2024-06. Per meta-fold 0.2205 / 0.6849 / −1.3536 / −2.2206.
- The unweighted M0 z-sum (4.0471) is within 0.21 of the best base (B3 4.26).
- On the meta-OOF common sample the ordering of the bases and s₀ differs from
  the I-1 full-OOF ordering (I-1: s₀ 4.19 > B2 3.59 > B0 3.50 > B3 3.24 >
  B1 3.18; here: B3 4.26 > M0 4.05 > B1 3.80 > s₀ 2.89 > B0 2.57 > B2 2.40).
  The predictions are identical (guard exact); the only change between the two
  views is the row set (2022H1 never meta-scored + 4.8993% common-sample
  exclusion). The record states this and does not explain it.
- Meta-folds M3 and M4 hit the 4,000,000 row cap (raw 4,504,553 / 5,804,977).
- The 26 sessions the common sample drops relative to the full meta-OOF set
  (498 → 472) are all I-1 abstain / zero-OOF sessions (23 in B0 − B1, 3 in
  B0 − B3), 20 of them CHOPPY by the census mapping.

## Next decision and whose it is

The prereg's FAIL-B consequence is an operator decision; this record applies
no gate beyond quoting it. The options the prereg anticipates are listed as
questions in the research doc §9: a new I-2 prereg with its own number; a
confirmatory prereg for a single base or the unweighted M0 on the sealed
window; or closing the line. The evaluation window 2024-07..2026-06 stays
sealed.
