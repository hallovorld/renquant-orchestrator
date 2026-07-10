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
    day. Ordinary daily-lag HAC/Newey-West (short lag, e.g. Newey-West with
    `lag = floor(4*(T/100)^(2/9))`, the standard Newey-West 1994 plug-in rule) is
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
  ≥ 0 (net of cost) AND, ONLY once `N_eff` is large enough for the CI itself to
  be trustworthy (§2a Tier 2's matured-block gate), a t-test/permutation-test CI
  excluding a value below the predeclared non-inferiority margin. Below that
  `N_eff` gate, report the point estimate as directional-only — no CI, no
  DSR/PBO (both require a stable variance estimate that a handful of blocks
  cannot supply) — per §2a Tier 1.
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
  **P1 (deployed fraction)**: shadow vs shadow_b end-of-chain deployed
  fraction per session, paired by session date. **P2 (quality of the marginal
  entrants, frozen HERE, not by cross-reference)**: on the pre-veto scored
  cross-section common to both arms (same scorer, same session, so the
  cross-section is identical before the floor is applied), three sets: (a)
  marginal entrants — `mean + 0.5σ ≤ rank_score < mean + 1.0σ` (admitted by
  S-0.5, rejected by S-1.0); (b) incumbent admits — `rank_score ≥ mean +
  1.0σ` (admitted by both arms); (c) rejects — `rank_score < mean + 0.5σ`
  (rejected by both, sanity check). Forward returns at 20d and 60d horizons,
  SPY-relative, computed per §1.2 unit (ii)'s non-overlapping-block method.
  **Quality bar (frozen)**: the marginal-entrant set's mean forward return
  must be (i) ≥ 0 net of the §1.1 cost/tax conventions, AND (ii) not more
  than the §2a non-inferiority margin below the incumbent set's mean, per the
  Tier 2 test below. "More deployed" with quality failing this bar = REJECT.
  Because both arms actually execute their admitted sets in real (isolated,
  simulated) broker state, **there is no hypothetical portfolio and no
  separate cost/tax model is needed for this estimand** — each arm's own
  fills carry the funnel's real simulated transaction cost and tax-drag
  mechanics automatically. This dissolves the "cost/tax accounting for the
  hypothetical entrant portfolio" problem in the superseded design: nothing
  here is hypothetical.
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

**Infrastructure this requires (NOT YET BUILT — researched at r5, not merely
asserted; a prerequisite for this protocol to run, tracked as follow-up work
in the OWNING repos, not implemented in this doc-only PR):**

Direct inspection (r5) of the actual multi-repo boundary, rather than
assuming one: `renquant-pipeline`'s `state_paths.py` (`ALLOWED_BROKERS`) is
already a generic, broker-agnostic path-construction allowlist — adding
`"alpaca_shadow_b"` there is a one-line pipeline-repo change, no new
capability. The state-path CONSUMER, however, is genuinely different: the
umbrella's `live/runner.py` already exposes a generic `--strategy-config-name`
override (so S-1.0's CONFIG selection needs zero new umbrella code — the
existing flag already does this), but the BROKER-STATE tag is a separate axis
that is NOT independently selectable today: `ReadOnlyBrokerWrapper.broker_name`
is a hardcoded class attribute (`"alpaca_shadow"`, verified in both the
umbrella's `live/broker_readonly.py` AND its as-yet-unwired port at
`renquant_execution.readonly_broker.ReadOnlyBrokerWrapper` — same hardcoded
value in both places). Running a second `--broker readonly-alpaca` process
today, even with `--strategy-config-name strategy_config.shadow_b.json`,
would still resolve `broker_name="alpaca_shadow"` and COLLIDE with S-0.5's
existing state files (`live_state.alpaca_shadow.json` /
`runs_alpaca_shadow.db`) — a real correctness bug, not a style objection.
**No existing multi-repo interface supports a second broker tag without ANY
code change** — confirmed by inspection, not assumed. The minimal owning-repo
addition, per the `RenQuant#454`→`renquant-execution#25` precedent (move
umbrella-resident logic to its owning repo rather than extend it in place):
1. `renquant-pipeline` `state_paths.py` (and its `kernel/state_paths.py`
   duplicate — both copies, per this project's known duplication pattern):
   add `"alpaca_shadow_b"` to `ALLOWED_BROKERS`. Zero umbrella involvement.
2. `renquant-execution`'s `readonly_broker.ReadOnlyBrokerWrapper` (already
   execution-repo-resident, currently unwired into the live runner): make
   `broker_name` a constructor parameter (`__init__(self, underlying,
   broker_name="alpaca_shadow")`), entirely within execution's own repo
   boundary — zero orchestrator/umbrella code touched for this change.
3. **Separate prerequisite, explicitly out of THIS protocol's scope**: cutting
   `live/runner.py`'s `readonly-alpaca` branch over to import
   `ReadOnlyBrokerWrapper` from `renquant_execution.readonly_broker` (now
   parameterizable) instead of its local hardcoded copy, and adding a second
   CLI invocation for S-1.0. This is a thin delegating call-site change of the
   SAME shape as `RenQuant#454` (import the owning repo's capability, fail-
   closed fallback to the existing single-arm behavior if the import fails) —
   not a new umbrella capability, but it is still a change to umbrella code,
   so it is tracked as its own follow-up PR under the adapter-migration
   program, gated on its own review, and is NOT a design decision this
   protocol PR makes. This protocol documents what that follow-up PR must
   satisfy (parameterized broker_name, isolated `alpaca_shadow_b` state, fail-
   closed to single-arm behavior on any wiring failure); it does not build it.
4. `strategy-104`: add `configs/strategy_config.shadow_b.json` (byte-for-byte
   clone of `shadow.json` except `buy_floor_std_mult = 1.0`) and a config-
   drift pin test alongside the existing `strategy_config.shadow.json` pin,
   verifying prod/golden stay untouched and shadow_b differs from shadow
   ONLY in `buy_floor_std_mult`. This is the "config-only treatment PR"
   `strategy-104#52` will become, scoped strictly to item 4 — never bundled
   with protocol or broker-wrapper design, per Codex's sequencing objection.

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

**Resolution — two-tier reporting, not a single fixed-N verdict:**
- **Tier 1 — early operational read, a SINGLE predeclared look at exactly
  `N = 10` live sessions (frozen HERE at this session count; NOT a repeated or
  continuously-monitored check — a single predeclared inspection point is not
  optional stopping, since the analyst cannot choose when to look; the
  optional-stopping failure mode Codex flagged requires either an undisclosed
  choice of when to peek or a vague, elastic threshold — both are closed by
  fixing both the session count AND the numeric bound below, in advance)**:
  at exactly N=10, report estimand (A)'s P2 (marginal-entrant mean forward
  return, NET of the §1.1 transaction-cost and tax-drag conventions — same
  net-of-cost basis as the Tier-2 bar below, for consistency) as a
  DIRECTIONAL POINT ESTIMATE ONLY — no CI, no DSR/PBO (zero complete blocks
  exist at N=10, so no variance estimate is available to compute one; a
  computed CI here would be false precision). **Frozen early-REJECT
  threshold**: REJECT early iff the N=10 point estimate is worse than −50
  bps/period net of cost — the SAME magnitude as the Tier-2 non-inferiority
  margin below, chosen for consistency rather than inventing a second number.
  This is checked in BOTH directions symmetrically at the single N=10 look
  (a point estimate at or better than −50bps, whether positive or mildly
  negative, does NOT trigger early REJECT and does NOT authorize ENABLE
  either — it authorizes continuing to Tier 2 either way). This closes the
  "grossly adverse is an example, not a threshold" gap from r5.
- **Tier 2 — confirmatory read, matured-block-gated (replaces the fixed
  "+10 extension" rule)**: continue running both arms until `N_eff ≥ 8`
  complete non-overlapping `h`-day blocks accumulate per estimand — 160
  sessions for the 20d estimand, 480 sessions for the 60d estimand, per the
  arithmetic above. At that point compute the preregistered t-test /
  permutation-test on the block-return sample (§1.2 unit (ii); the P2 quality
  bar frozen above: marginal-entrant mean ≥ 0 net of cost AND not
  significantly below the incumbent set by more than the non-inferiority
  margin) for real. This is
  the earliest point at which a RECOMMEND-ENABLE or REJECT verdict may be
  issued; a verdict issued before Tier 2's matured-block gate is not
  decision-grade regardless of what the point estimate shows. DSR is computed
  on this same block-return sample once `N_eff ≥ 8`, deflated for the 2 arms
  actually compared (S-0.5, S-1.0 — a small trials-correction, named
  explicitly since it's non-zero). **PBO does not apply to this comparison**
  (§1.2) — a single preregistered 2-arm paired design has no combinatorial
  train/test structure for CSCV to run over; PBO is not computed for
  estimand (A) or (B), and its absence is not a gap, it is the correct
  treatment of a 2-arm design per §1.2.
- **Non-inferiority margin (predeclared, Tier 2)**: the marginal-entrant set's
  mean forward return must not be more than 50 bps/period below the
  incumbent set's mean (one-sided non-inferiority margin, chosen as roughly
  the round-trip transaction-cost convention doubled — a conservative
  buffer against a treatment that is merely "not better" being mistaken for
  "materially worse"), in addition to the existing ≥0-net-of-cost bar. This
  gives the test a concrete margin rather than testing a point null the
  data can't resolve at any reachable N.
- Given the 20d estimand matures ~3× faster than 60d, Tier 2 MAY report the
  20d verdict first (at 160 sessions, `N_eff=8` complete 20d blocks) while
  continuing to accumulate toward the 60d gate (480 sessions, `N_eff=8`
  complete 60d blocks) — the two horizons are not required to mature
  together, and the 20d-only interim verdict is explicitly labeled as
  covering only the shorter horizon.

**Run-bundle fingerprint (closes the fingerprint-gap flagged in the r4 draft;
missingness rule added at r5)**: each shadow session for BOTH arms stamps:
(i) a config hash — sha256 of the resolved `strategy_config.shadow.json` /
`strategy_config.shadow_b.json` content; (ii) a model-artifact hash — reusing
the project's existing unified `model_content_sha256` /
`model_content_sha256_from_path` convention
(`renquant_pipeline.kernel.panel_pipeline.fingerprint_dispatch`), not a
bespoke scheme; (iii) the broker-state identity tag (`alpaca_shadow` /
`alpaca_shadow_b`); (iv) the code commit SHA of `renquant-strategy-104` and
`renquant-pipeline` at run time; (v) the frozen data/feature manifest hash
used by that session's scoring pass (the same manifest SHA convention as §1's
freeze-rule commit); (vi) this orchestrator repo's own commit SHA (so the
protocol version a session was run under is unambiguous even after this doc
changes again).

**Fingerprint-mismatch missingness rule (r5 — was previously "silently
excluded," now bounded and paired)**: a fingerprint mismatch on EITHER arm
invalidates that SESSION-PAIR in BOTH arms — a paired design requires paired
inclusion, so a clean S-1.0 session paired with a drifted S-0.5 session (or
vice versa) is excluded entirely, not half-counted. Track a running excluded-
pair count against the running attempted-pair count. **Predeclared bounds**:
if excluded pairs exceed 2 of the `h` sessions needed to complete a given
non-overlapping outcome block, that ENTIRE block is void and does not count
toward `N_eff` (it is not patched with a partial window); if cumulative
excluded pairs exceed 20% of all session-pairs attempted since the protocol
version's start, the experiment is void — do not continue accumulating under
a version with a demonstrated systemic drift problem; restart §2a under a new
protocol version with a fresh fingerprint freeze and reset session counters
(both thresholds are operator-judgment defaults, consistent in spirit with
the §2 turnover-tax gate's frozen-default treatment: no clean empirical basis
exists yet for a data-derived number, so a defensible round number is frozen
now and not adjusted after seeing how often mismatches actually occur).

**§2a non-degradation gates (frozen HERE, self-contained — not a cross-
reference to strategy-104#52, which is now config-only and cannot alter this
contract by drifting):**

| Gate | Tolerance | Applies to |
|---|---|---|
| Per-name concentration | both arms' configured cap unchanged from `shadow.json` (this protocol changes no cap; the D6 §4 cap-grid gate is a separate comparison) | S-0.5, S-1.0 |
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
  repo), issued only at Tier 2 maturity (`N_eff ≥ 8` complete blocks per
  estimand, per matured-block gate above). RECOMMEND-ENABLE iff: estimand
  (A)'s P1 shows a deployed-fraction lift AND P2 passes the ≥0-net-of-cost +
  non-inferiority bar on the 20d horizon (60d if matured) AND every §2a gate
  above is green on both arms for every counted session-pair AND run-bundle
  fingerprints are clean (missingness bounds not breached). Anything less:
  REJECT, or one declared extension of the accumulation window (no fixed
  "+10" — extend until the NEXT matured-block milestone, declared before
  inspecting any session in the extension).
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
    non-overlapping outcome blocks: `N_eff = floor(218/60) = 3`. Per §1.2's
    reliability floor (~5-10 blocks minimum for any HAC/t-test CI), the 20d
    estimand sits right at the usable floor (report a point estimate + a wide
    CI, explicitly labeled low-power) and the **60d estimand, at `N_eff = 3`,
    cannot support ANY significance test on this frozen historical pool** —
    report the 60d point estimate as directional-only, indefinitely, unless a
    future protocol version re-freezes a longer WF-cut history. This is an
    honest capacity limit of the available ~497-session pool, not something
    a smarter estimator can fix.
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
