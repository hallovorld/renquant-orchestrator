# L2-S design: sector awareness returns, at allocation granularity

STATUS:    design proposal only; no backtest has run; every threshold in
           the doc is frozen before any output exists.

WHAT:      doc/design/2026-08-09-l2-sector-conditional-allocation.md —
           sector-conditional expert allocation: per-sector Hedge paths on
           sector-book returns, shrunk toward the merged global L2 path by
           frozen width tiers (m_s ∈ {0.5, 0.67, 1.0}); six eligible
           sectors (≥14 names) covering 73.0% of the universe; four frozen
           comparison books; a frozen ADOPT/RECORD-ONLY rule; a
           sector-permutation placebo ×200.

WHY/DIR:   Operator 2026-08-09: the three-layer machine lost sector
           awareness and that loss is unacceptable — the original MoE
           vision was sector-first. The selection-level routing table died
           on measurement (#910–#913, IC on 8–26 names = noise); this
           design restores sector awareness at ALLOCATION granularity,
           where each decision rests on a 541-day book-return series
           instead of a daily thin-cross-section IC. Both of the
           operator's original shapes are endpoints of the shrinkage dial.

EVIDENCE:  artifact:      pinned sector map (strategy_config sha
                          43cbb9b2…) [VERIFIED — read this session]:
                          159 names / 15 sectors; six ≥14-name sectors
                          hold 116 names = 73.0%. Prior-line numbers
                          cited from merged records (#913 kill n=278;
                          #926 Hedge +45.9%/1.33; #927 net panel
                          +22.1%/0.49, churn drags 5.5–13.1pp).
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

NEXT:      operator veto window + codex review; on merge, execute the §4
           backtest once with committed artifacts + verifier; report
           ADOPT-for-shadow vs RECORD-ONLY exactly as frozen.

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
