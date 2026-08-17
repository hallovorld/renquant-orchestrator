# G-I MoE step 2 — corrected runner + the pilot run it supersedes

STATUS:    the runner's paired-cross-section defect is FIXED here; the run it
           produced is DEMOTED to an exploratory pilot and advances nothing.
           **The authorized one-shot run has not happened** and its budget is
           NOT spent. Docs + derivation artifacts only — no code, no config,
           no live surface. Revised 2026-08-17 after codex's HIGH on orch#990.

WHAT:      Two things, and the second is why the first exists.

           1. `doc/research/data/2026-08-17-gi-moe-screen-derivation.py` —
              genuine and placebo ICs are now computed on ONE shared
              cross-section (`paired_spearman_ic`): intersect finite genuine
              score, finite placebo score AND finite label first, apply
              `NAMES_PER_DATE_FLOOR=50` to that shared set, correlate both legs
              against the label over exactly those names. G7's documentation is
              rewritten to describe what the code does; the identity assertion
              now checks shared TICKERS, not just equal dates or equal counts.
              Per-leg counts survive as telemetry
              (`n_pairs_genuine_leg_only`, `n_pairs_placebo_leg_only`,
              `coverage_gap_genuine_minus_placebo`) so the size of the confound
              is visible in the output instead of inferred.

           2. `doc/research/2026-08-17-gi-moe-step2-screen-results.md` — demoted
              from "final one-shot result" to "exploratory pilot, WITHDRAWN as a
              verdict". `quality_gp` is NOT promoted; the table is a pilot
              outcome, not a verdict.

           **Deliberately NOT done: re-running.** Spec §7 step 2 requires the
           runner committed AND REVIEWED before execution. Running the corrected
           runner in this PR would repeat exactly the sequencing error that
           produced the defect. The re-run belongs in a separate PR, after this
           runner is reviewed.

WHY/DIR:   codex, HIGH: *"the runner does not implement a paired
           genuine-minus-placebo cross-section. G7 enforces common dates only;
           the code computes spearman_ic(gen_s, label) and spearman_ic(pla_s,
           label) on two independently filtered name sets, then subtracts
           them."*

           The mechanism is not incidental. The placebo IS the genuine score
           lagged 2h trading days, so a name short of history at the lagged date
           drops out of the placebo leg while surviving in the genuine leg. The
           coverage difference is therefore lag-dependent BY CONSTRUCTION, and
           it lands directly on Δ = mean(genuine IC) − mean(placebo IC) — the
           single quantity the §5 rule decides on. A composition artifact wearing
           the shape of the estimand.

           The runner's own G7 header claimed both series were "computed on
           exactly that common set". They were not; only the dates were common.
           An assertion in a docstring is not a measurement.

EVIDENCE:
  artifact:      the derivation script (paired computation + identity assertion
                 + corrected G7 header) and the results doc's demotion
  prod or exp:   exploratory. Nothing runs, nothing deploys, no candidate
                 advances, no live surface touched.
  existing data: the pilot's own outputs are retained unchanged under
                 `doc/research/data/` — they remain genuine evidence about the
                 PIPELINE (it ran end to end, guards fired, corpus and pins
                 resolved) while being withdrawn as evidence about the
                 CANDIDATES.
  best-known?:   yes at the reduced claim. The correction is structural rather
                 than a threshold tweak: it changes WHICH cross-section the two
                 legs are measured over, so the pilot's Δ values cannot be
                 patched into correctness and are not carried forward.
  scope:         this PR fixes the runner and withdraws the verdicts. It does
                 NOT re-run, does NOT advance `quality_gp`, does NOT consume the
                 spec's one-shot budget, and does NOT change the frozen rule,
                 corpus, estimand or thresholds.

VERIFICATION:
  `python3 -c "import ast; ast.parse(open(<runner>).read())"` → parses.
  No execution: re-running before this runner is reviewed is precisely the step
  §7 forbids, and is the reason the defect reached published numbers.

  The claim that could not be checked, stated plainly: the pilot asserted "the
  runner was committed BEFORE the run" on the strength of commit order within a
  single branch. That is author-controlled, and the results JSON carries no
  `runner_sha256`, so nothing tied those numbers to a specific script version.
  Adding that digest is the cheap fix that makes the next run's ordering claim
  self-supporting.

NEXT:      (1) this runner reviewed — on its own, before any execution;
           (2) add `runner_sha256` to the results JSON so ordering becomes
               checkable rather than asserted;
           (3) THEN the authorized one-shot run, as a separate results PR;
           (4) only after that does any candidate move in the #984 §5b queue.

HANDOVER:  opened by a concurrent Claude session that has since ended (socket
           gone, no longer listed). I picked it up rather than leave a
           CHANGES_REQUESTED PR unowned. I am also the author of spec §7, the
           clause codex cites — his review is the second, independent finding
           that its sequencing requirement was load-bearing rather than
           ceremonial.
