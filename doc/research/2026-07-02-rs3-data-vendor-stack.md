# RS-3: the data-vendor stack — recommendation memo (delegated decision, spend authorized)

STATUS: research recommendation (delegated per the 2026-07-02 grant; operator is NOTIFIED, not
asked — §1 of the merged route doc). Evidence tiers marked per claim; prices marked
[verify-at-checkout]/[unverified] where the vendor page was not directly probed this session.
**r2 (2026-07-02): corrected per Codex review** — Norgate pricing/integration model was wrong
(fixed-term, not monthly; Windows/VM + boolean-plugin, not downloadable lists), Alpaca "zero
integration" was overstated (entitlement verification now required before spend), the FMP
upgrade trigger is now an explicit decision rule, the "no retail vendor" PIT claim is narrowed
to this survey's actual scope, and Sharadar is reclassified as a separate fundamentals
candidate rather than an estimates-axis substitute. No purchases have been made under either
revision.
DATE: 2026-07-02
NEEDS SERVED: (a) PIT fundamentals/estimates for M-SIG; (b) consolidated tape for 105 IS
measurement; (c) survivorship-free small/mid membership + history for M7. (#231 §1 Term IC/EXEC.)

## Recommendation (one line each)

| Need | Recommendation | Cost | When |
|---|---|---|---|
| (b) consolidated tape | **Alpaca Algo Trader Plus** — full SIP (CTA+UTP, 100% of volume) + OPRA options + 10k rpm — **conditional GO, pending entitlement verification** (§ "Alpaca ATP — required verification before spend" below) | **$99/mo** [probed: alpaca.markets/data, confirmed by Codex 2026-07-02] | Entitlement probe + A/B capture FIRST; subscription start aligned to the #224/#227-gated N1b live-activation date, not before |
| (a) PIT fundamentals/estimates | **keep FMP on the existing key** (stable endpoints returned SOME data 2026-07-02 — coverage/cadence/PIT-semantics NOT yet established, see § below); upgrade to **Starter $29/mo** only per the explicit decision rule below | $0 now; +$29/mo conditional | decision falls out of N2's first real `--min-coverage` run |
| (c) survivorship-free small/mid | **Norgate Data US (Platinum)** — delisted securities + historical index constituency (R2000/R3000 membership BY DATE, exposed as a per-security/date boolean via vendor plugins — see § below) — **trial/POC-first, NOT a purchase commitment for M7** | $346.50 for a 6-month term OR $630 for 12 months — **no monthly plan; fixed-term, non-cancellable** [corrected 2026-07-02 per Codex review against current official pricing] | POC + 3-week trial acceptance test BEFORE any term commitment — do not schedule a firm M7 purchase date until that passes |
| (a-plus, conditional) | **Sharadar Core US bundle** (SEP prices + SF1 fundamentals, 14k+ tickers incl. dead) — a **separate fundamentals-axis candidate**, NOT a substitute for analyst-estimate-revision data (§ below) | ~$40–70/mo [unverified — not independently probed this session] | ONLY if FMP's coverage report shows quality-factor gaps, and only evaluated on the fundamentals axis |

**Steady-state new spend if Alpaca ATP entitlement verification passes: $99/mo now; realistic
ceiling ≈ $170–230/mo by August** if both conditionals trigger — Norgate's fixed-term cost is
NOT a monthly recurring number and must be budgeted as a $346.50/$630 lump commitment, not
folded into the "$40-60/mo" steady-state figure the prior revision used. All within the
authorized data budget, but the Norgate commitment size and non-cancellable term make the
trial-first gate load-bearing, not a formality.

## Why these and not the alternatives

- **Alpaca ATP vs Polygon/Massive Advanced ($199/mo, full SIP)**: identical tape coverage at
  half the price, and OPRA comes along for 107's options risk-shaping. Polygon wins only on
  flat-file bulk history — not a current need. [Probed: polygon.io/pricing → Advanced $199/mo;
  alpaca.markets/data → ATP $99/mo full SIP.]

  **"Zero integration" was overstated in the prior revision — corrected.** A subscription on
  the account does NOT by itself prove: (a) the collectors' actual API calls request
  `feed=sip` rather than defaulting to the free `iex` feed, (b) which feed was actually used
  is persisted per collected row, or (c) the LIVE trading key's entitlements are actually SIP
  after the subscription (a subscription and a specific key's entitlement can be distinct in
  Alpaca's system). **Required before this is spend-worthy, not optional polish:**
  1. A read-only entitlement probe against the live key confirming SIP access is genuinely
     active (not just that the account-level subscription exists).
  2. An A/B capture comparing SIP vs. IEX coverage/quote-counts on a sample window, to
     empirically confirm the upgrade delivers the broader coverage this memo assumes.
  3. Going forward, every collector row/run bundle stamps which feed was used, the plan tier,
     and the subscription-switch timestamp — so a future auditor can date exactly when data
     quality changed (mirrors the provenance-stamping pattern this session established
     elsewhere, e.g. #430's `output_content_sha256` / #426's `recipe_id` binding).
  4. **Align the subscription START DATE with the #224/#227-gated N1b live-activation
     gate** (established elsewhere this session — the collectors this feed serves are blocked
     from live activation until both those PRs merge to main). Subscribing before that gate
     clears burns paid time on a feed nothing is yet authorized to consume live.

- **FMP hold-not-upgrade, decision rule made explicit.** The existing key's `stable`
  analyst-estimates endpoint returned SOME data when probed 2026-07-02 — that establishes only
  that the endpoint is reachable, NOT universe coverage (how many tickers), endpoint coverage
  (which fields), revision cadence (does history actually accrue, or overwrite), or PIT
  semantics (is what's returned genuinely point-in-time, or does it silently restate).
  Memory's "402 plan-locked ~30%" figure was measured on the LEGACY v3 endpoints and does not
  settle the stable-API question either way. **Decision rule:** once #233's N2 collector has
  run for real and produced a `--min-coverage` report, upgrade to Starter ($29/mo) if and only
  if that report shows the free tier's usable-revision-history coverage falls below the
  Stage-1 census requirement for the target universe; hold on the free tier otherwise. This
  memo does not yet know which side of that line the free tier falls on — that is precisely
  what N2's first real run is for.
- **PIT estimate revisions (IBES-class): narrower claim.** No retail vendor was VERIFIED in
  THIS survey, at the authorized budget, to sell true point-in-time analyst-estimate-revision
  history — narrowed from the prior revision's unqualified "no retail vendor sells them."
  Vendors/fields actually checked this session: Alpaca (market data plans — no
  estimates/fundamentals product), FMP (`stable` analyst-estimates endpoint, reachability
  only, coverage unmeasured), Sharadar (SF1/SEP bundle pages — not probed for an
  estimate-revision-specific product; see below), Norgate (equities/index data — no
  estimates product). This is not an exhaustive retail-data-vendor survey; it reflects only
  what was checked in this session's authorized-budget scope. The honest path stays #233's
  forward accrual (which is why N2 is time-irreversible and outranks every purchase in this
  memo) — that conclusion does not depend on the categorical claim being softened.
- **Norgate for M7 — pricing and integration reality corrected (second pass).** The prior
  revision's "~$40–60/mo" figure was wrong; a first correction (2026-07-02) replaced it with
  "$476.50/6mo, $833/12mo," which Codex's direct check against the official US Platinum package
  page (retrieved 2026-07-02) found was ALSO wrong. Current figures per that check: $346.50 for
  a 6-month term or $630 for 12 months, no monthly plan, fixed-term and non-cancellable, quoted
  in USD. **Pricing metadata:** retrieval date 2026-07-02 (Codex review-time check against the
  official package page — this fork did not independently re-verify live pricing); confirm the
  live figure before any actual purchase, since vendor pricing pages change without notice.
  Tax treatment is unaddressed here (a business purchase may carry sales/use tax depending on
  jurisdiction — confirm separately before committing). These figures do NOT include the
  separate Windows/Windows-VM environment Norgate's proprietary database requires (see below) —
  that implementation cost is not yet estimated and must be added to total cost of ownership
  before a purchase decision (a small always-on cloud Windows VM is a reasonable placeholder to
  price out, e.g. AWS/Azure Windows instance + storage, but no specific figure is committed
  here). It is also NOT a simple API/download integration for this Python pipeline: Norgate stores data in
  a proprietary database that requires a Windows or Windows-VM environment, and historical
  index-constituency membership (the exact R2000/R3000-by-date feature this memo wants for
  M7's survivorship-clean panel spec) is exposed through supported plugins as a
  **per-security/date boolean lookup**, not as a downloadable constituent list — a materially
  different integration shape than this memo previously assumed. **Before any purchase
  commitment:**
  1. A Windows/VM + plugin integration POC proving the boolean-lookup interface can actually
     feed this pipeline's panel-construction needs at the required scale/cadence.
  2. Explicit review of export/licensing constraints — can extracted data be persisted and
     used within this system's own stores, or is it query-only against Norgate's proprietary
     DB (this changes whether it can ever become a durable, auditable input to M7).
  3. Treat the fixed-term, non-cancellable cost as a real $346.50–$630 commitment, not a
     trial — there is no monthly opt-out.
  4. A 3-week trial acceptance test, with defined pass/fail criteria, completed BEFORE
     committing to either term.
  **This downgrades Norgate from "M7 kickoff purchase" to trial/POC-first** — do not schedule
  a firm purchase date until the POC and acceptance test both pass.
- **Sharadar reclassified — not a substitute on the estimates axis.** The prior revision's
  table listed Sharadar as an "(a-plus)" conditional alongside PIT fundamentals/estimates.
  That's wrong: Sharadar's `datekey` field represents FILING dates (when a fundamental
  disclosure was made) — that is not equivalent to forward-looking analyst-ESTIMATE-REVISION
  history, a fundamentally different data axis. Sharadar is reclassified here as a **separate
  fundamentals-data candidate** (quality-factor substrate for M-SIG), evaluated only against
  FMP's fundamentals coverage gaps, never as a stand-in for the estimates axis. Its pricing
  and access have not been independently verified this session — the ~$40-70/mo figure
  carried over from the prior revision is unverified, not confirmed.

## Immediate actions (post-notification)

1. **Alpaca Algo Trader Plus — do NOT subscribe yet.** First: run the read-only entitlement
   probe + SIP-vs-IEX A/B capture (§ above). Then align the actual subscription start with the
   #224/#227-gated N1b live-activation date. Only after both: subscribe ($99/mo), and note the
   switch date + feed identity in the collector meta so the IS corpus marks the feed-quality
   regime change.
2. N2 first run renders the FMP coverage verdict → Starter upgrade or not, per the explicit
   decision rule above.
3. **Norgate: schedule the Windows/VM + plugin integration POC and 3-week trial acceptance
   test, not a purchase.** A firm M7-kickoff purchase date is not authorized by this memo until
   that POC/trial passes and the fixed-term commitment ($346.50/6mo or $630/12mo,
   non-cancellable) is explicitly accepted.
4. Sharadar: evaluate only if/when FMP's coverage report shows a fundamentals-axis gap;
   pricing/access still need independent verification before any recommendation, not just at
   checkout.

Sources: [Alpaca market data plans](https://alpaca.markets/data) ·
[Alpaca market-data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) ·
[Polygon/Massive pricing](https://polygon.io/pricing) ·
[Nasdaq Data Link SEP](https://data.nasdaq.com/databases/SEP) ·
[Sharadar](https://www.sharadar.com/) — pricing pages not all directly probed; items marked
[verify-at-checkout] or [unverified] get final confirmation before any purchase decision.
Norgate pricing ($346.50/6mo, $630/12mo, no monthly plan) and integration model
(Windows/VM + per-security/date boolean plugin interface) corrected 2026-07-02 per Codex
review against current official documentation — not independently re-probed in this fix.

---

## r2 addendum (2026-07-02, operator cost review): ATP DEFERRED

The operator challenged the $99/mo Alpaca ATP recommendation on cost. The challenge is
CORRECT and the recommendation is revised:

- **The arithmetic the r1 memo under-weighted**: $99/mo = ~$1,190/yr ≈ **11%/yr of the
  current $10.8k book** — measurement-precision spend an order of magnitude out of
  proportion to the book it measures.
- **What ATP is NOT needed for now**: opening-auction prints (the S10 references) come from
  official DAILY bars already on hand; the S10 study and its successor runs need no live
  SIP. Stage-1 collectors run observe-only — the IEX-only NBBO bias affects diagnostic
  precision, not safety, and is now **accepted + documented** (the #223 A5.3 second path):
  every collector row already carries its feed identity; analyses label the regime.
- **FMP Starter is NOT a substitute and was never the question**: FMP = fundamentals/
  estimates (need (a), now CONFIRMED subscribed — key-metrics + 10-year estimate depth
  verified 2026-07-02); ATP = real-time consolidated tape (need (b)). Different data;
  deferring (b) does not touch (a).
- **Re-trigger conditions (recorded)**: M2 canary go-live (real orders need honest arrival
  NBBO) OR book ≥ $50k (the %-of-book arithmetic flips) — whichever first.

Steady-state new spend drops to **$0/mo now** (FMP already active); Norgate stays at the
M7 kickoff slot.
