# RFC: Deployment Governor — top-down capital allocation for renquant-104/105

STATUS: design RFC (no behavior change; implementation gated on review + preregistered replay)
DATE: 2026-07-09
OPERATOR MANDATE (2026-07-09): full sizing-architecture redesign authorized; deployment
must be a dynamic regime-linked ALGORITHM (not a fixed number); concentrate capital in
the highest-conviction names; long-short extension on the table behind its own gate;
fractional-shares reopen decided separately after analysis.
EVIDENCE BASE: `doc/research/2026-07-09-cash-drag-binding-constraints-update.md` (PR #442),
QP forensics + active-path map (this session, summarized in §2), RFC #421 (merged).

---

## 1. Problem

The book idles 54–90% of equity in cash (65% average on 8 normal-flow days) while the
model ranks 15+ positive-ER candidates daily. Root cause is architectural, not a
mis-tuned knob:

**No component owns the deployment decision.** The active sizing path is a bottom-up
multiplicative chain — `min(0.12 cap, 0.3 × μ/σ²) × conv(score) × sig_m(σ)` — drained
greedily against broker cash with no portfolio-level capital target anywhere in the
chain. Idle cash is an emergent residual, never a controlled variable. [VERIFIED —
code inspection; the only "deploy toward X%" concepts in the codebase live in the
DISABLED QP (`target_invested`, `qp_cash_drag_lambda=0`) and the passive benchmark
sleeve.]

### 1.1 The compression stack (runtime values, [VERIFIED])

| Stage | Formula | Effect on 07-02 |
|---|---|---|
| Kelly | `min(0.12, 0.3 × μ/σ²_60d)` | ~7.4% avg target |
| × conviction | `clip((score−0)/0.3, 0, 1)`, `min_mult=0` | ×0.48 (GRMN); **zeroes** at-floor names |
| × sigma mult | `clip(σ_med/σ, 0.3, 1.0)` | ×0.3–1.0 |
| whole-share | `int(target$/price)` | BLK $995, AVGO $360 → 0 shares |
| result | | 1 order, $240 (2.2%), cash stays 65% |

Three structural defects, beyond any parameter choice:

1. **Double-counting**: conviction and sigma multipliers stack ON TOP of Kelly, which
   already prices μ and σ. The code comments acknowledge this
   (`disable_extra_multipliers` escape hatch exists, unused).
2. **Zeroing**: `min_mult=0` sends at/below-floor names to exactly 0% — a cliff, not
   a taper.
3. **No aggregate control**: nothing pulls Σw toward any target; a slate of weak/zeroed
   names leaves cash idle with no backstop, and a slate of strong names still cannot
   exceed `open_slots = max_concurrent_positions − held`.

### 1.2 Why the QP (the one component that HAD a deployment concept) is disabled

Forensics (renquant-pipeline `doc/2026-06-09-qp-new-buy-sizing-bug.md` + this
session's code audit): the QP objective is sound Markowitz-with-frictions; the failure
is **turnover-budget contention**. The hard constraint `‖Δw‖₁ ≤ 0.15` charges a NEW
position its full target weight while holdings ride free; a single forced 11% trim
consumes most of the budget; the residual splits across all admitted buys at ≈1.5%
each — below the 2% `qp_min_dw_pct` emission floor — so every buy is dropped. This is
a feasibility pin, insensitive to γ/caps/μ-scale (all ruled out by live experiment,
2026-06-09). Both engineered mitigations (`turnover_exempt_forced_trims`,
`qp_soft_sell_guard.align_solver`) exist but are OFF/unbuilt in prod.

**Judgment: do not repair the QP as primary sizer.** A 15-term convex optimizer
governing a 5–8 name $10.7k long-only book is complexity-as-liability (it has hidden
four distinct production bugs requiring live forensics each). The repo already
contains the replacement (`baseline_allocators.py`): `fractional_kelly_top_k`,
`hybrid_option_f_allocator` (SELECT→SIZE→PROJECT), with an A/B replay harness
(`run_ab_replay.py`) and live shadow telemetry ALREADY running `hybrid_option_f`
as candidate vs `current_qp` incumbent.

### 1.3 Additional dead structure retired by this design

- **Pairwise rotation tree** (`min_expected_advantage_pct=0.06` vs max observed
  net_adv 0.043; 0 rotations in 6 eligible days): under a portfolio-level allocator,
  rotation IS the weight delta between sessions. r1 review point 4 accepted: the tree
  is a RETIREMENT CANDIDATE, not pre-committed — it stays in place until replay shows
  the allocator's tax-aware target-delta execution dominates it. Concrete execution
  policy for delta orders: every exit leg is charged its lot-level tax drag (existing
  `tax_drag()` helper) + transaction cost at order generation; an exit+entry pair is
  emitted only if the post-cost improvement is positive; min-hold and wash-sale masks
  apply unchanged (they enter L2 as no-sell masks).
- **`panel_buy_top_n`**: not read anywhere in the active path (joint-actions-only
  knob); the live initiation cap is `open_slots`. Documenting to kill the recurring
  misattribution.
- **Config drift note (ops)**: the umbrella-tree `strategy_config.json` copy is stale
  (`fractional=0.5`, conviction disabled) vs the pinned runtime config
  (`fractional=0.3`, conviction enabled). Runtime uses the pin — "merged ≠ deployed"
  again. Fix tracked separately.

---

## 2. Design

Four layers. L1–L3 are this RFC's scope; L4 is staged behind its own gate.

```
L1 GOVERNOR   session target gross exposure E* — dynamic algorithm (§2.1)
L2 ALLOCATOR  concentrated conviction-weighted weights w_i summing to E* (§2.2)
L3 EXECUTION  integer-aware order generation minimizing residual cash (§2.3)
L4 EXTENSION  long-short overlay (short low-conviction to fund high-conviction longs)
              — staged, own preregistered gate, operator sign-off (§2.4)
```

The existing admission chain (universe gates, wash-sale, vol gate, veto, signal
direction, earnings blackout) is UNTOUCHED — it remains the SELECT stage. All exit
logic (stops, trailing, panel exit, regime halts) is UNTOUCHED. This RFC replaces
only what happens between "ranked admitted candidates" and "orders".

### 2.1 L1 — the deployment algorithm

Per operator mandate: no fixed number. §2 Phase-2 of D6 runs THREE L1 candidates as
independent, mutually exclusive arms (r4 review: each must be exactly and separately
defined — none is a special case of another, and only one has an analytic bound
relative to raw conviction):

```
raw_i  = λ · max(μ̂_i − s·σ_i, 0) / σ_i²        shrunk fractional Kelly per name
                                                  (λ = kelly fraction, s = μ-shrinkage;
                                                   both existing, trusted params)
E_raw  = Σ_{i ∈ top-k} min(raw_i, w_cap)         aggregate raw conviction (NOT an L1
                                                  candidate itself — an input to two
                                                  of the three below)

(A) E*_ceil      = E_ceil(regime)                 PREREGISTERED CANDIDATE for the
                                                    confirmatory evaluation (post-#447:
                                                    aggregate-Kelly E* transmits μ̂
                                                    noise and is second-order to the
                                                    breadth×cap ceiling). Independent
                                                    of E_raw by construction — on a
                                                    weak-signal day with a permissive
                                                    regime, E*_ceil can EXCEED E_raw.

(B) E*_kelly     = min(E_raw, E_ceil(regime))      COMPARISON ARM (the original
                                                    Σ-shrunk-Kelly formula). This is
                                                    the ONLY one of the three with
                                                    E* ≤ E_raw guaranteed by
                                                    construction — the min() makes it
                                                    so directly.

(C) E*_voltarget = min(E_vol, E_ceil(regime))       COMPARISON ARM, where
      E_vol = σ_target / σ̂_pf                       σ̂_pf = realized/forecast
                                                    portfolio-level vol at the
                                                    CURRENT top-k weights (iterated
                                                    once: weights from E_raw-capped
                                                    Kelly, then σ̂_pf computed on those
                                                    weights before applying the
                                                    vol-target scale); σ_target is a
                                                    regime-indexed constant (existing
                                                    regime-vol-band table). Like (A),
                                                    independent of E_raw — a low-σ̂_pf
                                                    slate can push E_vol above E_raw.
```

**Arm-name cross-reference to D6 §2 Phase-2** (same candidates, protocol-doc names):
(A) `E*_ceil` = the "regime-ceiling-riding" arm; (B) `E*_kelly` = `governor_kelly`;
(C) `E*_voltarget` = `voltarget`.

**Whichever of (A)/(B)/(C) the confirmatory run selects becomes the D2 default; the
others remain implemented behind the same config surface** (D6 §2 Phase-2, all three
locked before evaluation — no candidate is added or dropped after seeing results).

**The three candidates are NOT interchangeable with respect to L2's feasibility
property** (r4 review, point 1): only (B) is bounded by E_raw by construction. Under
(A) or (C), E* can legitimately exceed E_raw — that is not a bug, it is the expected
outcome whenever the regime (or the vol-target) is more permissive than the model's
own conviction supports. §2.2 restates the L2 allocator's actual behavior under all
three candidates without assuming (B)'s bound.

with (applying to all three L1 candidates):

- **Ceiling only, no floor** (r1 review, point 2 accepted): an exposure floor is
  forced deployment whenever the signal slate is weak — exactly the systematic
  low-quality exposure this design must not create. Shrunk Kelly already contracts
  when edges are weak; a weak slate → low E* is the CORRECT output, not a failure.
  Regime enters through `E_ceil` (risk-off regimes cap exposure) and through μ̂/σ̂
  themselves. Residual cash above E* is not "drag" — it routes to the parking
  sleeve (RS-1, S7 shadow already built) as the explicit idle-capital home.
- **Weak slate vs model fault are distinguished states**: model fault (staleness,
  fingerprint mismatch, calibrator contract failure) → Governor emits NO target,
  pipeline falls back to current behavior (fail-closed). Healthy model with a weak
  admitted slate → Governor emits the LOW E* the signal supports, with the slate
  quality (count of admitted names, Σ raw Kelly, μ̂ dispersion) stamped in the
  decision ledger so weak-slate sessions are auditable, not silent.
- **Hysteresis**: E* moves toward target through a no-trade band — reallocate only
  when `|E*_new − E_current| > band` (Davis-Norman closed form already in
  `davis_norman.py`), preventing daily churn from noise in μ̂.
- **Confidence scaling**: regime classifier confidence multiplies the distance E* may
  move per session (existing `confidence_to_size_multiplier` concept, relocated here).

### 2.2 L2 — concentrated allocation (achievable-exposure operator)

r1 review point 1 accepted: proportional scaling can push weights above per-name
caps, and projection can make a declared E* unattainable. The allocator is therefore
a deterministic DOWN-ONLY operator — it never scales any weight above its cap, and
the exposure it declares is computed AFTER all constraints:

```
1. w_i   = min(raw_i, w_cap_i)          per-name capped Kelly, top-k by conviction
2. w_i  ← project(w)                    sector cap, correlation-pair cap,
                                         no-sell/wash-sale masks — each applied by
                                         reducing the offending weights only
                                         (conviction-ordered: lowest conviction
                                         trimmed first), never raising any weight
3. if Σw > E*:  w ← w · E*/Σw           proportional scale-DOWN only (safe: every
                                         factor ≤ 1, caps preserved)
4. E_final = Σw                          the DECLARED exposure — always achievable
                                         by construction; E* is a ceiling input,
                                         never a promise
5. residual = E* − E_final ≥ 0           routes to the parking sleeve; stamped in
                                         the ledger with the binding constraint
                                         that produced it (cap_sector / cap_corr /
                                         mask / low_conviction / breadth_bound —
                                         see the corrected feasibility statement
                                         below for the full tag taxonomy)
```

**Corrected feasibility statement (r4 review — the prior claim "E* ≤ E_raw by §2.1"
was true only for candidate (B) and silently assumed away candidates (A) and (C),
where E* is independent of E_raw and can exceed it on a routine basis):**

Let `E_proj = Σw` after step 2 (post sector/corr/mask projection, so `E_proj ≤
E_raw` always, by construction — step 1 already caps each weight, step 2 only
reduces). Step 3 gives:

```
E_final = min(E_proj, E*)
```

This holds for ALL THREE L1 candidates and is a trivial identity (step 3 only
fires — and clamps exactly to E* — when `E_proj > E*`), not a proof requiring
`E* ≤ E_raw`. `E_final` is always achievable and no weight ever exceeds its cap,
regardless of which L1 candidate is active — the allocator's down-only safety
property does NOT depend on E*'s relationship to E_raw.

**"Cannot reach declared E*" (`E_final < E*`) now has THREE distinct sources, each
stamped separately in the ledger (extending step 5's binding-constraint tag)**:

1. **Step-2 projections** (sector/corr/mask): `E_proj < E_raw` and `E* ≥ E_proj`,
   so `E_final = E_proj`. Tag: `cap_sector` / `cap_corr` / `mask`.
2. **Low aggregate conviction** (only possible under candidates (A)/(C), where
   `E* > E_raw ≥ E_proj` is routine on a weak-signal day with a permissive regime
   or low realized vol): `E_final = E_proj ≤ E_raw < E*`. This is the CORRECT,
   expected "weak slate" output from §2.1 — not a defect, and not attributable to
   step-2 projections. Tag: `low_conviction`.
3. **Breadth** (fewer than k names pass admission): folded into `E_raw` itself
   (the top-k sum has fewer than k terms), surfaces identically to source 2 but is
   tagged separately (`breadth_bound`) since it reflects the SELECT stage, not L1
   or L2.

Under candidate (B) only, source 2 cannot occur (`E* ≤ E_raw` by construction), so
the original claim ("cannot-reach-E* arises only from projections") was correct
for (B) alone — it does not generalize to (A)/(C), which are the confirmatory
run's actual preregistered L1 candidate and one of its comparison arms. There is
no upward water-fill anywhere under any candidate: capital never flows to a name
beyond what its own conviction (raw_i) and caps justify.

This is `fractional_kelly_top_k` + the existing constraint set — analytic, per-name,
**no shared turnover budget** (turnover control lives in the per-name no-trade band,
which cannot starve new entries by construction).

- **Retires** the conviction × sigma multiplier stack (double-count) — μ and σ enter
  once, through Kelly. `min_mult=0` cliff replaced by top-k selection: a name is
  either allocated meaningfully or not at all (operator: concentrate, don't dust).
- **k** (number of names) comes from `max_concurrent_positions` (regime-aware,
  existing) — but the allocator may hold FEWER than k when E* is low.
- Rotation emerges from weight deltas: if a new name enters top-k and a held name's
  w_target → 0, the delta produces the exit+entry pair, tax-drag-adjusted at the
  order-generation stage (existing tax logic reused as an execution-layer cost, not
  a pairwise veto).
- Optional PROJECT stage: `hard_only_qp_allocator` (constraints-only QP, no
  objective terms) as a feasibility repair IF the cheap projection order proves
  insufficient in replay. Default OFF.

### 2.3 L3 — integer-aware execution (executed-state invariant)

At $10.7k, whole-share granularity is first-order: BLK is 9.3%/share. Order
generation is a greedy pass in conviction order with a residual-cash re-offer
(generalizing the one-share floor's deferred-rescue pass, strategy-104 PR #49,
which stays as the interim measure).

r2 review point 1 accepted — naive rounding of `w_i·PV/p_i` can push an order
ABOVE its L2 target or cap, and a portfolio of rounded orders can breach cash,
sector, or concentration constraints. L3 therefore carries its own invariant,
mirroring the one-share floor's explicit cap/headroom guarantees:

- **Round DOWN by default** (`floor(w_i·PV/p_i)` shares). A round UP (the
  one-share rescue case) is permitted only under the deferred-rescue conditions:
  one share ≤ per-name cap × PV AND ≤ remaining investable headroom, evaluated
  AFTER all round-down orders are funded.
- **Post-round recheck**: after integer quantities are fixed, cash (incl. reserve
  and tax-reserve conventions), single-name cap, sector cap, and correlation-pair
  constraints are re-verified on the EXECUTED quantities; any violating order is
  capped down or rejected — never submitted in breach.
- **Separate ledger fields**: `E_executed = Σ(shares_i·p_i)/PV` and
  `integer_residual = E_final − E_executed` are stamped per session, distinct from
  L2's continuous `E_final` and L1's `E*` — three auditable numbers, one per layer.

Fractional shares would collapse this layer to exact execution — analyzed in the
separate reopen memo (§5); this RFC does not depend on it.

**Conviction, defined** (r2 minor point): "conviction" throughout this RFC is
`raw_i` — the shrunk fractional-Kelly score itself — used ONLY as an ordering key
(top-k membership, constraint-trim priority, greedy funding order, residual
re-offer order). It never multiplies a weight: μ̂ and σ̂ enter position size exactly
once, inside `raw_i`. Ordering by `raw_i` is a monotone rank, so it cannot
reintroduce the μ/σ double-count under another name.

### 2.4 L4 — long-short extension (staged, NOT in initial scope)

Operator is open to shorting low-conviction names to lever high-conviction longs.
Design constraint: enters as `E_gross` vs `E_net` in the Governor (gross ≤ 1 + short
budget; net free within regime bounds), shorts sourced from the EXISTING shorting
mandate's admission bar (bottom-5% + N-of-N μ breach + confirmed BEAR + vetoes,
max 2 concurrent). Requires: margin/borrow cost model, its own preregistered
protocol, and operator sign-off at enablement (capital-risk change). Nothing in
L1–L3 assumes or precludes it.

---

## 3. Evaluation protocol (preregistered, end-of-chain)

Per Codex review of the evidence memo: constraint rankings from sequential funnel
counts are hypotheses; the decision standard is END-OF-CHAIN counterfactual replay.

- **Harness**: existing `run_ab_replay.py` + live shadow telemetry
  (`live_shadow_telemetry.py`) — both already in production use for the allocator
  shadow.
- **Arms**: (a) incumbent greedy+Kelly+multipliers (baseline), (b) Governor+allocator
  (this RFC), (c) `equal_weight_top_k`, (d) `inverse_vol_top_k` — (c)/(d) are the
  DeMiguel-2009 naive-diversification floors any smart allocator must beat.
- **Session set**: frozen BEFORE inspection; hypothesis-generation window (06-23 →
  07-09, used throughout this RFC) is EXCLUDED from evaluation; evaluation uses
  future-only shadow sessions + a held-out historical window not previously inspected.
- **Primary estimands**: end-of-chain deployed fraction (daily paired series —
  no forward window, NW lag ≤ 10 valid) and paired daily realized returns;
  block-aggregated return endpoints are enable-grade at the 20d block length
  ONLY, computed on non-overlapping complete blocks with DEPENDENCE-ROBUST
  inference — the blocks are not independent (60d is descriptive-only) —
  units, method, and the `N_blocks`/`ESS` minima are defined once, in D6
  §1.2, and this RFC defers to them. Historical replay evidence is
  directional/low-power support; enablement additionally requires the live
  shadow arm-level endpoint (D6 §5).
- **Non-degradation gates** (tolerances frozen at protocol sign-off, before data):
  turnover, max single-name concentration (≤12%), sector concentration, max drawdown,
  realized volatility.
- **Quality estimand for marginal capital** (Codex requirement): forward-return
  spread of positions the Governor adds vs baseline's idle cash + the names baseline
  held — i.e., does the ADDITIONAL deployment earn its risk, not just exist.
- **Stop rule**: defined SOLELY by D6 §5 (r3 review accepted — the two documents
  must not both define it): historical replay arms always run the FULL
  registered horizon with breaches recorded (no asymmetric censoring);
  immediate abort applies only to live shadow/canary.
- **Decision**: ENABLE requires (b) ≥ (a) on primary estimands AND all gates pass
  AND (b) not dominated by (c)/(d) — if equal-weight matches the Governor, ship
  equal-weight (simplicity wins).

## 4. Rollout (staged, each stage gated)

1. **S0 replay**: harness A/B on held-out sessions (no live footprint)
2. **S1 shadow**: Governor computes E*/weights in shadow JSONL alongside prod daily
   run (read-only, like existing allocator shadow)
3. **S2 canary**: Governor live but E* clamped to ±10pp of current behavior
4. **S3 enable**: full regime bounds active; kill switch = single config flag back
   to legacy path (which remains in code untouched)

Rollback at every stage is one config flag; no state migration; legacy path is the
permanent fallback for Governor failure semantics (§2.1).

## 5. Deliverables and repo split

| # | Deliverable | Repo | Nature |
|---|---|---|---|
| D1 | This RFC | orchestrator | design |
| D2 | Governor kernel task (E* algorithm + hysteresis + fail-closed) | renquant-pipeline | code, flag OFF |
| D3 | Allocator integration (fractional_kelly_top_k as SIZE stage, multiplier stack retirement behind flag) | renquant-pipeline | code, flag OFF |
| D4 | Integer-aware execution pass (generalize one-share deferred rescue) | renquant-pipeline | code, flag OFF |
| D5 | Config block (governor bounds, bands, flags — all default OFF) | renquant-strategy-104 | config |
| D6 | Replay protocol + frozen session set + tolerance freeze | orchestrator | prereg doc |
| D7 | Fractional-shares reopen analysis (active-path wiring, software stops, risks) | orchestrator | memo → operator decision |
| D8 | Long-short extension design | orchestrator | separate RFC, after S1 |

Boundary compliance: pipeline owns kernel primitives (D2–D4); strategy-104 owns
policy/config (D5); orchestrator owns orchestration, evaluation, and cross-repo
design (D1, D6–D8). No broker-adapter changes; no model-training changes; this
RFC's OWN deliverables (D1-D8) touch nothing in the umbrella live tree.
**Caveat (r6, D6 §2a)**: D6's breadth-lever shadow A/B carries a frozen
boundary rule — **no umbrella runner or call-site change is permitted for
that experiment, and the umbrella runner is not invoked on its path; the
umbrella remains a deprecated pin consumer**. Its entry is multi-repo-owned:
renquant-execution owns the parameterized read-only wrapper
(`renquant_execution.readonly_broker`, prerequisite PR P-1),
renquant-orchestrator owns the daily two-arm orchestration entrypoint
(prerequisite PR P-2), renquant-pipeline owns the (already parameterized)
broker-tagged state paths plus two allowlist entries, and strategy-104
contributes the config-only treatment PR. P-1 and P-2 are D6-§2a build
items, each subject to normal review; they are not part of this RFC's D1-D8
deliverable set and are not authorized by this RFC's approval.

## 6. Non-goals

- Not an alpha improvement: the Governor deploys the signal we HAVE (weak IC,
  compressed ER) with correct aggregate risk — it cannot make μ̂ better, and the
  replay explicitly tests whether deploying more of a weak signal is worth it
  (that is the decision, not an assumption).
- Not a QP repair: the QP survives only as an optional constraints-only projection.
- Not a fractional-shares decision (D7 informs it; operator decides).
- 105 (intraday) integration: the Governor's E* naturally becomes the intraday
  loop's capital budget input, but wiring that is out of scope until 105 Stage-2.
