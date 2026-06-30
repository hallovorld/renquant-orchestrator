# Design: Model Freshness Governance — 28-day ceiling, best-of-recent fallback, reliable retrain cadence, and WF-promote cleanup

STATUS: design for review (no implementation in this PR — describe → discuss → PR to Codex → then implement per-repo).

This is a discussion document. It proposes a governance contract and a phased
rollout; it does **not** change any code, config, broker, risk-cap, or sizing
behaviour. Cross-repo implementation happens in follow-up per-repo PRs **after**
this design is agreed.

## 1. Problem — "no buys" has two INDEPENDENT freshness root causes

Both root causes are now diagnosed. They are orthogonal: they live in different
repos, gate different decisions, and either one alone can zero the buy list.

### A. Per-ticker tournament models (universe-admission gate)

The per-ticker tournament artifacts under
`backtesting/renquant_104/models/<TICKER>/` (an RL Q-table + RF + a per-ticker
XGB) gate **universe admission**. `FilterStalenessTask` in
`renquant-pipeline kernel/pipeline/job_universe.py` reads each ticker's
`*-policy-metadata.json` `trained_date` and drops the ticker if
`today − trained_date > model_staleness_days`.

Their retrain (`scripts/train_104.py --skip-panel` → `BaselineTournamentJob`)
**times out**: `parallel_ticker_timeout_seconds = 600` (10 min) is far too low
for the 142-ticker tournament. Measured: only **67 / 142** complete within 600s
→ `ParallelTimeoutError` → the whole job fails → **no fresh models are written**.
There is **no acceptance gate** on the tournament; this is a pure cadence/timeout
failure, not a quality veto.

Consequence: cadence has been effectively **frozen since late April** (RL/RF
artifact mtimes ~2026-04-22; `trained_date` stuck at 2026-04-28/30). On
2026-06-30 the age is **61d > 60d**, so every non-held ticker is dropped from the
universe → Phase 2b reports **"0 candidates from 0 tickers" → no trade**
(observed in `logs/daily_104/2026-06-30.log`).

### B. Panel scoring model (largely vestigial GBDT gate)

The weekly GBDT WF-promote (`scripts/weekly_wf_promote.sh`, gating
`panel-ltr.alpha158_fund` via `scripts/run_wf_gate.py`) chronically **fails** —
but it is **largely VESTIGIAL**. The production panel scorer switched to
**PatchTST on 2026-06-05** (`ranking.panel_scoring.kind = hf_patchtst`, config
note `_2026_06_05_patchtst_promotion`; the live retrain path is
`scripts/weekly_retrain_patchtst.sh`).

The GBDT `panel-ltr.alpha158_fund` is now a **sell-only fallback**
(`promotion_status = "gated_buys"`, and it has **never gate-passed**). It reached
`prod/` via STAMP operations — a wl200 stamp on 05-18 and a sector-map re-stamp
on 06-25 via `scripts/restamp_prod_fingerprint.py` — **not** via
training/promotion. No `manual_promote.sh` / `RQ_ALLOW_NO_WF` bypass appears in
the logs.

The GBDT weekly promote keeps failing on a **rotating** tangle of causes:

| # | Failure | Status / window | Root cause | Mechanical? |
|---|---------|-----------------|------------|-------------|
| (recipe-fp) | Recipe-fingerprint mismatch (candidate `f4596e33` ≠ manifest `ccc412d0`) | One-week issue ~05-24, **FIXED 05-27→06-04** | Fingerprint hashed human-readable `feature_source_contract` prose that a refactor edited | Yes — already fixed (hash only contract KEYS; move `epochs`/`early_stopping`/`device` to execution-only params; rebuild manifest). Current candidate and manifest **both hash `cfdd6cb8` — they MATCH.** A manifest rebuild does **not** unblock today's gate. |
| Fix-1 | **sim per-bar scorer artifact-not-found (rc=1)** — most frequent June failure | Every cut, June | Derived WF-eval config resolves per-bar scorers from `artifacts/sim/artifacts/walkforward_v2_20260602/<date>/panel-ltr.json` (does **not** exist), while the validated manifest is `artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json` → `walkforward_gbdt_prod_recipe_v2/<date>/panel-ltr.json` (**does** exist) → `FileNotFoundError` (`backtesting/renquant_104/adapters/sim.py:851` → `panel_scorer.py:201`) | Yes — path inconsistency |
| Fix-2 | **WF config parity — PatchTST-kind vs GBDT-artifact** | Every run | Derived config inherits `panel_scoring.kind = hf_patchtst` from the live config but points the path at a GBDT `panel-ltr.json` → parity FAIL ("PatchTST scorer kind should not point at a non-PatchTST JSON artifact") | Yes — config-derivation bug |
| Fix-3 | **§5.2 placebo_ic floor is structurally unsatisfiable** | Every run since 06-09 | Gate requires `placebo_ic < 0.5 × \|aligned_real_ic\|`, but the 60-day label carries a ~+0.04 embargo-leakage floor; even at a 120d (2×horizon) shift the placebo IC (+0.035→+0.053) exceeds the threshold (+0.030→+0.043) | Yes — structural floor, independent of model quality |
| Fix-4 | **Substance — GBDT did not beat SPY** | Only the mechanically-clean runs, 06-11→14 | Mean 3-cut Sharpe ~+0.356, **0 / 3** cuts beat SPY, ΔSharpe −0.72; failed trade-gate monotonicity in BULL_CALM | **No** — this is the gate correctly rejecting a weak model |

The key reading: **Fixes 1–3 are mechanical/vestigial** (config-path bugs plus a
structural placebo floor, on a model that is no longer even the primary scorer).
**Fix-4 is the gate working correctly** — even after Fixes 1–3, this GBDT would
not pass on substance.

## 2. Goal

No production model — per-ticker tournament **or** panel — is ever older than
**28 calendar days**. If the normal retrain → gate → promote path cannot deliver
a fresh model, **fall back to the best model trained in the last 10 days** rather
than letting the live model age past the ceiling.

Plus three enabling objectives:

- make staleness **observable** (today it is silent until the universe zeroes);
- make retrain **reliable** (the tournament timeout and the vestigial GBDT gate);
- **clean up** the vestigial GBDT gate so the strict path can actually pass a
  good model — minimising how often the fallback must fire.

## 3. Design — three pillars + WF-gate cleanup

### Pillar 1 — 28-day hard ceiling + tiered freshness monitor

A daily monitor computes `age = today − trained_date` for (a) the panel prod
artifact and (b) the per-ticker tournament artifacts (min / median / max).

| Tier | Age | Action |
|------|-----|--------|
| healthy | ≤ 14d | none |
| warn | 14–21d | ntfy info; retrain due |
| escalate | 21–28d | ntfy warn; trigger on-demand retrain |
| breach | > 28d | trigger the Pillar-3 fallback **before** the universe gate zeroes buys; page operator |

Lower `model_staleness_days` from **60 → 28** — but **only after** the fallback +
cadence land. Tightening it first, with no fallback, makes the gating strictly
worse. Applies to **both** models.

### Pillar 2 — Reliable, monitored retrain cadence

- **Per-ticker tournament:** make the timeout fix durable —
  `parallel_ticker_timeout_seconds` 600 → ≥ 2400, or make the phase timeout scale
  with universe size; consider raising `parallel_workers` above auto. Restore a
  scheduled cadence.
- **Panel:** resolve the vestigial GBDT gate (Fix-2 below) and validate the
  **actual PatchTST production path**.
- **Cadence health is itself monitored:** alert if no successful retrain of
  *either* model in 14d.

### Pillar 3 — Best-of-last-10-days fallback auto-promote (the core directive)

Every retrain writes a **STAGING** artifact with `trained_date` + computable
quality metrics (WF / `genuine_ic`, holdout Sharpe, smoke-test deltas) **even
when it fails the strict gate**. Formalise the rolling staging registry (the
`*.staging.json` set already accumulates).

When the prod model would breach 28d **AND** the newest retrain failed the strict
WF gate:

1. select the **best** staging model trained within the **last 10 calendar days**
   by a pre-defined quality score;
2. verify it passes a **basic-integrity floor** — loads; scores a smoke panel
   without NaN; not degenerate / all-one-sign; recipe loads;
3. **auto-promote** it (supersede the stale prod) with loud ntfy + a provenance
   stamp marking it a **freshness-fallback** (a monitored exception), reversibly
   (retain the superseded artifact).

Never fall back to anything older than 10d. If nothing fresh exists within 10d,
that is a **cadence-down emergency**: page the operator; do **not** promote stale.

**The tradeoff, stated plainly and honestly.** The fallback deliberately trades
on models the strict gate rejected. Justification:

1. **The rejects are largely MECHANICAL / vestigial** — config-path bugs (Fix-1,
   Fix-2) plus a structural placebo floor (Fix-3) on a model that is not even the
   primary scorer — not a substance veto.
2. **Even where edge is marginal, staleness is the more certain risk.** A fresh
   model under the current regime is a smaller, less-certain risk than a 4–8-week-
   stale model.
3. **The strict gate remains the PREFERRED path.** The fallback is a bounded
   safety net — basic-integrity floor + best-of-recent (not newest-only)
   selection — not a replacement for the gate.

### WF-gate cleanup (so the strict path can PASS a good model)

This is what keeps the fallback rare — if the strict path can pass a legitimately
good model, the fallback almost never fires.

- **Fix-1** — unify the sim per-bar artifact path to
  `walkforward_gbdt_prod_recipe_v2`.
- **Fix-2** — **retire OR re-kind** the GBDT weekly promote: derive a GBDT-kind WF
  config instead of inheriting the live PatchTST kind, **and** validate the real
  PatchTST production path. Per the "PatchTST primary" decision, **retiring** the
  vestigial GBDT weekly promote is likely correct and removes most of the noise.
- **Fix-3** — replace the absolute placebo **ceiling** with a placebo-clean
  **difference** test (`real_ic − placebo_ic > margin`), or widen the embargo so
  the placebo shift clears the 60d label window.
- **Fix-4** is **not** a code fix — it is the gate correctly rejecting a sub-SPY
  model. The fallback's basic-integrity floor + best-of-recent selection is how we
  stay fresh **without** promoting a substance-failing model.

## 4. Rollout (staged, monitored, reversible)

| Phase | Scope | Risk |
|-------|-------|------|
| 0 (DONE) | Emergency per-ticker tournament retrain via a side config (`strategy_config.tournament_retrain.json`, timeout 3600) to clear today's 61d breach — already running **outside this PR** | operational |
| 1 | Ship the freshness **monitor** (observe-only ntfy tiers) + the durable timeout fix + restore the tournament cadence | low |
| 2 | WF-gate cleanup (Fix-1 / 2 / 3) — retire/re-kind the vestigial GBDT promote, unify paths, fix the placebo test; validate the PatchTST path passes | medium |
| 3 | The best-of-10d fallback auto-promote, **SHADOW-FIRST** (log what it *would* promote for ~1 week), then enable behind a flag | medium |
| Final | Flip `model_staleness_days` 60 → 28 — only after Phases 1–3 are live | low |

## 5. Safety / guards

- basic-integrity floor on **every** fallback promote;
- loud ntfy + provenance stamp on every fallback;
- reversible — retain the superseded artifact;
- recency cap at 10d; nothing older is ever promoted;
- cadence-down **pages the operator** (never silently promotes stale);
- ALL changes are config / script — **no broker, risk-cap, or sizing changes**;
- never bypass branch protection;
- cross-repo **implementation** happens in follow-up per-repo PRs **after** this
  design is discussed.

Cross-repo touch points:

- `renquant-pipeline` — `job_universe` staleness + the monitor;
- `renquant-strategy-104` config — `model_staleness_days`,
  `parallel_ticker_timeout_seconds`;
- umbrella `RenQuant/scripts` — `weekly_wf_promote`, train cadence,
  `run_wf_gate` placebo test, and the new fallback-promote logic.

## 6. Open questions for Codex / operator

1. **Fallback quality metric** — `genuine_ic` vs holdout Sharpe vs OOS IC: which
   is most trustworthy *on a gate-fail*?
2. **Numerics** — are 28d / 10d right? (28d ≈ 4 weekly cycles + buffer; 10d ≈ ~2
   cycles.)
3. **GBDT weekly promote** — retire it **entirely** vs **re-kind** it?
4. **Panel admission** — should we also gate panel admission on staleness?
   (Today only the per-ticker tournament gates the universe.)
