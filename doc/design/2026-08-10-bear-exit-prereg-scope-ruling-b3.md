# BEAR-exit prereg scope ruling B3 — the confirmatory run must cover the FULL frozen BEAR episode set (backfill required; no minor-bear-only verdict)

STATUS: FREEZE AMENDMENT to `doc/design/2026-08-08-bear-exit-prereg.md`,
per that prereg's own amendment instrument (a new dated document; the
frozen original is not edited). Scope: ONE ruling — which of the frozen
BEAR episodes the confirmatory run evaluates over. It changes NO candidate
value, NO estimand, NO arm/placebo count/threshold/gate. orch#962 blocker B3;
authorized by the operator's delegation "proceed per your recommendation"
(2026-08-10), the operator-level scope ruling that B4 (#965 line 47) explicitly
left open.

## The question (verified)

The frozen episode inventory (per B4, the production GMM, orch#962 derivation,
per-row verified) is **75 BEAR days / 5 episodes**:

| episode | days | sim-artifact reachable? |
|---|---|---|
| 2018-12-24..26 | 2 | NO — beyond all sim artifacts |
| **2020-02-27..04-24 (COVID)** | **41** | **NO — beyond all sim artifacts** |
| 2022-05-18 | 1 | yes (aux / 2024-window loader) |
| 2022-06-13..23 | 8 | yes |
| 2025-04-04..05-07 | 23 | yes |

The book sim binds models via `WalkForwardModelLoader.model_as_of(today)`
("latest retrain with cutoff_date < today; raises if none"); the manifest's 39
retrain cutoffs cover **2024-01..2026-03** only [VERIFIED — orch#962 §3 B3].
So the **2018-12 + 2020-COVID episodes = 43 of 75 BEAR days = 57%** are beyond
ANY existing sim artifact. The covered subset is 2022-05 + 2022-06 + 2025-04 =
**32 days / 3 episodes**.

## The ruling

**The confirmatory evaluation MUST cover the full frozen 5-episode / 75-day
BEAR set.** Running only the sim-covered 3-episode subset is REJECTED as the
verdict basis, and no partial verdict is authorized. Until the 2018-12 and
2020-COVID episodes are sim-artifact-reachable (a backfill of walk-forward
retrain artifacts with cutoffs preceding those episodes), the confirmatory run
stays BLOCKED on B3 — the same "blocked, not falsely-runnable" posture orch#962
established.

## Why (each load-bearing)

1. **Excluding COVID makes the decision non-credible for its own thesis.** G-B's
   thesis is that the BEAR panel signal (genuine IC +0.28, hit 96%) should route
   to *exits*. The single episode where exit timing matters most is the
   2020-COVID crash (41d — 55% of all BEAR days, and by far the most severe
   drawdown). A ruling on "should the BEAR exit fire" that never tests the
   decisive bear answers a different, minor question (2022 chop + a 2025 dip).
   The return-space estimand (net return + maxDD) is dominated by exactly the
   tail episode the subset omits.
2. **The freeze forbids silent window narrowing.** The prereg fixed a
   2017–2026 window and a 5-episode inventory *before* any backtest existed to
   steer them. Quietly evaluating 43% of the days is the post-hoc
   sample-selection the freeze was designed to prevent — it would let the run's
   feasibility, not the thesis, choose the evidence base.
3. **Power does not rescue the subset.** The frozen honest-power statement is
   already policy-grade (BEAR n_eff ≈ 4; statistics as annotation, not t≥2; the
   gates kill *artifact* explanations — placebo, timing — not sampling noise).
   The subset drops n_eff to ~2–3 episodes AND removes the only severe bear, so
   the placebo/timing gates would certify robustness on a sample that contains
   no real bear. That is weaker AND less representative — the worst of both.

## What this ruling does NOT do

- It changes no frozen candidate value, no estimand, no placebo/shift/bootstrap
  arm, no PASS rule. All numbers stay frozen as written (B4-corrected model).
- It does not change live config or activate anything. A confirmatory PASS
  (once the run is unblocked) still only earns the amendment the *right to be
  proposed*; the live `strategy_config.json` change remains a separate operator
  grant (§4 item 3, unchanged).
- The B3 backfill (walk-forward panel-LTR retrains for the ~2016–2020 cutoffs)
  is **LOCAL compute (alpha158 GBDT, ~1–2 min/cutoff, no cloud/Modal, no dollar
  spend), built in isolation** — it does not require spend authorization. The
  prerequisite it does NOT waive is the pin advance below.

## Consequence / next step (corrected — component-merged ≠ pinned, codex #969 P1)

MERGED to a component repo is NOT the same as available to the pinned
multi-repo confirmatory assembly. As of 2026-08-10:

- **B1** = renquant-pipeline **#282** (read `_by_regime` keys), **B2** =
  renquant-backtesting **#111** (regime-series injection seam), **B4** = **#965**
  — all MERGED to their component `main`. **But the umbrella `subrepos.lock.json`
  still pins `renquant-pipeline @ e13cd3e` and `renquant-backtesting @ 8c2c4456`
  — neither pinned revision contains those merge commits [VERIFIED 2026-08-10].**
  So B1/B2 are NOT runnable in the assembled confirmatory environment yet.
- **B3 backfill** = local compute (above), built in isolation.

**Prerequisites before ANY confirmatory invocation (fail-closed):**
1. A **reviewed pin advance** bumping renquant-pipeline past #282 and
   renquant-backtesting past #111, through renquant's standard pin-bump
   discipline: candidate-pin artifact gate + snapshot regeneration verified
   byte-exact + cross-repo integration check + the resolved run-bundle
   commit/artifact fingerprints recorded.
2. The B3 backfill artifacts present, with their fingerprints in the run bundle.
3. This B3 ruling ratified.

This ruling converts B3 from an open operator question to a recorded
precondition, and (per the #969 review) makes explicit that a component PR
merged ≠ a capability pinned and integration-verified. Do not substitute a
minor-bear-only run, and do not invoke the confirmatory run against an
assembly whose pins predate #282/#111.
