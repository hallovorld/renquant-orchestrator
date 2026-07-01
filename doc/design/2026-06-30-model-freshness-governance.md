# Design: Model Freshness Governance — 28-day ceiling, deferred best-of-recent fallback, reliable retrain cadence, and WF-promote repair

STATUS: design for review (no implementation in this PR — describe → discuss → PR to Codex → then implement per-repo).
REVISION: **R2 (round-2)** — reworked to address Codex's round-1 `CHANGES_REQUESTED` (head `183764a5`). Round-1 rested on a
**factually stale production-state premise** and let the fallback auto-promote gate-rejected models; R2 corrects the premise,
bounds the fallback to infrastructure failures behind an OOS floor, and defers it behind a point-in-time shadow experiment.

This is a discussion document. It proposes a governance contract and a phased
rollout; it does **not** change any code, config, broker, risk-cap, or sizing
behaviour. Cross-repo implementation happens in follow-up per-repo PRs **after**
this design is agreed.

## Response to Codex round-2 review (per-point map)

| Codex point | Resolution in R2 | Section |
|---|---|---|
| 1. Production-model premise is factually stale (XGB is the live primary, not PatchTST) | Premise rewritten; PatchTST is **shadow**, the XGB/GBDT panel is the **operator-directed active primary** frozen at 05-18; added a **production-state re-audit** action; WF-gate section reframed to **repair (re-validate the primary)**, not retire | §0, §1B, §4 WF-repair |
| 2. `trained_date` is not data-freshness | Freshness now keys on the **DATA cutoff** and fingerprints, not the training run time; stale/failed upstream feeds **block** a fresh stamp | §2 |
| 3. Auto-promoting a strict-gate failure has no quality floor | Fallback splits **mechanical/infra** vs **quality** failures; may bypass **only enumerated infra failures** and **only after independently recomputing an OOS economic floor**; substance/leakage/placebo/recipe-mismatch/unknown stay **fail-closed** | §4 Pillar 3 |
| 4. "Best of 10 days" is under-specified | Pre-registration schema per model family, **or DEFERRED**; per-ticker tournament and the single panel scorer are **different populations** → separate selection + separate freshness decisions | §4 Pillar 3, §5 |
| 5. 28d/10d and "stale is safer than a rejected fresh model" are unsupported | Gated behind a **point-in-time shadow replay** + a **pre-registered non-inferiority gate**; numbers become tunable outputs of the experiment, not asserted inputs | §5 |
| 6. Rollout & ownership incomplete | Remediation triggers **before** the ceiling; atomic promotion, concurrent-retrain, partial-completion, per-ticker coverage floor, rollback trigger, run-bundle provenance; **ownership split** (backtesting/model, strategy, pipeline, orchestrator); umbrella scripts do **not** own model selection | §6 |

**Bottom line (reconciled with Codex).** The near-term shippable work narrows to **Phase 1: an observable freshness monitor +
the measured timeout/cadence repair** — uncontroversial, ships first. The **best-of-10d fallback stays DISABLED / deferred**
until (a) the production-state audit, (b) the point-in-time shadow experiment, (c) a pre-registered selection policy, and (d)
a non-inferiority gate all land. The operator's core intent — *a fresh model beats a stale one when the retrain failed for a
mechanical/infra reason* — is **preserved but bounded** to infra-only failures + an OOS economic floor + shadow validation
(see §7 for the explicit narrowing and why).

## 0. Corrected production-state premise (R1 was wrong here)

Round-1 asserted that PatchTST has been the production primary since 2026-06-05 and that the XGB/GBDT panel is a vestigial,
sell-only fallback. **That is stale.** The verified current state of the **pinned** subrepo config
`renquant-strategy-104/configs/strategy_config.json` is:

- `ranking.panel_scoring.kind = "xgb"` — the **XGB/GBDT `panel-ltr.alpha158_fund`** panel scorer (`trained_date = 2026-05-18`)
  is the **current live PRIMARY**.
- This was an **operator-directed** switch on **2026-06-23** (config note `_2026_06_23_xgb_promotion`: *"Operator directive:
  XGB trades ALL regimes to restore live trading"*), which **reversed** the 2026-06-05 PatchTST promotion. The previous PatchTST
  primary was moved to `strategy_config.shadow.json` (`_2026_06_23_role`).
- **PatchTST is now SHADOW** — scored and logged (MLflow) but **not** the live decision. Confirmed by a real run:
  `LoadScorerTask: loaded xgb` (primary) + `ApplyShadowScoringTask: shadow hf_patchtst`.

Two premise corrections that change the whole rollout:

1. **The 06-23 XGB promotion was an operator-directed CONFIG-KIND switch, NOT a gate pass.** The `promotion_status = "gated_buys"`
   field stamped on the artifact is a **stale / superseded** attribute; it does not mean the live primary passed the WF gate.
2. **The weekly WF-promote failing to re-validate the XGB/GBDT matters BECAUSE that model is the ACTIVE primary** — it is not
   vestigial. The live primary panel is **frozen at 2026-05-18** and reached production **only via the config switch**, with no
   passing WF validation. So the correct goal for the weekly gate is to **REPAIR it so it can re-validate the primary**, not to
   retire it (R1's "retire the vestigial GBDT promote" recommendation is withdrawn).

**Action P0 — production-state re-audit (blocks §4 Pillar 3).** Before any selection/fallback logic is designed, re-derive the
production state directly from the pinned umbrella + subrepo commits and **distinguish**: (a) the active live scorer
(`panel_scoring.kind` + artifact `trained_date` + data cutoff), (b) the shadow scorer, (c) the rollback artifact retained for
reversal, and (d) the weekly job's actual candidate/manifest. R1 conflated (a) and (d); R2 must not.

## 1. Problem — "no buys" has two INDEPENDENT freshness root causes

Both root causes are diagnosed. They are orthogonal: they live in different
repos, gate different decisions, and either one alone can zero the buy list.
They are **different populations** and — per Codex point 4 — get **separate**
selection rules and **separate** freshness decisions.

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
failure (an **infrastructure** failure by the taxonomy in §4), not a quality veto.

Consequence: cadence has been effectively **frozen since late April** (RL/RF
artifact mtimes ~2026-04-22; `trained_date` stuck at 2026-04-28/30). On
2026-06-30 the age is **61d > 60d**, so every non-held ticker is dropped from the
universe → Phase 2b reports **"0 candidates from 0 tickers" → no trade**
(observed in `logs/daily_104/2026-06-30.log`).

### B. Panel scoring model — the ACTIVE PRIMARY panel is frozen and unvalidated

The live primary panel scorer is the XGB/GBDT `panel-ltr.alpha158_fund`
(`panel_scoring.kind = "xgb"`, `trained_date = 2026-05-18`), placed into
production by the 06-23 operator directive (§0), **not** by a passing gate. The
weekly WF-promote (`scripts/weekly_wf_promote.sh`, gating `panel-ltr.alpha158_fund`
via `scripts/run_wf_gate.py`) that would **re-validate** this primary chronically
**fails**. Because the model it fails to re-validate is the **live primary**, the
consequence is that the production panel is **frozen at 05-18 with no standing WF
evidence** — the opposite of R1's "vestigial" reading.

The weekly promote fails on a **rotating** tangle of causes. Each is tagged
**infra** (mechanical) or **quality** (substance) per the §4 taxonomy — this
tagging is what the fallback keys on:

| # | Failure | Class | Root cause | Status |
|---|---------|-------|------------|--------|
| (recipe-fp) | Recipe-fingerprint mismatch (candidate `f4596e33` ≠ manifest `ccc412d0`) | **infra** | Fingerprint hashed human-readable `feature_source_contract` prose that a refactor edited | **FIXED 05-27→06-04** (hash contract KEYS only; move `epochs`/`early_stopping`/`device` to execution-only params). Candidate + manifest now both hash `cfdd6cb8` — they MATCH. |
| Fix-1 | **sim per-bar scorer artifact-not-found (rc=1)** — most frequent June failure | **infra** | Derived WF-eval config resolves per-bar scorers from `artifacts/sim/artifacts/walkforward_v2_20260602/<date>/panel-ltr.json` (does **not** exist), while the validated manifest is `artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json` → `walkforward_gbdt_prod_recipe_v2/<date>/panel-ltr.json` (**does** exist) → `FileNotFoundError` (`backtesting/renquant_104/adapters/sim.py:851` → `panel_scorer.py:201`) | Open — path inconsistency |
| Fix-2 | **WF config scorer-kind parity** | **infra** | The WF-derived eval config must carry the **active primary's** kind (`xgb`) and point at the matching XGB `panel-ltr.json`; a kind↔artifact mismatch trips the parity guard. R1 described this as `hf_patchtst`-kind vs GBDT-artifact — that direction is **stale** now that the live kind is `xgb`; the **current** mismatch direction must be re-confirmed from a fresh gate run under the pinned `xgb` config (part of Action P0). | Open — re-confirm |
| Fix-3 | **§5.2 placebo_ic floor is structurally unsatisfiable** | **infra (structural)** | Gate requires `placebo_ic < 0.5 × \|aligned_real_ic\|`, but the 60-day label carries a ~+0.04 embargo-leakage floor; even at a 120d (2×horizon) shift the placebo IC (+0.035→+0.053) exceeds the threshold (+0.030→+0.043). Independent of model quality. | Open — structural |
| Fix-4 | **Substance — XGB/GBDT did not beat SPY** | **quality** | Mean 3-cut Sharpe ~+0.356, **0 / 3** cuts beat SPY, ΔSharpe **−0.72**; failed trade-gate monotonicity in BULL_CALM | **Not a bug** — the gate correctly rejecting a weak model |

The key reading (corrected): **Fixes 1–3 are mechanical/infra** (config-path +
parity bugs plus a structural placebo floor) and block the gate from **rendering a
verdict at all** on the live primary. **Fix-4 is the gate working correctly** — a
substance verdict of *no demonstrated edge*. Repairing 1–3 lets the gate finally
speak on the 05-18 primary; if it then still returns Fix-4, that is a **real
signal that the current live primary has no standing edge**, which must escalate to
the operator (the model is live only by directive), **not** be silently papered
over by promoting a different substance-failing model.

## 2. What "freshness" must mean — govern the DATA cutoff, not just `trained_date`

Codex point 2: a retrain run **today** against an old OHLCV/fundamentals cutoff
would stamp `age = 0` while being just as blind as the model it replaces. R1's
monitor keyed on `trained_date` (the run time) and is therefore spoofable.

**R2 freshness key.** A model is "fresh" only if the **relevant DATA cutoff** is
recent. The monitor (and the hard ceiling) key on the **max** of the model's
staleness across, at minimum:

- `trained_at` (run time) — retained, but **not** sufficient alone;
- **maximum feature `event_time`** actually present in the training panel;
- **`available_at`** (point-in-time availability, not event time) of the newest
  feature — guards against backfill that looks fresh by `event_time` but was not
  knowable at train time;
- **training-window end** (the label/feature cutoff the recipe actually used);
- **source data fingerprints** (OHLCV + fundamentals + estimate feeds);
- **code / config / recipe fingerprints** (the recipe + manifest hashes, e.g.
  `cfdd6cb8`);
- **artifact creation time**.

**Stale/failed upstream feeds BLOCK a "fresh" stamp.** If any required upstream
feed (fundamentals, estimates, prices) is itself stale or its last harvest
failed, the retrain **cannot** be stamped fresh regardless of `trained_at` — the
monitor reports the **binding** (oldest) axis. This closes the "retrain on stale
data resets the clock" hole.

## 3. Goal

No production model — per-ticker tournament **or** panel — serves the live
decision while its **binding data axis** (§2) is older than **28 calendar days**
(a candidate ceiling to be **validated by the §5 experiment**, not asserted). If
the normal retrain → gate → promote path cannot deliver a fresh, validated model,
prefer a **fresh model that failed for an enumerated infrastructure reason** over
an aging one — **bounded** by an OOS economic floor and fail-closed for substance
failures (§4 Pillar 3), and **only after** the §5 shadow experiment authorises it.

Plus three enabling objectives:

- make staleness **observable** (today it is silent until the universe zeroes);
- make retrain **reliable** (the tournament timeout; a WF gate that can render a
  verdict on the live primary);
- **repair** the weekly WF gate so the strict path can actually re-validate the
  active primary — minimising how often any fallback must fire.

## 4. Design — three pillars + WF-gate repair

### Pillar 1 — freshness monitor + 28-day ceiling (monitor ships now; ceiling gated by §5)

A daily monitor computes `age = today − (binding data axis, §2)` for (a) the panel
prod artifact and (b) the per-ticker tournament artifacts. Per Codex point 4 these
are **separate populations**: the panel is a **single** scorer (one freshness
decision); the tournament is **142 per-ticker** artifacts (a **coverage**
decision — see §6 per-ticker coverage floor — **not** one shared min/median/max
rule).

| Tier | Age | Action |
|------|-----|--------|
| healthy | ≤ 14d | none |
| warn | 14–21d | ntfy info; retrain due |
| escalate | 21–24d | ntfy warn; **trigger on-demand retrain now** (before the ceiling — Codex point 6) |
| breach | > 28d | page operator; the live model is knowingly stale until a validated (or §5-authorised fallback) replacement lands |

The **monitor is observe-only and ships in Phase 1**. Lowering
`model_staleness_days` **60 → 28** is deferred to **Final**, and only after the §5
experiment shows the tighter ceiling is net-non-inferior — tightening the gate
before a validated remediation path exists makes gating strictly worse.

### Pillar 2 — reliable, monitored retrain cadence

- **Per-ticker tournament:** make the timeout fix durable —
  `parallel_ticker_timeout_seconds` 600 → ≥ 2400, or make the phase timeout scale
  with universe size; consider raising `parallel_workers` above auto. Restore a
  scheduled cadence. This is a **measured infrastructure repair** (67/142 → full
  completion) and is part of the Phase-1 shippable set.
- **Panel:** repair the weekly WF gate (WF-repair below) so it can render a verdict
  on the **active primary**, and validate the shadow PatchTST path in parallel.
- **Cadence health is itself monitored:** alert if no successful, **data-fresh**
  (§2) retrain of *either* model in 14d.

### Pillar 3 — best-of-recent fallback (DEFERRED; infra-only + OOS floor + fail-closed)

This is the operator's core directive, and R2 keeps it as the north star — but it
is **DISABLED / deferred** until Action P0 (§0), the §5 shadow experiment, a
pre-registered selection policy, and a non-inferiority gate all land. What follows
is the **contract to pre-register**, not something this PR turns on.

**4.3.1 Failure taxonomy (the gate the fallback keys on).** Every strict-gate
rejection is classified. The fallback may act on the first class **only**:

- **MECHANICAL / INFRASTRUCTURE (enumerated, closed list):** phase/timeout
  (`ParallelTimeoutError`); config/artifact **path-not-found** (Fix-1);
  scorer-**kind parity** mismatch (Fix-2, once its current direction is
  reconfirmed); the **structural placebo floor** (Fix-3) *only while it remains an
  embargo artifact, not a real leakage signal*. These prove the software could not
  produce a verdict — they say nothing about edge.
- **QUALITY / SUBSTANCE (fail-closed, always):** sub-SPY / negative ΔSharpe
  (Fix-4); leakage or placebo **contamination** (a placebo signal that is real,
  not the embargo floor); **recipe-mismatch** (the candidate is not the model the
  recipe claims); and any **unknown / unclassified** failure. These **never**
  qualify for auto-promotion.

**4.3.2 Loadability is not edge.** Basic-integrity checks (loads; scores a smoke
panel without NaN; not degenerate / all-one-sign; recipe loads) prove **software
integrity, not predictive value**. The document's own evidence is the proof: the
mechanically-clean 06-11→14 XGB/GBDT ran at **ΔSharpe −0.72, 0/3 cuts beat SPY** —
a substance failure that passes every integrity check. Integrity is **necessary
but not sufficient**.

**4.3.3 Independent OOS economic floor (required before any bypass).** Even for an
enumerated infra failure, the fallback must **independently recompute** a minimum
out-of-sample economic floor for the candidate (e.g. OOS Sharpe ≥ SPY on a
pre-registered comparable window, non-negative net-of-cost return, no placebo
contamination) on a **point-in-time** registry. Only a candidate that clears
**both** the infra-failure filter **and** the recomputed OOS floor may promote.
Anything that fails the floor is treated as a **quality** failure → fail-closed.

**Why this actually serves the operator's real problem.** Today's rejects are
**exactly the mechanical/infra kind** — the 600s timeout (Pillar 2) and the sim
artifact-path bug (Fix-1). A correctly-scoped fallback promotes a fresh model past
**those**, which is the operator's genuine pain — but it will **never** promote
past a genuine *no-edge* verdict (Fix-4). The narrow version loses nothing the
operator actually wanted (see §7).

**4.3.4 Best-of-10-days — pre-registration schema (or DEFERRED).** Selecting "the
best model in the last N days" requires a pre-registered protocol, **per model
family** (they are different populations — Codex point 4):

| Item | Panel scorer (single population) | Per-ticker tournament (142 populations) |
|---|---|---|
| Candidate eligibility | data-fresh (§2) staging artifacts, correct recipe/kind | per-ticker fresh artifacts that trained successfully |
| Comparable OOS window / cutoffs | one fixed WF window, same embargo, same label horizon | per-ticker fixed OOS window; **no cross-ticker pooling** |
| Selection score | pre-registered (OOS Sharpe or genuine_ic, decided **before** looking) | per-ticker OOS score; the **admission** decision is coverage, not ranking |
| Uncertainty | report CI / SE on the score; require separation, not point-estimate ties | per-ticker CI |
| Multiple-candidate selection-bias control | deflate for #candidates compared (e.g. Šidák / DSR-style haircut) | per-ticker, low candidate count |
| Minimum sample / trades | pre-registered floor on #trades and #independent 60d outcomes | per-ticker minimum |
| Turnover / cost assumptions | net-of-cost, same cost model as live | same |
| Regime coverage | require ≥ N regimes represented in the OOS window | n/a (admission) |
| Tie-breaks | freshest data cutoff, then simplest recipe | freshest |
| Rollback criteria | see §6 | see §6 |

**The two populations do NOT share one rule.** The panel is a **single selection**
(pick one scorer). The tournament is a **coverage** problem (how many of 142 are
fresh enough to admit) — there is **no** shared min/median/max freshness statistic
across the two, and the tournament's "fallback" is a per-ticker coverage floor
(§6), not a tournament-wide best-of-N pick.

If the §5 experiment does not authorise auto-promotion within this PR's horizon,
Pillar 3 is explicitly marked **DEFERRED** and only the pre-registration above
ships as a written contract.

### WF-gate REPAIR (so the strict path can re-validate the PRIMARY)

Reframed from R1's "retire": the goal is to make the weekly gate able to render a
verdict on the **active primary** (the 05-18 XGB/GBDT), because that model is live
with no standing WF evidence.

- **Fix-1** — unify the sim per-bar artifact path to
  `walkforward_gbdt_prod_recipe_v2` so the eval can find the calibrated per-bar
  scorers.
- **Fix-2** — derive the WF-eval config with the **active primary's** scorer kind
  (`xgb`) pointing at the matching XGB `panel-ltr.json`; re-confirm the current
  parity-failure direction from a fresh run (Action P0). **Do not retire** the
  gate — it must re-validate the primary.
- **Fix-3** — replace the absolute placebo **ceiling** with a placebo-clean
  **difference** test (`real_ic − placebo_ic > margin`), or widen the embargo so
  the placebo shift clears the 60d label window — so an embargo artifact stops
  reading as a leakage failure.
- **Fix-4** is **not** a code fix — it is the gate correctly rejecting a sub-SPY
  model. If, after Fixes 1–3, the live primary still returns Fix-4, **escalate to
  the operator** (the primary is live only by directive and has no demonstrated
  edge). The fallback's integrity floor + OOS floor is **not** a way to route
  around a real no-edge verdict.

## 5. Point-in-time shadow replay experiment (gates the ceiling AND the fallback)

Codex point 5: the 28d / 10d numbers and the causal claim *"a stale model is safer
than a rejected fresh model"* are **unsupported**. Before any auto-promotion is
enabled, run a historical **shadow replay** with **point-in-time registries** (no
lookahead into artifacts/data that were not knowable at the simulated date):

- **Arms compared** at each simulated ceiling-breach date: (i) **current-prod
  hold** (keep aging the live model); (ii) **newest eligible** (promote the most
  recent data-fresh candidate); (iii) **proposed best-recent fallback** (the §4.3.4
  pre-registered pick, infra-only + OOS floor).
- **Metrics:** net OOS return / Sharpe / drawdown / turnover; **admission
  coverage** (how often each arm even has a candidate); **failure-mode strata**
  (results split by infra-vs-substance reject reason).
- **Pre-registered gate:** a **non-inferiority / safety** threshold (fallback must
  be **non-inferior** to current-prod-hold net of cost and drawdown) plus a
  **shadow duration** — all fixed **before** any auto-promotion enables.
- **Sample-size caveat:** the 60-day label means one week of shadow covers very few
  **independent** outcomes; the shadow must run long enough to accumulate enough
  independent 60d-label windows to distinguish the arms — likely well beyond one
  week. The `28d` / `10d` numbers are **outputs** of this experiment (chosen to
  satisfy the gate), not asserted inputs.

Only if arm (iii) clears the pre-registered non-inferiority gate does Pillar 3 move
from DEFERRED to shadow-first, then flag-enabled.

## 6. Rollout, ownership, and provenance

### Rollout (staged, monitored, reversible)

| Phase | Scope | Ships when | Risk |
|-------|-------|-----------|------|
| 0 (DONE) | Emergency per-ticker tournament retrain via a side config (`strategy_config.tournament_retrain.json`, timeout 3600) to clear today's 61d breach — already running **outside this PR** | done | operational |
| **1 (near-term shippable)** | Freshness **monitor** (observe-only, §2 data-axis keyed) + the **durable timeout fix** + restored tournament cadence + Action P0 production-state re-audit | first | low |
| 2 | **WF-gate repair** (Fix-1/2/3) so the gate re-validates the active primary; validate the shadow PatchTST path | after P0 | medium |
| 3 | **Point-in-time shadow experiment** (§5): current-prod-hold vs newest vs best-recent; pre-registered non-inferiority gate | after Phase 2 | analysis |
| 4 | Best-of-recent fallback **shadow-first** (log-only), then flag-enabled — **only if** Phase 3 clears the gate | after Phase 3 clears | medium |
| Final | Flip `model_staleness_days` 60 → 28 — only after Phases 1–4 and the §5 experiment authorise the tighter ceiling | last | low |

### Operational safety (applies to any promotion — fallback or normal)

- **Remediation triggers BEFORE the ceiling** — the `escalate` tier (21–24d) fires
  an on-demand retrain; the fallback is never the *first* response to aging.
- **Atomic promotion** — write-new-then-swap; the live decision never reads a
  half-written artifact; a promotion either fully lands or is a no-op.
- **Concurrent-retrain behaviour** — a single-writer lock; if a scheduled retrain
  and an on-demand retrain overlap, the later completion wins by data cutoff, not
  by wall-clock, and never interleaves partial writes.
- **Partial 142-ticker completion** — a tournament run that finishes only K/142 is
  **not** a whole-job failure: keep the fresh K, retain the prior artifacts for the
  rest, and admit on the **per-ticker coverage floor** below.
- **Per-ticker fallback / coverage minimum** — admission requires ≥ a
  pre-registered coverage floor of fresh tickers (e.g. ≥ X% of the watchlist fresh
  within the ceiling); below the floor, page the operator rather than silently
  trading a decimated universe.
- **Rollback trigger** — any fallback promote is reversible (retain the superseded
  artifact); a pre-registered rollback fires on realized-drawdown or
  coverage-collapse breach and restores the prior artifact atomically.
- **Run-bundle provenance** — every promotion (normal or fallback) stamps the run
  bundle with the selected artifact, its data-cutoff axes (§2), the failure class
  that authorised it (if fallback), the OOS-floor recompute, and the superseded
  artifact id — so any decision is auditable after the fact.
- ALL changes are config / script — **no broker, risk-cap, or sizing changes**;
  never bypass branch protection.

### Ownership (Codex point 6 — umbrella scripts do NOT own model selection)

| Concern | Owner repo | Rationale |
|---|---|---|
| WF-gate semantics (placebo test, parity, artifact-path resolution, the pass/fail verdict) | **backtesting / model** | the gate's correctness is a modelling contract |
| Freshness policy + thresholds + `model_staleness_days` + `panel_scoring.kind` | **strategy-104 config** | policy/config is strategy's single source of truth |
| Admission enforcement (staleness drop, coverage floor) | **renquant-pipeline** (`job_universe`) | pipeline enforces admission at run time |
| Coordination, monitor, run-bundle provenance, cross-repo sequencing | **renquant-orchestrator** | orchestration stitches the repos and persists the bundle |

Umbrella `RenQuant/scripts` may **schedule and invoke** but must **not** become the
owner of model-selection logic — selection lives in the model/strategy/pipeline
contracts above.

## 7. Explicit narrowing of the operator's original directive (and why)

The operator's original ask was **"best-of-10-days, even if it fails the gate."**
R2 **narrows** that to **"infra-failures only; substance / leakage / placebo /
recipe-mismatch / unknown stay fail-closed, and even infra-failures must clear an
independently recomputed OOS economic floor."** Why:

1. **Safety** — auto-promoting a model the gate rejected on **substance** (Fix-4:
   0/3 beat SPY, ΔSharpe −0.72) trades real capital on a model with **no
   demonstrated edge**; integrity checks cannot catch that.
2. **It targets the real problem** — the operator's actual pain is fresh models
   blocked by **mechanical** rejects (the timeout; the artifact-path bug). The
   narrow fallback promotes past **exactly those** and loses nothing the operator
   wanted.
3. **The north star is preserved** — the **28d ceiling + best-of-recent** remains
   the goal; it is staged behind the audit + shadow experiment + non-inferiority
   gate so it ships **safely**, not abandoned.

## 8. Open questions for Codex / operator

1. **OOS floor definition** — exact economic floor for §4.3.3 (SPY-relative Sharpe?
   net-of-cost return? both?) and the comparable-window spec.
2. **Ceiling numerics** — confirm 28d/10d are the §5-experiment outputs, not
   priors; what non-inferiority margin and shadow duration?
3. **Per-ticker coverage floor** — what fraction of the 142 watchlist must be fresh
   to admit vs page?
4. **Active-primary escalation** — if the repaired gate returns Fix-4 on the live
   05-18 XGB primary, what is the operator's intended action (retrain-and-wait,
   revert to PatchTST-primary, or accept-with-note)?
5. **Panel admission on staleness** — should panel staleness also gate admission
   (today only the per-ticker tournament gates the universe)?
