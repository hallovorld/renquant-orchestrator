# C2 quality composite — frozen-spec measurement: precondition NOT MET; exploratory clean ≈ 0 (NON-VOTING)

STATUS:   EXPLORATORY research measurement (read-only; committed script + evidence +
          pytest positive-control fixture). Does NOT cast C2's formal M-SIG vote; C2
          remains OPEN (the C3/#268 pattern). Spec NOT altered; 4 deviations disclosed.
WHAT:     `scripts/msig_c2_quality.py` + `tests/test_msig_c2_quality.py` +
          `doc/research/evidence/2026-07-03-c2/*.json` +
          `doc/research/2026-07-03-msig-c2-quality.md`. Measures spec §1.2 (merged #243 r4):
          equal-weight z composite of {GP/A, −accruals, −net issuance}, acceptedDate+1td
          lagged, daily Spearman IC vs fwd_60d excess-SPY, shifted-label placebo, moving-
          block bootstrap (block=60, n_boot=2000, seeds 42/43/44), one-sided 98.33%
          Bonferroni-k=3 rule, bar 0.015 placebo-clean. Field mapping + all build choices
          frozen in `c2_frozen_addendum.json`, committed BEFORE measurement (M8 pattern).
WHY/DIR:  operator dispatch — measure C2, the second M-SIG channel, on the fresh Starter
          FMP harvest (2026-07-03); the spec's §2a order had C2 third/2026-Q4 — early run
          disclosed as a deviation.

RESULT:
```
coverage precondition (spec §1.2, ">=20% panel-coverage improvement over the
  fundamentals_scan free-tier baseline"): NOT MET — measured −0.02% (Starter 0.9396
  vs free-tier 0.9397 mean all-3-leg coverage of 134 names, 2017-07→2026-07). The
  free-tier panel was never thin for C2's legs (20y annual, 0 nulls, native
  acceptedDate); the premise behind C2's re-test is REFUTED, not just unmet.
exploratory harness (fwd_60d, n=2,241 daily dates 2017-02-09→2026-01-08):
  real +0.0355 / placebo +0.0360 / placebo-clean −0.0005; 98.33% one-sided bounds
  [−0.055, +0.048] (seeds agree) → mechanical INCONCLUSIVE, labeled NON-VOTING.
  BULL_CALM (binding diagnostic cell): clean +0.0009 (n=1,637). Strongest leg GP/A
  clean +0.0033 — ~5× below the 0.015 bar. fwd_20d clean +0.0032, same reading.
positive controls (S-REL R2): PC-A planted decaying effect (2× bar) detected — GO
  all seeds; PC-B persistent/survivorship tilt real +0.164 → clean −0.008 (placebo
  removes it by design); PC-C permuted composite not GO. NULL admissible.
PIT (r4 rule, fail-closed): 1,263/1,324 obs admissible via acceptedDate; 0 filingDate;
  0 EDGAR; 61 INADMISSIBLE — vendor-backfilled acceptedDate==period_end on pre-IPO
  (AFRM/APP/RBLX/COIN/SNOW/PLTR…) + foreign-issuer (ASML/COHR/MRVL) rows: the S9
  earnings_291 backfill trap caught at row level by the frozen anomaly guard.
  Lag sanity: median 49d, p5 29d, min 18d (no zero-lag survivors).
G106 (V4 corrected composition, #268): stays ≥2-of-4 with C3 pending; C2 OPEN —
  neither GO nor KILL nor an adjudicated MISS; INCONCLUSIVE at 2027-Q3 absent a PIT
  substrate. Reopening (R4): PIT accrual ≥600 clean dates, OR purchased as-filed
  vintage data, OR operator-amended protocol — new frozen prereg, never a tweak-rerun.
```

Scope discipline: one candidate PR (design rule 5); C3/C4 untouched; no config/order/
production change; no re-litigation of the settled fundamentals_scan NULL — this PR
measures the frozen coverage-delta hypothesis that was the ONLY sanctioned reopening
route, and closes it.

[VERIFIED — script run end-to-end against real read-only stores (exit 0), all numbers
read from regenerated committed JSONs; 7/7 tests pass (umbrella venv); freeze commit
precedes harness and evidence commits in-branch; `git log` confirms the spec file
untouched. No git operations were executed against any primary checkout; all work in a
scratchpad worktree on `research/msig-c2-quality`.]
