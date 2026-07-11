# Progress — META score attribution deep dive (2026-07-11)

## What

Mechanistic attribution of why the live XGB panel's META score FELL (raw −0.047 → −0.176,
60d mu 0.019 → 0.006) across 2026-07-06..07-10 while META rallied +11.5%. Follow-up to the
META no-buy forensics (PR #473); operator framed it as "根本问题".

## Outcome (original submission — see Correction below, which supersedes this)

**Verdict: LEARNED model behavior, not a serving artifact.** STD60
(`rolling_std(close,60)/current_close` — price in the denominator) explains 74% of the
decline: the rally itself deflated META's dispersion feature across 29 learned split
thresholds sitting at the training mean. Panel-wide the same mechanism moved the whole
cross-section (33% of META's Δ common / 67% idiosyncratic on the 37-name common set).
Not anti-momentum: the model simultaneously top-ranks FTNT (+98%/60d) because its
dispersion is huge. Full evidence, SHAP tables, partial-dependence proof, and the
fundamentals-coverage finding in `doc/research/2026-07-11-meta-score-attribution.md`.

Key checks [VERIFIED]:
- Same model all week (sha `5211f6be…` in all 3 run bundles == file on disk == weekly
  rollback copies).
- Offline reproduction of recorded `raw_panel`: corr 0.983-0.984 per day; META delta
  reproduced at 95%.
- Fund-freshness clip bug (base-data #26 / pipeline #151): fixed AND feed rebuilt
  (axis to 2026-07-10). NEW finding: ey/b2p/gp coverage is broken (META never finite;
  67-317 of 826 finite) → median-imputed = valuation-blind.
- `demean_cross_sectional: false` in pinned + live config — the 06-25 monitored
  exception is no longer active; recorded mu has no demean (memory note stale).

## Correction (post-Codex-review, 2026-07-11 — this section is the current state)

Codex reviewed orchestrator PR #475 (CHANGES_REQUESTED) and found the verdict above
overclaimed causal/economic conclusions the evidence doesn't support. Codex's six
points, all accepted as correct:

1. Reproduction parity (mean |diff| ≈0.025 vs META's 0.124 move) is material, not
   sealed to a rigorous bound (max error, rank/gate agreement, SHAP additivity
   residual), and correlation 0.983 doesn't validate row-level attribution.
2. **STD60 is a price-level coefficient of variation, not return volatility** — a
   rising terminal price mechanically shrinks it even with flat return-risk. This is
   a feature-definition confound the original doc did not distinguish from a genuine
   dispersion signal.
3. The single-row PDP sweep is off-manifold (correlated technical features held
   fixed at combinations the model may never see) — a known PDP failure mode
   (Apley & Zhu, 2020).
4. SHAP/split-count evidence explains the model's representation, not causal economic
   contribution — non-identifiable under correlated features (Ma & Tourani, 2020).
5. The fundamentals conclusion ("CLEARED as driver") was too strong: a small weekly
   SHAP delta doesn't rule out the median-imputed factor materially setting score
   level/rank.
6. The proposed forward test (low-STD60 faded vs high-STD60 admitted) is
   selection-confounded and was never pre-registered.

**What was corrected:** `doc/research/2026-07-11-meta-score-attribution.md` now
opens with a corrigendum stating the defensible conclusion only —
*"same-model, approximate replay suggests sensitivity to the STD60 feature on this
path; this does not establish a 74% root cause, an economic dispersion premium, or a
reason to change the strategy"* — and walks back "LEARNED", "proven", "CLEARED",
"REFUTED" language throughout in place. Added: a dedicated STD60 price-level-CV vs
return-volatility caveat section, and a "Known Limitations / Not Yet Established"
section itemizing all six Codex points with what would be needed to close each.
PR title/body updated to match. All original evidence (reproduction numbers, SHAP
tables, split census, PDP output, controls) is retained — only the causal/economic
framing around it changed.

**What remains explicitly open (not attempted in this PR):** all six items above.
Per Codex and this doc's own placement note, closing them is model/pipeline work
(STD60→return-volatility ablation, conditional ALE/SHAP, path-consistent rescore)
and renquant-base-data work (fundamentals coverage repair, observed-vs-imputed
matched test), plus a properly pre-registered walk-forward forward test — none of
which is orchestrator-repo scope or done here.

**Evidence sealing:** the serving-run inputs/outputs this document's numbers are
based on (reproduction error, SHAP deltas, split census, PDP sweep output) are
sealed content-addressed in `renquant-artifacts`
(`registry/meta-score-attribution-20260711.json` +
`store/experiments/meta-score-attribution-20260711/RUN-LOCK.json`), following the
same pattern as bundles #14/#15/#16 in that repo. Fields with no independently
verifiable value in this run (e.g. a transform fingerprint distinct from the panel
sha) are marked absent, not fabricated.

## Follow-ups (recommended, not implemented — unchanged in substance, now explicitly gated by the Limitations section)

1. base-data: repair earnings_yield/book_to_price/gross_profitability coverage in
   `sec_fundamentals_daily.parquet` + alert on per-column imputed share.
2. decision-ledger: a **pre-registered** forward validation of the STD60 sensitivity
   (not the selection-confounded sketch originally proposed) — all upstream-eligible
   candidates, lagged signals, sector/size/regime-stratified STD quantiles, purged
   time blocks, matured 60d labels, block-bootstrap CIs, turnover/cost, multiplicity
   control.
3. model/pipeline: frozen-vintage ablation substituting a genuine return-volatility
   feature for STD60, plus conditional ALE/SHAP and a path-consistent rescore.
4. Monitor scored-universe size swings (41→88 in one session).

## Boundaries

Read-only on all production paths; DB copied before opening; isolated git worktree;
no git in the live umbrella tree or primary checkouts; local compute only. Research +
progress docs only — no code, no config, no gate changes.
