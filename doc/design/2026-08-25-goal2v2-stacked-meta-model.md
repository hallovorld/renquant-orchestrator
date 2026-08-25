# GOAL-2v2: a stacked meta-model over base-model scores and state/macro trend features

STATUS: design for review. Direction approved by the operator 2026-08-25 ("按这个做", responding to the staged plan in this exact form). Supersedes the GOAL-2 blend-weights line, whose
three kills (#1031 ESS, #1045 r2/r3 leakage, #1051 provenance) apply to
CONDITIONING THE EXISTING LEGS — not to this design, which builds and
preregisters its own base layer. GOAL-2's linear estimand (w(state) on the
served blend) is the linear special case of this architecture; it remains
parked on the live-panel accrual clock and is not resurrected here.

## 0. The goal, verbatim (operator, 2026-08-24)

> 根据包括sector，regime，或者某些比如宏观数据（比如美债收益率趋势，vix指数，
> 等等各种factor）的trend，用不同模型算出各种数值，然后通过可以利用这些数值，
> 用xgb，或者transformer或者什么复杂模型来做一个基于多个模型的模型，做出最后
> 的结论。我认为为了做到这个，我需要把当前的数据粒度升级到10分钟级别或者更
> 小的粒度。然后我还希望这个模型能够支持我105--live trading。

Standard name for this architecture: **two-layer stacked generalization**.
Base layer = multiple models each emitting scores, with sector / regime /
macro-factor trends among the inputs. Meta layer = a learned combiner
(xgboost first; transformer staged) consuming the base outputs plus the
state features, emitting the final cross-sectional score. The meta model is
LEARNED — not fixed weights, not per-state routing; both are special cases
it can represent.

This section is frozen so the goal cannot drift again: two prior
instantiations (linear state weights; per-state routing) each narrowed the
operator's spec, and the second narrowing was caught only by the operator.

## 1. Why the three GOAL-2 kills do NOT bind this design

All three kills traced to one root: the EXISTING legs' recipes were selected
using outcomes from the very windows any historical validation needs
(sighunt 2018–2026; C3 2017–2026; WF corpus 2024–2026). This design's base
layer is NEW: every recipe is frozen in the Stage-A prereg BEFORE any fit,
selected from literature-standard forms plus 2024–2026 experience only —
which is exactly the "selection consumed 2024–2026 outcomes only" criterion
the merged h=20 design froze as its pass bar. The quarantined evaluation
window (2020–2023) therefore stays clean by construction, and its ESS was
already computed: **~16 non-overlapping h=20 blocks ≥ the bar of 12**
[VERIFIED — #1045 §3].

One-shot discipline throughout: one fit per base model, one OOF pass, one
meta fit, one evaluation. No retries; a nonsurvival is NOT-DEMONSTRATED per
the #1045 r4 label semantics (NO-EFFECT is not an available label).

## 2. Stage A — daily-frequency stack (executable now)

**Base layer (recipes frozen in the Stage-A prereg; 3–5 models):**

| family | form (frozen at prereg) | why this family |
|---|---|---|
| cross-sectional momentum | xgb on price/volume momentum features, h=20 label | the strongest documented factor family; our own 12-1 evidence is regime-conditional, which is exactly what the meta layer exists to learn |
| mean-reversion / quality | xgb on reversal + fundamental quality features | anti-correlated with momentum by construction; a stack needs disagreement to combine |
| regime-specialist | one xgb per regime bucket (train rows partitioned by PIT regime label) | the operator's state-conditioning intuition, expressed as base models |
| (optional) vol/dispersion | linear or shallow model on realized-vol features | cheap, orthogonal signal |

**State/macro trend features (meta-layer inputs, PIT-clean, daily, free
sources):** VIX level + 20d trend; 10y yield level + trend (FRED DGS10);
2s10s slope trend; sector breadth (fraction of watchlist sectors above their
50d MA); realized dispersion of the cross-section; regime label. Exact
transforms frozen in the prereg.

**Meta layer:** xgboost, depth ≤ 3, inputs = base scores + state features.
Transformer is Stage C — with ~16 evaluation blocks, a transformer meta
cannot be honestly selected at Stage A (statistical reality, recorded, not
conservatism).

**Protocol:** train base models on 2016-01..2019-12; generate OUT-OF-FOLD
base scores inside that window (5 temporal folds, embargo ≥ h) to train the
meta; freeze the full stack; evaluate ONCE on 2020-01..2023-12 against two
preregistered baselines — (a) the best single base model, (b) the equal-z
combination of the base scores. The claim tested: the LEARNED combiner beats
both on h=20 forward DGTW-adjusted cross-sectional skill.

**Kills (frozen):** feature coverage < 80% on either window; assembled panel
n_eff < 12 at h=20; any base recipe's provenance failing the 2024–26-only
criterion (0b-α discipline, applied to our own new recipes); meta beating
neither baseline → NOT-DEMONSTRATED, line closes.

## 3. Stage A′ — 10-minute data backfill (parallel, $0)

Aggregate Alpaca minute history to 10-minute bars for the ~150-ticker
watchlist, 2018→present (~12M rows, <1GB, no new vendor cost under the
current data subscription). Integrity checks: bar-count-per-session
completeness, split/dividend adjustment parity against the daily bars.
This stage only PROCURES; no model consumes 10-minute data before Stage B.
Rationale for the split: whether the stacked architecture carries signal is
decidable on daily data for a fraction of the cost; the 10-minute upgrade's
value concentrates in the 105-serving variant (Stage B), so the data is
readied in parallel rather than gating Stage A or being gated by it.

## 4. Stage B — intraday variant, supporting 105

On Stage-A survival: add 10-minute features (intraday momentum/reversal off
the A′ bars, VWAP deviation, intraday vol) to the surviving stack and
re-validate under the same one-shot discipline (historical 10-minute panel
from A′). The serving integration point ALREADY EXISTS: S3-P4's
observe-only entry loop consumes an intraday scorer through the shadow
serving lane — the surviving stack replaces/augments the current pinned
blend re-score there, accrues its own shadow evidence, and reaches live
entries only through the existing ladder (≥10 clean sessions → the
operator's explicit S3-c flip). No new pipeline is built for serving.

## 5. Stage C — transformer meta (on Stage-B survival)

Preregistered swap of the meta layer only (base scores unchanged), evaluated
on the accrued shadow panel plus the historical windows. Earlier is
statistically dishonest at this panel size.

## 6. Relationship to adjacent lines

* **G-I MoE (sector×regime routing, ≈Nov clock):** routes EXISTING
  production models per state cell. This design trains NEW base models and
  LEARNS the combination. Complementary; survivors of either feed the same
  allocation machine. Nothing here touches G-I's prereg.
* **GOAL-2 (linear blend weights):** parked on the live-panel clock
  (~2027-07); the linear estimand stays there and is not double-counted.
* **Repo boundaries:** model training internals land in renquant-model;
  feature/panel assembly in renquant-pipeline; orchestration + prereg +
  evaluation harness in renquant-orchestrator (same split the S3 ladder
  used, per-repo PRs named in the implementation plan).

## 7. What this design does NOT do

No production config change; no live serving of any Stage-A artifact; no
touch of the S3-c gate; no claim about 2024–2026 (that window remains
development-contaminated for HISTORICAL validation and is reserved for the
accruing live panels).
