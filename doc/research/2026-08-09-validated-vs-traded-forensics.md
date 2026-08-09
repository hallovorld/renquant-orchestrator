# One system was validated, another was traded — the forensics, and the decision

Operator-ordered (2026-08-09 re-planning, Phase 1 step 1-2). All evidence
below is from existing artifacts, measured today, re-runnable.

Reproducibility (review r1): `data/2026-08-09-validated-vs-traded-rows.csv`
(the per-shared-date table: widths, top-3 books, overlap, Spearman) +
`data/2026-08-09-validated-vs-traded-derivation.py` (the rerun contract —
exact SQL, digest-verified replay matrix, asserts every published number,
refuses on input drift; run with the umbrella venv python). Inputs: served =
`/Users/renhao/git/github/RenQuant/data/runs.alpaca.db` (sqlite `mode=ro`;
`candidate_scores ⋈ pipeline_runs` on `run_id`, `run_type='live'`,
`role='candidate'`, `run_date<='2026-08-07'`; score = `panel_score`,
first-recorded-value-of-the-day per ticker); replay = the bt#110 served
matrix (run wfreplay-2026-08-08), hash-pinned by
`data/2026-08-09-l2-backtest-inputs.manifest.json` (digest-of-digests
×1685); config facts read from git at the manifest-recorded
renquant-strategy-104 commit `aa775931`.

## 1 · The measured divergence `[VERIFIED — data/2026-08-09-validated-vs-traded-derivation.py, rerun clean 2026-08-09]`

| axis | served (live) | replay (backtest arm) |
|---|---|---|
| daily scored cross-section RECORDED (mean width on the 5 shared dates) | **22.0** names (post-screen candidates only) | **147.8** names (full investable universe) |
| top-3 picks overlap (5 shared dates) | — | **0/15** |
| Spearman on intersection names | — | mean **0.144** (per-date 0.09/−0.42/0.67/0.18/0.20) |
| shared dates available | 58 live dates (04-23..08-07) | replay ends 05-07 → **5** shared |

## 2 · Root cause — three layers, each verified

1. **Different model FAMILIES.** The live scorer is, since the operator's
   2026-08-04 override ("z-blend进prod / 整本切换"), a **blend** scorer
   (`ranking.panel_scoring.kind = blend`), whose xgb component is ONE
   production artifact of a fixed vintage (`panel-ltr.alpha158_fund.json`;
   the config records its 2026-05-09 training and the 06-23 promotion). The
   replay arm is a sequence of **per-fold walk-forward xgboost boosters**,
   each retrained at its fold boundary (bt#110 emitter) `[VERIFIED —
   renquant-strategy-104 configs/strategy_config.json @ aa775931:
   ranking.panel_scoring.kind = "blend",
   ranking.panel_scoring._2026_06_23_xgb_promotion (the 06-23 promotion),
   panel_ltr._lookahead_days_reason_2026-05-10 ("trained 2026-05-09") —
   re-read from git by the committed derivation]`. A near-zero score correlation
   between a fixed-vintage blend and rolling-fresh pure boosters is the
   expected outcome, not an anomaly.
2. **The candidate screen thins the recorded cross-section 148 → ~22**, so
   even a perfect scorer comparison is impossible from `candidate_scores`
   alone — the live system does not RECORD what it thinks of the other ~126
   names `[VERIFIED — per-date counts above]`.
3. **The research surface drifted too**: sigma unstamped since 05-12,
   expected_return only since 04-27 (orch#931) — the recorded features are
   also incomplete.

## 3 · What stays valid, what does not

* Valid: cross-arm rankings INSIDE the replay frame (#926/#927/#936 —
  all arms share one construction); the RECORD-ONLY / KILL verdicts (they
  refused promotion; refusals are robust to the proxy being optimistic).
* NOT valid: any reading of replay-frame absolutes (Sharpe 1.96, +61%/q)
  as attainable by the live book — now pinned by measurement (orch#937).

## 4 · Decision memo — three options, one recommendation

**A. Research submits to production**: rebuild all research arms on served
scores only. Honest but starves on history (58 dates, 22-name widths).

**B. Production upgrades to the validated construction**: serve the
walk-forward xgb line directly. The clean end-state, but a full promotion
chain (gate + grants) — days, not hours.

**C. RECOMMENDED — converge from both ends, backtest-first:**
1. TODAY: a **full-universe scoring snapshot** lane, split along the
   multi-repo boundary: **renquant-model / renquant-strategy-104 own the
   scorer** — the snapshot entry point and its pinned-artifact-loading
   semantics (the SAME artifacts the live run serves) live there, not in
   orchestrator. The **orchestrator only schedules** that model-owned
   snapshot contract, pins its inputs, and persists the provenance/audit
   output; it does not load artifacts or reimplement scoring. The snapshot
   records scores for ALL ~150 investable names daily (the screen still
   governs trading; it stops governing what is RECORDED). Research and
   production become same-source going forward.
2. TODAY (backtest-now evidence): a **retro-replay** of the CURRENT pinned
   blend over the historical calendar — the current scorer, applied
   offline to the full universe on past dates. Declared caveat: the xgb
   component's training window overlaps that history, so the retro run is
   admissible for MECHANISM comparisons ONLY (screen on/off, score
   correlations, book overlap) — NOT for arm-ranking or performance
   conclusions; in-sample exposure can reverse rankings, so those need a
   frozen vintage whose training ends before the evaluation interval, or
   the prospective snapshot lane. Vintage artifacts (`.previous`, artifact
   ledger) provide such pre-evaluation vintages where they exist.
3. The replay-frame line (#926/#927/#936) closes as "mechanism research,
   absolute claims void" — no further absolute quotes from it.

## 5 · Acceptance (backtest-now, per the operator's rule)

Two separate checks — the full-universe snapshot and the screen-filtered
trade path do NOT share identical top-3s by construction, so no top-k
overlap number is an acceptance test here.

* **(a) Identity on the screened intersection — the acceptance test.**
  Pointed at a past date, the snapshot module must reproduce the served
  `candidate_scores` rows for the names the screen admitted with **exact
  score equality after canonicalization**. Frozen contract: comparator =
  served `panel_score`, first recorded value of the day per
  (`run_date`, ticker) ordered by `pipeline_runs.created_at` (same rule as
  the committed derivation); as-of = the snapshot scores date D from the
  same pinned artifact set and same input data as-of D that the live run
  used; canonicalization = compare at the precision stored in
  `candidate_scores` (float64 round-trip through sqlite). Tie semantics:
  none needed — the check is per-name score equality, not a selection;
  any top-k comparison falls under (b). Any inequality fails.
* **(b) Full-universe overlap — descriptive only.** The retro-replay ships
  with committed CSV + verifier and re-measures the overlap table on the
  full universe. That number carries **no acceptance threshold** until its
  comparator (universe, filter, date/as-of, tie rule) is explicitly
  defined in the step-3/4 PRs.
