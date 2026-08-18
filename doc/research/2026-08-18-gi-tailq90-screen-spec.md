# G-I candidate `tail_q90_60d` — FROZEN screen spec (before any training or scoring)

STATUS: **frozen experiment spec (docs only — the run happens AFTER this merges AND the
committed runner is reviewed).** DATE: 2026-08-18. The fourth and highest-prior screen
candidate: a quantile-regression (q=0.90) learner on the EXISTING panel, targeting the
account's PROVEN tail-driven top-decile skill (DGTW t=2.92) that the production
rank objective dilutes. Sequencing lesson applied: this candidate should have been built
FIRST (highest prior), not last (cheapest first) — prior declared here, before any run.

## 1. Family + corpus-exposure declaration

- **New candidate family** (`tail_q90`): its own one-shot budget. This is NOT a re-run of
  the #987 emitter family (whose budget was spent by #992).
- **Corpus exposure ledger** (per the #984 exposure-counting convention): this is the
  **2nd family** screened on the 2019-01-14..2026-03-02 weekly corpus (1st: the three
  #987 emitters, verdict 0/3 FLAGGED). The screen stays kill-only (admits nothing), so
  corpus reuse cannot manufacture an admission; the confirmatory Holm family in #984 §5b
  spans the full candidate manifest including every screen failure.

## 2. Frozen candidate definition (delta from production, everything else verbatim)

Base = the production core recipe as pinned by the served artifact
`artifacts/prod/panel-ltr.alpha158_fund.json` (config fingerprint sha256:f8fb2259b2bf1537):
- **Features**: the artifact's 172 `feature_cols` + per-column `feature_norm_kind`,
  VERBATIM.
- **Label**: `fwd_60d_excess` (the panel's existing label; `lookahead_days=60`) —
  zero new data preparation.
- **Learner params**: the artifact's params dict VERBATIM (max_depth, eta, subsample,
  colsample_bytree, min_child_weight, seed) with EXACTLY ONE delta:
  `objective: rank:pairwise → reg:quantileerror` with `quantile_alpha: 0.90`
  (XGBoost native pinball loss; the runner asserts the installed xgboost supports it and
  fails closed otherwise).
- **Score** = predicted q90 of 60d forward excess return (upside-tail forecast), emitted
  RAW; serve-time z-scoring is monotone and Spearman-invariant.
- Name: `tail_q90_60d` (training-label horizon in the name; the earlier working name
  tail_q90_20d is retired — the panel has no 20d label and building one would break the
  zero-new-architecture constraint).

## 3. Frozen PIT scoring calendar (the learner's version of "an emitter")

- **Refit cutoffs**: the last trading day of each calendar quarter, 2018-Q2 .. 2025-Q4
  (31 refits). Training window: expanding, from the data start (2016-01-04) to the
  cutoff. Training universe: the corpus watchlist (§4), rows with realized labels only.
- **Embargo**: at scoring date d, use the NEWEST refit whose cutoff C satisfies
  **C + 60 trading days ≤ d** (the training label horizon; no training-label overlap
  with the scoring date). No exceptions, no gap-filling with newer models.
- **Determinism**: fixed seed (the artifact's), fixed calendar, no early stopping on
  future data, no hyperparameter search of any kind. ~31 local trainings, $0, no cloud.

## 4. Corpus, estimand, and kill rule — IDENTICAL to #987 (no re-derivation)

Corpus (verbatim #987 §2): weekly cross-sections 2019-01-14..2026-03-02 (359 kept dates
as measured by #992), current 145-name watchlist, survivorship caveat carried (kills
valid, passes non-confirmatory), NAMES_PER_DATE_FLOOR=50.
Estimand (verbatim #987 §3, with the #990 pairing correction): PAIRED-cross-section
weekly Spearman IC of the RAW score vs h-day forward excess over SPY, h=20 primary /
h=60 informational; placebo = the same scores lagged 2h trading days; decision quantity
Δ = mean(genuine) − mean(placebo).
Inference + kill rule (verbatim #987 §4-5): block-t over the 89 non-overlapping 20d
blocks; **SURVIVES iff Δ>0 AND block-t ≥ 1.0 AND >50% of blocks-with-data positive, at
h=20** — else FLAGGED (triage semantics: deprioritized; PIT-universe rerun before any
formal kill). ONE execution; whatever comes out is final for this corpus. No horizon
rescue, no calendar tweak, no rerun.

Honest power context (counted before the rule, from #987 §4): n_eff ≈ 51 at h=20 — a
true-but-small edge can fail t≥1.0 here; that risk is accepted as the kill-only
asymmetry, unchanged from the emitter family.

## 5. Also measured (informational)

Pairwise Spearman ρ of `tail_q90_60d` scores vs `multifactor_core`-proxy where cheaply
reachable, and vs `mom_slow_12m` / `mom_fast` on common dates — for the |ρ|<0.7 roster
gate applied at prereg, not here. NOTE the specific risk for THIS candidate: it shares
all 172 features and the label with `multifactor_core` — only the objective differs — so
HIGH ρ is the expected failure mode; declaring it here prevents post-hoc surprise
framing. If core-score history is unreachable without heavy compute (the #992 named
gap), a same-recipe rank:pairwise refit at the SAME frozen cutoffs MAY be trained purely
as the ρ reference (declared here; its scores are used for ρ only, never screened).

## 6. Execution contract (the #990 lesson, applied prospectively)

The deterministic runner is committed AND REVIEWED (its own PR) BEFORE the run — the
freeze-then-review-then-run sequencing that the emitter-family pilot lacked. Guards it
must carry: byte-identity of runner vs main at execution; refit-calendar assertion (31
cutoffs); embargo assertion per scoring date; paired-cross-section assertion (G7-class);
date/block-count assertions; emitter-independence (this family touches no
renquant_model_factors code). Results land as their own PR: verdict table first, refit
ledger (per-cutoff train-row counts + model digests), ρ section, every number
provenance-tagged.
