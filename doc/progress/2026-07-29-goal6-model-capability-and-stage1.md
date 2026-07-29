# Progress: GOAL-6 design — model-capability programme (design only)

STATUS:   POST-DECISION record. The workstream was confirmed by the operator on
          2026-07-28 ("这是新的goal！你来drive！", then "按你的推荐推进试试"), so
          this is not a pre-decision proposal (codex BLOCKER). Named parameters
          D2/D3/D4 remain genuinely open and are listed as open in the MID record —
          confirming a direction is not answering every parameter. Docs only, no
          execution claim in this
          PR.
          CORRECTION (per codex BLOCKER, 2026-07-29): an earlier version of
          this PR bundled an already-executed Stage-1 panel-build result
          (§12 of the design doc) into this same PR, while Stage 0 (model#86,
          this design's own stated prerequisite) is APPROVED but not yet
          MERGED. That violates the design's own stated gate ("no stage
          begins before its own frozen prereg is merged") and mixed a
          renquant-base-data build report into an orchestrator design
          document. Removed §12 and its progress-doc evidence entirely —
          the Stage-1 finding (including the genuine, self-falsifying result
          that breadth does NOT also fix survivorship bias) is real and
          valuable, but belongs in its own PR once Stage 0 lands and the
          evidence has a durable, reviewable location — following the same
          pattern as model#91's corpus-index for the PatchTST corpus, not a
          session-scratch citation.

WHAT:     Adds `doc/research/2026-07-28-goal6-model-capability-design.md`
          (thesis, a per-lever value table, a 4-stage gated ladder, 5 ACs, and
          a repo-boundary table) plus the MID workstream
          `doc/memory/mid-term/model-capability.md`. The design itself is
          opened for review here — it had been pushed as a branch but never
          turned into a PR, so everything referencing it was citing an
          unreviewed document.

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

EVIDENCE: artifact:      `doc/research/2026-07-28-goal6-model-capability-design.md`
          (design only, this PR) `[VERIFIED — this PR's diff]`.
           prod or exp:   design/experiment — no production artifact touched;
          the design's own reused facts are prior-measured
          `[VERIFIED — direct parquet/artifact reads, 2026-07-28]`: training
          panel 142 tickers 2016-01-04 → 2026-04-28 (353,548 rows); fund
          panel 292; SEC fundamentals coverage 830. Fresh PatchTST val read
          (33,370 rows, 235 dates): IC +0.0430, naive t +5.39, block-adjusted
          t +0.70, within-date placebo −0.0008. Prior measured facts reused:
          tail spread t=2.92 vs IC t=1.15 (2026-07-24 capacity memo);
          intraday open→close net edge −6.4bp at IC 0.03 with σ_oc ≈ 152bp
          (Phase −1), which is why hourly data is explicitly out of scope.
           existing data: arithmetic in the lever table (1/√N sampling-noise
          decomposition; 14 → 83 names in the top decile) is derived from
          those measurements and labelled as projection, not measurement.
          Stage 0's own results (model#86) are cited only where the design
          depends on them (§3 option C). model#86 has since MERGED
          (2026-07-29T08:10:49Z) `[VERIFIED — gh pr view 86]`, but only as
          the FROZEN PREREG — its merged diff is 3 doc files with zero
          results; every results commit pushed to that PR during review was
          explicitly stripped before merge as premature. The
          `goal6-stage0/results.json` this design cites predates that freeze
          and is not in any reviewable record, so §3 option C's verdict
          stays marked provisional pending an actual Stage-0 results PR run
          against the frozen prereg — #86 merging does not by itself confirm
          it, per this design's own stage-gate rule and R1-R5.
           best-known?:   n/a — this PR proposes a design; no model/statistic
          ranking claim is made.
           scope:         "this is a pre-execution design proposal for
          GOAL-6. No stage's results are claimed here — the §4(b) sanity
          triad applies to whichever results doc follows each stage's own
          run, not to this design."

NEXT:     Operator decision requested on opening the MID workstream and on
          the staged plan. Once Stage 0 (model#86) merges, Stage 1 runs
          under its own frozen prereg; its build already happened once
          (finding: breadth alone does NOT fix survivorship bias — a real,
          self-falsifying result worth keeping) but that result and its
          evidence belong in a separate, properly-scoped PR — in
          renquant-base-data per the repo-boundary table in §4, with a
          durable evidence reference (model#91's corpus-index is the
          template), not bundled into this design's opening PR.
