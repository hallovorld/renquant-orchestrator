# Progress: GOAL-2v3 Stage I-1 DEV RUN — all four bases pass the life screen; the I-2 trigger fires by 0.087

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
