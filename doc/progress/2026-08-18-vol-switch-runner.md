# Vol-switch confirmatory — the frozen RUNNER (ships reviewed, runs later)

STATUS:    runner + tests ONLY, per the merged frozen prereg
           `doc/research/2026-08-18-vol-switch-confirmatory-prereg.md` (#1001). No
           refits, no scoring, no outputs in this PR. The ONE run happens after this
           PR is reviewed and merged (prereg §6 freeze-then-review-then-run) — and the
           runner mechanically enforces that order: it refuses to execute unless its
           bytes match a freshly FETCHED origin/main (guard V2), and refuses ever to
           re-run (guard V1).

WHAT:      Commit `doc/research/data/2026-08-18-vol-switch-derivation.py` implementing
           prereg §2–§6 verbatim, plus `tests/test_vol_switch_runner.py` (50 synthetic
           tests). Runner shape:
           - Scoring (§4): the production recipe VERBATIM — served artifact identity
             asserted (config fingerprint sha256:f8fb2259b2bf1537, 172 feature_cols +
             norm kinds, fwd_60d_excess, best_iter=100), objective left AT PRODUCTION
             (rank:pairwise, ZERO delta — asserted, the no-delta complement of
             tail_q90's single-delta constructor). One 39-cutoff quarterly ladder
             2016-Q2..2025-Q4 (last SPY trading day of each quarter, count asserted);
             primary corpus dates asserted to resolve within the primary sub-ladder
             2016-Q2..2023-Q3 (30 cutoffs, V5). Expanding train window from
             2016-01-04, realized-labels-only per refit (max train date + 60td ≤ C,
             V7); at scoring date d the NEWEST refit with C + 60td ≤ d, asserted per
             date (V6). Machinery REUSED from the reviewed tail_q90 runner
             (#996/#999): 11 defs (`build_refit_calendar`, `refit_index_for_date`,
             `latest_realized_label_pos`, `ReadersLite`, `assert_one_shot`,
             `load_trainer_module`, `load_served_artifact`, `fit_booster`,
             `score_frame`, `_sha256`, `_assert`) copied VERBATIM, byte-identity
             ENFORCED by a committed parametrized test.
             `assert_runner_matches_main` is instead the universe-stage1 runner's
             fetch-first U11 guard (orch#997 lineage) copied VERBATIM, byte-identity
             enforced by its own committed test — the tail_q90 copy validates
             against a possibly-stale local origin/main ref (review round 1).
           - State (§2): ON ⇔ SPY 20-td realized vol (close-to-close, ddof=1,
             √252) > 0.135 STRICT (exactly 0.135 is OFF — tested); sensitivity
             variant = expanding upper-tercile, 504-obs warmup from 2016-01-04,
             pre-threshold days OFF fail-closed (reported, never decisive).
             Frozen-geometry recompute HARD-asserted, tolerance EXACT (V9): 1,697 td;
             821/808 ON days; 28 complete 60-td blocks; 19/19 ON-eligible, 18 both;
             8/8 ON-dominant; threshold first defined 2018-01-31; 340 weekly dates.
           - Estimand (§3): weekly (every 5th td) cross-sections over the FULL
             production panel (292 tickers asserted — no watchlist filter; the prereg
             universe); label = the panel's own fwd_60d_excess (per-date z-scored,
             SD units — the formation's unit); per-date top-decile (N = round(n/10))
             DGTW-adjusted spread per the capacity-memo instrument (STD60×ROC60×BETA60
             per-date terciles, 27 cells, self-excluded cell mean) + the prereg's
             ≥15/cell floor (below-floor names keep the RAW label, FLAGGED, fraction
             reported). Vol-matched (STD60-cohort) top-decile outcome computed as the
             §6 tilt control (reported only).
           - Decision (§5 verbatim): positive control (unconditional primary
             spread > 0) computed BEFORE any conditional read (V13; failure ⇒
             INVALID_INSTRUMENT, conditional stats never computed); P1 = the canon
             §1.2 dependence-robust CONJUNCTION on the 19 fixed-definition ON-eligible
             block means — NW(lag 1) small-sample t (df = N−1, one-sided 95% CI
             excludes 0) AND stationary block bootstrap (expected length 2, 10,000
             resamples, seed 0, one-sided 95% CI [q05,∞) excludes 0); a split is
             DISAGREEMENT and FAILS (pre-frozen); winsorized ±50% ON-spread ≥ 0 as a
             further anti-lottery conjunct; P2 = per-block paired ON−OFF difference
             (blocks with ≥15 days in EACH state), block-t ≥ 1.0; guards ≥15
             ON-eligible blocks AND ESS ≥ 6 (ρ̂₁ clipped at 0) else UNMEASURABLE;
             verdict mapping CONFIRMED/PARTIAL/REFUTED with the §5 consequence
             strings echoed verbatim into the output JSON.
           - Guards as hard assertions: one-shot (V1, tested on temp paths — the
             tail_q90 lesson: no repo-state "un-run" test that the ONE authorized run
             would break); byte-identity vs a freshly FETCHED origin/main (V2 = the
             U11 fetch-first guard; fetch failure fails CLOSED; fail-closed
             re-verified on this unmerged copy AFTER the port, and fetch-precedes-
             compare pinned by test); frozen geometry EXACT (V9, tested); per-date embargo
             (V6, boundary tested C+60=d usable / C+59 not); paired weekly-grid
             identity — state classification positional AND label lookup must agree
             at every scoring date (V10); snapshot edge — last grid date + 60td
             within the SPY calendar AND panel realized labels reach the last grid
             date (V11); ≥100 usable names per cross-section as an ASSERT, not a
             filter (V12); zero writes outside doc/research/data/ (V14).
           - Interpretation ledger (constructions the prereg names but does not pin
             to code — frozen IN the runner docstring, for THIS review, before the
             run): P2 pairing (per-block paired difference, both-state ≥15-day floor
             from the formation DEFINITIONS.md cell rule); DGTW per-date application
             of the memo's groupby; cell-floor semantics (flagged rows keep the raw
             label); winsor clip applied per-name BEFORE the spread (memo
             construction, ±0.50 SD); bootstrap CI convention q05 > 0; top-decile
             N = int(round(n/10)) (round-half-even pinned by test).

WHY/DIR:   Prereg #1001 §6 execution contract: the deterministic runner is committed
           AND REVIEWED (its own PR) BEFORE the one run. Build-directive-vs-prereg
           conflicts resolved in the MERGED prereg's favor (its CORRECTIONS section
           is the review-round-1 record): the directive still carried the first
           draft's `29 blocks / 19 ON-eligible under both / P1 iid block-t ≥ 2.0
           (df=18)`; the merged prereg froze 28 non-overlapping 60-td blocks, 19/19
           eligible with 18 under BOTH, and the NW+bootstrap conjunction replacing
           the iid rule (CORRECTIONS #1/#2/#3) — the runner implements the merged
           prereg, and the local data reproduces ITS numbers exactly. The directive's
           formation-dir name `2026-08-18-tail-switch-formation/` does not exist; the
           committed bundle is `doc/research/data/2026-08-18-tail-switch-exploratory/`
           (the prereg's own reference) — read and followed.

EVIDENCE:
  artifact:      the runner + tests + this doc. No run outputs. No live change.
  prod or exp:   neither — the runner ships un-run.
  existing data: [VERIFIED — read-only dry-check 2026-08-18, this machine] the frozen
                 geometry recomputes EXACTLY from data/ohlcv/SPY/1d.parquet: 1,697
                 corpus td, 821/808 ON days, 28 blocks, 19/19 eligible, 18 both, 8/8
                 dominant, expanding threshold first 2018-01-31; weekly grid 340;
                 every ON-eligible block carries ≥1 ON weekly cross-section (min 1,
                 max 12) so the frozen N=19 series is constructible; 4 weekly dates
                 fall in the dropped 17-td remainder. Ladder: 39 quarter-end cutoffs
                 2016-06-30..2025-12-31, primary sub-ladder 30; first scoreable date
                 2016-09-26 < corpus start. Panel: 292 tickers, 2016-01-04..
                 2026-05-07, STD60/ROC60/BETA60 100% coverage, all grid dates
                 present, ≥264 names per primary weekly date, realized labels
                 through 2026-05-07 ≥ last grid date 2026-03-27 (snapshot edge OK;
                 secondary corpus 2,323 td / 38 blocks). DGTW cell occupancy under
                 the ≥15/cell floor: 62–79% of names sit in qualifying cells on
                 probed dates — the floor flags a minority, instrument intact.
                 [VERIFIED — synthetic/read-only plumbing dry-validation, no
                 real-data training] artifact identity asserts pass; feat-col
                 derivation and sentiment-gate replay on the FULL panel equal the
                 artifact's stored contract; recomputed norm kinds equal the
                 artifact's feature_norm_kind at BOTH ladder extremes (2016-06-30,
                 17,095 rows — the smallest window; 2025-12-31, 691,203 rows);
                 synthetic fit/score round trip deterministic (identical booster
                 digests across repeat fits); [VERIFIED — re-run 2026-08-18 after the
                 U11 port] V2 gate fails closed on this unmerged copy (real fetch
                 succeeded, then refused: "runner is not on origin/main");
                 xgboost 2.1.4.
  best-known?:   yes — scoring machinery is the reviewed #996/#999 engine reused
                 byte-identically (enforced by test, the repo's reuse convention);
                 every §5 quantity routes through a pure function with synthetic
                 tests flipping each condition; the constructions the prereg left
                 unpinned are frozen in the runner text NOW, so this review — not
                 the run — is where they get contested.
  scope:         "ships the runner + tests; authorizes NOTHING else. After merge:
                 the ONE local run (minutes, $0), results as their own PR (prereg
                 §6). CONFIRMED would authorize only a shadow-first design PR;
                 activation stays operator-gated."

TESTS:     `tests/test_vol_switch_runner.py` — 54 passed [VERIFIED — pytest -q,
           2026-08-18, review-round-1 head] (vol-state classification
           incl. the 0.135 boundary and expanding warmup; block eligibility ≥15;
           DGTW self-excluded cell mean hand-computed + cell-floor flagging;
           top-decile spread + rounding pin; NW lag-1 hand-computed; stationary
           bootstrap determinism + constant-series exactness; ESS hand-computed +
           clip-at-0; P1 conjunction each-condition flips incl. DISAGREEMENT and the
           anti-lottery guard; P2 pass/fail/floor/exclusion/fail-closed; verdict
           mapping + precedence + consequence strings; embargo boundary C+60=d
           usable / C+59 not; 39-cutoff ladder; one-shot mechanism; 11-way
           byte-identity vs the tail_q90 runner + V2-guard byte-identity vs the
           universe-stage1 U11 copy + 4 V2 behavior tests (fetch failure fails
           closed, unmerged refusal, byte-drift refusal, fetch-precedes-compare +
           lineage pin); frozen-constant and frozen-geometry
           pins). Full suite run on this branch alongside.

NEXT:      codex review of THIS PR (the interpretation ledger is the review surface)
           → merge → the one run on the merged bytes → results PR (verdict first,
           ON/OFF block tables both corpora × both state definitions, realized
           ρ̂₁/ESS, tilt control, provenance) → on CONFIRMED/PARTIAL, the
           deployment-window design PR (operator-gated).

CORRECTIONS (review round 1, 2026-08-18):
  - codex MED: the shipped `assert_runner_matches_main` was the tail_q90 copy,
    which compares against whatever local ref is cached as origin/main (no
    fetch) — a stale local main could bless stale bytes at the one run. FIXED:
    ported the universe-stage1 runner's U11 fetch-first fail-closed guard
    VERBATIM (mandatory `git fetch origin main` before show/rev-parse; fetch
    failure fails CLOSED, orch#997). The reuse-identity test now enforces the
    guard's byte-identity vs the U11 copy (the other 11 defs stay pinned to
    tail_q90), plus 4 ported behavior tests. Figures updated above: 12→11
    tail_q90-pinned defs; tests 50→54; the "fail-closed verified" evidence
    line re-measured on the ported guard.
