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
  rotation IS the weight delta between sessions — a separate pairwise-swap search with
  a hand-tuned threshold is redundant structure.
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

Per operator mandate: no fixed number. The theoretically correct aggregate deployment
for a Kelly bettor IS the sum of per-name Kelly fractions — it rises when the model
sees many strong, low-vol opportunities and falls when edges are weak. The Governor
computes:

```
raw_i  = λ · max(μ̂_i − s·σ_i, 0) / σ_i²        shrunk fractional Kelly per name
                                                  (λ = kelly fraction, s = μ-shrinkage;
                                                   both existing, trusted params)
E_raw  = Σ_{i ∈ top-k} min(raw_i, w_cap)         aggregate desired exposure
E*     = clip(E_raw, E_floor(regime), E_ceil(regime))
```

with:

- **Regime bounds, not regime targets**: `E_floor/E_ceil` per regime (e.g. BULL_CALM
  [0.5, 0.95], CHOPPY [0.2, 0.7], BEAR [0, 0.4] — exact values are config, frozen at
  protocol sign-off). Inside the bounds the SIGNAL decides — this is the "dynamic
  algorithm, not a number" requirement.
- **Hysteresis**: E* moves toward target through a no-trade band — reallocate only
  when `|E*_new − E_current| > band` (Davis-Norman closed form already in
  `davis_norman.py`), preventing daily churn from noise in μ̂.
- **Confidence scaling**: regime classifier confidence multiplies the distance E* may
  move per session (existing `confidence_to_size_multiplier` concept, relocated here).
- **Failure semantics**: if the model/calibrator is stale or fingerprint-mismatched,
  the Governor emits NO target and the pipeline falls back to current behavior
  (fail-closed = today's status quo, never forced deployment on a broken signal).

### 2.2 L2 — concentrated allocation

```
w_i = min(raw_i, w_cap) · E* / E_raw             proportional scale to hit E*
```

subject to (applied as a cheap projection, in order): per-name cap (regime
`max_position_pct`), sector cap, correlation-pair cap, held-position no-sell masks.
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

### 2.3 L3 — integer-aware execution

At $10.7k, whole-share granularity is first-order: BLK is 9.3%/share. Order
generation becomes a small greedy knapsack: sort by conviction, allocate
`round(w_i·PV/p_i)` shares with the residual-cash pass re-offering leftover cash to
the next-highest-conviction affordable name (generalizes the one-share floor's
deferred-rescue pass, strategy-104 PR #49, which stays as the interim measure).
Fractional shares would collapse this layer to exact execution — analyzed in the
separate reopen memo (§5); this RFC does not depend on it.

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
- **Primary estimands**: end-of-chain deployed fraction; realized 20d/60d forward
  portfolio return vs baseline arms.
- **Non-degradation gates** (tolerances frozen at protocol sign-off, before data):
  turnover, max single-name concentration (≤12%), sector concentration, max drawdown,
  realized volatility.
- **Quality estimand for marginal capital** (Codex requirement): forward-return
  spread of positions the Governor adds vs baseline's idle cash + the names baseline
  held — i.e., does the ADDITIONAL deployment earn its risk, not just exist.
- **Stop rule**: any mid-run gate breach aborts the arm.
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
design (D1, D6–D8). No broker-adapter changes; no model-training changes; nothing
touches the umbrella live tree.

## 6. Non-goals

- Not an alpha improvement: the Governor deploys the signal we HAVE (weak IC,
  compressed ER) with correct aggregate risk — it cannot make μ̂ better, and the
  replay explicitly tests whether deploying more of a weak signal is worth it
  (that is the decision, not an assumption).
- Not a QP repair: the QP survives only as an optional constraints-only projection.
- Not a fractional-shares decision (D7 informs it; operator decides).
- 105 (intraday) integration: the Governor's E* naturally becomes the intraday
  loop's capital budget input, but wiring that is out of scope until 105 Stage-2.
