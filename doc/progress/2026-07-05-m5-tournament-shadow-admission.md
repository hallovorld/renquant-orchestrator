# M5 Tournament Retirement -- Shadow Admission Logger + Delta Report

**Date:** 2026-07-05
**PR:** (this PR)
**Status:** New feature (shadow/observability only)

## What

Shadow admission logger that records BOTH per-ticker tournament and panel
admission verdicts in parallel during each daily run.  After >= 20 sessions of
shadow data, the delta report script produces a migration readiness assessment.

## Why

The per-ticker tournament model selection system (`training/tournament.py`,
459 LOC) causes recurring freshness incidents and admission artifacts.  The
panel-based scorer (PatchTST) is already primary and fully operational.
`bypass_ticker_gate = true` already bypasses the per-ticker gates, but the
tournament code remains.  Before permanently retiring it, we need quantitative
evidence that the two admission paths produce equivalent (or panel-superior)
results.

## What was built

### Shadow Admission Logger (`tournament_shadow_admission.py`, ~350 LOC)

- Replays `ScoreBuyTask` + `ScoreThresholdTask` gate logic (the tournament
  path) against the per-ticker scores that are ALWAYS computed even in bypass
  mode.
- Records the panel path's observed admission (which tickers actually survived
  through `VetoWeakBuysTask` / `RegimeModelAdmissionTask`).
- Computes set agreement: agreed_admit, agreed_reject, tournament_only,
  panel_only, agreement_rate.
- Appends one JSON-lines record per run to
  `data/shadow/tournament_vs_panel_admission.jsonl`.
- Default OFF (must be enabled via `RQ_TOURNAMENT_SHADOW_ENABLED=1` or
  `enabled=True`).
- Fail-open: any error is caught and logged; pipeline continues normally.

### Delta Report (`scripts/tournament_delta_report.py`, ~90 LOC)

- Reads the JSONL shadow log and produces either human-readable text or JSON.
- Per-session breakdown: which tickers each path admits/rejects.
- Cross-session analysis: agreement rate stats, chronic disagreement tickers.
- Recommendation: READY (>= 95% agreement), LIKELY READY (>= 85%), or NOT
  READY (< 85%).
- Exit codes: 0 = ready, 1 = insufficient data, 2 = not ready.

### Tests (`test_tournament_shadow_admission.py`, 34 tests)

- Tournament gate replay: buy signal + high rank admitted; hold signal, low
  rank, NaN rank, None signal all rejected; missing ticker handled.
- Panel path observation: candidate admitted; blocked recorded with reason.
- Session agreement: full agreement, partial disagreement, panel-only
  disagreement.
- Persistence: append/read JSONL, multiple appends, empty file, malformed
  lines.
- Fail-open entry point: disabled by default, enabled writes correctly.
- Delta report: empty, insufficient, high/medium/low agreement
  recommendations; chronic disagreements; format output; date range.
- CLI: nonexistent file, JSON output, --last N filter.
- Serialization round-trip.

## Integration point

The caller (daily pipeline in the umbrella) invokes
`log_shadow_admission()` after the pipeline completes, passing:
- `ticker_scores`: from `TickerInferenceContext._raw_score`, `_rank_score`,
  `model_action`
- `panel_candidates`: tickers that survived into `ctx.candidates`
- `panel_blocked`: from `ctx._blocked_by_ticker`
- `min_model_score`: from `ctx.regime_params["min_model_score"]`

## Safety

- Writes only to `data/shadow/` (non-production path).
- No orders, no model changes, no config changes.
- No git operations on any live tree.
- Default OFF.

## Round 2 (codex review)

STATUS: fixed
WHAT: the readiness metric was whole-watchlist `agreement_rate`
(`(agreed_admit + agreed_reject) / n_watchlist`) — dominated by trivial
both-reject names, so it could report high agreement even when the two
paths materially disagreed on the small subset of names that actually
survive into admission territory. `scripts/tournament_delta_report.py`'s
exit code was also driven directly by this metric.
WHY-DIR: codex correctly identified this as an experiment-design gap, not
style — a metric that hides disagreement on the names that matter makes
the retirement decision too easy to pass, producing "a comforting number,
not a decision-grade signal."
EVIDENCE: added `conditional_agreement_rate` (Jaccard overlap of the two
paths' admitted sets, restricted to the admission-relevant subset — names
at least one path would admit), plus `admission_precision`/
`admission_recall`, to `SessionRecord` and aggregated in `DeltaReport`
(mean/median/min/max + `n_sessions_admission_relevant`). `recommendation`
and the CLI exit code now key off `mean_conditional_agreement_rate`, not
`mean_agreement_rate`; the whole-watchlist number is retained but relabeled
"CONTEXT ONLY — not the decision signal" in both the dataclass docstring
and `format_delta_report`'s output. Added `TestConditionalAgreement` (4
tests) proving: (a) a synthetic 18-both-reject + 2-admission-relevant
watchlist reports 90% whole-watchlist agreement but 0% conditional
agreement — the exact failure mode codex described; (b) full/no-overlap/
asymmetric admission sets compute the new fields correctly; plus 2
`DeltaReport`-level tests proving the aggregate recommendation flips from
"would-be READY" to "NOT READY" once driven by the corrected metric, and
that zero admission-relevant sessions correctly produces "CANNOT ASSESS"
rather than a silent default. All 6 new tests confirmed to fail against
the pre-fix code (`git stash` check) and pass after. Full suite 3017/3020
(3 pre-existing skips, no new failures); also regenerated
`data/strategy_snapshot.json` for an unrelated pre-existing stale-snapshot
gap (this PR's own module was never in the baseline).
NEXT: none — logger is decision-grade for the redundancy question once
>= 20 sessions of shadow data with admission activity accumulate.

## Round 3 (codex review)

STATUS: fixed
WHAT: the minimum-sample-size gate (`n >= 20`) was checked against TOTAL
sessions, then the recommendation/exit-code decision was computed on
`n_relevant` (admission-active sessions). A report could say READY with,
e.g., 25 total sessions but only 1-2 admission-relevant sessions — a
statistically meaningless sample dressed up by a large but irrelevant
denominator. The same gap existed independently in
`scripts/tournament_delta_report.py`'s exit-code logic (`n_sessions < 20`
check, with no corresponding `n_sessions_admission_relevant` check) — found
while re-verifying the automated decision path, not just the text
recommendation.
WHY-DIR: codex correctly identified that the effective sample size for this
experiment is the admission-relevant subset, not the calendar count — the
"no admission activity = unassessable" handling already built in round 2
needed to carry through to the ordinary (nonzero-but-still-too-small) case
too, via one consistent rule.
EVIDENCE: added `MIN_ADMISSION_RELEVANT_SESSIONS = 20` and a new
`elif n_relevant < MIN_ADMISSION_RELEVANT_SESSIONS` branch (between the
existing `n_relevant == 0` and `mean_conditional >= 0.95` branches) that
reports "INSUFFICIENT ADMISSION-RELEVANT SAMPLE" instead of falling through
to a READY/LIKELY READY/NOT READY verdict. Applied the identical fix to the
CLI's exit code (`report.n_sessions_admission_relevant < 20` -> exit 1).
Added `test_insufficient_admission_relevant_sample_despite_25_total_sessions`
(25 total sessions, 2 admission-relevant sessions agreeing perfectly --
would trigger READY pre-fix) and the equivalent CLI-level
`test_exit_code_insufficient_despite_25_total_sessions` (asserts exit code
1, not 0, on the same scenario end-to-end through `append_record`/
`read_records`/`main()`). Both confirmed to fail against the pre-fix code
(`git stash`/`git apply` on the isolated hunks) and pass after. Full module
suite 42/42; full repo suite 3016/3018 (2 pre-existing unrelated failures
in `test_bundle_consistency_ci_gate.py`, confirmed reproducing on clean
`origin/main`).
NEXT: none.
