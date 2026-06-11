# M6 diagnosis — the WF-gate time-shift placebo FAIL on the weekly GBDT is a label-persistence confound, not a concrete bug

**Date:** 2026-06-11 · **Author:** Claude (Fable 5) · **Status:** diagnosis, for review
**Milestone:** M6 (recovery + decoupling plan, `doc/plans/2026-06-09-recovery-and-decoupling-plan.md`)
**Scope:** root-cause of the §5.2 sanity-battery time-shift placebo FAIL on the
staged weekly `alpha158_fund` GBDT. **No gate code changed; no threshold touched.**

---

## 0 · Verdict (one line)

The §5.2 time-shift placebo FAIL on the staged weekly GBDT
(`placebo_ic=+0.0359` at the 2×horizon=120d gate shift, vs `threshold=+0.0285`)
is a **label-persistence confound of the placebo *metric*, NOT a concrete bug**
in the feature pipeline, label alignment, embargo, or the placebo harness — and
NOT the genuine PatchTST-class leak (placebo > real) from the 2026-06-02 audit.
Every component is independently verified correct. The correct remediation is the
**model/gate-architecture Layer-1b work (RFC #259)** already scoped in M6, not a
quick code fix. **Do NOT relax or raise the placebo threshold** — it must stay
strict; relaxing it would also pass a genuinely-leaky model.

This doc is the **orchestrator-side M6 follow-up record**. The full
gate-architecture verdict and the Layer-1b fix path live in the umbrella at
`RenQuant/doc/research/2026-06-10-m6-placebo-gate-verdict.md`; everything below
was **independently re-reproduced** with the shared venv on 2026-06-11 so the
control panel has a self-contained audit trail.

---

## 1 · The failure (reproduced 2026-06-11)

From the gate's `run_sanity_battery`
(`renquant-backtesting/src/renquant_backtesting/wf_gate/runner.py`):

```
§5.2 sanity battery (shuffled-label + time-shift placebo)
  shuffled_ic = -0.0005                                      → PASS (signal is REAL)
  placebo_ic  = +0.0359  at gate_shift=120d (2×horizon=60d)  → FAIL
  aligned_real_ic = +0.0570 ; threshold = +0.0285 (0.5×|aligned_real_ic|)
  ratio placebo/aligned_real = 0.630
Sanity result: FAIL: placebo_ic=+0.0359 (must be < +0.0285)
```

**Gate code paths (file:line):**

- Threshold rule: `runner.py:154-156` —
  `_placebo_ic_threshold = max(0.005, 0.5*|aligned_real_ic|)`.
- Time-shift loop and gate-shift selection: `runner.py:2281-2361`. The gate shift
  is `2 × label_horizon` (`runner.py:2299`: `_gate_shift_days = 2*_label_horizon`);
  for `fwd_60d_excess` that is 120 trading-day rows.
- Pass criterion: `runner.py:2486-2494` (`pass_placebo`).
- Per-date cross-sectional Spearman IC primitive: `runner.py:2265-2269` (`cs_ic`).
- The canonical shift methodology (same one the Layer-1a profiles use):
  `renquant-backtesting/src/renquant_backtesting/analysis/analyze_manifest_sanity_placebo.py:101-164`
  (`shift_diagnostics`), shift at `:121`
  (`panel_s.groupby("ticker")[label].shift(-int(shift_days))`).

**Asymmetry is the first tell:** the *shuffled-label* placebo PASSES (`-0.0005`,
kills all structure → signal is real) while only the *time-shift* placebo fails.
A failing time-shift placebo *alone* is the classic signature of a **persistent
target**, not a leaky model.

## 2 · Independent reproduction — it is the overlapping-label autocorrelation confound

All numbers below regenerated 2026-06-11 with
`/Users/renhao/git/github/RenQuant/.venv/bin/python`.

### 2.1 · The panel is daily-sampled; the label is a 60-day overlapping window

`data/alpha158_291_fundamental_dataset.parquet`: 716,607 rows, 292 tickers,
**2,541 distinct dates with a dominant 1-trading-day gap** (daily sampling). The
training/gate label is `fwd_60d_excess`, built in
`RenQuant/scripts/build_alpha158_qlib.py:350-353` as
`fwd_ticker = close.shift(-n)/close - 1` minus the SPY leg, for `n=60`. A
60-trading-day forward return sampled daily means **adjacent rows of the same
name share up to 59/60 of their realization path** → strong serial correlation by
construction (López de Prado, *AFML* 2018, Ch. 4: concurrent/overlapping outcomes).

### 2.2 · The label is autocorrelated *exactly* at the gate's shift point

`repro_m6_placebo_confound.py --mode autocorr` on
`data/alpha158_291_fundamental_dataset_rawlabel.parquet` (per-date cross-sectional
`corr(label_t, label_{t-lag})`, n≈2,400+ dates), **reproduced 2026-06-11**:

| label | horizon | AC@1×h | **AC@2×h (gate shift)** | AC@3×h |
|---|--:|--:|--:|--:|
| fwd_5d_excess | 5 | −0.0113 | **−0.0009** | −0.0019 |
| fwd_20d_excess | 20 | −0.0137 | **+0.0093** | +0.0083 |
| **fwd_60d_excess** (prod) | 60 | +0.0362 | **+0.0489** | +0.0356 |

**Only the production label is autocorrelated at the 120d gate shift (+0.0489).**
For `fwd_5d`/`fwd_20d` the 2×h-shifted label is decorrelated (≈0), so their
time-shift placebo cleanly isolates leakage — but for `fwd_60d` the shifted label
still correlates at +0.0489, so a model that genuinely ranks forward returns
*necessarily* scores positive against the shifted labels too.

### 2.3 · The model placebo does not even exceed the label's own persistence floor

Independent val-partition check (last 20% of dates — the same partition the gate
scores — using a label-only oracle through the gate's own shift harness),
**reproduced 2026-06-11**:

```
shift=60d   label_autocorr_ic (real_t vs real_{t+shift}) = -0.0208   (n=129,546)
shift=120d  label_autocorr_ic (real_t vs real_{t+shift}) = +0.0422   (n=112,026)
```

The model's placebo IC at the 120d gate shift is **+0.0359, BELOW the label's own
+0.0422 persistence floor** on the same partition. There is **no excess signal
beyond label persistence** for the placebo to attribute to model leakage.

### 2.4 · The decisive regime discriminator: placebo IC tracks label autocorr, r=+0.993

`repro_m6_placebo_confound.py --mode regime` against the stamped failing artifact
(`backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.weekly_20260610T201007Z.staging.json`,
`metadata.wf_gate_metadata.model_placebo_profile`), **reproduced 2026-06-11**:

| regime | placebo_ic | label_autocorr_ic | aligned_real_ic | genuine_ic | n_dates |
|---|--:|--:|--:|--:|--:|
| BEAR | −0.0206 | +0.0223 | +0.2719 | +0.2925 | 49 |
| BULL_CALM | +0.0413 | +0.0422 | +0.0302 | **−0.0112** | 302 |
| CHOPPY | +0.0433 | +0.0403 | −0.0097 | **−0.0530** | 26 |
| **POOLED (gate point, 2×=120d)** | **+0.0359** | **+0.0390** | **+0.0570** | **+0.0211** | — |

**`corr(placebo_ic, label_autocorr_ic)` across regimes = +0.993.** The model's
placebo IC is, regime for regime, almost perfectly explained by the *target's own*
autocorrelation. Genuine leakage (the model peeking at future info independent of
label persistence) would put placebo HIGH where label autocorr is LOW — the
opposite of what is observed. This is a **confound signature, not a leakage
signature.** (Per the umbrella verdict and the codex review on PR #52, r=+0.993 is
*supporting* evidence, not a standalone leakage-exoneration proof — §2.5/§3 below
close the remaining leakage paths directly.)

### 2.5 · The CV is structurally leakage-safe — embargo = horizon, verified to the trading day

From the failing artifact: `cv_method=purged_walk_forward`, `cv_embargo_days=60`,
`lookahead_days=60`, `label_col=fwd_60d_excess`. Measuring the actual fold gaps in
**trading days** against the panel's own trading calendar (**reproduced 2026-06-11**):

```
train_end=2018-04-17 -> val_start=2018-07-13 : gap = 61 trading days  (lookahead=60)
train_end=2020-10-22 -> val_start=2021-01-21 : gap = 61 trading days  (lookahead=60)
train_end=2023-05-03 -> val_start=2023-08-01 : gap = 61 trading days  (lookahead=60)
```

**Embargo = 61 ≥ 60-day horizon in every fold** — the AFML-Ch.7 minimum to prevent
train/test label overlap. `oos_per_fold_ic = [+0.087, −0.011, +0.056]` (genuinely
positive in 2/3 folds); `training_train_ic=0.124` vs `oos_mean=0.044` (2.8× gap =
ordinary overfit, not catastrophic). No embargo bug; no fold contamination.

### 2.6 · No forward-looking features; label never enters the feature space

The 172 `feature_cols` are the standard alpha158 (Qlib) set — K-bar, ROC, MA, STD,
BETA, RSI, RANK, etc. — **all backward-looking**. A regex scan for
`fwd|future|lead|ahead|next|target|label|tomorrow` over the feature names returns
**zero** matches. The forward label uses `close.shift(-60)` (correct for a *label*:
it is the prediction target, never a feature), and is computed in a separate label
frame (`build_alpha158_qlib.py:324-354`) that is joined only as the `y` target.

## 3 · This is NOT a concrete bug (the four candidate bug classes, each ruled out)

| Candidate bug (per M6 task) | Verdict | Evidence (file:line / reproduced number) |
|---|---|---|
| (a) forward-looking feature | **ruled out** | 0 forward-named features; alpha158 set is backward-looking (§2.6) |
| (a) embargo gap too small | **ruled out** | embargo = 61 trading days ≥ 60 horizon, all folds (§2.5) |
| (a) label-alignment bug | **ruled out** | `fwd_60d_excess = close.shift(-60)/close-1 − SPY-leg`, used only as target (`build_alpha158_qlib.py:350-353`) |
| (b) placebo-harness bug (wrong shift/axis/look-ahead) | **ruled out** | shift is per-ticker `groupby("ticker")[label].shift(-shift_days)` (`analyze_manifest_sanity_placebo.py:121`), aligned by `(ticker,date)` MultiIndex intersection (`runner.py:2318-2332`); `genuine_ic = aligned_real − placebo` arithmetic correct (`runner.py:2017`); 32/32 placebo+M6 unit tests pass |
| (c) threshold/config artifact | **the metric is mis-specified, but the fix is NOT to change the constant** | the `0.5×aligned_real` rule (`runner.py:154-156`) implicitly assumes the shifted label is *decorrelated*; that holds for fwd_5d/fwd_20d but is **false for daily-sampled fwd_60d** (§2.2). Charging the model for the *label's* +0.049 persistence floor as if it were *model* leakage is the confound. **Fix = subtract the empirical persistence baseline (Layer-1b), not loosen the multiplier.** |

The placebo harness is **correctly measuring a real statistical property** of an
overlapping-window label. There is no off-by-one, no axis flip, no look-ahead in
the test harness. So there is no concrete code bug to patch — confirmed against the
32 green tests in `renquant-backtesting/tests/wf_gate/` (`test_m6_placebo_confound_repro.py`,
`test_placebo_gate_horizon.py`, `test_layer1a_diagnostic_profiles.py`).

## 4 · Contrast with the 2026-06-02 PatchTST leak (different class — does not transfer)

The 2026-06-02 experiment-validity audit
(`RenQuant/doc/research/2026-06-02-experiment-validity-audit.md`) found PatchTST
`B_tuned` leak-contaminated with **`timeshift_placebo +0.067 > real_ic +0.044`**
(ratio > 1) — a sequence-boundary leak crossing the `seq_len=24` window across the
train/val cut. The GBDT here is the **opposite signature**: placebo
`+0.0359 < aligned_real +0.0570` (ratio 0.63), placebo tracks label persistence,
and per-fold OOS IC is genuinely positive. **The two failures are not the same
class; the PatchTST finding does not transfer to the GBDT panel.**

## 5 · Recommended remediation (M6 model/gate-architecture work — NOT a quick fix, NOT a threshold change)

Implement the **RFC #259 Layer-1b distribution-calibrated gate** (full spec in
`RenQuant/doc/research/2026-06-10-m6-placebo-gate-verdict.md` §4). The Layer-1a
inputs it needs are **already computed and stamped** (`model_placebo_profile` with
per-date `n_dates`; `summarize_ic` returns per-date IC series + std), so no new
heavy compute. In outline:

1. Form per-date `genuine_ic_d = aligned_real_ic_d − placebo_ic_d` at the
   2×-horizon shift (nets out the label's own persistence by construction).
2. Block-bootstrap over dates (seed-pinned) the mean of `genuine_ic_d`; take the
   5% lower confidence bound (LCB).
3. **PASS iff `LCB(genuine_ic) > genuine_ic_floor`**, where the floor is fixed from
   the label's empirical persistence distribution **and** trading economics — never
   reverse-engineered to pass today's model.
4. Keep `shuf_ic` (|·| < 0.005) as an **independent hard gate** — it stays.
5. Require the LCB-positive condition **per production-dominant regime**; do not
   pool-average away a regime where `genuine_ic` is negative.

This stays fail-closed (a genuinely-leaky model with placebo > real has
`genuine_ic ≤ 0` → LCB ≤ 0 → FAIL) and removes the persistence penalty without
touching the strict shuffle gate.

Cheapest correct hardening to land first (Layer 2a): add **`fwd_20d_excess` as a
secondary sanity acceptance target** — its 2×h autocorr is +0.009 (≈ decorrelated),
so its time-shift placebo is *valid by construction* and is a clean second trust
boundary; the `fwd_60d` *training* label stays.

## 6 · Residual trading-risk flag (operator decision, separate from the leakage question)

Even with a correct Layer-1b gate, the per-regime decomposition (§2.4) shows the
GBDT's genuine alpha is **concentrated in BEAR (+0.29 genuine_ic, 49 dates)** and is
**negative in BULL_CALM (−0.011, 302 dates) and CHOPPY (−0.053, 26 dates)** — i.e.
in the production-dominant regime the model carries no genuine forward alpha beyond
momentum persistence. The live `P-REGIME-IC` gate already fails BULL_CALM/CHOPPY for
exactly this reason. A corrected placebo gate therefore does **not** auto-resume
buys; whether to be in-market with a momentum-tilted model in BULL_CALM is a
capital-allocation choice that must **not** be smuggled in by tuning the leakage
gate. Earn that tilt down via regime-specialist signal research, not gate relaxation.
This maps to the plan's M3 decision point (revert primary to XGB, gate + stamp,
PatchTST → shadow until leak-clean) being an operator call, not an agent bypass.

## 7 · What would falsify this diagnosis (re-open triggers)

- A future panel build with `embargo < horizon`, OR a feature computed with a
  forward window → that *would* be genuine leakage; re-open. (Current build:
  embargo = 61 ≥ 60, no forward features — ruled clean, §2.5/§2.6.)
- After Layer-1b, if pooled `LCB(genuine_ic)` is **not** > the economics floor →
  honest conclusion is "no tradeable alpha beyond momentum" → signal research, not
  gate-tuning.
- The +0.0489 autocorr is the *target's* property; the +0.0359 placebo is the
  *model's* persistence-contaminated IC inheriting it — related but distinct, and
  there is no closed-form floor (`0.049 × 0.059 = 0.0029 ≪ 0.0359`). Layer-1b must
  estimate the baseline empirically from the same panel, not a derived constant.

## 8 · Reproduction commands

```bash
PY=/Users/renhao/git/github/RenQuant/.venv/bin/python
PP=/Users/renhao/git/github/renquant-backtesting/src
cd /Users/renhao/git/github/RenQuant

# (a) label-autocorr decay — the root data (§2.2)
PYTHONPATH=$PP $PY -m renquant_backtesting.analysis.repro_m6_placebo_confound \
    --mode autocorr --rawlabel data/alpha158_291_fundamental_dataset_rawlabel.parquet

# (b) regime placebo↔autocorr discriminator from the STAMPED artifact (§2.4)
PYTHONPATH=$PP $PY -m renquant_backtesting.analysis.repro_m6_placebo_confound \
    --mode regime \
    --artifact backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.weekly_20260610T201007Z.staging.json

# (c) gate placebo + harness unit tests
cd /Users/renhao/git/github/renquant-backtesting && PYTHONPATH=src $PY -m pytest \
    tests/wf_gate/test_m6_placebo_confound_repro.py \
    tests/wf_gate/test_placebo_gate_horizon.py \
    tests/wf_gate/test_layer1a_diagnostic_profiles.py -q
```

**Related:**
`RenQuant/doc/research/2026-06-10-m6-placebo-gate-verdict.md` (full gate-architecture verdict + Layer-1b spec) ·
`RenQuant/doc/research/2026-06-08-overlapping-label-and-gate-architecture/` (RFC #259) ·
`RenQuant/doc/research/2026-06-02-experiment-validity-audit.md` (the different-class PatchTST leak) ·
`doc/plans/2026-06-09-recovery-and-decoupling-plan.md` (M6).

Agent-Origin: Claude
