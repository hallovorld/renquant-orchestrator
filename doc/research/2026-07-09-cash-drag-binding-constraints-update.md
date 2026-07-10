# Cash drag binding constraints — working diagnosis (2026-07-09)

STATUS: research memo — **working diagnosis; all constraint rankings are HYPOTHESES
pending end-of-chain counterfactual replay** (per Codex r1/r2 review)  
DATE: 2026-07-09  
CONTEXT: follows RFC #421 (merged 07-07); Phase 4 VOID (sweep design flaw, PR #440);
tournament retrain completed same day (staleness no-trade root cause RESOLVED).
SUPERSESSION NOTE: knob-level tactical priority in this memo is the EVIDENCE BASE for
the sizing-architecture redesign (Deployment Governor RFC, in progress) — not a
standalone fix plan. Tactical design PRs #47/#48 (strategy-104) were CLOSED in favor
of the redesign.

## Bottom line

Lane A's A-1 (`qp_cash_drag_lambda`) is **dead code** — QP path is disabled in production
(config: `joint_actions.enabled: false`, solver note: "QP path sizes all new buys <2%...
legacy SelectionJob+Kelly path until fixed"). The active sizing path is Kelly + SelectionJob.
This one claim is [VERIFIED] (config + code inspection, not funnel inference).

The following constraints are observed at high attrition rates in the diagnostic window.
**Sequential funnel kill rates are NOT marginal effect estimates** — downstream gates act
on survivors, so ranking these as causes requires holding other knobs fixed in replay and
measuring end-of-chain deployed-fraction lift. Until that replay exists, this table is
hypothesis-generating:

| Constraint (hypothesis) | Observed attrition | Mechanism | In Lane A? |
|---|---|---|---|
| VetoWeakBuys adaptive floor | 80% of scored (66/83 on 07-02) | `rank_score floor = mean + 1σ ≈ 0.575` | NO |
| Rotation threshold | 0 rotations in 6 eligible days | threshold 0.06 > max observed net_adv 0.043 | NO |
| Whole-share quantization | 2 of top-3 slots on 07-02 | Kelly 2-7% → $200-750; BLK/AVGO > price | YES (A-3) |
| QP cash penalty (A-1) | n/a | QP disabled; dead code | YES but dead |

---

## 1. Evidence: the full funnel (11 trading days, 06-23 → 07-09) — DIAGNOSTIC ONLY

The window mixes THREE regimes and must not be averaged as one production baseline
(Codex r1 point 1). Split:

**Normal decision-flow days (8):**

| Date | Equity | Cash % | Candidates | Post-vol | Post-veto | Kelly>0 | Orders |
|---|---|---|---|---|---|---|---|
| 06-23 | $10,551 | **90%** | 104 | 81 | 18 | 8 | 0 |
| 06-24 | $10,658 | 65% | 95 | 73 | 18 | 4 | 0* |
| 06-25 | $10,677 | 62% | 97 | 76 | 18 | 0 | 0 |
| 06-26 | $10,631 | 62% | 101 | 79 | 14 | 1 | 0 |
| 06-29 | $10,799 | 61% | 65 | 43 | 6 | 0 | 0 |
| 06-30 | $10,855 | 54% | 0 | 0 | 0 | 0 | 0 |
| 07-02 | $10,709 | 65% | 115 | 83 | **17** | **17** | 1 (GRMN $240) |
| 07-07 | $10,666 | 61% | 51 | 33 | 5 | 3 | 0 |

**Outage / fallback days (3) — excluded from structural-constraint summaries:**

| Date | Cash % | Failure mode |
|---|---|---|
| 07-01 | 57% | calibrator fingerprint mismatch → sell-only fallback |
| 07-08 | 71% | per-ticker staleness gate blocked all candidates (FIXED 07-09) |
| 07-09 | 70% | same staleness outage |

\* 06-24: CSCO/PANW/AVGO entered (fills visible as cash drop)

### Key ratios (normal-flow days ONLY)
- **Veto attrition**: 66/83 = 80% (07-02), 55/73 = 75% (06-24), 58/76 = 76% (06-25)
  — sequential attrition at one gate, NOT a marginal deployment effect
- **Average cash on the 8 normal-flow days**: 65% of equity (the finding survives
  the regime split — outage days do not drive it)
- **Best-case deployment**: 54% cash (06-30, 7 positions) — still >50% idle on the
  system's best day

---

## 2. Constraint decomposition

### 2.1 VetoWeakBuys floor (PRIMARY — 80% kill)

Config: `buy_floor: adaptive_mean_std`, `buy_floor_std_mult: 1`, `buy_floor_min: 0.2`

The adaptive floor computes `max(0.20, mean + 1.0 × std)` of the cross-sectional
calibrated `rank_score` distribution each day. With the XGB panel scorer's calibrated scores clustering
in [0.45, 0.65], this floor sits at ~0.54-0.58 and admits only the far-right tail.

On 07-02 (representative day with 83 scored candidates):
- Floor = 0.575
- Candidates above floor: 17 (20%)
- Candidates killed: 66 (80%)

**Theory**: the 1σ threshold is too aggressive for the XGB panel scorer's compressed
calibrated output — it mechanically filters out the MIDDLE of the distribution, not
just noise. The calibrator's ER=0 neutral sits at raw≈−0.29, and a rank_score of 0.55
maps to a positive ER (~+3%), meaning the floor rejects candidates the model considers
genuinely positive.

**Potential fix (strategy-104 config, NOT orchestrator):**
- Lower `buy_floor_std_mult` from 1.0 to 0.5 (admits ~35-40% instead of ~20%)
- OR switch to percentile-based floor (top 30-40%)
- Requires preregistered A/B per RS-2 protocol

### 2.2 Rotation threshold (hypothesis: mis-scaled to net-advantage distribution)

Config: `rotation.min_expected_advantage_pct: 0.06`, `rotation.transaction_cost_pct: 0`

The decision variable is **candidate-minus-incumbent NET advantage** (raw ER advantage
minus tax drag minus transaction cost), not candidate ER alone (Codex r1 point 3
accepted — earlier drafts overstated this from candidate ER). Measured from the
ROTATION_TREE logs, best net_adv per rotation-eligible day:

| Date | Best pair | raw_adv | tax drag | **net_adv** | vs 0.06 |
|---|---|---|---|---|---|
| 06-23 | PANW→MU | +0.008 | 0.544 | −0.536 | tax-dominated |
| 06-24 | CAT→AMZN | +0.002 | 0.002 | +0.000 | tiny edge |
| 06-26 | FTNT→AMZN | +0.043 | 0.000 | **+0.043** | threshold-blocked |
| 06-29 | FTNT→AMZN | +0.029 | 0.017 | +0.013 | threshold-blocked |
| 07-02 | FTNT→CSCO | +0.029 | 0.000 | **+0.029** | threshold-blocked |
| 07-07 | ZM→CSCO | +0.002 | 0.000 | +0.003 | tiny edge |

Observed: 0 rotations fired in 6 eligible days; max observed net_adv = 0.043 < 0.06.
On 3 of 6 days the binding blocker was tax drag or a genuinely tiny edge — the
threshold is NOT the sole blocker. Claim status: **hypothesis** — "0.06 exceeded every
observed net_adv in this window" is verified for the window, but "structurally
unreachable in general" requires the net_adv distribution over a preregistered session
set.

**Theory**: Perold (1988) and DeMiguel & Nogales (2009) establish that optimal rebalancing
thresholds should be proportional to sqrt(transaction costs × holding period). With zero
configured transaction costs, the threshold should be near zero (only estimation
uncertainty justifies a positive band). 6% is not anchored to any parameter. Code default
is 0.03 (rotation.py:447); the production 2× override is undocumented.

**Disposition**: strategy-104 PR #48 (0.06→0.02 knob patch) was CLOSED — under the
Deployment Governor redesign, rotation emerges from portfolio-level weight targets
rather than a pairwise threshold tree, so tuning this knob patches a structure the
redesign replaces.

### 2.3 Kelly × sigma_sizing compression (TERTIARY — sizing)

Config: `fractional: 0.5`, `sigma_sizing.floor: 0.3`, `max_concentration: 0.12`

Effective sizing: Kelly_f × conviction_mult × equity. The `sigma_sizing` maps panel score
to a conviction multiplier in [0.3, 1.0]. With XGB panel scores near the floor,
conviction_mult ≈ 0.48-0.60 → effective fractional ≈ 0.24-0.30.

Result on 07-02: GRMN sized at 2.2% target ($240 on $10.7k). At $240 per position:
- GRMN $240/share → 1 share ✓ (barely)
- AVGO $360/share → 0 shares ✗
- BLK $995/share → 0 shares ✗

A-3 (one-share floor) addresses the 0-share blocking but not the tiny position sizes.

### 2.4 Signal-direction gate (KNOWN — informational)

45/83 candidates (54%) on 07-02 had calibrated ER of OPPOSITE sign to their raw signal
(calibrator neutral_raw = -0.29). These are candidates in the [-0.29, 0] raw zone where
the XGB scorer says "slightly bearish" but the calibrator maps to "slightly positive." The
signal-direction gate correctly rejects these ambiguous signals.

This is NOT a miscalibration — it's the model's intrinsically-negative output distribution
(documented in memory). No change recommended.

---

## 3. Disposition: knob-level patching SUPERSEDED by architecture redesign

The observations above share one structural root: **no component in the pipeline owns
the deployment decision.** Kelly × conviction × σ-mult is a bottom-up multiplicative
chain where each conservative factor compounds (0.5 × ~0.5 × ~0.5 ≈ tiny positions);
the greedy SelectionJob funds slots sequentially with no portfolio-level target; the
actual portfolio optimizer (QP) is disabled dead code; and whole-share rounding is a
first-class problem at $10.7k that the design treats as an edge case.

Operator direction (2026-07-09): full sizing-architecture redesign authorized —
dynamic regime-linked deployment (algorithmic, not a fixed number), concentrated
conviction-weighted allocation, long-short extension staged behind its own gate.

| Item | Status |
|---|---|
| Deployment Governor RFC (top-down capital budget → concentrated allocation → integer execution) | IN PROGRESS |
| Fractional-shares reopen analysis (prereqs: active-path wiring, software stops) | memo pending, operator decides |
| One-share floor PREPARE (strategy-104 PR #49) | OPEN — interim L3 measure, shadow=ON |
| Veto-floor knob PR #47, rotation-threshold knob PR #48 | CLOSED — superseded |
| Sequential-funnel → causal ranking | retracted to hypothesis status (this memo) |

## 4. What this memo IS and IS NOT

- IS: the diagnostic evidence base (funnel attrition, net_adv distribution, dead-code
  QP finding, whole-share blocking) feeding the Deployment Governor RFC
- IS NOT: a validated causal ranking of constraints — that requires end-of-chain
  counterfactual replay, which the RFC's evaluation protocol will specify
- IS NOT: a knob-tuning plan — the knob-level Lane A framing (A-0/A-0b) is retired
