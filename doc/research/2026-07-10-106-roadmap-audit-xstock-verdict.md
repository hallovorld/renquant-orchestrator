# PR #106 model-capability roadmap — completion audit + cross-stock attention verdict

STATUS: research audit (GOAL-7a). Freeze-first: §5 (pilot pre-registration) is committed
BEFORE the pilot runs; results land in a later commit on this branch (verifiable in commit
order, same convention as `doc/research/2026-07-03-msig-c4-trendscan.md`).
DATE: 2026-07-10.
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
4. **The executable remnant is cheap and is executed here:** a frozen 2-seed paired pilot
   on the CURRENT corpus vintage under the exact weekly-rail recipe (§5, ~15–40 min/run,
   local MPS, scratch outputs only), plus a pre-registered **weekly-rail ride-along spec**
   (§6) that adds the paired cross-stock arm to the already-scheduled PatchTST weekly
   retrain at near-zero marginal cost — promotion authority stays exactly where it is
   (validated served-pin promote + production WF gate + scorer-lineup reopen triggers).
   Pilot results: §7.

Decision needed from operator/Codex: none to trade — this PR changes no production path.
Approve/deny the §6 ride-along wiring as a follow-up implementation PR.

---

## 1. Lead-status table — every actionable claim in #106, status 2026-07-10

| # | #106 lead | Claim then | Status TODAY (verified) |
|---|---|---|---|
| 1.1 | **Cross-stock attention** (`--cross-stock-attn`, `HFPatchTSTRanker`) | "highest-variance structural lead", DOE max 0.2035; errata: mean +0.0507, 12/25 neg | Flag exists and is live code (`renquant-model src/renquant_model_patchtst/hf_trainer.py:222,814`; orchestrator `build_patchtst_wf_manifest.py` passes it through). Evidence chain in §2: refuted as headline; suggestive-but-unresolved as a paired delta; parked by 2026-06-23 roadmap re-scope. **This memo completes it** (pilot §5/§7 + ride-along §6). |
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
2. §5: a FROZEN 2-seed paired pilot on the current corpus vintage — run locally after the
   freeze commit; results in §7.
3. §6: the pre-registered ride-along spec — the only justified execution path; wiring it is
   a small follow-up PR gated on operator/Codex approval of this memo.

## 5. Pilot pre-registration (FROZEN before any run in this branch)

**Question**: does the #126 paired cross-stock lift reproduce on the CURRENT corpus
vintage under the exact weekly-rail recipe? (Exploratory: informs §6 go/no-go only. NOT a
gate run, NOT promotion evidence — per #126's own discipline, "IC deltas are evidence for
running the gate, not a substitute".)

- **Arms**: base vs `--cross-stock-attn`; NOTHING else differs.
- **Recipe** (mirrors `build_patchtst_wf_manifest.build_train_cmd` exactly — the canonical
  weekly-rail argv): `--cut all --train-cutoff 2026-03-30 --label fwd_60d_excess
  --epochs 5 --lr 1e-4 --weight-decay 0.3 --seq-len 24 --early-stopping-patience 2
  --val-tail-pct 0.10 (default) --embargo-days 60 (default) --device mps --save-model`.
  Cutoff 2026-03-30 = the rail's own derivation
  (`renquant_orchestrator.patchtst_weekly_cutoff` on the refreshed corpus, Monday-quantized)
  `[VERIFIED — command output 2026-07-10]`.
- **Data (read-only)**: `RenQuant/data/transformer_v4_wl200_clean.parquet`
  (sha256 `46da7f431ccc7db228abf9162ac36b0af2d03c0013575c48e35562dec35ce197`, mtime
  2026-07-03, frontier 2026-04-02); SPY at `RenQuant/data/ohlcv/SPY/1d.parquet`. Outputs to
  the session scratchpad ONLY — no production path is written.
- **Code**: renquant-model @ `45e42a1` (main), orchestrator @ `40c51d33` (origin/main),
  umbrella venv python (torch 2.11.0, MPS).
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

## 6. Ride-along spec (pre-registered; implementation = follow-up PR, needs approval)

- **What**: the weekly PatchTST retrain (`weekly_retrain_patchtst.sh` → orchestrator
  `build_patchtst_wf_manifest`) trains ONE extra arm per week: same derived cutoff, same
  seed, `--cross-stock-attn` (builder already accepts the flag — zero new training code;
  the change is a loop + summary side-car in the orchestrator pipeline + an opt-in env
  flag `RQ_PATCHTST_XSTOCK_RIDEALONG=1`, default OFF).
- **Cost**: ≈ +15–40 min/week on the already-scheduled rail; no new schedule, no Modal.
- **Ledger**: append `{cutoff, seed, base_best_val_ic, xstock_best_val_ic, delta}` to a
  side-car JSONL in the WF output dir (research artifact, not a served path).
- **Promotion criteria (frozen NOW)**: unchanged from production. The ride-along arm may
  be pin-promoted to the SHADOW config only through the existing
  `promote_shadow_patchtst.py` validated gate, and only after ≥8 weekly pairs with
  (a) mean paired Δ > 0 and ≥6/8 pairs positive, AND (b) the cross-stock arm passes the
  same §3.4 load/parity/non-degenerate/sanity gates the base arm must pass. PRIMARY
  promotion is out of scope entirely (scorer-lineup decision + reopen triggers unchanged).
  If after 12 weeks the paired mean is ≤ 0, the arm is retired and the VERDICTS row closed
  as refuted.
- **Why this and not more**: it converts an unresolved 3/3-positive residue into a
  continuous, near-free, judge-aligned measurement instead of a one-shot underpowered
  campaign — and it cannot touch the live book without passing the same gates as today.

## 7. Pilot results (appended AFTER the §5 freeze commit; see commit order)

**Outcome: 2/2 paired deltas POSITIVE → per the frozen §5 rule, the §6 ride-along
recommendation STANDS.** Runs executed 2026-07-11 05:28–07:13Z, local MPS, outputs in the
session scratchpad only (`xstock_pilot/{base,xstock}_s{44,45}/`, summary.json + val-preds
parquet + checkpoint each).

| seed | base `best_val_ic` | xstock `best_val_ic` | paired Δ | binding (min) regime |
|---|---|---|---|---|
| 44 | +0.0420 | +0.0627 | **+0.0207** | BULL_CALM (both arms) |
| 45 | **−0.0076** | +0.0095 | **+0.0172** | CHOPPY (both arms) |

Mean paired Δ = **+0.0189** — consistent with #126's +0.0160 (its seed-44 delta was
+0.0215; ours +0.0207 on data ~10 months fresher).

Per-regime val-IC deltas (xstock − base), all four regimes, both seeds:

| seed | BULL_CALM | BULL_VOLATILE | BEAR | CHOPPY |
|---|---|---|---|---|
| 44 | +0.0207 | +0.0124 | +0.0260 | +0.0106 |
| 45 | +0.0153 | +0.0088 | +0.0002 | +0.0172 |

**8/8 per-regime deltas ≥ 0** — the lift is not a single-regime artifact on this split.

Secondary observations (frozen-scope, exploratory):
- **The dead-seed pattern reproduced exactly**: the base arm produced a dead seed
  (s45 −0.0076, min regime CHOPPY) while cross-stock produced none (min +0.0095) — the
  same robustness asymmetry #126 flagged (baseline dead seed 46 ≈ −0.0015, cross-stock min
  +0.0237). Two independent vintages now show base-arm training fragility that the
  cross-stock arm does not exhibit; for a weekly rail whose product is a servable shadow
  pin, fewer dead trainings is operational value independent of any IC claim.
- **Cost**: 17–28 min/run on MPS (s45 runs early-stopped at epoch 4) — the #106 "26-minute
  train" claim is still accurate; the weekly ride-along arm costs ≈ 20–30 min/week.
- Params 67,908 → 101,381 (+49%); identical data, split, seed, and hyperparameters per arm
  (summary.json `params` blocks differ ONLY in `cross_stock_attn`).

Honest run-integrity note: the first attempt at the seed-45 pair was killed mid-training
by session tooling (background-task stop, ~06:20Z); it was relaunched detached at 06:28Z
with the IDENTICAL frozen argv and ran to completion. No spec parameter changed; the
seed-44 pair was unaffected. Interpretation limits (unchanged from the freeze): these are
val-tail ICs on one split/vintage — paired differences only, no absolute-IC or gate claim,
n=2 seeds, no DSR/PBO. The next evidence must come from the §6 ride-along ledger, judged
by the existing validated promote + production WF gate.

## 8. VERDICTS.md row added in this PR

See `doc/research/VERDICTS.md` — "Cross-stock attention (#106 1.1 / #126)" row referencing
this memo.
