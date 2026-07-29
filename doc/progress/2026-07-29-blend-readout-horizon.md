# Progress: blend readout horizon 20d -> 60d (operator decision)

STATUS:   delivered (code + amendment + 9/9 tests). Amends a frozen rule, on explicit
          operator authority.

WHAT:     `mature_fill` now backfills from `fwd_60d`, and `MATURITY_TDAYS` moves 21 ->
          61 with it. Adds `doc/research/2026-07-29-blend-readout-horizon-amendment.md`
          recording the change against the frozen pipeline#213 rule.

WHY/DIR:  The 120-session forward ledger is the one piece of evidence here that cannot
          be re-derived later, and it was backfilling a 20-day spread while the
          certified effect (+0.0687, CI lower +0.0156) and both scored models are
          fwd_60d recipes. The Feb-2027 GATE read would have answered a question the
          certification never asked.

EVIDENCE: availability checked BEFORE committing `[VERIFIED - direct query]`:
          `ticker_forward_returns.fwd_60d` holds 17,084 non-null rows, latest as_of
          2026-04-30, so the column is populated rather than a new dependency. GOAL-6
          Stage 0 separately measured that the shorter horizon buys no power (H2 NOT
          SUPPORTED: ~3x the blocks, proportionately smaller effect). The
          maturity constant was the trap: left at 21 against a 60-day label it marks
          rows mature 40 sessions before their label can exist; a test now pins the
          horizon and the maturity window together. Both recorded sessions are
          unrealized, so no already-computed row is discarded. Suite 9/9.

NEXT:     Realized rows now arrive ~40 trading days later; the INFO read slips
          accordingly. That cost is stated in the amendment rather than buried.
