# PatchTST edge-recovery experiment — design + reliability (pre-registration)

**Goal (north star):** a 60d PatchTST that PASSES the WF gate → a promotable model →
**daily-full regains the ability to trade.** Promotion still needs operator sign-off and a
clean gate pass — this doc only pre-registers the experiments and their reliability checks.

## 1. Hypothesis (grounded, truth-tagged)
- Every IC measurement of the candidates is recorded: 60d unpruned `real_ic=-0.0227` (gate
  FAIL); 20d `real_ic=-0.0196` + val IC `-0.07` (gate FAIL — the **worst** direction);
  **B2 (60d, pruned) is the ONLY config with positive val IC: +0.0040 / +0.0239 (seeds 44/45).**
  `[VERIFIED — summary.json best_val_ic + gate logs]`
- B2 excluded `STD/MIN/IMIN` (16 cols). The `feat_ic_audit` (linear per-feature proxy) found
  the **pure-placebo** drivers (placebo_dominance > 1.5, ~zero aligned IC) to be
  `IMXD/CORR/RANK/RSV/IMAX + gross_profitability/sue_signal` — which **B2 kept**. `[VERIFIED — audit run]`
- **Hypothesis:** B2 has real but **placebo-entangled** signal (val IC +0.024, but earlier
  placebo ratio ~2.8 — `[GUESS, not re-verified]`). Pruning the **remaining pure-placebo**
  features on top of B2 may push the gate placebo below threshold **while keeping** the +0.024
  signal → a gate-passing 60d model.

## 2. The two experiments (concurrent A/B)
Both: 60d label `fwd_60d_excess`, **≥2 seeds**, full sparse WF corpus (train-cutoff splits =
leakage-safe), then the **production WF gate** (3-cut WF + §5.2 sanity) as judge.

| exp | recipe (`--exclude-feature-prefixes`) | tests |
|---|---|---|
| **baseline** (have) | none (172 feat) | control: `real_ic=-0.0227`, FAIL |
| **A — reproduce B2** | `MIN STD IMIN` | does B2's +0.024 val IC survive the GATE (placebo/regime sanity)? |
| **B — B2 + pure-placebo prune** | `MIN STD IMIN IMXD CORR RANK RSV IMAX gross_profitability sue_signal` | does pruning the remaining pure-placebo drivers clean the placebo while keeping signal? |

## 3. Reliability / validity (confirmed BEFORE running)
- **Judge:** the production WF gate (3-cut WF + §5.2 shuffle/time-shift placebo + regime
  sanity IC + trade monotonicity) — the same standard that (correctly) failed 60d/20d. Not a
  bespoke metric.
- **Leakage-safe:** the WF builder splits by `--train-cutoff` per cutoff (no val_tail bug).
- **Multi-seed:** ≥2 seeds per arm to avoid single-seed noise (B2 seed44 +0.004 vs seed45
  +0.024 shows seed variance is real).
- **Control:** the 60d-unpruned baseline (`-0.0227`, FAIL) is the comparison.
- **Isolation (never-touch-production-inputs):** all outputs to `/tmp/exp_A`, `/tmp/exp_B`
  (NOT the live tree); reads the prod panel + 60d rawlabel **read-only**; no prod path written.
- **Honest caveat:** `feat_ic_audit` is a *linear per-feature* proxy for what the nonlinear
  net learns; B2's prune (`STD/MIN`) disagrees with the audit's "keep STD/MIN", so the audit
  is a **hypothesis**, the gate is the **arbiter**. We do not pre-conclude.

## 4. Pass criteria (decisive)
A model "passes" only if the WF gate VERDICT = PASS (§5.2 sanity clean: placebo below
threshold AND regime-sanity IC not-negative; WF 3-cut floor; trade-monotonicity). Positive
val IC alone is NOT a pass (that was the early-20d mistake).

## 5. Decision after
- Either arm PASSES → a promotable 60d candidate → **operator sign-off → promote → daily-full
  trades.** (Never bypass the gate.)
- Neither passes → honest verdict: the current feature set lacks clean 60d cross-sectional
  edge; pruning reduces placebo but does not create signal → escalate (new features /
  architecture), not a forced promotion.
