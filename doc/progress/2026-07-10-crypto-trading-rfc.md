# Crypto Trading Capability RFC (GOAL-2)   (PR #453)

STATUS:    in-progress
WHAT:      Design RFC for Alpaca spot crypto trading as an isolated $1-2k
           sleeve: 24/7 intraday loop (fork of the 105 scheduler bones,
           always-open UTC-day sessions), new `renquant-strategy-crypto`
           config repo, asset-class abstraction threaded through pipeline/
           execution/base-data, and a new XGB crypto panel model
           (price/volume only, h=20 calendar days) under WF-gate governance
           plus a NEW shared net-of-cost gate primitive.
WHY/DIR:   Operator mandate (GOAL-2, 2026-07-10): enable crypto trading for
           the 104/105 system family as an isolated sleeve, capability and
           model designed together. Independent of the Deployment Governor/
           D6/shadow-AB lanes (separate design track, same repo).
EVIDENCE:  n/a (design doc, not a model/data claim — see RFC §2 for the
           file:line gap audit and §2.7 for direct SDK-surface verification)
NEXT:      Codex re-review of the r1 fixes below; on approval, implementation
           PRs D-C1..D-C13 per RFC §7 (strict merge order, orchestrator last,
           default-OFF).

## r1 update (2026-07-10) — first Codex review, four blockers + cost-model tightening

Codex's first review kept this design blocked on four numbered points plus
additional cost-model/GTC/repo-split tightening. All addressed as real design
decisions (doc-only PR, no code):

1. **Cash isolation (§5.3)**: the original "cadence separation + local sleeve
   cap means 104 needs no change" claim was FALSE under concurrent snapshots
   — traced the actual code (`OrderStateBook` is per-broker-tag,
   `reserved_cash()` only sees its own book's reservations) to confirm the
   double-reservation risk is real, not hypothetical. Fixed: a new
   account-scoped `AccountCashLedger` (execution-owned, D-C4) replaces
   per-book reservation as the sizing source of truth for BOTH sleeves;
   104's existing sizing path gains exactly one new `reserve()` call.
   Evaluated and dropped the broker-side segregated-sub-account alternative
   (not available in the Alpaca SDK surface).
2. **Survivorship bias (§4.6)**: investigated point-in-time crypto listing
   data availability — confirmed none exists (the SDK only returns current
   asset status, no historical-snapshot endpoint). Per Codex's explicit
   fallback, downgraded to two separate evidence tiers: an EXPLORATORY
   survivor-only historical panel (small continuously-listed subset, never
   called a "5-year validation" of the full universe) vs. the actual
   decision-grade evidence, which is PROSPECTIVE (Stage-1 shadow + Stage-2
   canary, not survivorship-biased since it's forward).
3. **Leakage-proof session contract (§3.5, §4.5)**: replaced the vague
   "00:00 UTC + 15-min quiet window" with an exact frozen contract — a
   `[D 00:00, D 00:15)` UTC quiet interval, a precise bar-close watermark,
   an immutable `signal_snapshot_digest` reusing the D6-§2a decision-
   snapshot pattern (same repo, different design track), fail-closed
   entries with no stale-signal fallback, and per-tick bundle persistence
   for replay audit.
4. **Label pre-registration + vol-target ambiguity (§4.3, §3.4/P7)**: froze
   raw 20-day forward return as the primary label BEFORE any WF evidence
   (removed the "decide on WF evidence" post-selection language); BTC-excess
   stays a pre-registered diagnostic only. For the vol-target ambiguity
   ("BTC-proxied or absolute"): recognized this as the SAME proxy-vs-real-
   portfolio-volatility flaw Codex had just corrected on the Deployment
   Governor RFC's voltarget arm (which was ultimately REMOVED there for lack
   of real portfolio-covariance infrastructure) — froze this RFC to
   ABSOLUTE vol target only, scoping a benchmark-relative version out of v1
   for the same reason.

Additional tightening:
- **Cost model (§4.4)**: replaced the fee-only formula with ONE authoritative
  net-cost primitive (fees, spread/slippage, increment rounding, rejected/
  unfilled/resting-order handling) shared identically by replay and runtime
  accounting, each component calibrated and bounded from the Stage-0 paper
  battery.
- **GTC stop-limit claim (§5.1)**: corrected "downside protection persists"
  to honestly describe gap-through/non-fill risk — broker residency means
  the stop order survives machine death, not that the exit price is
  guaranteed.
- **D-C8 repo split**: split into D-C8a (generic net-of-cost primitive,
  renquant-model-common/shared) and D-C8b (BTC-baseline + crypto promotion
  decision, renquant-model only) — avoids an asset-specific gate in shared
  code.

§9's three open questions are now resolved/frozen decisions, not open
questions (renamed accordingly).

## Basis

Read-only audit of live checkouts (execution, pipeline, base-data,
strategy-104, orchestrator) + direct verification of alpaca-py 0.43.4 crypto
surface (CryptoHistoricalDataClient v1beta3, CryptoDataStream, GTC/IOC,
stop_limit for crypto, per-asset increments, `crypto_status`). All gaps cited
file:line in RFC §2; unverifiable broker-side facts marked [GUESS] and routed
to the Stage-0 paper battery.

## Key findings

- Central breaks: TIF=DAY hardcoded in every submit path; reconciliation
  filters `asset_class=US_EQUITY` (crypto orders invisible); no fee model
  anywhere; NYSE calendar hardwired into freshness/hold-clocks/settlement;
  wash-sale engine has zero asset-class awareness; fundamentals gates
  hard-block a no-fundamentals asset class; `BTC/USD` slash breaks every
  symbol-derived file path; WF gate has NO transaction-cost model (grep-verified
  absence) — fee-aware evaluation is a new capability.
- Crypto advantage: broker-resident GTC stop-limit in native fractional qty is
  SDK-supported — a resting order survives machine death (not a guaranteed
  exit price, see r1 correction above).

## Operator decisions carried (2026-07-10)

sleeve $1–2k from the $10.7k account (exact at canary sign-off) · direct to
model (pipeline+model together) · full ~20-pair universe (CURRENT-universe
validation is prospective-only, see r1 point 2) · 24/7 loop on this Mac.

## Boundaries honored

No Deployment Governor / D6 / shadow-AB files touched; design-first — this
RFC merges before any implementation PR.
