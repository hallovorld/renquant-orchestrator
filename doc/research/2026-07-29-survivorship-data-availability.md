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

---

## Second reversal — the completeness objection was MY inference error

I rejected the free path above on the strength of two "missing" names. That
inference was wrong, and the method that replaces it does not have the problem
I rejected it for.

### The two misses were correct behaviour

VMW and SPLK are absent from the S&P 500 membership table in revisions dated
**2022-06-29 and 2023-06-19** `[VERIFIED — Wikipedia revision API + parse,
2026-07-29]` — both well BEFORE their respective acquisitions. They were never
S&P 500 constituents, so their absence from a list of S&P 500 changes is
correct, not a gap. The spot check was therefore **7 of the 7 probed names
that were actually in the index**, not 7 of 9.

The density argument (18 events in 2023 vs ~20-25 expected) still suggests the
CHANGES table is not exhaustive. That objection simply no longer matters, for
the reason below.

### Point-in-time membership without any event replay

Wikipedia exposes full revision history, and the oldest revision of this page
is **2005-09-14** `[VERIFIED — revision API]` — covering the whole 2016-2026
panel window with a decade to spare. Membership at date `d` is read directly
off the page as it stood at `d`; there is no backwards replay, so **a missing
change event cannot propagate**. That was the single defect that killed the
event-list approach.

Sanity check across four independent temporal transitions, all correct
`[VERIFIED — parsed membership per revision]`:

| as-of | members | TWTR | ATVI | SIVB | AAPL |
|---|---|---|---|---|---|
| 2016-06-26 | 504 | out (joined 2018) | **in** | out | in |
| 2020-06-28 | 505 | **in** | **in** | **in** | in |
| 2023-11-20 | 503 | out (taken private 2022) | out (MSFT closed 2023) | out (failed 2023) | in |

Counts of 503-505 are the right order for a "500" index carrying multiple
share classes.

### Corrected status — viable, with real caveats, and NOT declared solved

This is the second reversal on this question in two hours, so the caveats get
stated as prominently as the finding:

- **Edit lag.** Membership as-of `d` is really "as last edited before `d`". A
  change made on the 3rd may land in the page on the 6th. For a 60-day-label
  study that is tolerable, but it must be MEASURED and reported, not assumed
  tolerable.
- **Crowd-edited source.** A revision can be transiently vandalised or
  malformed. A build on this needs per-revision sanity gates (member count in
  a plausible band, ticker shape, diff size vs the previous snapshot) that
  fail closed rather than silently ingesting a bad revision.
- **Share classes and ticker renames** need explicit handling; a raw symbol
  set is not a clean universe key.
- **Still one universe CHOICE among several.** Adopting S&P 500 changes what
  the strategy is measured against, which remains an operator decision rather
  than a data-sourcing detail.

The honest summary of three rounds: regex said yes, a parse said no, and
checking whether the "misses" were ever in the index said yes again — with a
better method than the one originally proposed. The lesson is the same one
this session keeps paying for: **a number that decides something must be
checked against what it actually means, not just recomputed more carefully.**

---

## Edit lag — MEASURED, and it points the dangerous way

The caveat above said the lag must be measured rather than assumed tolerable.
Measured against three known removals, by scanning every revision in a window
around each effective date and finding the first one that no longer lists the
name `[VERIFIED — Wikipedia revision API + per-revision parse, 2026-07-29]`:

| ticker | effective removal | first revision without it | lag |
|---|---|---|---|
| SIVB | 2023-03-15 | 2023-03-14 | **−1 day** |
| ATVI | 2023-10-13 | 2023-10-14 | +1 day |
| TWTR | 2022-11-01 | 2022-10-29 | **−3 days** |

Magnitude is small (|lag| ≤ 3 days here), but **two of three are NEGATIVE**,
and the sign is what matters. Editors act on the ANNOUNCEMENT, not the
effective date, so the page can drop a name **before it actually left the
index**. A universe built naively from "membership as of d" would therefore
exclude a name that was still investable on d — a mild look-ahead baked into
the universe definition itself, which is precisely the class of error this
whole exercise exists to remove.

### The mitigation, and why it is the safe direction

**Define the universe at date `d` from membership as of `d − BUFFER`,** with
BUFFER ≥ the worst observed negative lag plus margin. That converts a possible
small LOOK-AHEAD into a guaranteed small STALENESS: the universe may briefly
retain a name that has just left, which costs a little realism, and can never
contain foreknowledge, which would cost correctness.

A 7-day buffer covers the worst case here with better than 2× margin. It is
proposed, not frozen: `n = 3` events is a spot check, not a distribution, and
the buffer belongs in a prereg with a wider measurement behind it.

### Status after four rounds on this question

Viable, measured, and still not built. What is now established: the revision
history covers the window (back to 2005), membership snapshots reproduce four
known temporal transitions, the "missing tickers" objection was my own
inference error, and the edit lag is small but signed the wrong way with a
known mitigation. What remains: per-revision fail-closed sanity gates, share
class and rename handling, a properly-sized lag measurement, and the operator
decision on whether S&P 500 is the universe this strategy should be measured
against at all.
