# Sector x Regime MoE — design draft (operator-directed new goal)

STATUS:    DESIGN DRAFT for review. Nothing deployed. Stage 0 is a BLOCKING
           measurement gate with a kill condition written before it runs.

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
                          (metadata.wf_gate_metadata.model_placebo_profile.per_regime)
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
             buys: BULL_CALM 136 / CHOPPY 9 / BULL_VOLATILE 9 / BEAR 0

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

NEXT:      1. Stage 0 — read-only, parallel-safe, touches no production surface.
              Per-(sector, regime) IC at all three shifts, `<5 names/date`
              reported UNESTIMABLE rather than 0.00.
           2. OPERATOR DECISION, design doc section 6: BEAR is the strongest
              measured regime and `entry_mode='blocked'` means its expert can
              never become a trade. Three coherent resolutions; my recommendation
              is routing BEAR skill to the EXIT side (BEAR already has 12 sells
              and 0 buys), which uses the signal without touching entry risk.
           3. Ownership on execution: model internals in `renquant-model`,
              harness in `renquant-backtesting`. NOT here — the orchestrator does
              not grow model internals (CLAUDE.md Hard Boundaries).
