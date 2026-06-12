# Design v2 — Short-Selling Capability (evidence-first rewrite)

**Status:** design / awaiting review (no code change)
**v2 rationale:** v1's Phase-1 entry ("short the bottom of the rank") was
**empirically vetoed** by the operator's own calibration protocol before any
code was written. v2 rebuilds the design around that finding and specifies the
experiment suite that must produce a validated entry signal before any
single-name short trades.

---

## 1. The calibration result that reshaped this design (measured)

Operator protocol: take the past year's lowest model scores, check whether
those stocks actually fell and whether a short entry would have profited; use
the cutoff as the future entry baseline.

| Sample (validation year 2025-02→2026-02) | fell (60d) | underperf. SPY | naked short P&L | hedged short P&L |
|---|---|---|---|---|
| 20 lowest scores (all) | 25% | 40% | **−5.2%** | −2.4% |
| 50 lowest (all) | 24% | 48% | −3.7% | −1.4% |
| 50 lowest (**ETFs excluded**) | 36% | 46% | **−7.5%** | −3.8% |

Who occupies the bottom: XLF/XLY/XLI/SPY (ETFs), MCD/MA/KO/CVX/INTU (defensive
quality mega-caps). **The ranker's "lowest score" means "will lag a bull tape,"
not "will fall."** Shorting it = shorting defensiveness = paying the equity
premium. The two worst events were mean-reversion rips (INTU +18%, LMT +19%).

**Design consequence: a raw-score threshold can NEVER be the short trigger for
this model family.** Any single-name short signal must be discovered and
validated by the experiment suite in §4 — until one passes, **Phase 1 does not
trade**.

## 2. Operator mandate (binding)

1. **Very high bar — default NO SHORT.** Entry signal must come from a
   §4-validated trigger (raw-score threshold already failed).
2. **Max 2 concurrent single-name shorts** (`risk.short.max_positions=2`).
3. **No regime precondition** — signal strength is the gate, in any tape.
4. Sub-PDT account: multi-day shorts only; runner counts day-trades.
5. Margin budget ≤ 20% NAV; Alpaca ETB-only; squeeze guard (PIT short-interest
   collector: days-to-cover, %float), earnings ±3d veto, borrow-fee cap,
   ex-dividend veto, hard stop mandatory.

## 3. Phases (unchanged shape, re-gated)

- **Phase 0 — index hedge** (short SPY / long SH) on risk-off triggers.
  Independent of §1's veto (no single-name signal needed). Gate: replay
  evidence of drawdown reduction net of cost (§4 E6).
- **Phase 1 — single-name shorts**: BLOCKED until a §4 trigger passes.
  **Literature prior (see literature review doc): likely fails in an ETB-only
  universe** (Drechsler & Drechsler; Muravyev et al. 2025) — burden of proof
  fully on the experiments.
- **Phase 2 — dollar-neutral sleeve**: only on Phase-1 evidence.

## 4. Experiment suite (each pre-registered; promote only on pass)

**Common protocol:** validation-year events (extend to 2 years when PIT models
allow), ≥50 events per candidate trigger, metrics = hit rate (fell), hedged &
naked P&L net of borrow (~1%/yr ETB assumption) and costs, max single-event
loss (squeeze tail), event-overlap accounting. **Pass bar (pre-registered):
hit-rate(fall) ≥ 55% AND net hedged mean P&L > 0 AND stop-simulated max single
loss within −25%.** Universe: single names only (no ETFs).

| # | Candidate trigger | Hypothesis | Status |
|---|---|---|---|
| **E1** | Raw-score floor (operator protocol, 20/50 lowest) | lowest score → falls | **DONE — FAILED** (24–36% hit, negative P&L) |
| **E2** | **Inverted protection**: calibrated μ < −τ_strong on ≥3 consecutive days | sustained bearish μ ≠ one-day low score; debounce may purge defensive-laggard noise | next |
| **E3** | **Broken momentum**: rank falls from top-half → bottom-decile within ≤10 days | fresh breakdowns fall further (short-side momentum continuation) | next |
| **E4** | E2/E3 ∩ **price < 200-DMA** | never short an uptrend; trend filter as veto | after E2/E3 |
| **E5** | E2/E3 ∩ **short-interest dynamics** (rising shares-short, DTC mid-band) | informed-short confirmation (Boehmer et al.); needs FINRA backfill | blocked on backfill |
| **E6** | **Phase-0 hedge replay**: 2022 bear + 2025-04 dip + dead window; hedge ratio h·β by drawdown/breaker state | hedge cuts MaxDD more than it costs | independent, can run now |
| **E7** | Horizon/stops: 20d vs 60d holds × stop levels on whichever of E2–E5 passes | shorts may need shorter horizons than longs | last |

Sequencing: **E6 (hedge) and E2+E3 first** — E6 needs no new signal; E2/E3 are
computable from existing artifacts today. E5 wires in the FINRA backfill.
All experiment code/results live on `epic/model-edge-experiments`; nothing
merges to main; any passing trigger then goes through the standard WF-gate +
shadow + operator-review pipeline before real orders.


## 4.5 Short exit design (cover triggers, priority-ordered)

Shorts are NOT mirrored longs. Three asymmetries drive the design:
(a) **loss is unbounded and a losing short GROWS its own exposure weight**
(a rising name takes up more NAV — the opposite of a losing long, which
shrinks itself); (b) **profit is bounded at 100%** and decays — time costs
borrow fees + dividend liability; (c) **gap risk is asymmetric** (buyout/
short-squeeze headlines gap UP). Hence: tighter stops than longs, intraday
monitoring, shorter time barrier, hard event vetoes.

Priority chain (first match covers; mirrors the long exit-chain architecture):

| # | Trigger | Rule | Class |
|---|---|---|---|
| 1 | **Hard stop** | adverse move ≥ min(+12%, 2.5σ_daily·√h) from entry; evaluated EOD AND on the existing ~12-min intraday rail (cover-only orders). Gap-up beyond stop → cover at next open, no anchoring | hard risk |
| 2 | **Broker/borrow risk** | leaves ETB, borrow fee > cap, DTC blows out, or buy-in notice → immediate cover | hard risk |
| 3 | **Event veto** | earnings within 3d → cover ahead; ex-dividend where dividend > borrow-adjusted edge → cover before ex-date | hard risk |
| 3b | **Rebound veto (entry-side)** | no NEW shorts while SPY 60d ret < −10% AND 5d ret > +3% (momentum-crash window, Daniel–Moskowitz 2016) | hard risk |
| 4 | **Profit lock (trailing)** | after favorable move ≥ 15%, trail: cover if price retraces 1/3 of max favorable move. Bounded-profit asset ⇒ lock, don't ride forever | profit |
| 5 | **Signal exit (inverted protection w/ hysteresis)** | entry was μ < −τ_strong for ≥3 consecutive days; cover when μ > −τ_weak (τ_weak < τ_strong, hysteresis band) for ≥2 consecutive days — debounced both directions | signal |
| 6 | **Rank exit** | name climbs out of the bottom quintile of the cross-section → thesis gone → cover | signal |
| 7 | **Time barrier** | maximum hold for shorts is SHORTER than longs — default 20 trading days, tuned by E7 (borrow + drift make time the short's enemy; the 60d long barrier does not transfer) | time |
| 8 | **Account breaker** | maintenance-margin utilization > 70% or margin budget breach → cover ALL shorts, largest adverse first | portfolio |

PDT interaction: same-day cover is permitted ONLY for triggers 1–3 (hard risk);
signal/profit/time exits always wait for the next session. The runner counts
day-trades and refuses a 4th in any rolling 5-day window even for stops
(falls back to next-open cover with an alert).

Sizing note (anti-martingale): because adverse moves grow the position weight,
the runner re-checks per-name cap (4% NAV) daily and trims back excess on
breach — trimming counts as a partial cover through the same chain.

All thresholds (+12%, 15%/⅓, τ_weak, 20d) are E7 experiment outputs, not
hand-picked constants — the table records the priors the experiments start from.

## 5. Plumbing inventory & risk register

Unchanged from v1 (signed positions, CoverJob, margin preflight, buy-in
handling, live_state mirrors, WF-gate short evidence; risks: squeeze, buy-in,
margin spiral, dividend liability, PDT, bull-tape bleed). Implementation starts
only for Phase 0 after E6 passes review; Phase-1 plumbing waits for a passing
trigger — no speculative code.

## 6. Operator questions (carried over)
1. P0 instrument: short SPY vs long SH? 2. Short budget 20% or 10% NAV?
3. Short-term-gains tax on covers acceptable?
