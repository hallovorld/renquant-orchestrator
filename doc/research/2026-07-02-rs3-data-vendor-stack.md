# RS-3: the data-vendor stack — recommendation memo (delegated decision, spend authorized)

STATUS: research recommendation (delegated per the 2026-07-02 grant; operator is NOTIFIED, not
asked — §1 of the merged route doc). Evidence tiers marked per claim; prices marked
[verify-at-checkout] where the vendor page was not directly probed this session.
DATE: 2026-07-02
NEEDS SERVED: (a) PIT fundamentals/estimates for M-SIG; (b) consolidated tape for 105 IS
measurement; (c) survivorship-free small/mid membership + history for M7. (#231 §1 Term IC/EXEC.)

## Recommendation (one line each)

| Need | BUY | Cost | When |
|---|---|---|---|
| (b) consolidated tape | **Alpaca Algo Trader Plus** — full SIP (CTA+UTP, 100% of volume) + OPRA options + 10k rpm | **$99/mo** [probed: alpaca.markets/data] | **NOW** — unblocks true-NBBO arrival quotes for the running collectors (#223 A5.3) |
| (a) PIT fundamentals/estimates | **keep FMP on the existing key** (stable endpoints verified returning estimates 2026-07-02); upgrade to **Starter $29/mo** ONLY if N2's first `--min-coverage` report fails; the load-bearing PIT asset is our OWN forward store (#233) — no vendor sells retail-priced true PIT estimate revisions | $0 now; +$29/mo conditional | decision falls out of N2's first run |
| (c) survivorship-free small/mid | **Norgate Data US (Platinum)** — delisted securities + **historical index constituency** (R2000/R3000 membership BY DATE — exactly M7's survivorship-clean panel spec) | ~$40–60/mo [verify-at-checkout] | at M7 kickoff (early Aug) — buying earlier buys nothing |
| (a-plus, conditional) | **Sharadar Core US bundle** (SEP prices + SF1 fundamentals, 14k+ tickers incl. dead, PIT `datekey` = filing date) as the M-SIG quality-factor substrate | ~$40–70/mo [verify-at-checkout] | ONLY if FMP's coverage report shows quality-factor gaps |

**Steady-state new spend: $99/mo now; realistic ceiling ≈ $170–230/mo by August** if both
conditionals trigger. All within the authorized data budget.

## Why these and not the alternatives

- **Alpaca ATP vs Polygon/Massive Advanced ($199/mo, full SIP)**: identical tape coverage at
  half the price, ZERO integration work (the collectors already speak the Alpaca SDK with the
  live keys), fills and quotes then share one venue-view/clock (cleaner IS pairing), and OPRA
  comes along for 107's options risk-shaping. Polygon wins only on flat-file bulk history —
  not a current need. [Probed: polygon.io/pricing → Advanced $199/mo; alpaca.markets/data →
  ATP $99/mo full SIP.]
- **FMP hold-not-upgrade**: the existing key already returns `stable` analyst-estimates
  (probed 2026-07-02); memory's "402 plan-locked ~30%" was measured on the LEGACY v3 endpoints
  — the stable-API coverage must be re-measured by the N2 collector's `--min-coverage` gate
  before spending. Deciding on measurement, not memory.
- **True PIT estimate revisions (IBES-class) are institutionally priced** — no retail vendor
  sells them. The honest path stays #233's forward accrual (which is why N2 is
  time-irreversible and outranks every purchase in this memo).
- **Norgate vs Sharadar for M7**: both are survivorship-free; Norgate's differentiator is the
  **index-constituency-by-date module** (point-in-time R2000 membership), which is literally
  the M7 panel-construction requirement (RS-5). Sharadar's differentiator is fundamentals
  (SF1) — hence its conditional slot on the (a) axis instead.

## Immediate actions (post-notification)

1. Subscribe **Alpaca Algo Trader Plus** on the live account ($99/mo) — after which the quote
   logger's NBBO is consolidated, not IEX-only; note the switch date in the collector meta so
   the IS corpus marks the feed-quality regime change.
2. N2 first run renders the FMP coverage verdict → Starter upgrade or not.
3. Norgate purchase enters the M7 kickoff checklist (RS-5).

Sources: [Alpaca market data plans](https://alpaca.markets/data) ·
[Alpaca market-data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) ·
[Polygon/Massive pricing](https://polygon.io/pricing) ·
[Nasdaq Data Link SEP](https://data.nasdaq.com/databases/SEP) ·
[Sharadar](https://www.sharadar.com/) — pricing pages not all directly probed; items marked
[verify-at-checkout] get final confirmation at purchase time.
