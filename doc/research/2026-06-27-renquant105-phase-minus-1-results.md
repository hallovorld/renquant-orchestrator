# renquant105 Phase -1 — measured cheap-feasibility results (read-only)

**Run timestamp (UTC):** 2026-06-27T19:08:06Z
**Script:** `scripts/research_phase_minus_1_feasibility.py` (read-only; data API only; no orders;
no writes outside this repo).
**Design spec / pre-registered STOP-GO:**
`doc/design/2026-06-27-renquant105-Phase-minus-1-cheap-feasibility.md` (branch
`design/renquant105-intraday`, design PR **#198**).
**Verdict:** **GO to M0** under the doc's pre-registered table — *with one material caveat the
table does not gate on* (negative net-edge band; see §6).

This is the FIRST gate in the renquant105 master DAG: a bounded, read-only go/no-go that runs
BEFORE the 10-17-week M0->M3 build. The single most load-bearing 105 assumption is the open->close
cross-sectional dispersion `sigma_oc ~= 150-250 bps`, which §A **ASSUMES** (a prior, not a
measurement). Phase -1 measures it (and three siblings) cheaply and applies the pre-registered
STOP/GO table EXACTLY — no post-hoc threshold tuning.

## 1. Data sources & universe snapshot (auditability)
- **Universe:** the **live pinned strategy-104 watchlist**, read READ-ONLY from
  `/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.json`. It is
  byte-for-set identical to `strategy_config.golden.json` (**142 names, identical sets**), so this
  is the production universe — no synthetic basket was needed. The 142 names include 8 ETFs
  (GLD, SPY, XLE, XLF, XLI, XLK, XLU, XLY) which are tradable single instruments and kept in-place.
- **Market data:** Alpaca `StockHistoricalDataClient` (read-only data API). **Feed: SIP** (the full
  consolidated tape), with `end` capped to ~16 min ago because the subscription forbids querying
  the most-recent ~15 min of SIP; IEX is wired as an automatic fallback (not needed this run).
- **Daily window:** 2021-06-22 -> 2026-06-27, **1258 trading sessions**, all 142 names present.
- **Intraday sample:** the most recent **30 RTH sessions** of 1-minute SIP bars (BOUNDED — not 5y
  of minute data).
- **Spread sample:** a midday (noon-ET) historical RTH quote window on the last closed session
  (2026-06-26), 12 names.

## 2. THE LOAD-BEARING NUMBER — causal open->close `sigma_oc` (bps)
Per-session cross-sectional dispersion of the intraday open->close return `r_i = close_i/open_i - 1`
across the 142 names, over 1258 sessions. Both a plain population std and robust (MAD/IQR) scale
estimates are reported, in bps.

| Estimator | median | p25 | p75 | mean | min | max |
|---|---|---|---|---|---|---|
| **std-based** (the §A comparand) | **152.5** | 130.3 | 186.7 | 163.3 | 61.6 | 533.2 |
| robust MAD->std | 114.0 | 95.6 | 139.0 | 123.1 | 46.0 | 505.1 |
| robust IQR->std | 115.1 | 96.2 | 141.3 | — | — | — |

**Assumed §A band: 150-250 bps.**

- The **std-based median (152.5 bps) lands just inside the assumed band's lower edge** (150 bps).
- The **robust** (outlier-resistant) estimates are materially **lower (114-115 bps)** — the
  std-based number is pulled up by a fat right tail (max 533 bps on shock days). So the *typical*
  name-to-name dispersion is ~115 bps; the std reaches the 150 floor partly via tail mass.
- **Causal / event-time check (finding 1).** To confirm the daily-OHLC `sigma_oc` is not inflated
  by the opening cross, dispersion was recomputed on the 30-session intraday sample with **entry at
  the first RTH bar >= 09:35 ET** (a proxy for the event-time contract's `first_eligible_fill_ts`,
  excluding the opening print) and **exit at the last RTH close**: **median 200.2 bps** (p25 165.1,
  p75 224.8, n=30). The causal dispersion is *higher*, not lower — the daily-OHLC proxy is therefore
  **not** inflated by the opening cross; if anything it is conservative. (Caveat: this causal leg is
  a 30-session sample, not the full 5y, so it is directional support, not the primary estimate.)

**Bottom line on (b):** the pre-registered criterion is "std-based median >= ~150 bps", and the
measured **152.5 bps clears it** — but only barely, and the robust estimators sit below the floor.
This is a *knife-edge* PASS, not a comfortable one.

## 3. Universe breadth (Fundamental-Law `sqrt(breadth)`)
Every one of the 1258 sessions has all **142 names with a valid open & close** (median = p25 = p75
= min = max = 142). Effective realistic breadth therefore = **142 names/session**, vastly above the
pre-registered "**>= ~4 effective independent bets/day**" floor. Criterion (c) passes with huge
margin. (Note: 142 *names* is the raw pool, not 142 *independent* bets — names are correlated; the
§A "~4 independent bets" is the independent-DoF estimate the program must still earn at M1. Phase -1
only verifies the realistic pool is not thin, which it clearly is not.)

## 4. Intraday data availability / coverage census
On the 30-session RTH minute sample: **142 / 142 names have intraday history; 0.0% have none.**

> **Design's "~50% of names had no intraday history" (2026-05-04 disable cause) is REFUTED today.**
> Every name in the live universe has clean, dense minute coverage in the recent sample. Whatever
> caused the May-2026 coverage gap is **not** present in the data Alpaca serves now. (This Phase -1
> sample is recent-window coverage on the *current* universe — it does not retro-audit the historical
> 2026-05-04 cache that triggered the disable; M0's point-in-time universe build remains responsible
> for any historical-coverage requirement.)

## 5. Conservative executable-cost bound
Measured from a midday RTH historical-quote sample (2026-06-26, 12 names): per-name median
half-spreads ranged **0.54 bps (AAPL) to 6.8 bps (APP)**; sample median half-spread **3.10 bps ->
measured round-trip ~6.2 bps** (p75 round-trip ~8.6 bps). Because the spread is only one leg and the
§A `~11 bps` prior also covers impact/slippage, the **conservative round-trip bound is floored at the
documented `11 bps` prior**. The measured spread (~6 bps round-trip) **confirms the 11 bps prior is
conservative, not wildly optimistic** — criterion (d) (`<= 17 bps`) passes.

*(Note: live latest-quote endpoints return stale/locked closing quotes when the market is shut —
they showed absurd ~500 bps half-spreads — so the cost bound deliberately uses **historical RTH**
quotes, not the latest-quote endpoint.)*

## 6. Measured net-edge band (`gross = IC * sigma_oc * factor`, `net = gross - cost`)
Using the §A edge identity with the MEASURED std-based `sigma_oc = 152.5 bps`, `factor = 1.0`
(conservative 1-sigma top-name selection), and the conservative `cost = 11 bps`:

| IC | gross edge (bps) | round-trip cost (bps) | **net edge (bps)** |
|---|---|---|---|
| 0.03 | 4.6 | 11.0 | **-6.4** |
| 0.05 | 7.6 | 11.0 | **-3.4** |

**The measured net-edge band is NEGATIVE at both IC anchors.** At a realistic intraday IC of
0.03-0.05 the top-pick gross open->close edge (4.6-7.6 bps) does **not** clear the conservative
11 bps round-trip cost.

**Why the verdict is still GO:** the design doc's pre-registered STOP/GO table gates on four binary
conditions — (a) coverage, (b) `sigma_oc >= 150`, (c) breadth, (d) `cost <= 17`. **Net-edge is a
*reported* measurement, not a pre-registered gate** in that table. Applying the table EXACTLY (the
explicit instruction — no inventing thresholds), all four conditions pass -> **GO to M0**. But the
negative net-edge band is the single most important quantitative finding for M0 to confront: it says
the §A "marginal-to-viable" case is, on these cheap measured numbers, **marginal-to-underwater** at
plausible IC. M0/M1 must show either (i) a higher realized IC, (ii) a `sigma_oc` nearer the top of
the band, or (iii) a lower realized cost, or the program does not clear cost.

## 7. Pre-registered STOP/GO decision (applied EXACTLY)
| Criterion | Threshold (pinned) | Measured | Pass? |
|---|---|---|---|
| (a) intraday names | >= ~30-40 | 142 | **PASS** |
| (b) causal `sigma_oc` median | >= ~150 bps | 152.5 bps (std) | **PASS (knife-edge)** |
| (c) effective breadth | >= ~4 bets/day | 142 names | **PASS** |
| (d) conservative cost | <= ~17 bps | 11.0 bps | **PASS** |

### VERDICT: **GO to M0** (all four pre-registered conditions met)

…**with a pinned caveat for M0 (NOT a STOP, but the decisive risk):** (1) the `sigma_oc` PASS is on
the std estimator and is *knife-edge* (152.5 vs 150; robust estimators 114-115 bps sit *below* the
floor); and (2) the **measured net-edge band is negative at IC 0.03 and 0.05**. A Phase -1 GO only
means "the full stack is worth standing up"; it does **not** assert tradability. M0 (proper
point-in-time universe + calibrated stratified cost model) and M1 (frozen-policy replay) must
re-measure and clear the net-edge hurdle, which Phase -1's cheap bounds do not.

## 8. Reproduce
```bash
cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a   # read-only data keys
/Users/renhao/git/github/RenQuant/.venv/bin/python \
  /path/to/renquant-orchestrator/scripts/research_phase_minus_1_feasibility.py        # human report
/path/to/.../scripts/research_phase_minus_1_feasibility.py --json                      # machine JSON
/path/to/.../scripts/research_phase_minus_1_feasibility.py --offline                   # plan only, no network
```
Pure helpers are unit-tested network-free in `tests/test_research_phase_minus_1_feasibility.py`.

## 9. Guardrails honoured
- READ-ONLY throughout. Zero writes / zero git to `/Users/renhao/git/github/RenQuant`; `.env` and the
  strategy config were only **read**. No canonical data path touched. Data API only — no orders, no
  broker-state change. All deliverables live in a fresh `/tmp` clone of the orchestrator repo.
- `≤ 5 analyst-days / ≤ 1 week` cap: all four measurements produced in a single bounded run
  (sub-minute wall-clock) on existing/available data — the cap is met with enormous margin.
