# Preregistration: G2 crypto reversal costed backtest (hypothesis H1)

Date: 2026-07-17
Status: RFC — frozen upon merge; the historical exercise may not run until
this document is merged and its input manifests are sealed. It is an
exploratory, costed feasibility screen only: it cannot confirm H1 or
authorize capital. Instantiates the six requirements frozen in the revised G2 gate memo
(doc/research/2026-07-17-g2-crypto-data-quality-gonogo.md §3, merged).
Drafted personally per design-review policy.

## H1 (the single admitted hypothesis)

Liquid-tier cross-sectional 3-day reversal at 1-day horizon on Alpaca
spot crypto, LONG-ONLY, evaluated NET of fees against a matched BTC
buy-and-hold baseline.

## 1. Selection control and evidence status (§3-item 1)

- The complete tested-spec family from the screen is recorded in the gate
  memo (momentum/reversal × {3,7,30,90}d × {1,7}d × {full-20, liquid-10}
  universes). That screen already used the available 2021-01-01 through
  2026-07-16 history. Therefore no statistic from this historical exercise
  is confirmatory, regardless of a reality-check adjustment. It may only
  decide whether the specified construction is economically plausible
  enough to enter a separately registered prospective paper-shadow test.
- The historical report still computes a block-bootstrap max-t over the
  fully enumerated, executable portfolio family as an overfitting diagnostic.
  Every family member uses its own frozen long-only construction; the report
  must not apply a rank-IC family to a portfolio-return statistic.
- No new specs may be added post-hoc. Any variant (different k, different
  tier) is a NEW registration.
- The only confirmatory H1 test is the prospective paper-shadow interval
  registered after this feasibility screen. It starts after the input seal,
  has a fixed duration and stopping rule, and uses recorded paper fills.

## 2. Inference model (§3-item 2)

- Unit: daily strategy-minus-baseline return difference d_t (see §4 for
  the executable strategy; baseline = BTC buy-and-hold at identical
  notional and cost treatment).
- Historical inference: one-sided MBB on mean(d_t) > 0 at α = 0.10, with a
  percentile lower confidence bound and a precomputed block length from the
  fitted autocorrelation of d_t. It is descriptive only; report n valid days,
  names-per-day, and the max-t diagnostic.
- Prospective power: before paper shadow starts, a fitted-null simulation at
  MDE = 5 bps/day net must show power ≥ 0.80 at its predeclared duration;
  otherwise the outcome is "underpowered — do not run to a verdict".

## 3. Point-in-time universe (§3-item 3)

- As-of membership schedule: pair p is in the liquid tier on day T iff its
  trailing 30-day median daily dollar volume (through T-1) ranks top-10
  among pairs LISTED on T-1 (MKR remains until its delisting date —
  survivorship handled by construction, delisting = forced exit at the
  last available price, cost-charged).
- Inputs sealed: the collected `crypto_ohlcv/` store's content digests +
  a frozen membership-schedule file are the immutable manifest; the
  backtest refuses to run on unsealed inputs (fail-closed).

## 4. Executable long-only construction (§3-item 4)

- Signal at close(T) (UTC day close per the collector's bar convention):
  rank pairs by trailing 3-day return; portfolio = equal-weight LONG the
  bottom-3 ranked (losers) of the liquid tier. No shorting exists on the
  venue; the strategy's "reversal" content is the long-loser tilt vs the
  BTC baseline.
- Historical execution proxy: the daily-bar open(T+1), not an asserted
  executable first post-close fill. The collector contains daily bars only;
  it cannot establish intraday fill quality. The subsequent paper-shadow
  test must use timestamped broker fills at its separately frozen schedule.
  Positions rebalance daily, are held 1 day, and use a minimum notional of
  $10; a pair failing the
  liquidity/membership screen exits at the same rebalance.
- Cash never idle: un-investable residue (min-notional clips) sits in
  BTC, keeping the comparison exposure-honest.

## 5. Quantified fee gate (§3-item 5)

- Fees: 25 bp/side taker (Alpaca crypto tier-0), charged on EVERY
  rebalance leg incl. baseline's (baseline trades ~never, which IS the
  point). Slippage stress: +10 bp and +25 bp scenarios. Stale-price
  guard: a pair with a zero-volume day is unrankable and untradeable that
  day.
- Report: expected daily turnover, gross mean d_t, net mean d_t under
  each stress, and the verdict statistic on NET.
- Historical feasibility rule: a base-fee lower bound ≤ 0 prevents paper
  shadow and records a G2 NO-GO. A positive historical result only permits
  the prospective paper-shadow registration; it is never a capital GO.

## 6. Timing convention (§3-item 6)

- Historical bars finalize at UTC day close. The signal uses information
  through close(T), execution is proxied by the next daily bar open(T+1),
  and scoring is open(T+1) → open(T+2). No close-to-close double use. This
  is a daily-bar accounting convention, not a claim that the proxy is an
  attainable fill. The paper-shadow protocol supplies the actual order
  timestamp, fill, and latency convention.

## 7. Outputs and disposition

- One frozen results artifact (JSON: max-t diagnostic, historical net d_t
  stats per stress, turnover, input digests, execution-proxy declaration,
  and seed).
- Historical feasibility pass ⇒ G2 may submit a paper-account shadow
  registration. It does not confirm H1 and authorizes no capital. Historical
  failure ⇒ G2 killed and the memo records the tombstone. Prospective paper
  shadow has its own pass/fail/underpowered verdict.
