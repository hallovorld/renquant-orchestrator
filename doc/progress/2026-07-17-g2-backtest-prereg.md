# Progress: G2 reversal costed-backtest preregistration

STATUS: delivered (design RFC)
WHAT: preregisters the historical feasibility screen for the single admitted
H1 (liquid-tier 3d reversal @1d, long-only). Because the original screen
already consumed the available history, the costed backtest is explicitly
exploratory, not confirmatory: max-t and MBB are diagnostics only. It freezes
PIT membership/delisting, long-loser construction, fee/slippage stress, and a
daily-bar next-open proxy; only a separately registered prospective
paper-shadow test with recorded fills may test H1.
WHY/DIR: G2's next gate; drafted personally per design-review policy.
EVIDENCE: n/a (prereg; the historical exercise may not run until merged +
inputs sealed, and cannot authorize capital regardless of outcome).
NEXT: seal input manifests, implement the descriptive feasibility runner,
then register a fixed-duration paper-shadow protocol only if the historical
fee-stress screen is positive.
