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
  - **(ii) h-day-ahead FORWARD-return estimands** (e.g. §2a's P2 marginal-entrant
    20d/60d forward-return quality): a rolling daily series of h-day-forward
    returns has each consecutive pair of observations sharing `h-1` days of the
    same forward window — HAC/Newey-West on the raw daily series does NOT fix
    this (r5 review, correcting the r4 fix): with h=60 and any calendar-block
    scheme shorter than several times h, a block's forward window spans past its
    own boundary into the next block's data (the blocks are NOT actually
    independent as the r4 fix claimed), and within a block of n≈60 daily
    observations there is only ~1 independent 60d-forward outcome anyway — HAC
    corrects small-sample bias, it does not manufacture information the
    overlapping series doesn't contain.
    **Corrected unit — non-overlapping OUTCOME blocks**: partition the eligible
    session range into consecutive, NON-OVERLAPPING windows of exactly `h`
    trading days each. Each window contributes exactly ONE outcome observation:
    the actual h-day holding-period return realized from that window's start to
    `h` trading days later. Consecutive blocks share zero calendar days, so their
    outcome windows cannot overlap by construction — the resulting sample IS
    genuinely independent (to first order; residual regime-persistence
    autocorrelation across blocks, if any, is a second-order concern not
    addressed by HAC either way). `N_eff` = the actual count of complete
    non-overlapping `h`-day blocks in the eligible range — a real count, not the
    `N/h` heuristic used in the (now superseded) r4 draft. Ordinary (non-HAC)
    inference — a paired t-test on the block-return sample, or its exact
    permutation-test analogue for small `N_eff` — is the valid tool here; a HAC
    correction is neither necessary (no within-sample overlap left) nor
    sufficient (it cannot rescue a sample this small). This is the unit for
    §2a's P2 estimand and for any other h-day-forward-return estimand in this
    protocol (superseding the "60-trading-day calendar block + per-block
    Newey-West + inverse-variance pooling" scheme from the r4 draft, which
    conflated units (i) and (ii) above).
- **Promotion bar, unit (i)**: paired mean advantage point estimate ≥ +1 bp/day
  AND (short-lag) HAC 95% CI excluding 0 AND DSR ≥ 0.95 AND PBO ≤ 0.10 (the
  harness's existing significance pass, `compute_significance_verdicts`).
- **Promotion bar, unit (ii)**: paired mean block-return advantage point estimate
  ≥ 0 (net of cost) AND, ONLY once **`N_eff ≥ 8` matured complete blocks (the
  frozen enable-grade minimum, everywhere in this protocol)**, a
  t-test/permutation-test CI
  excluding a value below the predeclared non-inferiority margin. Below 8
  matured blocks the outcome is **NO-ENABLE-BY-DEFAULT**: report the point
  estimate as directional-only — no CI, no
  DSR/PBO (both require a stable variance estimate that a handful of blocks
  cannot supply) — per §2a Tier 1, and continue accumulating under the
  predeclared extension rule of the relevant experiment (no peeking-based
  stop). **Enable-grade forward-return claims are made at the 20d horizon
  ONLY: the 60d horizon is DESCRIPTIVE-ONLY everywhere in this protocol** —
  at every planned sample size (live shadow AND the frozen replay pool) it
  yields `N_eff < 8`, so it is reported, never promotion-gating, and no 60d
  significance test is computed.
- **DSR/PBO applicability**: DSR (mean/std of the realized return sample,
  deflated for the number of configurations actually tried) applies to BOTH
  units once N is adequate — for unit (i), N = trading days in the evaluation
  window; for unit (ii), N = `N_eff` non-overlapping blocks, and the DSR trials
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

- **Arm S-0.5 (existing shadow, treatment)**: `configs/strategy_config.shadow.json`,
  frozen values restated here NORMATIVELY (this doc, not `strategy-104#52`, is
  the contract): scorer `hf_patchtst`, Kelly `fractional` 0.5 /
  `max_concentration` 0.35, BULL_CALM `max_position_pct` 0.15,
  `one_share_floor_enabled` true, `buy_floor = "adaptive_mean_std"`,
  `buy_floor_std_mult = 0.5`. Broker-state tag `alpaca_shadow` (existing) →
  `live_state.alpaca_shadow.json` + `runs.alpaca_shadow.db`.
- **Arm S-1.0 (NEW, control)**: `configs/strategy_config.shadow_b.json` — a
  clone of `shadow.json` differing in exactly TWO functional keys (plus inert
  `_reason` annotation strings):
  1. `ranking.panel_scoring.buy_floor_std_mult = 1.0` (`buy_floor` stays
     `adaptive_mean_std`, matching S-0.5) — the only key that differs in
     TREATMENT terms;
  2. `live.preflight.strict = false` — an arm-plumbing equivalence shim, NOT
     a treatment delta: the umbrella runner's preflight-strictness special
     case keys on the exact broker tag `"alpaca_shadow"`
     (`live/runner.py:461`, `shadow_strict` default false), so the S-1.0
     arm, which runs under tag `alpaca_shadow_b`, must reproduce the
     identical non-strict preflight behavior through the runner's EXISTING
     config surface (`config["live"]["preflight"]["strict"]`,
     `runner.py:457-465`) rather than through new umbrella code. Without
     this key the two arms would have asymmetric preflight abort semantics
     — a real arm-asymmetry bug, closed config-side.
  Every other key (scorer, Kelly, regime cap, one-share floor, sector caps,
  slots) is IDENTICAL to S-0.5, enforced by a config-drift pin test.
  Broker-state tag `alpaca_shadow_b` → `live_state.alpaca_shadow_b.json` +
  `runs.alpaca_shadow_b.db`. This is the true control
  arm for the floor treatment: same environment, same session, only the
  floor differs.
- **Estimand (A) — floor effect (the causal claim, THIS protocol's decision
  rule)**: paired S-0.5 vs S-1.0, same session dates, same everything else.
  **P1 (deployed fraction)**: shadow vs shadow_b end-of-chain deployed
  fraction per session, paired by session date. **P2 (quality of the marginal
  entrants, frozen HERE, not by cross-reference)**: on the pre-veto scored
  cross-section common to both arms (same scorer, same session, so the
  cross-section is identical before the floor is applied), three sets: (a)
  marginal entrants — `mean + 0.5σ ≤ rank_score < mean + 1.0σ` (admitted by
  S-0.5, rejected by S-1.0); (b) incumbent admits — `rank_score ≥ mean +
  1.0σ` (admitted by both arms); (c) rejects — `rank_score < mean + 0.5σ`
  (rejected by both, sanity check). Forward returns SPY-relative, NET of the
  5 bps/side transaction-cost convention and the §1.1 tax convention,
  computed per §1.2 unit (ii)'s non-overlapping-block method — **enable-grade
  at the 20d horizon ONLY; the 60d horizon is descriptive-only (§1.2)**.
  **Quality bar (frozen)**: the marginal-entrant set's mean forward return
  must be (i) ≥ 0 net of the §1.1 cost/tax conventions, AND (ii) not more
  than the §2a non-inferiority margin below the incumbent set's mean, per the
  Tier 2 test below. "More deployed" with quality failing this bar = REJECT.
  Because both arms actually execute their admitted sets in real (isolated,
  simulated) broker state, **there is no hypothetical portfolio and no
  separate cost/tax model is needed for P1 or any arm-book-level outcome** —
  each arm's own fills carry the funnel's real simulated transaction cost and
  tax-drag mechanics automatically; P2's set-level quality outcome is the one
  score-defined quantity, and it names its net convention above rather than
  importing one. This dissolves the "cost/tax accounting for the
  hypothetical entrant portfolio" problem in the superseded design: no
  executed quantity is hypothetical.
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

**Infrastructure this requires (NOT YET BUILT — researched at r5 by direct
read-only inspection, not merely asserted; a prerequisite for this protocol
to run, tracked as follow-up work in the OWNING repos, not implemented in
this doc-only PR). Zero new umbrella capability: the treatment's correctness
depends on no umbrella change.**

*Verified existing interfaces (the second arm rides these):*

1. **The existing shadow invocation is already orchestrator-mediated.** The
   umbrella `scripts/daily_104.sh` Step-4 shadow block's DEFAULT path
   (`RQ_DAILY_RUNNER=multirepo`, `daily_104.sh:599`) does not call the
   umbrella runner directly; it runs
   `python -m renquant_orchestrator live-bridge --repo-dir $REPO_DIR
   --strategy renquant_104 --broker readonly-alpaca --once
   --strategy-config-name strategy_config.shadow.json`
   (`daily_104.sh:600-609`, wall-clock timeout 1800s, non-fatal to prod). The
   orchestrator bridge (`src/renquant_orchestrator/live_bridge.py:run_bridge`)
   bootstraps the pinned subrepos and hands off to the pinned entrypoint. The
   plain `-m live.runner` branch is the legacy fallback only.
2. **The config document already comes from the PINNED strategy-104 subrepo,
   not the umbrella**: `live_bridge._with_pinned_strategy_config` rewrites
   `--strategy-config-name X` into
   `--strategy-config-path <subrepos>/renquant-strategy-104/configs/X`, so
   S-1.0's CONFIG selection needs zero new code anywhere
   (`--strategy-config-name strategy_config.shadow_b.json`).
3. **The broker-state tag is the one axis NOT independently selectable
   today** (a real correctness constraint, not a style objection):
   `ReadOnlyBrokerWrapper.broker_name` is a hardcoded class attribute
   (`"alpaca_shadow"` — verified in both the umbrella's
   `live/broker_readonly.py:47` AND its as-yet-unwired port at
   `renquant_execution.readonly_broker.ReadOnlyBrokerWrapper`; `__init__`
   never sets it). Running a second `--broker readonly-alpaca` process today,
   even with `--strategy-config-name strategy_config.shadow_b.json`, would
   resolve `broker_name="alpaca_shadow"` and COLLIDE with S-0.5's state files.
   The runner threads `broker.broker_name` — deliberately not the CLI string —
   into the adapter and preflight (`live/runner.py:1153-1162`), and state
   paths derive from that tag in `kernel.state_paths`
   (`live_state.{tag}.json` + `runs.{tag}.db`, `ALLOWED_BROKERS`-guarded).
   Under the multirepo bridge, `kernel.state_paths` is ALIASED to the pinned
   renquant-pipeline module (`bootstrap_multirepo` aliases every
   `renquant_pipeline.kernel` submodule into `kernel.*`), so the allowlist
   that governs at runtime is renquant-pipeline's, not the umbrella copy's.

*Owning-repo additions (all outside the umbrella):*

1. **renquant-pipeline (one-line allowlist, both copies)**: add
   `"alpaca_shadow_b"` to `ALLOWED_BROKERS` in `state_paths.py` and its
   `kernel/state_paths.py` duplicate (both copies, per this project's known
   duplication pattern). Zero umbrella involvement; without this entry the
   pinned allowlist raises `ValueError` on the new tag (fail-closed by
   design).
2. **renquant-orchestrator (arm tag + invocation — the owning boundary for
   cross-repo orchestration; this is what makes the second arm runnable with
   ZERO umbrella change)**:
   (a) a bridge-owned arm-tag flag (e.g. `--bridge-broker-tag
   alpaca_shadow_b`), consumed and stripped by the bridge exactly like its
   existing `--bridge-bundle-output` flag, which sets
   `live.broker_readonly.ReadOnlyBrokerWrapper.broker_name =
   "alpaca_shadow_b"` after import and before handing off to
   `live.runner.main()`. This uses the bridge's ESTABLISHED interception
   surface — the same layer that already aliases `kernel.*` modules to the
   pinned pipeline and patches `RunnerAdapter.commit` for bundle capture —
   and is process-local (each arm runs in its own process; the class
   attribute is read at wrapper construction inside that process only).
   (b) the S-1.0 invocation itself: an orchestrator-owned scheduled entry
   (launchd plist / scheduled-jobs registry in THIS repo), sequenced after
   the existing Step-4 shadow run (the two arms run SEQUENTIALLY, never
   concurrently, against the same session's inputs), invoking the same
   pinned entrypoint pattern the existing shadow uses:
   `python -m renquant_orchestrator live-bridge --repo-dir $REPO_DIR
   --strategy renquant_104 --broker readonly-alpaca --once
   --strategy-config-name strategy_config.shadow_b.json
   --bridge-broker-tag alpaca_shadow_b`
   — non-fatal to the prod cycle, same timeout convention as Step-4.
   `daily_104.sh` is NOT modified.
3. **renquant-strategy-104 (config only)**:
   `configs/strategy_config.shadow_b.json` (the two-key delta defined in the
   arm list above) and a config-drift pin test alongside the existing
   `strategy_config.shadow.json` pin, verifying prod/golden stay untouched
   and shadow_b differs from shadow in EXACTLY the two frozen keys
   (`buy_floor_std_mult`, `live.preflight.strict`). This is the "config-only
   treatment PR" `strategy-104#52` will become, scoped strictly to this item
   — never bundled with protocol or broker-wrapper design, per Codex's
   sequencing objection.
4. **renquant-execution (durable ownership route, NOT a dependency of this
   protocol)**: parameterize `broker_name` in the already
   execution-repo-resident `readonly_broker.ReadOnlyBrokerWrapper`
   (`__init__(self, underlying, broker_name="alpaca_shadow")`), entirely
   within execution's own boundary. Cutting the umbrella
   `live/runner.py` `readonly-alpaca` branch over to import that port is a
   thin delegating call-site change of the same shape as
   `RenQuant#454`→`renquant-execution#25` (import the owning repo's
   capability, fail-closed fallback) — tracked as its own separately-gated
   follow-up PR under the adapter-migration program. When that cutover
   lands, item 2(a)'s bridge tag override can be retired in favor of the
   constructor parameter. **This protocol does not wait for it**: the bridge
   route (items 1-3) runs the experiment with zero umbrella change.

**Explicit boundary statement**: zero new umbrella code AND zero new umbrella
scheduling lines — item 2(b)'s invocation is orchestrator-owned, and the
Step-4 command it sequences after is already an orchestrator entrypoint. If
sequencing-after-Step-4 proved unachievable from an orchestrator-owned
scheduler entry (not expected), the single fallback would be ONE added
invocation line in `daily_104.sh`, carried as a time-bounded migration
exception per the #454 precedent (umbrella keeps a compatibility call-site
only, never a capability). That is the dispreferred fallback, not the plan.

**Disclosed cosmetic asymmetries (accepted, not patched, to keep the umbrella
at zero changes)**: `live/runner.py:446` prefixes the log/ntfy label
`[READONLY]` only for the exact tag `"alpaca_shadow"`, and
`runner.py:719/1010` derive the ntfy "SHADOW/HYPOTHETICAL (no live orders)"
framing from that label — the S-1.0 arm's notifications carry neither.
Neither affects any order path: the write-swallowing safety property belongs
to `ReadOnlyBrokerWrapper` itself, independent of the label. The operational
risk of an S-1.0 ntfy being misread as live activity is mitigated through the
EXISTING `RENQUANT_NTFY_TOPIC` env surface (`runner.py:1009`): the
orchestrator entry for S-1.0 sets a dedicated shadow topic. The
preflight-strictness asymmetry is NOT cosmetic and is closed config-side via
`live.preflight.strict = false` (see the S-1.0 arm definition above).

**Statistical power (r5 correction: the r4 draft's `N_eff ≈ N/h` was a
heuristic for a DIFFERENT problem — overlapping daily observations. §1.2 now
defines the correct unit for an h-day-forward estimand as a non-overlapping
`h`-day OUTCOME BLOCK; applying that unit here, the concrete session counts
below are unchanged from r4 but are now an EXACT count, not an approximation,
and the inference tool is a plain t-test/permutation-test on the block
sample, not HAC):**

Each `h`-day non-overlapping block (both arms run the SAME calendar sessions,
so a block is `h` consecutive trading days on which both S-0.5 and S-1.0
executed) yields exactly one paired block-return observation for estimand
(A). `N_eff` = the number of complete such blocks that have accumulated since
both arms went live — an exact count of independent data points, not a ratio.
Common econometric guidance treats fewer than ~5-10 independent blocks as
unreliable for any CI (t-test, permutation, or HAC — none of them manufacture
power a too-small independent sample doesn't contain).

- At `N=10` live sessions: `N_eff = floor(10/20) = 0` complete 20d blocks,
  `floor(10/60) = 0` complete 60d blocks. Zero complete blocks means zero
  independent data points — the superseded design's ≥10-session HAC test was
  attempting inference on a sample that, correctly counted, contains no
  complete non-overlapping outcome at all yet.
- Reaching a conservative `N_eff = 8` complete blocks (the low end of the
  "unreliable below" guidance, not a fully-powered target) requires
  `N = 8h` live sessions: **160 sessions (~8 months) for the 20d estimand,
  480 sessions (~2 years) for the 60d estimand.** A fully-powered target
  (`N_eff ≈ 30`) would need 600 and 1800 sessions respectively — multi-year,
  impractical for a shadow gate meant to unblock a breadth-bound deployment
  problem now.

**Resolution — two-tier reporting, not a single fixed-N verdict (Tier-1 kill
rules FROZEN, r5 point 4: "grossly adverse"/"sharply negative" were examples,
not thresholds, and are WITHDRAWN as discretionary):**
- **Tier 1 — mechanical early-REJECT check only.** From valid paired session
  10 onward, a script — not a judgment call — evaluates exactly TWO frozen
  kill conditions, declared on **NET** terms. (A single fixed N=10 look at
  the P2 forward-return point estimate is NOT coherent here and is not used:
  at session 10 zero 20d forward windows have matured, so no P2 estimate
  exists yet to inspect. The rules below only ever fire on data that exists,
  and neither is elastic — frozen numeric bound, frozen window definition,
  scripted evaluation, so there is no undisclosed choice of when or how to
  peek.)
  - **P1-kill (available from session 10)**: the treatment arm's (S-0.5)
    deployed fraction is below the control arm's (S-1.0) by MORE than **5pp
    absolute**, as the mean over any **5 consecutive valid paired sessions**
    ending at or after session 10. Deployed fraction is observed same-day
    (no maturation lag). The treatment relaxes admission; persistently
    deploying materially LESS than control is a mechanically adverse
    signature, whatever its cause.
  - **P2-kill (available once ≥ 3 matured blocks exist)**: the
    marginal-entrant NET mean 20d return — after the 5 bps/side cost
    convention and the §1.1 tax convention, SPY-relative — across all
    matured non-overlapping blocks is below **−300 bps**, with **at least 3
    matured blocks**. Gross returns are never used for this rule.
  Either condition ⇒ REJECT immediately, recorded with the triggering
  window/blocks in the verdict memo. No other outcome-based early-reject
  path exists.
- **Symmetric no-early-ENABLE (no optional stopping in either direction)**:
  an equally sized FAVORABLE early read — e.g. a +5pp 5-session deployed-
  fraction lift, or a +300 bps net marginal-entrant mean — authorizes
  NOTHING: not an early enable, not a shortened Tier 2, not a reduced block
  minimum. ENABLE can only be decided at full Tier-2 maturity. The only
  mid-run stops are the two kill rules above and the §2a safety-gate stop
  rule below (predeclared safety conditions, which can only produce
  REJECT/REDESIGN, never ENABLE).
- **No interim confidence intervals**: at Tier 1 no CI, DSR, or PBO is
  computed or reported (below 8 matured blocks a variance estimate is not
  trustworthy; a computed CI would be false precision). Tier-1 output is the
  two kill-rule booleans plus point estimates explicitly labeled
  "underpowered, not significance-tested".
- **Tier 2 — confirmatory read, matured-block-gated (replaces the fixed
  "+10 extension" rule)**: continue running both arms until **`N_eff ≥ 8`
  complete non-overlapping 20d blocks** accumulate — 160 valid sessions plus
  the final block's maturation, per the arithmetic above (≈ 200-225
  scheduled sessions under the 20% missingness bound). At that point compute
  the preregistered t-test / permutation-test on the block sample (§1.2 unit
  (ii); the P2 quality bar frozen above: marginal-entrant mean ≥ 0 net of
  cost AND not significantly below the incumbent set by more than the
  non-inferiority margin). This is the earliest point at which a
  RECOMMEND-ENABLE or a final (non-kill) REJECT verdict may be issued; a
  verdict issued before Tier 2's matured-block gate is not decision-grade
  regardless of what the point estimate shows. **If, at any scheduled review
  point, matured blocks < 8, the outcome is NO-ENABLE-BY-DEFAULT** with
  exactly one predeclared extension: keep running until the 8th block
  matures (no peeking-based stop, no parameter change). DSR is computed on
  this same block sample once `N_eff ≥ 8`, deflated for the 2 arms actually
  compared (S-0.5, S-1.0 — a small trials-correction, named explicitly since
  it's non-zero). **PBO does not apply to this comparison** (§1.2) — a
  single preregistered 2-arm paired design has no combinatorial train/test
  structure for CSCV to run over; PBO is not computed for estimand (A) or
  (B), and its absence is not a gap, it is the correct treatment of a 2-arm
  design per §1.2.
- **Non-inferiority margin (predeclared, Tier 2)**: the marginal-entrant set's
  mean forward return must not be more than 50 bps/period below the
  incumbent set's mean (one-sided non-inferiority margin, chosen as roughly
  the round-trip transaction-cost convention doubled — a conservative
  buffer against a treatment that is merely "not better" being mistaken for
  "materially worse"), in addition to the existing ≥0-net-of-cost bar. This
  gives the test a concrete margin rather than testing a point null the
  data can't resolve at any reachable N.
- **60d horizon: DESCRIPTIVE-ONLY for this experiment (per §1.2)** — reaching
  `N_eff = 8` complete 60d blocks would take 480 sessions (~2 years), out of
  scope for this protocol version. 60d block returns are reported in the
  verdict memo descriptively as they mature, are explicitly NOT enable-grade
  at this sample size, and no 60d significance test is computed. The Tier-2
  verdict covers the 20d horizon only and is labeled as such. (This demotes
  the prior draft's "60d verdict at 480 sessions" path.)

**Run-bundle fingerprint (closes the fingerprint-gap flagged in the r4 draft;
missingness rule added at r5)**: each shadow session for BOTH arms stamps:
(i) a config hash — sha256 of the resolved `strategy_config.shadow.json` /
`strategy_config.shadow_b.json` content; (ii) a model-artifact hash — reusing
the project's existing unified `model_content_sha256` /
`model_content_sha256_from_path` convention
(`renquant_pipeline.kernel.panel_pipeline.fingerprint_dispatch`), not a
bespoke scheme; (iii) a calibrator hash (same unified convention — the
calibrator is a separate artifact with its own recurring-mismatch history in
this project); (iv) the broker-state identity tag (`alpaca_shadow` /
`alpaca_shadow_b`); (v) the pin SHAs of `renquant-strategy-104`,
`renquant-pipeline`, AND `renquant-execution` at run time; (vi) the frozen
data/feature manifest hash used by that session's scoring pass (the same
manifest SHA convention as §1's freeze-rule commit); (vii) this orchestrator
repo's own commit SHA — the commit of the invoking bridge (so the protocol
version a session was run under is unambiguous even after this doc changes
again).

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
is void and does not count toward `N_eff` (it is not patched with a partial
window); if cumulative excluded pairs exceed 20% of all session-pairs
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
  repo), issued only at Tier 2 maturity (`N_eff ≥ 8` complete 20d blocks,
  per the matured-block gate above). RECOMMEND-ENABLE iff ALL of:
  1. **P1**: the daily paired deployed-fraction mean difference > 0 AND its
     NW (§1.2 unit (i) lag rule, capped at 10) 95% CI excludes 0;
  2. **P2, 20d horizon ONLY** (60d is descriptive-only, never gating): the
     block-level net marginal-entrant mean passes the ≥ 0-net-of-cost bar
     AND the one-sided block-level test does not find the marginal set worse
     than the incumbent set beyond the 50 bps non-inferiority margin;
  3. every §2a gate above is green on both arms for every counted
     session-pair;
  4. run-bundle fingerprints are clean on every counted session-pair, the
     missingness bounds are not breached, and zero treatment-fingerprint
     drift occurred.
  Anything less: REJECT — or, where the only failure is matured blocks < 8,
  the honestly-underpowered NO-ENABLE-BY-DEFAULT with its single predeclared
  extension (keep running until the 8th block matures; no other extension
  mechanism exists).
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
  `buy_floor_std_mult` (or simply stop running the S-1.0 arm). Blast radius is
  zero by construction: both arms run on isolated shadow broker state
  (`alpaca_shadow` / `alpaca_shadow_b`) and place no live orders.

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
    30-trading-day embargo (this project's existing WF-gate embargo convention
    on 60d-horizon labels), followed by the EVALUATION range (remaining
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
    forward-window overlap in a same-day realized return. For any h-day-forward
    estimand computed over that range (§1.2 unit (ii) — e.g. §2a's P2), slice
    the EVALUATION range into non-overlapping `h`-day OUTCOME blocks (a pure
    accounting unit for the estimand, separate from the continuous portfolio
    simulation underneath it) and use `N_eff` = the actual number of complete
    such blocks, per §1.2.
  - **Concretely**, with ~497 total frozen sessions (the #442/cap-grid freeze
    record's scale): tuning ≈ 249 sessions, 30-day embargo, evaluation ≈ 218
    sessions (497 − 249 − 30). Within that 218-session evaluation range:
    20d non-overlapping outcome blocks: `N_eff = floor(218/20) = 10`. 60d
    non-overlapping outcome blocks: `N_eff = floor(218/60) = 3`. Against
    §1.2's frozen enable-grade minimum of 8 matured blocks, the 20d estimand
    clears the floor at `N_eff = 10` — enable-grade, but reported with its
    wide CI and explicitly labeled low-power — and the rule binds if the
    frozen list yields fewer than 8 (the verdict is then
    NO-ENABLE-BY-DEFAULT; replay history cannot be "collected" like live
    sessions, so the only extension is a new frozen session list under a new
    protocol version). The **60d estimand, at `N_eff = 3`, cannot support
    ANY significance test on this frozen historical pool** — it is
    DESCRIPTIVE-ONLY (per §1.2): report the 60d point estimate
    directionally, indefinitely, unless a future protocol version re-freezes
    a longer WF-cut history. This is an honest capacity limit of the
    available ~497-session pool, not something a smarter estimator can fix.
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
non-overlapping-block method (this is an h-day-forward estimand, the same
class as §2a's P2 — subject to the same r5 correction, not the daily-return
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
