# rq105 Stage-3: intraday LIVE entries — the pinned 104 model on fresh data

STATUS: design for review. No implementation in this PR. Operator-directed
2026-08-23 ("105 = live trade; 尽快"), with the staged-rollout mandate:
design → codex approval → implementation PRs → deploy.

## 1. What this is, in one sentence

Give the book **intraday BUY capability** by re-scoring the **same pinned 104
model** on an **intraday feature snapshot**, and executing through the **same
funnel gates** — no new signal, no new model, no gate bypass.

Corrected framing (the operator's phrase "104 只能 live sell" refers to the
intraday lane): `daily_104` already places live buys **once** at 13:55 ET;
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
for names admitted by BOTH the day's 13:55 batch decision AND the intraday
re-score (intersection). The model was trained on EOD bars; scoring intraday
mids is a distribution shift. The intersection bounds it: intraday data can
only *confirm or veto* a batch admission, never admit a name the batch
declined. Relaxing this is a separate, evidence-gated decision.

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
