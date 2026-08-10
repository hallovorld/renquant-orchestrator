# Extension corpus built + bit-for-bit invariance vs the frozen corpus

STATUS:    measurement; read-only on all repo/production surfaces; the
           rebuilt parquet lives in session scratch only. Task #26 /
           orch#939 step.

WHAT:      doc/research/2026-08-09-extension-corpus-invariance.md — a
           two-line scratch-copy patch of the alpha158 builder
           (committed hash-pinned as data/2026-08-09-extension-builder.patch)
           extends feature coverage from 2026-05-07 to 2026-08-07; the
           committed checker proves the frozen corpus's 726,128 rows
           reproduce EXACTLY on all 70 FEATURES (max abs diff 0.0, zero
           NaN mismatches, primary keys asserted unique, corpus sha256
           asserted against the harness pin). LABELS are NOT fully
           invariant: 144/726,128 rows differ (≤1.68pp), all on the
           single boundary date 2026-05-07 — vintage sensitivity of the
           final day's forward window, profiled in the committed report;
           downstream label reuse must exclude that date (the frozen
           corpus stays the v2 verdict's label authority).

WHY/DIR:   Live scoring starts 05-20; the frozen corpus ends 05-07 —
           replay vs served had zero shared dates (orch#937/#938). The
           extension window (9,953 rows, 63 trading days, 292 tickers)
           closes that structural gap with the SAME measurement process,
           so the #26 full-width comparison and the Stage-C extension
           corpus (model#215 §2b, date>05-07 only) both become
           constructible. Historical label-gap resurrections (8,616
           rows ≤05-07) are excluded by construction.

EVIDENCE:  artifact:      doc/research/data/2026-08-09-overlap-invariance-check.py
                          (CLI-arg paths, machine-independent) +
                          …-overlap-invariance-report.json
                          [VERIFIED — run 2026-08-09, exit 0]
           prod or exp:   experiment; nothing under RenQuant written
           existing data: frozen corpus sha 870f68eb… (pin ast-read from
                          renquant-model frozen harness); builder
                          RenQuant/scripts/build_alpha158_qlib.py:448
                          (the dropna) and :97 (REPO_ROOT)
           best-known?:   yes — note §4 states what is NOT done (no
                          scores, no comparison, fwd_60d covers only 432
                          extension rows)
           scope:         research note + checker + report JSON only

TESTS:     make test not run — docs+research-data-only change (no code
           surface of this repo touched); the checker itself ran exit 0.

NEXT:      score the extension window with the replay-side model, join
           `ticker_daily_state`, publish the full-width overlap table
           (#26 acceptance surface).
