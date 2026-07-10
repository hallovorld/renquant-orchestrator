# renquant105 Stage-1 shadow data — first systematic evaluation: entry execution timing

**Date:** 2026-07-10
**Status:** EXPLORATORY throughout — nothing in this memo is decision-grade; no gate is moved.
**Scope:** READ-ONLY analysis of the accumulated Stage-1 observe-only shadow data
(quote logger, entry-timing shadow arms, paired-arrival records) against roadmap P4:
*execution-quality residual is the controllable return*.
**Evidence:** `doc/research/evidence/rq105_first_eval/` (5 JSONs + the analysis script
`analyze_rq105.py` that produced every number below). All numbers `[VERIFIED]` against
those artifacts unless tagged otherwise.
**Prior art:** `2026-07-04-open-auction-is-measurement.md` (S10: fills competitive with
same-day VWAP, Apr–May sample); Phase −1 intraday-alpha NO-GO
(`2026-06-27-renquant105-phase-minus-1-results.md`, S-REL V6 UPHELD). This memo is the
first look at the *new* Stage-1 feed, not a re-adjudication of either.

## Bottom line

1. **The pipe works and is accumulating usable data.** 6 sessions (2026-07-02 →
   2026-07-10), **271,904 accepted quote samples** across **145 tickers** at a stable
   **~60 s cadence**, full 09:30–16:00 ET coverage from 07-06 on. Two mechanical feed
   defects should be fixed cheaply before this data feeds any prereg (§3).
2. **Spread data is bimodal and mostly NOT NBBO.** The feed is `alpaca-iex`
   (IEX top-of-book). Only **45/145 names** show a median spread ≤ 25 bps (SPY 0.4,
   NVDA 1.0, NFLX 1.4 bps — credible); **95/145 names** show medians > 50 bps up to
   1,012 bps (PNC), which is IEX book thinness, not the real market. Spread-cost
   conclusions are therefore restricted to the tight subset; on it, half-spread cost is
   **4.7 bps in the first 25 min vs 1.4–1.6 bps midday/close** (§4).
3. **No stable entry-window edge is detectable.** On the tight subset, SPY-adjusted
   window mids vs the official next-day open fill have medians between **−26 and
   +7 bps** with IQRs of ~±100 bps, and per-session medians flip sign day to day (§5).
   Consistent with S10 ("no large execution leak") and the Phase −1 NO-GO.
4. **Honest $ bound:** at current sizes (mean buy ≈ $496, ~250 entries/yr), a
   sustained **10 bps/entry improvement ≈ $124/yr**; 30 bps ≈ $372/yr (§7). The entry-
   timing program's value at today's ~$10.7k book is option value for a larger book,
   not current P&L.
5. **The decisive P4 dataset is still empty.** `paired_is.jsonl` has 5 records and
   **zero both-arm real fills** (every record censored `no_batch_fill`); the
   batch-arm fill capture must get wired before any execution-quality verdict (§6, R4).

## 1. Data sources (all read-only)

| Source | Content | Volume |
|---|---|---|
| `logs/renquant105_pilot/intraday_ticks.jsonl` | bid/ask/mid quote samples, schema v3 | 271,904 rows |
| `…/intraday_ticks.jsonl.censored.jsonl` | rejected samples + reason | 39,498 rows |
| `…/entry_timing_shadow.jsonl` | 4 hypothetical entry policies × 145 names × session | 3,480 rows |
| `…/entry_timing_policy_shadow.jsonl` | policy arms on real parent intents | 18 rows |
| `…/paired_is.jsonl` | paired batch-vs-intraday arrival records | 5 rows |
| `…/intraday_session_manifest_*.json` | per-session config/window/counters | 5 files |
| `logs/rq105/quote_logger_*.log`, `session_scheduler_*.log` | operational logs | 07-02 → 07-10 |
| `data/ohlcv/<T>/1d.parquet` | official open prints (fill proxy for the current convention) | — |
| `data/runs.alpaca.db` (ro) | `buy_pending` decisions since 06-22 | 27 unique |

Current convention being evaluated: the daily 104 run starts ~13:55 PT and submits
market orders ~14:07 PT = **17:07 ET, after the close** — they fill at the **next
session's opening auction** (verified: GRMN ordered 07-02 → `entry_dates` 07-06;
AVGO ordered 06-23 → entry 06-24). The comparison anchor for "current cost" is
therefore the next-day official open print.

## 2. Inventory

| Session | rows ok | censored | tickers | cycles | first–last tick ET | cadence p50 (s) | quote_age p50/p95 (s) |
|---|---|---|---|---|---|---|---|
| 2026-07-02 | 34,463 | 6,827 | 145 | 286 | 11:08–15:59 | 60.2 | 1.8 / 21.5 |
| 2026-07-06 | 38,484 | 7,789 | 145 | 321 | 09:30–15:59 | 60.3 | 1.8 / 20.8 |
| 2026-07-07 | 47,678 | 8,347 | 145 | 388 | 09:30–15:59 | 60.2 | 1.6 / 20.3 |
| 2026-07-08 | 49,660 | 6,465 | 145 | 389 | 09:30–15:59 | 60.2 | 1.6 / 21.1 |
| 2026-07-09 | 50,669 | 5,241 | 145 | 389 | 09:30–15:59 | 60.2 | 1.7 / 23.8 |
| 2026-07-10 | 50,950 | 4,829 | 145 | 389 | 09:30–15:59 | 60.2 | 1.9 / 25.5 |

- 07-02 was launch day (started 11:08 ET). 07-03 was the July-4 observed holiday
  (0 cycles; the launchd job's DNS errors that morning are cosmetic).
- Cadence is a clean 60 s loop; p95 cycle gap ≤ 61 s — **no intra-session outages**
  across the 6 sessions.
- 07-06 `session_scheduler` also crashed once on a missing
  `data/rq105/data_manifest.json` before recovering (see `session_scheduler_2026-07-06.log`).

## 3. Data-quality findings (both actionable, both cheap)

**DQ-1 — Clock-skew censoring discards the *best* names.** 39,240 of the 39,498
censored rows are `future_quote` (quote timestamp newer than local wall clock →
negative `quote_age` → rejected). The median "future" skew is **−0.054 s** (p5
−0.35 s) — pure NTP-level clock skew, not bad data. Because the fastest-updating
names hit this most, censoring is concentrated exactly in the most liquid tickers:
SPY loses 1,557 of ~2,162 cycles (**~72%**), XLK 1,556, NVDA 1,402, INTC 1,311,
AAPL 959. Net effect: the accepted sample under-represents the names whose quotes
are most trustworthy, and SPY (the natural market-adjustment anchor) is the single
worst-covered ticker. *Fix:* tolerate small negative `quote_age` (e.g. ≥ −2 s, clamp
to 0) or NTP-discipline the host; keep censoring genuinely stale quotes.

**DQ-2 — IEX top-of-book spread is not the NBBO for ~2/3 of the watchlist.**
Distribution of per-ticker median spreads: 33 names ≤ 5 bps, 45 ≤ 25 bps, but
**95 names > 50 bps** with a cross-ticker median-of-medians of **365 bps** and a max
of 1,012 bps (PNC). GRMN's displayed median "spread" of 570 bps is an IEX
thin-book artifact — its consolidated spread is a few bps. Two consequences:
(a) displayed spread must NOT be used as a cost input for those 95 names;
(b) their *mid* carries up to ±half-the-displayed-spread of uncertainty, so all
mid-based timing analysis below is restricted to the **tight subset (45 names,
median ≤ 25 bps)**. Getting real NBBO would require a consolidated/SIP feed — that
is the already-deferred ATP decision (re-trigger at M2 canary per the standing
operator decision); this memo does not request spend.

**DQ-3 — 0 crossed quotes, sane ages.** No `bid > ask` rows; accepted `quote_age`
p50 ≈ 1.6–1.9 s, p95 ≈ 21–25 s (within the 120 s policy). The feed is internally
consistent; the defects above are policy/venue issues, not corruption.

## 4. Spread distributions

Time-of-day buckets, tight subset (45 names — the only honest spread read),
half-spread = the incremental cost a marketable intraday order pays vs mid:

| Bucket (ET) | n | half-spread p50 (bps) | half-spread p95 (bps) |
|---|---|---|---|
| 09:35–10:00 | 3,899 | **4.72** | 306 |
| 10:00–11:30 | 14,409 | 2.35 | 171 |
| 11:30–14:30 | 34,055 | 1.55 | 63 |
| 14:30–15:30 | 12,047 | 1.41 | 98 |
| 15:30–16:00 | 5,310 | **1.37** | 193 |

Reading: entering in the first 25 minutes costs ~3.3 bps more (median) in spread
than entering after 11:30 — real, but small; the p95 tail (illiquid moments) is
where the actual risk lives. The full 145-name bucket table (inflated by DQ-2) is
in `spreads.json` for completeness: pooled medians 135–305 bps — do not quote those
as costs.

Recently-bought names, all-day median / p95 displayed spread (bps) — flagging which
are measurable at all on this feed:

| Ticker | p50 | p95 | Verdict on feed usability |
|---|---|---|---|
| NFLX | 1.4 | 6.5 | usable |
| AMZN | 2.8 | 35 | usable |
| CSCO | 3.5 | 371 | usable (day); open bucket noisy |
| MCHP | 21 | 694 | marginal |
| PANW | 47 | 601 | poor |
| AVGO | 81 | 455 | poor |
| CME | 429 | 1,017 | unusable (IEX artifact) |
| APH | 489 | 1,044 | unusable |
| ZM | 493 | 1,066 | unusable |
| FTNT | 513 | 1,109 | unusable |
| GRMN | 570 | 1,082 | unusable |

This alone is a material finding: **for most of what the strategy actually buys, the
Stage-1 feed cannot measure spread cost** (and its mid is noisy to ±½ displayed
spread).

## 5. Entry-window counterfactuals vs the current convention

Method: for each ticker-session, compare the time-averaged IEX mid in a window
against the same session's official opening print (OHLCV `open` — the fill proxy for
the current post-close market order). Positive bps = that window would have cost a
buyer MORE than the open fill. SPY-adjusted = minus SPY's same-window delta
(imperfect: SPY coverage is degraded by DQ-1). Tight subset only.

| Window (ET) | n | raw p50 | SPY-adj p50 | SPY-adj IQR | SPY-adj p5/p95 |
|---|---|---|---|---|---|
| open+5 (09:35–09:40) | 209 | +5.6 | −3.1 | −45 … +47 | −140 / +145 |
| midday (11:00–13:00) | 264 | +1.8 | +7.3 | −91 … +99 | −220 / +237 |
| close−30 (15:25–15:35) | 262 | +2.7 | −19.9 | −120 … +74 | −215 / +258 |
| near close (15:50–16:00) | 259 | +14.1 | −25.6 | −123 … +74 | −224 / +323 |

*n is the raw column's count; SPY-adjusted n is smaller (85/264/218/132 by row)
because DQ-1 censoring guts SPY's own window coverage.*

Per-session medians (tight subset, raw, bps vs open) show the sign is regime/day
noise, not structure:

| Session | open+5 | midday | close−30 | near close |
|---|---|---|---|---|
| 07-02 | — | +12.4 | +26.5 | +20.2 |
| 07-06 | +0.9 | +16.6 | +27.0 | +31.3 |
| 07-07 | +26.2 | −7.8 | −41.6 | −45.0 |
| 07-08 | −5.5 | −20.5 | −35.6 | −18.1 |
| 07-09 | −0.6 | +40.2 | +35.3 | +29.9 |
| 07-10 | +12.4 | +8.1 | +31.2 | +37.9 |

Reading `[VERIFIED]` for the numbers, `[GUESS]`-tier for any directional claim: a
−20 bps median at close−30 coexists with 4 of 6 sessions where waiting until late
day was *more* expensive. Six sessions of one calm-bull week cannot rank these
windows; the dispersion (IQR ~±100 bps) is the message — window choice is a ~1σ
±100 bps lottery per name-day against a ≤ 5 bps spread saving.

**Recent actual buys.** Decision-reference price → next-open fill proxy
("overnight slip", + = paid more), n = 21 unique buys 06-22 → 07-07 (CRWD excluded:
4:1 split back-adjustment makes its stored opens incomparable; the 4 buys placed
07-10 fill on 07-13 and are not yet observable):

- overnight slip: **mean −49.5 bps, median −20.2 bps**, range −414 (MCHP 07-07) to
  +170 (AVGO 06-24); excess over SPY: mean −40.4 bps.
- i.e. in these 3 weeks the post-close-order convention *gained* ~20–50 bps vs the
  decision price on average — no evidence of a bleeding entry in this window
  (matches S10's Apr–May conclusion). Small n, one regime, not a standing verdict.

Names whose fill session falls inside the feed window (counterfactual windows vs
their actual open-fill session; mid-noise caveats from §4 apply):

| Ticker (fill) | slip vs ref | open+5 | midday | close−30 | feed quality |
|---|---|---|---|---|---|
| GRMN (07-06) | +30.0 | −119 | +103 | −43 | unusable-tier mid |
| AVGO (07-07) | −196.6 | +17 | +58 | +205 | poor |
| MCHP (07-07) | −414.4 | −85 | −47 | +52 | marginal |
| ZM (07-08) | +11.7 | +3 | +191 | +184 | unusable-tier mid |

No pattern survives the mid-noise on these names; listed for completeness.

## 6. Shadow policy arms (mechanics, not performance)

`entry_timing_shadow.jsonl` (6 sessions × 145 names × 4 policies; baseline =
`immediate_first_eligible_tick` ~09:35). Entry price vs baseline, tight subset:

| Policy | eligible | p50 (bps) | mean | interpretation |
|---|---|---|---|---|
| vwap_cross | 867/870 | +7.1 | +29.6 | waits for VWAP cross → drifts with the tape |
| opening_range_breakout | 442/870 | +106.6 | +157.7 | fires only after strength → mechanically pays up; 49% never trigger |
| pullback_to_ref | 758/870 | −45.2 | −99.6 | fills only if price comes back → mechanically "cheaper", the 112 no-fills are exactly the runners |

These are **conditional entry-price mechanics, not execution quality and not
returns**: ORB's +107 bps is not a cost (it buys confirmation), pullback's −45 bps
is not a saving (it's adverse selection — you get filled when the name is weak, and
the censored 13% are the winners that ran). Any real adjudication needs
unconditional accounting (censored → forced entry at deadline) on arrival-anchored
pairs — which is what `paired_is.jsonl` is designed for and where the data is still
missing: **5 records, 0 both-arm fills, every record censored `no_batch_fill(+…)`**.
The `entry_timing_policy_shadow.jsonl` real-intent arm has 18 records over 2
sessions (6 intents; `delay_fixed` "saved" +316.9/+55.1 bps on 2 of 6, 0 elsewhere)
— far too small to read.

## 7. What is X bps worth? (the honest bound)

From `runs.alpaca.db`: 39 buys since 05-25, median notional **$336**, mean **$496**
(account equity ≈ $10.7k). At the stated ~250 entries/yr:

| Improvement | $/yr at current sizes |
|---|---|
| 5 bps | $62 |
| 10 bps | $124 |
| 20 bps | $248 |
| 30 bps | $372 |
| 50 bps | $620 |

Even the optimistic end of anything §5 could ever deliver (~20–30 bps, which the
data does NOT currently support) is worth ~$250–370/yr at this book size. The
correct framing for P4 stays: build the *measurement capability* (cheap, reusable,
scales with the book), don't chase the residual as current-book P&L.

## 8. Limitations

1. **6 sessions, one calm-bull week.** Zero power for directional window claims;
   per-session sign flips shown in §5. Detecting a true 10 bps day-level effect
   against ~30 bps day-median noise needs on the order of 70+ sessions (day-level
   observations are the effective n — name-sessions are cross-correlated).
2. **IEX top-of-book ≠ NBBO** (DQ-2): spreads unusable for 95/145 names; mids noisy
   to ±½ displayed spread; the tight-45 restriction is itself a liquidity-biased
   subsample.
3. **Censoring bias** (DQ-1): the most liquid names are under-sampled; SPY
   adjustment is built on the worst-covered ticker in the file.
4. **60 s sampling**: opening auction, sub-minute microstructure, and momentary
   liquidity are invisible; official opens were taken from daily OHLCV, which is
   back-adjusted (CRWD split exclusion in §5 is the cautionary example).
5. **Shadow ≠ fills**: all intraday "entries" are hypothetical mid-fills with no
   impact model; the paired-arms file that would anchor real execution-shortfall
   accounting has zero usable pairs so far.
6. **Survivorship of logged names**: the 145-ticker watchlist is the current
   universe snapshot; names added later have no history, and nothing delisted is
   represented.
7. Decision-reference prices in `trades` are pipeline reference prices, not
   broker-confirmed fills; the DB has no reconciled fill prices after 05-22, so
   "slip" in §5 is decision-ref → official-open, not ref → actual fill.

## 9. Recommendations (all shadow-side; no live-path change proposed)

- **R1 (fix, cheap):** eligibility tolerance for small negative `quote_age`
  (≥ −2 s, clamp to 0) or NTP-discipline the host. Recovers ~12.7% of samples,
  concentrated in the most valuable names. Config/one-liner in the quote logger's
  eligibility policy.
- **R2 (policy):** ban displayed IEX spread as a cost input outside the tight-45
  subset; annotate the watchlist with a per-name `iex_spread_usable` flag derived
  from this memo's `spreads.json`. Consolidated-feed upgrade remains parked behind
  the standing ATP/M2-canary trigger.
- **R3 (keep accumulating):** run the logger 4–6+ more weeks before freezing any
  entry-timing prereg; today's file supports engineering validation, not gates.
- **R4 (the real gap, P4-critical):** wire batch-arm fill capture into
  `paired_is.jsonl` — every record to date is censored `no_batch_fill`. Until both
  arms carry real (or pre-registered fill-model) fills, the execution-quality
  residual cannot be measured at all.
- **R5 (method):** any future policy-arm comparison must use unconditional
  accounting (censored day = forced deadline entry) per §6, or it will keep
  manufacturing pullback-style pseudo-savings.

*Produced read-only from the live logs; no production path touched. Analysis script
and JSON evidence: `doc/research/evidence/rq105_first_eval/`.*
