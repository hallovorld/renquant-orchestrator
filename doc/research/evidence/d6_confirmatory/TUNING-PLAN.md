# D6 confirmatory replay — freeze + declared tuning plan (committed BEFORE any arm runs)

Protocol (binding): `doc/design/2026-07-09-governor-prereg-replay-protocol.md`
at orchestrator `origin/main` (commit `1de64df9`, the merged FINAL text).
This file is committed together with `freeze_20260710.json` and pushed BEFORE
any tuning or evaluation arm is executed — the push timestamp is the prereg
proof. Everything below is declared now; nothing here is adjusted after seeing
arm output.

## 1. Freeze provenance

- Source DB: `/Users/renhao/git/github/RenQuant/data/sim_runs.db`
  (production; byte-copied READ-ONLY, never opened writable).
  - Production main-file sha256: `82084a6d026a1a8db39c92d19ee119f7f79c96e82a4dade91404d93848772a88`
    (byte-identical pristine copy retained: `sim_runs.pristine.db`).
  - Production `-wal` sidecar was EMPTY (0 bytes) at copy time, so the main
    file contains the complete content.
  - The working copy's journal header was normalized (`PRAGMA
    journal_mode=DELETE`, a header-only change required because a plain
    `mode=ro` open of a WAL-header DB without its `-shm` fails) →
    working-copy sha256 `72b25fdbd3f246fa5fbefb679349d7e7bd6206d511090bef37602e1b8498827d`
    (the sha stamped in the freeze record).
  - Logical-content identity PROVEN: full `iterdump` sha256 of pristine
    (immutable ro) vs working copy both =
    `f342eebd095680742f13859840e07dee9a5c7274d6d841ebc87ba5f2113ec8b9`;
    `PRAGMA integrity_check` = ok.
- Freeze tool: merged `scripts/d6_freeze_record.py` v2.0.0 (orchestrator main).
  NOTE: v2 has NO `--seed` — the merged protocol froze a DETERMINISTIC
  chronological split (earliest ⌈N/2⌉ = tuning, 60-trading-day purged embargo,
  remainder = evaluation), replacing the retired seeded-hash draft. The only
  frozen stochastic seeds in this run are the §1.2 stationary-bootstrap seed 0
  and the harness `pbo_rng_seed=0`.
- Exclusions applied: hypothesis-generation window `2026-06-23:2026-07-09`
  (endpoints inclusive; tool default = protocol value). #442-inspected
  sessions: every session date named in
  `doc/research/2026-07-09-cash-drag-binding-constraints-update.md` falls
  INSIDE that window (checked mechanically: all YYYY-MM-DD / MM-DD mentions
  are 2026-06-23..2026-07-09), so no additional `--exclude-session` args are
  required.
- Result: union 497 sessions → tuning 249 (2024-01-02..2025-01-08),
  embargo 60, evaluation 188 (2025-05-08..2026-03-27 @ fwd_1d; 174 @ fwd_60d).
  20d non-overlapping outcome blocks in evaluation: floor(188/20) = 9
  (≥ 8 minimum). 60d blocks: 3 → DESCRIPTIVE-ONLY per §1.2 (frozen).
- Harness: renquant-pipeline `origin/main` commit `3e68737` (post-#182
  L3_FULL fidelity engine, #183/#184 merged), fresh detached worktree; harness
  code untouched. Runner scripts live in this evidence dir and register custom
  arms via the established `register_allocator` pattern (cap-grid precedent).
- Sector map: PINNED strategy-104 config (umbrella `subrepos.lock.json` pin
  `0e5d9891`, `configs/strategy_config.json`): 159-ticker `sector_map`,
  `max_positions_per_sector` 6. NOT the (stale) umbrella-tree copy.
- Conventions (all arms): `stateful + tax + integer_shares + enforce_caps`
  (L3_FULL), 5 bps/side, tax 50%/32% @365d, whole shares, fill at close,
  initial capital $10,700, sector cap 0.35, fwd_1d bars (daily unit).

## 2. Declared tuning procedure (TUNING subset ONLY — 249 sessions)

Nested-selection list (§1): regime `E_ceil` values, hysteresis band width,
top-k, shrinkage `s`, Kelly fraction `λ`. Anchors = the D5 `deployment_governor`
config block (pinned strategy-104, values explicitly "PLACEHOLDERS pending
nested-selection tuning"): E_ceil {BC 0.95, BV 0.70, CH 0.60, BEAR 0.35},
band 0.05, k 8, s 0.0, λ 0.3, max_step 0.15.

Grids (declared now):
- E_ceil profiles (BULL_CALM/BULL_VOLATILE/CHOPPY/BEAR), all ≤ 0.95 gross
  budget: P_flat95 = .95/.95/.95/.95; P_D5 = .95/.70/.60/.35;
  P_mid = .95/.80/.60/.30; P_derisk = .90/.70/.45/.20; P_cons = .80/.60/.40/.10.
- hysteresis band ∈ {0.02, 0.05, 0.10}; top-k ∈ {4, 6, 8};
  s ∈ {0.0, 0.1, 0.2}; λ ∈ {0.3, 0.5}; σ_target (voltarget arm, annualized)
  ∈ {0.12, 0.15, 0.18}. max_step_per_session FIXED at the declared 0.15 (not
  in the §1 nested list). σ (fwd_60d-horizon) annualized by √(252/60).
- Staged search (declared): (i) rider arm E*_ceil: E_ceil × band × k (45
  configs) at s=0, λ=0.3 L2 weights; (ii) governor_kelly: s × λ (6) at the
  rider-chosen E_ceil/band/k; (iii) voltarget: σ_target (3) at the same.
- Selection criterion (declared): maximize net annualized Sharpe on the tuning
  subset, subject to tuning-window sanity gates MDD ≤ 0.30 and
  turnover-tax ratio ≤ 0.50; ties → higher total net return, then lower
  turnover. Chosen values + full tuning table are recorded in the results doc.
- Regime label missing on a bar → the governor arms FAIL CLOSED for that
  session (target = carry current book, no reallocation), counted and
  reported.

## 3. Locked evaluation family (EVALUATION subset, ONE pass — no re-runs)

Phase-1 baselines (registry, per-name cap 0.12): `current_qp` (reference),
`equal_weight_top_k`, `inverse_vol_top_k`, `fractional_kelly_top_k`,
`hybrid_option_f_allocator`, `hard_only_qp_allocator`, `stage_a_a2_long_only`.

Phase-2 (locked §2 family, tuned values from §2 above):
- `gov_ceiling_ck` — PRIMARY L1 (E* = E_ceil(regime), hysteresis + max_step,
  fail-closed), L2 = down-only capped-Kelly, cap 0.12.
- `gov_kelly_ck` — comparison (E* = min(E_raw, E_ceil)).
- `gov_voltarget_ck` — comparison (E* = min(σ_target/σ̂_pf, E_ceil)).
- Breadth×cap grid at pure regime-ceiling deployment (no hysteresis, mirrors
  the exploratory grid): `cap12_ew_ceil`, `cap12_ck_ceil`, `cap20_ew_ceil`,
  `cap20_ck_ceil` (cap 25 DROPPED per the merged amendment).
- Controls: `cash_park` (zero-equity; net 0%/day per the project's existing
  SGOV `cost_no_carry` convention, with a DESCRIPTIVE 4.0%-annual T-bill carry
  overlay reported in analysis only), and `ew_at_incumbent_estar`
  (equal-weight scaled to the session's realized incumbent deployment
  `1 − cash/PV` from the sim run bundles, `pipeline_runs`, last run per date).
- `ew_at_gov_estar` — equal-weight at the PRIMARY governor's E* series
  (estimand (a)'s preregistered equal_weight comparator arm).

Veto-floor arms are NOT run here (moved to the §2a live shadow A/B — not
replayable from post-admission sim bars; frozen protocol amendment).

## 4. Declared analysis (per §1.2 / §3 / §4 / §5)

- Unit (i): daily paired net returns over the 188-session evaluation range;
  NW lag = min(floor(4·(T/100)^(2/9)), 10); promotion bar = mean ≥ +1 bp/day
  AND HAC 95% CI excludes 0 AND DSR ≥ 0.95 AND PBO ≤ 0.10. DSR/PBO across the
  full named family (n_trials = family size; `pbo_rng_seed=0`, CSCV 16
  slices); the cash control is excluded from the DSR/PBO candidate matrix
  (constant series is not a candidate strategy).
- Unit (ii): 20d non-overlapping blocks (9), per-arm block return =
  exp(Σ log(1+r_daily)) − 1; paired diffs; NW(lag 1)-on-blocks t-CI
  (df = N−1) AND stationary bootstrap (E[block len] = 2, 10,000 resamples,
  seed 0), one-sided α = 0.05, conjunction rule; ESS = N(1−ρ̂₁)/(1+ρ̂₁)
  (ρ̂₁ clipped ≥ 0); minima N_blocks ≥ 8 AND ESS ≥ 6. 60d (3 blocks):
  descriptive point estimates only, NO significance test.
- Decomposition: (a) `ew_at_gov_estar` vs `ew_at_incumbent_estar`;
  (b) allocator skill at matched exposure = within-cap-group grid pairs
  (identical E* by construction); (c) `gov_ceiling_ck` vs `current_qp`
  (reference), with (a)/(b) as the attribution. Marginal-capital estimand =
  (a)'s paired difference on unit (ii) blocks; requirement ≥ 0 (report also
  the −50 bps/20d-block non-inferiority margin test, labeled).
- §4 gates per arm, tolerances as frozen (own-cap construction invariant; 12%
  operator policy ceiling; sector ≤ 0.35; turnover ≤ 2× equal-weight arm;
  MDD ≤ 0.30; concentration-event p5 ≥ −(cap×0.20); turnover-tax ≤ 0.50;
  fail-closed injected test). Historical replay: breaches RECORDED, series
  completes (no mid-window abort).
- §5: replay evidence is directional/low-power support ONLY; the S1 live
  shadow bullet is unmet by construction, so the maximum verdict here is
  RANK/SCREEN support (or REJECT) — never ENABLE.
