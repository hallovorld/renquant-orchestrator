# Design: Shadow scorer (PatchTST) freshness — restore the stopped retrain cadence + monitor (the shadow axis of #210)

STATUS: design for review (no implementation in this PR — describe → discuss →
PR to Codex → then implement per-repo). This document changes **no** code,
config, broker, risk-cap, or sizing behaviour. It is scoped to the **SHADOW**
panel scorer (a champion–challenger / model-monitoring concern), **not** the live
trading path.

This RFC is a **companion to PR #210** (`doc/design/2026-06-30-model-freshness-governance.md`).
#210 governs a matrix of **{prod, shadow} × {panel, per-ticker}** model
populations and covers the **prod panel** and the **per-ticker tournament** cells.
It does **not** cover the **shadow panel** cell. This RFC fills exactly that cell
and **reuses** #210's machinery (the data-cutoff freshness key, the tiered
monitor, the ownership split, the staged/reversible rollout) rather than
duplicating it.

## 0. Where this sits — the shadow-panel cell of #210's freshness matrix

| | panel scorer | per-ticker tournament |
|---|---|---|
| **prod** | #210 §1B — XGB `panel-ltr.alpha158_fund`, 05-18, WF-promote chronically rejects | #210 §1A — 600s timeout, 67/142 finish |
| **shadow** | **THIS RFC** — HF PatchTST `pt07…20260522`, frozen ~05-22, no retrain cadence | (out of scope; the tournament has no shadow twin) |

The production **primary** today is the XGB/GBDT panel scorer
(`ranking.panel_scoring.kind = "xgb"`, an operator-directed switch on 2026-06-23;
see #210 §0). **PatchTST is the SHADOW scorer** — scored and logged via MLflow but
**not** the live decision (`LoadScorerTask: loaded xgb` primary +
`ApplyShadowScoringTask: shadow hf_patchtst`). So a stale shadow scorer is **not a
live-trading risk**. It is a **model-monitoring** failure: the champion–challenger
comparison that is supposed to tell the operator whether PatchTST should ever be
re-promoted is **meaningless** when the challenger is 39 days (and ~140 data-days)
behind the champion. You cannot trust a challenger you never refreshed.

None of the three RenQuant model populations — prod XGB panel, per-ticker
tournament, **shadow PatchTST panel** — currently has a reliably-running,
**monitored** refresh cadence. #210 addresses the first two; this RFC addresses the
third so the set is complete.

## 1. Problem + root cause (confirmed read-only, 2026-06-30)

**The live shadow PatchTST scorer is frozen, and it is frozen for TWO compounding
reasons — not one.** Both were confirmed read-only against the live umbrella tree.

### 1.1 The served shadow artifact is stale

The pinned shadow config
`renquant-strategy-104/configs/strategy_config.shadow.json` sets:

- `ranking.panel_scoring.kind = "hf_patchtst"`
- `ranking.panel_scoring.artifact_path =
  ../../artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt`

That artifact's `model.pt` has an mtime of **2026-05-22**, and its metadata reads
`trained_date = 2026-05-22`, `effective_train_cutoff_date = 2024-11-13`,
`effective_selection_cutoff_date = 2026-02-10`. As of 2026-06-30 the **artifact
age is ~39 calendar days**; by #210's *data-cutoff* freshness key (freshness keys
on the DATA cutoff, never `trained_date` alone — #210 §2) the served model has seen
**no data past 2026-02-10**, i.e. its fast-axis data cutoff is **~140 days behind**.

### 1.2 The retrain cadence is unowned — there is no scheduled job

`scripts/weekly_retrain_patchtst.sh` (an umbrella script that delegates to the
orchestrator-owned `renquant_orchestrator.build_patchtst_wf_manifest` pipeline) is
**not wired to any scheduler**. `launchctl list | grep renquant` shows the other
scheduled model jobs — `retrain-panel104`, `conditional-retrain104`,
`retrain-alpha158-linear`, `monthly-meta-label-retrain`, `weekly-wf-promote`,
`weekly-fundamental-refresh`, `monthly-calibrator-refresh`, `weekly-apy104`,
`daily104`, `intraday104`, etc. — but **no `weekly-retrain-patchtst`** entry. The
script has therefore run only when a human invoked it: the log directory
`logs/weekly_retrain_patchtst/` contains exactly three files —
`2026-06-07.log`, `2026-06-08.log` (rc=0), and `2026-06-16.log` (rc=0, finished
2026-06-17T09:06Z). **The last run was 2026-06-16, and nothing has run in the ~2
weeks since.** (The parent investigation cited 2026-06-08; the ground-truth
last-run is 2026-06-16 — both were manual, and the material fact is unchanged:
there is no scheduled cadence, so the job is unowned and has lapsed.)

### 1.3 Even a retrain does NOT unfreeze the served model (the deeper gap)

This is the non-obvious part and the reason "just re-run the script" is
insufficient. `weekly_retrain_patchtst.sh` writes a **walk-forward validation
manifest** — per-cutoff artifacts under
`backtesting/renquant_104/artifacts/walkforward_patchtst/<cutoff>/` plus
`walkforward_patchtst_manifest.json` — whose **latest cutoff is 2026-03-09** (itself
bounded by the source manifest and the training panel
`data/transformer_v4_wl200_clean.parquet` ending 2026-02-10). It does **not** touch
the served snapshot `patchtst_shadow/pt07…20260522/`. The served artifact is pinned
by a **fixed absolute path** in `strategy_config.shadow.json`; no automated
promote advances that pin to a freshly-retrained model. So even the 2026-06-08 and
2026-06-16 runs left the served shadow model at its 2026-05-22 bytes (confirmed:
`model.pt` mtime unchanged at 22 May after both runs).

This is a textbook instance of the repo's recurring *"merged is not deployed /
deployed-but-dark"* failure: producing a fresh artifact is not the same as serving
it. **A freshness fix must restore both the cadence AND the retrain → served-pin
promote step**, or the model will keep aging in place while the retrain "succeeds".

### 1.4 Parallel to the other two broken populations (#210)

The same disease, three organs: the per-ticker tournament froze because its retrain
**timed out** (#210 §1A, `parallel_ticker_timeout_seconds = 600`, 67/142 finish;
manually unblocked 2026-06-30); the prod XGB panel froze because its weekly
**WF-promote chronically rejects** (#210 §1B, `panel-ltr.alpha158_fund` at 05-18);
and the shadow PatchTST froze because its retrain **has no scheduled job and no
serving promote** (this RFC). All three share the root pathology #210 names:
**refresh cadence that is neither reliable nor monitored.**

## 2. Why it matters (and why it is bounded)

Because PatchTST is shadow-only, a stale shadow model **cannot move capital** — the
blast radius is the champion–challenger evaluation, not the live book. But the
whole point of running PatchTST as a logged shadow is to answer *"is the challenger
good enough to re-promote?"* A challenger frozen 39 days / ~140 data-days behind the
prod XGB champion makes every prod-vs-shadow MLflow delta an artefact of vintage
skew, not model quality. The shadow comparison is silently producing numbers the
operator might act on, and those numbers are **not trustworthy**. That is the harm
this RFC removes — a **monitoring-integrity** harm, deliberately kept distinct from
#210's live-trading-risk framing.

## 3. Design

Three complementary pieces. None is a trading gate; all reuse #210's contracts.

### 3.1 A reliable, MONITORED retrain cadence for the shadow scorer (+ serving promote)

- **Restore the scheduled job.** (Re)install a `com.renquant.weekly-retrain-patchtst`
  launchd job that runs `scripts/weekly_retrain_patchtst.sh` **weekly**, matching
  the cadence of the other scorers (`weekly-wf-promote`, `weekly-fundamental-refresh`).
  Cadence health is itself monitored (§3.2): a *"last successful shadow retrain"*
  timestamp is stamped on each rc=0 run, and an alert fires if it exceeds the
  staleness tier — closing the exact gap that let this job silently lapse.
- **Add the missing retrain → served-pin promote step (the §1.3 gap).** A successful
  retrain must be followed by an explicit, atomic promote that advances the served
  shadow snapshot (or the `strategy_config.shadow.json` `artifact_path` pin) to the
  fresh model, **stamped against the current pinned shadow config fingerprint**
  (§3.3). Write-new-then-swap; the shadow decision never reads a half-written
  artifact; the superseded artifact is retained for reversal. Because this is the
  shadow path, the promote can be **fully automatic** (no operator gate) — there is
  no capital at risk — which is the key simplification versus #210's prod promote.
- **Name the data-vintage dependency (do not silently absorb it).** The served
  model's data cutoff is capped by the training panel
  `data/transformer_v4_wl200_clean.parquet` (ends 2026-02-10). Restoring the cadence
  refreshes the WF corpus and the served bytes, but the model's *data* freshness is
  bounded by that panel's vintage. A full fast-axis fix therefore also depends on the
  upstream panel-dataset refresh (base-data/model ownership), consistent with #210's
  data-cutoff freshness key. This RFC restores the cadence + promote; it flags the
  panel refresh as a named upstream dependency, not in-scope work.

### 3.2 A shadow-scorer freshness monitor (reuse #210's tiered monitor)

Reuse #210 Pillar 1's daily, observe-only monitor and its data-cutoff freshness
key — applied to the shadow artifact. Two things the shadow monitor keys on:
(a) the **served artifact's** age/data-cutoff (§1.1), and (b) the **retrain
cadence** — the *"last successful shadow retrain"* timestamp (§3.1). Tiers, keyed
to the weekly cadence and deliberately more lenient at the breach end than #210's
trading ceiling:

| Tier | Age since last fresh shadow retrain/promote | Action |
|------|--------------------------------------------|--------|
| healthy | ≤ 14d (≈ 2 weekly cycles) | none |
| warn | 14–21d | ntfy info; shadow retrain overdue |
| escalate | 21–28d | ntfy warn; **trigger an on-demand shadow retrain + promote now** |
| breach | > **35d** | flag the prod-vs-shadow comparison as **UNTRUSTWORTHY** and suppress/annotate the challenger deltas in the shadow report; notify the **model-monitoring owner** — **not** a live-trading page |

**Chosen breach ceiling = 35d, and why it is looser than #210's 28d prod ceiling.**
#210's 28d fast-axis ceiling binds a model that **trades capital**; a breach there is
a live-risk event that pages the operator. The shadow model trades nothing, so a
breach here degrades only the *challenger comparison's validity* — a monitoring
artefact, not risk. A modestly looser 35d ceiling (a) avoids paging a trading
operator on a non-trading axis, while (b) still bounding how meaningless the
comparison is allowed to get before it is explicitly marked untrustworthy. Because
the shadow monitor is **observe-only and touches no trading decision**, this 35d is a
cheap, reversible **monitor-tier default** — it does **not** require the §5-style
point-in-time replay authorization that #210 rightly demands of its *trading*
ceiling. It is proposed as a default to confirm in discussion (see §6), not asserted
as earned truth. Note: the current served model (~39d) is **already past this
breach** — which is precisely the signal a monitor would have surfaced ~4 days ago
had it existed.

### 3.3 Reconcile with the shadow config-fingerprint fail-closed (do not reintroduce it)

The shadow PatchTST path **fail-closes** when the live
`strategy_config.shadow.json` config fingerprint (watchlist / sector_map /
lookahead / etc.) drifts from the fingerprint **stamped into the model metadata**:
`panel_scorer_config_mismatch → clears all → "no trade"`. The evidence of this is
already on disk — the served model carries
`config_fingerprint = sha256:f8fb2259b2bf1537`
(`config_fingerprint_stamped_from = strategy_config.shadow.json`) with a
`…metadata.json.bak.20260625-restamp` sibling: the 2026-06-25 **re-stamp** event
(the metadata mtime of 25 Jun is that re-stamp, **not** a retrain).

The distinction the freshness fix must preserve:

- **Re-stamp handles CONFIG drift** (additive watchlist/sector_map growth on an
  otherwise-valid model) — `scripts/stamp_patchtst_fingerprint.py` re-stamps the
  model against the **pinned** config. This is **not** a retrain and must remain the
  mechanism for keeping an unchanged model servable across additive drift.
- **Retrain handles DATA/staleness drift** (this RFC) — produces a **new** model
  whose fingerprint is stamped from the current pinned config at promote time.

Two guardrails so the freshness fix does not reintroduce the fail-closed:

1. **Every fresh shadow promote (§3.1) stamps against the current pinned
   `strategy_config.shadow.json` fingerprint** — never an older one — so a
   just-promoted model cannot immediately `panel_scorer_config_mismatch`.
2. **The monitor must not conflate the two conditions.** A config-FP fail-closed
   ("no trade" from a fingerprint mismatch) is a **contract** event, not a staleness
   breach; the freshness monitor keys on age/data-cutoff only, and the config-FP
   mismatch keeps its own separate alarm and its own remedy (re-stamp). Conflating
   them would mask a stale model behind a "config" label or vice-versa.

## 4. Immediate operational remediation (execute AFTER this design is discussed — NOT in this PR)

Per the repo's discuss-before-implement rule, this PR does **not** execute any of
the following. It specifies them so they can be run once the design is agreed:

1. **One manual refresh now.** Run `scripts/weekly_retrain_patchtst.sh` once to
   rebuild the shadow WF corpus, then **promote** the fresh model to the served
   shadow pin (re-stamped against the pinned `strategy_config.shadow.json`, §3.3) so
   the served shadow snapshot advances off its 2026-05-22 bytes. (Refreshing the WF
   corpus alone — as the 06-08 / 06-16 runs did — does **not** unfreeze the served
   model; the promote is the load-bearing step, §1.3.)
2. **(Re)install the scheduled job.** Install the `com.renquant.weekly-retrain-patchtst`
   launchd plist so the weekly cadence resumes and never silently lapses again.
3. **Verify the monitor sees it.** Confirm the *"last successful shadow retrain"*
   timestamp updates and the freshness tier returns to `healthy`.

These are umbrella-ops actions on the live tree; they are **not** performed by any
agent as part of this design PR.

## 5. Rollout, ownership, provenance

**Staged, monitored, reversible; design-only.** Per-repo implementation follows
after discussion, mirroring #210's phasing.

| Phase | Scope | Risk |
|-------|-------|------|
| 1 (near-term) | Shadow freshness **monitor** (observe-only, §3.2) + *"last successful shadow retrain"* timestamp | low |
| 2 | **(Re)install the weekly scheduled job** (§3.1) + the manual refresh/promote remediation (§4) | low (shadow, no capital) |
| 3 | **Automated retrain → served-pin promote** step (§3.1), atomic + re-stamped against the pinned config (§3.3) | low–medium |
| 4 | Confirm the 35d breach-tier default in discussion; wire the untrustworthy-comparison annotation into the shadow report (§3.2) | low |

Operational safety (reused from #210): remediation triggers **before** the breach
(escalate at 21–28d fires an on-demand retrain); **atomic** write-new-then-swap
promote; the superseded artifact is retained for **rollback**; every promote stamps
the run bundle with the selected artifact, its data-cutoff axes, and the superseded
artifact id. All changes are config / script — **no broker, risk-cap, or sizing
changes; never bypass branch protection.**

**Ownership** (mirrors #210's split; umbrella scripts schedule/invoke but do not own
model selection):

| Concern | Owner repo |
|---|---|
| Shadow retrain **script + launchd schedule** (`weekly_retrain_patchtst.sh`, the plist) | **umbrella ops** (`RenQuant/scripts` + launchd) |
| Shadow model **recipe / WF corpus / promote-to-served mechanics** | **backtesting / model** |
| Shadow **freshness policy + tiers + `artifact_path` pin** | **strategy-104 config** (`strategy_config.shadow.json`) |
| Shadow **freshness monitor + run-bundle provenance + cross-repo sequencing** | **renquant-pipeline / renquant-orchestrator** |

## 6. Open questions (for Codex / operator)

1. **Breach ceiling.** Is **35d** the right shadow breach tier, or should the shadow
   monitor simply reuse #210's 28d (uniform ceiling, simpler) given both are
   observe-only? (Proposed: 35d, non-trading rationale in §3.2.)
2. **Promote autonomy.** Should the retrain → served-pin promote be **fully
   automatic** for the shadow path (proposed, since no capital is at risk), or should
   it require the same operator confirmation #210 reserves for the prod promote?
3. **Data-vintage dependency.** The served shadow model's data cutoff is capped by
   the training panel (2026-02-10). Is refreshing that panel in-scope for the shadow
   freshness effort, or a separate base-data/model track that this RFC only names as
   a dependency? (Proposed: name-only here.)
4. **Cadence match.** Weekly is proposed to match the other scorers; is a different
   shadow cadence (e.g. bi-weekly) acceptable given it is non-trading and the panel
   vintage is the binding constraint anyway?
