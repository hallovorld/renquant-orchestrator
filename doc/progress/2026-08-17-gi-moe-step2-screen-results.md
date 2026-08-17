# G-I MoE step 2 — screen results (the one authorized run)

STATUS:    results of the ONE authorized execution of the frozen triage spec
           orch#987. Docs + committed derivation artifacts only — NO code /
           config / live-surface change.

WHAT:      Executed doc/research/2026-08-17-gi-moe-step2-ic-screen-spec.md
           exactly once, in an isolated worktree, runner committed BEFORE the
           run (spec §7). Verdicts under the frozen h=20 rule (Δ>0 AND
           block-t≥1.0 AND >50% positive blocks): **quality_gp NOT FLAGGED**
           (Δ=+0.00417, t=1.443, 51.7% pos); **high52w FLAGGED** (t=0.528,
           49.4% pos); **lowbeta FLAGGED** (t=0.911). 359/359 cross-sections
           kept (zero floor drops), 89/89 and 29/29 blocks with data. ρ vs
           momentum lanes: high52w 0.44/0.51, lowbeta ≈0, quality_gp ≈0.03–0.09;
           multifactor_core column = NAMED GAP (no reachable historical series
           without the panel pipeline). Deviation reported: the frozen
           every-5th-day RULE yields 359 cross-sections, not the spec's derived
           358 — rule governs, nothing dropped, |n−358|≤1 asserted.

WHY/DIR:   G-I MoE #984 §5 step 2 — triage the three step-1 emitters
           (model#227) before the §5b prereg batch. FLAGGED = deprioritised +
           point-in-time rerun required before any kill; NOT FLAGGED = proceeds
           to the §5b manifest freeze. The screen neither kills nor admits.

EVIDENCE:
  artifact:      doc/research/2026-08-17-gi-moe-step2-screen-results.md +
                 doc/research/data/2026-08-17-gi-moe-screen-{derivation.py,
                 results.json,ic-series.csv}. The runner commit precedes the
                 results commit on this branch (freeze-then-run, auditable in
                 history); results.json carries sha256 pins of every input
                 (SPY + 146 OHLCV parquets digest-of-digests, sec fundamentals
                 store, watchlist config d93d28c5…, model pin 74c22647 verified
                 = renquant-model main HEAD).
  prod or exp:   exp — isolated worktree research/gi-moe-step2-screen-results;
                 read-only inputs (OHLCV, sec_fundamentals_daily, strategy-104
                 golden config, ticker_sectors); outputs land ONLY in
                 doc/research/data/; no live tree, no data/ write path, no
                 production artifact touched.
  existing data: yes — zero new data (spec §2): SPY calendar 2019-01-14..
                 2026-03-02 (1,792 trading days), current 145-name live
                 watchlist, upstream gross_profitability with its PIT
                 available_at column (available_at ≤ date asserted on every
                 served row).
  best-known?:   yes for this corpus — deterministic re-runnable script, no
                 randomness, all frozen params imported from the emitters' own
                 v0 modules (never re-declared); frozen-guard assertions all
                 passed (grid ≈358 → 359 reported; ≥50 pairs on every kept
                 date; exactly 89/29 complete blocks; identical genuine/placebo
                 date sets). Known limits are the spec's own: survivorship-
                 tilted universe (why FLAGGED ≠ killed) and no multiplicity
                 correction (exploratory triage by design).
  scope:         a triage record under orch#987 §1. Authorizes NO kill, NO
                 admission, NO deploy, NO re-run. quality_gp advances only into
                 the #984 §5b frozen-prereg path; high52w/lowbeta wait on a
                 point-in-time rerun. The h=60 tables are informational only.

NEXT:      quality_gp (the one NOT-FLAGGED emitter) → the #984 §5b frozen-prereg
           manifest; high52w + lowbeta → deprioritised pending a point-in-time
           rerun before any kill decision; multifactor_core's missing historical
           series remains a NAMED GAP until the panel pipeline can serve one.
           No code/config/live change follows from this PR.
