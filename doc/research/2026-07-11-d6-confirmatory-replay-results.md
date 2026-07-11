# D6 confirmatory replay — results (first protocol-valid run)

DATE: 2026-07-11
STATUS: CONFIRMATORY EVALUATION COMPLETE — verdict below
PROTOCOL: `doc/design/2026-07-09-governor-prereg-replay-protocol.md` @ orchestrator
`origin/main` commit `1de64df9` (the merged FINAL text)
FREEZE COMMIT (pushed BEFORE any arm ran, 2026-07-11T05:15:11Z):
`d5c570e52060af62c7518a03009a658167406794` — freeze record + declared tuning plan in
`doc/research/evidence/d6_confirmatory/` (this branch)
EVIDENCE: `doc/research/evidence/d6_confirmatory/evidence_eval_fwd1d.json` (+
`tuning_results.json`, runner scripts `d6_tuning.py` / `d6_evaluation.py`)

---

## 0. Bottom line

**§5 verdict: REJECT / REDESIGN — no arm is promotable from this replay.**

1. **The primary L1 candidate (`gov_ceiling_ck`, regime-ceiling-riding E*) does
   NOT beat naive diversification**: vs `equal_weight_top_k` it loses
   −3.95 bp/day (NW t = −0.47, p = 0.64); vs `inverse_vol_top_k` it gains a
   statistically-indistinguishable +0.65 bp/day (t = 0.15). The very first §5
   ENABLE bullet fails.
2. **No arm in the 16-configuration family passes the unit-(i) DSR/PBO
   promotion bar**: family CSCV PBO = **0.874** (bar: ≤ 0.10) — the family's
   in-sample ranking has an 87% probability of not holding out-of-sample. No
   paired comparison clears mean ≥ +1 bp/day with a zero-excluding HAC CI.
3. **§4 gate breaches (recorded; series completed per the replay stop rule)**:
   the **turnover-tax ratio fails for EVERY arm** (0.855–0.998 vs ≤ 0.50 —
   frictions consume 86–100% of gross edge in every configuration at this
   book size), and the single-name construction invariant is breached by
   whole-share quantization drift in every equity arm (max realized weight
   0.129–0.156 vs 0.12 cap; harness trade-time breach counters = 0 for all
   Phase-2 arms — the excess is integer-share drift at $10.7k PV, the D7
   fractional-shares dependency made concrete).
4. **Marginal-capital estimand (§3, decisive for the cash-drag question)**:
   +5.1 bp per 20d block (point ≥ 0, so the specific REJECT trigger
   "deploying more destroys value" is NOT met) — but statistically
   indistinguishable from zero (NW lcb95 −45 bp, bootstrap lcb95 −30 bp) and
   carried entirely by one block (+237 bp; median block −17 bp). The extra
   exposure the Governor adds over incumbent deployment earns ~nothing.
5. **ENABLE was impossible from this run by construction** (§5: the live
   shadow S1 endpoint is required; replay ranks and screens only). The run's
   value is the ranking + the gate findings, which it delivered.

**The honest §5-prescribed next move**: the cash-drag answer per this evidence
is "the signal does not support more deployment at this cost structure" — the
protocol's own text routes this to the parking sleeve (RS-1) for idle cash,
plus the S-FRAC/PV lever for the quantization breach, NOT a Governor enable.

## 1. What ran (protocol compliance)

| Item | Value |
|---|---|
| Freeze rule | mechanical §1: all WF cuts, exclusion window 2026-06-23:2026-07-09; every #442-inspected session is inside the window (checked; zero extra exclusions) |
| Split (merged §2, deterministic) | union 497 → tuning 249 (2024-01-02..2025-01-08) / purged embargo 60 / evaluation 188 (2025-05-08..2026-03-27) — chronological ⌈N/2⌉ + 60-trading-day embargo; no seed exists in the merged tool (seeded-hash draft retired); frozen stochastic seeds: bootstrap 0, PBO rng 0 |
| Data | byte-copy of production `sim_runs.db`; pristine sha `82084a6d…`; working copy (journal-header normalized, logical identity proven by iterdump sha `f342eebd…`) sha `72b25fdb…`, re-verified before tuning AND before evaluation (`--verify` OK) |
| Harness | renquant-pipeline `origin/main` `3e68737` (#182 L3_FULL engine; #183/#184), fresh worktree, code untouched; custom arms registered driver-side (cap-grid precedent) |
| Conventions | stateful + tax (50%/32% @365d) + integer-shares + enforce-caps = **L3_FULL**, 5 bps/side, fill at close, PV $10,700, sector map from PINNED strategy-104 (`0e5d9891`), fwd_1d bars |
| Evaluation | ONE pass, ONE continuous book per arm over the 188-session range; no re-runs, no session re-selection |
| Blocks | 20d: 9 complete non-overlapping (≥ 8 minimum); 60d: 3 → descriptive-only (frozen) |
| Fail-closed gate | injected missing/unknown-regime cases: **3/3 emit no target** (carry book) — PASS |

## 2. Tuning phase (nested selection, tuning subset only)

Declared grids and criterion were committed in the freeze commit BEFORE
running. Chosen: **E_ceil = P_D5 (BULL_CALM .95 / BULL_VOLATILE .70 / CHOPPY
.60 / BEAR .35 — the declared D5 config-block values), hysteresis band 0.10,
top-k 8; governor_kelly s = 0.2, λ = 0.3; voltarget σ_target = 0.18**;
max_step fixed 0.15 (declared, not in the §1 nested list).

Honest flag (recorded in `tuning_results.json`): **every tuning config failed
the tuning turnover-tax sanity ratio** (0.68–0.81 vs ≤ 0.50; MDD always fine)
— the declared fallback (best Sharpe, flagged) applied. The tuning window is
BULL_CALM-heavy (224/249), so E_ceil profiles barely differentiate; the
turnover-tax failure foreshadowed the evaluation-window gate breach.

## 3. Evaluation — family table (188 sessions, one continuous book each)

| arm | mean deployed | net return | Sharpe | MDD | tax+cost/gross | DSR | PBO (family) | §4 gates |
|---|---|---|---|---|---|---|---|---|
| equal_weight_top_k | 0.469 | **+9.33%** | **0.53** | −0.201 | 0.855 | 0.999 | 0.874 | FAIL (sector drift 0.367; ratio) |
| hard_only_qp_allocator | 0.567 | +6.25% | 0.47 | −0.197 | 0.888 | 1.000 | 0.874 | FAIL |
| current_qp (reference) | 0.558 | +4.62% | 0.38 | −0.206 | 0.916 | 1.000 | 0.874 | FAIL |
| hybrid_option_f_allocator | 0.455 | +4.08% | 0.37 | −0.190 | 0.918 | 1.000 | 0.874 | FAIL |
| fractional_kelly_top_k | 0.443 | +3.51% | 0.33 | −0.195 | 0.927 | 0.997 | 0.874 | FAIL |
| stage_a_a2_long_only | 0.287 | +3.26% | 0.28 | −0.220 | 0.927 | 0.996 | 0.874 | FAIL |
| ew_at_incumbent_estar | 0.566 | +3.22% | 0.30 | −0.201 | 0.939 | 0.997 | 0.874 | FAIL |
| cap12_ck_ceil | 0.578 | +3.07% | 0.29 | −0.214 | 0.944 | 0.994 | 0.874 | FAIL |
| **gov_ceiling_ck (PRIMARY)** | 0.583 | +2.94% | 0.28 | −0.215 | 0.946 | 0.992 | 0.874 | FAIL |
| cap12_ew_ceil | 0.591 | +2.34% | 0.25 | −0.218 | 0.956 | 0.973 | 0.874 | FAIL |
| inverse_vol_top_k | 0.452 | +2.25% | 0.25 | −0.197 | 0.952 | 0.950 | 0.874 | FAIL |
| ew_at_gov_estar | 0.596 | +2.18% | 0.24 | −0.219 | 0.959 | 0.963 | 0.874 | FAIL |
| cap20_ck_ceil | 0.650 | +2.08% | 0.24 | −0.281 | 0.967 | 0.923 | 0.874 | FAIL |
| gov_kelly_ck | 0.174 | +1.02% | 0.19 | −0.095 | 0.948 | 0.757 | 0.874 | FAIL |
| gov_voltarget_ck | 0.193 | +0.69% | 0.14 | −0.100 | 0.967 | 0.532 | 0.874 | FAIL |
| cap20_ew_ceil | 0.673 | +0.11% | 0.14 | −0.288 | 0.998 | 0.554 | 0.874 | FAIL |
| cash_park (control) | 0.000 | 0.00% | — | 0.000 | n/a (zero gross) | — | — | ratio gate n/a (control) |

Eval regimes: BULL_CALM 171 / BULL_VOLATILE 17 (no CHOPPY/BEAR sessions —
the E_ceil regime differentiation is largely UNTESTED on this range).
Descriptive: incumbent's own realized sim PV over the same sessions −2.85%;
cash_park + 4%-T-bill overlay ≈ +2.97% (descriptive only; the sleeve
convention is cost_no_carry).

**Reading**: deployment ORDERING is as designed (governor/grid arms deploy
0.58–0.67 vs 0.44–0.47 baselines) — but every percentage point of extra
deployment bought LESS net return. Equal-weight at its own natural ~0.47
deployment beats everything, including every governor arm and every cap
variant. DeMiguel-floor confirmed; the prior exploratory "α-tilt dominates
current_qp" finding is REFUTED on the frozen evaluation window
(stage_a_a2 +3.3%/0.28 vs current_qp +4.6%/0.38).

## 4. Preregistered comparisons

### Unit (i) — daily paired, NW lag 4 (rule-capped), 95% CI

| comparison | mean/day | t | p | CI95 (bp) | promotion bar |
|---|---|---|---|---|---|
| gov_ceiling − equal_weight | −3.95 bp | −0.47 | 0.64 | [−20.5, +12.6] | FAIL |
| gov_ceiling − inverse_vol | +0.65 bp | +0.15 | 0.88 | [−7.8, +9.1] | FAIL |
| gov_ceiling − current_qp (c) | −0.81 bp | −0.30 | 0.77 | [−6.2, +4.5] | FAIL |
| ew@E*gov − ew@E*incumbent (a) | −0.46 bp | −0.33 | 0.74 | [−3.2, +2.3] | FAIL |
| gov_kelly − equal_weight | −5.78 bp | −0.58 | 0.56 | [−25.2, +13.7] | FAIL |
| gov_voltarget − equal_weight | −5.94 bp | −0.60 | 0.55 | [−25.2, +13.3] | FAIL |
| cap12 ew − ck (b) | −0.39 bp | −0.49 | 0.63 | [−2.0, +1.2] | FAIL |
| cap20 ew − ck (b) | −1.03 bp | −0.72 | 0.47 | [−3.9, +1.8] | FAIL |

(b) verdict: no allocator separation at matched exposure — equal-weight vs
capped-Kelly indistinguishable at both caps (Kelly ahead on point estimate).

### Unit (ii) — 20d non-overlapping blocks (N = 9), NW-lag-1 t(8) + stationary bootstrap (seed 0, 10k), one-sided α = 0.05, conjunction

| comparison | mean bp/20d | ESS | lcb95 NW | lcb95 boot | rejects "≤ −50 bp"? | notes |
|---|---|---|---|---|---|---|
| marginal capital (a) | **+5.1** | 9.00 | −45.1 | −30.1 | **YES (conjunction)** | point ≥ 0 ✔; NOT distinguishable from 0; one block (+237) carries the mean |
| gov_ceiling − current_qp | −33.2 | 9.00 | −74.5 | −73.4 | no | worst block −226 bp |
| gov_ceiling − equal_weight | −74.0 | 9.00 | −175.3 | −165.3 | no | worst block −571 bp |
| gov_ceiling − inverse_vol | +12.9 | 6.21 | −65.3 | −37.5 | **DISAGREEMENT** (NW no / boot yes) → NOT enable-grade per §1.2 | |

All four meet the N_blocks ≥ 8 AND ESS ≥ 6 minima. Per §1.2 the
NW/bootstrap DISAGREEMENT row is recorded and treated as REJECT/inconclusive.

### 60d blocks — DESCRIPTIVE ONLY (3 blocks, frozen: no test)

marginal capital +10.8 bp/60d; gov−ew −214 bp; gov−iv +46 bp; gov−qp −92 bp.

## 5. §4 gate table (recorded; replay series completed — no mid-window abort)

| Gate | Result |
|---|---|
| Turnover-tax ratio ≤ 0.50 | **FAIL — every arm** (0.855–0.998). Structural: ~$4–6k realized tax + $200–450 cost against ≤ $1.1k net gain on a $10.7k book |
| Single-name ≤ own cap (construction invariant) | **FAIL — every equity arm** on realized (post-trade-drift) weights: 0.129–0.156 @ cap 0.12 / 0.201–0.206 @ cap 0.20. Trade-time harness breach counters = **0** for all Phase-2 arms (429–629 for registry baselines, which emit uncapped targets that the engine projects down). The realized excess is whole-share quantization + inter-session drift at $10.7k PV — the D7 fractional-shares dependency, now measured as a frozen-gate breach |
| Operator 12% policy ceiling | cap20 arms flagged (would need recorded operator sign-off; moot under REJECT) |
| Sector ≤ 0.35 | PASS for all Phase-2 arms (max 0.3498-0.3502 drift); FAIL for equal_weight_top_k (0.367), hard_only_qp (0.354), stage_a_a2 (0.353) |
| Session turnover ≤ 2× equal-weight arm | PASS all arms |
| MDD ≤ 0.30 | PASS all arms (worst cap20_ew −0.288) |
| Concentration-event p5 ≥ −(cap × 0.20) | PASS all arms (worst −1.37% @ tol −4.0%) |
| Fail-closed (injected) | PASS 3/3 |

## 6. §5 decision rules, applied

| §5 ENABLE condition | Outcome |
|---|---|
| Governor beats equal_weight AND inverse_vol at DSR/PBO bar | **NO** (loses to ew outright; PBO 0.874 fails everyone; no CI excludes 0) |
| Marginal-capital estimand ≥ 0 | point estimate +5.1 bp/20d ≥ 0 (indistinguishable from 0) |
| Every §4 gate passes | **NO** (turnover-tax all arms; construction invariant all equity arms) |
| No session violates arm's own cap | **NO** (quantization drift, above) |
| S1 live shadow endpoint meets its bar | **NOT RUN** — future-only by definition; replay cannot satisfy it |
| cap > 12% operator sign-off | n/a (moot) |

**VERDICT: REJECT / REDESIGN.** Nothing here authorizes S1→S2. The §5 REJECT
text's own routing applies: idle-cash EV at this signal quality and cost
structure favors the parking sleeve (RS-1); the quantization-breach lever is
fractional shares / larger PV (D7, operator decision), not a bigger cap or a
deployment governor.

**What survives as directional/low-power support (unit-(ii) 9-block, per
§1.2 "replay ranks and screens")**: (i) the Governor's EXTRA capital is
~zero-sum before power (not catastrophic — the marginal-capital point
estimate is not negative); (ii) if any L1 idea re-enters S1 shadow later,
the family ordering says the ceiling-rider dominated the Σ-Kelly and
voltarget variants (both of which collapsed deployment to ~0.18 via tuned
shrinkage); (iii) allocator choice at matched E* is second-order vs the
deployment/cost problem — consistent with the merged protocol's own prior.

## 7. Limitations (recorded)

1. Eval regime mix is BULL_CALM 171 / BULL_VOLATILE 17, zero CHOPPY/BEAR —
   the regime-differentiated E_ceil values were never exercised on
   evaluation data; this replay cannot certify regime behavior.
2. PBO 0.874 is a family-level statement (CSCV over 16 configs): the
   observed ranking itself is unstable; treat §3's ordering as weak.
3. The construction-invariant breach is an execution-layer (integer-share)
   artifact at $10.7k PV, not an allocator-logic defect — but the gate is
   frozen on realized weights and the breach is therefore recorded as a
   breach, per protocol discipline (a future protocol version could split
   trade-time vs drift tolerances; NOT retro-applied here).
4. Tuning selected under a flagged sanity regime (no config passed the
   tuning turnover-tax gate); the declared fallback was applied. The eval
   turnover-tax failure is therefore expected, not surprising.
5. The tuning subset (2024-01..2025-01) vs eval (2025-05..2026-03) spans a
   regime shift; the tuned shrinkage s=0.2 collapsed governor_kelly's
   deployment out-of-sample — an instance of exactly the nested-selection
   overfitting the protocol's design anticipates and correctly charges to
   the arm.
6. `zip(strict=True)` in the merged harness requires Python ≥ 3.10; run
   executed under Python 3.10.20 (scratchpad venv-p1, numpy 2.2.6,
   statsmodels 0.14.6, cvxpy 1.7.5).
