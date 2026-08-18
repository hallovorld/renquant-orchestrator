# Universe-extension Stage 1 triage — frozen spec (doc only)

STATUS:    frozen experiment spec for review. Docs only — the run happens only after
           this merges AND the committed runner is separately reviewed.

WHAT:      Commit `doc/research/2026-08-18-universe-stage1-triage-spec.md`: the Stage-1
           TRIAGE (never kill/admit — survivor-only snapshot + the #987
           withdrawn-convention ruling) of the structural thesis that the account's
           unused capacity edge lives down-cap. Frozen: arms (A = ~609-name
           full-recipe extension scored by the SERVED pin verbatim — pure transfer;
           W = watchlist positive control, mandatory, void-on-failure; B =
           alpha158-only exploratory, never pooled), corpus 2021-07..2026-02-13 weekly
           (zero new data, zero writes to any live store), estimand = DGTW-adjusted
           top-decile spread at h=60 with 2h-lag paired placebo + RS-5 bucket costs
           per name, effective sample counted first (19 blocks, triage-grade), the
           4-condition pass bar incl. the transfer prediction (A ≥ W in a costable
           bucket), $1-5M-ADV excluded (uncostable), one-shot, runner
           reviewed-before-run.

WHY/DIR:   Operator-directed 2026-08-18 ("我要真正的alpha"). The 08-18 feasibility
           study: extension corpus already on disk (~609 full-recipe / ~1,955
           alpha158-only), $0 data cost, minutes of scoring compute; adverse priors
           (E34 NO-GO, RS-5) declared — neither tested the tail statistic, which is
           the gap this fills.

EVIDENCE:
  artifact:      the spec + this doc. No code, no run, no data fetch, no live change.
  prod or exp:   neither — spec only.
  existing data: [VERIFIED — 08-18 feasibility memo, measured in-session] inventory
                 (2,790 tickers w/ 1d.parquet; filter cascade → 2,058/1,758; 627
                 fund-covered → 609 with ≥5y OHLCV; ADV/price quantiles), coverage by
                 feature family (100%/30%/11%/0.6%), snapshot survivor-only (zero
                 delisted), RS-5 cost buckets + E34/RS-5 priors. The t=+2.92 figure is
                 cited from its COMMITTED source (renquant-model
                 doc/research/2026-07-24-capacity-and-power-reconciliation.md §7 +
                 its evidence dir) and is DOWNGRADED throughout to a single-run,
                 winsorized-fragile (t=1.70), not-independently-reproduced instrument
                 choice — a hypothesis about where power lives, not a proven fact
                 (codex round 1).
  best-known?:   yes — transfer-not-retrain isolates the thesis from E34's
                 retrain-dilution mode; the positive control makes instrument failure
                 distinguishable from a real transfer fail; costs are charged with the
                 only frozen down-cap cost instrument the house has; triage semantics
                 honor the survivorship ruling in BOTH directions; zero-writes +
                 isolated scratch honors the production-inputs hard rule.
  scope:         "freezes Stage 1. Authorizes, AFTER merge + a reviewed runner PR: the
                 one-time isolated corpus build (~1h) + the ONE scoring run (minutes,
                 served pin), results as a separate PR. A PASS authorizes ONLY the
                 Stage-2 PIT program proposal (own spend ask, ~$37-66/mo trial-first);
                 nothing here changes serving, universes, or data stores."

TESTS:     none — doc-only PR.

NEXT:      codex review → runner PR (reviewed BEFORE execution) → the one run →
           results PR → (on PASS) Stage-2 PIT proposal to the operator.
