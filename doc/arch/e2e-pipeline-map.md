# The complete E2E execution pipeline — every link, its automation, and its trust mechanism

AS-OF: **2026-08-05T04:05Z (21:05 PT)** — every mutable status cell below
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
| Prod panel (alpha158+fund, reversal-leaning — now component[0] of the served z-blend) | WEEKLY Saturday 05:00 retrain → staging → WF gate → promote (`weekly_wf_promote.sh`, wrapper sha pinned in the emitter contract) | gate criterion untouched; RFC#210 freshness fallback ARMED and EXERCISED 2026-08-04 — manual promotion 11:31 PT ended 44d staleness (prod now trained 08-02); the 13:00 PT scheduled run then exercised the WHOLE chain end-to-end (PIT pass → retrain → gate FAIL genuine_ic +0.0021 → decide REFUSE on a 2d-fresh prod = correct); reject notification is STATE-AWARE since RQ#568 (fresh-reject → calm + exit 0; anything unproven → alarm + exit 1, fail-closed); 5-check governance + PERMANENT `promotion_basis` stamp unchanged; sentinel counts FALLBACK-PROMOTED as an ACTION |
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
| PROD | full funnel → live Alpaca orders. **2026-08-04 OPERATOR OVERRIDE: the primary scorer is now the z-blend** (`kind=blend`, components = governance-served reversal scorer + chain-verified slow-momentum ledger) on the FULL book, with nine unit-dependent control groups disabled (audit manifest `zblend_prod_artifact_manifest.json`, single-commit rollback, review condition 10 sessions / −5% / 2026-08-31) | preflight gate battery — P-WF-GATE (BOTH twins) learned the RFC#210 serving license 2026-08-04 after the governance-served artifact hard-failed `passed` and the book went sell-only for one session (pipeline#263; the 14:42 PT rerun then hard-PASSED with governance provenance and placed 3 buys + 1 sell, broker-ACCEPTED); fail-closed loader contracts; R4 `wf_gate_provenance` in the persisted bundle is a MEASURED GAP — see gaps |
| In-process shadows (xgb variant, slow momentum, fast momentum) | same scoring pass, identity-stamped health records | shadow-scorer sentinel (3 lanes incl. the dormant fast lane), liveness receipts, silent-refusal sentinel with a versioned emitter contract |
| Step 5: clf-blend e2e | full funnel, readonly broker, own state/db | certified profile with dual identity pins; distinct alert titles; rank-domain guard fail-closes probability floors on uncalibrated scores |
| Step 5b: S1 momentum-blend e2e (callsign **RSs**) | ACTIVE; first execution 2026-08-04 found TWO consumer misses fixed same-day (pipeline#263 license; pipeline#264 broker tag) | gates on the PINNED config only; lane-isolated tag/state/db; guard file CI-enumerated |
| Step 5c/5d/5e: fleet lanes **Rf / RCS / RCf** (GOAL-9, orch#794) | rails + profiles + tags all deployed 2026-08-04; RCS (rev-blend + slow) is serving-eligible, Rf/RCf dormant until the 2026-08-08 fast-momentum genesis | tags registered AT BIRTH (pipeline#265 — the #793 checklist applied before the rail existed); 3-component support via pipeline#267 (equal-weight z-sum generalized verbatim, N≥2); each lane's success echo pinned to its OWN profile identity by test |

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
- LESSON INSTITUTIONALIZED 2026-08-04 (SIX consumers, one day): a
  promotion-license OR scorer-identity change must enumerate EVERY consumer. RFC#210 changed what
  "servable" means, and THREE `passed`-consumers were re-taught the same
  day, each found by running rather than review (runtime P-WF-GATE twins →
  sell-only session; reject-notify tone → operator alarm fatigue; bundle
  checker → doctor RED). Fingerprint identity is SCHEMA-SCOPED: the
  runtime legacy hash is authoritative for calibrator binding; the common
  v1 hash is a different schema, not a contradiction (triple-impl class,
  occurrence #5).

## Honest gaps as of 2026-08-05T04:05Z (21:05 PT)

1. **THE WF GATE IS BLOCKED AND THAT IS THE HONEST STATE (orch#799).**
   Measured 2026-08-04: two runs, byte-identical booster, Sharpe 0.6018 vs
   0.0524 — because the z-blend switch made the pinned primary `kind=blend`,
   no pinned config matched the xgb candidate, and the reference search fell
   through to the umbrella WORKING COPY (A8's known-diverged file). The gate
   derived phantom "production semantics" from it while `config_parity`
   passed. RenQuant#580 makes the lock-aligned runtime config the ONLY
   candidate and FAILS CLOSED otherwise. Consequence: until the blend-prod
   reference rule is decided (#799), the weekly promote will BLOCK loudly
   rather than emit numbers — and RFC#210 freshness governance, which runs on
   any nonzero gate exit, is what keeps prod fresh. Three redesign items stay
   open: scrap Sharpe-vs-SPY as an admission criterion, re-derive the placebo
   bar from this corpus's shuffled-label floor, move admission onto Stage-2
   candidate scoring.
2. The **z-blend full book has ZERO out-of-sample record** — the operator's
   explicitly accepted risk (manifest). The blend-level PIT backtest is
   drafted (orch#797) and NOT yet frozen; the nine disabled control groups
   have no measurement either way.
3. R4 `wf_gate_provenance` — **CLOSED 2026-08-04**: measured present
   (10,087 B bundle, `promotion_basis=freshness_fallback_rfc210`,
   `trained_date=2026-08-02`) after RQ#573 wired it into the SERVING bundle
   producer; the pre-deploy run measured ABSENT at 9,154 B (before/after pair
   is the acceptance evidence). orch#564 closed.
4. S1/S2 as a PROD-vs-BLEND comparison is **degenerate from the switch date**
   (treatment == control); the 2026-08-31 readout is reclassified as a
   retrospective, and fleet-relative comparison (orch#794 AC4) is the standing
   evidence stream. Session 1 (2026-08-04) stays on record.
5. Fast momentum's first artifact is Saturday 2026-08-08; that batch must ALSO
   add the fast fp pins, delete the pending markers, and commit the fast
   ledger genesis (playbook orch#795).
6. The rawlabel σ-head sidecar has **no living scheduled host** — its only
   republish rode inside the retired PatchTST job (orphaned side-product;
   republished manually tonight, structural re-home tracked as orch#798).
7. The clf WF corpus is BUILT (43/43 windows, `built_unscored`) but NOT yet
   scored — Stage-2 integration is the next GOAL-6 step.
8. Fingerprint-schema unification (ONE shared `model_content_sha256`) is still
   open structural debt; the divergence is NAMED and runtime-authoritative,
   not gone.
