# The complete E2E execution pipeline — every link, its automation, and its trust mechanism

AS-OF: **2026-08-04T22:10Z (15:10 PT)** — every mutable status cell below
is verified at this timestamp; refresh the timestamp with any update.

Operator directive 2026-08-04 ("我要的是e2e的完整执行流水线…完整的！可信任的！").
This document is the single map of the full chain — data → training →
artifact governance → serving → execution → evaluation → promotion — with,
for every link: WHAT runs it, WHEN, and WHAT MAKES IT TRUSTWORTHY (the
mechanical check that fails loudly, never a promise). Status keys are
dated; a link with no independent verifier is listed as a GAP, not
papered over.

## 1. Data

| link | automation | trust mechanism |
|---|---|---|
| Daily OHLCV + fundamentals + sentiment ingest | scheduled daily jobs (launchd, manifest-pinned) | PIT freshness guard in every retrain: missing/future bars are INTEGRITY failures, never tolerated (proven live 2026-08-04: it refused two mid-session manual retrains); per-ticker completeness on the panel path |
| Run-surface integrity | daily drift scan | manifest↔disk BIDIRECTIONAL comparison (43→40 jobs, reviewed); unmanifested-job and swapped-ProgramArguments alarms; the pending-uninstall contract forces cleanup through review |

## 2. Training updates (the "训练更新" half)

| model | cadence | trust mechanism |
|---|---|---|
| Prod panel (alpha158+fund, reversal-leaning) | WEEKLY Saturday 05:00 retrain → staging → WF gate → promote (`weekly_wf_promote.sh`, wrapper sha pinned in the emitter contract) | gate criterion untouched; RFC#210 freshness fallback ARMED and EXERCISED 2026-08-04 — manual promotion 11:31 PT ended 44d staleness (prod now trained 08-02); the 13:00 PT scheduled run then exercised the WHOLE chain end-to-end (PIT pass → retrain → gate FAIL genuine_ic +0.0021 → decide REFUSE on a 2d-fresh prod = correct); reject notification is STATE-AWARE since RQ#568 (fresh-reject → calm + exit 0; anything unproven → alarm + exit 1, fail-closed); 5-check governance + PERMANENT `promotion_basis` stamp unchanged; sentinel counts FALLBACK-PROMOTED as an ACTION |
| Slow momentum v0 (12-1) | WEEKLY Saturday train job → dated artifact + append-only digest-chained ledger | params FROZEN pre-run (model#199 lineage); chain verified on EVERY load (single-read snapshot, sha both directions, row↔artifact parity, GOLDEN REPRODUCTION — the served scores are recomputed from stored features, never trusted); genesis artifact live since 08-02 |
| Fast momentum v1 (63/5) | same Saturday job, second NON-FATAL step (deployed 2026-08-04; first artifact 2026-08-08) | own ledger (`artifacts/momentum_fast/`), identical chain contract; sentinel third lane watches it FROM THE DORMANT WINDOW; the umbrella candidate-pin gate admits its ledger only under the declared pending marker |
| Calibrators | refit within the weekly promote | same staging→gate path; never promoted alone (the binding-orphan class is closed by the atomic pair swap) |

## 3. Artifact governance

| link | trust mechanism |
|---|---|
| Identity | content sha + config fingerprint on every artifact; ledger-served artifacts pinned by RECIPE fingerprint (byte pins refused on append-only surfaces — enforced by loader AND the umbrella gate) |
| Lineage | Stage-1 lineage stamp LIVE (43/43); Stage-2 seam-separated scoring stamp LIVE — bt#104 merged + deployed, FIRST stamp landed in the 13:00 PT gate run: pre_seam 82/82 scored, post_seam 42/43 (final ladder window refused BY DESIGN: "no closing edge; never invented"), stage1_lineage_root_match=true — stamps are SIBLINGS, admission byte-identical |
| Pins | every subrepo pinned in `subrepos.lock.json`; pin bumps run the candidate-pin artifact gate + snapshot regeneration verified byte-exact against the candidate assembly; runtime checkouts synced only to reviewed pins |

## 4. Serving (daily 14:00 PT `daily_104.sh`)

| lane | what runs | trust mechanism |
|---|---|---|
| PROD | full funnel → live Alpaca orders | preflight gate battery — P-WF-GATE (BOTH twins) learned the RFC#210 serving license 2026-08-04 after the governance-served artifact hard-failed `passed` and the book went sell-only for one session (pipeline#263; the 14:42 PT rerun then hard-PASSED with governance provenance and placed 3 buys + 1 sell, broker-ACCEPTED); fail-closed loader contracts; R4 `wf_gate_provenance` in the persisted bundle is a MEASURED GAP — see gaps |
| In-process shadows (xgb variant, slow momentum, fast momentum) | same scoring pass, identity-stamped health records | shadow-scorer sentinel (3 lanes incl. the dormant fast lane), liveness receipts, silent-refusal sentinel with a versioned emitter contract |
| Step 5: clf-blend e2e | full funnel, readonly broker, own state/db | certified profile with dual identity pins; distinct alert titles; rank-domain guard fail-closes probability floors on uncalibrated scores |
| Step 5b: S1 momentum-blend e2e | ACTIVE — profile landed; first execution 2026-08-04 found TWO consumer misses fixed same-day (P-WF-GATE license pipeline#263; `alpaca_shadow_blend_mom` absent from ALLOWED_BROKERS pipeline#264) | gates on the PINNED config only; lane-isolated tag/state/db (tag allowlisted since #264); guard file CI-enumerated |

## 5. Execution

| link | trust mechanism |
|---|---|
| Live orders | broker wrapper with allowlisted state tags (fail-closed on unknown); wash-sale NPV floor ($5 operator-set); protection exits (3-strike mu rule — exercised live 2026-08-04 on APH/INTC); STATE-EXT-SELL reconciliation stamps the true broker fill |
| Shadow orders | readonly wrapper — reads live, writes swallowed; sized picks visible in ntfy with lane-distinct prefixes |

## 6. Evaluation → promotion (the ladder back into production)

| stage | status 2026-08-04 | trust mechanism |
|---|---|---|
| S1: blend lane operational window | prereg FROZEN (orch#777); **LANE LIVE** — s104#86 merged (d84604d7), RenQuant#565 merged (a7cd21d49), deployment boundary RECORDED 2026-08-04T18:19:44Z (grants trail + s104#86 comment); **today's 14:00 PT run is session 1 of 20** | 20 scheduled sessions from the verified boundary; every session counts; green defined mechanically |
| S2: three-lane returns comparison | prereg FROZEN (orch#781 + amendment #782); readout MERGED pre-window (orch#783 c6ebddc5; provider loader pipeline#262 f25574fc merged + DEPLOYED in the #565 sync) | score-level primary (the only shared layer), ≥19/20 matched-pair coverage on BOTH pairs, two-phase extension rule, seeded placebo, per-session serving-identity triplets, no significance theater at n=20 |
| S3: MoE (regime-conditional weights) | machinery exists; weight map MUST be preregistered with placebo arms (AC3) | gated by S2 verdict |
| S4: capital sleeve | gated by S2 + operator quota sign-off | sleeve-level risk rules + own rollback + containment record |

## 7. Cross-cutting trust

- Every review is adversarial (codex CODEOWNERS gate; no self-merge, no
  admin bypass — held under explicit operator pressure 2026-08-04).
- Every deployment is a logged grant with literal reverts; the drift scan
  alarms on anything that bypasses it.
- Every number in a report carries a provenance tag; preregs freeze
  before outcomes exist; negative results publish (the 07-23 KILL verdict
  and both booster measurements are archived with unreproduced-historical
  labels rather than deleted or over-claimed).
- LESSON INSTITUTIONALIZED 2026-08-04: a promotion-license change must
  enumerate EVERY consumer of the old license. RFC#210 changed what
  "servable" means, and THREE `passed`-consumers were re-taught the same
  day, each found by running rather than review (runtime P-WF-GATE twins →
  sell-only session; reject-notify tone → operator alarm fatigue; bundle
  checker → doctor RED). Fingerprint identity is SCHEMA-SCOPED: the
  runtime legacy hash is authoritative for calibrator binding; the common
  v1 hash is a different schema, not a contradiction (triple-impl class,
  occurrence #5).

## Honest gaps as of 2026-08-04T22:10Z (15:10 PT)

1. R4 `wf_gate_provenance` is ABSENT from the persisted run bundle of
   today's successful full run (measured: `pipeline_runs.run_bundle_json`
   9,154 B, no key) — the R4 requirement is deployed-but-dark on the
   daily path; orch#564 AC6 stays OPEN with this measurement on record.
2. S1 session 1: the two blockers are fixed AND deployed; the record for
   today is expected from the currently-running Step 5b (or a manual
   rerun tonight if it misses) — the window is 0/20 until a record
   EXISTS, and the ≥19/20 S2 coverage bar has no slack left for a second
   miss in the window.
3. Fast momentum's first artifact is Saturday 2026-08-08.
4. Momentum-alone has NO trade-level record by design (score-level only).
5. Doctor `bundle_consistency` RED clears only when orch#791 (license
   mirror + runtime-authoritative calibrator match) merges and the run
   checkout syncs.
6. Fingerprint-schema unification (ONE shared model_content_sha256) is
   still an open structural debt; today's fix makes the divergence NAMED
   and runtime-authoritative, not gone.
