# Progress — exploratory baseline allocator replay diagnostics (2026-07-09)

**STATUS**: reframed after Codex review — this is exploratory diagnostics,
**not** a valid D6 S0 run. The freeze record and results were committed
together in this PR while D6's governing RFC (#443) was still under
`CHANGES_REQUESTED`; an in-artifact timestamp cannot prove the freeze
genuinely preceded the runs, which is what preregistration requires. See
the memo's status note for the full explanation.

**What**: Ran the 7 registered Phase-1 baseline allocator arms referenced by
the Deployment Governor replay protocol
(`doc/design/2026-07-09-governor-prereg-replay-protocol.md`, PR #443, not yet
merged) through the existing `run_ab_replay.py` harness (renquant-pipeline,
unmodified). Self-reported freeze record: 497 fwd_1d sessions (2024-01-02 →
2026-03-27), frozen sim-DB sha256 `82084a6d…772a88` (independently
re-verified against the live file as part of this review — matches exactly),
hypothesis-generation window 2026-06-23 → 2026-07-09 excluded by end-cut
(all sessions predate it by ≥ 88 days).

**Diagnostic observation (not a decision, not usable to select an allocator)**:
applying D6's promotion-bar math retroactively, no arm beats
`equal_weight_top_k` or `inverse_vol_top_k` at the bar (≥ +1 bp/day AND HAC
CI excl 0 AND DSR ≥ 0.95 AND PBO ≤ 0.10) — QP family leads EW by +2.5–2.6
bp/day (HAC t ≈ 0.85, CI includes 0) and IV by +5.1–5.2 bp/day (t ≈ 2.5, CI
excludes 0) but pooled PBO = 0.171 fails everything; the prior "A2 α-tilt
dominates current_qp" clean-signal finding does not reproduce in this
exploratory replay (−1.56 bp/day vs current_qp, n.s., plus dw_max violations
on 497/497 sessions) — worth a genuine preregistered re-check, not treated
as settled.

**Artifacts**:
- Results memo: `doc/research/2026-07-09-s0-phase1-baseline-replay.md`
  (status note up top, freeze record, per-arm tables, diagnostic ordering
  observation, explicit list of why this doesn't satisfy D6 — including but
  not limited to tax drag and whole-share quantization not being implemented
  by the existing harness).
- Raw evidence JSON + freeze record + deployed-fraction script:
  `doc/research/evidence/s0_phase1/`.

**Boundaries honored**: read-only on all repos and the live tree; replay ran
against a byte-identical scratch copy of `data/sim_runs.db`; no pipeline code
modified; no cloud spend (full run ≈ 7 s local).

**Next**: run the actual preregistered S0 after #443 is approved and merged —
freeze record committed on its own, before any arm executes, against the
approved protocol. Phase-2 (`governor_kelly` arm) remains pending D2, flag
OFF, and additionally requires frozen disjoint tuning/eval session subsets
plus harness support for tax drag and whole-share quantization per protocol
§1.1.
