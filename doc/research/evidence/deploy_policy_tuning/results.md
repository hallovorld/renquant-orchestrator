# Deployment-policy replay experiment — EXPLORATORY / TUNING SUBSET ONLY

**Label: EXPLORATORY HYPOTHESIS-GENERATION. Tuning subset only (149/497 sessions).
NOT decision evidence. The evaluation subset (348 sessions) was never touched.**

- Date: 2026-07-09
- Harness: renquant-pipeline `feat/replay-harness-d6-conventions` (PR #180, commit 6ac718f),
  worktree `scratchpad/wt-harness` — code untouched; arms registered via `register_allocator`.
- Freeze tool: renquant-orchestrator `feat/d6-freeze-tooling` (PR #446, commit 53be6a9d),
  worktree `scratchpad/wt-freeze`.
- Data: byte-copy of `/Users/renhao/git/github/RenQuant/data/sim_runs.db`
  (sha256 `82084a6d026a...` — identical to source at copy time). All reads against the copy.
- Freeze record: `d6_freeze_20260709.json` (seed 20260709, tuning_frac 0.3,
  exclude-window 2026-06-23:2026-07-09 inclusive). fwd_1d: 497 kept sessions
  (2024-01-02..2026-03-27), **149 tuning / 348 evaluation**. `--verify` OK post-run
  (no drift). Note: 0 sessions fell inside the exclude window at fwd_1d because the
  DB's fwd_1d joined coverage ends 2026-03-27.
- Conventions (identical across arms): `--stateful --tax --integer-shares
  --enforce-caps`, cost 5 bps/side, PV start $10,700, top-k 8, per-name cap 12%,
  sector cap 35% (strategy sector map, 156 tickers, read-only snapshot in
  `sector_map_snapshot.json`), fwd_1d horizon, D6 tax (ST 50% / LT 32%, losses = zero credit).

## (a) One-table arm comparison (149 tuning sessions, paired bars)

| arm | mean E_dep | med E_dep | total net ret | Sharpe (ann, net) | MDD | tax $ | cost $ | mean turnover | sector-cap breaches | int. resid | HAC t vs ew_full (p) | win-rate vs ew_full |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ew_full | 0.523 | 0.462 | **+4.70%** | +0.38 | −15.8% | 4,806 | 227 | 0.269 | 30 | 0.031 | — | — |
| kelly_raw | 0.498 | 0.446 | +0.62% | +0.17 | −12.1% | 3,976 | 217 | 0.263 | 26 | 0.034 | −0.69 (0.49) | 0.530 |
| govern_kelly | 0.496 | 0.446 | +0.58% | +0.16 | −12.0% | 3,954 | 217 | 0.263 | 24 | 0.033 | −0.69 (0.49) | 0.537 |
| voltarget_ew (15%) | 0.413 | 0.362 | −5.08% | −0.31 | −10.3% | 3,045 | 187 | 0.236 | 11 | 0.037 | −1.03 (0.30) | 0.678 |
| voltarget_kelly (15%) | 0.422 | 0.384 | −3.80% | −0.21 | −9.7% | 3,072 | 188 | 0.236 | 11 | 0.036 | −0.86 (0.39) | 0.604 |
| voltarget_ew_12 (12%) | 0.361 | 0.340 | −4.14% | −0.29 | −8.2% | 2,675 | 164 | 0.208 | 2 | 0.038 | −0.87 (0.39) | 0.671 |

HAC sign: arm − ew_full (negative = arm underperforms). Name-cap breaches are 0 for
all arms by construction (per-name 12% pre-applied inside each allocator; the
harness projection therefore only fires on the sector cap). Off-universe forced
liquidations: 137–141 of 149 sessions for every arm. No-candidates sessions: 0.
DSR: ew_full 0.9999, kelly/governor ~0.81–0.82, all voltarget ~0. PBO = 0.61 for
every arm (high overfit probability — consistent with these deltas being noise).

## (b) kelly_raw Σw distribution — the "no-multiplier bridge" answer

Σw = Σᵢ min(0.3·μᵢ/σᵢ², 0.12) over top-8 positive-μ names, before the 0.95 cash
budget:

- **mean 0.541, median 0.480**; p5/p25/p75/p95 = 0.195 / 0.240 / 0.857 / 0.960
- 21.5% of sessions ≥ 0.90 gross; 60.4% of sessions ≤ 0.60 gross
- UNCAPPED Σ 0.3·μ/σ²: mean 2.37, median 2.15 (i.e., raw 30%-Kelly on the 60d-horizon
  μ/σ̂ wants ~2.4× leverage); the 12% name cap binds ≥half the raw weight on
  **96% of sessions**.

So the bridge deploys ≈ **48–54%**, numerically close to the hypothesized ~59%
(8 × 7.4%), **but for a different reason than the hypothesis**: per-name Kelly is
cap-saturated almost everywhere, so realized Σw ≈ 0.12 × (# positive-μ candidates,
≤8). Deployment is **breadth-driven, not conviction-sized**: tuning sessions carry
a median of only 4 usable names (2–18; only 40/149 sessions have ≥8). The
"Σw ≈ 8×7.4%" mental model (moderate per-name Kelly weights) is falsified; the
correct model is "12% cap × candidate breadth".

## (c) Vol-targeted vs signal-governed, net of everything

**Vol-targeted arms did NOT beat signal-governed arms on the tuning subset.**

- Total net return: voltarget arms −3.8%..−5.1% vs kelly/governor +0.6% vs ew_full +4.7%.
- Per-session mean deltas vs ew_full: −7.4 to −8.3 bps, HAC t ≈ −0.9..−1.0 (p 0.30–0.39)
  — **none significant**; treat ordering as a hypothesis, not a result.
- Win-rate inversion worth flagging: voltarget arms win 60–68% of individual sessions
  (fewer dollars traded → less tax+cost per session) but lose the mean via the right
  tail — big up-sessions reward higher deployment. Lower deployment bought lower MDD
  (−8.2%..−10.3% vs −15.8%) and less tax.
- Per-regime (by-regime first, pooled second): ew_full best in BULL_CALM (128/149
  bars, Sharpe 0.79 vs voltarget ~0.0–0.2); voltarget arms best in BULL_VOLATILE
  (n=14, −3.3 vs −6.2 for ew_full) and BEAR (n=2) — both **undersampled**, but
  directionally consistent with vol-targeting paying off only in high-vol regimes,
  which the tuning window barely contains.
- govern_kelly (hysteresis 0.05 on E*) is indistinguishable from kelly_raw
  (Δtotal −4 bps, 2 fewer sector breaches): the E* path moves in ~0.12 steps as
  breadth changes, so a 0.05 band almost never holds. Governor E*: mean 0.540,
  median 0.480. Voltarget E* pre-cap: mean 0.66/0.67 (15%), 0.53 (12%); the
  per-name cap then truncates executed exposure to ~0.41/0.36 — i.e., **the
  vol-target formula frequently ASKS for more gross than the cap discipline
  will execute** (σ̂_pf mean 0.256 annualized).

Hypothesis generated (needs the eval subset + a real D6 run to test): under the
D6 cap discipline and current score-DB breadth, deployment level is dominated by
candidate breadth × per-name cap; among policies, "fully-deploy-what-the-caps-allow"
(ew_full) is the tuning-subset leader, and vol-targeting mainly buys drawdown/tax
reduction, not return.

## (d) Limitations (explicit)

1. **Exploratory, tuning subset only** — 149 sessions selected by seeded hash; the
   freeze JSON was NOT committed/pushed before arms ran (this is hypothesis
   generation, not a preregistered D6 run). Nothing here is promotion evidence;
   PBO = 0.61 across the board.
2. **Non-contiguous session sequence** — the tuning subset is a random 30% of dates,
   so the stateful carry (lots, prices, holding periods) spans multi-week gaps;
   positions are marked ONLY by each session's fwd_1d return (returns-consistent
   pricing), so inter-session price moves are invisible. Absolute return/Sharpe/MDD
   levels are therefore not portfolio-realistic; only paired arm-vs-arm contrasts
   on identical bars are meaningful. "Annualized" Sharpe treats each session as one
   day.
3. **Returns-consistent pricing** (harness convention): internal prices evolve by
   fwd_1d from the entry anchor; deviation from true close-to-close marks is a
   documented harness limitation, amplified by the non-contiguous subset.
4. **ρ = 0.4 single-parameter correlation approximation** in
   σ̂_pf = sqrt(Σw²σ² + ρ·Σ_{i≠j}w_i w_j σ_i σ_j); no factor structure, no
   regime-conditional ρ. σ̂_pf is also built from the MODEL's σ̂, not realized vol.
5. **Sigma units**: `score_distribution.sigma` is the model σ̂ on the fwd_60d label
   horizon (median 0.123 → ~25% annualized; verified against the loader, which
   passes DB values through untransformed). Vol-target arms annualize by
   sqrt(252/60) ≈ 2.049. If σ̂ were actually a different horizon, the voltarget E*
   levels shift proportionally. The Kelly ratio μ/σ² uses the DB's (same-horizon)
   values as specified by the arm formula.
6. **Universe churn dominates the tax bill**: the session universe is "tickers
   scored that day" (median 4), so 137–141/149 sessions force off-universe
   liquidations; with the D6 asymmetric tax convention (50% ST on gains, zero
   credit on losses) tax ($2.7k–4.8k) dwarfs linear cost ($164–227) and consumes
   nearly all gross return in every arm. Policy deltas are second-order to this
   churn×tax interaction; a real deployment-policy decision needs the persistent
   full watchlist universe, not the sparse score trace.
7. **Thin breadth compresses the arms**: with ≤4 candidates on half the sessions,
   all six arms collapse toward "0.12 × n" portfolios; differentiation only exists
   on the 40 sessions with ≥8 names and via the E* scalers.
8. **dw_max / turnover families not enforced in-arm**: loader-default snapshot
   families (±0.10/session per name, 1.0 L1) were left as counters (41–82 dw_max
   ticks per arm), not projections — the task's arm definitions don't include a
   slippage cap, and enforcing it would have contaminated the deployment question.
   The harness's own promotion gate would reject all arms on this; irrelevant here
   (exploratory).
9. **Sector map is today's snapshot** (156 tickers) applied to 2024–2026 history
   (documented Step-4h Option-2 approximation); ~30 sector-cap breach projections
   for ew_full, fading to 2 for voltarget_ew_12.
10. BULL_CALM is 86% of tuning bars; BEAR/CHOPPY/BULL_VOLATILE are undersampled
    (2/5/14) — regime-conditional conclusions are not supportable from this subset.

## Files

- Evidence JSON (all series, side channels, HAC, DSR/PBO, regimes):
  `deploy_policy_results/evidence_tuning_fwd1d.json`
- Freeze record: `deploy_policy_results/d6_freeze_20260709.json` (copy of
  `../d6_freeze_20260709.json`; `--verify` OK post-run)
- Sector map snapshot: `deploy_policy_results/sector_map_snapshot.json`
- Driver (registers the 6 arms, runs replay_all + reductions):
  `deploy_policy_results/run_deploy_policy_arms.py`
- DB byte-copy: `../sim_runs.db` (sha256 82084a6d026a…)
