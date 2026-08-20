# The 60% vol cap: frozen SCREEN prereg (contaminated) + formation evidence

STATUS:   delivered — prereg + the committed formation bundle. **Docs and
          exploratory scripts only.** No config, no code path, no live
          surface, no run. The confirmatory executes only after this merges
          AND its runner is separately reviewed (the #990 sequencing).

WHAT:     The operator asked whether the "trades the same few names" complaint
          has a fixable cause, and explicitly asked me to determine the answer
          rather than hand back a question. Measured on the live 2026-08-19
          run: `RealizedVolGateTask` removes **29 of 113 candidates (26%)**
          before the panel scores anything, and the removed set is a coherent
          style bucket — AMAT(88%), AMD(79%), ANET(61%), APP(78%), COHR(113%)
          and 24 more. The drop count is growing: 24/108 (08-05) -> 26/111
          (08-11) -> 29/113 (08-19).

          FORMATION (exploratory, committed here): equal-weight forward return
          of the KEPT pool at seven caps, PIT 60d vol, non-overlapping blocks
          on the 2016-2026 panel. Both raw return AND a risk-adjusted proxy
          improve **monotonically** as the cap loosens toward ~100%. Paired on
          identical blocks, 100% vs 60%: **+0.0023, t=+2.18, 74/129 positive**
          at h=20; **+0.0071, t=+2.04, 22/42** at h=60.

          So the cap is not buying risk-adjustment — it is costing return and
          getting nothing measurable back at the POOL level.

          A METHOD ERROR I MADE AND CAUGHT, recorded because it reversed the
          reading: my first pass compared the kept cohort against the dropped
          cohort and concluded the cap was working. Those two runs used
          DIFFERENT block sets (one required a non-empty dropped cohort, the
          other did not), so the same 60% cap scored +0.416 in one and +0.302
          in the other. Re-run on ONE fixed block set chosen independently of
          any cap, the conclusion inverts. `sweep.py` carries that reasoning in
          its docstring so the artefact is not re-derived by the next reader.

WHY/DIR:  G-E (capital deployment). This is the first candidate cause of the
          narrow book that is (a) upstream of the model, (b) measurable, and
          (c) a one-line config change if it survives. But seven thresholds
          were swept with no multiplicity control on an estimand chosen after
          looking, so t≈2.1 is a LEAD, not a result — and a live capital gate
          does not move on a lead
          ([[speed-pressure-is-not-license-to-force-capital-gates]]). The
          prereg buys exactly one comparison (60% vs 100%) at the TRADED
          estimand, because the formation measured the pool mean and the book
          buys the top decile — a pool-level gain need not survive selection,
          and could reverse if the added names crowd out better picks.

EVIDENCE:
  artifact:      `doc/research/2026-08-20-volcap-confirmatory-prereg.md`;
                 formation bundle `doc/research/data/2026-08-20-volcap-formation/`
                 (`cohort_measure.py`, `sweep.py`, and both `.out` logs as run).
  prod or exp:   **exp** — worktree off main `3bc782ab`. Scripts read
                 `data/ohlcv/*/1d.parquet` and the pinned strategy config
                 READ-ONLY; nothing written outside the worktree. No run of the
                 confirmatory itself.
  existing data: measured, not assumed —
                 - the live funnel counts and the dropped-name list
                   [VERIFIED — logs/daily_104/2026-08-19.log]
                 - the drop-count trend across 08-05/08-11/08-19 [VERIFIED]
                 - the seven-cap sweep on one fixed block set, both horizons
                   [VERIFIED — committed .out logs]
  best-known?:   yes for a prereg. The bar (CI90 lower > 0 on both inference
                 legs) is INHERITED verbatim from model#75, not invented here;
                 the block geometry (28) is the count orch#1007 measured on the
                 identical grid, not re-derived to taste; the alternative arm is
                 the trend's ENDPOINT (100%) rather than the sweep's argmax,
                 precisely to avoid rewarding the multiplicity.
  scope:        docs + exploratory scripts. Deliberately does NOT touch
                `RealizedVolGateTask`, any config, or any job.

CORRECTION (2026-08-20, codex on orch#1017, before merge): the first draft let
           a PASS authorize a live config PR. **Withdrawn.** The formation chose
           the direction AND the arm from 2016-2026 outcomes, and the primary
           window sits inside that history; swapping the estimand from pool-mean
           to top-decile DGTW does not restore error control. No untouched
           historical holdout exists — the sweep consumed the panel. So the
           grade is now SCREEN, and the consequence is staged: FAIL closes the
           line, PASS reaches only a never-submits `shadow_cap100` lane whose
           PROSPECTIVE record is the untouched evidence. Contaminated evidence
           can kill a hypothesis it cannot license.

           Two further blockers from the same review, both fixed: the decisive
           statistic is now written as exact per-date arithmetic with an 80%
           DGTW-adjusted-coverage guard (27 tercile cells over 292 names let
           sparse dates silently degrade it into a raw-return spread), and the
           formation scripts now compute, print and ASSERT an input manifest
           (config sha + rolled-up per-ticker parquet shas) so a rerun on a
           refreshed live tree fails loudly instead of quietly disagreeing with
           the committed logs. Drift guard mutation-tested: corrupting the
           manifest exits 1 with INPUT DRIFT.

NEXT:      Runner PR (reusing the reviewed vol-switch refit engine), then ONE
           run, then a results PR. A PASS authorizes exactly one thing: the
           `shadow_cap100` lane. A production cap proposal needs that lane's own
           prospective record and is a separate, operator-gated step.

REVIEW:    codex (haorensjtu-dev). Design-review fixes on this are mine
           personally — the withdrawn first reading was my error.
