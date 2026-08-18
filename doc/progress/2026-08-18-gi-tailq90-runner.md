# G-I `tail_q90_60d` — the frozen screen RUNNER (ships reviewed, runs later)

STATUS:    runner + tests ONLY, per the merged frozen spec
           `doc/research/2026-08-18-gi-tailq90-screen-spec.md` (#994). No training on
           real data, no scoring, no outputs in this PR. The ONE run happens after this
           PR is reviewed and merged (spec §6 freeze-then-review-then-run) — and the
           runner mechanically enforces that order: it refuses to execute unless its
           bytes match origin/main (guard T2), and refuses ever to re-run (guard T1).

WHAT:      Commit `doc/research/data/2026-08-18-gi-tailq90-derivation.py` implementing
           spec §2–§6 verbatim, plus `tests/test_tailq90_runner.py` (33 synthetic
           tests). Runner shape:
           - Candidate (§2): XGBoost with the served artifact's recipe VERBATIM
             (172 feature_cols + per-col norm kinds + params + fwd_60d_excess +
             best_iter=100, all asserted; config fingerprint sha256:f8fb2259b2bf1537
             asserted) with EXACTLY ONE delta — objective → reg:quantileerror,
             quantile_alpha 0.90 — built by an asserted single-delta constructor (T5).
             xgboost quantileerror support is HARD-asserted by a behavioral 1-round
             probe, fail-closed (T3).
           - PIT calendar (§3): 31 quarterly refit cutoffs (last SPY trading day of
             each quarter 2018-Q2..2025-Q4, count asserted), expanding train window
             from 2016-01-04, realized-labels-only asserted per refit (max train date
             + 60 trading days ≤ C, T8); at scoring date d the NEWEST refit with
             C + 60 trading days ≤ d, asserted per date, no gap-filling (T7).
             Fixed seed (the artifact's), no early stopping, no search.
           - Training-data path (§3, feasibility resolved): the production training
             frame `data/alpha158_291_fundamental_dataset.parquet` read-only + the
             production trainer's OWN helpers (scripts/train_production_model.py,
             imported read-only): panel-space transform, per-cutoff fund robust-z
             recompute, sentiment trained_zeroing regime replay. Recomputed norm kinds
             asserted == the artifact's; the replayed sentiment-gate contract asserted
             == the artifact's stored contract (config drift fails closed) (T9).
           - Screen (§4): corpus/estimand verbatim #987 + the #990 pairing correction,
             REUSED from the merged corrected runner — `build_grid`, `close_panel`,
             `paired_spearman_ic`, `spearman_ic`, `MomReaders`, `_assert`, `_sha256`
             copied VERBATIM and byte-identity ENFORCED by a committed test against
             `2026-08-17-gi-moe-screen-derivation.py`. Weekly 2019-01-14..2026-03-02;
             **h=60 PRIMARY** (29 blocks, strict-majority min-blocks floor 15,
             fail-closed insufficient_blocks) per the spec §4 REVISION; h=20
             informational (89 blocks), NO verdict field. NOT FLAGGED iff Δ>0 AND
             block-t ≥ 1.0 AND >50% blocks-with-data positive, at h=60.
           - ρ section (§5): tail_q90 vs mom_slow_12m / mom_fast via the momentum
             machinery on common dates (≥50 common names), plus the declared
             same-cutoffs rank:pairwise refit as the core ρ reference (params VERBATIM,
             no delta; ρ only, never screened) — included in the runner, EXECUTED only
             at run time (T14).
           - Guards as hard assertions: refit-count=31 (T6); embargo per date (T7);
             paired-cross-section identity G7-class (T11); date/block counts —
             |n−358|≤1, 89/29 complete blocks exactly (T10/T12); artifact-fingerprint
             (T4); one-shot marker — refuses to run if any output exists, outputs only
             to doc/research/data/ at run time, THIS PR emits none (T1, tested);
             emitter-independence — renquant_model_factors asserted absent from
             sys.modules (T15).

WHY/DIR:   Spec #994 §6 execution contract: the deterministic runner is committed AND
           REVIEWED (its own PR) BEFORE the run — the sequencing the emitter-family
           pilot (#990) lacked. Prompt-vs-spec conflict resolved in the spec's favor:
           the build directive carried the PRE-REVISION `h=20 primary / 89 blocks`
           wording; the MERGED spec §4 (codex 2×HIGH revision) makes h=60 primary /
           h=20 informational, and the runner implements the merged spec.

EVIDENCE:
  artifact:      the runner + tests + this doc. No run outputs (a committed test
                 asserts none exist on this branch). No live change.
  prod or exp:   neither — the runner ships un-run.
  existing data: [VERIFIED] feasibility probed read-only 2026-08-18 on this machine:
                 panel parquet 726,128 rows / 292 tickers / 2016-01-04..2026-05-07,
                 all 172 artifact feature_cols present; watchlist 145 with 3 names
                 absent from the panel (CRWV, RKLB, SPCX — recorded by the runner,
                 never silently dropped); SPY calendar yields exactly 31 quarter-end
                 cutoffs 2018-06-29..2025-12-31 and a 359-date weekly grid; xgboost
                 2.1.4 trains reg:quantileerror (behavioral probe passed).
                 [VERIFIED] run-time plumbing dry-validated read-only with a SYNTHETIC
                 training frame (no real-data training): production-helper imports,
                 regime-map replay, per-cutoff normalization (kinds == artifact's),
                 sentiment-gate contract == artifact's stored contract, fit/score
                 round-trip both objectives, deterministic booster digests across
                 identical refits, T2 fail-closed confirmed on the unmerged copy.
                 [VERIFIED] deterministic placebo-gap expectation: at h=60 the first
                 9 weekly placebo dates precede the first refit's maturity
                 (2018-06-29 + 60td) and are dropped WITH a counted, asserted reason;
                 h=20 has zero such drops. Corpus grid dates are all scoreable.
  best-known?:   yes — reuse over rewrite everywhere the spec inherits (#987/#990
                 machinery byte-identity-tested; production trainer helpers imported,
                 not re-implemented, so "everything else verbatim" is structural
                 rather than transcribed); every frozen number is asserted, not
                 assumed; every fail path is fail-closed. One declared implementation
                 pin beyond the spec text: rows are stable-sorted before the DMatrix
                 build (production uses an unstable quicksort; row order within a
                 date is loss-invariant but feeds the subsample RNG, so the stable
                 order pins byte-reproducibility — digest-verified).
  scope:         "ships the reviewed runner. Authorizes, AFTER merge: the ONE
                 deterministic local run (31 expanding refits x 2 objectives +
                 scoring + ρ, read-only inputs, ~15–20 min estimated from the
                 measured 0.4–0.5 s tiny-fit calibration at 10–20k rows x 172 cols x
                 100 rounds, run under caffeinate), results as their own PR: verdict
                 table first, refit ledger (per-cutoff train-row counts + model
                 digests), ρ section, every number provenance-tagged. Nothing else:
                 no admission, no serving change, no deploy, no new data source."

TESTS:     tests/test_tailq90_runner.py — 33 passed (umbrella venv): refit-calendar
           generation (count=31, quarter-end last-trading-day property re-derived
           independently, fail-closed on truncated calendar); embargo boundaries
           (C+60=d exactly usable, C+59 not; newest-refit selection; none before
           maturity); realized-label boundary mirror; single-delta construction
           (verbatim-except-objective vs a fixture artifact params dict; rejects
           wrong base objective / pre-existing quantile_alpha / missing seed / empty;
           input not mutated); triage rule (each criterion flips the verdict at its
           exact boundary; insufficient_blocks fail-closed; reason names every failed
           criterion); reused-machinery byte-identity vs the moe runner (7 defs);
           functional G7 pairing checks (shared-set identity, floor→NaN); one-shot
           marker (passes clean, refuses on existing output, and the branch itself
           carries no outputs); frozen-constant pins. No market data, no xgboost
           training in tests.

NEXT:      codex review of this PR → merge → the ONE run on the merged copy (T2
           enforces byte-identity with origin/main) → results PR per spec §6.
