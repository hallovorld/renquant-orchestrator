# Routing persistence pre-test — the 1-quarter follow-the-winner rule fails (scope narrowed)

STATUS:    measurement; read-only over committed artifacts; the Stage-1
           policy walk-forward is NOT built, by design.

WHAT:      doc/research/2026-08-10-sector-routing-persistence.md +
           committed derivation/decisions/summary. Hit rate 27.8% (below
           chance), adjacent-quarter Spearman −0.185, oracle capture 41%,
           and (r1) the blind equal-weight baseline: +8.1%/q vs the
           rule's +7.6%/q — follow-the-winner underperforms blind.
           SCOPE: exactly the 1-quarter argmax rule; other
           lookbacks/hysteresis untested (own prereg if pursued); 54
           correlated rows, binomial p optimistic.

WHY/DIR:   The operator asked how a backtest picks each sector's model
           for next quarter. The cheapest decisive experiment is the
           persistence premise; it failed, killing the tested
           follow-the-winner rule before Stage-1 construction (broader
           rule families untested by design — multiplicity). The living
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
