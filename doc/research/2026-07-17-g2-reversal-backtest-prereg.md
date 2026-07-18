# Preregistration: G2 crypto reversal costed backtest (hypothesis H1)

Date: 2026-07-17
Status: RFC — frozen upon merge; the historical exercise may not run until
this document is merged and its input manifests are sealed. It is an
exploratory, costed feasibility screen only: it cannot confirm H1 or
authorize capital. Instantiates the six requirements stated in the
round-1 codex review of orch#532 (the gate memo's revision source; the
merged memo's §3 records the GO-narrow verdict, not the list — citation
corrected r2); their substance is restated in §1–§6 below, which are the
frozen text.
Drafted personally per design-review policy.

## H1 (the single admitted hypothesis)

Liquid-tier cross-sectional 3-day reversal at 1-day horizon on Alpaca
spot crypto, LONG-ONLY, evaluated NET of fees against a matched BTC
buy-and-hold baseline.

## 1. Selection control and evidence status (§3-item 1)

- The tested-spec family (r2 — corrected to the ACTUAL search path of
  the #532 screen, not a padded rectangle): signal {momentum, reversal}
  × (lookback→horizon) pairs {3→1, 7→1, 7→7, 30→7, 90→20} × universe
  {full-20, liquid-10} = 20 members. The earlier "×{1,7}d" recording
  both understated the search (horizon 20 was screened) and padded it
  with never-screened cells; a reality-check family must cover exactly
  what was searched. That screen already used the available 2021-01-01
  through 2026-07-16 history. Therefore no statistic from this
  historical exercise is confirmatory, regardless of a reality-check
  adjustment. It may only decide whether the specified construction is
  economically plausible enough to enter a separately registered
  prospective paper-shadow test.
- The historical report still computes a block-bootstrap max-t over the
  fully enumerated, executable portfolio family as an overfitting
  diagnostic. Every family member's frozen long-only construction is
  DEFINED HERE (r2): the §4 template with that member's signal
  direction, lookback, horizon, and universe substituted, k=3 in both
  tiers, all other rules identical. No member has any other latitude.
  The report must not apply a rank-IC family to a portfolio-return
  statistic.
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
- Prospective power (r2 — house decision structure, per the G1 v5
  standard): `MEE = 5 bps/day net` is the materiality threshold and
  requires a written economic rationale in the paper-shadow registration
  (~18%/yr on the sleeve vs BTC; on the $10.7k sleeve ≈ $5/day — the
  minimum worth the operational surface); the planning effect
  `PE = 10 bps/day` sits strictly above MEE and is where power ≥ 0.80
  must be demonstrated by a fitted-null simulation at the predeclared
  duration; type-I ≤ 0.10 is evaluated for the deployment rule at
  μ = MEE. The shadow verdict separates statistical efficacy (LB > 0,
  reported) from advancement eligibility (LB > MEE, decides) — bare
  LB>0 cannot advance G2, and a gate at LB>MEE=MDE would be structurally
  powerless at MEE (the v3-class error).
- Underpowered disposition (r2 — named): if power ≥ 0.80 at PE cannot be
  shown at the predeclared duration, the outcome is "underpowered — do
  not run to a verdict" and G2 is PARKED: no verdict may be claimed, and
  the only exits are a NEW registration with a longer predeclared
  duration, or a revised MEE/PE with fresh economic rationale. Parking
  is recorded in the goal memo; the §5 fee-gate kill remains the only
  kill path.

## 3. Point-in-time universe (§3-item 3)

- As-of membership schedule: pair p is in the liquid tier on day T iff its
  trailing 30-day median daily dollar volume (through T-1) ranks top-10
  among pairs listed on T-1 per the MEMBERSHIP-SCHEDULE FILE (below).
  Delisting = forced exit at the last available price, cost-charged.
- **Listing provenance (r2 — replaces "survivorship handled by
  construction", which was unfalsifiable).** "Listed on T-1" must come
  from Alpaca's HISTORICAL listing/delisting record (support
  announcements, assets-API history), never from data presence in the
  collected store: a pair listed in-window and delisted before our 2026
  collection is absent from the store on every day it was actually
  tradable, and for a LONG-LOSER strategy that censoring is worst-case —
  delisting-bound coins are disproportionately the bottom-3 picks, so
  their absence inflates net d_t and biases the §5 kill statistic toward
  PASS. (MKR's history happens to survive in the store; that fact
  generalizes to nothing.) Before sealing, exactly one of:
  (a) **verified-complete**: the schedule file documents, with sources
  and retrieval dates, that the 20 collected pairs are the COMPLETE set
  ever tradable on Alpaca spot in-window — then the universe is genuinely
  point-in-time; or
  (b) **enumerated-censoring**: every known omission is listed in the
  manifest, the bias direction is REGISTERED (inflates PASS), and any
  feasibility PASS is downgraded to CONDITIONAL — the censoring caveat
  must be carried verbatim into the paper-shadow registration, whose
  fully prospective (censoring-free) result is controlling.
  If neither can be produced, the inputs cannot seal and the exercise
  does not run (fail-closed).
- Inputs sealed: the collected `crypto_ohlcv/` store's content digests +
  the frozen membership-schedule file WITH its provenance declaration are
  the immutable manifest; the backtest refuses to run on unsealed inputs
  (fail-closed).

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
- Historical feasibility rule (r2 — stress consequence registered): in a
  24/7 market the daily-bar proxy grants effectively zero-latency,
  zero-spread fills, so the base case is the MOST-optimistic accounting.
  Feasibility PASS therefore requires the net lower bound > 0 at BASE
  fees AND at +10 bp slippage; the +25 bp scenario is reported as stress
  information. A base-fee lower bound ≤ 0, OR a +10 bp lower bound ≤ 0,
  prevents paper shadow and records a G2 NO-GO with tombstone. A pass
  only permits the prospective paper-shadow registration; it is never a
  capital GO.

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
  registration; a §3(b) CONDITIONAL pass carries the enumerated-censoring
  caveat verbatim into that registration, whose prospective result is
  controlling. It does not confirm H1 and authorizes no capital.
  Historical failure (base or +10 bp, §5) ⇒ G2 killed and the memo
  records the tombstone. Underpowered (§2) ⇒ G2 PARKED with the named
  re-registration exits. Prospective paper shadow has its own
  pass/fail/underpowered verdict under the §2 house structure.
