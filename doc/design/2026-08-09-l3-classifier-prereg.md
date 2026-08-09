# L3 classifier prereg — dataset-contract pointer (the prereg lives in renquant-model)

**Ownership (codex P1 on this PR):** the classifier preregistration — model
class, features, splits, embargo, placebo, metrics, PASS/KILL — is
model-factory research and lives in **renquant-model**:
`doc/design/2026-08-09-l3-classifier-prereg.md` (renquant-model PR #207).
This repo owns the dataset export only. This file records the dataset
contract that prereg consumes, and nothing else.

## The dataset contract (what this repo serves)

* **Producer:** `src/renquant_orchestrator/l3_candidate_dataset.py`
  (merged orch#928; orch#930 pending), schema `l3_candidate_dataset.v2`
  — v1 (merged #928) published the regime fields; v2 (orch#930) removes
  them for causality, with a fail-closed build assertion refusing any
  export in which a regime-derived column reappears. One row per
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
* **REGIME — EXCLUDED (r3; no causal score-time source exists):**
  regime-based features may not be consumed from this dataset at all.
  The producer trace refutes every consumer-side join:
  `live_state_snapshots` is documented as a close-of-run audit row
  ("what did live_state look like at the close of run R?", RenQuant
  `backtesting/renquant_104/kernel/persistence.py:189-205`) and
  `RunnerAdapter.commit()` writes `record_candidate_scores`
  (`adapters/runner.py:2179`) BEFORE `record_live_state_snapshot`
  (`adapters/runner.py:2342`), from post-run state `[VERIFIED — read
  this session]`. So the date-latest join leaks, timestamp inequality
  voids the field, and same-run identity (the r2 construction) proves
  ATTRIBUTION only — never availability at candidate-score time.
  orch#930 accordingly REMOVES the regime columns from the dataset,
  with a regression test pinning the exclusion. Readmission requires
  the producer to stamp regime/confidence into `candidate_scores` at
  scoring time (or an immutable score-time feature artifact) with
  score-time provenance and producer-side ordering tests — and a NEW
  dated prereg admitting the block. The renquant-model prereg (#207)
  freezes the 6 base features unconditionally: no regime block, no
  merge-state gate.
* **External test:** the 64 `trade_evaluations` rows `[VERIFIED — sqlite
  ro count, this session]`, consumed once-only per the prereg.
