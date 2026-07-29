# Progress: the live book is half cash because a tax filter with no materiality threshold blocks buys

STATUS:   finding, measured on the live run logs. NO fix applied — the remedy
          changes a capital gate and belongs in a reviewed design change, not
          a unilateral edit.

WHAT:     The live 104 buy path is being zeroed by `wash_sale_mass_block` on a
          majority of recent sessions. The filter computes an NPV tax cost per
          candidate, logs it, and then blocks UNCONDITIONALLY — there is no
          materiality threshold. A $0.04 tax cost blocks a position exactly as
          hard as a $13.62 one.

WHY/DIR:  Started from the operator's standing question — when can the system
          place reliable orders. Read the live account rather than the models:
          equity $10,552, cash $5,272 = 50.0% of equity, 6 positions, total
          unrealised -$7.10. Half the book idle is not a model verdict, so I
          went to the funnel.

EVIDENCE: artifact: live Alpaca account (READ-ONLY), and
                    `RenQuant/logs/daily_104/2026-07-*.log`;
                    config `backtesting/renquant_104/strategy_config.json`.
  prod or exp:      PROD observation. Account read READ-ONLY, no orders placed,
                    no config or code changed.
  existing data:    Yes, measured this session:

    date        wash_block  candidates   orders placed
    2026-07-20      0          105        2  ($260)
    2026-07-21      0          102        1  ($75)
    2026-07-22      0          101        1  ($335)
    2026-07-23      1          100        none
    2026-07-24      1          100        none
    2026-07-27      0          109        2  ($463)
    2026-07-28      2          107        0  ($0 of $6,868 cash)

    2026-07-28 detail — the whole block, with the tax it was avoiding:
      MCHP  loss -$1.28   20d ago   NPV cost $0.04
      BWXT  loss -$3.13    7d ago   NPV cost $0.09
      NEE   loss -$3.24   27d ago   NPV cost $0.09
      AFRM  loss -$10.21   4d ago   NPV cost $0.28
      CSCO  loss -$13.67  18d ago   NPV cost $0.38
      FTNT  loss -$25.43   6d ago   NPV cost $0.71
      CRWD  loss -$488.43 26d ago   NPV cost $13.62
      MU    P/L unknown   13d ago   BINARY block

    The pipeline's own integrity checker fired and said so in plain words:
      FunnelIntegrityAlert: STRUCTURAL_BLOCK — engineering condition
      suppressed buy capability; do NOT report this session as a normal
      no-trade. fired=['wash_sale_mass_block']

  best-known?:      Yes for the block and its cost figures — they are the
                    pipeline's own logged numbers. NOT established: how much
                    return the blocked names would have produced. The cost of
                    the block is opportunity cost, which is unmeasured here.
  scope:            Observation only. No pin advanced, no config or code
                    changed, no order placed.

THE ASYMMETRY:
          Blocking a candidate to avoid $0.04 of tax is not a conservative
          choice, it is a large bet against the model stated in units nobody
          declared. On 2026-07-28 the filter protected at most ~$15 of tax
          across eight names while $6,868 of cash sat unused and zero orders
          were placed. Three of the last five sessions went to zero this way.

          The `MU` line is a second issue inside the first: when realised P/L
          is unknown the filter does a BINARY block. Failing closed on missing
          data is right for a safety gate and wrong for a tax optimisation —
          it converts a data gap into a capital gate.

WHAT IS NOT CLAIMED:
          That the wash-sale rule should be removed. It encodes a real tax
          consequence. What is missing is a MATERIALITY threshold: the only
          config knob is `wash_sale_days = 30`, and no cost floor exists
          anywhere in the filter.

          Also not claimed: that this explains all 50% cash. Even on unblocked
          sessions the system places 1-4 orders totalling $75-$800 against
          $5-7k of cash, so a second, separate deployment question remains
          open.

## SECOND CONSTRAINT (measured after the above): fractional sizing is OFF

The unblocked sessions have a different cause, and it is not the model either.
Full funnel, 2026-07-27 (an UNBLOCKED session):

    118 tickers
    -> 109 candidates            (8 wash-sale drops + 1 earnings)
    ->  80  RealizedVolGate      dropped 29 over the 60% annualised vol cap
    ->  15  VetoWeakBuys         dropped 65 below rank_score floor 0.538
    ->   4  ConvictionGate       dropped 11 below mu_floor 0.03
    ->   4  Kelly sizing         4/4 non-zero, avg 6.1% target
    ->   2 ORDERS, $463 of $9,301 cash

The two that did not make it:

    TSLA insufficient cash — skip (remaining_cash=$9301 price=$309.22)
    EME  insufficient cash — skip (remaining_cash=$8838 price=$742.73)

**There was $9,301 of cash and TSLA costs $309.22.** The message is wrong. The
real condition is `compute_position_size(...) -> 0 shares`: the per-name target
was ~2.2% (~$231 on this book) and INTEGER share math floors $231/$309 to zero.
AMZN ($231.33) and SPG ($231.70) cleared only because one share happens to
land at the target.

Note what the log line does NOT say: it has no `, fractional` suffix, so it
took the whole-share branch — `use_frac` was False.

ROOT CAUSE `[VERIFIED]`: `kernel/sizing.py:204` — "no behaviour change unless
strategy-104 opts in via `execution.fractional_shares.enabled`". The live
config's `execution` block contains only
`['_settlement_reason_2026_05_24', 'enabled', 't2_settlement_days',
'buying_power_mode']`, and `execution.fractional_shares` is **null**.

S-FRAC v2 is built, merged and pinned in the pipeline. Strategy-104 never
opted in. It has been sitting dark, which is the "deployed-but-dark" pattern
exactly: a default-OFF fix that never reaches daily-full is worth zero.

## The two constraints together explain the idle half

Neither is a model problem, and neither needs new alpha:

  1. `wash_sale_mass_block` zeroes buys entirely on 3 of the last 5 sessions,
     protecting ~$15 of tax across eight names;
  2. with fractional OFF, every surviving name priced above its ~$231 position
     target is skipped on an integer-share floor while thousands in cash sit
     unused, and the operator is told "insufficient cash".

NEXT:     1. `renquant-pipeline` issue proposing a materiality floor on the
             wash-sale filter (its code, its call — not an orchestrator edit).
          2. Turning on `execution.fractional_shares.enabled` is a LIVE CAPITAL
             GATE change on the strategy config. It needs a design PR with a
             behaviour-invariance argument and operator sign-off, not a flag
             flip — even though the flag is the whole fix. Also fix the
             "insufficient cash" message, which reports a cash shortage that
             does not exist and would mislead anyone debugging this next.
