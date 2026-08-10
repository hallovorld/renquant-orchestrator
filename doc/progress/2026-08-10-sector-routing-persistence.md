# Routing persistence pre-test — Stage-0 KILL for trailing-performance routing

STATUS:    measurement; read-only over committed artifacts; the Stage-1
           policy walk-forward is NOT built, by design.

WHAT:      doc/research/2026-08-10-sector-routing-persistence.md +
           committed derivation/decisions/summary. Hit rate 27.8% (below
           chance), adjacent-quarter Spearman −0.185, oracle capture 41%.

WHY/DIR:   The operator asked how a backtest picks each sector's model
           for next quarter. The cheapest decisive experiment is the
           persistence premise; it failed, killing every
           trailing-performance policy before construction. The living
           MoE alternative is state-conditioning (model#215).

EVIDENCE:  artifact:      2026-08-10-routing-persistence-summary.json +
                          -decisions.csv (all 54 rows) + derivation
                          [VERIFIED — run this session; reads only the
                          committed #936 dailies]
           prod or exp:   read-only measurement
           existing data: entirely (the #936 committed dailies)
           best-known?:   yes — the contrarian temptation is explicitly
                          NOT promoted (post-selection); replay-frame
                          caveats carried
           scope:         Stage-1 not built; rerun on served data when
                          it accrues.

TESTS:     derivation re-runnable read-only; decisions CSV enumerates
           every (sector, quarter) pair.

NEXT:      nothing on this line — it is complete; the MoE condition axis
           continues in model#215.
