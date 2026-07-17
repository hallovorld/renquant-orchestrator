# Preregistration: G2 crypto reversal costed backtest (hypothesis H1)

Date: 2026-07-17
Status: RFC — frozen upon merge; the backtest may not run until this
document is merged and its input manifests are sealed. Instantiates the
six requirements frozen in the revised G2 gate memo
(doc/research/2026-07-17-g2-crypto-data-quality-gonogo.md §3, merged).
Drafted personally per design-review policy.

## H1 (the single admitted hypothesis)

Liquid-tier cross-sectional 3-day reversal at 1-day horizon on Alpaca
spot crypto, LONG-ONLY, evaluated NET of fees against a matched BTC
buy-and-hold baseline.

## 1. Selection control (§3-item 1)

- The complete tested-spec family from the screen is recorded in the gate
  memo (momentum/reversal × {3,7,30,90}d × {1,7}d × {full-20, liquid-10}
  universes). H1 was selected from it; therefore the CONFIRMATORY
  statistic here is computed on data/date-ranges NOT used by the screen
  where possible, and the primary inference applies a block-bootstrap
  max-t (reality-check) over the ORIGINAL family as the multiplicity
  control: H1 must survive the family-wise test, not a solo t.
- No new specs may be added post-hoc. Any variant (different k, different
  tier) is a NEW registration.

## 2. Inference model (§3-item 2)

- Unit: daily strategy-minus-baseline return difference d_t (see §4 for
  the executable strategy; baseline = BTC buy-and-hold at identical
  notional and cost treatment).
- Test: one-sided MBB on mean(d_t) > 0 at α = 0.10 — the house machinery
  (G1 v4 / G4 v3), block length from fitted autocorrelation of d_t,
  frozen before evaluation; report n valid days and names-per-day.
- Power: fitted-null simulation at MDE = 5 bps/day net (economic
  materiality for a small sleeve) must show power ≥ 0.80 at the available
  T, else the recorded outcome is "underpowered — do not run to a
  verdict" (no peeking runs).

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
- Rebalance daily at open(T+1) proxy (first bar after UTC close);
  positions held 1 day; minimum notional $10; a pair failing the
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
- KILL RULE (pre-registered): net-of-fee MBB lower bound ≤ 0 at base
  fees ⇒ G2 dies (the operator's early-kill discipline, final form).

## 6. Timing convention (§3-item 6)

- Bars finalize at UTC day close; signal availability = close + 5 min;
  earliest execution = the open(T+1) proxy price (first post-close bar);
  scoring interval open(T+1) → open(T+2). No close-to-close double use.
  (Same structural convention as G4 v3 §B — house standard.)

## 7. Outputs and disposition

- One frozen results artifact (JSON: family-wise p, net d_t stats per
  stress, turnover, power-check numbers, input digests, seed).
- PASS ⇒ G2 proceeds to a paper-account shadow phase (its own
  registration; no capital from this document). FAIL ⇒ G2 killed, memo
  records the tombstone. Underpowered ⇒ wait/accumulate, no verdict.
