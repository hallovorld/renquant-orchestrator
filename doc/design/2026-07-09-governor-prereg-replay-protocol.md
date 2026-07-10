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

## 1.2 Statistical contract (frozen — valid units of inference, r5 point 3)

- **Daily paired series** (deployed fraction; realized daily portfolio
  returns): the observation is the session. Neither quantity carries a
  forward-looking window — both are observed same-day — so daily HAC/
  Newey-West inference with **lag ≤ 10 (frozen)** is valid on these series.
  All primary paired-mean-advantage claims live here.
- **Forward-horizon estimands**: enable-grade ONLY at the **20d horizon** and
  ONLY on matured, complete, **NON-OVERLAPPING** 20d windows — one window =
  one unit of inference (mechanical constructions in §2 and §2a). A minimum
  of **8 matured units (frozen)** is required for any enable-grade
  forward-return verdict; with fewer, the outcome is NO-ENABLE-BY-DEFAULT
  with the predeclared extension defined where each experiment is specified.
  Overlapping daily-sampled forward returns are never used for confirmatory
  inference: HAC corrects the bias of overlap, it does not manufacture
  independent observations the data lacks.
- **60d horizon: DESCRIPTIVE-ONLY everywhere in this protocol.** At every
  planned sample size it yields fewer than 8 non-overlapping units; it is
  reported in memos, never promotion-gating, and no 60d significance test is
  computed.
- **Promotion bar per replay comparison** (daily paired series): paired mean
  advantage point estimate ≥ +1 bp/day AND NW(lag ≤ 10) 95% CI excluding 0
  AND DSR ≥ 0.95 AND PBO ≤ 0.10 (the harness's existing significance pass,
  computed on the paired daily REALIZED-return series). **DSR/PBO are
  REPLAY-ONLY metrics**: they are computed only on daily paired
  realized-return series in §2 Phase-1/Phase-2 historical replay, never on
  forward-window estimands, and never applied to the §2a live-shadow
  experiment at any tier.
- Marginal-capital estimand: same daily-series bar (CI excluding 0) on the
  paired difference series defined in §3.
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

- **Arm S-0.5 (existing shadow, treatment)**: `configs/strategy_config.shadow.json`,
  frozen values restated here normatively (this doc, not `strategy-104#52`, is
  the contract — see the frozen experiment contract below): scorer
  `hf_patchtst`, Kelly `fractional` 0.5 / `max_concentration` 0.35, BULL_CALM
  `max_position_pct` 0.15, `one_share_floor_enabled` true,
  `buy_floor = "adaptive_mean_std"`, `buy_floor_std_mult = 0.5`. Broker-state
  tag `alpaca_shadow` (existing) → `live_state.alpaca_shadow.json` +
  `runs.alpaca_shadow.db`.
- **Arm S-1.0 (NEW, control)**: `configs/strategy_config.shadow_b.json` — a
  clone of `shadow.json` differing in exactly TWO functional keys (plus inert
  `_reason` annotation strings):
  1. `ranking.panel_scoring.buy_floor_std_mult = 1.0` (`buy_floor` stays
     `adaptive_mean_std`, matching S-0.5) — the only key that differs in
     TREATMENT terms;
  2. `live.preflight.strict = false` — an arm-plumbing equivalence shim, NOT
     a treatment delta: the umbrella runner's preflight-strictness special
     case keys on the exact broker tag `"alpaca_shadow"`
     (`live/runner.py:461`, `shadow_strict` default false), so the S-1.0 arm,
     which runs under tag `alpaca_shadow_b`, must reproduce the identical
     non-strict preflight behavior through the runner's EXISTING config
     surface (`config["live"]["preflight"]["strict"]`, `runner.py:457-465`)
     rather than through new umbrella code. Without this key the two arms
     would have asymmetric preflight abort semantics.
  Every other key (scorer, Kelly, regime cap, one-share floor, sector caps,
  slots) is IDENTICAL to S-0.5, enforced by a config-drift pin test. Broker-
  state tag `alpaca_shadow_b` → `live_state.alpaca_shadow_b.json` +
  `runs.alpaca_shadow_b.db`. This is the true control arm for the floor
  treatment: same environment, same session, only the floor differs.
- **Estimand (A) — floor effect (the causal claim, THIS protocol's decision
  rule)**: paired S-0.5 vs S-1.0, same session dates, same everything else.
  P1 (deployed fraction) and P2 (20d forward-return quality of the
  marginal-entrant set; 60d descriptive-only) are both computed on this pair;
  both are DEFINED IN FULL in the frozen experiment contract below (no
  cross-repo import). For P1 and any arm-book-level outcome, because both
  arms actually execute their admitted sets in real (isolated, simulated)
  broker state, **there is no hypothetical portfolio and no separate cost/tax
  model is needed** — each arm's own fills carry the funnel's real simulated
  transaction cost and tax-drag mechanics automatically. P2's set-level
  quality outcome is computed on score-defined sets and therefore carries the
  DECLARED net convention (5 bps/side + §1.1 tax), stated exactly in the
  frozen contract. This dissolves the "cost/tax accounting for the
  hypothetical entrant portfolio" problem in the superseded design: no
  executed quantity is hypothetical, and the one set-level estimand names its
  cost convention up front.
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

**Implementation contract — zero new umbrella capability (r5 point 1; the
prior draft's infrastructure items 2-4 required new umbrella broker/runner/
daily_104.sh code and are WITHDRAWN — the umbrella is a deprecated pin
consumer, and the treatment's correctness must not depend on new umbrella
code). All facts below verified by direct read-only inspection, 2026-07-10:**

1. **The existing shadow invocation is already orchestrator-mediated.** The
   umbrella `scripts/daily_104.sh` Step-4 shadow block's DEFAULT path
   (`RQ_DAILY_RUNNER=multirepo`, `daily_104.sh:599`) does not call the
   umbrella runner directly; it runs
   `python -m renquant_orchestrator live-bridge --repo-dir $REPO_DIR
   --strategy renquant_104 --broker readonly-alpaca --once
   --strategy-config-name strategy_config.shadow.json`
   (`daily_104.sh:600-609`, wall-clock timeout 1800s, non-fatal to prod).
   The orchestrator bridge (`src/renquant_orchestrator/live_bridge.py:
   run_bridge`) bootstraps the pinned subrepos, then hands off to the pinned
   entrypoint. The plain `-m live.runner` branch is the legacy fallback only.
2. **The config document already comes from the PINNED strategy-104 subrepo,
   not the umbrella.** `live_bridge._with_pinned_strategy_config` rewrites
   `--strategy-config-name X` into
   `--strategy-config-path <subrepos>/renquant-strategy-104/configs/X`.
   A second config file is therefore reachable through this EXISTING surface
   with zero code change anywhere:
   `--strategy-config-name strategy_config.shadow_b.json`.
3. **Broker-state isolation mechanism (corrected from the prior draft — the
   tag is NOT a config key).** `--broker readonly-alpaca` constructs
   `ReadOnlyBrokerWrapper`, whose `broker_name` is a hardcoded CLASS
   attribute `"alpaca_shadow"` (`live/broker_readonly.py:47`; `__init__`
   never sets it, so a class-level override binds every instance constructed
   afterwards in that process). The runner threads `broker.broker_name` —
   deliberately not the CLI string — into the adapter and preflight
   (`live/runner.py:1153-1162`), and state paths derive from that tag in
   `kernel.state_paths` (`live_state.{tag}.json` + `runs.{tag}.db`, guarded
   by the `ALLOWED_BROKERS` allowlist). Under the multirepo bridge,
   `kernel.state_paths` is ALIASED to the pinned renquant-pipeline module
   (`bootstrap_multirepo` aliases every `renquant_pipeline.kernel` submodule
   into `kernel.*`), so the allowlist that governs at runtime is
   renquant-pipeline's, not the umbrella copy's.

**What the second arm requires — all outside the umbrella (NOT YET BUILT; a
prerequisite for this protocol to run, tracked as follow-up work, not
implemented in this doc-only PR):**

- **renquant-strategy-104 (config only)**: `configs/strategy_config.shadow_b.json`
  (defined above) + a config-drift pin test alongside the existing
  `strategy_config.shadow.json` pin, verifying prod/golden stay untouched and
  shadow_b differs from shadow in EXACTLY the two frozen keys
  (`buy_floor_std_mult`, `live.preflight.strict`). This is the config-only
  treatment PR `strategy-104#52` becomes — never bundled with protocol
  design, per Codex's sequencing objection.
- **renquant-pipeline (one-line allowlist, both copies)**: add
  `"alpaca_shadow_b"` to `ALLOWED_BROKERS` in `state_paths.py` AND its
  `kernel/state_paths.py` duplicate (both copies, per this project's known
  duplication pattern). The pipeline owns the state-path convention; without
  this entry the pinned allowlist raises `ValueError` on the new tag
  (fail-closed by design).
- **renquant-orchestrator (arm tag + invocation — the owning boundary for
  cross-repo orchestration)**:
  1. a bridge-owned arm-tag flag (e.g. `--bridge-broker-tag alpaca_shadow_b`),
     consumed and stripped by the bridge exactly like its existing
     `--bridge-bundle-output` flag, which sets
     `live.broker_readonly.ReadOnlyBrokerWrapper.broker_name =
     "alpaca_shadow_b"` after import and before handing off to
     `live.runner.main()`. This uses the bridge's ESTABLISHED interception
     surface — the same layer that already aliases `kernel.*` modules to the
     pinned pipeline and patches `RunnerAdapter.commit` for bundle capture —
     and is process-local (each arm runs in its own process; the class
     attribute is read at wrapper construction inside that process only).
     Zero umbrella lines.
  2. the S-1.0 invocation itself: an orchestrator-owned scheduled entry
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

**Explicit boundary statement**: zero new umbrella code AND zero new umbrella
scheduling lines — the correctness of the treatment does not depend on any
umbrella change. If sequencing-after-Step-4 proved unachievable from an
orchestrator-owned scheduler entry (not expected: the Step-4 command is
already an orchestrator entrypoint, so ordering is a scheduling concern the
orchestrator owns), the single fallback would be ONE added invocation line in
`daily_104.sh`, carried as a time-bounded migration exception per the #454
precedent (umbrella keeps a compatibility call-site only, never a
capability). That is the dispreferred fallback, not the plan.

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

**Frozen experiment contract (self-contained — r5 point 2). Everything
decision-critical is frozen HERE, in this orchestrator protocol.
`strategy-104#52` is config-only and must conform to this section; it is
cited as provenance, never as a normative dependency. A later config PR
cannot alter this experiment contract by changing a cross-reference — any
divergence between a running arm's resolved config hash and the hash frozen
at experiment start is treatment-fingerprint drift and VOIDS the experiment
(rule below).**

*Estimand definitions (frozen):*

- **P1 — deployed fraction (PRIMARY)**: end-of-chain deployed fraction per
  arm per session; the estimand is the daily PAIRED DIFFERENCE (S-0.5 minus
  S-1.0) over valid paired sessions (inclusion rule below).
- **P2 — marginal-entrant quality**: on each valid session's pre-veto
  calibrated cross-section — IDENTICAL for both arms by construction (same
  scorer, same model artifact, same data snapshot; only the floor differs;
  the bundle's model/calibrator/manifest shas enforce this per session) —
  define three sets:
  (a) **marginal entrants**: `mean + 0.5σ ≤ rank_score < mean + 1.0σ`;
  (b) **incumbents**: `rank_score ≥ mean + 1.0σ`;
  (c) **rejects**: `rank_score < mean + 0.5σ` (ordering sanity check only).
  Outcome variable: 20-trading-day forward return, SPY-relative, **NET** of
  the 5 bps/side transaction-cost convention and the §1.1 tax convention
  (short 50% / long 32% on the realized leg). The 60d horizon is
  DESCRIPTIVE-ONLY per §1.2.
- **Estimand (B)** (S-1.0 vs actual production): diagnostic only, exactly as
  defined above — never part of the ENABLE/REJECT rule.

*Safety gates (exact frozen tolerances; evaluated on BOTH arms, every counted
session):*

| Gate | Frozen tolerance |
|---|---|
| Per-name concentration | each arm's book ≤ its OWN configured caps: BULL_CALM `max_position_pct` 0.15 and Kelly `max_concentration` 0.35 (identical in both arms; the production 12% cap is untouched by this experiment) |
| Sector concentration | ≤ 35% weight per sector AND ≤ 6 names per sector |
| Session turnover | each arm ≤ 2× the SAME session's production turnover |
| Drawdown | each arm's MDD over the evaluation window ≤ 0.30 (regime `drawdown_halt_pct` 0.35 with ≥ 5pp headroom) |
| Fail-closed contract | a fingerprint/contract failure is never counted as an observation (inclusion rule below) |

Stop rule (live-shadow venue): immediate stop on any gate breach; the breach
is recorded and the verdict pathway is REJECT/REDESIGN. A safety stop can
never produce an early ENABLE — this asymmetry is predeclared and
safety-dominant, distinct from the outcome-based kill rules in Tier 1 below.
No tolerance may be relaxed mid-run.

*Paired-session inclusion rule (exact):* a session date is COUNTED iff ALL of:
(i) both arms ran to completion on that date; (ii) both per-session bundles
are present and complete; (iii) every fingerprint in both bundles matches the
values frozen at experiment start; (iv) both arms' bundles record the SAME
model-artifact sha, calibrator sha, and data/feature manifest sha for that
session (the arms must have scored the same world); (v) neither arm hit a
preflight abort, timeout, or contract failure
(`panel_scorer_config_mismatch`-class fail-closed events included). **A
failure of any condition in EITHER arm invalidates the session in BOTH arms**
— a fingerprint mismatch is never silently excluded from one arm's count
alone, and every invalidated session is logged with its reason.

*Bounded missingness and drift (VOID conditions, frozen):*
- If invalidated sessions exceed **20% of scheduled sessions** (scheduled =
  every trading day from experiment start through the evaluation point), the
  experiment is **VOID** and restarts under a new protocol version.
- If ANY treatment-fingerprint drift occurs — the resolved config hash of
  EITHER arm changes mid-run relative to its frozen-at-start hash — the
  experiment is **VOID** and restarts under a new protocol version. A config
  change never reinterprets the experiment; it terminates it.

*Per-session run bundle (both arms, every session — frozen field list):*
(i) resolved config hash — sha256 of the arm's resolved
`strategy_config.shadow.json` / `strategy_config.shadow_b.json` content (BOTH
arms' hashes recorded in each session's record); (ii) model-artifact sha —
the project's existing unified `model_content_sha256` /
`model_content_sha256_from_path` convention
(`renquant_pipeline.kernel.panel_pipeline.fingerprint_dispatch`), not a
bespoke scheme; (iii) calibrator sha (same unified convention); (iv) the
broker-state tag (`alpaca_shadow` / `alpaca_shadow_b`); (v) pin shas of
renquant-strategy-104, renquant-pipeline, AND renquant-execution at run time;
(vi) the renquant-orchestrator commit sha of the invoking bridge; (vii) the
data/feature manifest sha of the session's input data.

**Units of inference and statistical power (r5 point 3 — replaces the prior
`N_eff ≈ N/h` heuristic framing with predeclared valid units; same contract
as §1.2):**

- **P1 (PRIMARY)**: the unit is the valid paired SESSION. Deployed fraction
  carries no forward-looking window, so the daily paired-difference series
  supports valid daily inference: paired mean with Newey-West SE at
  **lag ≤ 10 (frozen)**, 95% CI.
- **P2 — enable-grade at the 20d horizon ONLY; the unit is one matured,
  complete, NON-OVERLAPPING 20-valid-session window.** Construction
  (mechanical, no discretion): partition the chronological valid-paired-
  session stream into consecutive disjoint windows of 20 valid sessions
  (final partial window dropped); marginal entrants and incumbents are
  assigned to the window containing their admission session; a window's unit
  value = (equal-weighted mean net 20d forward return of its marginal
  entrants) − (same for its incumbents); a unit is MATURED when every
  constituent entry's 20d forward window has fully elapsed. Adjacent units'
  outcome spans share at most a 19-session seam (an entry admitted late in
  window k matures inside window k+1's span); this residual seam dependence
  is handled with a Newey-West lag-1 correction on the UNIT-level series
  (frozen) and is second-order next to the daily-overlap problem this
  construction removes.
- **Declared minimum and planned duration**: enable-grade requires **≥ 8
  matured units (frozen, = §1.2's minimum)**. 8 units × 20 valid sessions
  + ~20 sessions of final-unit maturation ≈ 180 valid sessions; under the
  20% missingness bound that is ≈ 200-225 scheduled sessions (~10-11
  months). This is the honest cost of a 20d forward-return claim at this
  breadth; no shortcut is declared.
- **60d horizon: DESCRIPTIVE-ONLY.** The planned duration yields at most ~3
  non-overlapping matured 60d units — below any defensible minimum. 60d
  numbers appear in the verdict memo descriptively, are explicitly NOT
  enable-grade at this sample size, and no 60d significance test is computed.
  (The prior draft's "~480 sessions for a 60d verdict" path is out of scope
  for this protocol version.)
- **HONESTLY-UNDERPOWERED rule (frozen)**: if, at any scheduled review point,
  matured non-overlapping units < 8, the outcome is **NO-ENABLE-BY-DEFAULT**,
  with exactly one predeclared extension: both arms CONTINUE running until 8
  matured units exist — no peeking-based stop, no parameter change, no
  re-randomization — and the verdict is issued at the first review point at
  or after the 8th unit matures. No other extension mechanism exists.
- **DSR / PBO: not applied to this shadow experiment at any tier** (declared
  REPLAY-ONLY metrics per §1.2) — at the ~8-12 units this experiment can
  reach they would be false precision.
- **Non-inferiority margin (restated at unit level, unchanged value)**: the
  P2 unit-level mean must not be below zero by more than **50 bps/period**
  (one-sided margin, ≈ the round-trip transaction-cost convention doubled),
  in addition to the ≥ 0-net-of-cost point requirement.

**Two-tier reporting — Tier-1 kill rules FROZEN (r5 point 4: "grossly
adverse" / "sharply negative" were examples, not thresholds, and are
WITHDRAWN as discretionary; the rules below are exact, mechanical, and
declared gross-vs-net):**

- **Tier 1 — mechanical early-REJECT check only.** From valid paired session
  10 onward (the ≥10-session trigger retained from the superseded design), a
  script — not a judgment call — evaluates exactly TWO frozen kill
  conditions, both on **NET** terms:
  - **P1-kill**: the treatment arm's (S-0.5) deployed fraction is below the
    control arm's (S-1.0) by MORE than **5pp absolute**, as the mean over any
    **5 consecutive valid paired sessions** ending at or after session 10.
    (The treatment relaxes admission; persistently deploying materially LESS
    than control is a mechanically adverse signature, whatever its cause.)
  - **P2-kill**: the marginal-entrant NET mean 20d return — after the
    5 bps/side cost convention and the §1.1 tax convention, SPY-relative —
    across all matured units is below **−300 bps**, with **at least 3 matured
    units** (units as defined above). Gross returns are never used for this
    rule.
  Either condition ⇒ REJECT immediately, recorded with the triggering
  window/units in the verdict memo. No other outcome-based early-reject path
  exists.
- **Symmetric no-early-ENABLE (no optional stopping in either direction)**:
  an equally sized FAVORABLE early read — e.g. a +5pp 5-session deployed-
  fraction lift, or a +300 bps net marginal-entrant mean — authorizes
  NOTHING: not an early enable, not a shortened Tier 2, not a reduced unit
  minimum. ENABLE can only be decided at full Tier-2 maturity (≥ 8 matured
  units). The only mid-run stops are the two kill rules above and the
  safety-gate stop rule in the frozen contract (predeclared safety
  conditions, which can only produce REJECT/REDESIGN, never ENABLE).
- **No interim confidence intervals**: at Tier 1 no HAC CI is computed or
  reported — below the unit minimum a CI would be false precision, not
  honest uncertainty. Tier-1 output is the two kill-rule booleans plus point
  estimates explicitly labeled "underpowered, not significance-tested".
- **Tier 2 — confirmatory verdict at ≥ 8 matured units**: compute the
  preregistered tests — P1: daily paired NW(lag ≤ 10) mean + 95% CI; P2
  (20d only): unit-level mean with NW(lag 1) against the ≥ 0-net bar and the
  50 bps non-inferiority margin. This is the earliest point at which
  RECOMMEND-ENABLE or a final (non-kill) REJECT may be issued; a verdict
  issued earlier is not decision-grade regardless of the point estimates.

**Decision rule (self-contained — supersedes #52 §9 for the floor-effect
claim; the verdict-as-memo / separate-live-enablement-PR / single-config-
revert structure is retained as restated HERE, not by reference):**
RECOMMEND-ENABLE iff ALL of the following hold at Tier-2 maturity (≥ 8
matured units):
1. **P1**: daily paired deployed-fraction mean difference > 0 AND its
   NW(lag ≤ 10) 95% CI excludes 0;
2. **P2 (20d only)**: unit-level net marginal-entrant mean ≥ 0 AND the
   one-sided unit-level test does not find the marginal set worse than the
   incumbent set beyond the 50 bps non-inferiority margin;
3. every safety gate in the frozen contract is green on both arms for every
   counted session;
4. run-bundle fingerprints are clean on every counted session, invalidated
   sessions ≤ 20% of scheduled, and zero treatment-fingerprint drift
   occurred.
Anything less: REJECT — or, where the only failure is units < 8, the
honestly-underpowered NO-ENABLE-BY-DEFAULT with its predeclared extension.
The verdict is a recommendation memo (`doc/research/`); live enablement is a
SEPARATE, gated PR (production `buy_floor_std_mult` flip carrying the memo, a
pre-registration gate, and Codex review — never bundled with this protocol);
rollback is a single config revert; the shadow arms place zero live orders.
Estimand (B) is reported alongside as a scorer-transfer-risk diagnostic but
is NOT a gating condition for this verdict — it gates whether that SEPARATE
future live-enablement PR may cite this shadow evidence as externally valid
for production, which is that future PR's decision to make, not this
protocol's.
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
  - **Units of inference and aggregation (r5 point 3 — the r4 scheme
    [per-block Newey-West on each block's own series with a 60d-horizon
    overlap structure, pooled across ~4 evaluation blocks by inverse-variance
    fixed effects] is WITHDRAWN as statistically incoherent: a 60-trading-day
    block contains ~1 independent 60d-forward outcome; forward windows at a
    block boundary leak into the next block, so the claimed cross-block
    independence was false; and NW on n=60 for a 60d horizon cannot produce a
    reliable HAC CI or valid DSR/PBO promotion evidence).** The predeclared
    replacement:
    - (i) **PRIMARY estimand — daily deployed-fraction paired difference**:
      one observation per evaluation-subset session (deployed fraction has no
      forward window), pooled chronologically across evaluation blocks into
      one daily paired series; NW **lag ≤ 10 (frozen)** is valid on this
      series; report paired mean + 95% CI. The paired daily REALIZED-return
      series gets the identical treatment (also daily, no forward window).
    - (ii) **Forward-return quality — 20d horizon ONLY, non-overlapping
      window units**: each 60-day evaluation block partitions exactly into
      **3 disjoint 20-day windows** (60 = 3 × 20; no window spans a block
      boundary by construction). One unit = the paired difference of the two
      arms' compounded returns over one window. Planned yield: ~4 evaluation
      blocks × 3 = **~12 units** (the exact count is whatever the frozen
      session list produces). Inference: unit-level mean with NW lag 1
      (adjacent-unit seam dependence); enable-grade requires **≥ 8 matured
      units** (§1.2's declared minimum) — the planned corpus clears it, but
      the rule binds if the frozen list yields fewer.
    - (iii) **60d horizon — DESCRIPTIVE-ONLY**: one non-overlapping 60d
      window per block ⇒ ~4 units < 8 ⇒ never enable-grade at this corpus
      size. No 60d significance test is computed or cited for promotion.
    - (iv) **DSR/PBO**: computed by `compute_significance_verdicts` on the
      pooled daily paired REALIZED-return series of (i) only — valid daily
      units — never on forward-window estimands (§1.2).
    - (v) **Honestly-underpowered rule (replay)**: if the frozen list yields
      < 8 matured 20d units, the forward-quality estimand is NOT enable-grade
      and the replay verdict is NO-ENABLE-BY-DEFAULT; replay history cannot
      be "collected" like live sessions, so the only extension is a new
      frozen session list under a new protocol version.
  - Concretely with ~497 total frozen sessions (the #442/cap-grid freeze
    record's scale) and 60-day blocks: roughly 8 blocks total, ~4 tuning / ~4
    evaluation after the embargo — yielding ~240 daily paired observations,
    ~12 twenty-day units, and ~4 sixty-day (descriptive-only) units in
    evaluation. The exact counts are whatever the frozen session list and
    this mechanical rule produce; nothing is hand-picked.
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
