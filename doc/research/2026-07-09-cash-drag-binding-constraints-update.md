# Cash drag binding constraints — updated evidence (2026-07-09)

STATUS: research memo  
DATE: 2026-07-09  
CONTEXT: follows RFC #421 (merged 07-07); Phase 4 VOID (sweep design flaw, PR #440);
tournament retrain completed same day (staleness no-trade root cause RESOLVED).

## Bottom line

Lane A's A-1 (`qp_cash_drag_lambda`) is **dead code** — QP path is disabled in production
(config: `joint_actions.enabled: false`, solver note: "QP path sizes all new buys <2%...
legacy SelectionJob+Kelly path until fixed"). The active sizing path is Kelly + SelectionJob.

The two largest cash-drag binding constraints are **not addressed in the current Lane A
plan** (A-1/A-2/A-3):

| Constraint | Kill rate | Mechanism | In Lane A? |
|---|---|---|---|
| VetoWeakBuys adaptive floor | **80%** (66/83 on 07-02) | `rank_score floor = mean + 1σ ≈ 0.575` | NO |
| Rotation threshold | **100%** structural | `min_expected_advantage_pct=0.06` > model max ER (0.051) | NO |
| Whole-share quantization | ~30% of survivors | Kelly 2-7% → $200-750; BLK/AVGO > price | YES (A-3) |
| QP cash penalty (A-1) | 0% | QP disabled; dead code | YES but dead |

---

## 1. Evidence: the full funnel (11 trading days, 06-23 → 07-09)

| Date | Equity | Cash % | Candidates | Post-vol | Post-veto | Kelly>0 | Orders |
|---|---|---|---|---|---|---|---|
| 06-23 | $10,551 | **90%** | 104 | 81 | 18 | 8 | 0 |
| 06-24 | $10,658 | 65% | 95 | 73 | 18 | 4 | 0* |
| 06-25 | $10,677 | 62% | 97 | 76 | 18 | 0 | 0 |
| 06-26 | $10,631 | 62% | 101 | 79 | 14 | 1 | 0 |
| 06-29 | $10,799 | 61% | 65 | 43 | 6 | 0 | 0 |
| 06-30 | $10,855 | 54% | 0 | 0 | 0 | 0 | 0 |
| 07-01 | $10,810 | 57% | 114 | 83 | — | — | 0† |
| 07-02 | $10,709 | 65% | 115 | 83 | **17** | **17** | 0 |
| 07-07 | $10,666 | 61% | 51 | 33 | 5 | 3 | 0 |
| 07-08 | $10,628 | **71%** | 0‡ | 0 | 0 | 0 | 0 |
| 07-09 | $10,768 | **70%** | 0‡ | 0 | 0 | 0 | 0 |

\* 06-24: CSCO/PANW/AVGO entered (fills visible as cash drop)  
† 07-01: calibrator fingerprint mismatch → sell-only fallback  
‡ 07-08/09: per-ticker staleness gate blocked all candidates (FIXED this session)

### Key ratios
- **Veto kill rate**: 66/83 = 80% (07-02), 55/73 = 75% (06-24), 58/76 = 76% (06-25)
- **Average cash**: 65% of equity over 11 days
- **Best-case deployment**: 54% cash (06-30, 7 positions) — still >50% idle

---

## 2. Constraint decomposition

### 2.1 VetoWeakBuys floor (PRIMARY — 80% kill)

Config: `buy_floor: adaptive_mean_std`, `buy_floor_std_mult: 1`, `buy_floor_min: 0.2`

The adaptive floor computes `max(0.20, mean + 1.0 × std)` of the cross-sectional
calibrated `rank_score` distribution each day. With PatchTST's compressed scores clustering
in [0.45, 0.65], this floor sits at ~0.54-0.58 and admits only the far-right tail.

On 07-02 (representative day with 83 scored candidates):
- Floor = 0.575
- Candidates above floor: 17 (20%)
- Candidates killed: 66 (80%)

**Theory**: the floor was designed for the GBDT-era XGB model whose scores had wider
dispersion. PatchTST's output compresses into a narrower band (the calibrator's ER=0
neutral sits at raw=-0.24, confirming intrinsically-negative scores). The 1σ threshold
was appropriate for a wider distribution but is too aggressive for PatchTST's compressed
output — it mechanically filters out the MIDDLE of the calibrated distribution, not just
noise.

**Potential fix (strategy-104 config, NOT orchestrator):**
- Lower `buy_floor_std_mult` from 1.0 to 0.5 (admits ~35-40% instead of ~20%)
- OR switch to percentile-based floor (top 30-40%)
- Requires preregistered A/B per RS-2 protocol

### 2.2 Rotation threshold (SECONDARY — structural block)

Config: `rotation.min_expected_advantage_pct: 0.06`, `rotation.transaction_cost_pct: 0`

On 07-02, the best candidate (FTNT) had `er=+0.0511`. The rotation threshold is 0.06.
**No candidate can trigger a rotation** because the model's maximum calibrated ER is below
the threshold.

| Candidate | ER | Threshold | Gap | Result |
|---|---|---|---|---|
| FTNT | +0.0511 | 0.06 | -0.0089 | BLOCKED |
| BLK | +0.0459 | 0.06 | -0.0141 | BLOCKED |
| GRMN | +0.0367 | 0.06 | -0.0233 | BLOCKED |

With `transaction_cost_pct=0`, the threshold represents a pure edge hurdle with NO cost
justification. The 6% hurdle was set before PatchTST's adoption; its scores produce
lower calibrated ERs than the prior XGB model.

**Theory**: Perold (1988) and DeMiguel & Nogales (2009) establish that optimal rebalancing
thresholds should be proportional to sqrt(transaction costs × holding period). With zero
configured transaction costs, the threshold should be near zero (only estimation
uncertainty justifies a positive band). 6% is not anchored to any parameter.

**Potential fix (strategy-104 config):**
- Lower to 0.03 (where FTNT would clear: 0.0511 - 0.0225 = 0.0287 > 0.03 after
  deducting held CSCO's ER)
- OR make it dynamic: `threshold = f(model_output_std, transaction_cost)`
- Requires preregistered A/B per RS-2 protocol

### 2.3 Kelly × sigma_sizing compression (TERTIARY — sizing)

Config: `fractional: 0.5`, `sigma_sizing.floor: 0.3`, `max_concentration: 0.12`

Effective sizing: Kelly_f × conviction_mult × equity. The `sigma_sizing` maps panel score
to a conviction multiplier in [0.3, 1.0]. With PatchTST scores near the floor,
conviction_mult ≈ 0.48-0.60 → effective fractional ≈ 0.24-0.30.

Result on 07-02: GRMN sized at 2.2% target ($240 on $10.7k). At $240 per position:
- GRMN $240/share → 1 share ✓ (barely)
- AVGO $360/share → 0 shares ✗
- BLK $995/share → 0 shares ✗

A-3 (one-share floor) addresses the 0-share blocking but not the tiny position sizes.

### 2.4 Signal-direction gate (KNOWN — informational)

45/83 candidates (54%) on 07-02 had calibrated ER of OPPOSITE sign to their raw signal
(calibrator neutral_raw = -0.29). These are candidates in the [-0.29, 0] raw zone where
PatchTST says "slightly bearish" but the calibrator maps to "slightly positive." The
signal-direction gate correctly rejects these ambiguous signals.

This is NOT a miscalibration — it's the model's intrinsically-negative output distribution
(documented in memory). No change recommended.

---

## 3. Revised Lane A priority

| Priority | Knob | Owner repo | Impact estimate | Status |
|---|---|---|---|---|
| **A-0** | VetoWeakBuys `buy_floor_std_mult` 1.0 → 0.5 | strategy-104 | +60% candidates surviving | NEW — needs design PR |
| **A-0b** | Rotation threshold 0.06 → 0.03 | strategy-104 | unblocks ALL rotations | NEW — needs design PR |
| ~~A-1~~ | ~~`qp_cash_drag_lambda`~~ | ~~strategy-104~~ | ~~0%~~ | ~~DEAD CODE — QP disabled~~ |
| **A-2** | `panel_buy_top_n` 3 → 5-6 | strategy-104 | +3 entries/day | DEFERRED (per RS-2) |
| **A-3** | One-share initiation floor | pipeline | +2-3 high-price names | READY for shadow |

---

## 4. Next actions (repo-correct)

1. **Design PR in strategy-104**: preregistered A/B protocol for VetoWeakBuys floor
   calibration (A-0) — shadow replay comparing `std_mult=1.0` vs `std_mult=0.5` on
   frozen session set, measuring deployed fraction + turnover + concentration
2. **Design PR in strategy-104**: rotation threshold calibration (A-0b) — shadow replay
   comparing `min_expected_advantage_pct=0.06` vs `0.03`
3. **Shadow implementation in pipeline**: one-share initiation floor (A-3) — per RS-2
   preregistered protocol (already designed)
4. **Close A-1**: document QP-disabled status; A-1 is blocked until QP path is repaired
