# Exploratory baseline-harness diagnostics — allocator A/B replay (2026-07-09)

**Date**: 2026-07-09
**Related**: Deployment Governor RFC (PR #443, under review) and its companion
replay protocol draft [`doc/design/2026-07-09-governor-prereg-replay-protocol.md`](../design/2026-07-09-governor-prereg-replay-protocol.md).

> ## STATUS — EXPLORATORY ONLY
>
> This run **predates approval of the D6 protocol** (RFC #443 is still under
> review), and the run-input inventory below was committed **together with the
> results**, not pushed before execution. A timestamp inside a still-editable
> PR artifact is not a tamper-proof pre-run commitment — the artifact structure
> cannot prove the inventory preceded the results, which is exactly what
> preregistration exists to guarantee. It therefore is **not** a preregistered
> run and **MUST NOT be used to select the L2 allocator or to clear any
> D6 / Deployment Governor gate**.
>
> A valid D6 evaluation begins only after RFC #443 approval, with:
> 1. a freeze commit **pushed BEFORE execution** (session IDs + input hashes),
> 2. the registered conventions actually implemented in the harness —
>    **stateful positions, tax drag, integer (whole-share) quantization, and
>    in-allocator sector caps** — none of which the current harness models,
> 3. disjoint tuning/evaluation session subsets frozen in the same commit.
>
> Everything below is hypothesis-generation material for designing that run.

**Bottom line (as hypotheses, not verdicts)**: on 497 historical WF-trace
sessions, none of the seven baseline arms separates from the naive
diversification floors with jointly convincing statistics under the thresholds
drafted in D6 (point estimate, HAC CI, DSR, PBO). The data *suggest* (i) rough
naive-diversification parity at the daily horizon — the QP family leads
equal-weight by only ~2.5 bp/day with a HAC CI straddling 0 — and (ii) that the
earlier clean-signal finding "Stage-A A2 α-tilt dominates current_qp" does not
carry over to the WF manifold. Both are to be tested properly in the
post-approval registered run.

---

## 0. Run inputs and session inventory (recorded at run time — NOT a preregistration freeze)

Machine-readable inventory with all exact session IDs:
[`evidence/exploratory_baseline/run_input_inventory.json`](evidence/exploratory_baseline/run_input_inventory.json)
(sha256 `f3c4491c091c03de8db41363df27d06a2c1c1d2973b44c23313d1840ea34fd4b`).
Raw artifacts retain the labels they were generated under; they are committed
unmodified.

| Item | Value |
|---|---|
| Loader | `renquant_pipeline.kernel.portfolio_qp.wf_replay_loader.load_replay_bars_from_sim_db` — the default WF-cut loader of `run_ab_replay.py` |
| Source decision-trace DB | `RenQuant/data/sim_runs.db` (read-only; replay ran against a byte-identical frozen scratch copy) |
| DB sha256 | `82084a6d026a1a8db39c92d19ee119f7f79c96e82a4dade91404d93848772a88` |
| DB as-of mtime / size | 2026-07-06 16:12:59 / 21,925,888 bytes |
| Sector-cap snapshot | `renquant-strategy-104/configs/strategy_config.json`, sha256 `eeb247f8c5f1305ace0531715e97e52684593d43dd831e11c35658697ed0f174`, mtime 2026-07-09 20:32:16 (159-name sector_map, max_positions_per_sector = 6; Option-2 today-snapshot per #136/#154) |
| CLI cut range | 2024-01-01 → 2026-06-22 (end-cut excludes the 2026-06-23 → 2026-07-09 hypothesis-generation window) |
| Sessions, fwd_1d (primary) | 497 sessions, 2024-01-02 → 2026-03-27 |
| Sessions, fwd_60d (secondary) | 483 sessions, 2024-01-02 → 2026-03-09 |
| Data cutoff | 2026-03-27 — every session predates the excluded window by ≥ 88 days |
| #442-inspected sessions | all fall inside the excluded window; none exist in the replay range |
| Run timestamp | 2026-07-09T13:46Z (see JSON) |
| Regime mix (497 sessions) | BULL_CALM 90.3%, BULL_VOLATILE 5.6%, CHOPPY 3.0%, BEAR 1.0% |

Harness conventions in effect: 5 bps linear cost per traded dollar per side (L1
turnover × 5 bp), full fill at session close, all arms allocating from the same
ConstraintSnapshot (per-name cap 15%/20% by regime, dw_max 10%, 5% cash
reserve). The harness does **not** model tax drag, whole-share quantization, or
stateful positions — see §7.

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

- Primary pass: `--fwd-horizon-days 1` (non-overlapping daily returns; the
  harness's internal `constraint_fidelity` check passes with the sector-cap
  snapshot supplied — a harness field name, not a status claim for this run).
- Secondary pass: `--fwd-horizon-days 60 --allow-overlapping-forward-horizon`
  (prod-label horizon; overlapping windows inflate pooled statistics — §6).
- Runtime: ~7 s per pass locally; no cloud resources used.
- The loader is deterministic (sorted (date, ticker)), so the three incumbent
  passes replay identical bars; paired blocks are exact re-pairings.
- No pipeline code was added or modified; renquant-pipeline was consumed
  read-only.

Raw evidence JSON: [`evidence/exploratory_baseline/`](evidence/exploratory_baseline/).

## 2. Per-arm results — fwd_1d primary pass (497 sessions)

Deployed fraction computed from each arm's `target_w` on the identical bar
sequence
([`evidence/exploratory_baseline/deployed_fraction_and_gates.json`](evidence/exploratory_baseline/deployed_fraction_and_gates.json)).
The replay is stateless (w_current = 0 each session), so deployed fraction ≡
session turnover, and the 10% per-name dw_max cap bounds deployment at
0.10 × n_candidates (mean 5.7 candidates/session → ceiling ≈ 0.57). Deployment
numbers characterize the harness convention, not the live book.

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
slices): DSR ≥ 0.998 for all seven arms; PBO = 0.171 for all seven arms (the
pooled-manifold PBO is arm-invariant at this slice count). Arms with
hard-constraint violations (current_qp, hard_only, stage_a_a2) are stamped
`diagnostic_only` by the harness's fail-closed gate.

## 3. Paired comparisons vs the naive-diversification floors (fwd_1d)

Sign convention: positive = challenger beats the floor. |HAC t| > 1.96 ⟺ HAC
95% CI excludes 0. These tables report how each pairing sits relative to the
thresholds *drafted* in D6 — recorded purely to inform the future registered
run, not as pass/fail verdicts.

### 3.1 vs `equal_weight_top_k`

| Challenger | Paired mean (bp/day) | HAC t | CI excl 0 | DSR | PBO |
|---|---|---|---|---|---|
| hybrid_option_f | +2.60 | +0.87 | no | ~1.0 | 0.171 |
| hard_only_qp | +2.53 | +0.86 | no | ~1.0 | 0.171 |
| current_qp | +2.49 | +0.84 | no | ~1.0 | 0.171 |
| stage_a_a2 | +0.93 | +0.30 | no | ~1.0 | 0.171 |
| fractional_kelly | −2.00 | −0.99 | no | ~1.0 | 0.171 |
| inverse_vol | −2.62 | −1.09 | no | ~1.0 | 0.171 |

### 3.2 vs `inverse_vol_top_k`

| Challenger | Paired mean (bp/day) | HAC t | CI excl 0 | DSR | PBO |
|---|---|---|---|---|---|
| hybrid_option_f | +5.22 | +2.55 | yes | ~1.0 | 0.171 |
| hard_only_qp | +5.15 | +2.60 | yes | ~1.0 | 0.171 |
| current_qp | +5.11 | +2.53 | yes | ~1.0 | 0.171 |
| stage_a_a2 | +3.55 | +0.73 | no | ~1.0 | 0.171 |
| equal_weight | +2.62 | +1.09 | no | ~1.0 | 0.171 |
| fractional_kelly | +0.62 | +0.95 | no | ~1.0 | 0.171 |

Under the D6-drafted joint thresholds (point ≥ +1 bp/day, CI excluding 0,
DSR ≥ 0.95, PBO ≤ 0.10), no pairing satisfies all four at once: vs equal-weight
the CI never excludes 0; vs inverse-vol three pairings clear the CI but the
pooled PBO (0.171) sits above the drafted 0.10 line for every arm.

### 3.3 vs the reference `current_qp`

hybrid_option_f ≈ current_qp: paired mean +0.11 bp/day for hybrid (HAC t =
0.32, n.s.) while winning 70.8% of sessions with zero hard-cap violations
(current_qp: 54). hard_only_qp −0.03 bp/day (t = −0.12, n.s.). stage_a_a2
−1.56 bp/day vs current_qp (t = −0.31, n.s.) — the diagnostic clean-signal
claim "A2 dominates current_qp at >2.7σ" **does not reproduce** on the WF
manifold; A2 additionally ignores the 10% per-session dw cap (dw_max violation
on 497/497 sessions), so its return stream is not feasibility-honest.

The harness's own built-in verdict logic (win-rate z + its internal PBO < 0.5
line — a different and weaker standard than D6 drafts) selects
`hybrid_option_f_allocator` over current_qp in all three incumbent passes.
Recorded for completeness; it carries no gate-clearing weight.

## 4. Observed ordering and hypotheses generated

**Order (fwd_1d, mean daily return):**
`hybrid_option_f ≈ hard_only_qp ≈ current_qp (+17.8–17.9 bp/day) > stage_a_a2 (+16.3) > equal_weight (+15.3) > fractional_kelly (+13.3) > inverse_vol (+12.7)`

Hypotheses for the registered run (none of these is a conclusion):

1. **Naive-diversification parity at the daily horizon.** The QP family's edge
   over equal-weight (~+2.5 bp/day, HAC CI straddling 0) is consistent with
   parity; the registered run should be powered to distinguish +1 bp/day.
2. **The DeMiguel "naive dominates optimized" direction is NOT suggested
   here** — point estimates favor the QP family over both floors — but the
   evidence is statistically weak vs equal-weight.
3. **A2 α-tilt dominance is likely a clean-signal artifact**: it fails to
   reproduce on the WF manifold and violates the per-session dw cap on every
   bar. The registered run should include a feasibility-honest A2 variant.
4. **hybrid_option_f may be a violation-free drop-in for current_qp** (same
   returns, zero hard-cap violations, 70.8% session win rate) — worth a
   dedicated registered comparison.
5. Per-regime: 90.3% of sessions are BULL_CALM; BEAR (5), CHOPPY (15),
   BULL_VOLATILE (28) are all undersampled (< 30 bars) — per-regime ordering
   is not interpretable from this run.

## 5. Measurements against the D6-drafted §4 tolerances (diagnostic only)

| Drafted tolerance | Measurement on this run |
|---|---|
| Max single-name weight ≤ 12% | 6 arms max out at 10.0% (dw_max-bound); stage_a_a2 reaches 20% and exceeds 12% in 497/497 sessions |
| Max sector weight ≤ 35% | every arm exceeds 35% at least once: current_qp 32 sessions (max 50%), hybrid 32, hard_only 25, equal_weight/inverse_vol/kelly 1 each (max ≈ 40%). Structural: mean 5.7 candidates/session under a 90%-slack snapshot sector cap (6 × 15%) makes ≥ 35% single-sector sessions mechanical. Design note for D6: the governor arm must enforce the 35% cap inside the allocator, not inherit the snapshot's |
| Session turnover ≤ 2× equal-weight | max observed ratio 1.25 (current_qp) |
| Max drawdown ≤ 0.30 | worst observed −16.9% |
| Fail-closed on stale model | not measurable here (governor arm does not exist yet) |

## 6. fwd_60d secondary pass (overlapping windows — weakest evidence tier)

Prod-label horizon (483 sessions). Overlapping 60-day forward returns treated
as bar returns inflate every pooled statistic; the harness stamps the run
research-only and PBO rises to 0.628 for all arms. Directionally consistent
with fwd_1d: current_qp/hybrid lead equal_weight by +177 bp/60d (HAC t = 4.3)
and inverse_vol by +247 bp/60d (t = 4.3). Recorded in
[`evidence/exploratory_baseline/fwd60d_research.json`](evidence/exploratory_baseline/fwd60d_research.json)
and the two 60d incumbent re-pairings; no conclusion is drawn from this pass.

## 7. Known limitations (must be resolved before any registered D6 run)

1. **Not preregistered**: the run executed before RFC #443 approval and the
   input inventory was committed with the results. A registered run needs the
   freeze commit pushed before execution.
2. **"Manifest SHA" scope**: the default loader consumes the sim decision-trace
   DB (`data/sim_runs.db`), not the `walkforward_*` cut manifests under
   `backtesting/renquant_104/artifacts`; the recorded hash is of the DB plus
   the strategy-config snapshot.
3. **Tax drag not modeled**: the harness applies only the 5 bps/side linear
   cost; `tax_drag()` is not wired into `allocator_replay`. Identical across
   arms, but a registered run under the drafted §1.1 conventions requires it.
4. **Whole-share quantization not modeled**: continuous weights only.
5. **Stateless replay**: w_current = 0 every session — no position carry, so
   turnover ≡ deployment and multi-day holding effects are invisible.
6. **Deployed fraction** is not emitted by the harness JSON; it was computed by
   a read-only scratch script over the identical frozen bars
   ([`evidence/exploratory_baseline/compute_deployed_fraction.py`](evidence/exploratory_baseline/compute_deployed_fraction.py)).
7. **Paired blocks vs the two floors** come from re-running the same CLI with
   `--incumbent` set accordingly (the CLI emits paired blocks only against its
   incumbent; deterministic loader ⇒ identical bars).
8. **No tuning/eval split**: no hyperparameters were chosen on this data (all
   arms run registry defaults), but a registered run must still freeze disjoint
   subsets in advance.
9. **Sector caps are today's snapshot** (Option 2, #136/#154): historical
   per-session sector maps are not reconstructable;
   `sector_snapshot_source: today_snapshot` is stamped in every evidence JSON.

## 8. Reproduction

The committed inventory (DB SHA, cut range, allocator list, incumbent, horizon,
strategy-config SHA) fully determines each evidence JSON (deterministic loader
ordering). Commands in §1.
