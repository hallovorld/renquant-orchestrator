# D6: Preregistered replay protocol — Deployment Governor evaluation

STATUS: preregistration (companion to the Deployment Governor RFC, same PR)
DATE: 2026-07-09
DISCIPLINE: every rule, arm, estimand, and tolerance below is FROZEN at protocol
sign-off (PR merge), BEFORE any evaluation arm is run or inspected. Changes after
sign-off void the run and require a new protocol version.

## 1. Data and session freeze rule

- **Source**: the WF-cut loader used by `run_ab_replay.py` (renquant-pipeline
  `portfolio_qp/`), which refuses synthetic placeholder bars by construction.
- **Freeze rule** (mechanical, no discretion): all WF manifold cuts available at
  sign-off, EXCLUDING any session in the hypothesis-generation window
  **2026-06-23 → 2026-07-09** and excluding any session individually inspected in
  the evidence memo (#442). The concrete cut list (exact session IDs), manifest SHA,
  data cutoff date, and as-of feature/model artifact timestamps are committed in the
  S0 results PR header BEFORE arms run.
- **Nested selection** (r1 point 3): ALL Governor hyperparameters — regime `E_ceil`
  values, hysteresis band width, top-k, shrinkage `s`, Kelly fraction `λ` — are
  chosen on a TUNING subset of sessions disjoint from the evaluation subset. Both
  subset ID lists are frozen in the same commit. The evaluation subset is never used
  to choose any parameter; a parameter change after seeing evaluation results
  requires a new protocol version and a fresh evaluation subset. The mechanical
  construction of the tuning/evaluation split (contiguous blocks, embargo, exact
  assignment rule) is specified in §2's Evaluation scheme, Phase 2.
- **Live confirmation set**: S1 shadow sessions are future-only by construction.

## 1.1 Cost, tax, and fill conventions (frozen)

- Linear transaction cost: 5 bps per side on every traded dollar, both directions.
- Tax drag: realized-gain tax at configured rates (short 50% / long 32%) charged on
  every exit leg's realized PnL, via the existing `tax_drag()` convention.
- Whole-share quantization applied in all arms' execution layer (no fractional
  assumption anywhere in the replay).
- Fill convention: full fill at the session close price (replay convention; the
  S1 live shadow measures real-world deviation from this assumption).

## 1.2 Statistical contract (frozen)

- Paired daily returns per arm-pair; inference on the paired series with
  HAC/Newey-West standard errors (forward-return overlap at the 60d horizon makes
  iid inference invalid).
- Promotion bar per comparison: paired mean advantage point estimate ≥ +1 bp/day
  AND HAC 95% CI excluding 0 AND DSR ≥ 0.95 AND PBO ≤ 0.10 (the harness's existing
  significance pass).
- Marginal-capital estimand: same bar (CI excluding 0) on the paired difference
  series defined in §3.
- "Governor ≥ baseline" without meeting this bar is NOT enable-grade evidence.

## 2. Arms

**Phase 1 (runs immediately — no new code required):** the registered baseline
allocators: `equal_weight_top_k`, `inverse_vol_top_k`, `fractional_kelly_top_k`,
`hybrid_option_f_allocator`, `hard_only_qp_allocator`, `current_qp` (reference),
`stage_a_a2_long_only`.
Purpose: establish the naive-diversification floor ordering (DeMiguel 2009) and
confirm/refute the prior clean-signal finding that α-tilt dominates current_qp.

**Phase 2 (after D2 lands + this protocol is finalized; treatment family LOCKED
here per the #447 review, before any evaluation run):**
- **L1 candidate**: regime-ceiling-riding E* (fail-closed + hysteresis retained);
  `governor_kelly` (Σ shrunk-Kelly E*) and `voltarget` (σ_target/σ̂_pf) demoted
  to comparison arms — the #447 tuning result showed both are second-order to
  the breadth×cap ceiling, but that finding is exploratory and all three run in
  the confirmatory evaluation.
- **Breadth×cap grid (amended after the cap-grid exploratory run,
  doc/research/evidence/cap_grid_tuning/)**: per-name cap {12%, 20%} × weights
  {equal_weight, capped-Kelly}, deployment = regime-ceiling. Cap 25% is DROPPED
  from the confirmatory family: on the tuning subset it bought +18pp deployment
  at −8.2% net return (vs +4.7% at cap 12), doubled the single-name loss tail
  (p5 −0.97% → −1.98% of PV), and deepened MDD — dominated on every axis except
  raw deployment; carrying it into eval would spend a multiplicity budget on a
  dominated arm.
- **Veto-floor arms MOVE to a shadow A/B protocol** (design flaw in the r3 grid,
  found by the same run): replay bars contain only post-admission survivors
  (median breadth 4) — pre-veto candidates are not in the sim DB, so a veto
  {1.0σ, 0.5σ} arm CANNOT be replayed with existing data. Admission-breadth
  treatments run in the live SHADOW pipeline (which executes the full funnel
  incl. veto). Breadth is the PRIMARY remaining lever per the identity
  `deployable ≤ breadth × cap` and the cap result above.
  **The dedicated protocol (r4 review) is `renquant-strategy-104#52`**
  (`doc/design/2026-07-10-admission-breadth-shadow-ab.md`, frozen at merge):
  configurations (`buy_floor_std_mult` 1.0σ prod vs 0.5σ shadow, both keys
  moving together), exposure estimand (P1: end-of-chain deployed fraction,
  with a marginal-entrant vs floor-incumbent decomposition), return estimand
  (P2: 20d/60d SPY-relative forward returns on the marginal-entrant set,
  HAC-inferred, explicit REJECT bar; P3: production-XGB counterfactual so the
  PatchTST-shadow instrument alone cannot justify enablement), safety stop
  rules (§6: 12% cap / 35% sector / turnover ≤2× / MDD ≤0.30, immediate stop
  on breach per the live-shadow venue in D6 §5), comparison window (≥10
  future-only sessions, one declared +10 extension), and promotion rule (§9:
  RECOMMEND-ENABLE iff P1 lift is floor-attributable AND P2 passes on both
  the shadow instrument and the P3 counterfactual AND every §6 gate is green;
  live enablement is a separate gated PR, never bundled with the verdict).
  **One open gap** (not yet in #52, flagged for a follow-up to that PR, not
  fixed here since #52 is a different repo's PR): no run-bundle fingerprint
  (config hash + code commit + model-artifact hash) is stamped per shadow
  session. This project has hit exactly this failure mode before (shadow
  `panel_scorer_config_mismatch` silently fail-closing to "no trade" on
  config drift) — without a stamped fingerprint, a silent config drift
  mid-run could contaminate the ≥10-session comparison window without being
  detected. Until that gap closes, the verdict memo must manually confirm
  each session's shadow config hash matches the frozen treatment before
  counting it.
- **Fractional-shares dependency quantified**: integer flooring shaves 3.1-4.1pp
  of deployment at $10.7k PV in every arm; P(E_exec ≥ 0.90) is stuck at 10-12%
  regardless of cap — reaching ~90% living deployment requires breadth ≥ 5-8
  PLUS fractional execution (S-FRAC v2 stage-3) or larger PV. Cross-references
  the D7 memo (#444).
- **Controls**: cash/parking-sleeve arm (idle capital at T-bill yield).
- **Evaluation scheme — deterministic contiguous fold construction** (r4 review:
  the exploratory grid's non-contiguous 30%-random-hash session sampling forced
  an off-universe liquidation on 140-141/149 sessions every arm, per
  `cap_grid_tuning/results.md` limitation #6 — normal multi-session holding
  continuity never existed in that sample. Contiguous blocks fix this by
  construction: within a block, positions carry over session-to-session like a
  real book):
  - **Block construction (mechanical, no discretion)**: take the full frozen
    WF-cut session range from §1 (all available cuts, excluding the
    2026-06-23 → 2026-07-09 hypothesis window and the individually-inspected
    #442 sessions), ordered chronologically, and partition it into contiguous
    blocks of 60 trading days each (long enough to contain a full 60d
    forward-return cycle plus buffer; the final partial block, if any, is
    dropped rather than padded).
  - **Train/eval assignment (walk-forward, no discretion)**: the earliest
    ⌈N/2⌉ blocks (chronologically) are the TUNING subset — used ONLY for the
    §1 nested-selection hyperparameter choices (`E_ceil` table, hysteresis
    band, top-k, shrinkage `s`, Kelly fraction `λ`). A 30-trading-day embargo
    gap follows (consistent with this project's existing WF-gate embargo
    convention on 60d-horizon labels). The remaining blocks (chronologically
    after the embargo) are the EVALUATION subset — used ONLY for §3
    estimands, §4 gates, and the §5 decision rule. Neither subset is ever
    used for the other's purpose; a parameter change after inspecting any
    evaluation-subset result voids the run (§1's existing nested-selection
    rule applies unchanged to this fold structure).
  - **Fold aggregation and HAC treatment** (r4 review): forward-return overlap
    creates autocorrelation WITHIN a contiguous block (up to the 60d horizon
    length) but NOT across blocks (blocks are chronologically separated by
    construction, and the embargo additionally separates tuning from
    evaluation). Per-arm-pair inference therefore: (i) computes HAC/Newey-West
    standard errors (§1.2's existing lag convention, matching
    `compute_significance_verdicts`) SEPARATELY on each evaluation block's own
    paired daily-return series; (ii) combines the per-block point estimates
    via inverse-variance-weighted (fixed-effect) pooling into one overall
    paired-mean-advantage estimate and CI. This models the real
    within-block autocorrelation without falsely assuming autocorrelation
    across block boundaries where none exists.
  - Concretely with ~497 total frozen sessions (the #442/cap-grid freeze
    record's scale) and 60-day blocks: roughly 8 blocks total, ~4 tuning / ~4
    evaluation after the embargo — the exact count is whatever the frozen
    session list and this mechanical rule produce; it is not hand-picked.
- **Additional gates** (r4 review — formulas and thresholds, not just names):
  - **Concentration-event gate**: per-session worst-single-name loss
    contribution, `min over held names of (w_i × r_i)`, at the p5 percentile
    across the evaluation window. Tolerance: `p5 ≥ -(cap_i × 0.20)`, i.e. the
    arm's OWN configured cap times an assumed ≤20% adverse single-name move —
    the same adverse-move assumption already used for the D7 fractional-shares
    machine-death bound (#444), reused here for cross-RFC consistency rather
    than a freshly invented number. At cap=12%: -2.4%; at cap=20%: -4.0%. (The
    cap-grid exploratory p5 values — cap12 -0.97%/-0.92%, cap20 -1.61%/-1.36%
    — sit inside these tolerances, but that run is tuning-subset/exploratory
    and does NOT freeze or validate the threshold; the threshold is frozen
    independently, before the confirmatory run, per protocol discipline.)
  - **Turnover-tax gate**: `(total realized tax + total transaction cost) /
    max(total gross return, ε)`, computed once over the FULL evaluation
    window per arm (not per-session — per-session gross return can be near
    zero, making a per-session ratio unstable). Tolerance: ≤ 0.50 (frictions
    may not consume more than half of gross edge). This is a stated OPERATOR
    JUDGMENT default, not an empirical derivation: the cap-grid exploratory
    window's own tax/cost ratio was contaminated by forced off-universe
    liquidations (140-141/149 sessions, cap_grid_tuning/results.md limitation
    #6) — an artifact of that grid's non-contiguous random-hash session
    sampling, which the contiguous-fold evaluation scheme below is
    specifically designed to eliminate. A clean empirical baseline is not yet
    available; 0.50 is frozen now per protocol discipline and is not to be
    adjusted after seeing evaluation-fold results.
  - Both gates apply the SAME stop-rule split as §4/§5 below: recorded-but-
    completes in historical replay, immediate-stop in live shadow/canary.
- **Arm-specific single-name concentration contract** (r4 review — resolves
  the apparent contradiction between "12% cap is a frozen gate" and "20% cap
  is an evaluation arm"): the per-name-cap non-degradation gate is NOT a flat
  12% tolerance — each cap-family arm's allocator enforces its OWN configured
  cap by construction (L2 §2.2 is a down-only operator; no weight can ever
  exceed the cap it was built with), so "max single-name weight ≤ 12%" as a
  universal promotion gate would make the cap20 arm fail by definition before
  any statistical comparison runs, which is not the intent — the grid exists
  to COMPARE cap values, not to pre-reject all but one. The corrected
  contract: (i) each arm's single-name-weight gate tolerance equals ITS OWN
  declared cap (a construction invariant / regression check, not a
  discriminating statistical tolerance); (ii) the 12% figure remains the
  OPERATOR POLICY ceiling — a SEPARATE, governance-level gate — meaning any
  cap-family arm configured above 12% is evaluated on statistical merit
  alongside the others but CANNOT itself reach ENABLE without the recorded
  operator sign-off already required below; a cap12 arm can reach ENABLE
  through the standard §5 decision rule alone. This makes explicit what was
  previously implicit in the single "any cap >12% requires sign-off" bullet.
- Any cap value above 12% reaching ENABLE additionally requires recorded
  operator sign-off (capital-risk change), after this confirmatory evidence.

## 3. Estimands

**Primary:**
1. End-of-chain deployed fraction (mean and per-session distribution).
2. Paired daily portfolio returns vs each baseline arm, significance via the
   existing DSR / PBO pass (`compute_significance_verdicts`) — promotion-grade
   requires positive paired mean with DSR ≥ 0.95 and PBO ≤ 0.10 (the harness's
   existing promotion bar).

**Decomposed design (r2 point 2 accepted — the L1 deployment question and the L2
allocator question are separate, answered by separate paired comparisons):**

- **(a) L1 — does Governor-selected E* beat incumbent deployment?** SAME allocator
  on both sides, and that allocator is PREREGISTERED HERE as `equal_weight_top_k`
  (r3 review accepted — choosing (b)'s winner on the evaluation subset would make
  (a) post-selection; equal-weight is fixed a priori as the DeMiguel-floor
  default, independent of any evaluation outcome):
  `equal_weight@E*_governor` vs `equal_weight@E*_incumbent`, where incumbent E*
  is the session's realized live deployment from run bundles.
- **(b) L2 — which allocator, at MATCHED exposure?** All allocator variants run at
  the SAME session E*; allocator skill judged independent of deployment level.
- **(c) Combined system vs incumbent**: `governor + chosen allocator` end-to-end vs
  incumbent greedy+Kelly+multipliers. The enable decision references (c), with
  (a)/(b) as its decomposition — if (c) wins but (a) is flat, the win is
  allocator-only and the Governor layer must not claim it, and vice versa.

**Quality of marginal capital** (Codex requirement from #442): the EXTRA exposure
in (a) must itself earn ≥ 0 net forward return — computed as the paired return
difference between (a)'s two registered arms. This is exactly reproducible (same
allocator, same sessions, only E* differs); no separately-constructed synthetic
portfolio exists. More invested but worse risk-adjusted = REJECT.

**Risk-normalization rule**: raising deployment mechanically raises portfolio
volatility; that risk appetite is the operator's granted mandate, NOT an estimand.
(b) isolates allocator skill at matched E*; (a) isolates the deployment decision;
the §4 gates bound the risk of both.

## 4. Non-degradation gates (tolerances frozen now)

| Gate | Tolerance | Rationale |
|---|---|---|
| Max single-name weight (construction invariant) | ≤ the arm's OWN configured cap (12% or 20% per §2 Phase-2 cap grid) | mechanical allocator invariant, not a discriminating statistical tolerance — see the arm-specific contract in §2 |
| Max single-name weight (operator policy ceiling) | ≤ 12% to reach ENABLE without extra sign-off; >12% requires the recorded operator sign-off (§2, capital-risk change) | existing operator sizing mandate — a governance gate, separate from the construction invariant above |
| Max sector weight | ≤ 35% | existing regime cap |
| Session turnover | ≤ 2× the equal-weight arm's | churn control without a shared L1 cap |
| Max drawdown (replay window) | ≤ regime `drawdown_halt_pct` (0.35) with ≥ 5pp headroom (i.e. ≤ 0.30) | never design to the halt line |
| Concentration-event (per-session worst single-name loss) | p5 across the window ≥ -(arm's cap × 0.20) | reuses the D7 (#444) ≤20%-adverse-move assumption for cross-RFC consistency; formula in §2 |
| Turnover-tax ratio | (total tax + total cost) / max(total gross return, ε) ≤ 0.50, computed over the full window per arm | frictions must not consume the majority of gross edge; frozen operator-judgment default, formula/rationale in §2 |
| Fail-closed behavior | Governor emits no target on stale/mismatched model in 100% of injected-failure cases | RFC §2.1 semantics |

## 5. Decision rules

ENABLE the Governor (proceed S1 → S2) iff ALL of:
- Governor arm beats `equal_weight_top_k` and `inverse_vol_top_k` on paired returns
  at the DSR/PBO bar (if it cannot beat naive diversification, ship equal-weight
  under the same E* governor — the L1 layer can still be right when the L2 answer
  is "naive");
- marginal-capital estimand ≥ 0;
- every gate in §4 passes;
- no single session violates the arm's own configured concentration cap;
- if the winning arm's cap is >12%, the recorded operator sign-off (§2, capital-
  risk change) is in hand before S1 → S2 proceeds — a cap>12% arm can win the
  statistical comparison and still not enable without it.

REJECT / REDESIGN iff any gate breaches, or the marginal-capital estimand is
negative (deploying more of this signal destroys value — then the cash-drag answer
is "the signal doesn't support more deployment", and the honest next move is the
parking sleeve (RS-1) for idle cash, not forced equity exposure).

**Stop rule** (r2 point 2 accepted — split by venue):
- **Historical replay**: NO mid-window abort — aborting an arm on a
  drawdown/turnover breach censors returns asymmetrically. Every arm runs the FULL
  registered horizon; a gate breach is RECORDED and fails promotion, but the
  series completes.
- **Live shadow / canary (S1/S2)**: immediate stop on any gate breach — safety
  dominates statistical cleanliness once real or near-real capital is involved.

## 6. What this protocol does NOT authorize

- No live enablement: S2 canary and S3 enable each require their own recorded
  decision (S3 = behavior change → pre-registration gate + operator notification).
- No long-short: L4 has its own future protocol.
- No fractional shares: D7 memo → operator decision, independent of this.
