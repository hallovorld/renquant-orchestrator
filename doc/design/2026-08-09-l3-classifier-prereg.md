# L3 classifier prereg — dataset-contract pointer (the prereg lives in renquant-model)

**Ownership (codex P1 on this PR):** the classifier preregistration — model
class, features, splits, embargo, placebo, metrics, PASS/KILL — is
model-factory research and lives in **renquant-model**:
`doc/design/2026-08-09-l3-classifier-prereg.md` (renquant-model PR #207).
This repo owns the dataset export only. This file records the dataset
contract that prereg consumes, and nothing else.

## The dataset contract (what this repo serves)

* **Producer:** `src/renquant_orchestrator/l3_candidate_dataset.py`
  (merged orch#928), schema `l3_candidate_dataset.v1`. One row per
  (run_date, ticker) from each date's widest candidate run (equal-width
  ties: latest created_at, then latest run_id — a total order); label =
  market forward return at the score date, `fwd_20d` primary (frozen),
  `fwd_60d` carried; no pairing, no lot ambiguity by construction.
* **Provenance as columns, never filter defaults:** `run_type`
  (live/sim), acted-ness (`selected`, `blocked_by`),
  `n_candidates_that_date` for explicit cross-section-width flooring.
* **Canonical manifest** `[VERIFIED — read-only module rebuild, this
  session: DB mode=ro, CSV + manifest under /tmp, figures from module
  stdout]`: 7,167 rows / 523 dates / 1,275 candidates without a forward
  row excluded-and-counted / selected 135 / base win rate 0.6307 /
  live 2,189 vs sim 4,978.
* **REGIME — causal join gated on orch#930:** the merged #928 join takes
  the run_date's latest `live_state_snapshots` row, which is NOT causal
  (a later same-day snapshot postdates the scoring — codex P0). orch#930
  replaces it with the join by RUN IDENTITY (the same run's snapshot,
  computed before that run scored its candidates), carrying
  `regime_source = same_run_snapshot | absent` and
  `regime_snapshot_created_at` per row. Under that join regime is
  honestly live-only: 2,184 of 2,189 live rows carry it, all 4,978 sim
  rows are `absent` `[VERIFIED — read-only rebuild on the orch#930 head,
  this session]`. **Regime-based features are excluded from the prereg
  unless orch#930 is merged when the training run starts** — the
  deterministic gate is frozen in the renquant-model prereg §2, not
  decided at run time.
* **External test:** the 64 `trade_evaluations` rows `[VERIFIED — sqlite
  ro count, this session]`, consumed once-only per the prereg.
