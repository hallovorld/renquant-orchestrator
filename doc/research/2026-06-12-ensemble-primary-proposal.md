# Proposal — Ensemble Primary Scorer (PatchTST + GBDT + Quality)

**Status:** proposal / awaiting review (no code change here)
**Origin:** operator + agent debate (2026-06-12). Operator: "XGB's logic feels
dated; it should be shadow/ensemble material, not primary." Agent rebuttal:
architecture age is not evidence; adaptivity comes from retrain cadence, not
architecture; GBDT remains SOTA-competitive on tabular data (Grinsztajn et al.
2022); and **no single model should be primary at all** — our own measurements
say the combination beats every component. Operator verdict: *"我现在对于
ensemble 模型非常期待了"* → this proposal.
**Companions:** `2026-06-12-patchtst-capability-boundary.md` (§5 findings) and
the model-edge recovery workstreams now folded into the system feature map /
git history.

---

## 1. New facts from the fairness check (measured 2026-06-12)

1. **The XGB "+0.0909 vs +0.0706" same-val win is likely contaminated.** The
   prod XGB artifact (`panel-ltr.alpha158_fund.json`) is `trained_date
   2026-05-18` (weekly retrain) — its training window almost certainly overlaps
   the 2025-02→2026-02 validation year, so its same-val IC is partially
   in-sample. **The single-number "XGB beats PatchTST" headline from §5.1 must
   not be acted on directly.** A fair comparison requires identical strict-OOS
   cutoffs (folded into WS-2).
2. **However — the XGB artifact carries a PASSING walk-forward gate stamp:**
   `wf_gate_metadata.passed = true`, `wf_3cut_sharpe_mean = 0.646` (vs SPY mean
   1.081 over the same cuts; the gate's criteria were met at stamping time).
   This is point-in-time evidence via the proper 39–43-retrain GBDT manifests —
   the very evidence class PatchTST lacks (1 retrain, 2/3 cuts unexecutable).

**Implication:** the house already owns one gate-passing scorer family (GBDT,
with full PIT retrain infrastructure) and one scorer with capabilities GBDT
lacks (PatchTST: sequence modeling + a distributional σ head that measurably
ranks risk, Spearman +0.27 — the input Kelly sizing and σ-stops depend on).
Neither alone is the right primary. **Combine them.**

---

## 2. Why ensemble (evidence, not aesthetics)

| Evidence | Source |
|---|---|
| Zero-training 1/3 blend (PatchTST + asset_growth + roe) flips the dead window from IC **−0.09 → +0.14** | boundary doc §5.2, measured |
| Top-8 selection edge: full-year +0.264z but **−0.124z** in calm tape — single-model failure is economically real | boundary doc §5.3, measured |
| Forecast combination beats components under model uncertainty — one of the most robust results in forecasting | Timmermann (2006), *Handbook of Economic Forecasting* |
| GBDT ≥ DL on tabular; DL adds value via sequence/distribution heads — complementary, not substitutes | Grinsztajn et al. (2022); our own σ measurement |
| Qlib ensemble practice (average of LGB/linear/DL z-scores) as industry baseline | Qlib benchmarks |

Component roles:
- **PatchTST** — sequence patterns + the **only σ source** (risk ranking for Kelly/SDL).
- **GBDT (alpha158_fund)** — tabular cross-sectional ranking strength + the
  family with working PIT evidence rails.
- **Quality/slow factors (asset_growth, roe; later §2.5 sources)** — the only
  signals measured alive in calm tape (asset_growth IC −0.23 in the dead window).

## 3. Design

### 3.1 Score combination (v1: fixed weights, no fitting)
Per date, per ticker: `S = w_pt·z(PatchTST) + w_gb·z(GBDT) + w_q·z(Quality)`
with per-date cross-sectional z-ranks (rank → z), `Quality = z(−asset_growth)
+ z(roe)` averaged. **v1 weights: 1/3, 1/3, 1/3** — fixed, pre-registered, no
in-sample tuning (avoids the Bailey–LdP overfitting trap). μ/σ for sizing
continue to come from the PatchTST calibrated head (σ unchanged); the ensemble
replaces the **ranking** signal only. v2 (later, only if v1 passes): regime-
conditional weights, fitted on training-period data and gated again.

### 3.2 Integration point (minimal surface)
A new scorer `kind: "ensemble"` in the panel-scoring model registry that wraps
the two existing scorer artifacts + quality columns — config-gated, default
OFF. The shadow-scoring rail (#114, revived) runs it as a shadow first; primary
flip only after the gate passes. No new training infrastructure needed for v1.

### 3.3 Evidence plan (in order)
1. **Fair strict-OOS comparison** (prerequisite, rides WS-2): retrain GBDT and
   PatchTST at the SAME historical cutoffs; score the same val windows →
   honest per-component and ensemble ICs (full-year + calm-window).
2. **Backfill ensemble val study** (cheap, now): score the existing GBDT
   artifact lineage point-in-time (the 39-retrain manifests provide PIT GBDT
   scores) + existing PatchTST preds + panel quality columns → ensemble IC
   over 2025-02→2026-02 without any new training. Pre-registered metrics:
   full-year IC, dead-window IC, top-8 selection edge, per-regime IC.
3. **WF gate run** on the ensemble candidate (3 cuts + sanity battery): the
   recipe validator must require point-in-time inputs for every enabled
   component on every cut. If PatchTST is missing cuts 1–2, either complete
   WS-2 first or register a separately named GBDT+quality ablation; do not call
   a partial-component replay the full ensemble.
4. **Shadow period** (1–2 weeks daily shadow decisions via the #114 rail),
   then promotion decision by the operator.

### 3.4 Success criteria (pre-registered, same bar as any candidate)
- WF gate `passed=true` (absolute + benchmark-relative + sanity battery).
- Calm-window IC > 0 (the failure mode this is designed to fix).
- Top-8 selection edge positive in BOTH the full year and the calm window.
- No degradation of σ quality (σ stays PatchTST's; verify pass-through).
- Component coverage provenance is complete: every score stream used by the
  ensemble is point-in-time for the evaluated cut.

## 4. What this does NOT change
- The WF gate stays the sole promotion authority (no aesthetic promotions —
  in either direction; this includes not demoting GBDT for being "old").
- Buys remain blocked until **some** artifact passes; the fastest legitimate
  unblock may well be this ensemble, since GBDT's PIT evidence rails already
  exist while PatchTST's are being built (WS-2).
- Daily data pipeline (§6 of the boundary doc) and WS-1/2/3 proceed unchanged.

## References
- Timmermann (2006), *Forecast Combinations*, Handbook of Economic Forecasting.
- Grinsztajn, Oyallon, Varoquaux (2022), *Why do tree-based models still
  outperform deep learning on tabular data?*
- Bailey & López de Prado (2014) — pre-registered weights vs in-sample tuning.
- Cooper, Gulen & Schill (2008) — asset growth; Novy-Marx (2013) — quality.
- Qlib ensemble benchmarks (LGB/linear/DL z-average).
