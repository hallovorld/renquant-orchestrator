# Progress: GOAL-6 Stage 1 panel — built, gated, one criterion NOT met

STATUS:   delivered as evidence; Stage-1 acceptance **NOT MET** on survivorship. The
          panel exists in scratch only and replaces nothing.

WHAT:     Records the Stage-1 build in the GOAL-6 design as a new §12, and corrects
          the design's own claim that breadth would also remove survivorship bias.
          Also opens the design itself for review — it had been pushed as a branch
          but never turned into a PR, so everything referencing it was citing an
          unreviewed document.

WHY/DIR:  Breadth is the lever three independent evaluations pointed at (the tail
          statistic leads IC every time and clears no bar — a power problem). The
          build tests whether that lever is actually available.

EVIDENCE: `[VERIFIED — build contract.json / gate report / survivorship_evidence.json]`
          1,427,575 rows, 850 tickers, 2016-01-04 → 2026-07-28, 46.5 s, recipe not
          forked. PIT assertion: 1,245,896 rows checked, 0 violations. Reproduction
          gate against a pre-fixed tolerance: per-date Spearman ρ = 1.000000 on rows
          and labels over the 142-name overlap × 2,594 dates, min 0.99848 across 167
          feature columns. Unlabeled rows retained with NaN, so the frontier reaches
          2026-07-28 against the incumbent's 2026-04-28 — the ~91-day structural lag
          behind RenQuant#541 is gone, making this the upstream fix that gate patch
          could not be. NOT MET: 0 of 23 probed known-delisted large caps present;
          universe monotone non-decreasing with ZERO exits in 10.3 years; the 830 list
          is a today-alive screen. Separately flagged: as-filed EDGAR ratios rank
          ρ ≈ 0.53 against production's served values, attributed to the
          as-filed-vs-v1 derivation rather than to this build. No IC/Sharpe claim is
          made, so the §4(b) triad does not apply.

NEXT:     Survivorship needs a delisting-inclusive ticker history plus bars for exited
          names — a separate purchase from breadth, and Stage 2 on this panel would
          inherit the bias. Three concrete asks land in renquant-base-data (R1 explicit
          universe config, R2 drop_unlabeled flag, R3 as-filed ratio serving). The
          ρ ≈ 0.53 ratio divergence deserves its own investigation.
