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
  construction of the tuning/evaluation split (two contiguous ranges, embargo,
  exact assignment rule) is specified in §2's Evaluation scheme, Phase 2.
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

- **Two distinct quantities, two distinct inference units — do not conflate them:**
  - **(i) Realized daily paired portfolio returns** (e.g. Governor arm's daily P&L
    minus baseline arm's daily P&L, same session, same everything else): each
    day's value is NOT a forward-looking label — it's what actually happened that
    day. Ordinary daily-lag HAC/Newey-West (short lag: the standard Newey-West
    1994 plug-in rule `lag = floor(4*(T/100)^(2/9))`, CAPPED at lag 10 — both
    the rule and the cap frozen here) is
    valid here — there is no forward-window overlap to correct for beyond normal
    short-range serial correlation. This is the unit for the §3(a)/(b)/(c) L1/L2
    allocator promotion-bar comparisons and the marginal-capital estimand.
  - **(ii) h-day BLOCK-aggregated return endpoints** (both kinds used in this
    protocol: compounded REALIZED ledger returns over an h-day block — §2a's
    primary P2 endpoint — and h-day FORWARD returns of an entry cohort —
    §2a's P2d diagnostic and the §3 marginal-capital estimand): a rolling
    daily series of h-day-forward returns has each consecutive pair of
    observations sharing `h-1` days of the same forward window —
    HAC/Newey-West on the raw daily series does NOT fix this (r5 review,
    correcting the r4 fix): with h=60 and any calendar-block scheme shorter
    than several times h, a block's forward window spans past its own
    boundary into the next block's data, and within a block of n≈60 daily
    observations there is only ~1 independent 60d-forward outcome anyway —
    HAC corrects small-sample bias, it does not manufacture information the
    overlapping series doesn't contain.
    **Corrected unit — non-overlapping OUTCOME blocks**: partition the
    eligible session range into consecutive, NON-OVERLAPPING windows of
    exactly `h` trading days each; each window contributes exactly ONE
    outcome observation (the block-aggregated return realized inside it).
    Consecutive blocks share zero calendar days, which removes the
    MECHANICAL forward-window overlap. **This does NOT make the blocks
    independent (r6 correction — the r5 "genuinely independent by
    construction" claim is WITHDRAWN): financial regime persistence induces
    serial dependence across adjacent blocks, violating both t-test
    independence and permutation exchangeability.** `N_blocks` = the actual
    count of complete non-overlapping `h`-day blocks in the eligible range.
    **Frozen dependence-robust inference for unit (ii) — complete hypothesis
    test (r7 point 2: alpha, statistic, compounding, and bootstrap spec were
    underspecified; frozen exactly here, no discretion left to a future
    implementation PR):**
    - **Alpha**: `α = 0.05`, ONE-SIDED (the non-inferiority framing is
      inherently directional — "not worse than the margin" — so a one-sided
      test is the correct, not merely convenient, choice). This matches the
      project's existing significance convention: `DSR ≥ 0.95` is documented
      as "selection-bias-corrected significance at 5%"
      (`renquant_pipeline/kernel/portfolio_qp/replay_significance.py:36`) —
      §1.2 freezes the SAME 5% level for consistency across this protocol's
      statistical gates, not a fresh number.
    - **Test statistic**: the sample mean of the paired block-difference
      series `d_1, ..., d_N` where each `d_i` = (S-0.5's compounded block
      return − S-1.0's compounded block return) for non-overlapping block
      `i`. **Compounding convention**: each arm's within-block return is
      GEOMETRIC compounding of daily net log-returns
      (`r_block = exp(Σ log(1 + r_daily)) − 1`), not an arithmetic sum of
      simple daily returns — geometric compounding is exact for multi-day
      holding-period returns (arithmetic summation over-states a multi-day
      return by a second-order term that grows with both the horizon and
      the daily return's magnitude) and is standard practice for this
      project's other multi-day estimands (the §3 marginal-capital
      estimand's forward-return convention).
    - **(1) PRIMARY** — mean of `d_i` with a Newey-West (lag 1) standard
      error computed ON THE BLOCK SERIES, small-sample-corrected via the
      t-distribution with `N_blocks − 1` degrees of freedom; ENABLE requires
      the resulting one-sided 95% CI to exclude the non-inferiority margin
      (below).
    - **(2) predeclared robustness check** — a stationary block bootstrap on
      the `d_i` series: expected block length 2 (of the `d_i` series itself,
      preserving inter-block dependence at the lag the NW correction already
      targets), **10,000 resamples, fixed seed 0** (reusing this project's
      existing `pbo_rng_seed=0` default convention,
      `replay_significance.py:58`, for the same reason — reproducibility via
      a named, non-arbitrary constant rather than a fresh one), one-sided
      95th-percentile CI.
    - **Conjunction rule (frozen)**: ENABLE requires BOTH (1) AND (2) to
      exclude the margin at their respective one-sided `α = 0.05` bound. **If
      they disagree** (one excludes the margin, the other does not): the
      verdict is NOT enable-grade — report BOTH point estimates and CIs in
      the memo explicitly labeled **DISAGREEMENT**, treat as REJECT/
      inconclusive (never resolved by picking whichever method supports
      ENABLE). This is the conservative conjunction, stated as an executable
      rule rather than left to a future reviewer's judgment call.
    - **(3) Effective-sample-size criterion (frozen)**: `ESS = N_blocks ×
      (1 − ρ̂₁)/(1 + ρ̂₁)`, where `ρ̂₁` is the lag-1 sample autocorrelation of
      the block series (clipped below at 0); enable-grade additionally
      requires **`N_blocks ≥ 8` AND `ESS ≥ 6`** (r7 point 3 below adds a
      power-derived floor on top of this fixed minimum — see §2a's
      Statistical power section). This is the unit and method for §2a's P2
      endpoint and for any other h-day block-aggregated estimand in this
      protocol (superseding both the r4 per-block-NW/pooling scheme and the
      r5 plain-t-test claim).
- **Promotion bar, unit (i)**: paired mean advantage point estimate ≥ +1 bp/day
  AND (short-lag) HAC 95% CI excluding 0 AND DSR ≥ 0.95 AND PBO ≤ 0.10 (the
  harness's existing significance pass, `compute_significance_verdicts`).
- **Promotion bar, unit (ii)**: paired mean block-return advantage point estimate
  ≥ 0 (net) AND, ONLY once **`N_blocks ≥ 8` complete blocks AND `ESS ≥ 6`
  (the frozen enable-grade minima, everywhere in this protocol)**, the
  dependence-robust test above (NW-on-blocks small-sample CI AND stationary
  bootstrap, in conjunction) excluding values beyond the predeclared
  non-inferiority margin. Below those minima the outcome is
  **NO-ENABLE-BY-DEFAULT**: report the point estimate as directional-only —
  no CI, no DSR/PBO (a handful of dependent blocks cannot supply a stable
  variance estimate) — per §2a Tier 1, and continue accumulating under the
  predeclared extension rule of the relevant experiment (no peeking-based
  stop). **Enable-grade block-return claims are made at the 20d horizon
  ONLY: the 60d horizon is DESCRIPTIVE-ONLY everywhere in this protocol** —
  at every planned sample size (live shadow AND the frozen replay pool) it
  yields `N_blocks < 8`, so it is reported, never promotion-gating, and no
  60d significance test is computed.
- **Historical replay evidence is directional/low-power support ONLY (r6
  point 3)**: even where the frozen replay pool clears the `N_blocks`/`ESS`
  minima, historical 20d block evidence CANNOT by itself clear promotion —
  ENABLE additionally requires the LIVE shadow arm-level endpoint (§2a P2,
  future-only sessions) to meet its own bar under the same dependence-robust
  method. Replay ranks and screens; live shadow confirms.
- **DSR/PBO applicability**: DSR (mean/std of the realized return sample,
  deflated for the number of configurations actually tried) applies to BOTH
  units once N is adequate — for unit (i), N = trading days in the evaluation
  window; for unit (ii), N = `N_blocks` non-overlapping blocks (subject to
  the `ESS` criterion), and the DSR trials
  count is the number of arms/configurations actually compared in that Phase-2
  family (named per-family in §2/§2a, not a generic constant). **PBO does NOT
  apply to §2a's breadth-lever comparison**: PBO's combinatorially-symmetric
  cross-validation (CSCV) procedure needs many candidate strategies split across
  many train/test combinations to estimate an overfitting probability; §2a is a
  single paired 2-arm comparison (S-0.5 vs S-1.0) with one preregistered
  treatment, not a multi-strategy search — there is no combinatorial structure
  for CSCV to run over. PBO IS retained for the general Phase-2 L1/L2/cap-grid
  family (§2, ~14 named configurations across baselines + L1 candidates +
  cap-family variants — a genuine multi-strategy selection scenario), computed
  via CSCV over the unit-(i) daily paired-return series for each configuration.
- "Governor ≥ baseline" (or "S-1.0-floor ≥ S-0.5-floor") without meeting the
  applicable bar above is NOT enable-grade evidence.

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

- **Arm S-0.5 (treatment)**: `configs/strategy_config.shadow.json`,
  frozen values restated here NORMATIVELY (this doc, not `strategy-104#52`, is
  the contract): scorer `hf_patchtst`, Kelly `fractional` 0.5 /
  `max_concentration` 0.35, BULL_CALM `max_position_pct` 0.15,
  `one_share_floor_enabled` true, `buy_floor = "adaptive_mean_std"`,
  `buy_floor_std_mult = 0.5`. Broker-state tag `alpaca_shadow_a` →
  `live_state.alpaca_shadow_a.json` + `runs.alpaca_shadow_a.db`
  (a NEW tag, distinct from the legacy `alpaca_shadow` used by the untouched
  `daily_104.sh` Step-4 ops shadow — see the execution plan below for why the
  experiment cannot share that tag's state files).
- **Arm S-1.0 (control)**: `configs/strategy_config.shadow_b.json` — a
  clone of `shadow.json` differing in exactly ONE functional key (plus inert
  `_reason` annotation strings): `ranking.panel_scoring.buy_floor_std_mult
  = 1.0` (`buy_floor` stays `adaptive_mean_std`, matching S-0.5). Every
  other key (scorer, Kelly, regime cap, one-share floor, sector caps, slots)
  is IDENTICAL to S-0.5, enforced by a config-drift pin test. (The r5
  draft's second key, a `live.preflight.strict=false` shim for the umbrella
  runner's tag-keyed preflight special case, is WITHDRAWN — the umbrella
  runner is no longer on the experiment's path; arm-symmetric preflight
  policy is a required property of the orchestrator two-arm entrypoint, see
  the execution plan.) Broker-state tag `alpaca_shadow_b` →
  `live_state.alpaca_shadow_b.json` + `runs.alpaca_shadow_b.db`. This is
  the true control arm for the floor treatment: same environment, same
  session, only the floor differs.
- **Estimand (A) — floor effect (the causal claim, THIS protocol's decision
  rule)**: paired S-0.5 vs S-1.0, same session dates, same everything else.
  Two decision-grade endpoints, both END-TO-END arm-level quantities (r6
  point 2: score-threshold cohort membership does not establish that a name
  was actually selected, sized, filled, or exited — QP/slot/sector/no-sell
  interactions can change all of these — so no cohort quantity is
  decision-grade):
  - **P1 — deployed fraction (the deployment claim)**: each arm's
    end-of-chain deployed fraction per session, paired by session date
    (daily paired difference, S-0.5 minus S-1.0).
  - **P2 — PRIMARY quality / non-inferiority endpoint: paired ARM-LEVEL NET
    REALIZED portfolio return.** For each valid paired session, each arm's
    ledger-realized net daily portfolio return — actual simulated fills,
    actual whole-share quantization, realized tax drag on actual exits,
    actual transaction costs, i.e. AFTER all reweighting and turnover the
    treatment induces. Block endpoint: compound each arm's net daily series
    over each non-overlapping 20-valid-session block (§1.2 unit (ii)); the
    unit value is the paired difference (S-0.5 − S-1.0) of the two
    compounded block returns. No benchmark adjustment is needed — both arms
    run the same sessions, so market moves cancel in the pair. NO
    hypothetical cost/tax convention enters this endpoint anywhere: it is
    read off the two actual ledgers. A block is complete at its 20th valid
    session — realized returns carry no forward-window maturation lag.
    **Enable-grade at the 20d block length ONLY; 60d blocks are
    descriptive-only (§1.2).** A deployed-fraction lift with this endpoint
    failing = REJECT: if the actual treatment portfolio loses after its
    reweighting and turnover, no cohort statistic can rescue it.
  - **P2d — cohort diagnostic (DEMOTED from decision-grade; never gating;
    exact cohort definition frozen here)**: cohorts are **EXECUTED ENTRY
    LOTS** — names an arm ACTUALLY entered (fills recorded in its own
    ledger), split by which arm(s) entered them: (a) treatment-only entries
    (entered by S-0.5, not by S-1.0 — the executed realization of the
    "marginal entrant" concept); (b) common entries (entered by both);
    (c) control-only entries (entered by S-1.0 only — expected rare; a
    large count is itself a diagnostic flag for QP-interaction effects).
    Outcome per lot: 20d forward return from the lot's actual entry fill
    price, SPY-relative, net of the 5 bps/side + §1.1 tax CONVENTION —
    explicitly HYPOTHETICAL accounting at the cohort level (a lot's realized
    exit timing and tax treatment may differ from the convention), which is
    exactly why this analysis is diagnostic, not decision-grade. It is
    reported as a decomposition of WHERE the P2 arm-level difference comes
    from. The former pre-veto SCORE-threshold cohorts (marginal
    `mean+0.5σ ≤ rank_score < mean+1.0σ`, incumbent `≥ mean+1.0σ`, reject
    `< mean+0.5σ`, on the cross-section common to both arms) are retained
    as a purely DESCRIPTIVE report of score-band composition — threshold
    membership establishes neither selection nor execution, and no decision
    rule or kill rule references them.
- **Estimand (B) — residual environment effect (a SEPARATE diagnostic
  estimand, NOT part of the ENABLE/REJECT decision for the floor)**: paired
  S-1.0 vs actual production, same session dates. S-1.0 matches production's
  floor (1.0σ) exactly, so this comparison isolates the effect of everything
  ELSE that differs between the shadow environment and production (scorer,
  Kelly, regime cap, one-share floor) — holding the floor fixed. This is a
  prerequisite DIAGNOSTIC before any future live-enablement PR can claim the
  floor conclusion generalizes from shadow to production (scorer-transfer
  risk — the 2026-06-11 audit found `adaptive_mean_std` shape-unstable on
  Platt-compressed PatchTST scores, rank_score IQR 0.039, 1.0σ dropping 86%
  admits that day; the σ-multiplier treatment is scale-free per-session,
  which mitigates but does not eliminate this); it is not evidence for or
  against the floor itself, and a bad reading here blocks *generalizing* the
  S-0.5-vs-S-1.0 result to production, not the shadow-only verdict.
- **Explicitly retired**: a "production-XGB counterfactual" estimand
  (computing the marginal-entrant set on logged production scores that were
  never actually traded, as the superseded design proposed) is superseded by
  estimand (B) above, which uses a REAL executed comparison arm instead of a
  computed counterfactual. Do not compute a counterfactual P3 in addition to
  (B) — it would answer a strictly weaker version of the same question with
  a hypothetical portfolio where a real one is available.

**Execution plan — multi-repo-owned entry; umbrella changes PROHIBITED (r6
point 1; supersedes BOTH prior routes: the r5 draft's umbrella
runner/daily_104.sh items AND the r5-merge's bridge-tag route, which modified
no umbrella file but still drove the experiment through the umbrella
`live.runner` call path and monkeypatched an umbrella class attribute — an
umbrella integration in substance, now retired):**

**Prohibition (frozen protocol rule): no umbrella runner or call-site change
is permitted for this experiment — not as a prerequisite, not as a
separately-gated follow-up, not as a fallback. The umbrella remains a
deprecated pin consumer, and it is not invoked on the experiment's path.**
The prior draft's `daily_104.sh` "time-bounded migration exception" fallback
is WITHDRAWN outright. The entire entry path is owned by multi-repo
components:

*Ownership map (each fact verified by direct read-only inspection,
2026-07-10):*

- **renquant-execution — owns the parameterized read-only wrapper.**
  `renquant_execution.readonly_broker.ReadOnlyBrokerWrapper` already exists
  in the execution repo (an as-yet-unwired port of the umbrella wrapper) but
  hardcodes `broker_name = "alpaca_shadow"` as a class attribute
  (`readonly_broker.py:14`; `__init__` never sets it) — the same defect as
  the umbrella copy. Required change: a constructor/factory parameter
  (`__init__(self, underlying, broker_name: str = "alpaca_shadow")`) so each
  arm's instance tags itself. Entirely within the execution repo's boundary.
  The umbrella's local wrapper copy is NOT touched — it keeps serving the
  legacy single-arm Step-4 path unchanged.
- **renquant-pipeline — owns state paths; ALREADY parameterized.** Verified:
  every path function in `kernel/state_paths.py` takes `broker_name`
  (`live_state_path`, `runs_db_path`, `resolve_live_state_read`), guarded by
  the `ALLOWED_BROKERS` allowlist. The only change is the allowlist entries
  for the two experiment tags (below), in both copies (`state_paths.py` +
  `kernel/state_paths.py`, per this project's known duplication pattern);
  without them the allowlist raises `ValueError` (fail-closed by design).
- **renquant-orchestrator — owns the daily two-arm orchestration
  entrypoint.** A NEW orchestrator-owned script + launchd entry (in THIS
  repo) that, once per session, invokes the pinned pipeline decisioning
  entry TWICE, sequentially — once per (config, broker-state tag) pair —
  resolving both configs from the pinned strategy-104 subrepo, constructing
  each arm's broker as
  `ReadOnlyBrokerWrapper(AlpacaBroker(paper=False), broker_name=<tag>)`
  from `renquant_execution.readonly_broker`, and threading the tag into
  pipeline `kernel.state_paths` for state isolation. It does NOT import or
  invoke umbrella `live.runner`; `daily_104.sh` is NOT modified; the entry
  schedules independently after the daily cycle and is non-fatal to prod.

**Arm identity under this entry (tag correction from the r5 draft):** BOTH
experiment arms are produced by the orchestrator two-arm entrypoint — the
same code path, differing only in (config, tag) — because pairing an
umbrella-run arm with an orchestrator-run arm would itself be an
uncontrolled environment delta. The existing `daily_104.sh` Step-4 shadow
keeps running UNTOUCHED as ops monitoring, and it keeps writing the legacy
`alpaca_shadow` state (`live_state.alpaca_shadow.json`). The experiment's
arms therefore use their OWN tags so they can never collide with that
untouched legacy shadow's state:
- **S-0.5 → `alpaca_shadow_a`** (config `strategy_config.shadow.json`);
- **S-1.0 → `alpaca_shadow_b`** (config `strategy_config.shadow_b.json`).
Both arms start from fresh, empty shadow state at experiment start —
symmetric initial books by construction. The legacy `alpaca_shadow` tag
remains owned by the untouched Step-4 run and is NOT part of the experiment.

*Prerequisite PRs — D6-§2a build items, each subject to normal review
(Codex approval, progress doc, boundary checks). The experiment cannot start
until both are merged, plus the strategy-104 config-only PR (the #52
successor: `strategy_config.shadow_b.json` + config-drift pin test verifying
prod/golden untouched and shadow_b differing from shadow in EXACTLY the one
frozen treatment key, `buy_floor_std_mult`):*

1. **P-1 — renquant-execution: readonly-broker parameterization + wiring.**
   The constructor parameter above, plus behavior pins proving the port is a
   faithful owner before anything depends on it: reads forwarded to the
   underlying broker, every write converted to a shadow ack, no network
   mutation on any code path, and tag threading verified against pipeline
   `state_paths` — write-swallowing parity with the umbrella wrapper's
   tested contract.
2. **P-2 — renquant-orchestrator: two-arm shadow runner.** The entrypoint
   above. Required properties, frozen here as that PR's review contract:
   (i) both arms run the IDENTICAL pinned code path with arm-symmetric
   preflight policy (shadow non-strict for BOTH arms, owned by this
   entrypoint — not by a config shim, and not by the umbrella runner's
   tag-keyed special case, which is out of the path entirely; the r5
   draft's `live.preflight.strict=false` second config key is therefore
   WITHDRAWN and the config delta returns to exactly one key);
   (ii) arms run sequentially, never concurrently, against the same
   session's inputs; (iii) per-session run bundles stamped for both arms
   (field list below); (iv) symmetric labeling and notification for both
   arms on a DEDICATED shadow ntfy topic (never the live topic);
   (v) fail-closed: any wiring or contract failure invalidates the
   session-pair (inclusion rule below) and can never touch prod state;
   (vi) no umbrella runner import and no umbrella modification anywhere on
   the runner path. Scope note (honest): the umbrella currently hosts the
   runner-adapter glue for the daily LIVE path; P-2 assembles the two-arm
   SHADOW path from pipeline-owned decisioning components
   (`renquant_pipeline` kernel jobs, `native_inference`,
   `live_state_contract`) plus execution-owned brokers. Its exact assembly
   is decided in P-2's own review; its boundary contract — no umbrella
   change, no umbrella runner invocation — is frozen HERE and is not that
   review's to relax.

**Paired-world input synchronization — the decision snapshot (r7 point 1:
state isolation and post-hoc fingerprint matching do not, by themselves,
prove both arms consumed the SAME input world — sequential execution means
arm 2 could observe a different as-of reality than arm 1 if nothing forces
them onto a shared snapshot BEFORE either runs. Frozen here as a P-2 review
contract requirement, not left to that PR's discretion):**

- **What gets frozen, once, before EITHER arm is invoked**: P-2 materializes
  a single **decision snapshot** per session, consisting of: (i) the as-of
  decision timestamp; (ii) the candidate/scoring universe hash (the ticker
  list + any filters applied before scoring); (iii) the prices and
  corporate-action snapshot used for that session's bars (a hash of the
  resolved OHLCV + corporate-action table slice); (iv) the model artifact
  identity (reusing `model_content_sha256`, per the run-bundle fingerprint
  convention below); (v) the calibrator artifact identity (same convention);
  (vi) the starting portfolio-state convention for that session (each arm's
  own prior-EOD state — NOT shared between arms, since S-0.5 and S-1.0 hold
  different books by construction; what's frozen is the RULE that both arms
  read "yesterday's own close" rather than one arm accidentally reading a
  stale or future state); (vii) the session identifier (calendar date).
  P-2 computes ONE digest (sha256 of the concatenated, canonically-ordered
  fields above) for the session and passes that digest as an explicit
  parameter to BOTH arm invocations (e.g. a `--decision-snapshot-digest
  <hash>` CLI argument threaded into each pinned pipeline entry call) —
  neither arm independently resolves "today's" universe/prices/artifacts at
  its own invocation time; both are handed the identical frozen reference.
- **Consumption-side verification (fail-closed)**: each arm's pipeline
  invocation, upon actually resolving its inputs (universe, prices, model,
  calibrator) for the session, computes the SAME digest formula over what it
  actually consumed and asserts it equals the digest it was handed. A
  mismatch aborts that arm's run for the session (the existing fail-closed
  pattern) rather than proceeding on a silently-different input world. This
  closes the sequential-execution gap Codex flagged: even though arm 2 runs
  strictly after arm 1, it is constitutionally unable to consume a
  different-from-frozen universe/price/artifact snapshot without tripping
  this check.
- **Extends the run-bundle fingerprint and missingness rule below**: the
  decision-snapshot digest is added as an EIGHTH stamped field per session
  (alongside the seven already listed), and the paired-session inclusion
  rule's condition (iii) ("every fingerprint in both bundles matches the
  values frozen at experiment start") is read to include this digest
  matching across BOTH arms for that session — a session-pair where the two
  arms' actually-consumed-input digests differ is excluded under the SAME
  paired-exclusion mechanism already frozen below (voids the pair in BOTH
  arms, counts against the same missingness bounds), not a new mechanism.
- **Integration tests this requires** (specified precisely enough that a
  future implementation PR cannot satisfy the letter while missing the
  point; test CODE is not written in this doc-only PR):
  1. **Shared-digest test**: drive the two-arm entrypoint for one synthetic
     session and assert BOTH arm invocations received the IDENTICAL
     decision-snapshot digest string/parameter — not merely "both ran
     successfully," but an explicit equality assertion on the digest value
     each arm was handed.
  2. **Distinct-state-path test**: assert the two arms' resolved state file
     paths (`live_state.alpaca_shadow_a.json` vs `_b.json`, and the
     corresponding `runs.*.db` paths) are different, and that writing a
     sentinel value through one arm's state path does not appear when
     reading the other's — a genuine collision check, not just a
     string-inequality check on the tag names.
  3. **No-umbrella-import test**: after invoking the two-arm entrypoint,
     assert no module whose qualified name resolves into the umbrella
     package tree (`RenQuant.*`, or however that repo's package is
     importable from this process) appears in `sys.modules` — a static or
     runtime import-graph check proving the P-2 execution path never reaches
     umbrella code, not merely an assertion that `daily_104.sh` wasn't
     invoked as a subprocess.
  4. **Pair-fail-closed test**: synthetically corrupt one arm's consumed
     input (e.g. monkeypatch its resolved universe hash) after the shared
     digest was issued, run both arms for that session, and assert: (a) the
     mismatching arm's run aborts per the fail-closed rule; (b) the SESSION
     PAIR is excluded from `N_blocks` counting in BOTH arms (not just the
     corrupted one); (c) the exclusion is logged with a reason referencing
     the digest mismatch, distinguishable in the verdict memo from a
     mid-run config-fingerprint drift (a different, already-specified
     failure mode below) even though both route through the same
     paired-exclusion mechanism.

**Statistical power (r6-corrected: §1.2 unit (ii) defines the unit as a
non-overlapping `h`-day OUTCOME BLOCK with DEPENDENCE-ROBUST inference —
the blocks are not independent, so the tool is the §1.2 NW-on-blocks
small-sample CI + stationary-bootstrap conjunction with the `ESS`
criterion, not a plain t-test):**

Each 20-valid-session non-overlapping block (both arms run the SAME calendar
sessions, so a block is 20 consecutive valid paired sessions on which both
S-0.5 and S-1.0 executed) yields exactly one paired block observation for
the P2 arm-level endpoint — the paired difference of the arms' compounded
net realized ledger returns over that block. Because the endpoint is
REALIZED (not forward-labeled), a block's observation exists as soon as the
block's 20th valid session closes — no maturation lag. `N_blocks` = the
count of complete blocks since both arms went live; the enable-grade minima
are `N_blocks ≥ 8` AND `ESS ≥ 6` (§1.2).

- At `N=10` live sessions: `floor(10/20) = 0` complete blocks. Zero
  complete blocks means zero block observations — the superseded design's
  ≥10-session HAC test was attempting inference on a sample that, correctly
  counted, contains no complete block at all yet.
- Reaching `N_blocks = 8` (the frozen ABSOLUTE FLOOR — see the power
  derivation below for why this is a floor, not a target) requires **160
  valid paired sessions (~8 months); ≈ 200 scheduled sessions under the 20%
  missingness bound.**

**Real power derivation (r7 point 3 — `N_blocks ≥ 8`/`ESS ≥ 6` were
thresholds asserted without a power justification; the r6 draft's "~30
blocks (~600 sessions) for full power" claim was ALSO an unsubstantiated
assertion, not a derivation — corrected here with an actual calculation and
an honest accounting of what variance estimate is and isn't available):**

- **Formula**: for a one-sided non-inferiority test at significance `α` and
  target power `1 − β`, detecting margin `δ` against a block-difference
  standard deviation `σ_block`, the required effective sample size is
  `N ≈ ((z_α + z_β) · σ_block / δ)²`. At the frozen `α = 0.05` (`z_α =
  1.645`) and a conventional `power = 0.80` (`z_β = 0.84`) target, `(z_α +
  z_β) ≈ 2.485`, and `δ = 50 bps` (the frozen non-inferiority margin).
- **No real prior variance estimate exists for the actual treatment.** The
  S-0.5-vs-S-1.0 comparison (differing ONLY in `buy_floor_std_mult`, same
  cap, same scorer, same everything else) has never been run — there is no
  historical data to estimate `σ_block` for THIS SPECIFIC treatment before
  the experiment starts. The only available empirical evidence is the
  cap-grid tuning data (`doc/research/evidence/cap_grid_tuning/results.md`,
  exploratory/tuning subset), which compares cap12 vs cap20/25 — a
  STRUCTURALLY LARGER perturbation (name-cap 12%→20%, sector breaches
  30→72 sessions, turnover 0.269→0.359) than a same-cap admission-floor
  tweak. Reusing it is a labeled, likely-CONSERVATIVE (over-stated) proxy,
  not a calibrated estimate of the true treatment's variance — a
  structurally bigger perturbation should produce a noisier arm-difference
  series than a subtler one, so this proxy is expected to overstate
  `σ_block`, and therefore overstate the required `N` (erring toward
  over-caution, the safe direction for a sample-size floor).
  - From the cap-grid table: `cap20_ew` vs `cap12_ew`, HAC t = −1.09 over
    149 daily paired sessions, total net returns +4.70%/−3.08% respectively.
    Back-solving (mean daily diff ≈ (−3.08% − 4.70%)/149 ≈ −5.22 bps/day;
    `SE_HAC(mean) = mean/t ≈ 4.79 bps`; `σ_daily ≈ SE × √149 ≈ 58.5 bps`) —
    an approximate, order-of-magnitude back-calculation from the reported
    HAC t-statistic, not an independent re-derivation from raw daily
    returns (which this doc-only PR does not have runtime access to
    recompute).
  - Scaling to a 20-day block under a near-i.i.d. daily-increment
    approximation (`σ_block ≈ σ_daily · √20`): `σ_block ≈ 58.5 · 4.47 ≈
    262 bps` per 20-day block.
  - Plugging into the formula: `N ≈ (2.485 · 262/50)² ≈ (13.0)² ≈ 170`
    effective blocks (`ESS ≈ 170`) — roughly **170 × 20 ≈ 3,400 sessions
    (~13-14 years)** at this conservative proxy. This is grossly impractical
    and, being a conservative (likely over-stated) proxy, an UPPER bound on
    the true requirement — not a number to freeze as the actual target.
- **Honest conclusion**: the frozen `N_blocks ≥ 8`/`ESS ≥ 6` minima are an
  ABSOLUTE FLOOR (below which no variance estimate is trustworthy at all —
  §1.2), NOT a power-justified target; the conservative proxy above suggests
  the TRUE power-justified target could be far higher, but that estimate is
  built on a structurally mismatched comparison and cannot be frozen as the
  real requirement either. Neither number (8, nor ~170) is fit to freeze as
  THE sample-size target before the actual treatment has produced any data.
- **Resolution — blinded sample-size re-estimation (frozen mechanism, not a
  frozen number)**: at the SAME predeclared checkpoint already frozen for
  the Tier-1 P2-kill inspection (the first 3 complete blocks — see Tier 1
  below), compute the REALIZED sample standard deviation of the `d_i` block
  series accumulated so far, `σ̂_block`, using ONLY the squared deviations
  of the observed `d_i` values (a variance-only computation, BLIND to the
  sign/magnitude of the mean — this is standard "blinded sample-size
  re-estimation" practice: recalculating the required N from a nuisance
  parameter, not from the treatment-effect estimate itself, does not
  reopen the optional-stopping problem because no decision about the
  DIRECTION of the effect is made at this checkpoint). Plug `σ̂_block` into
  the formula above with the same frozen `α = 0.05`, `power = 0.80`, `δ =
  50 bps` to obtain `N*`, the REAL required effective sample size for THIS
  experiment's actual data. **Freeze the Tier-2 gate as `N_blocks ≥ max(8,
  N*)` AND `ESS ≥ 6`** — the fixed 8-block floor from §1.2 remains a floor;
  `N*` can only raise the bar, never lower it below 8. This re-estimation
  happens EXACTLY ONCE (at 3 complete blocks), is recorded in the verdict
  memo with its inputs (`σ̂_block`, `N*`), and is never redone at a later
  block count.
- **If `N*` is impractically large** (plausible, given the conservative
  proxy above lands near 170): the protocol's honest posture, per this
  finding, is that the live shadow arm-level 20d endpoint may not reach a
  statistically defensible ENABLE within a practical timeframe at this
  margin. The default outcome in that case is NOT a forced ENABLE at a
  weaker bar — it is **DESCRIPTIVE-ONLY / NO-ENABLE-BY-DEFAULT**,
  indefinitely, with the point estimate and its (untrustworthy, wide) CI
  reported for operator awareness, same as the existing 60d-horizon
  treatment. This is stated as a first-class possible outcome of running
  this experiment, not a design failure: a subtler treatment effect
  (admission-floor multiplier, same cap) may in reality have much lower
  variance than the cap-grid proxy implies, in which case `N*` computed
  from REAL data at the 3-block checkpoint could turn out far more
  tractable than 170 — this is exactly why the re-estimation is deferred to
  real accumulated data rather than frozen from the proxy now.

**Resolution — two-tier reporting, not a single fixed-N verdict (Tier-1 kill
rules FROZEN, r5 point 4: "grossly adverse"/"sharply negative" were examples,
not thresholds, and are WITHDRAWN as discretionary):**
- **Tier 1 — mechanical early-REJECT check only, each rule a SINGLE
  predeclared inspection, not a rolling/repeated look (r7 point 4: "any 5
  consecutive sessions ending at/after session 10" was a rolling window
  re-evaluated fresh every session — that IS repeated looking, just
  disguised as a window rather than literal day-by-day monitoring; fixed
  below by collapsing each rule to exactly one fixed, non-overlapping,
  never-re-evaluated window).** A script — not a judgment call — evaluates
  exactly TWO frozen kill conditions, declared on **NET** terms, each fired
  at most once, ever:
  - **P1-kill — evaluated EXACTLY ONCE, at valid paired session 10**: the
    mean deployed-fraction difference (S-0.5 − S-1.0) over the FIXED,
    non-overlapping window of valid paired sessions 6-10 (inclusive — five
    sessions, computed once) is below **−5pp absolute**. Deployed fraction
    is observed same-day (no maturation lag). This check is evaluated ONE
    TIME, at session 10, using ONLY sessions 6-10; it is NEVER re-evaluated
    at session 11, 12, or any later session — if it does not trigger at
    session 10, the P1-kill check is RETIRED (no further monitoring-based
    P1 REJECT path exists; P1's real gating happens at Tier-2 maturity per
    §5's frozen hypothesis test, which is a one-time confirmatory
    evaluation, not a repeated look either).
  - **P2-kill — evaluated EXACTLY ONCE, at the FIRST 3 complete non-
    overlapping 20d blocks (valid paired sessions 1-60, i.e. blocks 1-3)**:
    the mean of the PAIRED ARM-LEVEL NET realized 20d block return (S-0.5 −
    S-1.0, read off the two actual ledgers — actual fills, realized tax,
    actual costs; the P2 endpoint above) over EXACTLY blocks 1-3 (not "all
    complete blocks so far," which would re-evaluate at every new block) is
    below **−300 bps per 20d block**. Gross returns are never used for this
    rule; no cohort statistic feeds it. This check is evaluated ONE TIME,
    when block 3 completes; it is NEVER re-evaluated when block 4, 5, or
    any later block completes — if it does not trigger, the P2-kill check
    is RETIRED (Tier-2 maturity's confirmatory test governs P2 from then
    on).
  Either condition, at its single evaluation, ⇒ REJECT immediately,
  recorded with the triggering window/blocks in the verdict memo. No other
  outcome-based early-reject path exists, and neither check is ever
  performed a second time.
- **Symmetric no-early-ENABLE (no optional stopping in either direction)**:
  an equally sized FAVORABLE read at either single checkpoint — e.g. a +5pp
  sessions-6-10 deployed-fraction lift, or a +300 bps blocks-1-3 paired
  arm-level net mean — authorizes NOTHING: not an early enable, not a
  shortened Tier 2, not a reduced block minimum. ENABLE can only be decided
  at full Tier-2 maturity.
- **Safety-breach stops are a DIFFERENT failure mode from statistical-
  efficacy stopping, and are not subject to the look-count discipline
  above.** The two kill rules just fixed are STATISTICAL-EFFICACY stops:
  governed by the single-look, no-repeated-monitoring discipline above,
  because they are inferences about the treatment effect and therefore
  subject to the optional-stopping/multiple-comparisons problem. The §2a
  non-degradation gates (per-name/sector concentration, session turnover,
  drawdown, fingerprint cleanliness — listed in the gate table below) are
  SAFETY stops: engineering/risk checks evaluated EVERY session, with no
  look-count restriction, because they are not testing a hypothesis about
  the treatment effect — they are bounding operational risk, and a cap or
  drawdown breach is real regardless of how many times it's been checked
  for. A safety-gate breach triggers an IMMEDIATE stop (recorded,
  REJECT/REDESIGN pathway) at whatever session it occurs, with no
  "predeclared single look" requirement — checking every session for a
  drawdown breach is not optional stopping, because the drawdown gate isn't
  inferring anything about the floor's causal effect.
- **No interim confidence intervals**: at Tier 1 no CI, DSR, or PBO is
  computed or reported (below the §1.2 `N_blocks`/`ESS` minima a variance
  estimate is not trustworthy; a computed CI would be false precision).
  Tier-1 output is the two kill-rule booleans plus point estimates
  explicitly labeled "underpowered, not significance-tested".
- **Tier 2 — confirmatory read, block-gated (replaces the fixed
  "+10 extension" rule; gate revised at r7 point 3 to include the blinded
  power re-estimation above)**: continue running both arms until
  **`N_blocks ≥ max(8, N*)` complete non-overlapping 20d blocks AND `ESS ≥
  6`** accumulate, where `N*` is the ONE-TIME blinded power re-estimate
  computed at the 3-block checkpoint (above) — 160 valid sessions is the
  ABSOLUTE FLOOR (≈ 200 scheduled under the 20% missingness bound); if `N*
  > 8`, the real target is `N*` blocks, recorded in the verdict memo
  alongside `σ̂_block` the moment it's computed. The realized endpoint has
  no maturation lag. At that point compute the preregistered §1.2 unit-(ii)
  dependence-robust test on the paired arm-level block series (NW-on-blocks
  small-sample CI AND stationary bootstrap, in conjunction, plus the `ESS ≥
  6` check): the P2 bar is (a) paired arm-level net block mean ≥ 0 AND (b)
  the one-sided test rejects "mean ≤ −50 bps/block" (the non-inferiority
  margin below). This is the earliest point at which a RECOMMEND-ENABLE or
  a final (non-kill) REJECT verdict may be issued; a verdict issued before
  Tier 2's block gate is not decision-grade regardless of what the point
  estimate shows. **If, at any scheduled review point, complete blocks <
  max(8, N*) or ESS < 6, the outcome is NO-ENABLE-BY-DEFAULT** with exactly
  one predeclared extension: keep running until both minima are met (no
  peeking-based stop, no parameter change) — **if `N*` is impractically
  large (the statistical-power section above's conservative proxy suggests
  this is plausible), this extension may never practically complete, in
  which case the honest, first-class outcome is an indefinite
  DESCRIPTIVE-ONLY read, not a forced verdict at a weaker bar.** DSR is
  computed on this same block series once the minima are met, deflated for
  the 2 arms actually compared (S-0.5, S-1.0 — a small trials-correction,
  named explicitly since it's non-zero). **PBO does not apply to this
  comparison** (§1.2) — a single preregistered 2-arm paired design has no
  combinatorial train/test structure for CSCV to run over; PBO is not
  computed for estimand (A) or (B), and its absence is not a gap, it is the
  correct treatment of a 2-arm design per §1.2.
- **Non-inferiority margin (predeclared, Tier 2)**: the paired arm-level net
  block-return mean (S-0.5 − S-1.0) must not be below **−50 bps per 20d
  block** (one-sided non-inferiority margin, chosen as roughly the
  round-trip transaction-cost convention doubled — a conservative buffer
  against a treatment that is merely "not better" being mistaken for
  "materially worse"), in addition to the ≥ 0 point-estimate requirement in
  the Tier-2 bar (deploying MORE capital must show up as at-least-flat
  arm-level net return; a deployed-fraction lift with a negative arm-level
  point estimate means the treatment portfolio loses after its reweighting
  and turnover — REJECT). The margin gives the test a concrete alternative
  rather than a point null the data can't resolve at any reachable N.
- **60d horizon: DESCRIPTIVE-ONLY for this experiment (per §1.2)** — reaching
  8 complete 60d blocks would take 480 sessions (~2 years), out of scope for
  this protocol version. 60d block statistics are reported in the verdict
  memo descriptively as they complete, are explicitly NOT enable-grade at
  this sample size, and no 60d significance test is computed. The Tier-2
  verdict covers the 20d block length only and is labeled as such.

**Run-bundle fingerprint (closes the fingerprint-gap flagged in the r4 draft;
missingness rule added at r5)**: each shadow session for BOTH arms stamps:
(i) a config hash — sha256 of the resolved `strategy_config.shadow.json` /
`strategy_config.shadow_b.json` content; (ii) a model-artifact hash — reusing
the project's existing unified `model_content_sha256` /
`model_content_sha256_from_path` convention
(`renquant_pipeline.kernel.panel_pipeline.fingerprint_dispatch`), not a
bespoke scheme; (iii) a calibrator hash (same unified convention — the
calibrator is a separate artifact with its own recurring-mismatch history in
this project); (iv) the broker-state identity tag (`alpaca_shadow_a` /
`alpaca_shadow_b`); (v) the pin SHAs of `renquant-strategy-104`,
`renquant-pipeline`, AND `renquant-execution` at run time; (vi) the frozen
data/feature manifest hash used by that session's scoring pass (the same
manifest SHA convention as §1's freeze-rule commit); (vii) this orchestrator
repo's own commit SHA — the commit of the invoking two-arm runner (so the
protocol version a session was run under is unambiguous even after this doc
changes again); (viii) the decision-snapshot digest (r7 point 1, above) each
arm actually consumed for that session.

**Paired-session inclusion + fingerprint-mismatch missingness rule (r5 — was
previously "silently excluded," now exact, bounded, and paired)**: a session
date is COUNTED iff ALL of: (i) both arms ran to completion on that date (no
preflight abort, timeout, or `panel_scorer_config_mismatch`-class fail-closed
contract failure in either arm); (ii) both per-session bundles are present
and complete; (iii) every fingerprint in both bundles matches the values
frozen at experiment start; (iv) both arms' bundles record the SAME
model-artifact sha, calibrator sha, and data/feature manifest sha for that
session (the arms must have scored the same world). A failure of any
condition on EITHER arm invalidates that SESSION-PAIR in BOTH arms — a
paired design requires paired inclusion, so a clean S-1.0 session paired
with a drifted S-0.5 session (or vice versa) is excluded entirely, not
half-counted — and every exclusion is logged with its reason. Track a
running excluded-pair count against the running attempted-pair count.
**Predeclared bounds**: if excluded pairs exceed 2 of the `h` sessions
needed to complete a given non-overlapping outcome block, that ENTIRE block
is void and does not count toward `N_blocks` (it is not patched with a
partial window); if cumulative excluded pairs exceed 20% of all session-pairs
attempted since the protocol version's start, the experiment is **VOID** —
do not continue accumulating under a version with a demonstrated systemic
drift problem; restart §2a under a new protocol version with a fresh
fingerprint freeze and reset session counters (both thresholds are
operator-judgment defaults, consistent in spirit with the §2 turnover-tax
gate's frozen-default treatment: no clean empirical basis exists yet for a
data-derived number, so a defensible round number is frozen now and not
adjusted after seeing how often mismatches actually occur).
**Treatment-fingerprint drift voids immediately**: if the resolved config
hash of EITHER arm changes mid-run relative to its frozen-at-start hash —
regardless of how few sessions that has affected so far — the experiment is
**VOID** and restarts under a new protocol version. A config change never
reinterprets the experiment; it terminates it. This, not a cross-reference,
is what makes the contract robust to later config PRs (including
`strategy-104#52` itself).

**§2a non-degradation gates (frozen HERE, self-contained — not a cross-
reference to strategy-104#52, which is now config-only and cannot alter this
contract by drifting):**

| Gate | Tolerance | Applies to |
|---|---|---|
| Per-name concentration | each arm's book ≤ its OWN configured caps, stated exactly: BULL_CALM `max_position_pct` 0.15 and Kelly `max_concentration` 0.35 (identical in both arms, unchanged from `shadow.json`; this protocol changes no cap — the D6 §4 cap-grid gate is a separate comparison; the production 12% cap is untouched) | S-0.5, S-1.0 |
| Sector concentration | ≤ 35% per sector, max 6 names/sector | S-0.5, S-1.0 |
| Session turnover | each arm ≤ 2× the OTHER arm's same-session turnover (paired, not vs production — S-0.5/S-1.0 differ only in the floor, so a turnover blowout on one side signals a funnel bug, not a floor effect) | S-0.5 vs S-1.0 pair |
| Drawdown | either arm's MDD over the accumulated window ≤ 0.30 (regime `drawdown_halt_pct` 0.35 minus ≥5pp headroom, matching D6 §4) | S-0.5, S-1.0 |
| Fingerprint cleanliness | every counted session-pair passes the run-bundle fingerprint match above; the missingness rule's block/experiment-void bounds are not breached | S-0.5, S-1.0 |

**Stop rule**: immediate stop on ANY gate breach (live-shadow venue, per D6
§5's venue split) — the breach is recorded and the verdict pathway is
REJECT/REDESIGN; no gate tolerance may be relaxed mid-run.

**Decision rule (self-contained; supersedes the superseded design's §9 for
the floor-effect claim)**:
- **Verdict = recommendation memo** (`doc/research/`, in this orchestrator
  repo), issued only at Tier 2 maturity (`N_blocks ≥ 8` complete 20d blocks
  AND `ESS ≥ 6`, per the block gate above). RECOMMEND-ENABLE iff ALL of:
  1. **P1 (r7 point 2 — minimum effect size added; "> 0" alone permitted an
     arbitrarily small noisy increase to satisfy a capital-deployment
     claim)**: the daily paired deployed-fraction mean difference is **≥ 2
     percentage points absolute** (a practically meaningful lift — the whole
     point of loosening the floor is materially more deployment, not a
     statistically-detectable-but-trivial nudge; chosen as roughly 40% of
     the 5pp P1-kill threshold below — small enough to be achievable given
     the floor relaxation's modest expected magnitude, large enough to move
     the needle toward the ~90%-deployment target this lever exists to
     serve) AND its NW (§1.2 unit (i) lag rule, capped at 10) one-sided 95%
     CI (`α = 0.05`, consistent with §1.2's frozen level) excludes both 0
     AND the 2pp threshold — i.e. the CI's lower bound must clear 2pp, not
     merely exclude 0;
  2. **P2 — the PRIMARY arm-level endpoint, 20d blocks ONLY** (60d is
     descriptive-only, never gating; the P2d cohort diagnostic and the
     score-band report gate NOTHING): the paired arm-level net realized
     block-return mean (S-0.5 − S-1.0, actual ledgers) is ≥ 0 AND the §1.2
     dependence-robust one-sided test (NW-on-blocks small-sample CI AND
     stationary bootstrap, in conjunction) rejects "mean ≤ −50 bps/block";
  3. every §2a gate above is green on both arms for every counted
     session-pair;
  4. run-bundle fingerprints are clean on every counted session-pair, the
     missingness bounds are not breached, and zero treatment-fingerprint
     drift occurred.
  Anything less: REJECT — or, where the only failure is complete blocks <
  max(8, N*) (the r7 blinded power re-estimation floor, §2a Statistical
  power) or ESS < 6, the honestly-underpowered NO-ENABLE-BY-DEFAULT with its
  single predeclared extension (keep running until both minima are met; no other
  extension mechanism exists).
- Estimand (B) is reported alongside as a scorer-transfer-risk diagnostic but
  is NOT a gating condition for THIS verdict — it gates whether a SEPARATE
  future live-enablement PR may cite this shadow evidence as externally valid
  for production, which is that future PR's decision to make, not this
  protocol's.
- **Live enablement is a SEPARATE, gated decision**: its own PR flipping
  PRODUCTION `buy_floor_std_mult` (not shadow), carrying this memo, a pre-
  registration gate, and Codex review — a live-book behavior change is never
  bundled with this protocol or with strategy-104#52's eventual config-only
  PR. Neither this protocol nor #52 authorizes anything on the live book.
- **Rollback**: a single config value — revert `shadow_b.json`'s
  `buy_floor_std_mult` (or simply stop the orchestrator two-arm runner).
  Blast radius is zero by construction: both arms run on isolated shadow
  broker state (`alpaca_shadow_a` / `alpaca_shadow_b`) and place no live
  orders.

**[End of §2a.] The remaining bullets below (fractional-shares dependency
through the arm-specific concentration contract) are the GENERAL Phase-2
L1/L2/cap-grid Governor evaluation — a separate comparison family from §2a's
breadth-lever shadow A/B, sharing this §2 heading only because no new
subsection break existed in the r4 draft. They do not gate or depend on §2a,
and §2a does not gate or depend on them.**

- **Fractional-shares dependency quantified**: integer flooring shaves 3.1-4.1pp
  of deployment at $10.7k PV in every arm; P(E_exec ≥ 0.90) is stuck at 10-12%
  regardless of cap — reaching ~90% living deployment requires breadth ≥ 5-8
  PLUS fractional execution (S-FRAC v2 stage-3) or larger PV. Cross-references
  the D7 memo (#444).
- **Controls**: cash/parking-sleeve arm (idle capital at T-bill yield).
- **Evaluation scheme — contiguous simulation, corrected inference unit** (r4
  review, corrected again at r5 — the r4 fix conflated two separate problems
  and got the second one wrong; see below):
  - **Problem 1 (r4's actual target, still fixed the same way): portfolio
    continuity.** The exploratory grid's non-contiguous 30%-random-hash session
    sampling forced an off-universe liquidation on 140-141/149 sessions every
    arm (`cap_grid_tuning/results.md` limitation #6) — normal multi-session
    holding continuity never existed in that sample. **Fix**: take the full
    frozen WF-cut session range from §1 (excluding the 2026-06-23 → 2026-07-09
    hypothesis window and the individually-inspected #442 sessions), ordered
    chronologically, and split it into exactly TWO contiguous ranges — not
    multiple 60-day blocks, which was r4's over-construction and the root of
    the r5 bug below: the earliest ⌈N/2⌉ sessions are the TUNING range (used
    ONLY for the §1 nested-selection hyperparameter choices), followed by a
    **60-trading-day PURGED embargo (r6 point 3 — raised from the r5 draft's
    30d: the embargo must be at least as long as the LONGEST forward horizon
    evaluated (60d), otherwise the 60d-forward outcomes of the final tuning
    sessions share calendar returns with evaluation outcomes and the claimed
    holdout is not purged; the existing 30d WF-gate convention was set for a
    different context and under-purges here. The alternative — full purged
    walk-forward with explicit position/label carryover accounting — buys no
    additional purge at this corpus size for substantially more machinery;
    the ≥60d embargo is the simpler predeclared rule and is chosen)**,
    followed by the EVALUATION range (remaining
    sessions, used ONLY for §3 estimands, §4 gates, and the §5 decision rule).
    Each range is simulated as ONE continuous book — positions carry over
    session-to-session within a range like a real book, with zero internal
    gaps — which is what actually fixes the off-universe liquidation problem;
    it does not require chopping the evaluation range into further sub-blocks.
  - **Problem 2 (r5 correction — r4 got this wrong): the unit of statistical
    inference is NOT the same thing as the unit of portfolio-continuity
    simulation.** r4's draft additionally chopped the evaluation range into
    60-trading-day CALENDAR blocks and ran per-block Newey-West on each block's
    ~60 daily paired-return observations, then inverse-variance-pooled across
    blocks — Codex's r5 review correctly identified that this is broken twice
    over: (a) a session near a block's end has its h-day (up to 60d) forward
    return window spanning PAST that block boundary into the next block's
    data, so blocks are NOT actually independent as claimed; (b) even ignoring
    (a), a 60-day block of daily 60d-forward-labeled observations contains
    only ~1 independent outcome (every observation in the block shares nearly
    the same forward window) — Newey-West on n≈60 such observations estimates
    a standard error from data that doesn't contain enough independent
    information for the SE itself to be trustworthy, regardless of the
    correction technique.
  - **Fix — apply §1.2's non-overlapping-outcome-block method to whichever
    quantity is actually being estimated**: for the §3 realized daily paired
    portfolio-return promotion bar (§1.2 unit (i) — NOT forward-looking),
    compute directly on the EVALUATION range's full continuous daily series
    with ordinary short-lag HAC — no sub-blocking needed, since there's no
    forward-window overlap in a same-day realized return. For any h-day
    block-aggregated estimand computed over that range (§1.2 unit (ii) —
    e.g. the §3 marginal-capital estimand), slice the EVALUATION range into
    non-overlapping `h`-day OUTCOME blocks (a pure accounting unit for the
    estimand, separate from the continuous portfolio simulation underneath
    it) and apply §1.2's dependence-robust method — the blocks are NOT
    treated as independent (r6): NW-on-blocks small-sample CI + stationary
    bootstrap in conjunction, with the `N_blocks ≥ 8` AND `ESS ≥ 6` minima.
  - **Concretely**, with ~497 total frozen sessions (the #442/cap-grid freeze
    record's scale): tuning ≈ 249 sessions, **60-day embargo**, evaluation
    ≈ 188 sessions (497 − 249 − 60). Within that 188-session evaluation
    range: 20d non-overlapping outcome blocks: `N_blocks = floor(188/20) =
    9`. 60d blocks: `floor(188/60) = 3`. Against §1.2's frozen enable-grade
    minima, the 20d estimand clears the count floor at `N_blocks = 9` —
    subject to the `ESS ≥ 6` check on the realized block series — and is
    reported with its wide dependence-robust CI, explicitly labeled
    low-power; the rule binds if the frozen list yields fewer than 8 blocks
    or `ESS < 6` (the verdict is then NO-ENABLE-BY-DEFAULT; replay history
    cannot be "collected" like live sessions, so the only extension is a
    new frozen session list under a new protocol version). The **60d
    estimand, at 3 blocks, cannot support ANY significance test on this
    frozen historical pool** — it is DESCRIPTIVE-ONLY (per §1.2): report
    the 60d point estimate directionally, indefinitely, unless a future
    protocol version re-freezes a longer WF-cut history. This is an honest
    capacity limit of the available ~497-session pool, not something a
    smarter estimator can fix. **And per §1.2 (r6): even a passing 20d
    replay read is directional/low-power SUPPORT, not promotion — ENABLE
    additionally requires the live shadow arm-level endpoint (S1) to meet
    its own bar; see §5.**
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
    sampling, which the contiguous-simulation evaluation scheme above is
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
difference between (a)'s two registered arms, using §1.2 unit (ii)'s
non-overlapping-block method with its dependence-robust inference (an h-day
block-aggregated estimand, the same class as §2a's P2 — not the daily-return
unit (i) treatment used for the DSR/PBO promotion bar above). This is exactly
reproducible (same allocator, same sessions, only E* differs); no
separately-constructed synthetic portfolio exists. More invested but worse
risk-adjusted = REJECT.

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
- **the S1 LIVE shadow arm-level paired-return endpoint meets its own §1.2
  unit-(ii) dependence-robust bar on future-only sessions (r6 point 3):
  historical replay evidence — including a passing 20d block read — is
  directional/low-power SUPPORT and cannot by itself clear this rule;
  replay ranks and screens, live shadow confirms;**
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
