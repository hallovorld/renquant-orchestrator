# L2-S design: sector awareness returns, at allocation granularity

STATUS:    design proposal only; no backtest has run; every threshold in
           the doc is frozen before any output exists.

WHAT:      doc/design/2026-08-09-l2-sector-conditional-allocation.md —
           sector-conditional expert allocation: per-sector Hedge paths on
           sector-book returns, shrunk toward the merged global L2 path by
           frozen width tiers (m_s ∈ {0.5, 0.67, 1.0} `[ASSUMED — frozen in the
           design]`); six eligible sectors (≥14 names) covering 73.0% of
           the universe `[DERIVED — pinned sector-map sums]`; four frozen
           comparison books; a frozen ADOPT/RECORD-ONLY rule; a
           sector-permutation placebo ×200 `[ASSUMED — frozen in the
           design]`.

WHY/DIR:   Operator 2026-08-09: the three-layer machine lost sector
           awareness and that loss is unacceptable — the original MoE
           vision was sector-first. The selection-level routing table died
           on measurement (#910–#913, IC on 8–26 names = noise); this
           design restores sector awareness at ALLOCATION granularity,
           where each decision rests on a 541-day book-return series
           `[VERIFIED — #926 committed CSV span]` instead of a daily
           thin-cross-section IC `[VERIFIED — #913 record]`. Both of the
           operator's original shapes are endpoints of the shrinkage dial.

EVIDENCE:  artifact:      pinned sector map (strategy_config sha
                          43cbb9b2…) [VERIFIED — read this session]:
                          159 names / 15 sectors; six ≥14-name sectors
                          hold 116 names = 73.0%. Prior-line numbers
                          cited from merged records (#913 kill n=278 `[VERIFIED — #913 record]`;
                          #926 Hedge +45.9%/1.33 `[VERIFIED — #926
                          verifier output]`; #927 net panel +22.1%/0.49,
                          churn drags 5.5–13.1pp `[VERIFIED — #927
                          verifier output]`).
           prod or exp:   design doc only; nothing executes until it
                          merges and the backtest PR runs under §4.
           existing data: the #926 replay arms + sector map suffice for
                          the whole backtest — no new data purchase.
           best-known?:   yes — the design states its own weakest joints
                          (mixture step has no fresh regret theorem;
                          thin-book concentration; regime out of scope).
           scope:         design + evaluation contract; the backtest is
                          the next PR; shadow needs its own grant.

TESTS:     none — prose contract; its test is §4's zero-live-choice
           executability (the L3 lesson: every fold/guard/tie-break
           constant is IN the doc, not in a runner).

NEXT:      the design is already MERGED (#934). This follow-up PR is a
           provenance/record repair only and authorizes NO execution. The
           §4 backtest runs only as its own separately reviewed PR
           executing the frozen contract (committed artifacts + verifier;
           ADOPT-for-shadow vs RECORD-ONLY reported exactly as frozen).
           No shadow or live action is implied by this PR or by the
           merged design.

REVIEW r1: codex CHANGES_REQUESTED (2026-08-09), two MED — both hidden
           live choices, i.e. exactly the doc's own §4 executability
           standard. Fixed in the design doc, no mechanism change:
           1. shortfall state frozen (§3): a sector×arm book short of k
              investable fresh names holds min(k, available) equal-weight;
              at available = 0 it holds cash, books a 0.0 return, and the
              Hedge recursion consumes the zero unchanged; shortfall-day
              counts per book are committed backtest artifacts.
           2. composite pinned (§4): the nine ineligible sectors POOL into
              one 27.0% bucket replicating the global-only book — not
              per-sector sub-books under global weights; rationale (no
              frozen k below 14 names; exact convex-mix attribution)
              stated in the doc.

REVIEW r2: codex P1 (2026-08-09): the #927 "swap = 2/3 book" shortcut is
           wrong for top-2 books and cash-shortfall transitions. Adopted
           the general turnover rule with one VISIBLE correction to the
           review's literal formula (§4): cost = 10 bps × names-only
           holdings L1 change, no ½ factor, cash sleeve excluded — the
           review's "0.5·Σ|Δh| incl. cash" gives ⅓ × 10 bps on the full
           top-3 one-swap, a factor-2 shortfall vs the #927 identity it
           must reduce to. All-cash h_0 with day-0 entry cost frozen;
           per-book turnover/cost columns + verifier re-derivation from
           holdings paths required. (This section records the r2 fix,
           which shipped in the design doc only — repaired here in r3.)

REVIEW r3: codex MED (2026-08-09): the placebo gate and the top-k rank
           still carried runner discretion. Frozen in the design doc:
           1. §4 placebo: seeds 0..199 via
              numpy.random.default_rng(σ).permutation(159) over tickers
              in ascending lexicographic order, one date-invariant map
              per seed; delta(σ) = permuted-composite net Sharpe −
              global-only net Sharpe; p95 = 190th ascending value of the
              200 deltas (⌈0.95·200⌉ order statistic); pass iff observed
              delta > p95 strictly; placebo fail demotes ADOPT-for-shadow
              to RECORD-ONLY; every map + delta committed, verifier
              recomputes the gate.
           2. §3 tie-break: ranking into top-k by (−score, ticker) —
              descending score, ties by ascending ticker — after the
              staleness + investability filters.

REVIEW r5: codex MED ×2 (2026-08-09) on the provenance follow-up (#935):
           1. the "~20× longer evidence axis per decision" line turned a
              ratio of unlike axes (time depth ÷ per-date name breadth)
              into an evidentiary-strength claim; a `[DERIVED]` tag
              documents the arithmetic, not the conclusion's validity.
              The design doc (§1) now states measurement shape only —
              541-day book-return series instead of a thin per-date IC —
              with an explicit disclaimer that this is not an
              effective-sample-size or power claim (serial dependence;
              IC precision depends on dependence/dispersion); the §4
              placebo/backtest remain the evidence.
           2. NEXT was stale after #934 merged and ambiguously read as if
              this provenance-only PR authorizes the backtest; rewritten
              above — execution happens only in its own separately
              reviewed backtest PR, no shadow/live action implied.
