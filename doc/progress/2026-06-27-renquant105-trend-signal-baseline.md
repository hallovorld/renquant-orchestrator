# renquant105 trend-signal — data-quality / provenance DIAGNOSTIC (verdict UNDETERMINED)

2026-06-27.

## STATUS
Read-only DIAGNOSTIC. **Bottleneck verdict = `UNDETERMINED`.** The decision ledger cannot yet
adjudicate MODEL vs GATE for the primary trend horizon, so this PR ships a data-quality /
provenance diagnostic + the controlled-experiment design — **NOT** a lever ranking and **NOT**
a retraining recommendation (both withdrawn after review). No canonical path written, no order
placed, no git in the live tree.

## WHAT
renquant105's goal = catch MORE (recall) + MORE-ACCURATE (precision) multi-period TREND
signals. Question = MODEL vs GATE bottleneck. Measured READ-ONLY off the now-wired ledger
`data/runs.alpaca.db` (opened `mode=ro`, analysed against a `/tmp` copy; canonical mtime
2026-06-26 14:07 unchanged).

## WHY UNDETERMINED
The faithful LIVE ledger has only **9 aged `fwd_20d` dates** in one ~5-week window ⇒
**≈ 0.45 effective non-overlapping blocks** (~1 independent observation); `fwd_60d` = 0. The
live `mu` cohort is a **scorer MIXTURE** (panel_ltr_xgboost-dominant; only 85 `hf_patchtst`
rows ledger-wide), not PatchTST-primary. The SIM ledger is NOT faithful (NULL scorer,
non-PatchTST raw) ⇒ reference-only. ≈1 effective block of a mixed cohort cannot support a
model-vs-gate ranking, an IC significance claim, or a retraining call. The script now **gates
the conclusion**: `bottleneck_verdict = UNDETERMINED`, `lever_ranking = null`, and the report
consumes the gate.

## REVIEW FIXES (8/8)
1. Insufficiency gates the conclusion — verdict UNDETERMINED, no lever ranking emitted.
2. Relabelled "scorer-mixture vs one synthetic threshold"; deployed `selected`/`blocked_by`
   summarized (real path: ~1.2 selected/date, 50% zero, blockers `veto:*/kelly_zero/qp_*`).
3. Killed-winner split reported across a (book,floor) sensitivity grid — ratio ≈ [0.91, 2.80],
   reverses at book=12/floor=0.06; labelled k-dependent + non-causal.
4. Naive baselines added inline (random recall, market-sign precision); model edge is small
   once baselined; richer baselines + trend-event definition listed as REQUIRED follow-ups.
5. Sufficiency is now in EFFECTIVE non-overlapping blocks (`--min-eff-blocks`), not raw dates.
6. Causal staleness claim REMOVED; flagged `DESCRIPTIVE_ONLY_confounded`; controlled paired
   freshness experiment designed in the research doc.
7. Stopped citing the foreign 0.036 floor; added an on-cohort shuffled-label placebo
   (`--placebo-shuffles`) with a p-value vs the placebo distribution.
8. Immutable manifest (DB sha256, schema_version, resolved run_ids, scorer mix, deterministic
   tie rejection, CLI args, session calendar); every denominator/window explicitly labelled
   (all-live vs aged-9 subset no longer conflated).

## EVIDENCE
- `scripts/research_trend_signal_baseline.py` run read-only over the ledger 2026-06-27 ~16:27
  PDT ⇒ `bottleneck_verdict=UNDETERMINED`, `lever_ranking=None`; manifest sha256
  `731d566f…`, schema_version 138, 351 resolved runs, 235 ambiguous dates rejected.
- `tests/test_research_trend_signal_baseline.py` — 8/8 pass (incl. a test asserting
  insufficiency ⇒ UNDETERMINED + no lever ranking, and effective-block sufficiency).

## NEXT
Do NOT prioritize retraining on this evidence. Run the controlled experiments in the research
doc (N_eff power pre-registration, faithful path replay, on-cohort placebo, controlled paired
freshness experiment, baseline+event suite) once the live ledger reaches the pre-registered
N_eff and a faithful PatchTST cohort is wired (#133 follow-through), THEN re-attempt a verdict.
