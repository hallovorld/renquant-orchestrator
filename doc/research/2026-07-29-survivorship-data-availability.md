# Survivorship fix — what the existing subscriptions can and cannot buy

Date: 2026-07-29. Status: findings + a costed decision, no spend made.

GOAL-6 Stage 1 built the breadth panel and failed its survivorship criterion:
0 of 23 probed known-delisted large caps present, zero exits in 10.3 years,
830 names that are a today-alive screen. Any Stage-2 result on it inherits the
bias. This probes whether the fix is available on what we already pay for.

## Measured, this session `[VERIFIED — live API probes, read-only]`

| capability | source | result |
|---|---|---|
| bars for a **known** delisted symbol | FMP `stable/historical-price-eod/full` | **WORKS.** TWTR returns **459 bars ending 2022-10-27** — its real final trading days |
| the delisting **registry** (enumerate who left, and when) | FMP `stable/delisted-companies` | **page 0 only**: 100 rows spanning 2026-07-02…07-27. Page 1 returns **HTTP 402 Payment Required** on the Starter plan |
| an inactive-symbol universe | Alpaca `/v2/assets?status=inactive` | **19,209 symbols** — but OTC-dominated (16,355 OTC vs 1,310 NASDAQ / 845 NYSE / 97 AMEX), and it hits only **2 of 9** probed known-delisted majors (CERN, XLNX; misses TWTR, ATVI, VMW, SIVB, FRC, PXD, SPLK) |

## What that means

The constraint is precise and it is **not** the price data:

- **We can already fetch history for a delisted name once we know its ticker.**
- **We cannot enumerate the delisted universe.** FMP gives ~4 weeks on this
  plan; Alpaca's inactive list is not a delisting registry — it is whatever
  Alpaca stopped carrying, which misses 7 of 9 large-cap delistings we
  checked and drowns the rest in OTC.

So survivorship is blocked on a **symbol list**, not on prices, and the
missing list is exactly the expensive part of any vendor's product.

## Options, costed

1. **FMP tier upgrade** — unblocks `delisted-companies` paging directly, and
   the price endpoint already works. Cost: the delta above Starter ($29). This
   is the cheapest path IF the registry's history reaches back to 2016; the
   probe cannot confirm depth because page 1 is gated. **Verify depth before
   paying** — a plan that pages further but still only covers recent years
   buys nothing.
2. **Historical index constituents** (e.g. S&P 500 membership by date) — a
   different product, gives PIT membership rather than a delisting registry.
   Solves survivorship *for an index-defined universe*, which is arguably the
   better-defined experiment anyway.
3. **Reconstruct from what we hold** — the panel's own history plus EDGAR
   filings can identify names that stopped filing, but conflates delisting
   with acquisition, going private, and filer-status changes. Cheap, noisy,
   and hard to defend in a prereg.
4. **Scope down** — run Stage 2 on an explicitly today-alive universe and
   report the survivorship bias as a stated limitation rather than pretending
   it is absent. Costs nothing and is honest, but every number it produces
   carries an asterisk that cannot be removed later.

## Recommendation

**Option 2, then 1.** An index-constituent-by-date list defines the universe
the strategy actually competes against, and it makes "who was investable on
date d" answerable without a delisting registry at all. Option 1 is the
fallback if constituent history proves harder to source than the tier upgrade.

**Not option 4 silently.** If Stage 2 runs before this is fixed, its
limitation section must state the bias in the same place its results are
quoted, not in a footnote.

## What this probe does NOT establish

Whether FMP's paid registry reaches back to 2016 (page 1 is gated, so depth is
unmeasured); what an index-constituent product costs; and whether Alpaca's
inactive list would be adequate after filtering to names that ever appeared in
our panel — that last one is cheap to check and is the obvious next probe.
