# Exploratory baseline-allocator replay diagnostics (NOT preregistered, NOT decision-grade)

**Date**: 2026-07-09
**Status**: EXPLORATORY DIAGNOSTICS ONLY. This is **not** a valid D6 S0 run.

**Why this is not S0** (per Codex review): D6 preregistration requires an
independently committed freeze — pushed as its own artifact, BEFORE any arm
executes, against an APPROVED protocol. Neither condition holds here: the
freeze record and the results below were introduced together in this single
PR, and D6's own governing RFC (**#443**) was still under `CHANGES_REQUESTED`
when this ran. A timestamp inside an unmerged, still-editable artifact is not
a tamper-proof pre-run commitment — it cannot rule out the freeze having been
written after the results were already known. This label change does not
allege that actually happened; it says the current artifact structure cannot
prove it didn't, which is what preregistration exists to guarantee.

**What this IS**: a real, reproducible run of the 7 registered Phase-1
baseline allocators through the existing `run_ab_replay.py` harness
(unmodified — no new pipeline code). Every number below is independently
verifiable: the source DB and strategy-config sha256 hashes in the evidence
JSON were re-derived directly against the live files as part of this review
and matched exactly, and the reported session count/date range are
reproducible from the committed evidence. Useful as harness/allocator
engineering diagnostics.

**What this is NOT, and cannot be used for**: it cannot select an L2
allocator, validate Governor deployment behavior, or satisfy any D6
promotion gate. A genuine S0 run requires, in order: #443 approved and
merged, then a freeze record committed on its own — before any arm executes
— against that approved protocol.

**Protocol referenced for context (not satisfied by this run)**:
[`doc/design/2026-07-09-governor-prereg-replay-protocol.md`](../design/2026-07-09-governor-prereg-replay-protocol.md)
(D6, PR #443).

**Diagnostic observation, not a protocol verdict**: retroactively applying
D6's promotion-bar math (≥ +1 bp/day paired mean AND HAC 95% CI excluding 0
AND DSR ≥ 0.95 AND PBO ≤ 0.10) to this exploratory run, none of the seven
baseline arms would have cleared it against either naive-diversification
floor. The QP family (current_qp / hybrid_option_f / hard_only) leads
equal_weight by +2.5–2.6 bp/day but the HAC CI includes 0; it leads
inverse_vol by +5.1–5.2 bp/day with HAC CI excluding 0 and DSR ≈ 1.0, but
pooled PBO = 0.171 > 0.10 fails the bar. The prior clean-signal finding that
Stage-A A2 α-tilt dominates current_qp does **not** reproduce in this
exploratory replay. None of this authorizes an L2/Governor decision; it is
recorded here only as a diagnostic prior for whoever runs the real S0.

---

## 0. Freeze record (committed alongside results — NOT an independent pre-run freeze)

This record was written into the same PR as the results below, not pushed as
its own prior commit against an approved protocol — see the status note
above for why that means it does not satisfy D6 preregistration. It is
included because it makes every number below independently reproducible
(source DB / config pinned by sha256, exact session ID list), which is
useful regardless of preregistration status.

Full machine-readable record with **all exact session IDs**:
[`evidence/s0_phase1/session_freeze_record.json`](evidence/s0_phase1/session_freeze_record.json)
(sha256 `f3c4491c091c03de8db41363df27d06a2c1c1d2973b44c23313d1840ea34fd4b`).

| Item | Value |
|---|---|
| Loader (registered) | `renquant_pipeline.kernel.portfolio_qp.wf_replay_loader.load_replay_bars_from_sim_db` — the default WF-cut loader of `run_ab_replay.py` |
| Source decision-trace DB | `RenQuant/data/sim_runs.db` (read-only; replay ran against a byte-identical frozen scratch copy) |
| DB sha256 (= manifest SHA for this loader) | `82084a6d026a1a8db39c92d19ee119f7f79c96e82a4dade91404d93848772a88` |
| DB as-of mtime / size | 2026-07-06 16:12:59 / 21,925,888 bytes |
| Sector-cap snapshot | `renquant-strategy-104/configs/strategy_config.json`, sha256 `eeb247f8c5f1305ace0531715e97e52684593d43dd831e11c35658697ed0f174`, mtime 2026-07-09 20:32:16 (159-name sector_map, max_positions_per_sector = 6; Option-2 today-snapshot per #136/#154) |
| CLI cut range | 2024-01-01 → **2026-06-22** (end-cut mechanically excludes the 2026-06-23 → 2026-07-09 window) |
| Sessions, fwd_1d (primary) | **497** sessions, 2024-01-02 → 2026-03-27 |
| Sessions, fwd_60d (research) | 483 sessions, 2024-01-02 → 2026-03-09 |
| Data cutoff | 2026-03-27 (last session with μ/σ + realized fwd_1d overlap) — every session predates the exclusion window by ≥ 88 days |
| #442-inspected sessions | all fall inside the exclusion window (2026-06-23 → 2026-07-09); none exist in the replay range, so no additional exclusions were required |
| Freeze timestamp (self-reported, not independently verifiable) | 2026-07-09T13:46Z (see JSON) — an in-artifact timestamp, not a prior committed record; see status note above |
| Regime mix (497 sessions) | BULL_CALM 90.3%, BULL_VOLATILE 5.6%, CHOPPY 3.0%, BEAR 1.0% |

Frozen conventions honored by the harness: 5 bps linear cost per traded dollar per
side (L1 turnover × 5 bp), full fill at session close (fwd returns measured from
close), matched E* by construction (all arms allocate from the same
ConstraintSnapshot: per-name cap 15%/20% by regime, dw_max 10%, 5% cash reserve).
See §6 for the two §1.1 conventions the existing harness does **not** implement
(tax drag, whole-share quantization) — declared deviations, identical across arms.

## 1. What ran

```
python -m renquant_pipeline.kernel.portfolio_qp.run_ab_replay \
  --wf-artifact-root <frozen sim_runs.db copy> \
  --start-cut 2024-01-01 --end-cut 2026-06-22 \
  --fwd-horizon-days 1 \
  --allocators current_qp,hard_only_qp_allocator,hybrid_option_f_allocator,\
fractional_kelly_top_k,equal_weight_top_k,inverse_vol_top_k,stage_a_a2_long_only \
  --incumbent <current_qp | equal_weight_top_k | inverse_vol_top_k> \
  --strategy-config renquant-strategy-104/configs/strategy_config.json
```

- Primary pass: `--fwd-horizon-days 1` → the harness stamps
  `decision_grade_daily_return: true` and `constraint_fidelity.decision_grade: true`.
- Research pass: `--fwd-horizon-days 60 --allow-overlapping-forward-horizon`
  (prod-label horizon; the harness hard-blocks overlapping horizons as decision
  evidence, so this pass is diagnostic-only — §5).
- Runtime: ~7 s per pass on the workstation (smoke slice projected ~20 s; no
  cloud resources used).
- The loader is deterministic (sorted (date, ticker)), so the three incumbent
  passes replay identical bars; paired blocks are exact re-pairings.

Raw evidence JSON: [`evidence/s0_phase1/`](evidence/s0_phase1/).

## 2. Per-arm results — fwd_1d primary pass (497 sessions)

The harness stamps this horizon `decision_grade_daily_return: true` (its own
internal flag meaning "non-overlapping, so statistically valid for daily
paired inference" — distinct from the fwd_60d overlapping-horizon pass in
§6). That is a harness-level statistical-validity flag, not a claim that
this run is D6 decision-grade; per the status note above, no output here can
be used to make an allocator/Governor decision.

Deployed fraction is computed per the D6 protocol's §3 estimand-1 definition
(referenced for terminology only, since this run does not satisfy D6), from
each arm's
`target_w` on the identical bar sequence
([`evidence/s0_phase1/s0_phase1_deployed_fraction_and_gates.json`](evidence/s0_phase1/s0_phase1_deployed_fraction_and_gates.json)).
Note the replay is stateless (w_current = 0 each session), so deployed fraction ≡
session turnover, and the 10% per-name dw_max cap bounds deployment at
0.10 × n_candidates (mean 5.7 candidates/session → deployment ceiling ≈ 0.57).
Deployment numbers characterize the harness convention, not the live book.

| Arm | Mean ret (bp/day) | Sharpe | Cum ret | MDD | Deployed (mean / median) | Hard-cap violations (family) |
|---|---|---|---|---|---|---|
| hybrid_option_f_allocator | **+17.93** | 2.296 | +134.6% | −16.9% | 0.453 / 0.360 | **0** (QP fallback on 11 sessions) |
| hard_only_qp_allocator | +17.86 | **2.340** | +134.1% | −16.3% | 0.445 / 0.349 | 28 (cash_budget 2, dw_max 26) |
| current_qp (reference) | +17.82 | 2.274 | +133.3% | −16.9% | 0.460 / 0.365 | 54 (cash_budget 8, dw_max 46) |
| stage_a_a2_long_only | +16.26 | 1.668 | +112.2% | −15.7% | 0.322 / 0.300 | **497** (dw_max — every session) |
| equal_weight_top_k | +15.33 | 1.912 | +106.0% | −16.4% | 0.368 / 0.400 | 0 |
| fractional_kelly_top_k | +13.33 | 2.028 | +88.7% | −16.3% | 0.353 / 0.393 | 0 |
| inverse_vol_top_k | +12.71 | 1.973 | +83.2% | −16.2% | 0.359 / 0.400 | 0 |

DSR / PBO (pooled significance pass, `compute_significance_verdicts`, 16 PBO
slices): DSR ≥ 0.998 for **all seven arms**; PBO = **0.171 for all seven arms**
(the pooled-manifold PBO is arm-invariant at this slice count). Arms with
hard-constraint violations (current_qp, hard_only, stage_a_a2) are stamped
`diagnostic_only` by the harness's fail-closed promotion gate.

## 3. Paired comparisons vs the naive-diversification floors (fwd_1d)

Sign convention: positive = challenger beats the floor. HAC 95% CI excludes 0 ⟺
|HAC t| > 1.96.

### 3.1 vs `equal_weight_top_k`

| Challenger | Paired mean (bp/day) | ≥ +1 bp/day | HAC t | CI excl 0 | DSR ≥ 0.95 | PBO ≤ 0.10 | **Promotion bar** |
|---|---|---|---|---|---|---|---|
| hybrid_option_f | +2.60 | PASS | +0.87 | **FAIL** | PASS | FAIL (0.171) | **FAIL** |
| hard_only_qp | +2.53 | PASS | +0.86 | **FAIL** | PASS | FAIL | **FAIL** |
| current_qp | +2.49 | PASS | +0.84 | **FAIL** | PASS | FAIL | **FAIL** |
| stage_a_a2 | +0.93 | FAIL | +0.30 | FAIL | PASS | FAIL | **FAIL** |
| fractional_kelly | −2.00 | FAIL | −0.99 | FAIL | PASS | FAIL | **FAIL** |
| inverse_vol | −2.62 | FAIL | −1.09 | FAIL | PASS | FAIL | **FAIL** |

### 3.2 vs `inverse_vol_top_k`

| Challenger | Paired mean (bp/day) | ≥ +1 bp/day | HAC t | CI excl 0 | DSR ≥ 0.95 | PBO ≤ 0.10 | **Promotion bar** |
|---|---|---|---|---|---|---|---|
| hybrid_option_f | +5.22 | PASS | +2.55 | PASS | PASS | **FAIL (0.171)** | **FAIL** |
| hard_only_qp | +5.15 | PASS | +2.60 | PASS | PASS | **FAIL** | **FAIL** |
| current_qp | +5.11 | PASS | +2.53 | PASS | PASS | **FAIL** | **FAIL** |
| stage_a_a2 | +3.55 | PASS | +0.73 | FAIL | PASS | FAIL | **FAIL** |
| equal_weight | +2.62 | PASS | +1.09 | FAIL | PASS | FAIL | **FAIL** |
| fractional_kelly | +0.62 | FAIL | +0.95 | FAIL | PASS | FAIL | **FAIL** |

### 3.3 vs the incumbent `current_qp` (reference pairing)

hybrid_option_f ≈ current_qp: paired mean +0.11 bp/day for hybrid (HAC t = 0.32,
n.s.) while winning **70.8%** of sessions with **zero** hard-cap violations
(current_qp: 54). hard_only_qp −0.03 bp/day (t = −0.12, n.s.). stage_a_a2
**−1.56 bp/day vs current_qp** (t = −0.31, n.s.) — the diagnostic clean-signal
claim "A2 dominates current_qp at >2.7σ" does **not** reproduce on the WF
manifold; A2 additionally ignores the 10% per-session dw cap (dw_max violation
on 497/497 sessions), so its return stream is not feasibility-honest.

The harness's own §8 verdict (weaker bar than this protocol: PBO < 0.5 +
win-rate z > 2) selects `hybrid_option_f_allocator` as promotion candidate over
current_qp in all three incumbent passes. That is a harness verdict, not a
protocol-bar pass — recorded for completeness only.

## 4. Ordering observation (diagnostic only — this phase does not authorize an answer)

**Order (fwd_1d, mean daily return):**
`hybrid_option_f ≈ hard_only_qp ≈ current_qp (+17.8–17.9 bp/day) > stage_a_a2 (+16.3) > equal_weight (+15.3) > fractional_kelly (+13.3) > inverse_vol (+12.7)`

These are diagnostic observations from an exploratory run, not a resolved
protocol question — this run does not satisfy D6, so nothing below is a
sanctioned decision:

1. **Nothing clears D6's promotion-bar math, applied retroactively.** Binding
   failures: HAC CI vs equal_weight includes 0 (t ≈ 0.85), and PBO = 0.171 >
   0.10 everywhere (including vs inverse_vol where the CI does exclude 0).
2. **The DeMiguel naive floor does NOT dominate here** — direction favors the QP
   family over equal-weight/inverse-vol, opposite to the ordering that would
   suggest "ship equal-weight" — but the evidence is not promotion-grade,
   preregistered, or authorized for that call.
3. **α-tilt-dominates-QP does not reproduce on this manifold** (§3.3): the
   prior clean-signal finding does not hold up in this exploratory replay —
   worth a genuine, properly preregistered re-check, not treated as settled.
4. Per-regime: 90.3% of sessions are BULL_CALM; BEAR (5), CHOPPY (15) and
   BULL_VOLATILE (28) are all undersampled (< 30 bars) — per-regime ordering is
   diagnostic-only regardless of preregistration status.

Possible consequence for the Governor program, stated as a hypothesis to be
tested by a real S0, not a conclusion: Phase-2 (governor_kelly arm, pending
D2) may inherit a floor set where the QP family is the strongest baseline
but no allocator clears the bar; if that holds under a genuine preregistered
run, D6 §5's own rule is that the L2 answer defaults to naive under the L1
E* overlay. This run cannot be cited as evidence for that outcome — only as
a reason to prioritize running the real S0 before D2 lands.

## 5. §4 non-degradation gates, measured on the Phase-1 arms (fwd_1d)

| Gate (frozen tolerance) | Result |
|---|---|
| Max single-name weight ≤ 12% | PASS for 6 arms (max 10.0%, dw_max-bound). **stage_a_a2 FAILS** (20% name weight, 497/497 sessions > 12%) |
| Max sector weight ≤ 35% | **Every arm breaches at least once**: current_qp 32 sessions (max 50%), hybrid 32, hard_only 25, equal_weight/inverse_vol/kelly 1 each (max ≈ 40%). Structural: mean 5.7 candidates/session under a 90%-slack snapshot sector cap (6 × 15% = 90%) makes ≥ 35% single-sector sessions mechanical. The protocol tolerance is stricter than the replay snapshot cap — flagged for the Phase-2 design (governor arm must enforce the 35% cap inside the allocator, not inherit the snapshot's) |
| Session turnover ≤ 2× equal-weight | PASS all arms (max ratio 1.25 = current_qp) |
| Max drawdown ≤ 0.30 | PASS all arms (worst −16.9%) |
| Fail-closed on stale model | N/A — Phase-2 (governor) gate |

## 6. fwd_60d research pass (diagnostic only — NOT decision evidence)

Prod-label horizon (483 sessions). Overlapping 60-day forward returns treated as
bar returns inflate every pooled statistic; the harness stamps
`decision_grade_daily_return: false` and PBO = 0.628 for all arms. Directionally
consistent with fwd_1d: current_qp/hybrid lead equal_weight by +177 bp/60d
(HAC t = 4.3) and inverse_vol by +247 bp/60d (t = 4.3). Recorded in
[`evidence/s0_phase1/s0_phase1_fwd60d_research.json`](evidence/s0_phase1/s0_phase1_fwd60d_research.json)
and the two 60d incumbent re-pairings; no conclusion is drawn from this pass.

## 7. Why this is not valid D6 evidence (explicit, complete)

0. **Preregistration integrity (the disqualifying issue, per Codex review)**:
   the freeze record in §0 and the results in §§2-6 were committed together
   in this single PR, and D6's governing RFC (#443) was still under
   `CHANGES_REQUESTED` when this ran. Preregistration requires the freeze to
   be an independently committed artifact, pushed before any arm executes,
   against an approved protocol — an in-PR timestamp cannot prove that
   ordering. This alone means nothing in this document can stand in for S0,
   regardless of the additional deviations below (which a real S0 would also
   need to fix).
1. **"Manifest SHA"** — the registered loader consumes the sim decision-trace DB
   (`data/sim_runs.db`), not the `walkforward_*` cut manifests under
   `backtesting/renquant_104/artifacts`. The freeze SHA is therefore the SHA256
   of the DB itself (plus the strategy-config snapshot). No separate WF manifest
   file is an input to this harness.
2. **Primary horizon = fwd_1d, not the 60d prod label.** The harness hard-blocks
   overlapping horizons as decision evidence (`invalid_experiment` unless the
   research-only escape hatch is passed), and the protocol's promotion bar is
   denominated in bp/day. The 60d pass is included as research-only (§6) with
   the HAC treatment the protocol's §1.2 anticipates.
3. **Tax drag not modeled** (§1.1): the existing replay harness applies only the
   5 bps/side linear cost; `tax_drag()` is not wired into `allocator_replay`.
   Identical across arms; paired comparisons are unaffected at equal turnover
   (turnover ratios ≤ 1.25). No new code was permitted in Phase 1.
4. **Whole-share quantization not modeled** (§1.1): the harness allocates
   continuous weights. Same caveat as (3); flagged as a Phase-2 harness
   requirement before governor evidence is decision-grade under §1.1.
5. **Deployed fraction** is not emitted by the harness evidence JSON; it was
   computed by a read-only scratch script over the identical frozen bars using
   the same loader + allocator registry (script committed alongside the evidence:
   [`evidence/s0_phase1/compute_deployed_fraction.py`](evidence/s0_phase1/compute_deployed_fraction.py)).
6. **Paired blocks vs the two floors** come from re-running the same CLI with
   `--incumbent equal_weight_top_k` / `--incumbent inverse_vol_top_k` on the
   identical deterministic bars (the CLI emits paired blocks only against its
   incumbent).
7. **Nested tuning/eval split (§1 r1-3) not exercised**: Phase 1 chose no
   hyperparameters — all arms run registry defaults that predate this protocol.
   Phase-2 must freeze the disjoint tuning/evaluation session subsets before the
   governor arm runs.
8. **Sector caps are today's snapshot** (Option 2, #136/#154): historical
   per-session sector maps are not reconstructable; `sector_snapshot_source:
   today_snapshot` is stamped in every evidence JSON.

## 8. Reproduction

Freeze + runs are reproducible from the committed evidence: the frozen DB SHA,
cut range, allocator list, incumbent, horizon and strategy-config SHA fully
determine each JSON (deterministic loader ordering). Commands in §1.
