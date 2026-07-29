# Progress: GOAL-6 design + Stage-1 panel build (model capability)

STATUS:   design proposed for review, PLUS Stage-1 executed as evidence.
          Stage-1 acceptance **NOT MET** on survivorship; the panel exists in
          scratch only and replaces nothing. Operator decision requested on
          staging and on opening the MID workstream.

WHAT:     Adds `doc/research/2026-07-28-goal6-model-capability-design.md`
          (thesis, a per-lever value table, a 4-stage gated ladder, 5 ACs, and
          a repo-boundary table) plus the MID workstream
          `doc/memory/mid-term/model-capability.md`. Also records the Stage-1
          build as a new §12 in the design doc, and corrects the design's own
          claim that breadth would also remove survivorship bias. The design
          itself is opened for review here — it had been pushed as a branch
          but never turned into a PR, so everything referencing it was citing
          an unreviewed document.

WHY/DIR:  Operator directive after the PatchTST read: build experiments that
          actually yield a more capable model. The diagnosis is that our
          verdicts are unresolvable rather than negative, and two of the
          three causes cost nothing to fix. Ladder: Stage 0 re-baseline the
          ruler (free) → Stage 1 build the 830-name PIT panel with a stamped
          freshness contract → Stage 2 retrain the CERTIFIED top-decile
          recipe on breadth through the same frozen chain → Stage 3
          capacity/ensembling only once 0-2 make results interpretable.
          Breadth is the lever three independent evaluations pointed at (the
          tail statistic leads IC every time and clears no bar — a power
          problem); Stage 1 tests whether that lever is actually available.

EVIDENCE: `[VERIFIED — direct parquet/artifact reads, 2026-07-28]` training
          panel **142 tickers** 2016-01-04 → 2026-04-28 (353,548 rows); fund
          panel 292; SEC fundamentals coverage **830** — we train on 17% of
          the cross-section already owned and rebuilt as-filed
          (base-data#52). Fresh PatchTST val read (33,370 rows, 235 dates):
          IC +0.0430, naive t +5.39, **block-adjusted t +0.70**, within-date
          placebo −0.0008. Prior measured facts reused: tail spread t=2.92 vs
          IC t=1.15 (2026-07-24 capacity memo); intraday open→close net edge
          −6.4bp at IC 0.03 with σ_oc ≈ 152bp (Phase −1), which is why hourly
          data is explicitly out of scope. Arithmetic in the lever table
          (1/√N sampling-noise decomposition; 14 → 83 names in the top
          decile) is derived from those measurements and is labelled as
          projection, not measurement. No new IC/Sharpe claim is made by the
          design itself, so the §4(b) sanity triad applies to the Stage-0/
          Stage-1 results, not to the design.

          Stage 1 build `[VERIFIED — build contract.json / gate report /
          survivorship_evidence.json]`: 1,427,575 rows, 850 tickers,
          2016-01-04 → 2026-07-28, 46.5 s, recipe not forked. PIT assertion:
          1,245,896 rows checked, 0 violations. Reproduction gate against a
          pre-fixed tolerance: per-date Spearman ρ = 1.000000 on rows and
          labels over the 142-name overlap × 2,594 dates, min 0.99848 across
          167 feature columns. Unlabeled rows retained with NaN, so the
          frontier reaches 2026-07-28 against the incumbent's 2026-04-28 —
          the ~91-day structural lag behind RenQuant#541 is gone, making this
          the upstream fix that gate patch could not be. NOT MET: 0 of 23
          probed known-delisted large caps present; universe monotone
          non-decreasing with ZERO exits in 10.3 years; the 830 list is a
          today-alive screen. Separately flagged: as-filed EDGAR ratios rank
          ρ ≈ 0.53 against production's served values, attributed to the
          as-filed-vs-v1 derivation rather than to this build. No IC/Sharpe
          claim is made by Stage 1 either, so the §4(b) triad does not apply.

NEXT:     Operator confirms staging → Stage 0 runs under its own frozen
          prereg (zero new data, zero training). Survivorship needs a
          delisting-inclusive ticker history plus bars for exited names — a
          separate purchase from breadth, and Stage 2 on this panel would
          inherit the bias. Three concrete asks land in renquant-base-data
          (R1 explicit universe config, R2 drop_unlabeled flag, R3 as-filed
          ratio serving). The ρ ≈ 0.53 ratio divergence deserves its own
          investigation. Stage 1 is the first stage that writes an artifact,
          and it lands in renquant-base-data — not here.
