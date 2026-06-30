# renquant105 direction decision — progress

2026-06-28.

STATUS: SCOPED DIRECTION HYPOTHESIS doc opened for Codex + operator discussion,
revised twice for Codex CHANGES_REQUESTED on PR #207 (round 1 = 2026-06-29
framing; round 2 = 2026-06-29 Track-A executability + PR title/body). The operator
delegated the directional call to me; this PR is the discussion vehicle. No code,
no scans, no orders, no git in the live tree, no canonical writes — the §1
evidence was produced by already-shipped read-only scans (durable, referenced)
plus temporary `/tmp` model-audit scratch (NOT durable; downgraded to discussion
evidence). Framed as a scoped hypothesis with cited artifacts, NOT a definitive
exhaustion decision.

WHAT: `doc/design/2026-06-28-renquant105-direction-decision.md` — the decision
record: §1 the scoped finding ("no robust directional edge has surfaced under the
current diagnostic suite on the current large-cap inputs," with numbers), §2 the
two-track decision, §3 why (honest), §4 the Track A test spec, §4(b) the evidence
contract (provenance / prod-or-exp / inputs / scope per source), §5 references.
Round-1 revision: (1) softened the headline from "directional alpha is exhausted /
binding constraint = DATA+UNIVERSE" to the scoped framing; (2) added §4(b)
evidence blocks for A1/A2/BEAR and downgraded them to discussion evidence (`/tmp`
scratch from unmerged scripts); (3) made Track A a conditional-pick-quality test
spec; (4) corrected the #205 status; (5) converted this progress doc to C5 format.
Round-2 revision (this commit), addressing Codex's second review on Track A
executability: (1) removed the contradiction where §4 reused the `/tmp` OOS table
— Track A's first step is now an explicit REGENERATION PR (committed generator,
durable experiment-path output, schema) before anything runs; (2) recalibrated the
stop/go gate to PORTFOLIO impact (annualized capital-weighted book lift ≥ +50bps/yr
as the binding economic gate, plus turnover / missed-winner opportunity-cost caps),
so a statistically-nonzero-but-untradeable result cannot pass; (3) relabeled the
test CANDIDATE-QUALITY (top-decile candidates), explicitly distinct from the live
acted-on book (cash / risk caps / held-name / regime / execution intervene);
(4) gave each conditioning variable an exact source + as-of semantics + PIT status
([VERIFIED] regime/dispersion/margin; [GUESS — needs check] earnings-window /
vol-ADV), with the rule that any variable needing an unmerged source is DROPPED
(it would be Track B); (5) rewrote the PR title/body to scoped language so the
permanent commit does not reintroduce the removed overclaim.

WHY/DIR: The original 105 goal — "catch more / more-accurate trends" — requires a
directional edge. This session's read-only diagnostics found NO usable
directional cross-sectional edge surfacing on the current 134-large-cap universe
+ current data, under this diagnostic suite. We state the inputs as the SUSPECTED
(not proven) bottleneck — a scoped, falsifiable hypothesis, not an exhaustion
theorem and not a proven causal binding constraint. The diagnostics are
current-watchlist / survivorship-biased and the strongest model-side numbers are
un-durable `/tmp` scratch, so the claim is deliberately scoped. Direction: do the
immediate non-directional thing now (Track A, gated on a conditional-signal test
that can legitimately return null), and flag the real directional path (Track B =
input change) as the operator's call.

EVIDENCE: §1, this session, read-only, OOS/CI/placebo. The A1/A2/BEAR numbers
below are **temporary `/tmp` scratch outputs from unmerged, uncommitted scripts —
DISCUSSION EVIDENCE, NOT a decision keystone; they will be deleted and a reviewer
cannot re-fetch them from git.** Full provenance is §4(b) of the design doc.
- A1 (live-model audit) — `/tmp` scratch, NOT committed. Scripts
  `/tmp/a1_modeledge/01_get_oos_predictions.py … 05_regime_and_sharpe.py`;
  outputs `/tmp/a1_modeledge/{VERDICT.md, regime_sharpe.json, rigor_summary.json,
  injection_floor_leak.json, oos_*.parquet}`. EXPERIMENT/scratch read-only
  re-score of PROD manifest `walkforward_manifest_gbdt_prod_recipe_v2.json` (37
  PIT artifacts; feature panel `alpha158_291_fundamental_dataset.parquet`, label
  `fwd_60d_excess`, 147,066 rows / 508 OOS dates 2024-02→2026-02). Reproduced
  committed genuine_ic to 4dp (0.0415 vs 0.0417) = faithful. Finding: genuine_ic
  CI [−0.031,+0.129] includes 0; fails slow-persistence injection (genuine
  0.042→0.29 = not clean leak removal); BULL_CALM (79% of OOS) genuine ≈ −0.003
  (coin flip); all skill carried by ~10% BEAR slice. Scope: current-watchlist,
  survivorship-biased; best read-only audit of THIS model on THIS panel, not a
  durable artifact.
- A2 (GKX combination) — `/tmp` scratch, NOT committed. Scripts
  `/tmp/a2_combo/{combo.py, combo_model.py, walkforward.py, eval.py}`; outputs
  `/tmp/a2_combo/{VERDICT.md, manifest.json, economics.csv, ...}`. 10 factors,
  sector+120d-beta neutral, walk-forward 17 blocks refit/63d purge20d, OOS
  2022-05-31→2026-06-26 = 1002 dates; EW/Ridge/GBM combos. Finding: every combo
  dominated by single mom_12_1 (net L/S Sharpe EW −0.09 / Ridge +0.23 / GBM +0.74
  vs mom +1.11); mom itself a recent-bull artifact; no multi-factor synergy.
  Single-spec read (hyperparams fixed to avoid OOS-peeking), survivorship-biased.
- BEAR/short audit — `/tmp` scratch, NOT committed. Per-regime cut of the same A1
  scratch (`05_regime_and_sharpe.py` → `regime_sharpe.json`). BEAR genuine +0.236
  on n≈50 dates only (effective N small), bootstrap CI includes 0; it's a
  V-recovery LONG-ranking (config forbids acting on as a short,
  `BEAR.max_position_pct=0`); short leg net-negative; intraday adds nothing. NOT a
  short edge.
- Durable / committed evidence (NOT `/tmp`, re-fetchable) — the price-trend,
  regime-momentum, fundamentals scans (`sighunt.py`, `robustness.py`,
  `regimemom.py`, `fundamentals_scan.py`) and their write-ups: price-trend 5
  canonical factors show no robust 20/60d edge (mom_12_1 clears floor only at h=5;
  h20 IC 0.74×); regime-momentum NO (yearly sign-flip survives inside UP-trend,
  2021 100% UP yet IC −0.065); fundamentals value wrong-sign & soft once overlap
  respected (EY-252d non-overlap t≈−2.4), quality/growth null. These are the parts
  of §1 a reviewer can re-fetch.
- Honest framing: scoped hypothesis, not a proof. "No robust edge surfaced under
  this diagnostic" ≠ universal exhaustion; "consistent with large-cap-weak anomaly
  literature" ≠ proven causal binding constraint. Inputs are the SUSPECTED
  bottleneck, kept falsifiable.

NEXT (the decision — two-track):
- Track A (immediate, no new inputs) — meta-label entry filter, but gated on a
  conditional CANDIDATE-QUALITY test FIRST (design §4). NOT runnable today: the
  test needs a durable OOS pick table that does not exist as a committed artifact
  (the A1 table is `/tmp` scratch that will be deleted; no committed generator in
  this repo — `model_sanity_compare.py` only collates JSON). So Track A's literal
  first move is a small REGENERATION PR that commits a generator
  (proposed `scripts/regen_oos_pick_table.py`) re-scoring the prod manifest
  read-only to an EXPERIMENT path (proposed `data/exp/oos_pick_table_recipe_v2.parquet`,
  never a canonical prod path), schema {date,name,score,decile_rank,fwd_60d_excess,
  regime} over 508 OOS dates. Test spec (against that regenerated table): label =
  binary candidate-success (top-decile long candidate's fwd_60d_excess > 0 net of
  11bps) — CANDIDATE quality, NOT the live acted-on book (which is gated by cash /
  risk caps / held-name / regime / execution; reconstructing it is a separate
  larger step, out of scope here); conditioning vars = regime + score dispersion +
  score margin (all [VERIFIED] available, derived from the table) PLUS
  earnings-surprise window (`data/fmp_harvest/earnings_291.parquet`, PIT via SEC
  acceptedDate) + 60d-vol/ADV bucket (price/bars panel) — both umbrella-tree files
  (read-only, NOT this repo, NOT new inputs) but [GUESS — full-OOS coverage / PIT
  not verified from here]; if either fails the availability check it is DROPPED
  (not substituted with an unmerged feed — that would be Track B), and the test
  runs on the [VERIFIED] vars alone. Split = chronological, fit first 60% of 508
  OOS dates, embargo 60d, test remaining ~40%; baseline = unconditional top-decile
  candidates; metrics = hit-rate (block-bootstrap CI), per-pick expectancy net of
  turnover/cost, ANNUALIZED CAPITAL-WEIGHTED book-return lift, turnover /
  missed-winner opportunity cost, active-day exposure. STOP/GO calibrated to
  PORTFOLIO impact (not per-pick statistical nonzero): GO only if held-out
  annualized capital-weighted book lift ≥ +50bps/yr (CI lower > 0, the binding
  economic gate) AND per-pick net lift ≥ +5bps/60d (CI lower > 0, a
  necessary-not-sufficient significance floor) AND hit-rate lift ≥ +3pp (CI
  excludes 0) AND active-day exposure ≥ 25% AND the filter drops ≤ 1/3 of baseline
  winners / no more than doubles turnover; else declare Track A NULL and that Track
  B is the only remaining path. The +50bps/yr and opportunity-cost levels are
  first-pass proposals for operator/Codex calibration (set to reject a
  statistically-nonzero-but-untradeable pass; open to tightening, not loosening).
  HONEST CAVEAT: meta-labeling improves precision of acting on a primary signal —
  it CANNOT manufacture edge from a coin-flip primary; the test can legitimately
  return null. Secondary levers: vol/risk-timing, execution/cost.
- Track B (operator-level; FLAG, don't start): change an input — broaden /
  down-cap the universe (anomalies stronger in small/mid-cap) OR acquire new data.
  CORRECTION: the estimate-revision snapshotter #205 is proposed / blocked —
  pending base-data ownership + scheduler; NOT merged (CI-red 2026-06-28); NOT
  accruing any PIT revision history yet. No history exists today. Months-long,
  conflicts with the large-cap liquidity design → explicitly the operator's call.
- ASK (for Codex): is Track A worth it given the coin-flip primary? Is Track B
  (input change) the honest answer? Is the conditional-pick-quality test spec (§4)
  a sufficient pre-filter gate, and is the stop/go threshold calibrated right?
- NOT DONE / OUT OF SCOPE: No new scan, no retraining, no order, no live-tree
  mutation, no self-merge. No CPCV/FWER/DSR framework — a scoped decision
  hypothesis, not a research cathedral. Track A step-1 test and Track B are NOT
  started under this PR.
