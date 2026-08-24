# rq105 Stage-3: intraday LIVE entries — the pinned 104 model on fresh data

STATUS: design for review. No implementation in this PR. Operator-directed
2026-08-23 ("105 = live trade; 尽快"), with the staged-rollout mandate:
design → codex approval → implementation PRs → deploy.

## 1. What this is, in one sentence

Give the book **intraday BUY capability** by re-scoring the **same pinned 104
model** on an **intraday feature snapshot**, and executing through the **same
funnel gates** — no new signal, no new model, no gate bypass.

Corrected framing (the operator's phrase "104 只能 live sell" refers to the
intraday lane): `daily_104` already places live buys **once** at 13:55 **PT**
(= 16:55 ET, i.e. 55 min AFTER the close — corrected 2026-08-24, §4b(i));
`intraday104` is sell-only. Stage-3 adds intraday buys. This matches RFC #208
(105 = intraday execution of 104's decisions).

## 2. Why — measured, not aspirational

- **The 13:55 decision runs on a partial final bar.** orch#1021: the same
  candidate set re-run post-close flipped APH from `nonpositive_expected_return`
  (13:55) to BUY (post-close, panel 2.434→2.463); prod bought APH the next day.
  One data point, but it is exactly the class of error intraday freshness
  addresses — and S3-b's paired logging turns that n=1 into a measured series.
- The decision lane already exists and skips daily:
  `SKIP not-wired: no producer exists for feature_snapshot_<date>.json
  (Stage-3, #221)` — every session since 2026-08-12 [VERIFIED — one-line
  shadow_serving logs].

## 3. What exists vs what is missing [all VERIFIED against the running tree]

| piece | state |
|---|---|
| `realtime_data_plane.py` | EXISTS — intraday snapshot with causality (`source_ts <= as_of`), same-session, staleness censoring; consumes `intraday_ticks.jsonl` |
| `shadow_realtime_serving.py` | EXISTS — observe-only collector; DI scorer via `renquant_common.load_scorer` (read-only pinned artifact); requires `FeatureSnapshot.from_mapping` (`feature_cutoff`, `builder_version`, non-empty `features`, content digest) |
| `quote_logger` | RUNNING — ~51k rows/day |
| `batch_scores_<date>.json` + meta | RUNNING — 06:15 export with `score_content_sha256`, scorer identity, coverage |
| **T-1 frozen FEATURE panel** | **MISSING** — nothing persists the served feature vectors (G-K gap; also why score attribution is impossible, task #17). Verified today: no feature file under `data/` |
| snapshot producer | MISSING — the `#221` blocker |
| intraday BUY path | MISSING — `intraday104` is sell-only |

## 4. Architecture — four pieces, each its own implementation PR

**S3-P1 — persist the daily feature panel.** The daily full run writes
`data/rq105/feature_panel_<date>.json` + `.meta.json`: per-ticker served
feature vector frozen at T-1 EOD, with `feature_cutoff`, `builder_version`,
content sha256. Mirrors the existing `batch_scores` export shape. Side
benefits: closes part of G-K and unblocks post-hoc score attribution (#17).

**S3-P2 — snapshot producer.** New module + `ops/renquant105/
build_feature_snapshot.sh`: feature panel (T-1 frozen) + intraday overlay via
`realtime_data_plane` (causality + staleness censoring as-is) →
`feature_snapshot_<date>.json` conforming to `FeatureSnapshot.from_mapping`.
Deterministic given (panel, ticks, as_of); content-digested.

**S3-P3 — wire the existing shadow lane.** `run_shadow_serving.sh` stops
skipping; the collector starts pairing intraday re-scores with frozen batch
scores daily. Zero new decision surface — this is the lane doing what it was
built for.

**S3-P4 — intraday entry loop (the only new decision surface).** A new
orchestrator entrypoint that: re-scores via the pinned scorer; applies the
SAME funnel (direction gates, wash-sale, sector caps, `max_concurrent_positions`
— shared with the daily run, no separate budget); sizes via the production
`compute_position_size`; emits limit BUY orders through `live.runner`'s
existing broker path.

**v1 admission rule (domain-shift bound):** intraday entries are allowed only
for names admitted by BOTH the **T-1** batch decision (the artifact named in
§4b(ii)) AND the intraday re-score (intersection). NOT "the day's" batch
decision: that run fires after the close and does not exist during the session
it would gate (§4b(i)). The model was trained on EOD bars; scoring intraday
mids is a distribution shift. The intersection bounds it: intraday data can
only *confirm or veto* a batch admission, never admit a name the batch
declined. Relaxing this is a separate, evidence-gated decision.

### 4a. Repo ownership — which repo builds each piece `[REVISED 2026-08-24, codex review]`

The orchestrator's hard boundaries forbid implementing pipeline internals or
broker adapters here, so "four implementation PRs" is not enough: each needs a
named home. Verified against the running tree, not assumed.

| piece | target repo / module | why there |
|---|---|---|
| **S3-P1** persist the feature panel | **renquant-pipeline** — `src/renquant_pipeline/kernel/panel_pipeline/` (`feature_matrix.py` / `alpha158_features.py` build the served vectors) | the feature vectors are produced there. The orchestrator has **no** feature-building code today [VERIFIED — no `build_feature*` / `feature_vector` definition anywhere in `renquant-orchestrator/src`], and adding one would be implementing pipeline internals in this repo. The orchestrator CONSUMES the artifact; it does not produce it. |
| **S3-P2** snapshot producer | **renquant-orchestrator** — new module + `ops/renquant105/build_feature_snapshot.sh` | `realtime_data_plane.py` and `FeatureSnapshot` already live here [VERIFIED]. Assembling a T-1 panel with an intraday overlay is data-plane orchestration, not feature construction. |
| **S3-P3** wire the shadow lane | **renquant-orchestrator** — `run_shadow_serving.sh`, `shadow_realtime_serving.py` | existing orchestration surface; no new logic. |
| **S3-P4** intraday entry loop | **renquant-orchestrator** entrypoint | orchestration. See the two reuse contracts below — both are constraints, not preferences. |

**S3-P4's two reuse contracts.**

1. **Pipeline primitive.** The loop is composed from `renquant_common.pipeline`
   — `Task` / `Job` / `Pipeline` [VERIFIED — the primitives exported there] —
   the same way `daily.py` composes the batch run. It does not invent a second
   orchestration idiom for the same funnel.
2. **Execution interface.** Orders leave ONLY through the existing execution
   port: `renquant_execution.alpaca_broker_port.AlpacaBrokerPort`, reached via
   `live.runner`'s current broker path. **No broker-adapter code is written in
   this repo** — if the intraday loop needs a capability the port does not
   expose, that is a change to `renquant-execution` under its own review, not
   a local workaround.

### 4b. The batch side of `batch ∩ intraday` — identity, and a timing correction

`[REVISED 2026-08-24, codex review]` The intersection was specified against
"the day's 13:55 batch decision", which is not auditable and, as written, not
implementable. Two separate problems:

**(i) The timing claim is wrong, and it inverts the rule.** §2 says
`daily_104` places live buys "once at 13:55 **ET**". It is **13:55 local (PT)**
[VERIFIED — `~/Library/LaunchAgents/com.renquant.daily104.plist`,
`StartCalendarInterval Hour=13 Minute=55`, **no `TZ` in
`EnvironmentVariables`**, so the system zone applies; log timestamps agree,
e.g. 2026-08-21 13:55→14:25]. 13:55 PT is **16:55 ET — 55 minutes AFTER the
16:00 ET close**, not two hours before it.

Consequence: during session T (06:30–13:00 PT; the intraday lane's own logs end
13:00–13:01), **today's batch decision does not exist yet**. An intersection
against "the day's" batch decision can never be evaluated inside the window it
is meant to gate. The batch side is necessarily **T-1's** decision.

**(ii) The artifact must be named, and one already exists.** The batch side is
the completed prior-session live run in `runs.alpaca.db`:

- **identity**: the `pipeline_runs` row — `run_id`, `run_date`, `run_bundle_json` —
  selected with `run_type='live'`, non-empty `strategy`, and bound
  config / artifact / watchlist fingerprints, joined to its
  `candidate_scores` rows with `role='candidate'`;
- **loader**: `renquant_orchestrator.intraday_session_inputs` already implements
  exactly this selection and enforces the leak guard twice — it queries ONLY
  `previous_session(calendar, session_date)` and re-asserts that the selected
  run strictly predates the session, raising `SignalLeakError` otherwise
  [VERIFIED — read at head]. S3-P4 **reuses that loader**; it does not
  re-implement the selection.

**Rejection contract (fail closed).** The intraday loop refuses to emit any
order when: the resolved run's `run_date` is not the immediately preceding
exchange session; any bound fingerprint (config / artifact / watchlist) differs
from the one the intraday scorer is running under; the run bundle is absent or
its digest does not match; or coverage falls below the loader's existing
`min_rows` / `min_coverage` floors. Every refusal is recorded with the
`run_id` it refused, so "no entries today" is always attributable to a named
artifact rather than to silence.

**What the intersection therefore means, stated exactly:** a name may be
entered intraday on session T only if it was admitted by the T-1 batch run
identified above AND by the intraday re-score. This preserves the
domain-shift bound (intraday data can confirm or veto, never admit a name the
batch declined) and is auditable, because both sides now name an artifact.

## 5. Guardrails (S3-P4 ships with all of these ON)

| guardrail | v1 value |
|---|---|
| max intraday entries / day | 2 |
| max intraday notional / day | $1,500 |
| no-entry windows | first 15 min, last 15 min |
| order type | limit only, at snapshot mid |
| kill switch | `RENQUANT_RQ105_HALT=1` checked every cycle |
| account guard | same expected-account check as daily_104 |
| position cap | SHARED with daily (no bypass of `max_concurrent_positions`) |
| stale snapshot | censored quote ⇒ no entry for that name (fail closed) |

## 6. Rollout ladder — each step gated, the live flip is an operator ask

| step | content | pass criteria |
|---|---|---|
| S3-a | P1+P2+P3 deployed; shadow lane live-data | not-wired line gone; snapshot digest stable across re-runs; coverage ≥ 80% of watchlist |
| S3-b | ≥ 10 sessions paired shadow | zero causality violations; divergence vs batch RECORDED daily (not judged); no crash/skip days |
| S3-c | **LIVE with v1 guardrails** | **explicit operator authorization — hard gate, ask-first** |
| S3-d | relax guardrails stepwise | ≥ 10 clean live sessions per step |

## 7. Kill / rollback

- Any causality violation in shadow ⇒ S3-b resets to day 0.
- Any live order outside guardrails ⇒ `RENQUANT_RQ105_HALT=1` + containment
  protocol record + rollback of the enabling config in the same batch.
- Rollback is one launchd job disable + one config flag; both named in the
  S3-c enablement record before the flip.

## 8. Explicitly NOT in this design

- **No new model, no GOAL-2 coupling** — 105 consumes the meta-model only if
  GOAL-2 survives its own gates.
- **No 10-minute bar pipeline** — `quote_logger`'s tick stream + censoring
  covers v1; finer bars are a later enhancement with its own justification.
- **No alpha claim.** This is execution freshness. The model's
  `genuine_ic ≈ 0` problem is untouched and unhidden.
- No change to wash-sale, direction gates, or the daily 13:55 run.

## 9. Review

codex (haorensjtu-dev). Implementation PRs only after this design is approved
(operator mandate; design-approved-before-impl).
