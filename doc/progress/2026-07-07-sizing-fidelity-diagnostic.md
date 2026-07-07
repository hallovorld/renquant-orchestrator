# 2026-07-07 — Sizing-fidelity diagnostic + cash-drag root-cause data

**PR**: add `scripts/check_sizing_fidelity.py`

## What

Diagnostic script that measures whole-share quantization error and
decomposes candidate blocking reasons from `runs.alpaca.db`. Provides the
Phase 1 (S-FRAC) baseline measurement.

## Round 2 (codex review) — measurement was overstated, now corrected

STATUS: fixed
WHAT: codex found two real measurement gaps: (1) the block-breakdown query
wasn't restricted to canonical daily FULL runs — could mix partial/monitor/
non-canonical rows into the `81.6%` headline; (2) the fractional-shares
conclusion (`0.8%`) was based only on a `blocked_by = 'size_insufficient_cash'`
string count, missing whole-share quantization loss that surfaces under a
different label or no label at all.
WHY-DIR: an overstated or understated number here could misdirect real
engineering priority (this diagnostic is the evidentiary basis for PR #408's
prioritization design), so both gaps needed a real fix, not a caveat.
EVIDENCE:
- Canonical-run filtering now reuses `tc_measurement._canonical_daily_runs`
  (one genuine completed run per `run_date`, deduped by `max(created_at)`,
  requiring ≥80 `candidate_scores` rows) instead of a raw `run_date >= ...`
  join that could admit partial/monitor rows.
- The quantization-loss metric compares each candidate's intended weight
  (`kelly_target_pct`) against its actually-executed weight (0.0 if no trade
  was placed), for every candidate that **survived to the sizing stage** —
  reusing `tc_measurement`'s own admission taxonomy
  (`_PRE_SELECTION_BLOCKERS` excluded, `_SIZING_FAILURES`/
  `_SELECTED_SUBMITTED` or no label included) rather than a single string
  match. This catches quantization loss regardless of which (if any)
  sizing-stage label got attached.
- Two design choices were investigated against the real DB directly, not
  assumed: `selected=1` was considered as the "candidate the pipeline chose
  to buy" criterion but rejected — it is essentially unpopulated on live
  runs after 2026-05-22 (a pipeline change stopped setting it). `qp_target_w`
  was also considered and rejected: on live runs it and `selected=1`
  essentially never co-occur (0 of ~232k selected=1 rows have it populated —
  a disjoint code path). `kelly_target_pct` + the taxonomy-based
  survived-to-sizing filter is what remains reliable on current data.
- Cross-check against the existing TC/ETR methodology
  (`transfer_coefficient.py`, which also needs both `kelly_target_pct` and
  `qp_target_w`) was attempted but is **not currently possible**: that
  dataset tops out at `run_date=2026-06-01` for the same `qp_target_w`
  reason above, so it cannot validate this diagnostic's 30-day window. This
  is a pre-existing gap in the TC measurement's live-data coverage, not
  something this PR introduces — flagged here as a related follow-up, out
  of scope for this fix.
- Reproducible evidence artifact:
  `doc/research/evidence/2026-07-07-sizing-fidelity/evidence.json` (the
  canonical run list, per-candidate gap rows, and aggregate stats — anyone
  can regenerate it via `check_sizing_fidelity.py --evidence-out ...`).
- 5 new tests: canonical-run dedup/partial-run exclusion, quantization gap
  capture under a non-`size_insufficient_cash` label, admission-stage
  exclusion, no-gap-when-fully-deployed, and evidence-artifact writing. All
  confirmed to fail against the pre-fix code (an `ImportError` — the
  pre-fix module has no canonical-run helper at all) and pass after. Full
  suite 3173/3176 (no new failures).

## Corrected headline numbers (30-day window, canonical runs only)

**These differ meaningfully from the original claim below — the corrected
block breakdown is directionally similar (mixing partial runs didn't change
the ranking much), but the fractional-shares number is now understood
differently: `size_insufficient_cash` is a LOWER BOUND, not the full
picture.**

| Metric | Original (uncorrected) | Corrected |
|---|---|---|
| Canonical runs (30d) | not computed | **10** |
| #1 blocker | `veto:rank_score_below_floor` 81.6% | `veto_weak_buys` **81.4%** (817 total blocks, canonical runs only — close to the original, mixing partial runs didn't move this much) |
| `size_insufficient_cash` (labeled) | 0.8% | **0.9%** of block breakdown (unchanged in substance — this label alone is still small) |
| Whole-share quantization loss (new metric) | not measured | **66** candidates survived to sizing across 10 canonical runs; **64** (97.0%) had executed < intended; mean gap per candidate = **5.7%** of portfolio value; mean gap per canonical run = **37.7%** of that day's portfolio (sum across runs = 3.77, NOT a single-day percentage) |
| Of the quantization-loss rows | not measured | **15 of top 20** gaps have NO blocked_by label at all — invisible to the label-count metric entirely |

**Revised implication**: the labeled `size_insufficient_cash` count (0.9%) is
still small, but it undercounts the real whole-share quantization effect —
97% of candidates that reach the sizing stage end up under-deployed relative
to their intended weight, and most of that (15/20 in the sampled gaps) carries
no explicit block label the old metric could have found. The `81.4%`
`veto_weak_buys` finding survives the canonical-run correction largely
intact, so PR #408's prioritization question (rank-floor calibration vs.
fractional shares) should be evaluated against BOTH corrected numbers, not
just the rank-floor share — the quantization loss is real and larger than
the original 0.8% figure implied, even though it doesn't overturn the
veto-floor finding as the largest single block category.

## Scope

- New diagnostic script only, no behavior changes
- Exit 0 = healthy, exit 1 = problems found
