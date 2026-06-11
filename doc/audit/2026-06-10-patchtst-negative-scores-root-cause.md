# PatchTST all-negative scores — the real root cause of sell-only (2026-06-10)

**Trigger:** post-merge verification of the decision-tree audit fixes (BL-1..BL-4, H-1/H-2). Operator: re-run daily-full to prove the fixes add value.
**Method:** ran the *merged* scoring path over the **real 142-name watchlist** with **real OHLCV asof 2026-06-10**, the prod PatchTST model (`pt07_strict_trainfit_embargo60_20260522/seed_44`) and its calibrator. Reproducible: `scripts/verify_bl1_scores.py`, `scripts/verify_score_to_signal.py`, `scripts/verify_gate_admissions.py`.

## Headline

**The model is fine. The buy gate was wrong.** BL-1 (CSRankNorm cross-section) was correct plumbing but did **not** make scores positive — and could not. The real root cause of structural sell-only is the signal-direction gate assuming `raw = 0` is neutral.

## What the real data showed

| quantity | value (142 names, asof 2026-06-10) |
|---|---|
| raw PatchTST score range | **[−0.27, −0.07]**, median −0.19, **0% positive** |
| extra features (fundamental/PEAD/sentiment) | healthy, 74–100% non-zero (not a data artifact) |
| calibrator ER=0 neutral (`neutral_raw`) | **−0.198** |
| calibrated μ range | [−0.034, **+0.059**], **56% > 0** |
| calibrated P(outperform) | [0.40, 0.65] |

### Admission counts through the real `long_signal_ok` predicate
| direction gate | new longs admitted (of 142) |
|---|---|
| `raw > 0` (legacy, PR #81) | **0** — book can never open a long |
| `μ > 0` (calibrated) | **80** |
| `raw > neutral_raw` (−0.198) | **80** |

Top admitted (μ-ranked): DDOG, SMCI, FTNT, DELL, QCOM, CRWD, TEAM, NOW, COHR, RBLX, MU, LITE, INTC, SNOW, PLTR (μ +3.5…+5.9%, P 0.59…0.65).

## Why the scores are all-negative (Part 2 investigation — BENIGN)

Model metadata: `label_col = fwd_60d_excess`, CSRankNorm features, distributional head. **OOS IC ≈ 0.13** (`pool_ic` / `scorer_oos_mean_ic` — the ~0.1 the operator remembered; `val_ic = 0.03` is a separate pessimistic split). Per-regime IC positive everywhere (BEAR 0.19).

PatchTST is a cross-sectional **ranker**: the output head sits at an arbitrary offset (~−0.20) and only the **relative ordering** carries signal. The Platt calibrator is exactly the tool that corrects the offset — its neutral is at raw −0.198, and the **2026 live output still aligns with the 2023–24-fit neutral** (stable, not drifting). So the negative level is **benign**, not a defect; **no retraining or sign-fix is needed.**

## The operator's intuition, recalibrated

"负数的ticker还做多？疯了" is correct **for a zero-centred model**. This model centres at −0.198, so *every* name is negative and "don't long negative" collapses to "never long." The scientific rule the calibrator already encodes: **long names with positive calibrated expected return (μ>0 ⇔ raw>neutral_raw)** — i.e. ranked *above the model's own neutral*, not above zero.

## Fix (shipped, behind a flag, default OFF)

- **Pipeline PR #98** — `ranking.panel_scoring.signal_gate_prefer_calibrated_mu` (default OFF). When ON and a calibrated μ is present, the direction test is `μ>0` alone; the `raw>0` conjunct is not applied. Falls back to the raw gate only when μ is absent.
- **strategy-104 PR #21** — flips the flag ON in active + golden (operator go-ahead). No-op until #98 merges **and** the subrepo pin is bumped; the live runner reads the pinned checkout.

## Correction to the audit synthesis

`doc/audit/2026-06-10-decision-tree-deep-audit.md` framed **BL-1** as "the root of every score negative." That is **superseded**: BL-1 is a real, correct improvement (rank over the trained cross-section, not 3 post-gate names), but it is **not** why scores are negative — the negative offset is an intrinsic, benign property of the ranker. The operative root cause of sell-only is the `raw>0` gate, fixed by #98/#21.

Agent-Origin: Claude
