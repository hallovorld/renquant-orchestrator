# Design: Shadow scorer (PatchTST) freshness — restore the stopped retrain cadence + monitor (the shadow axis of #210)

STATUS: design for review (no implementation in this PR — describe → discuss →
PR to Codex → then implement per-repo). This document changes **no** code,
config, broker, risk-cap, or sizing behaviour. It is scoped to the **SHADOW**
panel scorer (a champion–challenger / model-monitoring concern), **not** the live
trading path.

REVISION: **r2 (round-2)** — addresses Codex's review of r1 (head `c771eab6`), which **accepted
the diagnosis** (the shadow retrain has no scheduler; successful WF runs do not advance the
served shadow pin) and raised **ONE** blocking issue: **cadence + automatic promotion do NOT
make stale INPUT DATA fresh.** r1 confirmed the training panel ends 2026-02-10, then left that
panel refresh out of scope while proposing an immediate retrain/promote and marking the monitor
healthy on retrain success — which would churn the served pin to a **newly-created artifact
carrying the SAME ~140-day-old information set** (reset operational timestamps, no actual data
freshness): exactly the `trained_date`-versus-data-cutoff error #210 §2 is built to prevent. r2
fixes this by making point-in-time DATA freshness — not cadence or pin-churn — the thing the fix
actually repairs: it makes the upstream **point-in-time panel refresh a PREREQUISITE** for the
shadow retrain/promote (§3.1); requires the promote to **FAIL CLOSED** unless every
recipe-required source is on its **source-specific SLA** (reusing #210 §2/§3) **AND** the
effective training/selection cutoffs **actually advance** — an explicitly-justified no-advance
retrain is **LABELED non-fresh** and does not reset the freshness clock (§3.1, §3.4); adds a
**validated-promote gate** (§3.4) so `rc=0` is not enough to change the served pin (artifact
load + smoke inference, schema/recipe/config-fingerprint parity, non-degenerate outputs,
resource bounds, a minimum shadow-quality sanity floor — else keep the old pin); states the
**blast radius** (shadow moves no capital but shares the inference + reporting paths, so a broken
shadow artifact can still fail the daily pipeline or corrupt champion–challenger evidence — §2);
and **re-keys the freshness monitor's `healthy` state to the served artifact's BINDING DATA
CUTOFF + a successful VALIDATED promote**, never merely "last successful retrain" (§3.2),
explicitly consistent with #210 §2's data-cutoff-not-`trained_date` key. Prior: r1 (head
`c771eab6`) diagnosed the two compounding freezes (no scheduled job; retrain does not advance the
served pin) and proposed cadence + monitor + config-FP reconcile.

This RFC is a **companion to PR #210** (`doc/design/2026-06-30-model-freshness-governance.md`).
#210 governs a matrix of **{prod, shadow} × {panel, per-ticker}** model
populations and covers the **prod panel** and the **per-ticker tournament** cells.
It does **not** cover the **shadow panel** cell. This RFC fills exactly that cell
and **reuses** #210's machinery (the data-cutoff freshness key, the tiered
monitor, the ownership split, the staged/reversible rollout) rather than
duplicating it.

## Response to Codex review (per-point map)

Codex **accepted r1's diagnosis** (no scheduler; successful WF runs do not advance the served
pin) and raised **ONE** blocking issue. It is resolved by making point-in-time **DATA freshness**
— not cadence or pin-churn — the thing the fix actually repairs.

| Codex blocker | Resolution in r2 | Section |
|---|---|---|
| **Cadence + automatic promotion do not make stale INPUT DATA fresh.** r1 confirms the training panel ends 2026-02-10, then leaves that panel refresh out of scope while proposing an immediate retrain/promote and marking the monitor healthy after success — producing a newly-created artifact with the SAME ~140-day-old information set, resetting operational timestamps and churning the served pin without repairing data freshness (the `trained_date`-versus-data-cutoff error #210 prevents). Make upstream point-in-time panel refresh a **prerequisite**, not a name-only dependency. A promote must **fail closed** unless every recipe-required source is on its **source-specific SLA** and the effective cutoffs **actually advance** (or a justified no-advance retrain is **labeled non-fresh**). `rc=0` is **insufficient**: require artifact load / smoke inference, schema/recipe/config-fingerprint parity, non-degenerate outputs, resource bounds, and a minimum shadow-quality sanity floor before atomically changing the served pin. Shadow moves no capital, but it shares the **inference and reporting paths**, so a broken artifact can still fail the daily pipeline or corrupt champion–challenger evidence. Key the monitor's healthy state to the served artifact's **binding data cutoff** and a successful **validated promote**, never merely "last successful retrain." | (1) **§3.1 makes upstream POINT-IN-TIME PANEL REFRESH a PREREQUISITE** of the shadow retrain/promote — the recipe-required sources (transformer panel `transformer_v4_wl200_clean.parquet` + rawlabel + fundamentals) must be refreshed to current point-in-time before a retrain is meaningful; **no longer** a name-only / out-of-scope dependency (§6 Q3 updated). (2) **§3.1 + §3.4 make the promote FAIL CLOSED unless** every recipe-required source is on its **source-specific SLA** (reusing #210 §2/§3's per-source SLA framing) **AND** `effective_train_cutoff_date` / `effective_selection_cutoff_date` **ACTUALLY ADVANCE** past the served pin; an explicitly-justified no-advance retrain is **LABELED non-fresh** and does **not** reset the freshness clock. (3) **New §3.4 validated-promote gate:** before the atomic pin swap, `rc=0` is not enough — require artifact **LOAD + SMOKE INFERENCE**, **schema / recipe / config-fingerprint PARITY** (reconciled with the `panel_scorer_config_mismatch` re-stamp issue, §3.3), **NON-DEGENERATE** outputs, **RESOURCE** bounds, and a **minimum shadow-quality SANITY FLOOR** — else fail closed and **keep the old pin**. (4) **§2 states the blast radius:** shadow moves no capital but **shares the inference + reporting paths**, so a broken shadow artifact can still fail the daily pipeline or corrupt champion–challenger evidence → the validation gate is **not optional**. (5) **§3.2 re-keys the monitor's `healthy` state to the served artifact's BINDING DATA CUTOFF + a successful VALIDATED promote** (per-source SLA on the recipe's actually-used feeds), **never** "last successful retrain" — explicitly consistent with #210 §2's data-cutoff-not-`trained_date` key. | §2, §3.1, §3.2, §3.4, §6 |

**Required-CI note.** Codex requires the repo's required checks green before merge. This revision
keeps the branch current by **merging `origin/main`** (which carries the weekly-APY look-ahead
fix, PR #211) so the shared `test` check reruns against fixed code. This PR remains **docs-only**
(no code / config / broker / risk / sizing change).

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

**Blast radius — bounded, but not zero (why the validation gate is not optional).** "Shadow"
bounds *capital* risk to zero; it does **not** bound *operational* risk. The shadow scorer runs
inside the **same daily pipeline** and **shares the inference and reporting paths** with the prod
decision (`ApplyShadowScoringTask` on the live run; the shadow deltas land in the same run
report). So a broken or degenerate shadow artifact — a bad promote, a schema/fingerprint
mismatch, an OOM, NaN scores — can still **fail the daily run** or **corrupt the
champion–challenger evidence** the operator reads. A shadow promote that merely "succeeds with
`rc=0`" is therefore **not** safe. This is exactly why the automatic shadow promote must still be
**gated**, not merely *automatic* (§3.4): "automatic" here means unattended, never unchecked.

## 3. Design

Three complementary pieces. None is a trading gate; all reuse #210's contracts.

### 3.1 Refresh the DATA first, then a reliable cadence + a VALIDATED serving promote

The order is load-bearing: **fresh data → retrain → validated promote → cadence.** r1 had this
backwards — it proposed restoring the cadence and an automatic promote while leaving the data
refresh out of scope, which would churn the served pin to a new artifact carrying the **same
2026-02-10 information set**. Cadence and pin-churn are **not** freshness.

- **Upstream POINT-IN-TIME panel refresh is a PREREQUISITE (not a name-only dependency).** The
  served model's data cutoff is capped by its recipe's **actually-used** sources — chiefly the
  transformer training panel `data/transformer_v4_wl200_clean.parquet` (ends 2026-02-10), plus
  the rawlabel and the fundamentals feed those sources depend on. **These must be refreshed to
  the current point-in-time BEFORE a retrain is meaningful.** A retrain on the stale panel just
  re-mints 2026-02-10 information under a new `trained_date` — the precise failure Codex flagged.
  Refreshing the panel is base-data / model-owned work, but this RFC now treats it as an
  **in-line prerequisite of the shadow retrain/promote**, not out-of-scope (§6 Q3 updated). This
  is the load-bearing change versus r1.
- **The retrain → served-pin promote must FAIL CLOSED unless the DATA actually advanced.** A
  successful WF run (`rc=0`) is necessary but **not** sufficient to promote. The promote proceeds
  **only if** (a) **every recipe-required source is on its own source-specific SLA** — reusing
  #210 §2/§3's per-source SLA framing (fast axis: OHLCV / price-derived / retrain-data cutoff
  within the fast ceiling; slow axis: quarterly fundamentals / estimates on their filing-calendar
  SLA), **not** one global age — **AND** (b) the fresh model's **`effective_train_cutoff_date` /
  `effective_selection_cutoff_date` ACTUALLY ADVANCE** past the currently-served pin's. If a
  retrain is deliberately run on a non-advancing panel (e.g. to pick up a code/recipe fix), the
  resulting artifact is **explicitly LABELED non-fresh**: it may still be promoted for the
  stated recipe-fix reason, but it **does NOT reset the freshness clock** (§3.2) and the monitor
  keeps reporting the unchanged binding data cutoff. Otherwise the promote **fails closed and
  keeps the old pin.**
- **The promote itself must pass the validated-promote gate (§3.4) — `rc=0` is not enough.**
  Because the shadow path shares the daily inference + reporting paths (§2), the atomic pin swap
  is additionally gated on artifact load + smoke inference, schema/recipe/config-fingerprint
  parity, non-degenerate outputs, resource bounds, and a minimum shadow-quality sanity floor.
  Write-new-then-swap; the shadow decision never reads a half-written artifact; the superseded
  artifact is retained for reversal. See §3.4.
- **Restore the scheduled job — as the CADENCE, not the freshness key.** (Re)install a
  `com.renquant.weekly-retrain-patchtst` launchd job that runs
  `scripts/weekly_retrain_patchtst.sh` **weekly**, matching the other scorers
  (`weekly-wf-promote`, `weekly-fundamental-refresh`). A **cadence-lapse** alert fires if no run
  completes on schedule, so the job cannot silently lapse again. But the monitor enforces the
  distinction (§3.2): **a run completing on schedule is a LIVENESS signal, not a freshness
  signal** — a weekly job faithfully re-minting stale data is still stale. Because no capital is
  at risk the promote can run **without an operator gate — but never without the §3.4
  validated-promote gate and the §3.1 fail-closed conditions**; "automatic" means unattended, not
  unchecked. This is the only simplification versus #210's operator-gated prod promote.

### 3.2 A shadow-scorer freshness monitor (reuse #210's tiered, DATA-cutoff monitor)

Reuse #210 Pillar 1's daily, observe-only monitor and — critically — its **data-cutoff freshness
key**: freshness keys on the served artifact's **binding DATA cutoff**, never on `trained_date`
or a "last successful retrain" run-time (#210 §2). The shadow monitor's `healthy` state requires
**BOTH** of the following to hold — this is the direct fix to Codex's blocker:

- (a) the **served** artifact's binding data cutoff is on-SLA, judged **per-source** across the
  recipe's actually-used feeds (#210 §2/§3: fast axis within the fast ceiling; slow axes on their
  filing-calendar SLA) — **not** one global age; **and**
- (b) the served artifact reached the pin via a **successful VALIDATED promote** (§3.4) and is
  **not** labeled non-fresh (§3.1).

A run "completing on schedule" is explicitly **NOT** sufficient for `healthy`: a weekly job that
faithfully re-mints 2026-02-10 data, or a promote that failed the §3.4 gate and kept the old pin,
leaves the monitor **not-healthy** even though the cadence "ran". Retrain cadence / last-run time
is still **tracked and alerted separately** (a lapsed cadence is its own warning), but it is a
*liveness* signal — **never** the *freshness* key. Tiers, keyed on the **served artifact's binding
data cutoff** (with the cadence-lapse alert as a parallel track), deliberately more lenient at
the breach end than #210's trading ceiling:

| Tier | Served artifact freshness (keyed on BINDING DATA CUTOFF, per-source SLA — #210 §2/§3) | Action |
|------|--------------------------------------------------------------------------------------|--------|
| healthy | every recipe-required source on-SLA (fast axis ≤ #210's 28d fast ceiling; slow axes on filing SLA) **AND** the pin was set by a validated promote (§3.4), not labeled non-fresh | none |
| warn | fast-axis data cutoff 28–33d behind its SLA | ntfy info; shadow data refresh overdue |
| escalate | fast-axis 33–35d behind, **or** any recipe-required source off its SLA, **or** the cadence produced no validated fresh promote in ≈2 cycles | ntfy warn; **trigger the §3.1 panel-refresh → retrain → validated-promote pipeline now** |
| breach | fast-axis data cutoff > **35d** past its SLA, **or** the served pin is non-advancing / labeled non-fresh | flag the prod-vs-shadow comparison as **UNTRUSTWORTHY** and suppress/annotate the challenger deltas in the shadow report; notify the **model-monitoring owner** — **not** a live-trading page |

**Chosen breach ceiling = 35d on the DATA cutoff, and why it is looser than #210's 28d prod
ceiling.** Both ceilings now bind the same thing — the served model's **fast-axis data cutoff**
(#210 §2) — which makes the comparison clean: #210's 28d binds a model that **trades capital**, so
a breach pages the operator; the shadow model trades nothing, so a breach degrades only the
*challenger comparison's validity* — a monitoring artefact, not risk. A modestly looser 35d
data-cutoff ceiling (a) avoids paging a trading operator on a non-trading axis, while (b) still
bounds how meaningless the comparison is allowed to get before it is explicitly marked
untrustworthy. Because the shadow monitor is **observe-only and touches no trading decision**,
this 35d is a cheap, reversible **monitor-tier default** — it does **not** require the §5-style
point-in-time replay authorization that #210 rightly demands of its *trading* ceiling. It is
proposed as a default to confirm in discussion (§6), not asserted as earned truth. Note: the
current served model's data cutoff (2026-02-10, **~140 data-days behind**) is **far past** this
35d breach — precisely the untrustworthy state a data-cutoff monitor would surface, and one that
**no amount of pin-churn without the §3.1 panel refresh can clear** (a fresh `trained_date` on the
same panel would still read breach).

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

### 3.4 The validated-promote gate — `rc=0` is necessary but NOT sufficient

Changing the served shadow pin is the load-bearing, blast-radius-carrying step (§2), so it must
be gated on far more than a zero exit code. Before the **atomic write-new-then-swap** pin change
(§3.1), the candidate artifact must pass **all** of the following — else the promote **fails
closed and the old pin is retained**:

1. **Artifact LOAD + SMOKE INFERENCE.** The `model.pt` loads and scores a small fixed probe batch
   end-to-end without error — proving the served bytes are actually **servable**, not merely
   present on disk.
2. **Schema / recipe / config-fingerprint PARITY.** The candidate's feature schema and recipe
   match what the shadow path expects, and its `config_fingerprint` is stamped from the **current
   pinned** `strategy_config.shadow.json` (§3.3) — so the promote cannot itself reintroduce the
   `panel_scorer_config_mismatch` fail-closed. This reconciles the gate with the known re-stamp
   issue: re-stamp handles config drift; this parity check confirms the *fresh* artifact is
   stamped correctly at promote time.
3. **NON-DEGENERATE outputs.** Probe scores are finite (no NaN/Inf), non-constant, and within a
   sane distribution — a model that emits a single value or all-NaN is rejected, not served.
4. **RESOURCE bounds.** Load + inference stay within a memory / latency budget, so a pathological
   artifact cannot OOM or hang the **shared** daily pipeline (§2).
5. **A minimum shadow-quality SANITY FLOOR.** The fresh challenger clears a low, pre-declared
   floor on the WF / holdout evaluation it was selected on — **not** a trading gate, just a floor
   to reject a broken or collapsed model — so the champion–challenger comparison is not corrupted
   by a degenerate promote.

**Plus** the §3.1 freshness conditions (every recipe-required source on its per-source SLA **and**
the effective cutoffs advance — or the artifact is explicitly **labeled non-fresh** and does not
reset the freshness clock). Any failure surfaces to the **model-monitoring owner** with its
failure class; the superseded artifact is retained for rollback either way. This gate is why an
*automatic* shadow promote (§3.1) is safe: automatic execution, but never an unchecked pin swap.

## 4. Immediate operational remediation (execute AFTER this design is discussed — NOT in this PR)

Per the repo's discuss-before-implement rule, this PR does **not** execute any of
the following. It specifies them so they can be run once the design is agreed:

1. **Refresh the upstream panel to point-in-time FIRST (the prerequisite, §3.1).** Refresh the
   recipe's actually-used sources — the transformer panel
   `data/transformer_v4_wl200_clean.parquet` (currently ending 2026-02-10), the rawlabel, and the
   fundamentals feed — to the current point-in-time. Without this, steps 2–3 only re-mint
   2026-02-10 information under a new `trained_date`. This is base-data / model-owned work and is
   the load-bearing step.
2. **Retrain on the refreshed panel, then promote through the validated-promote gate (§3.4).**
   Run `scripts/weekly_retrain_patchtst.sh` to rebuild the shadow WF corpus, then **promote** the
   fresh model to the served shadow pin (re-stamped against the pinned
   `strategy_config.shadow.json`, §3.3) so the served snapshot advances off its 2026-05-22
   bytes — but **only if** every recipe-required source is on-SLA **and** the effective cutoffs
   advanced (§3.1); a non-advancing retrain is promoted only for an explicit recipe-fix reason and
   **labeled non-fresh**. (Refreshing the WF corpus alone — as the 06-08 / 06-16 runs did — does
   **not** unfreeze the served model; the **validated promote** is the load-bearing serving step,
   §1.3 / §3.4.)
3. **(Re)install the scheduled job.** Install the `com.renquant.weekly-retrain-patchtst`
   launchd plist so the weekly cadence resumes and never silently lapses again — as the cadence,
   with freshness still keyed on the served data cutoff (§3.2).
4. **Verify the monitor sees a genuinely fresh served pin.** Confirm the served artifact's
   **binding data cutoff actually advanced** (not merely that a retrain ran) and the freshness
   tier returns to `healthy` on the per-source SLA (§3.2).

These are umbrella-ops actions on the live tree; they are **not** performed by any
agent as part of this design PR.

## 5. Rollout, ownership, provenance

**Staged, monitored, reversible; design-only.** Per-repo implementation follows
after discussion, mirroring #210's phasing.

| Phase | Scope | Risk |
|-------|-------|------|
| 1 (near-term) | Shadow freshness **monitor** (observe-only, §3.2) keyed on the served artifact's **binding DATA cutoff + validated-promote status** (not last-retrain); cadence-lapse alert as a parallel liveness track | low |
| 2 | **(Re)install the weekly scheduled job** (§3.1) as the **cadence** | low (shadow, no capital) |
| 3 | Wire the upstream **point-in-time panel refresh prerequisite** (§3.1) ahead of retrain + the **validated-promote gate** (§3.4, fail-closed unless per-source SLA on-SLA **and** cutoffs advance) — the load-bearing serving path | low–medium |
| 4 | **Automated retrain → VALIDATED served-pin promote** (§3.1 / §3.4), atomic + re-stamped against the pinned config (§3.3); run the §4 manual remediation | low (shadow, no capital) |
| 5 | Confirm the 35d **data-cutoff** breach default in discussion; wire the untrustworthy-comparison annotation into the shadow report (§3.2) | low |

Operational safety (reused from #210): remediation triggers **before** the breach (escalate
fires the §3.1 panel-refresh → retrain → validated-promote pipeline); the pin swap is gated by
the **validated-promote gate (§3.4)** and the §3.1 fail-closed-unless-DATA-advances conditions;
**atomic** write-new-then-swap promote; the superseded artifact is retained for **rollback**;
every promote stamps the run bundle with the selected artifact, its **data-cutoff axes** and
per-source SLA verdicts, the validated-promote gate result, the non-fresh label (if any), and the
superseded artifact id. All changes are config / script — **no broker, risk-cap, or sizing
changes; never bypass branch protection.**

**Ownership** (mirrors #210's split; umbrella scripts schedule/invoke but do not own
model selection):

| Concern | Owner repo |
|---|---|
| **Upstream point-in-time PANEL REFRESH prerequisite** (`transformer_v4_wl200_clean.parquet` + rawlabel + fundamentals, §3.1) | **base-data / model** |
| Shadow retrain **script + launchd schedule** (`weekly_retrain_patchtst.sh`, the plist) | **umbrella ops** (`RenQuant/scripts` + launchd) |
| Shadow model **recipe / WF corpus / promote-to-served mechanics + validated-promote gate** (§3.4) | **backtesting / model** |
| Shadow **freshness policy + tiers + `artifact_path` pin** | **strategy-104 config** (`strategy_config.shadow.json`) |
| Shadow **freshness monitor + run-bundle provenance + cross-repo sequencing** | **renquant-pipeline / renquant-orchestrator** |

## 6. Open questions (for Codex / operator)

1. **Breach ceiling.** Is **35d** the right shadow breach tier on the **fast-axis DATA cutoff**
   (looser than #210's 28d data-cutoff ceiling because shadow is non-trading), or should the
   shadow monitor reuse #210's 28d uniformly given both are observe-only? (Proposed: 35d,
   non-trading rationale in §3.2.)
2. **Promote autonomy.** Should the retrain → served-pin promote run **without an operator gate**
   for the shadow path (proposed, since no capital is at risk) — noting it still passes the §3.4
   validated-promote gate and the §3.1 fail-closed-unless-DATA-advances conditions — or should it
   require the same operator confirmation #210 reserves for the prod promote?
3. **Data-vintage prerequisite (direction RESOLVED per Codex; ownership/sequencing open).** r1
   proposed naming the panel refresh as an out-of-scope dependency; per Codex, this RFC now makes
   the upstream **point-in-time panel refresh a PREREQUISITE** of the shadow retrain/promote
   (§3.1) — a retrain on the 2026-02-10 panel is not a freshness fix. Open only: **which repo owns
   scheduling that panel refresh** so it reliably precedes each shadow retrain (base-data/model vs
   umbrella-ops sequencing), and whether the shadow cadence should **block / no-op** (rather than
   run) when the panel is off-SLA. (Proposed: a shadow retrain on a stale panel is a no-op or is
   **labeled non-fresh** (§3.1), never minting a stale-data artifact under a new `trained_date`.)
4. **Cadence match.** Weekly is proposed to match the other scorers; is a different shadow cadence
   (e.g. bi-weekly) acceptable given it is non-trading and the **panel-refresh prerequisite**
   (§3.1), not the retrain interval, is the binding freshness constraint?
