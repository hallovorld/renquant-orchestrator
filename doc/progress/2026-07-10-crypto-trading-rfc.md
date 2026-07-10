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
NEXT:      Codex re-review of the r5 fix below (N*/δ direction correction);
           on approval, implementation PRs D-C1..D-C13 per RFC §7 (strict
           merge order, orchestrator last, default-OFF).

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
2. **Survivorship bias (§4.6)**: named the candidate PIT
   listing/tradability sources, each marked — Alpaca assets endpoint
   [VERIFIED — no history in the SDK surface], Alpaca listing
   announcements / web-archive doc snapshots / CoinGecko exchange-listings
   history [all GUESS — Stage-0 investigation items], CoinMarketCap
   snapshots [GUESS — upper-bound screen only, no Alpaca tradability].
   Stage 0 gets a timeboxed (≤1 day) reconstruction attempt: a defensible
   interval table upgrades the historical panel to PIT-gated; otherwise the
   pre-registered WEAKER claim stands — two separate evidence tiers: an
   EXPLORATORY survivor-only historical panel (small continuously-listed
   subset, never called a "5-year validation" of the full universe) vs. the
   decision-grade PROSPECTIVE evidence (Stage-1 shadow + Stage-2 canary,
   forward, hence not survivorship-biased).
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

## r2 update (2026-07-10) — second Codex review, two decision-grade blockers

Codex accepted the r1 ownership map and controls as materially better, and
narrowed to two remaining decision-grade blockers:

1. **Operational readiness vs economic efficacy conflated (§6, NEW §6.1)**:
   the 14-day shadow + 2-week canary window was being read as if it could
   substantiate a 20-calendar-day-horizon model — it cannot; at most ONE
   complete non-overlapping 20-day block fits in either window. Fixed:
   explicitly relabeled Stages 1-2 as OPERATIONAL-ONLY gates (scheduler/
   stop/reconciliation reliability), and added a NEW Stage 2.5 —
   prospective economic evaluation, capital HELD at $500 (not scaled) —
   worked exactly like the Deployment Governor RFC's own analogous power
   problem (§1.2/§2a, merged orchestrator#443): non-overlapping 20-day
   blocks as the unit of inference, an 8-block absolute floor (160 days,
   ~5.3 months) below which no variance estimate is trustworthy, a labeled
   conservative-proxy power check (50%/100% annualized vol proxy → N* ≈
   212/847 blocks ≈ 11.6/46 years — both plainly impractical, the SAME
   honest conclusion the Governor RFC reached with its own proxy), and a
   blinded sample-size re-estimation at the 8-block checkpoint (95% UCB on
   realized variance, freeze `N_blocks ≥ max(8, N*)`) rather than a single
   fixed-N guess. NO-GO (indefinite $500/descriptive-only) is a frozen,
   first-class, acceptable outcome if the re-estimated N* is impractical —
   the exploratory survivor panel is explicitly forbidden from setting
   these thresholds. Stage 3 (full sleeve) now requires Stage 2.5's NO-GO
   check to clear, not operator sign-off alone.
2. **Stage-0 paper-fill calibration boundary (§4.4)**: paper fills validate
   fee schedule, increment rounding, and order-acceptance/rejection/resting
   RATES (real API behavior) — they do NOT calibrate spread/slippage or
   stop-limit non-fill/gap-through risk, since a paper fill has no real
   market impact. Fixed: spread/slippage and non-fill/gap bounds are now
   sourced as conservative EX-ANTE bounds from Alpaca's own quote/trade
   market data (not paper simulation) — concretely: per-pair spread
   percentiles (median/p95/worst-weekend-hour), depth-vs-order-size, and
   GAP STATISTICS (max adverse excursion between consecutive bars/ticks,
   weekends included), the last of which also sizes the §5.1 stop-limit
   band and its residual gap-through probability — added as a Stage-0
   deliverable (§6's Stage 0 row). A frozen update rule allows ONLY realized live-
   canary fills to later tighten those bounds (monotonically more
   conservative unless a pre-registered minimum sample is met), and
   explicitly FORBIDS retroactively re-scoring the historical WF gate or
   Stage-1 shadow evidence with updated bounds — the same post-selection/
   laundering problem this RFC's label freeze and the D6-§2a protocol both
   guard against elsewhere.

Additional tightening (ledger, §5.3): added idempotency-key semantics to
`reserve()` (keyed on `parent_intent_id`, already unique — a retried call is
a no-op, never a double reservation) with a TTL surfaced through the
existing orphan sweep rather than silent auto-release; added a broker-cash
RECHECK immediately before order submit (the local ledger cannot atomically
reserve real Alpaca buying power, and external/manual orders remain
possible) — a recheck failure is a real reconciliation mismatch, not a soft
warning, and triggers fail-closed-for-new-entries across EVERY sleeve
sharing the account (not just the sleeve that noticed), matching the
existing orphan/leak response.

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

## r3 update (2026-07-10) — third Codex review, one statistical blocker

Codex caught a real methodological bug in the r2 Stage 2.5 derivation: a
"200 bps/block non-inferiority margin" vs BTC meant the sleeve would PASS
the economic gate even while reliably LOSING up to 200 bps every 20 days to
simply holding BTC — incompatible with this RFC's own stated purpose
(§4.4: "the panel model must beat buy-and-hold BTC... or it does not
promote").

Fixed: reframed §6.1's endpoint as a SUPERIORITY test (`H0: excess_return ≤
0`), with the promotion rule now "one-sided lower confidence bound of
realized net-of-cost excess return over BTC must exceed 0" — not "must not
be too far below BTC." The 200 bps figure is retained but reframed as a
MINIMUM DETECTABLE EFFECT (MDE) for power-sizing purposes only — it no
longer relaxes the promotion threshold, which is fixed at zero. The
underlying arithmetic is unchanged (`N* ≈ 212 blocks ≈ 11.6 years` at 50%
sleeve vol, `≈ 847 blocks ≈ 46 years` at 100%) since a superiority test's
sample-size formula needs an assumed effect size to size N against, exactly
as the withdrawn non-inferiority formula needed a margin — the bug was in
the DECISION RULE (what the test passes on), not the equation. BTC
buy-and-hold is now explicitly the SOLE primary baseline for Stage 2.5; the
§4.4 historical WF gate's secondary "naive BTC-timing rule" is explicitly
demoted to secondary/descriptive status for the Stage 2.5 decision (no
multiplicity-correction plan is frozen or needed, since the WF gate is a
cheap exploratory historical screen, not the decision-grade prospective
test).

## r4 update (2026-07-10) — fourth Codex review, MDE governance

Codex accepted the r3 superiority-endpoint correction but caught a subtler
problem: the `δ=200 bps/block` MDE was still un-derived ("a plausible...
edge, not itself derived from data"). Since `N* ∝ 1/δ²`, an operator could
pick an arbitrarily LARGER δ to shrink `N*` and reach Stage-3 eligibility
sooner — even though the actual pass/fail bar (lower CI bound > 0) never
depends on δ. An un-derived δ is a hidden lever on the *timeline*, and had
to be frozen from principled inputs before any Stage-2.5 data, not picked
for tractability.

Fixed: derived `δ` from the three inputs Codex named — (1) capital-at-risk
= the $500 Stage-2.5 canary (not the eventual $1-2k Stage-3 figure); (2)
Stage-0 ex-ante cost bound = 25 bps taker/side, round-trip = 50 bps; (3)
minimum economically-material annualized objective, reusing this document
family's OWN established convention (the Deployment Governor RFC's r9 "2x
round-trip cost" non-inferiority-margin sizing rule) rather than inventing
a fresh number: `δ = 2 × 50 bps = 100 bps/block` (≈18.25%/yr simple,
≈92.3 bps/block compounded — within ~8%, confirming the linear
approximation is adequate for a detection threshold). Recomputed `N*` under
the frozen, more conservative δ: `≈847 blocks ≈46.4 years` at 50% sleeve
vol, `≈3,388 blocks ≈185.6 years` at 100% — MORE impractical than the
withdrawn illustrative 200bps figures (212/847 blocks), which is the
correct honest direction: a properly-derived, more conservative MDE makes
the sample-size requirement larger, not smaller, exactly what Codex's
round-4 review expected and explicitly sanctioned ("if no defensible MDE
exists, retain the conservative NO-GO rather than select one for
tractability" — this derivation didn't need that fallback, but lands on the
same qualitative NO-GO-favoring conclusion). Froze governance: owner =
operator (same role as every other capital-risk freeze in this RFC),
version = "MDE v1, frozen 2026-07-10," and an explicit immutability rule —
`δ` cannot change once the first Stage-2.5 block is collected; revising it
requires a new RFC version applied only to a future attempt, never
retroactively.

## r4 refinement (2026-07-10, same day) — cost-input tightening

A concurrent pass on the r4 fix tightened the cost-input derivation before
Codex's r5 review landed: switched from a fee-only cost figure to the FULL
Stage-0 friction bound (fee + spread/2 + slippage) as the eventual basis for
δ once Stage-0 completes, kept capital-at-risk as a one-sided check only
(cannot justify a larger δ), and confirmed the linear annual↔block mapping
as primary (compounded kept as a one-time sanity check). This introduced
the bug r5 corrects below: it framed the Stage-0 full-friction instantiation
as something that could RAISE δ from the fee-only figure, calling that "more
conservative."

## r5 update (2026-07-10, same day) — fifth Codex review, N*/δ direction bug

Codex caught a real mathematical error in the r4 refinement: `N* ∝ 1/δ²` (already
established in r4) means a LARGER δ gives a SMALLER N* — raising δ from
Stage-0 friction data would SHORTEN the sample-size requirement and pull
Stage-3 eligibility FORWARD, not push it back. The r4-refinement text's
"more friction ⇒ larger δ ⇒ larger N* ⇒ more conservative" reasoning had the
direction backwards — it wasn't a valid escape from the round-4 prohibition
on an upward-adjustable δ; it reintroduced exactly that anti-conservative
lever under different packaging.

Fixed: `δ` is frozen at the fee-only figure (`100 bps/block`) permanently
for this Stage-2.5 attempt — from this commit forward, not just after the
first block — and neither the Stage-0 full-friction instantiation NOR any
canary/shadow data may raise (or lower) it, ever. The full-friction bound
still governs two things this derivation does not touch: (a) the net-of-cost
return computation itself (higher realized friction correctly shows up in
the measured excess return, which is what the superiority test already
evaluates), and (b) initial canary position sizing/risk budgeting.
Conflating "the cost bound used to size positions and compute net returns"
with "the MDE used to size the sample" was the r4-refinement's error. `N*`
arithmetic is unchanged (100 bps/block was already the fee-only figure used
in the original r4 derivation): `≈847 blocks ≈46.4 years` at 50% vol,
`≈3,388 blocks ≈185.6 years` at 100%.
