# GOAL-4 two-expert ensemble — pre-registration (power-first, tiered)

**Status:** FROZEN spec (commit-1). Design PR; not yet executed.
**Frozen spec:** `doc/research/evidence/2026-07-23-g4-ensemble/frozen_spec.json`
(`sha256=4126b04c…`, built by `renquant_orchestrator.g4_ensemble.spec`).
**Method code:** `src/renquant_orchestrator/g4_ensemble/` (composes the codex-
reviewed `expkit` prereg primitives + a new power/MDE calculator).
**Tests:** `tests/test_g4_ensemble.py` (13, green).

---

## 0. Why this document exists (the failure it corrects)

A prior attempt fired a \$32 Modal walk-forward run to "re-inference the
history and read PatchTST's IC." That design was wrong for one decisive
reason: **it spends compute to produce a result that is knowably
under-powered.** The 60-day forward-return label creates overlapping returns,
so 2.3 years of history is only ~10 *independent* blocks. A t-test on ~10
blocks cannot separate a realistic edge (IC ≈ 0.02–0.05) from the embargo
leakage floor. Running it buys a foregone "inconclusive."

A rigorous design therefore starts from a **power analysis** and only measures
where power exists. This is that design.

## 1. Power analysis (the backbone)

Estimand: the time-mean of a per-date cross-sectional rank-IC series. Because
IC observations inside one horizon window are ~perfectly autocorrelated, the
independent-observation count is the number of non-overlapping date blocks
`K = n_dates // horizon` (`expkit.stats.usable_blocks`). One-sided z-test:

    MDE = (z_{1-alpha} + z_{power}) * sigma_ic / sqrt(K)

With ~600 trading days, `sigma_ic ≈ 0.10` (a placeholder re-estimated from real
data in Tier-0), one-sided `alpha=0.05`, `power=0.80`
(`renquant_orchestrator.g4_ensemble.power`):

| horizon | K ≈ 600/h | MDE (one-sided) | verdict |
|--------:|----------:|----------------:|---------|
| **5d**  | ~120      | **~0.025**      | powered — screen here |
| **20d** | ~30       | ~0.045          | marginal |
| **60d** | ~10       | **~0.079**      | **cannot detect a realistic edge** |

The 60d row is the crux: the minimum IC detectable at 60d (~0.08, and ~0.13
once the ~0.04 leakage floor is added) is exactly the magnitude of the
previously-retracted "+0.13" — i.e. that number sat at the detectability
boundary and was indistinguishable from floor+noise. **Conclusion: the 60d
operating-horizon go/no-go cannot be settled from history at any reasonable
MDE. History can screen for signal existence at short horizons and give a
suggestive paired increment; the definitive 60d answer requires forward
accrual.** This is stated in the frozen spec's R3 `not_covered`.

## 2. Hypotheses (frozen)

- **H1 — existence.** At least one of {XGB, PatchTST} has a placebo-clean
  cross-sectional rank-IC strictly above its shifted-label leakage floor at
  some horizon in {5, 20, 60}d.
- **H2 — increment.** The 2-expert ensemble out-ranks the *best single* expert
  on identical dates/names, measured as a **paired** clean-IC delta whose
  one-sided lower bound > 0.
- **H0 default.** No existence at any horizon ⇒ **KILL G4**. Existence but no
  positive increment ⇒ **defer to the forward test** (neither go nor kill).

Estimator of record for every verdict: the one-sided lower bound of a
**gap-respecting block bootstrap** (block = horizon) of the relevant mean —
never two separate CIs eyeballed. Bonferroni family `k = 6` (2 experts × 3
horizons); one-sided `alpha = 0.05/6`. Seeds {44, 7, 123} are unanimity checks,
not extra looks (`expkit` #264 lesson).

## 3. Tiered protocol with pre-registered gates

### Tier 0 — harness validation (prerequisite; ~\$0)
- **Positive control** (`positive_control_recovery`): inject a synthetic score
  at known rank-correlation ρ ≥ 0.6; the pipeline must recover `real_ic > 0.5`.
  Criterion `tier0_positive_control_real_ic`. If it fails, the harness is
  broken and **no result on this substrate is admissible.**
- **Negative control** (the placebo leg of every existence run): the
  shifted-label placebo *is* the leakage floor the real IC must clear;
  `clean_ic = real - placebo` is floor-subtracted by construction.

### Tier 1 — signal existence × horizon (the high-power screen; XGB ~free)
Per (expert, horizon): `label = fwd_excess(close, bench, h)`,
`placebo = shifted_label_placebo(label, gate_shift_sessions(h))`,
`clean_ic = per_date_ic(...)`, block-bootstrap the mean.
- **PASS** iff `clean_boot.lb_one_sided > 0` for some cell
  (criterion `tier1_existence_clean_ic_lb`).
- **KILL GATE (pre-registered):** if every cell's lower bound ≤ 0 across all
  experts and horizons ⇒ **KILL G4** (two individually-null experts do not
  ensemble into signal), **zero further compute.**

### Tier 2 — ensemble increment (only if Tier 1 passes)
`evaluate_increment`: paired clean-IC delta (ensemble − best single) on the
same dates; block-bootstrap. Baselines to beat: XGB-only, PatchTST-only,
equal-weight-of-experts, naive equal-weight portfolio.
- **PASS** iff `delta_boot.lb_one_sided > 0` (criterion
  `tier2_increment_paired_lb`). A CI containing 0 (the likely 60d outcome) ⇒
  **historical increment unproven ⇒ defer to Tier 3**, explicitly *not* a go.
- Net-of-cost portfolio Sharpe/APY is a **separate downstream stage**, entered
  only if the increment is positive (frictions ate 86–100% of gross for prior
  candidates — Deployment-Governor memo).

### Tier 3 — forward confirmation (the only route to 60d power; \$0 compute)
History cannot reach the required power (§1). Pre-register a live shadow
forward test with a **sequential (alpha-spending) stopping rule** and a fixed
horizon, accruing genuinely non-overlapping decisions. This is the auditable
form of "~560 sessions."

## 4. Compute plan (every dollar gated behind evidence)

- Tier 0 + Tier 1(XGB) run on existing data with cheap/GBDT models ≈ \$0.
- The **only** discretionary spend — the full walk-forward PatchTST corpus
  (43 folds, ~\$32 on Modal T4 at the measured ~38 min/fold, ≥3 seeds) — is
  unlocked **only after** Tier 1 shows a 60d-relevant lead. Spending it first
  (as the prior attempt did) is the error this design removes.

## 5. Rigor scaffolding

Pre-registration (freeze-first, committed-before-results — `expkit.prereg`);
as-of walk-forward cutoffs with horizon-matched embargo; PIT features with
train-only clipping quantiles; block-bootstrap / effective-sample inference;
Bonferroni across the existence family + multi-seed unanimity; economic
realism (net-of-cost metrics downstream); and an explicit R3 statement that the
60d verdict is *not covered* by the historical arm.

## 6. What is NOT in this PR

The real PatchTST/XGB scorers are **not** wired into the `score` input — that is
the compute-gated follow-up. This PR is the frozen method + spec + controls,
runnable end-to-end on synthetic panels (the tests), so the *design* can be
reviewed before any spend.

## 7. Reopening (R4)

A fresh expert family outside {XGB, PatchTST}; a materially different label
horizon/objective; or the Tier-3 forward test reaching its pre-registered
admissible-session count. Each reopens as a *new* frozen prereg.
