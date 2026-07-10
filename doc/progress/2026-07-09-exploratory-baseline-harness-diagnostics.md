# Progress — Exploratory baseline-harness diagnostics (2026-07-09)

**STATUS: EXPLORATORY ONLY.** This run predates approval of the D6 replay
protocol (RFC #443, under review) and its input inventory was committed
together with the results — it is NOT a preregistered run and MUST NOT be used
to select the L2 allocator or clear any D6/Governor gate. A valid D6 run begins
only after RFC #443 approval, with a freeze commit pushed before execution and
with the registered stateful/tax/integer/sector-cap conventions implemented.

**What**: Ran the 7 baseline allocator arms named in the D6 protocol draft
(`doc/design/2026-07-09-governor-prereg-replay-protocol.md`) through the
existing `run_ab_replay.py` harness (renquant-pipeline, unmodified) as a
harness shakeout and hypothesis-generation pass. Run inputs recorded at run
time: 497 fwd_1d sessions (2024-01-02 → 2026-03-27), frozen sim-DB sha256
`82084a6d…772a88`, sessions in the 2026-06-23 → 2026-07-09 window excluded by
end-cut (all sessions predate it by ≥ 88 days).

**Observations (hypotheses, not verdicts)**: under the D6-drafted joint
thresholds no arm separates from `equal_weight_top_k` or `inverse_vol_top_k`
(pooled PBO 0.171 above the drafted 0.10 line everywhere; HAC CI vs
equal-weight straddles 0) — suggests naive-diversification parity at the daily
horizon, to be tested properly post-approval. The prior clean-signal
"A2 α-tilt dominates current_qp" finding does not reproduce on the WF manifold
(−1.56 bp/day vs current_qp, n.s., dw_max violations on 497/497 sessions).
hybrid_option_f matched current_qp with zero hard-cap violations — candidate
hypothesis for a registered comparison.

**Artifacts**:
- Memo: `doc/research/2026-07-09-exploratory-baseline-harness-diagnostics.md`
  (STATUS box at top, run-input inventory, per-arm tables, hypotheses, 9 known
  limitations — notably tax drag, whole-share quantization, and stateful
  positions are not implemented by the existing harness).
- Raw evidence JSON + input inventory + deployed-fraction script:
  `doc/research/evidence/exploratory_baseline/`.

**Boundaries honored**: read-only on all repos and the live tree; replay ran
against a byte-identical scratch copy of `data/sim_runs.db`; no pipeline code
modified; no cloud spend (full run ≈ 7 s local).

**Next**: after RFC #443 approval — freeze commit (session subsets + hashes)
pushed before execution, harness upgrades for the registered conventions, then
the actual D6 Phase-1/Phase-2 evaluation.
