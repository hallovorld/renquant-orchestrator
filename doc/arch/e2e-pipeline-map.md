# The complete E2E execution pipeline — every link, its automation, and its trust mechanism

AS-OF: **2026-08-04T18:25Z (11:25 PT)** — every mutable status cell below
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
| Prod panel (alpha158+fund, reversal-leaning) | WEEKLY Saturday 05:00 retrain → staging → WF gate → promote (`weekly_wf_promote.sh`, wrapper sha pinned in the emitter contract) | gate criterion untouched; RFC#210 freshness fallback ARMED 2026-08-04 — a rejected-but-fresh candidate promotes ONLY under the 5-check governance (explicit passed=False, >28d prod staleness, ≤10d candidate, finite placebo-clean genuine_ic ≥0, no downward ratchet) with a PERMANENT `promotion_basis` stamp; sentinel counts FALLBACK-PROMOTED as an ACTION; Step-2 rollback backup every run |
| Slow momentum v0 (12-1) | WEEKLY Saturday train job → dated artifact + append-only digest-chained ledger | params FROZEN pre-run (model#199 lineage); chain verified on EVERY load (single-read snapshot, sha both directions, row↔artifact parity, GOLDEN REPRODUCTION — the served scores are recomputed from stored features, never trusted); genesis artifact live since 08-02 |
| Fast momentum v1 (63/5) | same Saturday job, second NON-FATAL step (deployed 2026-08-04; first artifact 2026-08-08) | own ledger (`artifacts/momentum_fast/`), identical chain contract; sentinel third lane watches it FROM THE DORMANT WINDOW; the umbrella candidate-pin gate admits its ledger only under the declared pending marker |
| Calibrators | refit within the weekly promote | same staging→gate path; never promoted alone (the binding-orphan class is closed by the atomic pair swap) |

## 3. Artifact governance

| link | trust mechanism |
|---|---|
| Identity | content sha + config fingerprint on every artifact; ledger-served artifacts pinned by RECIPE fingerprint (byte pins refused on append-only surfaces — enforced by loader AND the umbrella gate) |
| Lineage | Stage-1 lineage stamp LIVE in the gate runner (43/43); Stage-2 seam-separated scoring stamp WIRED 2026-08-04 under the operator's sign-off (bt#104, in review) — stamps are SIBLINGS, admission byte-identical until the separately-authorized conjunction transition |
| Pins | every subrepo pinned in `subrepos.lock.json`; pin bumps run the candidate-pin artifact gate + snapshot regeneration verified byte-exact against the candidate assembly; runtime checkouts synced only to reviewed pins |

## 4. Serving (daily 14:00 PT `daily_104.sh`)

| lane | what runs | trust mechanism |
|---|---|---|
| PROD | full funnel → live Alpaca orders | preflight gate battery (P-WF-GATE … P-FUND-FRESHNESS), fail-closed loader contracts, run bundle validated at persist (R4: `wf_gate_provenance` REQUIRED — deployed 2026-08-04) |
| In-process shadows (xgb variant, slow momentum, fast momentum) | same scoring pass, identity-stamped health records | shadow-scorer sentinel (3 lanes incl. the dormant fast lane), liveness receipts, silent-refusal sentinel with a versioned emitter contract |
| Step 5: clf-blend e2e | full funnel, readonly broker, own state/db | certified profile with dual identity pins; distinct alert titles; rank-domain guard fail-closes probability floors on uncalibrated scores |
| Step 5b: S1 momentum-blend e2e | DORMANT rail (deployed 2026-08-04) — activates when the pinned profile lands | gates on the PINNED config only; lane-isolated tag/state/db; guard file CI-enumerated after its rot was found and fixed |

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

## Honest gaps as of 2026-08-04T18:25Z (11:25 PT)

1. Prod's FIRST real freshness-fallback promotion is SCHEDULED for
   13:02 PT TODAY (**future at this as-of**; PT, not UTC — the two
   mid-session attempts this morning were correctly refused by the PIT
   guard, grants trail 08:12/09:22 PT). Until it lands, prod serves the
   06-21 model.
2. The S1 lane went LIVE at the 18:19:44Z boundary; its first session
   (today 14:00 PT) has NOT yet run — the window is 0/20.
3. Fast momentum's first artifact is Saturday 2026-08-08.
4. Momentum-alone has NO trade-level record by design (score-level only);
   S2's primary metric is frozen at score level accordingly.
5. Stage-2 lineage wiring (bt#104) is in review — stamps begin at its
   merge + next gate run.
