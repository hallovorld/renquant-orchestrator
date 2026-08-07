# Sector x Regime MoE — design draft (operator-directed new goal)

STATUS:    DESIGN DRAFT for review. Nothing deployed. Stage 0 (data
           eligibility) and Stage 2 (the held-out incremental effect) are
           BLOCKING gates, each with a kill condition written before it runs.
           Design/progress content review is clean (codex re-read at
           `74f655d2`).

           VISIBLE CORRECTION 7 (2026-08-07, this commit). The paragraph below
           is superseded, kept for the record rather than silently dropped
           (LONG ledger #10). It previously read: "merge is blocked only by a
           repo-wide CI failure unrelated to this diff, tracked at orch#898
           ... Not fixed in this PR." orch#898's root cause (`.github/workflows/ci.yml`
           checked out `renquant-pipeline` with no `ref:`, so the GOAL-3
           export-resolution record's `VERIFIED-AT` pin raced a moving HEAD)
           was fixed by orch#903 (pins the checkout, re-derives the record at
           the pinned sha), merged to `main` at `a0e90866`. This branch is now
           rebased onto that `main`, so the CI failure this note describes no
           longer applies — separately from that, this rebase also replaces a
           merge commit an out-of-scope reviewer identity (`haorensjtu-dev`)
           had pushed directly onto this PR-owner branch (merging orch#896's
           branch in, in an attempt to pull the same CI fix transitively);
           per `CLAUDE.md` §3.0 a PR branch carries exactly one GitHub commit
           identity, so the branch was rebuilt from `main` as clean
           single-identity history instead of kept as pushed.

WHAT:      `doc/design/2026-08-07-sector-regime-moe.md` — a hierarchical mixture
           (soft regime gate, shrunk sector-GROUP experts as additive
           corrections on the pooled base), staged 0-4, each stage carrying its
           own kill condition, plus the operator decision the design cannot make
           for itself.

WHY/DIR:   Operator directive 2026-08-07: "根据不同 sector 不同 regime 的 moe
           模型 ... 给我一个可行的设计". Two measurements decide the shape:

           (1) Per-sector skill has NEVER been measured. `wf_gate_metadata`
               contains ZERO keys matching `sector`. The proposal's premise is
               unverified, so Stage 0 measures it before anything is built.

           (2) A flat 13x4 grid is not estimable. 15 of 52 cells hold under 500
               ticker-days; `telecom` has ONE ticker so its per-date
               cross-sectional IC is undefined on every date, and `commodity`
               has two. Hence groups (>=8 names) rather than raw sectors, and
               additive corrections on a shared base so a thin cell degrades to
               today's behaviour instead of producing confident garbage.

EVIDENCE:  artifact:      panel-ltr.alpha158_fund.weekly_20260706T230931Z.staging.json
                          (metadata.wf_gate_metadata.model_placebo_profile.per_regime,
                          .trade_buy_regime_counts_total, .trade_sell_regime_counts_total)
                          + pinned strategy_config.json + config_fingerprint_fields.sector_map
           prod or exp:   experiment — staging WF artifact, not a prod artifact
           existing data: `wf_gate_metadata` contains ZERO keys matching `sector`;
                          per-sector skill has never been measured before this doc
           best-known?:   first correctly-read per-regime IC from this artifact;
                          supersedes orch#805 and this doc's own two earlier
                          summaries, which misread the key structure and reported
                          BEAR's point estimate rather than its range (see the
                          VISIBLE CORRECTION note below)
           scope:         this is panel-ltr.alpha158_fund staging artifact,
                          experiment, vs existing best: no per-sector or
                          leakage-corrected per-regime measurement exists yet —
                          this is the first

           per-regime, all three shift multiples
           `[VERIFIED — panel-ltr.alpha158_fund.weekly_20260706T230931Z.staging.json,
             metadata.wf_gate_metadata.model_placebo_profile.per_regime, 2026-08-07]`
             BEAR          real 0.353/0.351/0.361  placebo +0.108/+0.016/-0.122
                           genuine +0.245/+0.335/+0.483   n_dates 50
             BULL_CALM     genuine -0.027/-0.029/-0.068   n_dates 363
             BULL_VOLATILE genuine -0.032/-0.080/+0.269   n_dates 11
             CHOPPY        genuine -0.001/-0.041/+0.006   n_dates 28

           entry policy `[VERIFIED — pinned strategy_config.json]`
             BEAR.entry_mode='blocked', max_position_pct=0, cash_reserve_pct=1

           trade counts by regime `[VERIFIED —
             panel-ltr.alpha158_fund.weekly_20260706T230931Z.staging.json,
             metadata.wf_gate_metadata.trade_buy_regime_counts_total /
             trade_sell_regime_counts_total, 2026-08-07]`
             buys:  BULL_CALM 136 / CHOPPY 9 / BULL_VOLATILE 9 — no BEAR key
                    in `trade_buy_regime_counts_total`; the producer
                    (renquant-backtesting `src/renquant_backtesting/wf_gate/
                    runner.py:1058-1064 _merge_trade_counts`) emits a key
                    only for regimes with >=1 observed buy row, so the
                    omission means zero buys, not a stored `0`
                    `[DERIVED — same artifact, key-omission semantics,
                    2026-08-07]`
             sells: CHOPPY 36 / BULL_CALM 20 / BEAR 12 / BULL_VOLATILE 8

           sector map `[VERIFIED — config_fingerprint_fields.sector_map]`
             144 tickers -> 13 sectors; telecom 1, commodity 2, real_estate 3
           cell arithmetic `[DERIVED — sector counts x regime days]`
             15 of 52 cells < 500 ticker-days

           VISIBLE CORRECTION. orch#805 and my own two summaries quoted BEAR's
           `genuine_ic` as the single number +0.335. `per_regime` is keyed by
           shift multiple FIRST; I had read `n_dates`/`genuine_ic` directly off
           the regime node and got `None` — the recurring "invented key returns a
           silent empty" failure. Reading the real structure shows BEAR's REAL ic
           is stable (0.353/0.351/0.361) while the PLACEBO swings +0.108 ->
           -0.122, and a negative placebo ADDS to `genuine = real - placebo`. On
           ~50 dates that is more plausibly sampling noise than real negative
           leakage. BEAR must be reported as a RANGE (+0.245..+0.483) whose width
           is owed to leakage correction, not to signal. The qualitative claim
           survives at the conservative end; the point estimate does not.
           BULL_VOLATILE (n=11, placebo -0.195 at 3x flipping -0.080 to +0.269)
           can support no conclusion at all.

           VISIBLE CORRECTION 2 (codex on orch#897, accepted in full). The first
           revision formed sector groups by clustering sector-level residual
           returns and then used the resulting between-group IC spread as the
           evidence that a sector effect exists — selecting the grouping on the
           same series that evaluates it. Preregistering the clustering RULE does
           not fix this; the rule can carve groups that maximise apparent spread,
           and the spread is then read as proof the groups are real. Group
           formation is now NESTED AND TEMPORAL (cluster on training dates only,
           inside each walk-forward fold, frozen before the embargoed validation
           dates are touched), and the kill condition is a block-bootstrap
           fold-level CI on the paired held-out increment
           `IC(regime x group) - IC(regime-only)`, compared against the
           bootstrap's own quantiles rather than a hardcoded critical value on a
           single-digit fold count. The original spread-vs-noise-band condition
           is WITHDRAWN.

           VISIBLE CORRECTION 3 (codex on orch#897, accepted in full). The
           nested-temporal Stage-0 gate as first written killed only when the
           fold-level CI for `Δ` covered zero, which let a CI sitting entirely
           below zero — sector specialization reliably WORSENING held-out IC —
           pass the gate under a literal "does it cover zero" reading. The
           gate is now directional: proceed to Stage 2 only if the CI's lower
           bound is greater than zero; KILL if the CI covers zero OR sits
           entirely below zero. Applied identically to the Stage 2 kill
           condition and the falsification section (design doc §5, §7).

           VISIBLE CORRECTION 4 (codex on orch#897, accepted in full). The
           "trade counts by regime" evidence block tagged `BEAR 0` buys as
           `[VERIFIED — ...trade_buy_regime_counts_total...]`, which reads as
           if the artifact literally stores a `0` for BEAR. It does not: the
           producer (`_merge_trade_counts`, renquant-backtesting
           `src/renquant_backtesting/wf_gate/runner.py:1058-1064`) builds the
           map only from regimes with >=1 observed buy row, so BEAR is
           simply absent — a zero bucket represented by key omission, not an
           explicit stored zero. Both this doc and the design doc now state
           "no BEAR key in `trade_buy_regime_counts_total`" and tag the
           zero-buys inference `[DERIVED — same artifact, key-omission
           semantics, 2026-08-07]` rather than `VERIFIED`. The underlying
           conclusion (BEAR has 12 sells and effectively zero buys) is
           unchanged; only the provenance tag is corrected.

           VISIBLE CORRECTION 5 (codex on orch#897, accepted in full). A
           read-only feasibility probe of the live runs DB
           `[VERIFIED — sqlite3 read-only on
           /Users/renhao/git/github/RenQuant/data/runs.alpaca.db, 2026-08-07]`
           found `candidate_scores` (243,902 rows, `sector`/`regime` columns
           present) joinable to `ticker_forward_returns` without new plumbing
           — but the live regime split cannot carry this design's premise:
           live BEAR is 27 dates vs. the WF replay's 73 (live BULL_VOLATILE
           30 vs. 147, CHOPPY 21 vs. 42, BULL_CALM 546 vs. 489 — 88% live vs.
           65% WF-replay share). This was first surfaced only as a PR comment,
           which is not a committed record; Stage 0's data source is now
           stated as binding in the design doc (§5): the WF replay's persisted
           served matrix (artifact family
           `panel-ltr.alpha158_fund.weekly_20260706T230931Z.staging.json`,
           `hmm_regime_counts_total`) is the required source, the live DB is
           explicitly excluded as a substitute, and a live-sample
           BULL_CALM-only check (where `ticker_forward_returns` is a ready
           label source) is named as a separate question with its own
           preregistration, not a Stage-0 shortcut.

           VISIBLE CORRECTION 6 (codex P2 on orch#897, accepted in full). Stage
           0 was labelled "BLOCKING, no modelling" but its kill condition was
           the full nested-fold clustering + fit-both-arms + paired held-out Δ
           procedure — the core model experiment, duplicating what Stages 1-2
           already describe (§4.1(b) already attributes this exact procedure to
           "Stage-2 minus Stage-1"). A team reading only the Stage-0 heading
           could implement the whole MoE believing it was a read-only premise
           check. Design doc §5 is split: Stage 0 keeps only the descriptive
           per-(sector, regime) table and a data-eligibility kill condition
           (can any sector form an estimable group in any regime — no
           clustering or fitting); the nested/temporal group formation, the
           regime-only vs. regime×group fit, the paired `Δ_fold` statistic, the
           block bootstrap, and the directional kill rule all move to Stage 2,
           evaluated jointly with Stage 1 as its control arm. §7's falsification
           bullet and §8's "Stage 0 is read-only" note are now consistent with
           the split (Stage 0 is genuinely read-only again; Stages 1-2 are
           where `renquant-model` fitting happens, per §8's existing ownership
           note).

NEXT:      1. Stage 0 — read-only, descriptive, no modelling, parallel-safe,
              touches no production surface. The per-(sector, regime) table at
              all three shifts, `<5 names/date` reported UNESTIMABLE rather
              than 0.00 — but that table is DIAGNOSTIC, and Stage 0's own kill
              condition is a data-eligibility check (can any sector form an
              estimable group in any regime), not a judgement on whether a
              sector effect exists. Data source is the WF replay path only
              (VISIBLE CORRECTION 5) — the live DB is excluded.
           1a. Stage 1–2 — this is where model fitting and the fold-level CI on
              the held-out incremental effect happen (VISIBLE CORRECTION 6);
              nothing about effect existence may be promoted on Stage 0's
              descriptive table alone.
           2. OPERATOR DECISION, design doc section 6: BEAR is the strongest
              measured regime and `entry_mode='blocked'` means its expert can
              never become a trade. Three coherent resolutions; my recommendation
              is routing BEAR skill to the EXIT side (BEAR already has 12 sells
              and no buys — no BEAR key in `trade_buy_regime_counts_total`, see
              "trade counts by regime" evidence above), which uses the signal
              without touching entry risk.
           3. Ownership on execution: model internals in `renquant-model`,
              harness in `renquant-backtesting`. NOT here — the orchestrator does
              not grow model internals (CLAUDE.md Hard Boundaries).
