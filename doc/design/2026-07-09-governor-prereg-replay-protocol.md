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
  **The dedicated protocol is §2a below** (revised from the r4 note in this
  section, which pointed at `renquant-strategy-104#52`
  (`doc/design/2026-07-10-admission-breadth-shadow-ab.md`) as the satisfying
  artifact — Codex's DIRECT review of that PR, posted after this section was
  first drafted, found the within-shadow marginal-entrant decomposition +
  prod-counterfactual design in #52 cannot actually identify the floor's
  causal effect once QP/sizing interactions change portfolio weights, and
  that the cross-repo protocol belongs in orchestrator, not bundled with a
  strategy-config PR. §2a is the corrected design. `strategy-104#52` is now
  DRAFT, held pending §2a's review, and will be resubmitted as a **config-only
  treatment PR** referencing §2a once §2a itself merges — it must not flip any
  shadow config before then.

### §2a. Breadth-lever admission A/B — true isolated design (supersedes #52's within-shadow decomposition)

**Problem with the superseded design**: a single shadow arm (PatchTST scorer,
Kelly 0.5/0.35, regime cap 0.15, one-share floor ON, `buy_floor_std_mult`=0.5)
compared against production (XGB, Kelly 0.3/0.12, cap 0.12, floor OFF, mult=1.0)
confounds the floor treatment with four other pre-existing deltas. A
within-shadow marginal-entrant decomposition (splitting shadow's own admitted
set into "would-pass-at-1.0σ" vs "marginal") plus a scores-only production
counterfactual cannot recover the true floor effect, because QP and Kelly
sizing are nonlinear in the admitted set — changing which names are admitted
changes every other name's weight too, so "hold everything constant except the
floor" is not actually achieved by decomposing one arm's output after the fact.

**Corrected design — two simultaneous isolated shadow arms, identical except
the floor:**

- **Arm S-0.5 (existing)**: `configs/strategy_config.shadow.json` as `#52`
  already defines it — PatchTST, Kelly 0.5/0.35, regime cap 0.15, one-share
  floor ON, `buy_floor_std_mult = 0.5`. Broker state: `alpaca_shadow`
  (existing, `live_state.alpaca_shadow.json` + `runs_alpaca_shadow.db`).
- **Arm S-1.0 (NEW)**: `configs/strategy_config.shadow_b.json` — a byte-for-byte
  clone of `shadow.json` with exactly ONE key different:
  `buy_floor_std_mult = 1.0` (and `buy_floor` left at `adaptive_mean_std`,
  matching S-0.5). Every other key (scorer, Kelly, regime cap, one-share
  floor, sector caps, slots) is IDENTICAL to S-0.5. This is the true control
  arm for the floor treatment: same environment, same session, only the
  floor differs.
- **Estimand (A) — floor effect (the causal claim, THIS protocol's decision
  rule)**: paired S-0.5 vs S-1.0, same session dates, same everything else.
  P1 (deployed fraction) and P2 (20d/60d forward-return quality of the
  marginal-entrant set, defined identically to #52 §4 P2) are both computed
  on this pair. Because both arms actually execute their admitted sets in
  real (isolated, simulated) broker state, **there is no hypothetical
  portfolio and no separate cost/tax model is needed for this estimand** —
  each arm's own fills carry the funnel's real simulated transaction cost and
  tax-drag mechanics automatically. This dissolves the "cost/tax accounting
  for the hypothetical entrant portfolio" problem in the superseded design:
  nothing here is hypothetical.
- **Estimand (B) — residual environment effect (a SEPARATE diagnostic
  estimand, NOT part of the ENABLE/REJECT decision for the floor)**: paired
  S-1.0 vs actual production, same session dates. S-1.0 matches production's
  floor (1.0σ) exactly, so this comparison isolates the effect of everything
  ELSE that differs between the shadow environment and production (scorer,
  Kelly, regime cap, one-share floor) — holding the floor fixed. This is a
  prerequisite DIAGNOSTIC before any future live-enablement PR can claim the
  floor conclusion generalizes from shadow to production (scorer-transfer
  risk, #52 §7 point 2); it is not evidence for or against the floor itself,
  and a bad reading here blocks *generalizing* the S-0.5-vs-S-1.0 result to
  production, not the shadow-only verdict.
- **Explicitly retired**: the #52 P3 "production-XGB counterfactual" estimand
  (computing the marginal-entrant set on logged production scores that were
  never actually traded) is superseded by estimand (B) above, which uses a
  REAL executed comparison arm instead of a computed counterfactual. Do not
  compute P3 in addition to (B) — it would answer a strictly weaker version
  of the same question with a hypothetical portfolio where a real one is
  available.

**Infrastructure this requires (NOT YET BUILT — a prerequisite for this
protocol to run, tracked as follow-up work, not implemented in this doc-only
PR):**
1. `renquant-pipeline` `state_paths.py` (and its `kernel/state_paths.py`
   duplicate — both copies, per this project's known duplication pattern):
   add `"alpaca_shadow_b"` to `ALLOWED_BROKERS`.
2. Umbrella `live/broker_readonly.py`: `ReadOnlyBrokerWrapper.broker_name` is
   currently a HARDCODED class attribute (`"alpaca_shadow"`), not a
   constructor parameter — verified by direct inspection. Needs
   `__init__(self, underlying, broker_name="alpaca_shadow")` so a second
   instantiation can tag itself `"alpaca_shadow_b"` without touching the
   default (backward-compatible) behavior.
3. Umbrella `live/runner.py`: a new CLI surface to select the second shadow
   arm (e.g. a `--broker readonly-alpaca-b` choice, or a `--shadow-tag`
   flag) defaulting its config to `strategy_config.shadow_b.json` and
   constructing `ReadOnlyBrokerWrapper(real, broker_name="alpaca_shadow_b")`.
4. `daily_104.sh`: a third invocation (Step 5, alongside the existing Step 4
   shadow pass) running S-1.0. Non-fatal to the prod cycle, same as the
   existing shadow step.
5. `strategy-104`: add `configs/strategy_config.shadow_b.json` (the S-1.0
   config described above) and a config-drift pin test alongside the
   existing `strategy_config.shadow.json` pin, verifying prod/golden stay
   untouched and shadow_b differs from shadow ONLY in `buy_floor_std_mult`.
   This is the "config-only treatment PR" `strategy-104#52` will become,
   scoped strictly to items 5 (+ whatever of 1-4 lands in strategy-104's own
   repo boundary) — never bundled with protocol design, per Codex's
   sequencing objection.

**Statistical power (honest treatment — the superseded design's ≥10-session
HAC test on 20d/60d overlapping returns is NOT adequately powered; showing
the reasoning rather than asserting a fix):**

For a daily paired series with an `h`-day-ahead overlapping return horizon,
consecutive observations share `h-1` days of the same forward window, so the
number of *effectively independent* blocks is roughly `N_eff ≈ N / h` (the
standard heuristic for non-overlapping-block decomposition of
serially-overlapping return series). HAC/Newey-West standard errors correct
the *bias* from this overlap but do not manufacture power the data doesn't
contain: with too few effective blocks, the corrected SE is itself unstable.
Common econometric guidance treats fewer than ~5-10 effective blocks as
unreliable for cluster/HAC-robust inference.

- At `N=10` sessions and `h=20`: `N_eff ≈ 0.5`. At `h=60`: `N_eff ≈ 0.17`.
  Both are far below the reliability floor — the superseded design's
  ≥10-session HAC test was not analyzing noise correctly; it was analyzing a
  sample too small for the standard error itself to be trustworthy at all.
- Reaching even a conservative `N_eff = 8` (the low end of the "unreliable
  below" guidance, not a fully-powered target) requires `N ≈ 8h` sessions:
  **~160 sessions (~8 months) for the 20d estimand, ~480 sessions (~2 years)
  for the 60d estimand.** A fully-powered target (`N_eff ≈ 30`) would need
  ~600 and ~1800 sessions respectively — multi-year, impractical for a
  shadow gate meant to unblock a breadth-bound deployment problem now.

**Resolution — two-tier reporting, not a single fixed-N verdict:**
- **Tier 1 — early operational read, `N ≥ 10` sessions (unchanged trigger
  from #52 §5)**: report P1/P2 as DIRECTIONAL POINT ESTIMATES ONLY, explicitly
  labeled "underpowered, not significance-tested" — no HAC CI is computed or
  reported at this tier because at `N_eff < 1` a computed CI would be
  false precision, not honest uncertainty. Used only for a coarse kill
  check: if the point estimate is grossly adverse (e.g. marginal-entrant mean
  return sharply negative net of cost, or any §6 gate breach), REJECT early
  rather than waiting out a multi-month confirmatory window for a treatment
  that is already failing directionally. A favorable or neutral Tier-1 read
  does NOT authorize ENABLE — it authorizes continuing to Tier 2.
- **Tier 2 — confirmatory read, matured-observation-gated (replaces the fixed
  "+10 extension" rule)**: continue running both arms until `N_eff ≥ 8` matured
  observations accumulate per estimand (a matured observation is one whose
  full `h`-day forward-return window has elapsed) — concretely, ~160 sessions
  for the 20d estimand and ~480 for the 60d estimand, per the arithmetic
  above. At that point compute the preregistered HAC significance test (#52
  §4 P2's bar: marginal-entrant mean ≥ 0 net of cost AND not significantly
  below the incumbent set) for real. This is the earliest point at which a
  RECOMMEND-ENABLE or REJECT verdict may be issued; a verdict issued before
  Tier 2's matured-N gate is not decision-grade regardless of what the point
  estimate shows.
- **Non-inferiority margin (predeclared, Tier 2)**: the marginal-entrant set's
  mean forward return must not be more than 50 bps/period below the
  incumbent set's mean (one-sided non-inferiority margin, chosen as roughly
  the round-trip transaction-cost convention doubled — a conservative
  buffer against a treatment that is merely "not better" being mistaken for
  "materially worse"), in addition to the existing ≥0-net-of-cost bar. This
  gives the test a concrete margin rather than testing a point null the
  data can't resolve at any reachable N.
- Given the 20d estimand matures ~3× faster than 60d, Tier 2 MAY report the
  20d verdict first (at ~160 sessions) while continuing to accumulate toward
  the 60d gate (~480 sessions) — the two horizons are not required to mature
  together, and the 20d-only interim verdict is explicitly labeled as
  covering only the shorter horizon.

**Run-bundle fingerprint (closes the gap flagged in the prior draft of this
section)**: each shadow session for BOTH arms stamps: (i) a config hash —
sha256 of the resolved `strategy_config.shadow.json` /
`strategy_config.shadow_b.json` content; (ii) a model-artifact hash — reusing
the project's existing unified `model_content_sha256` /
`model_content_sha256_from_path` convention
(`renquant_pipeline.kernel.panel_pipeline.fingerprint_dispatch`), not a
bespoke scheme; (iii) the broker-state identity tag (`alpaca_shadow` /
`alpaca_shadow_b`); (iv) the code commit SHA of `renquant-strategy-104` and
`renquant-pipeline` at run time. A session whose stamped fingerprint doesn't
match the frozen treatment's expected values is excluded from both Tier 1 and
Tier 2 counts, not silently included — reusing this project's own
`panel_scorer_config_mismatch` fail-closed convention rather than treating a
config-drifted session as a valid observation.

**Decision rule (supersedes #52 §9 for the floor-effect claim; #52 §9's
overall structure — verdict-as-memo, live enablement as a separate gated PR,
single-config-revert rollback — is unchanged and reused as-is):**
RECOMMEND-ENABLE iff, at Tier 2 maturity: estimand (A)'s P1 shows a deployed-
fraction lift AND P2 passes the ≥0-net-of-cost + non-inferiority bar on the
20d horizon (60d if matured) AND every #52 §6 gate is green on both arms AND
run-bundle fingerprints are clean for every counted session. Estimand (B) is
reported alongside as a scorer-transfer-risk diagnostic but is NOT a gating
condition for this verdict — it gates whether a SEPARATE future live-
enablement PR may cite this shadow evidence as externally valid for
production, which is that future PR's decision to make, not this protocol's.
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
