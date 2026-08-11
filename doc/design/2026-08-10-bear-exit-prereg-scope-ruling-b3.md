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
- It does not launch the backfill. **The backfill is a compute campaign
  (walk-forward retrains + artifact assembly for ~2016–2022 cutoffs) that
  requires OPERATOR spend authorization** — recorded here as the ruling's
  precondition, not executed by it.
- It does not change live config or activate anything. A confirmatory PASS
  (once the run is unblocked) still only earns the amendment the *right to be
  proposed*; the live `strategy_config.json` change remains a separate operator
  grant (§4 item 3, unchanged).

## Consequence / next step

G-B's confirmatory run is now blocked on exactly two capabilities, both scoped:
**B2** (book-simulator regime-series injection — the placebo/shift arms;
renquant-backtesting PR) and **the B3 backfill** (2016–2022 walk-forward
artifacts; operator spend-gated). Neither is calendar-gated. B1 (#282) and B4
(#965) are done. This ruling converts B3 from "open operator question" to a
recorded precondition: schedule the backfill, or G-B's verdict waits — but do
not substitute a minor-bear-only run for it.
