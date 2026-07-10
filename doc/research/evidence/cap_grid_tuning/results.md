# Cap-grid replay experiment — [EXPLORATORY / TUNING SUBSET — does not select anything, does not clear any gate]

**Label: EXPLORATORY / TUNING SUBSET ONLY (149/497 sessions). NOT decision
evidence. The 348-session evaluation subset is RETIRED and was never touched.**

- Date: 2026-07-10
- Harness: renquant-pipeline `feat/replay-harness-d6-conventions` (commit 6ac718f),
  worktree `scratchpad/wt-harness` — verified on-branch and clean; harness code
  untouched (realized per-name weights captured by a driver-side wrap of
  `_record_family_violations`, restored after the run).
- Data: byte-copy `scratchpad/sim_runs.db`, sha256
  `82084a6d026a1a8db39c92d19ee119f7f79c96e82a4dade91404d93848772a88` — re-verified,
  matches the freeze record exactly. All reads against the copy.
- Freeze: `deploy_policy_results/d6_freeze_20260709.json`, fwd_1d TUNING ids only
  (149 sessions, 2024-01-03..2026-03-27). Regimes on bars: BULL_CALM 128,
  BULL_VOLATILE 14, CHOPPY 5, BEAR 2.
- Deployment target: **gross 0.95 for every session** (the regime ceiling).
  Regime labels ARE present on these bars, but the ceiling is intentionally fixed
  per the task spec — this isolates the cap × breadth effect from regime scaling
  (and BULL_CALM is 86% of the window anyway).
- Conventions: `--stateful --tax --integer-shares --enforce-caps`
  (name cap = the arm's cap; sector cap 35%, snapshot map, max/sector 6),
  5 bps/side, PV $10,700, top-k 8, fwd_1d. Each cap group ran with its own
  `ReplayConventions(per_name_cap=cap)`; bars identical across arms so paired
  contrasts are valid.
- Weight rules: `ew` = min(0.95/n_sel, cap) on top-8 positive-μ;
  `ck` = min(max(0.3·μ/σ², 0), cap), down-only budget scale to 0.95 — the literal
  spec formula, no scale-up to the ceiling (raw Kelly wants ~2.4× leverage so the
  cap saturates almost everywhere; realized shortfall vs the ceiling is 2.3–5.2pp
  gross, reported below).
- **Reproduction cross-check**: cap12_ew ≡ the prior experiment's ew_full and
  cap12_ck ≡ kelly_raw — all metrics match the 2026-07-09 run exactly
  (+4.70% / 0.38 Sharpe / −15.8% MDD / $4,806 tax; HAC t −0.69 p 0.487),
  confirming the instrumentation changed nothing.

## (a) One-table grid comparison (149 tuning sessions, paired bars)

| arm | mean E_exec | med E_exec | total net ret | Sharpe (ann) | MDD | tax $ | cost $ | turnover | max name w | worst-name p1 | worst-name p5 | sector br. | int. resid | HAC t vs cap12_ew (p) | win rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **cap12_ew** (incumbent) | 0.522 | 0.462 | **+4.70%** | +0.38 | −15.8% | 4,806 | 227 | 0.269 | 0.120 | −1.68% | −0.97% | 30 | 0.031 | — | — |
| cap12_ck | 0.497 | 0.446 | +0.62% | +0.17 | −12.1% | 3,976 | 217 | 0.263 | 0.120 | −1.23% | −0.92% | 26 | 0.034 | −0.69 (0.49) | 0.530 |
| cap20_ew | 0.655 | 0.704 | −3.08% | +0.08 | −17.9% | 5,609 | 288 | 0.359 | 0.200 | −2.79% | −1.61% | 72 | 0.037 | −1.09 (0.28) | 0.436 |
| cap20_ck | 0.626 | 0.682 | −2.45% | +0.02 | −13.2% | 4,894 | 283 | 0.350 | 0.200 | −2.06% | −1.36% | 55 | 0.033 | −0.72 (0.47) | 0.503 |
| cap25_ew | 0.700 | 0.746 | −8.18% | −0.12 | −18.9% | 5,578 | 305 | 0.393 | 0.250 | −3.11% | −1.98% | 72 | 0.041 | −1.42 (0.15) | 0.416 |
| cap25_ck | 0.668 | 0.734 | −5.06% | −0.09 | −14.7% | 5,111 | 306 | 0.387 | 0.250 | −2.35% | −1.56% | 62 | 0.034 | −0.79 (0.43) | 0.490 |

HAC sign: arm − cap12_ew (negative = arm loses). Name-cap breaches 0 for all arms
by construction (cap pre-applied in-arm). Off-universe forced liquidations
140–141/149 for every arm; no-candidates sessions 0. worst-name p1/p5 = percentile
of the per-session min over held names of (wᵢ × rᵢ), i.e. the single worst name's
contribution to session P&L as a fraction of PV.

## (b) Deployment ceiling / breadth proxy

Candidate breadth (identical for all arms): median **4** names; histogram
1:4, 2:35, 3:25, 4:18, 5:8, 6:11, 7:9, 8:39 sessions; P(n≥4)=0.570,
P(n≥5)=0.450, P(n≥8)=0.262.

| arm | theo ceiling mean (min(0.95, n·cap)) | E_exec/ceiling | ceiling breadth-bound (n·cap<0.95) | P(E_exec ≥ 0.80) | P(E_exec ≥ 0.90) | breadth needed for 0.90 (pre-shave) | P(breadth ≥ needed) |
|---|---|---|---|---|---|---|---|
| cap12_ew | 0.563 | 0.937 | 73.8% | 23.5% | 10.1% | 8 | 26.2% |
| cap12_ck | 0.563 | 0.882 | 73.8% | 22.8% | 2.7% | 8 | 26.2% |
| cap20_ew | 0.724 | 0.915 | 55.0% | 34.2% | 10.7% | 5 | 45.0% |
| cap20_ck | 0.724 | 0.859 | 55.0% | 34.9% | 10.1% | 5 | 45.0% |
| cap25_ew | 0.792 | 0.891 | 43.0% | **39.6%** | 12.1% | 4 | 57.0% |
| cap25_ck | 0.792 | 0.835 | 43.0% | **38.9%** | 10.7% | 4 | 57.0% |

- **At cap=25%, only ~39–40% of sessions reach ≥80% deployed** (ew 39.6%, ck 38.9%).
- **Breadth needed for 90% deployed** — arithmetic (ceiling ≥ 0.90): 8 names at
  cap 12% (available on 26.2% of sessions), 5 at cap 20% (45.0%), 4 at cap 25%
  (57.0%). **But breadth alone does not deliver 90%**: the execution shave
  (integer-share flooring 3.1–4.1pp gross on a $10.7k book + the 35% sector-cap
  projection, which fired on 26–72 sessions/arm) cuts E_exec to 0.84–0.94 of the
  ceiling on average, so at mean shave you need ceiling ≥ 0.90/0.89 ≈ 1.01 at
  cap 25 — above the 0.95 budget. Hence P(E≥0.90) is stuck at 10–12% in every
  arm (only low-shave sessions get there). To actually live at ~90% deployed this
  book needs breadth ≥ 5–8 **and** either fractional shares or a bigger PV, and a
  sector-cap-aware selector.
- ck arms fall short of the ceiling by a further 2.3–5.2pp gross (target-gross
  shortfall vs min(0.95, n·cap)) — sessions where per-name Kelly lands below the
  cap; the saturation claim (ck ≈ ceiling) holds to within those pp.

## (c) Concentration tail — what the cap costs when one name breaks

Per-session worst single-name loss contribution, min over held names of (wᵢ × rᵢ):

| arm | p1 | p5 | median | worst session |
|---|---|---|---|---|
| cap12_ew | −1.68% | −0.97% | −0.23% | −2.20% |
| cap12_ck | −1.23% | −0.92% | −0.21% | −1.51% |
| cap20_ew | −2.79% | −1.61% | −0.29% | −3.08% |
| cap20_ck | −2.06% | −1.36% | −0.26% | −2.27% |
| cap25_ew | −3.11% | −1.98% | −0.29% | −3.81% |
| cap25_ck | −2.35% | −1.56% | −0.28% | −2.72% |

- The tail scales ~linearly with the cap: ew p5 goes −0.97% → −1.98% (×2.04 for a
  ×2.08 cap raise); p1 −1.68% → −3.11% (×1.86). Max realized single-name weight
  hits the cap exactly in every arm — names DO ride at the cap, so the cap is the
  binding lever on single-name event risk.
- Kelly weighting buys a consistently thinner tail at the same cap (p1 ~25% less
  negative at cap 25) because low-σ̂ names get under-cap weights; it also had
  shallower MDD in all three cap groups.

## (d) Reading (hypothesis-grade only)

Raising the cap bought deployment (0.52 → 0.70 mean E_exec) but on this tuning
window it bought **negative** marginal return (+4.7% → −8.2% ew; all HAC t between
−0.69 and −1.42, p ≥ 0.15 — none significant), deeper MDD, ~$0.8k more tax, and a
~2× fatter single-name loss tail. The extra deployment concentrates into the
top-of-book names (breadth median 4), so the marginal exposure is exactly the
concentration the 12% cap exists to prevent. Deployment remains breadth-bound at
every cap tested; the deployment lever this grid actually surfaces is breadth (and
execution shave), not the cap.

## (e) Limitations

1. **Exploratory, tuning subset only** — 149 seeded-hash sessions, not
   preregistered, does not clear any gate; evaluation subset untouched. Prior-run
   PBO on these bars was 0.61 (high overfit probability); all HAC deltas here are
   insignificant — ordering is hypothesis, not result.
2. **Non-contiguous stateful carry** — the tuning subset is a random 30% of dates;
   lots/prices/holding periods span multi-week gaps and positions are marked only
   by each session's fwd_1d return, so absolute return/Sharpe/MDD levels are not
   portfolio-realistic; only paired arm-vs-arm contrasts on identical bars are
   meaningful.
3. **Returns-consistent pricing** (harness convention) — internal prices evolve by
   fwd_1d from entry anchors; deviation from true close-to-close marks is a
   documented harness limitation, amplified by the non-contiguous subset.
4. **Fixed 0.95 ceiling** — regime labels exist on bars (BULL_CALM 86%) but were
   intentionally unused per spec; a regime-scaled ceiling would barely differ
   in-window and is untested here.
5. **capped_kelly is the literal min(0.3μ/σ², cap) with down-only budget scale**
   — no scale-up to the ceiling; it under-deploys the ceiling by 2.3–5.2pp gross.
   A renormalized ("kelly-tilted at ceiling") variant is a different arm.
6. **Universe churn × asymmetric tax dominates**: 140–141/149 sessions force
   off-universe liquidations; the D6 tax convention (ST 50%/LT 32%, zero loss
   credit) charges $4.0–5.6k against a $10.7k book, dwarfing every cap effect.
   A real cap decision needs the persistent watchlist universe.
7. **Thin breadth compresses the grid**: with median 4 candidates, arms differ
   mainly by cap×n and the top-of-book weights; only 39/149 sessions have 8 names.
8. **Sector map is today's 156-ticker snapshot** applied to 2024–26 history;
   the 35% sector projection fired on 26–72 sessions/arm and is a first-order
   part of the deployment shave.
9. **Concentration proxy** uses post-trade executed weights (relative to the
   post-liquidation PV base) × fwd_1d return; it is not a full loss attribution
   (no overnight/gap moves between non-contiguous sessions).
10. **Integer flooring on a $10.7k PV** shaves 3.1–4.1pp gross on average —
    material relative to the cap deltas being measured; results scale with PV.
11. **dw_max / turnover-cap families not enforced** (counters only), as in the
    prior experiment; the harness promotion gate would reject all arms on this.
12. **σ̂ units**: model σ̂ is fwd_60d-horizon (median ~0.123); the Kelly ratio
    μ/σ² uses same-horizon DB values per the arm formula, as before.

## Files

- Evidence JSON (full series, side channels, per-session worst-name series):
  `cap_grid_results/evidence_cap_grid_tuning_fwd1d.json`
- Driver: `cap_grid_results/run_cap_grid_arms.py`
  (run with venv-d6 python, PYTHONDONTWRITEBYTECODE=1,
  PYTHONPATH=renquant-artifacts/src:renquant-base-data/src primary checkouts,
  read-only imports)
- Freeze record / sector snapshot: reused from `deploy_policy_results/`
  (d6_freeze_20260709.json; sector_map_snapshot.json)
- DB byte-copy: `../sim_runs.db` (sha256 82084a6d026a…, re-verified pre-run)
