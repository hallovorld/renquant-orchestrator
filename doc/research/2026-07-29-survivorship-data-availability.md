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

---

## Follow-up probes (same session) — a ZERO-COST path exists

Three further read-only probes, all `[VERIFIED — 2026-07-29]`:

1. **Our own OHLCV store is survivorship-biased too.** It holds 2,928 ticker
   directories, but **0 of the 9** probed known-delisted names are present
   (TWTR, ATVI, VMW, SIVB, FRC, CERN, XLNX, PXD, SPLK all absent). So the bias
   is not confined to the 830-name screen; it is in the price store beneath it.

2. **FMP's constituent endpoints are also gated.** Both
   `stable/sp500-constituent` and `stable/historical-sp500-constituent` return
   **HTTP 402** on the current plan. So option 2 via FMP costs the same upgrade
   as option 1.

3. **But the constituent-change history is available free.** The Wikipedia
   S&P 500 page carries a "Selected changes to the list" table with add/remove
   tickers AND dates. Fetched (1.5 MB, 2 wikitables) and probed for the same
   nine names: **7 of 9 found** — TWTR, ATVI, SIVB, FRC, CERN, XLNX, PXD
   (missing VMW, SPLK). That is 7/9 against Alpaca's **2/9**.

### What this changes in the recommendation

The recommendation stands (option 2, index constituents by date) but its
**price drops to zero for the S&P 500 universe**: the add/remove event history
is public, and FMP's price endpoint — which already works on our plan for
delisted tickers — supplies the bars once a symbol is known. The gated
registry was never the only way to learn who left.

Honest caveats before anyone treats this as done:

- **7 of 9, not 9 of 9.** VMW and SPLK were not found by the crude probe; both
  were acquisitions, and the changes table may record them under a different
  string or in an earlier section. Coverage must be measured properly, not
  inferred from a regex.
- **A scraped table is not a data contract.** Wikipedia's structure changes
  without notice, so a build depending on it needs a snapshot, a digest, and a
  fail-closed parser — the same discipline as any other frozen input.
- **S&P 500 is one universe choice, not the only one.** It defines a
  large-cap-only experiment; our panel is not S&P-defined today, so adopting it
  changes what the strategy is measured against. That is a design decision, not
  a data-sourcing detail.
- **Point-in-time reconstruction still needs care**: an add/remove event list
  must be replayed backwards from today's membership to get membership at date
  d, and any missed event silently corrupts every earlier date.

---

## Viability test of the free path — it FAILS the completeness bar

The zero-cost recommendation above was made on a regex probe. Parsed properly
`[VERIFIED — fetched + parsed 2026-07-29, snapshot sha256 9d11adaa871755a5,
1,509,483 bytes]`:

- the changes table yields **406 events**, **372 distinct removed tickers**,
  spanning **1976-07-01 → 2026-06-30**;
- known-delisted coverage is **7/9** — ATVI, CERN, FRC, PXD, SIVB, TWTR, XLNX;
- the two misses, **VMW and SPLK, have ZERO rows** in the table. Not a parser
  bug: they are absent.

**The table's own title says why: "Selected changes to the list of S&P 500
components."** It is a curated selection, not a complete corporate-action
record. The per-year density confirms it — 18 events in 2023 and 13 so far in
2026, against the ~20–25 changes the index actually makes in a typical year.

### Why "mostly complete" is not good enough HERE

For PIT membership you replay events backwards from today's list. **A missed
removal leaves that name in the reconstructed universe for every earlier
date** — i.e. it silently reintroduces exactly the survivorship bias the
exercise exists to remove, and it does so invisibly: the reconstructed
universe still looks plausible, just slightly too clean. Two known misses in a
nine-name spot check implies a systematic gap, not a rounding error.

### Corrected recommendation

The free path is **rejected as a source of truth**. It remains useful as a
CROSS-CHECK: any paid constituent history must reproduce these 406 events, and
a paid source that disagrees with a hand-curated public record on a name like
TWTR or SIVB is itself suspect.

That returns the decision to a **paid** constituent-history product (or an FMP
tier that unlocks `historical-sp500-constituent`), with the depth verified
before purchase — the same caution as before, now without a free alternative
to hope for. Cost is unquantified here because no vendor was priced; that is
the next step, not an assumption.

I am recording this reversal in full rather than quietly downgrading the
earlier recommendation: the free path looked viable on a 7/9 regex hit, and it
was the parse — plus reading the table's own title — that killed it.
