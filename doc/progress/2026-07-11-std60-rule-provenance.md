# Progress — STD60 rule provenance (deepest-layer root cause of the META fade)

- **Date:** 2026-07-11 (revised 2026-07-11, same day, per Codex review — see "Revision"
  section below)
- **Scope:** research only — investigate where the live XGB's low-STD60→bearish rule came
  from in the training data and whether it was ever valid OOS. Follow-up to #475
  (META score attribution). No code, no config, no gate changes.
- **Deliverable:** `doc/research/2026-07-11-std60-rule-provenance.md`.

## What was done (original pass)

- Established the live booster's exact training window from the artifact + corpus
  (row-count match): full-panel fit, 2016-01-04 → 2026-04-08, label = CS-z of fwd-60d
  excess vs SPY.
- Investigated four hypotheses with per-date cross-sectional analysis of the actual
  training corpus + OHLCV-recomputed raw labels + HMM regime labels, plus the artifact's
  own WF-gate record (framing corrected below — originally reported as a root-cause
  verdict; now hypotheses pending a preregistered test plan):
  - **H1 class confusion: refuted** on an in-corpus descriptive check (low-STD60 is 66%
    uptrend names, and the uptrend/near-high subset had the *worst* in-corpus forward
    returns). Surviving hypothesis: survivorship bias (0 delisted names; 42% of
    high-STD60 rows from eventual ≥5x survivors).
  - **H2 regime generalization — live hypothesis, not validated.** Rule's in-corpus edge
    concentrates in BEAR/BULL_VOLATILE/rebound years (2020 +0.213, 2023 +0.117,
    2025 +0.122); near zero 2021/2022/2024; BULL_CALM 2026 in-corpus IC −0.088 (hit 0.15,
    n=20 dates). Post-training OOS is underpowered (4 mature 60d-matched dates) and the
    June-window figure is a 20d-truncated calculation, not comparable to the trained 60d
    target — both are now labeled descriptive-only, not evidence of inversion.
  - **H3 feature mis-specification — mechanical decomposition independently verified;
    causal mechanism not established.** META fade week: 101% of the STD60 decline is the
    price denominator; returns-vol rose +4.8% and stayed above the panel mean (this
    decomposition was independently recomputed from OHLCV in the 2026-07-11
    evidence-sealing pass). FTNT's "92% trend component" figure remains as-reported, not
    independently reproduced.
  - **H4 governance — confirmed process fact, independently re-verified this session
    directly from the live artifact's `wf_gate_metadata`.** The live booster failed its
    own gate on this failure mode (BULL_CALM regime-IC FAIL, monotonicity inverted
    −13.7pp) and reached primary via the 2026-07-06 freshness `manual_override`; the
    07-05 candidate failed identically and was correctly NOT overridden. This is a
    governance fact, not proof of which mechanism (H2 or H3) explains the mis-score.
- Settled the operator's literal question: **no short position/order/intent on META ever**
  (ledger actions are buy/sell only; `long_short.enabled=false`; book = MU/GRMN/AVGO). This
  part is a direct ledger/config fact and was not affected by the revision.
- Candidate hypothesis list with owners/effort (returns-vol feature, trend-interaction
  features, per-feature regime screen at training, regime-scoped override consequences on
  the #467 weekly rail, survivorship remediation, ledger cohort tracking) — relabeled below
  from "fix menu" to "candidates for a test plan," per the revision.

## Revision 2026-07-11 (Codex review response)

Codex posted CHANGES_REQUESTED on the original head commit, with four findings:

1. **Reproducibility:** the computation lived in uncommitted scratch scripts
   (`std60_provenance.py`, `std60_followup.py`) against mutable local OHLCV/DB files —
   not a sealed, citable evidence trail.
2. **OOS underpowered:** the four mature 60d OOS entry dates cannot establish a regime
   conclusion; the June→July 20d-truncated calculation is not comparable to the trained
   60d target and must be descriptive-only.
3. **Post-hoc selection / data snooping:** the era/regime/feature screens are selection on
   the same corpus with no preregistered, selection-adjusted inference plan (White,
   *A Reality Check for Data Snooping*).
4. **Mechanism not established:** univariate STD60 IC plus PDP/SHAP-style reasoning cannot
   establish an unconditional causal rule was learned, given correlated features and PDP's
   off-manifold extrapolation behavior (Apley & Zhu).

**What was corrected in `doc/research/2026-07-11-std60-rule-provenance.md`:**

- Replaced the "Verdict (bottom line first)" section and the H1-H4 "REFUTED/SURVIVES"
  table with a "Hypotheses (bottom line first) — not a verdict" framing; H1 stays
  "refuted" (Codex's own suggested framing keeps this label), H2/H3 are now explicitly
  "live hypothesis, not validated," and H4 is labeled "confirmed governance/process fact"
  (re-verified directly from the artifact) rather than a causal-mechanism claim.
- Added an explicit OOS-underpowered caveat in §2: the 4-date 60d-matched OOS window and
  the 20d-truncated June figure are now both marked descriptive-only; removed language
  implying the rule "inverted" OOS.
- Added an explicit post-hoc-selection/data-snooping caveat in §1 and §2 covering the
  quintile cuts, distance bands, and year/regime buckets.
- Added an explicit mechanism-not-established caveat in §3: the numerator/denominator/
  returns-vol decomposition for META was independently reproduced from OHLCV in this
  session (verified), but the claim that the fitted booster's learned response is driven
  by this channel (as opposed to a correlated proxy) still requires conditional ALE/SHAP,
  local support counts, grouped-attribution residuals, and frozen-model ablations — none
  of which have been run.
- Relabeled §5 from "Fix menu" (F1-F6, with a "recommended path") to "Candidate hypotheses
  for the test plan" (C1-C6) — removed the promotion/recommendation framing; nothing here
  should be built ahead of the preregistered plan.
- Added new §7 "Required next artifact": the preregistered, cross-repo experiment design
  Codex asked for — ownership split across renquant-model (feature/ablation),
  renquant-pipeline (training metadata), renquant-base-data (coverage/survivorship),
  renquant-artifacts (sealed evidence), renquant-orchestrator (experiment ledger);
  baseline-vs-returns-vol/trend-redesign comparison required before any MoE/regime-gated
  architecture is considered, with an explicit MoE bar (stable ex-ante regime
  interactions, sufficient expert occupancy, gate stability, double-OOS vs. the simpler
  redesign).
- Added §6 "Evidence sealing and reproduction status," splitting exactly what was
  independently re-verified in the 2026-07-11 sealing session (model identity, the full
  wf_gate_metadata record, the META STD60 mechanical decomposition — all re-derived
  directly from the live artifact/OHLCV/corpus files, read-only) from what remains
  sealed **as-reported only** (the §1/§2 quintile and per-year/regime IC tables, the FTNT
  trend-decomposition figure, the cross-sectional rank-correlation figure) because the
  original scratch scripts that produced them are not available to re-run.
- Sealed a content-addressed evidence bundle in `renquant-artifacts` covering the
  independently-verified facts above, with explicit manifest notes on what is
  reconstructed/as-reported rather than independently reproduced (see PR link in the
  orchestrator PR body).

## Method / safety

- READ-ONLY on all production paths (runs DB opened `mode=ro`; corpus/OHLCV/artifacts read
  only). No git in the live umbrella tree or primary checkouts; authored in an isolated
  orchestrator worktree. Local compute only (no Modal). The 2026-07-11 re-verification pass
  read the live umbrella tree's artifact/OHLCV/corpus files read-only (no writes, no git
  operations) to independently re-derive the facts listed in the revision above.
- Statistics: overlap-adjusted t-stats (n_eff = n_dates/horizon); Spearman/quintile results
  invariant to the corpus's z transforms; raw economics recomputed from OHLCV.

## Memory-tier touch

- SHORT/MID: this doc is the durable record. Corrected framing: the low-STD60 rule's
  origin is a set of **live hypotheses** (H1 refuted on a descriptive check; H2/H3
  regime-confusion and feature-mis-specification remain unvalidated; H4 governance-FAIL
  confirmed), not an established root cause. The preregistered cross-repo test plan (§7 of
  the research doc) is the explicitly open item — nothing here justifies a feature or
  training-pipeline change yet.

## Next

- The preregistered, cross-repo experiment design (§7): renquant-model owns the
  feature/ablation harness and conditional ALE/SHAP tooling; renquant-pipeline owns
  training-metadata provenance for the walk-forward split; renquant-base-data owns
  coverage/survivorship; renquant-artifacts owns sealed evidence for the new run;
  orchestrator owns the preregistration document and comparison report. This has not
  started. C4 (#467 rail override-consequence wiring) and C6 (forward-validation ledger
  cohort) can be discussed on governance/evidence-accumulation merits independent of that
  experiment; C1/C2/C3/C5 (feature and corpus changes) should wait for it.
