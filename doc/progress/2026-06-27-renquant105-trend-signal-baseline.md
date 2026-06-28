# renquant105 trend-signal — data-quality / provenance DIAGNOSTIC (verdict UNDETERMINED)

2026-06-27.

## STATUS
Read-only DIAGNOSTIC. **Bottleneck verdict = `UNDETERMINED`, UNCONDITIONALLY.** The script has
NO code path that flips the verdict or emits a model-vs-gate lever ranking from the synthetic
`(book_size, mu_floor)` decomposition (scorer-mixed, k-dependent, non-causal, not the deployed
path — more dates do NOT repair the estimand). A faithful verdict needs a future STATEFUL
production replay this script does not do; sufficiency is necessary, not sufficient. This PR
ships a data-quality / provenance diagnostic + the controlled-experiment design — **NOT** a lever
ranking and **NOT** a retraining recommendation (both withdrawn after review). No canonical path
written, no order placed, no git in the live tree.

## WHAT
renquant105's goal = catch MORE (recall) + MORE-ACCURATE (precision) multi-period TREND
signals. Question = MODEL vs GATE bottleneck. Measured READ-ONLY off the now-wired ledger
`data/runs.alpaca.db` (opened `mode=ro`, analysed against a `/tmp` copy; canonical mtime
2026-06-26 14:07 unchanged).

## WHY UNDETERMINED
The faithful LIVE ledger has only **9 aged `fwd_20d` dates** in one ~5-week window ⇒
**≈ 0.45 overlap-ratio** (a conservative DESCRIPTOR, ~1 independent observation, NOT power/N_eff);
`fwd_60d` = 0. The live `mu` cohort is a **scorer MIXTURE** (panel_ltr_xgboost-dominant; only 85
`hf_patchtst` rows ledger-wide), not PatchTST-primary. The SIM ledger is NOT faithful (NULL
scorer, non-PatchTST raw) ⇒ reference-only. But the deeper reason is structural: the synthetic
`(book_size, mu_floor)` killed-winner decomposition is scorer-mixed, k-dependent, non-causal, and
not the deployed path, so **no date count can turn it into a model-vs-gate ranking.** The script
now emits `bottleneck_verdict = UNDETERMINED` **unconditionally**, `lever_ranking = null`
**always**.

## ROUND-2 FIXES (4 blockers + 1 correctness — all accepted, no defence)
1. **Lever ranking REMOVED entirely.** Deleted the `live_ok`→`DETERMINED` branch and the
   `_lever_ranking()` builder; verdict UNDETERMINED unconditionally, `lever_ranking` always null.
   A "sufficient" overlap-ratio may at most unlock IC descriptives (`ic_descriptives_unlocked`),
   never a ranking. Sufficiency is necessary, not sufficient.
2. **Placebo preserves time dependence.** Replaced the within-date permutation (null too narrow;
   SIM ref printed p=0) with a dependence-preserving **blockwise circular date-shift** + finite-MC
   `(exceedances+1)/(B+1)` (p never 0; LIVE fwd_20d p≈0.33), run **only on the faithful LIVE
   cohort** (SIM placebo skipped — also kills the >1-min SIM-placebo runtime).
3. **overlap-ratio renamed** (`primary_overlap_ratio`, `--min-overlap-ratio`) — a conservative
   DESCRIPTOR, not power/N_eff; verdict stays UNDETERMINED. The real unblock wording — which
   **#201 must consume as the SAME criterion** — is emitted as `overlap_ratio_unblock_note`:
   conservative overlap-ratio now; pre-registered min-effect/power + empirical-dependence on a
   faithful homogeneous cohort as the real unblock (NO calendar date).
4. **Baselines implemented/distinguished.** Analytic random recall `k/n` (no MC noise) +
   current-selected-book recall implemented; market-sign kept; simple-momentum REMOVED from
   implemented (no trailing-price feature) and listed as a follow-up. Report emits
   `baselines_implemented` vs `baselines_followups_NOT_implemented`.
5. **(correctness) As-of filter.** `load()` filters candidate runs + manifest provenance + the
   session calendar to `run_date ≤ as_of`; manifest flag `runs_filtered_to_run_date_le_as_of`.

(Round-1 findings 1–8 — verdict gate, scorer-mixture labelling + deployed-selection summary,
killed-winner sensitivity grid, baselines, overlap descriptor, staleness de-confounding, on-cohort
placebo, immutable manifest — remain addressed; see the research doc.)

## EVIDENCE
- `scripts/research_trend_signal_baseline.py` run read-only over a `/tmp` copy of the ledger
  2026-06-27 ⇒ `bottleneck_verdict=UNDETERMINED`, `lever_ranking=None`,
  `runs_filtered_to_run_date_le_as_of=true`, max resolved run_date 2026-06-26 ≤ as_of; manifest
  sha256 `731d566f…`, schema_version 138, 351 resolved runs, 241 ambiguous dates rejected; LIVE
  placebo p∈{0.79,0.57,0.33} (never 0), SIM placebo not run.
- `tests/test_research_trend_signal_baseline.py` — 11/11 pass (incl. a test asserting the verdict
  is UNDETERMINED + `lever_ranking is None` EVEN at a large overlap-ratio and `_lever_ranking`
  no longer exists; the placebo p∈(0,1] run LIVE-only; analytic random recall; the as-of filter).

## NEXT
Do NOT prioritize retraining on this evidence. The script can never adjudicate model vs gate. Run
the controlled experiments in the research doc (pre-registered min-effect/power + empirical
dependence, faithful STATEFUL path replay, on-cohort placebo, controlled paired freshness
experiment, baseline+event suite) once the live ledger reaches the pre-registered min-effect/power
and a faithful PatchTST cohort is wired (#133 follow-through), THEN re-attempt a verdict.
