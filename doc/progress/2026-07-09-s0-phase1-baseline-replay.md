# Progress — S0 Phase-1 baseline allocator replay (2026-07-09)

**What**: Ran the 7 registered Phase-1 baseline allocator arms of the
preregistered Deployment Governor replay protocol
(`doc/design/2026-07-09-governor-prereg-replay-protocol.md`, PR #443) through the
existing `run_ab_replay.py` harness (renquant-pipeline, unmodified). Session
freeze recorded before any arm ran: 497 fwd_1d sessions (2024-01-02 → 2026-03-27),
frozen sim-DB sha256 `82084a6d…772a88`, hypothesis-generation window
2026-06-23 → 2026-07-09 excluded by end-cut (all sessions predate it by ≥ 88 days).

**Result (one line)**: no arm beats `equal_weight_top_k` or `inverse_vol_top_k`
at the promotion bar (≥ +1 bp/day AND HAC CI excl 0 AND DSR ≥ 0.95 AND
PBO ≤ 0.10) — QP family leads EW by +2.5–2.6 bp/day (HAC t ≈ 0.85, CI includes 0)
and IV by +5.1–5.2 bp/day (t ≈ 2.5, CI excludes 0) but pooled PBO = 0.171 fails
everything; the prior "A2 α-tilt dominates current_qp" clean-signal finding is
refuted on the WF manifold (−1.56 bp/day vs current_qp, n.s., plus dw_max
violations on 497/497 sessions).

**Artifacts**:
- Results memo: `doc/research/2026-07-09-s0-phase1-baseline-replay.md`
  (freeze record at top, per-arm tables, ordering verdict, 8 explicit protocol
  deviations — notably tax drag and whole-share quantization are not implemented
  by the existing harness).
- Raw evidence JSON + freeze record + deployed-fraction script:
  `doc/research/evidence/s0_phase1/`.

**Boundaries honored**: read-only on all repos and the live tree; replay ran
against a byte-identical scratch copy of `data/sim_runs.db`; no pipeline code
modified; no cloud spend (full run ≈ 7 s local).

**Next**: Phase-2 (`governor_kelly` arm) pending D2, flag OFF; requires frozen
disjoint tuning/eval session subsets plus harness support for tax drag and
whole-share quantization per protocol §1.1.
