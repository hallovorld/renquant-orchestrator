# Progress: GOAL-2v3 Stage I-1 DEV RUN — all four bases pass the life screen; the I-2 trigger fires by 0.087   (PR #1088)

STATUS:    delivered. Descriptive record of one preregistered `--dev-run`; the
           bundle is committed unchanged; nothing rerun, nothing recommended,
           no production path written (two docs + the bundle directory only).

WHAT:      Commits the Stage I-1 development-run bundle (`report.json` +
           `g2v3_stage_i1_audit.json.gz`) and records what it says against the
           prereg text as written: all four bases clear the life bar (block-t
           ≥ 1.0 overall @ h=13); B2 beats B0 by 0.0873 block-t units;
           `stage_i2_trigger.fired: true` by the literal rule.

WHY/DIR:   GOAL-2v3 intraday-granularity line: prereg #1076 → Stage I-0 gate
           #1083 → I-1 harness #1084 → this run. The prereg's I-2 trigger is
           what decides whether the line proceeds to the stacked meta-learner;
           this record states the trigger's literal outcome AND its margin so
           the operator sees both before any I-2 design is frozen.

EVIDENCE:  §4(b) block — this PR makes a model/data claim.
           artifact:      `doc/research/data/2026-08-29-g2v3-i1/i1-dev-20260829T113813Z-666484a7/report.json`
                          (sha256 `666d9c6a…`, 28,451 B) + `g2v3_stage_i1_audit.json.gz`
                          (sha256 `d124d8f2…`, 271,331 B) — run_id
                          `i1-dev-20260829T113813Z-666484a7`, commit 666484a7, `clean_tree: true`.
           prod or exp:   experiment — `run_status: DEV_RUN`, development window
                          2020-08-01..2024-06-30 only (`frozen.dev_window`); the
                          evaluation window 2024-07..2026-06 stays sealed; no live
                          path read or written, no artifact promoted.
           existing data: no prior Stage I-1 number exists — this is the first and
                          only `--dev-run`. #1084 ran a synthetic smoke only (planted
                          signal, B0 block-t 10.12, not comparable). Upstream gate:
                          I-0 GATE_RUN `i0-gate-20260829-f3d5bf7b` PASS, BEAR
                          n_eff_adj 191 vs bar 30 (#1083).
           best-known?:   the only variant of Stage I-1. Among the four learned bases
                          B2 (3.5915) is the highest; the naive reference s₀ = −r13
                          scores higher (4.1861) but is not a base, is not gated, and
                          the prereg compares it to nothing (descriptive only).
           scope:         "this is the Stage I-1 dev-run bundle, experiment,
                          development window; block-t @ h=13 B0 3.5042 / B1 3.1837 /
                          B2 3.5915 / B3 3.2394, s₀ 4.1861; B2 − B0 = 0.0873; vs
                          existing best: none (first run)"
                          `[VERIFIED — report.json bases.*.overall.block_t,
                          s0_reference.overall.block_t, base_vs_b0, stage_i2_trigger,
                          provenance.source; re-read 2026-08-29]`.
           Re-verified for r2 (2026-08-29, review r1 by codex): provenance /
           gate-binding / gate-bundle tests + `test_require_progress_doc.py`
           → 55 passed `[VERIFIED — pytest, 2026-08-29]`;
           `validate_i1_provenance(report, audit, run_root)` → `[]` when the
           validator is imported from the run's own checkout (its `GATE_AUDIT`
           path constant is checkout-bound; from any other checkout the only
           message is that path-string line, every hash check passes)
           `[VERIFIED — in-session re-run, 2026-08-29]`.
           The claim "the trigger fires" is the prereg's strict inequality on two
           point estimates (no margin, no significance requirement); it is a
           preregistered-rule outcome, not a conclusion that B2 is better than B0.

NEXT:      a Stage I-2 preregistration frozen BEFORE any I-2 fit (agent-authored,
           codex-reviewed, like #1076). The 0.087 margin is surfaced for the
           operator's information, not applied as a gate. Nothing else is
           unblocked; no rerun is planned.


2026-08-29. Bottom line: the preregistered Stage I-1 development run
(`--dev-run`, clean main commit 666484a7, authorized by the I-0 GATE_RUN bundle
`i0-gate-20260829-f3d5bf7b`) scored block-t at h=13 of **B0 3.5042, B1 3.1837,
B2 3.5915, B3 3.2394** — every base ≥ 1.0 — and the naive reference s₀ = −r13
at **4.1861** `[VERIFIED report.json bases.*.overall.block_t, s0_reference.overall.block_t]`.
The prereg's Stage I-2 trigger, quoted: *"at least one of B1/B2/B3 passes AND beats
B0's block-t … Otherwise I-1 is recorded as a failed attempt and the line pauses
for an operator decision."* B2 passes and beats B0, so **the trigger fires by the
literal rule** (`stage_i2_trigger.fired: true`). It fires by
**B2 − B0 = 3.5915 − 3.5042 = 0.0873 block-t units**; the rule as written has no
margin, minimum difference, or significance requirement — it is a strict
inequality on two point estimates. Nothing was rerun; nothing is recommended.

Full descriptive record: `doc/research/2026-08-29-g2v3-stage-i1-dev-run.md`
(verdicts as preregistered, overall / per-regime / per-fold tables, the zero-OOF
and abstain cells, the s₀ observation, the 12 interpretations, provenance, and
what the run does not show). Prereg: `doc/design/2026-08-27-goal2v3-intraday-granularity.md`
("Stage I-1" section, #1076). Harness + interpretations: `doc/progress/2026-08-29-g2v3-stage-i1-harness.md`
(#1084). Gate: `doc/research/2026-08-29-g2v3-stage-i0-gate-run.md` (#1083).

## Bundle (immutable, its own directory)

`doc/research/data/2026-08-29-g2v3-i1/i1-dev-20260829T113813Z-666484a7/`:
`report.json` (sha256 `666d9c6a…`, 28,451 B) + `g2v3_stage_i1_audit.json.gz`
(sha256 `d124d8f2…`, 271,331 B; uncompressed sha256 `a27da065…`, 746,174 B).
`validate_i1_provenance` → no problems; provenance / gate-binding / gate-bundle
tests → 49 passed `[VERIFIED 2026-08-29]`. Commit 666484a7, `clean_tree: true`,
UTC 11:38:13–11:45:05, store manifest 1,508 hashed == gate audit, consumed-bar
aggregate `4addcbe2…` (1,508 files) rebuilt from the audit == report.

## Anomalies recorded (not adjudicated)

- Fold-4 `B3[S-F+]` and `B3[S-F-]` fitted but had **0 OOF rows** (the slow leg
  is +1 on all 124 sessions of 2024H1); B3's fold-4 number is S+-only. Six B1
  cells show the same regime-absent-from-OOF pattern. No declared interpretation
  covers a fitted state with no OOF rows (Interpretation 8 covers zero
  TRAINING rows; the prereg covers a MISSING state).
- Two ABSTAIN cells (fold-0 `B1[BEAR]`, fold-1 `B1[CHOPPY]`: no training rows)
  leave 1,365,266 OOF rows (19.2%) unscored; B1 forms 511 blocks vs B0's 622,
  so B1's 3.1837 is on a smaller, less-BEAR session set than B0's 3.5042.
- Row cap 4,000,000 binds in 9 of 86 fitted cells (B0 folds 1–4, B2[OTHER]
  folds 1–4, B1[BULL_CALM] fold 4).
- s₀ (4.1861) exceeds every learned base (3.18–3.59); the prereg defines no
  comparison against s₀ — descriptive only.

## Next decision and whose it is

By the prereg, a fired trigger means Stage I-2 ("the stacked meta-learner, xgb
first; anything heavier needs its own gate … over surviving bases' OOF outputs +
slow state. Same OOF discipline") proceeds; the operator-decision branch is the
"otherwise" branch, which did not occur. What the prereg does NOT freeze is the
Stage I-2 numeric design (inputs, model, folds, bar), so the next artefact is a
Stage I-2 preregistration frozen BEFORE any I-2 fit — authored by the agent,
reviewed by codex, like #1076. Whether a 0.087 block-t margin over the pooled
control should carry the line into I-2 is not a question the prereg asks; it is
surfaced here for the operator's information, not as a gate this record can
apply. The evaluation window 2024-07..2026-06 stays sealed.
