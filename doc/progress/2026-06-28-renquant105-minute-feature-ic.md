# renquant-105 minute-feature cross-sectional IC scan — corrected to an honest null   (PR #206)

STATUS:   delivered (READ-ONLY research gate; no promotion, no model change, no canonical write,
          no order, no live-tree git, no self-merge)

WHAT:     Tests whether minute-derived cross-sectional features carry **next-tradable,
          marginal-over-the-daily-factors** Spearman rank-IC on the renquant-104 universe at
          1d/3d (and 5d/20d), and whether any candidate survives a chronological OOS holdout,
          as a cheap gate BEFORE any heavy PatchTST-on-minute experiment. The first cut over-
          claimed a short-horizon edge ("vwap_dev 1d marginal IC +0.028 t=5.2, net Sharpe ~4");
          the #206 review identified three bugs (DST-contaminated RTH filter, optimistic same-
          close entry, invalid FWL partial). This PR fixes all six review items and the apparent
          edge **collapses to a clean null**. Adds `scripts/minute_rth.py` (shared DST-correct
          RTH + daily-factor helpers), rewrites `scripts/minute_feature_scan.py` and
          `scripts/minute_signal_costtest.py` to the corrected pipeline, and adds
          `tests/test_minute_feature_scan.py` (11 tests: DST premarket/afterhours filtering,
          half-day truncation, next-session label alignment / no-look-ahead, proper-FWL partial
          correlation).

WHY/DIR:  Cheap, falsifiable gate for the renquant-105 line of work (catch more / more-accurate
          multi-day trend signals). A NEGATIVE gate means we do NOT spend on a PatchTST-on-minute
          experiment in renquant-model. It also corrects an over-claim in the operator's most
          over-claim-prone area, restoring the "minute = noise" prior on this evidence rather than
          refuting it.

EVIDENCE: This PR makes a model/data conclusion (VERDICT = NULL), so the §4(b) block is required:

          artifact:      `/tmp/rq206f_out/` — `results.csv`, `marginal_placebo_floor.json`,
                         `oos_winners.json` (empty list), `manifest.json` (from
                         `scripts/minute_feature_scan.py --as-of 2026-06-25`); and
                         `costtest_summary.csv`, `costtest_perperiod.csv`,
                         `costtest_by_year.json`, `costtest_manifest.json` (from
                         `scripts/minute_signal_costtest.py --as-of 2026-06-25`).
          prod or exp:   experiment — TEMPORARY `/tmp` outputs, NOT committed, NOT a production
                         path. No `data/*.parquet`, no `strategy_config.json`, no live artifact/
                         state/WF corpus written. Reproducible cache-first WITHOUT Alpaca
                         credentials (`used_cache_without_credentials=true`); pinned `--as-of
                         2026-06-25` (no `datetime.now` in the math).
          existing data: this is a fresh scan of the minute panel; no prior committed
                         minute-feature IC/oos_mean_ic summary exists to compare against. The
                         only "prior" is the first cut's over-claim in this same PR, now retired.
                         Result is consistent in DIRECTION with the prior PEAD / fundamentals
                         nulls and with the canonical price-trend "no stable multi-day edge".
          best-known?:   N/A as a positive variant — there is no surviving variant. The corrected
                         marginal IC at 1d/3d is ~0 (vwap_dev 1d +0.0017 t=0.23; 3d +0.017
                         t=1.62), zero discovery winners (positive marg + clears floor + NW t≥3),
                         zero OOS survivors; market-neutral L/S is negative before cost at 1d and
                         not robust at 3d. This is the WORSE-than-floor (null) outcome, reported
                         as such.
          scope:         "this is `/tmp/rq206f_out` minute-feature scan + cost test, EXPERIMENT,
                         vs existing best — no committed minute-feature edge of record; the
                         corrected marginal IC ~0 does not clear the marginal placebo floor with
                         a positive sign and t≥3, so there is no edge to rank."

          Decomposition (vwap_dev 1d marginal IC, one fix at a time, full 626-date sample):
          OLD (fixed-UTC RTH + close-entry + invalid-FWL) +0.0279 (t=5.10, reproduces headline)
          -> +DST-correct RTH -0.0151 (t=-2.86, sign flips) -> +next-session entry +0.0020
          (t=0.36) -> +proper FWL +0.0004 (t=0.07, null). The old fixed UTC 13:30-21:00 filter
          admitted 290,917 bars (11.8%) of pre-market (EST) / after-hours (EDT) data that
          *created* the apparent signal. Local validation on this head: 11 passed
          (`tests/test_minute_feature_scan.py`); CI green.

NEXT:     none required — the gate is NEGATIVE. Do NOT spin up a PatchTST-on-minute experiment
          for renquant-105 multi-day OR for a short-horizon (1-3d) sleeve on this evidence; the
          "minute = noise" prior is not refuted. Finer 1-min bars would be a separate, heavier
          pull that must first overcome this clean null. Full methodology, the six fixes mapped
          to the review, and the per-cell tables are in
          `doc/research/2026-06-28-renquant105-minute-feature-ic.md`.

DO NOT merge / approve — opened for review by the counterpart agent.
