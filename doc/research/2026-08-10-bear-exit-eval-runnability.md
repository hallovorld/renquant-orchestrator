# BEAR exit confirmatory run — NOT runnable today; blockers named, episode list derived and committed

BOTTOM LINE: the frozen orch#917 evaluation (doc/design/2026-08-08-bear-exit-prereg.md
§3/§3.1) cannot be executed now. Nothing waits on future market data — every
input through 2026-08-07 exists — but three reviewed capabilities are missing
and one freeze-text ambiguity needs a recorded ruling before any arm may run.
Per the freeze's own discipline ("no other values may be tried"; doc text wins)
no substitute estimand was run. The one §3 step the frozen text itself
prescribes as run-time derivable — the episode list from the production regime
artifact — WAS executed and is committed here as the derivation artifact, and
it quantifies the coverage blocker exactly.

Decision needed from the operator: a freeze addendum (through review) ruling
on §4 below before the machinery work in §3 is worth sequencing.

## 1 · What the frozen run requires (restated from #917, no reinterpretation)

* Data: BEAR episodes 2017–2026 re-derived at run time from the production
  regime artifact, each with a 10-trading-day post-episode tail; episodes are
  the unit.
* Estimand: net return `R` and max drawdown `DD` of the SIMULATED BOOK under
  {current config} vs {amended config}, same fills, same costs, on the
  concatenated BEAR episode windows only.
* Arms: true regime series; 200-seed episode-block-permuted placebo; regime
  series lagged +5/+10/+20 days.
* Inference: episode-level block bootstrap (gap ≥ 20 trading days, 10,000
  resamples, seed 20260808); PASS = all five legs D1–D5.

## 2 · The derivation that DID run (committed)

`doc/research/data/2026-08-10-bear-exit-episode-derivation.py` labels every
trading day 2017-01-01..2026-08-07 (n = 2,412) by regime-artifact argmax using
the PRODUCTION functions imported from the renquant-pipeline sibling checkout
(`kernel.regime.gmm_predict` / `kernel.regime_hmm.hmm_predict`; those modules
are byte-identical between the umbrella production pin `e13cd3eb` and checkout
HEAD `69bf7116` `[VERIFIED — empty git diff, 2026-08-10]`), then groups
contiguous BEAR days into episodes with 10-trading-day tails. Outputs:
`…-regime-days.csv` (2,412 rows) + `…-episodes.csv` (22 rows); default mode
re-verifies every number below from the CSVs alone; 7 planted/null fixture
tests committed (`tests/test_bear_exit_episode_derivation.py`).

| series | BEAR days | episodes | longest | episodes sim-reachable (proper / aux) |
|---|---|---|---|---|
| `prod/spy-gmm-regime.json` (what production loads) | **75** | **5** | 41d (COVID) | **1 / 3** |
| `sim/spy-hmm-regime.json` (the only HMM on the machine) | 211 | 17 | 49d | 3 / 9 |

`[VERIFIED — committed CSVs; verify mode exit 0]`. The GMM row reproduces the
prereg's planning estimate (~77 days / ~4 episodes) almost exactly — the
2026-08-08 recon was evidently this artifact despite the prereg's "HMM" name.

The five production-artifact episodes: 2018-12-24..26 (2d), 2020-02-27..04-24
(41d), 2022-05-18 (1d), 2022-06-13..23 (8d), 2025-04-04..05-07 (23d).

## 3 · Why the confirmatory run is blocked (each leg verified)

**B1 — the amended arm's config keys are unread.** The two NEW keys
(`xs_panel_percentile_floor_by_regime`, `mu_sell_ceiling_by_regime`) do not
exist in the pipeline: `task_panel_conviction_xs.py:133-134` reads the scalar
keys only `[VERIFIED — renquant-pipeline HEAD 69bf7116]`.
(`min_holding_days_by_regime` IS already regime-keyed —
`soft_exit_guards.py:61` — only the two new keys block.) Prereg §4.2 requires
this as a normal renquant-pipeline PR + codex review + behaviour-invariance
regression. Different repo — deliberately NOT done in this PR.

**B2 — the simulator cannot consume a supplied regime series.** The book sim
(`renquant-backtesting wf_gate/sim_driver.py` → the 104 sim) computes regime
internally per day from SPY + the artifact through the `task_regime` stack;
no override/injection input exists anywhere in renquant-backtesting or
renquant-pipeline `[VERIFIED — grep for regime_override/regime_series/
forced_regime across both src trees: no injection site]`. D2 (200 permuted
series) and D4 (lagged series) are therefore inexpressible today. New
reviewed capability, renquant-backtesting.

**B3 — the frozen 2017–2026 window exceeds all existing sim-artifact
coverage.** The sim binds models through
`WalkForwardModelLoader.model_as_of(today)` ("latest retrain with
cutoff_date < today; raises if none"); the manifest carries 39 retrain
cutoffs 2024-01-01..2026-03-09, the earliest aux artifact set is
`sim/aux_2022-04-01`, and a single `walkforward_pre_2024` fallback exists
`[VERIFIED — sim/walkforward_manifest.json + artifacts/sim listing]`.
Measured against §2's episode list: ONE of five episodes (2025, 23 BEAR days)
sits inside properly-artifacted coverage; the two 2022 episodes (9 days)
only via the aux set; the 2018-12 and 2020-COVID episodes — **43 of 75 BEAR
days, 57%** — are beyond ANY existing sim artifacts. Running the covered
subset would silently narrow the frozen window; the freeze does not authorize
that, and with 57% of the sample in the excluded episodes it is materially
lossy — an operator-level scope ruling either way (backfill campaign for
2018–2022 artifact sets, or a reviewed freeze addendum).

**B4 — freeze-interpretation ruling needed before ANY episode list is
official.** The prereg says "production HMM", but production loads
`strategy_config.json::regime.gmm_artifact = prod/spy-gmm-regime.json`,
which is a legacy GMM (no `model_type`, no `transition_matrix`)
`[VERIFIED — pinned config + artifact keys]`; the only HMM on the machine is
`sim/spy-hmm-regime.json`. §2 shows the choice is material: 75/5 vs 211/17.
The same ruling should fix two underspecifications the derivation surfaced:
(a) tail overlap — under the HMM series, episode 8's tail (2022-06-09..06-23)
overlaps episode 9's BEAR days (concatenation would double-count); the GMM
series happens to have no overlap; (b) artifact-argmax vs the RESOLVED live
regime — argmax shows zero 2026 BEAR days while the live resolved series
(hard-BEAR overrides etc.) recorded BEAR dates in 2026 (orch#905 cites 27
live BEAR dates). §3's text names the artifact; the ruling should confirm
that reading applies to the sim arms too.

## 4 · Earliest runnable

Capability-gated, not calendar-gated. Sequence: (i) freeze addendum ruling on
B4 + overlap semantics; (ii) B1 pipeline PR; (iii) B2 simulator PR; (iv) B3
scope ruling (backfill vs addendum). After those, the run is compute only —
roughly 205 book sims (under §3's wording that the placebo shuffles what
"the amendment [is] keyed to" — i.e. the exit-rule keying only, a reading
the B4 ruling should confirm — 1 current-config sim suffices for all series:
the current config is regime-flat in every exit knob, so `R(current, series)`
is series-invariant `[DERIVED — §2 of the prereg: current values 60/60 +
scalars]`; plus 1 + 200 + 3 amended-arm sims), a hours-to-days local batch
under caffeinate.

## 5 · Pre-publication P0 sweep (open issues, this machinery)

* **orch#900** (holdings vs candidates written by different producers;
  candidates z-scale since 08-04) — TOUCHES the exit rule's live inputs. Its
  evidence is `rank_score`; whether `panel_score` (the exit task's operative
  field) shares the split is explicitly not established in the issue. Does
  not touch this derivation (SPY + regime artifacts only) and cannot overturn
  the reachability verdict's zero-fires DB count, but it is a mandatory
  pre-run check for the confirmatory sim and for any live proposal.
* **orch#799** (WF gate sims a phantom config — derive-config-from-prod lost
  fidelity) — TOUCHES the same simulator family the confirmatory run would
  use; must be fixed or shown inert for the exit-config A/B before the run.
* orch#905 / #805 / #941 / #942 — BEAR-side context (scarce live BEAR
  sample; served-model admissibility/freshness); none touches this
  derivation's machinery.

No open P0 touches the episode derivation itself.

## 6 · Task #21 status

Unchanged by this note: the prereg stays frozen and un-run; no arm was
evaluated; "the exit side stays as-is" remains the standing state until the
blockers clear and the run executes exactly as frozen. This note + the
committed derivation are the deliverable the freeze's §3 permits today.
