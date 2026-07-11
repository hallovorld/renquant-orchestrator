# PR #106 model-capability roadmap — completion audit + cross-stock attention verdict

STATUS: research audit (GOAL-7a). Freeze-first: §5 (run pre-registration) is committed
BEFORE the runs; results land in a later commit on this branch (verifiable in commit
order, same convention as `doc/research/2026-07-03-msig-c4-trendscan.md`).
DATE: 2026-07-10 (r1); r2 2026-07-11 (Codex CHANGES_REQUESTED, 4 objections accepted:
(1) seeds 44/45 were pre-known-positive from #126 → the run is reclassified throughout as
a **TARGETED CONFIRMATION**, never a fresh replication, and a deterministic independent
seed-selection rule is preregistered in §5a; (2) evidence moved out of the session
scratchpad into a sealed content-addressed bundle in renquant-artifacts (PR #14, commit
`82ad63ee8`, `store://experiments/xstock-pilot-20260711/RUN-LOCK.json`, fingerprint
`sha256:86b06dec…` — cited from §7); (3) input/code identity rebound to pinned artifacts
and exact commits, with the umbrella-path consumption recorded as a limitation of THIS run
rather than rewritten (§5, RUN-LOCK.json `code_identity`/`inputs`); (4) §6's "≥8 weekly
pairs" replaced with a defined analysis protocol — fixed window, overlap treatment,
no-peeking rule, forward-data OOS gate named precisely — plus the plain statement that
the n=2 result justifies NO live or shadow promotion. Frozen §5 parameters are unchanged;
r2 edits are annotations and reclassifications, with r1 preserved in branch history.)
SCOPE: audit every actionable lead in merged orchestrator PR #106
(`research: model capability roadmap`, merged 2026-06-12; body deleted from main in the
2026-06-16 consolidation c5506281 — final text incl. the post-merge errata recoverable at
`git show c5506281^:doc/research/2026-06-12-model-capability-roadmap.md`), verify each
against the repos as of today, and either complete the strongest executable lead or refute
it honestly.

---

## 0. Bottom line

1. **The headline lead ("cross-stock attention, May DOE best_val_ic 0.203 vs 0.157–0.188
   base, never promoted") is REFUTED as stated — and was already refuted in-repo on
   2026-06-12** by the #109 post-merge errata: 0.2035 is the winner-picked max of a 25-point
   (5-cut × 5-seed) DOE whose full-run mean is **+0.0507, std 0.0896, 12/25 points
   negative** `[VERIFIED — RenQuant/logs/hf_cross_stock_5cut_5seed_pt07/driver.log,
   aggregation table reproduced §2.1]`.
2. **"Never promoted" ≠ neglected.** The lead was follow-up-tested within days and at every
   later stage: strict paired 3-seed re-run 3/3 positive but sub-significant (#126,
   2026-06-13); a **production-scorer bug that silently dropped cross-stock weights on
   load** was found and fixed (umbrella #380 + fail-closed #382, 2026-06-16 — the flag was
   not even deployable before then); the mid-June campaign judged it "helps but doesn't
   pass alone; does not stack on top of pruning (B3 < B2)"; the 2026-06-23 roadmap
   re-scoped it to long-term ("re-scope onto the new label/features"). §2 gives the dated
   chain.
3. **No dedicated GPU promotion campaign is justified today.** The expected effect
   (paired val-IC delta ≈ +0.016, #126) is ~4× below what the repaired WF gate can
   currently resolve (C4 precedent 2026-07-03: SE ≈ 0.023 ⇒ a GO needs mean ≈ +0.069 at
   the Bonferroni-corrected CI). A campaign now is predictably INCONCLUSIVE — the C4
   outcome — and PatchTST is currently the **shadow**, not the primary (`kind: xgb` in the
   pinned `strategy_config.json`; shadow pin = `pt07_strict_trainfit_embargo60_20260522/
   seed_44`, cross_stock=False) `[VERIFIED — renquant-strategy-104/configs]`.
4. **The executable remnant is cheap and is executed here:** a frozen 2-seed paired
   **targeted confirmation** on the CURRENT corpus vintage under the exact weekly-rail
   recipe (§5 — r2: seeds 44/45 are pre-known-positive from #126, so this tests
   vintage-robustness only, never seed-generalization), plus a pre-registered
   **weekly-rail ride-along spec with a defined analysis protocol** (§6/§6a: fixed
   16-week window, forward-data-only confirmatory estimand, no-peeking rule, deterministic
   independent-seed secondary set, named OOS gate) — promotion authority stays exactly
   where it is (validated served-pin promote + production WF gate + scorer-lineup reopen
   triggers), and **the n=2 result justifies NO live or shadow promotion**. Results +
   sealed evidence bundle (renquant-artifacts PR #14): §7.

Decision needed from operator/Codex: none to trade — this PR changes no production path.
Approve/deny the §6 ride-along wiring as a follow-up implementation PR.

---

## 1. Lead-status table — every actionable claim in #106, status 2026-07-10

| # | #106 lead | Claim then | Status TODAY (verified) |
|---|---|---|---|
| 1.1 | **Cross-stock attention** (`--cross-stock-attn`, `HFPatchTSTRanker`) | "highest-variance structural lead", DOE max 0.2035; errata: mean +0.0507, 12/25 neg | Flag exists and is live code (`renquant-model src/renquant_model_patchtst/hf_trainer.py:222,814`; orchestrator `build_patchtst_wf_manifest.py` passes it through). Evidence chain in §2: refuted as headline; suggestive-but-unresolved as a paired delta; parked by 2026-06-23 roadmap re-scope. **This memo completes it** (targeted confirmation §5/§7 + ride-along protocol §6/§6a). |
| 1.2 | **Scale sweep** (0.07M params, d_model/layers/seq_len grid, "~26-min trains") | pre-register 6-cell grid ≈ 4 h | **NEVER RUN.** Sits in `doc/roadmap-backlog.json` as `model-scale-sweep`, status `pending`, tagged OPERATOR-ONLY (burns GPU). Trainer + rail intact (weekly retrain ≈ 15 min/model on MPS), so still nearly free to *train* — but it faces the same judge-power ceiling as §3; a sweep without a resolvable judge selects winners by noise. Recommendation: keep pending until the gate-power problem (S-REL/C4 line) is resolved; then run as pre-registered. |
| 1.3 | **Multi-horizon multi-task heads** (5d/20d auxiliary heads on the 60d head) | "standard multi-task lift", cheap | Aux-head variant itself never built. The adjacent evidence went the other way: 20d label val IC −0.07 / gate FAIL (`2026-06-19-patchtst-edge-recovery-experiment.md`); multi-horizon **ensemble/sleeves** REJECTED and closed (PR #149; 2026-06-23 roadmap "do-not-redo" list; `win-rate-is-backtest-not-live` record). Backlog `model-horizon-decision` = `blocked`. **Deprioritized with evidence; do not revive without a new label-side result.** |
| 1.4 | **Label engineering** (triple-barrier, overlap-aware weights; WS-5) | approved ride-along | Partially superseded by the stronger label result: trend-scanning label (2026-06-23, 3/3 seeds beat raw on BULL_CALM placebo-clean, mean +0.0149) → frozen as **M-SIG C4** → run through the REPAIRED gate 2026-07-03: **INCONCLUSIVE on all 3 seeds** (point estimates +0.033 mean, above margin; CI lower bound < 0 — honestly underpowered). Triple-barrier per se: not run. Label work now lives in the M-SIG program, not #106. |
| 1.5 | **Feature expansion** (analyst revisions / options-IV / short interest) | gated per-group screen | **Graduated into the M-SIG/G106 program** — the surviving descendant of #106 (`doc/design/renquant-106-as-built.md`): C2 quality REJECTED on free-tier (adds BULL_CALM only, HURTS BULL_VOLATILE); fundamental momentum REJECTED (#177) with reopening path = C2 on FMP Starter; C1 PIT revision-drift PENDING (PIT clock 2027-01, collectors active); options-IV still accumulating. |
| 1.6 | **3-seed averaging at promotion** | cheap variance reduction | Adopted as *research* convention (seeds {42,43,44} frozen in the M-SIG spec). NOT wired into the weekly retrain rail (trains seed 44 only — `weekly_retrain_patchtst.sh RQ_PATCHTST_SEED:-44`). Honest status: partial. |
| Q2 | **MASTER challenger** (1-day port, only if 1.1 confirms) | conditional | Never run. The condition ("1.1 confirms") was only weakly met (#126 suggestive, p≈0.083) and the judge was then found broken/underpowered — correctly not escalated. Stays conditional; same §3 power argument applies. |
| Q2 | **TSFMs** (TimesFM/Chronos/Moirai) | low prior, don't pursue | Not pursued — consistent with #106's own recommendation and the feature-map pending-discussion entry. No action needed. |
| Q3.1 | **Freshness institutionalized** | quarterly/monthly retrain rail + staleness preflight | **DONE and exceeded**: model-freshness governance (operator directive 2026-06-30: no model >28d; best-of-last-10-days fallback; RFC #210), weekly retrain rails for both models, corpus-frontier cutoff derivation (S12 B3: orch #259, umbrella #435), validated fail-closed served-pin promote (`promote_shadow_patchtst.py`). |
| Q3.2 | **Daily data pipeline + provenance** | nightly append + PIT collectors + stamps | Partial-to-done: corpus refresh now runs inside the weekly rail (staged swap + partial-freeze fail-close); PIT snapshot collectors installed (launchd); provenance via ArtifactResolver sha256 (backlog `s1-wire-artifact-resolver` = done). Corpus verified fresh: `transformer_v4_wl200_clean.parquet` rebuilt 2026-07-03, label-resolved frontier 2026-04-02 `[VERIFIED — parquet metadata]`. |
| Q3.3 | **Deployment gates + HMM regime engine (RFC #93)** | shadow-first | Gate items shipped in the 06-12 week (#112/#113/#27/#110/#111/#114). HMM/Markov-switching engine: **still pending an RFC decision, never built** (feature-map pending-discussion). |
| Q3.4 | **Universe/breadth 142→200** | gated experiment, negative prior | Negative prior now CONFIRMED twice at higher standard: M8 cluster wave-1 **NO-GO** (UPHELD, adversarially verified) and D3 core-shrink **NULL** (VERDICTS.md 2026-07-03 rows). Breadth-by-expansion is closed; any revisit routes through D3. |
| Q3.5 | **Shorts Phase-B TC sleeve** | design under review | Built, gated OFF behind the shorting mandate (very high bar, max 2 concurrent). Unchanged. |
| Q3.6 | **Optuna budget wiring** | systematize HP search | **Not built** (feature-map pending-discussion). Same §3 judge-power caveat as 1.2 before it can be useful. |

Cross-cutting correction that postdates #106 and reframes all its absolute IC numbers: the
WF-gate **embargo leakage floor** (~+0.04 shuffled-label floor on the 60d label; only
placebo-clean *differences* are trusted) and the S1–S3 gate repair (placebo-difference
semantics, merged by 2026-07-03). Every May-DOE absolute val-IC in #106 (0.203 max, 0.188
base, 0.153 DLinear…) predates the strict_trainfit protocol (landed 2026-05-22; the DOE ran
2026-05-21) — the DOE's WF cuts did use `embargo_days=60`
`[VERIFIED — scripts/eval_hf_cross_stock_5cut_5seed.py docstring]`, but the numbers are
only comparable *within* the DOE, not against today's gate scale.

## 2. The cross-stock attention evidence chain (dated, each step verified)

**Mechanism** `[VERIFIED — code read]`: one MultiheadAttention block over the day's
cross-section (batch = one day's tickers via the identity collator), inserted between the
PatchTST backbone pooling and the heads; gated residual `h + α·(transformed(h) − h)` with
α=0 at init plus zero-init output projections → exact identity at init, strict superset of
the baseline. O(N²)/day, N≈142 — cheap.

| Date | Event | Result | Where |
|---|---|---|---|
| 2026-05-21 | 5-cut × 5-seed DOE, `--cross-stock-attn`, pt07 knobs | full-run best_val_ic mean **+0.0507**, std 0.0896, min −0.0594, max **+0.2035** (cut4_svb seed46), **12/25 negative**; per-cut means covid +0.113 / fed −0.042 / inflpk +0.012 / svb +0.187 / unwind −0.015 | `RenQuant/logs/hf_cross_stock_5cut_5seed_pt07/driver.log` |
| 2026-06-12 | #106 merged citing "0.2035" as headline; **same-day codex errata (#109)** corrects it to the full-run distribution + requires paired A/B with DSR/PBO before any adoption | headline claim retracted in-repo | `git show c5506281^:doc/research/2026-06-12-model-capability-roadmap.md` (ERRATA §1) |
| 2026-06-13 | Strict paired 3-seed re-run (strict_trainfit, same cuts/seeds), orch **#126** | paired Δbest_val_ic **+0.0215 / +0.0012 / +0.0252** (seeds 44/45/46), 3/3 positive, mean **+0.0160**, paired t=2.14, one-sided p≈0.083 — "suggestive, not conclusive"; bonus finding: baseline had a dead seed (−0.0015), cross-stock had none (min +0.0237). Operator A/B/C decision requested; no dedicated gate run followed | PR #126 body (merged; epic-branch research) |
| 2026-06-16 | **Deployability bug**: production scorer silently DROPPED cross-stock/FiLM weights on model load (silent mis-score) | fixed umbrella **#380**; **#382** makes missing component weights fail-closed. Before this, a promoted cross-stock model would have served WITHOUT its attention layer | umbrella PRs #380/#382 |
| 2026-06-16 | Mid-June retrain campaign verdict recorded in the consolidated feature map | "cross-stock attention … now deployable (#380). Evidence: **helps but doesn't pass alone; does not stack on top of pruning (B3 < B2)**" | `doc/renquant-system-feature-map.md:181-183`. **Caveat: the B3 run's raw artifacts were not preserved** (no summary.json / log found in umbrella models/ or logs/); the claim is contemporaneous but unreproducible — treat as [ASSERTED 2026-06-16], weight accordingly |
| 2026-06-19→21 | PatchTST edge-recovery prereg (Exp A/B, pruning line) | all gate runs FAIL; all aligned real ICs in the noise band (<0.01); gate placebo threshold floor dominates — the 60d judge is ill-conditioned near zero IC | `doc/research/2026-06-2{0,1}-patchtst-edge-recovery-*.md` |
| 2026-06-23 | Roadmap re-prioritization; operator re-promotes XGB primary (PatchTST → shadow) | cross-stock moved to LONG-term: "already planned (Tier 2, #126 3/3 positive, deployable); **re-scope onto the new label/features**" | `doc/research/2026-06-23-model-and-engineering-roadmap.md` §1 long-term |
| 2026-07-03 | Gate repaired (S1–S3, placebo-difference semantics) and its power measured by the C4 run | INCONCLUSIVE at SE≈0.023: GO needs mean ≈ +0.069; observed label-side effects ~+0.033 can't resolve | `doc/research/2026-07-03-msig-c4-trendscan.md` |
| 2026-07-10 | Shadow pin still `pt07_strict_trainfit_embargo60_20260522/seed_44` (cross_stock=False, trained 2026-05-22) | the weekly validated promote has not advanced it | `renquant-strategy-104/configs/strategy_config.shadow.json` |

**Audit verdict on "why never promoted":** not neglect — a sequence of (a) an honest
errata downgrade, (b) a sub-significant confirmation, (c) a deployability bug that made
promotion impossible before 06-16, (d) a no-pass when stacked through the gate path, and
(e) a deliberate re-scope decision. The residue that is still alive: a 3/3-positive paired
val-IC delta (+0.016) and the dead-seed-robustness observation, neither ever tested on a
post-repair judge or on fresh data. That residue is what §5–§7 executes.

## 3. Why NOT a dedicated promotion campaign now (the refutation of task framing)

- **Judge power**: the repaired gate's measured resolution (C4, 2026-07-03) is
  SE ≈ 0.023 per seed at n≈600+ dates ⇒ a Bonferroni-corrected one-sided GO needs a mean
  effect ≈ +0.069. The cross-stock paired delta on the val metric is ≈ +0.016 (#126).
  Expected outcome of a dedicated campaign: INCONCLUSIVE, ~1 GPU-day per #126's own
  estimate, decision value ≈ 0.
- **Wrong slot**: PatchTST is the shadow. A cross-stock PatchTST cannot reach the live
  book except through the scorer-lineup reopen triggers (shadow dominates primary ≥1
  quarter, etc.) — none has fired. Improving the shadow is worthwhile only at ~zero
  marginal cost, which is exactly the §6 ride-along.
- **Program alignment**: the mid-term IC program is M-SIG (signal/label level) with G106
  structurally not clearable today; 2026-06-23 explicitly sequenced architecture AFTER
  label/features. A standalone architecture campaign would re-litigate that sequencing
  without new evidence.

## 4. What this PR does instead

1. This audit memo (the #106 completion record) + a VERDICTS.md row for the cross-stock
   lead.
2. §5: a FROZEN 2-seed paired **targeted confirmation** (pre-known seeds; bias stated) on
   the current corpus vintage — run locally after the freeze commit; results + sealed
   evidence bundle in §7.
3. §6/§6a: the pre-registered ride-along spec with its full analysis protocol — the only
   justified execution path; wiring it is a small follow-up PR gated on operator/Codex
   approval of this memo.

## 5. Run pre-registration (FROZEN before any run in this branch) — r2: this is a TARGETED CONFIRMATION, not a replication

**Question**: does the #126 paired cross-stock lift hold up on the CURRENT corpus vintage
under the exact weekly-rail recipe, at the same seeds #126 measured? (Exploratory: informs
§6 go/no-go only. NOT a gate run, NOT promotion evidence — per #126's own discipline, "IC
deltas are evidence for running the gate, not a substitute".)

**r2 — selection-bias statement (plain):** seeds 44 and 45 were **already reported
positive in #126**. Re-running pre-known favorable seeds tests only whether those specific
results are *vintage-robust* (fresh data, current recipe); it is structurally incapable of
testing seed-generalization and MUST NOT be described as a fresh or independent
replication. Anywhere this memo says "confirmation," read "targeted confirmation on
pre-known seeds." The r1 text's "reproduce on fresh vintage" framing understated this;
corrected here.

### 5a. Deterministic independent seed rule (preregistered for ALL future runs)

Any future run claiming seed-independence (including the §6 secondary set) uses seeds from
this rule, fixed BEFORE results: take `sha256("d6-xstock-ridealong-2026")` =
`ad0666c93dc1bd933139f23f4227295dec9a784792a1135156e09d4a9449d564`; read successive
4-hex-char groups as integers mod 10000; skip duplicates and the previously-inspected set
{42, 43, 44, 45, 46}; the first N survivors are the seeds. First five, precomputed and
binding: **4294, 6313, 5809, 8531, 2601**.

- **Arms**: base vs `--cross-stock-attn`; NOTHING else differs.
- **Recipe** (mirrors `build_patchtst_wf_manifest.build_train_cmd` exactly — the canonical
  weekly-rail argv): `--cut all --train-cutoff 2026-03-30 --label fwd_60d_excess
  --epochs 5 --lr 1e-4 --weight-decay 0.3 --seq-len 24 --early-stopping-patience 2
  --val-tail-pct 0.10 (default) --embargo-days 60 (default) --device mps --save-model`.
  Cutoff 2026-03-30 = the rail's own derivation
  (`renquant_orchestrator.patchtst_weekly_cutoff` on the refreshed corpus, Monday-quantized)
  `[VERIFIED — command output 2026-07-10]`.
- **Data identity (r2 — rebound to artifact identity, consumption-path limitation
  recorded)**: training corpus = `transformer_v4_wl200_clean.parquet` identified by
  **content sha256 `46da7f431ccc7db228abf9162ac36b0af2d03c0013575c48e35562dec35ce197`**
  (401,398,353 bytes; 351,134 rows, 342,330 after label dropna; labeled frontier
  2026-04-02; recipe owner = renquant-base-data `transformer_corpus.py`, runtime pin
  `fef604bff`). SPY OHLCV identified by sha256 `ab9f5d4a…9125` (122,481 bytes). **Recorded
  limitation of THIS run (not rewritten): both blobs were genuinely consumed READ-ONLY
  from the local umbrella working copy (`RenQuant/data/`), not resolved through a pinned
  artifact-store binding.** The §6 wiring MUST resolve inputs by recipe commit + content
  sha256 via the `artifact_store` mechanism (renquant-artifacts `store/README.md`), never
  a local umbrella path. No production path was written (outputs isolated; now sealed in
  the §7 evidence bundle).
- **Code identity (r2 — exact commits)**: imports resolved via `subrepo_env.sh` to the
  **pinned runtime checkouts** `RenQuant/.subrepo_runtime/repos/*` (all clean trees):
  renquant-model `84a3c1864` (trainer files byte-identical to renquant-model main
  `45e42a1e3` — verified empty diff), renquant-common `f5cb6ab2c`, renquant-orchestrator
  `690c82fc6` (cutoff derivation), renquant-base-data `fef604bff`; full 9-repo pin map in
  the bundle's `RUN-LOCK.json`. Strategy config read from renquant-strategy-104 primary @
  `6d205fd41` (fingerprint stamp only, no training effect). Python 3.10.20 / torch 2.11.0
  / transformers 5.8.1, device MPS, via the umbrella-managed venv (recorded limitation:
  environment is umbrella-managed, not a pinned image — same remediation path as inputs).
- **Seeds**: {44, 45}, paired same-seed. 4 runs total. If wallclock exceeds ~3 h, report
  completed PAIRS only; never report a single arm of a pair.
- **Metric**: paired Δ `best_val_ic` (cross_stock − base) from each run's summary.json
  (min-per-regime val IC — the selection metric, same as #126).
- **Frozen interpretation rule**:
  - Both seeds Δ > 0 → §6 ride-along recommendation STANDS (wire it, accumulate paired
    weekly evidence, let the validated promote + production gate adjudicate over weeks).
  - Mixed sign or both ≤ 0 → fresh-vintage evidence AGAINST; ride-along recommendation
    WITHDRAWN; VERDICTS row records the refutation; no re-pitch without a new mechanism
    argument.
  - No DSR/PBO claims at n=2; no absolute-IC claims (embargo-floor discipline); the val
    window (last 10% of dates before 2026-01-02 data end, 60-bday embargo) is regime-narrow
    — this is acknowledged as a pilot limitation either way.

## 6. Ride-along spec (pre-registered; implementation = follow-up PR, needs approval) — r2: full analysis protocol

**Plain statement first (r2, per review): the §7 n=2 targeted confirmation justifies NO
live and NO shadow promotion.** It justifies exactly one thing: spending ~25 min/week of
already-scheduled compute on a paired arm plus an append-only ledger, adjudicated by the
protocol below.

- **What**: the weekly PatchTST retrain (`weekly_retrain_patchtst.sh` → orchestrator
  `build_patchtst_wf_manifest`) trains ONE extra arm per week: same derived cutoff, same
  seed, `--cross-stock-attn` (builder already accepts the flag — zero new training code;
  the change is a loop + summary side-car in the orchestrator pipeline + an opt-in env
  flag `RQ_PATCHTST_XSTOCK_RIDEALONG=1`, default OFF). **Wiring requirement (r2, per
  review objection 3): both arms' inputs must resolve from pinned artifacts (recipe commit
  + content sha256 via the renquant-artifacts `artifact_store` binding), never a local
  umbrella path.**
- **Cost**: ≈ +15–40 min/week on the already-scheduled rail (+2 runs every 4th week for
  the independent-seed set below); no new schedule, no Modal.
- **Ledger**: append `{cutoff, seed, base_best_val_ic, xstock_best_val_ic, delta,
  run_bundle_hashes}` to an append-only side-car JSONL in the WF output dir (research
  artifact, not a served path).

### 6a. Analysis protocol (fixed BEFORE enable; replaces r1's bare "≥8 weekly pairs")

1. **Fixed analysis window and label-availability cutoff (r3, per review: the estimand
   is `fwd_60d_excess` — a 60-BUSINESS-DAY-forward label — so the scoring window and the
   readout date are NOT the same date).** Enable date E = the first scheduled weekly run
   after the wiring PR merges and its pin advances. The confirmatory SCORING window is the
   **16 scheduled weekly runs in [E, E+16 weeks)**; missed weeks are recorded as missed,
   never backfilled. A scored forward session is includable in the readout only once its
   realized label has matured: `score_date + 60 business days <= as_of_date`. Because the
   LAST scored date in the cohort is at E+16w, its label does not mature until
   E+16w+60 business days — so **the readout cannot happen at E+16w** (at that date only
   the first ~20 business days of the cohort have mature labels, well under the block-
   bootstrap's 60-session block size; the bootstrap literally cannot form one block).
   **One readout**, on the first Monday ≥ **E + 16 weeks + 60 business days** (≈32 weeks
   after enable) — by which point every scored session in the [E, E+16w) cohort has a
   mature label and the full ~80-session sample is genuinely usable. If the inference
   machinery refuses for small-n (below), the window EXTENDS by further preregistered
   16-week blocks, each with the SAME +60-business-day maturity wait before its own
   readout — the test is never relaxed and immature-label sessions are never substituted
   in to hit a readout date early.
2. **Overlap/dedup treatment (why weekly pairs are NOT 16 trials).** Consecutive weekly
   val tails share ~98% of their dates (the tail advances ~5 BDays/week across a
   ~227-session window) and adjacent 60d label windows overlap. Therefore the weekly
   val-side Δ series is treated as **one autocorrelated series — monitoring only** (sign
   consistency, dead-seed incidence). It carries **zero confirmatory weight**, which also
   forecloses satisfying the gate by repeated validation-tail selection.
3. **Confirmatory estimand = FORWARD data only, mature labels only.** Each week, both arms
   shadow-score the forward sessions strictly AFTER that week's train date (scores only;
   no order path). Dedup rule: each calendar session counts once, attributed to the most
   recent weekly pair trained before it (deterministic). **Inclusion rule (r3, per
   review): a scored session is includable at readout iff `score_date + 60 business days
   <= as_of_date`** — this is what pins the readout date to E+16w+60bd in §6a.1, and it
   applies again identically at every extended window's own readout. At readout: per-date
   paired ΔIC (xstock − base, cross-sectional Spearman) over the deduplicated,
   label-mature forward sessions; inference = moving-block bootstrap, **block = 60
   sessions** (label horizon; house convention per
   `research_panel_exit_predictiveness.py::_moving_block_bootstrap`), n_boot = 2000, seeds
   {42,43,44} all reported. **GO statistic: one-sided 95% CI lower bound of the mean
   forward ΔIC > 0.** Honest power note: at the corrected readout (E+16w+60bd), the full
   16-week scoring cohort's labels have matured, so 16 weeks ≈ 80 forward sessions ≈ 1.3
   independent 60-session blocks IS the valid count at that date (it was NOT valid at the
   uncorrected E+16w readout — at that earlier date only ~20 sessions would have mature
   labels, under one full block, and the bootstrap could not even start). Expect the
   small-n refusal (expkit convention) to extend the window at least once even with the
   corrected count; that is the designed behavior, not a failure.
4. **Seed handling.** The weekly pair runs at the rail seed (44) for served-pin
   comparability — seed 44 is pre-known-favorable (§5a), so its val-side deltas are doubly
   non-confirmatory. Every 4th scheduled week, the pair ALSO trains at the next unused
   seed from the §5a deterministic schedule (4294, 6313, 5809, 8531, …). These
   independent-seed pairs (≥4 by first readout) form the **secondary confirmation set**:
   reported as a sign test on paired Δ, no tuning, no exclusion.
5. **No-peeking rule.** Arm deltas are written by the rail to the append-only ledger and
   are **not consulted before the readout date**. Automated integrity checks (run
   succeeded/failed, artifact hashes) are permitted — they reveal no deltas. Any interim
   inspection of deltas must itself be logged in the ledger and **downgrades the readout
   from confirmatory to exploratory** (S-REL discipline); the window then restarts.
6. **Out-of-sample gate (named precisely).** Any promotion of the xstock arm to the
   SHADOW pin requires ALL of: (a) the §6a.3 forward-data GO statistic; (b) the §6a.4
   secondary set not contradicting (no majority-negative sign); (c) the existing validated
   served-pin gate — `renquant-orchestrator doc/design/2026-06-30-shadow-scorer-freshness.md`
   §5 (RFC r2, orchestrator PR #212) §3.4: load / parity / non-degenerate / resource /
   sanity checks, fail-closed, executed against the candidate ARTIFACT and the current
   panel (not training-val tails). **The gate's implementing script is intentionally
   umbrella-owned per that RFC's §5 ownership split** ("the umbrella owns the script +
   launchd schedule; the served `artifact_path` pin lives in strategy-104 config") — this
   is a deployment-time operational step invoked only AFTER this protocol's own §6a.3
   analysis has independently produced a GO verdict from pinned artifacts; it is not a
   runtime dependency of the analysis itself, and no computation in §6a reads or executes
   umbrella code. **PRIMARY promotion is out of scope entirely** (scorer-lineup decision +
   reopen triggers unchanged).
7. **Kill rule.** If at the first readout the forward ΔIC point estimate is ≤ 0, or the
   secondary seed set is majority-negative, the arm is retired, the flag removed, and the
   VERDICTS row closed as refuted — no second window, no re-pitch without a new mechanism
   argument.

- **Why this and not more**: it converts an unresolved suggestive residue into a
  continuous, near-free, forward-data measurement instead of a one-shot underpowered
  campaign — and it cannot touch the live book without passing the same gates as today.

## 7. Targeted-confirmation results (appended AFTER the §5 freeze commit; see commit order)

**Classification (r2): TARGETED CONFIRMATION on pre-known seeds — seeds 44/45 were
already positive in #126 (§5 bias statement). This section evidences vintage-robustness
of those specific paired deltas ONLY; it is not a replication and justifies no
promotion.**

**Outcome: 2/2 paired deltas POSITIVE → per the frozen §5 rule, the §6 ride-along
recommendation STANDS (subject to the §6a protocol).** Runs executed 2026-07-11
05:28–07:13Z, local MPS.

**Evidence of record (r2 — sealed, content-addressed; scratchpad paths are no longer part
of the evidence chain):** renquant-artifacts PR #14, commit `82ad63ee8`, bundle
`store://experiments/xstock-pilot-20260711/` — registry entry
`registry/xstock-pilot-20260711.json`, fingerprint
`sha256:86b06dec1c2dec3a04a37eb278bf995b52bd31a17a0fc445b921b107b21fd01d`
(= sha256 of the bundle's `RUN-LOCK.json`). The bundle contains the four run summaries +
metadata sidecars, the four val-preds parquets (per-date per-ticker predictions + labels —
every number below is independently recomputable from the bundle alone), cleaned
stdout/stderr logs + raw-log hashes + the exact runner scripts, the argv/env lock, the
9-repo runtime-pin code identity, the data-artifact identity, the interruption/restart
record, and sha256+size of the four excluded model checkpoints. All 20 blobs are
sha256-listed in `store/STORE-MANIFEST.json` (CI-verified).

| seed | base `best_val_ic` | xstock `best_val_ic` | paired Δ | binding (min) regime |
|---|---|---|---|---|
| 44 | +0.0420 | +0.0627 | **+0.0207** | BULL_CALM (both arms) |
| 45 | **−0.0076** | +0.0095 | **+0.0172** | CHOPPY (both arms) |

Mean paired Δ = **+0.0189** — consistent with #126's +0.0160 *at the same pre-known
seeds* (its seed-44 delta was +0.0215; ours +0.0207 on data ~10 months fresher). This is
vintage-robustness of the seed-44/45 deltas, NOT seed-independent evidence.

Per-regime val-IC deltas (xstock − base), all four regimes, both seeds:

| seed | BULL_CALM | BULL_VOLATILE | BEAR | CHOPPY |
|---|---|---|---|---|
| 44 | +0.0207 | +0.0124 | +0.0260 | +0.0106 |
| 45 | +0.0153 | +0.0088 | +0.0002 | +0.0172 |

**8/8 per-regime deltas ≥ 0** — the lift is not a single-regime artifact on this split.

Secondary observations (frozen-scope, exploratory):
- **The dead-seed asymmetry recurred** (observation, not a preregistered test): the base
  arm produced a dead seed here (s45 −0.0076, min regime CHOPPY) while cross-stock did not
  (min +0.0095) — the same asymmetry #126 flagged on a DIFFERENT seed (its baseline dead
  seed was 46 ≈ −0.0015; cross-stock min +0.0237). Two vintages, two distinct dead base
  seeds, zero dead cross-stock seeds so far; for a weekly rail whose product is a servable
  shadow pin, fewer dead trainings is operational value independent of any IC claim. The
  §6a.4 independent-seed set is the proper test of this.
- **Cost**: 17–28 min/run on MPS (s45 runs early-stopped at epoch 4) — the #106 "26-minute
  train" claim is still accurate; the weekly ride-along arm costs ≈ 20–30 min/week.
- Params 67,908 → 101,381 (+49%); identical data, split, seed, and hyperparameters per arm
  (summary.json `params` blocks differ ONLY in `cross_stock_attn`).

Honest run-integrity note: the first attempt at the seed-45 pair was killed mid-training
by session tooling (background-task stop, ~06:20Z); it was relaunched detached at 06:28Z
with the IDENTICAL frozen argv and ran to completion. No spec parameter changed; the
seed-44 pair was unaffected (the exact record, with both attempts' timestamps and the
relaunch script, is in the bundle's `RUN-LOCK.json` `interruption_record`). Interpretation
limits (unchanged from the freeze, tightened by r2): these are val-tail ICs on one
split/vintage at pre-known seeds — paired differences only, no absolute-IC or gate claim,
n=2, no DSR/PBO, **no live or shadow promotion justified**. The next admissible evidence
is the §6a protocol: forward-data paired ΔIC at readout (E+16w+60bd, per the label-
availability cutoff in §6a.1/§6a.3) + the independent-seed secondary set, gated by the
served-pin promote script per §6a.6.

## 8. VERDICTS.md row added in this PR

See `doc/research/VERDICTS.md` — "Cross-stock attention (#106 1.1 / #126)" row referencing
this memo.
