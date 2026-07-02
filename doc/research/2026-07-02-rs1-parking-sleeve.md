# RS-1: parking-sleeve vehicle — β-budgeted SPY/SGOV split, PROVISIONAL pending real risk measurement

STATUS: research recommendation, PROVISIONAL — the SPY arm requires its own preregistered
gate (per #228 §1.3's authorization-bar correction) before any capital exposure; this doc
proposes and designs, it does not authorize live enablement of either arm.
DATE: 2026-07-02
REVISION: r2 (Codex round 1 — corrected a regression against the merged #228 §1.3 SPY-risk
framing, an unjustified 30/70 derivation, G* authorization-bar misuse, and a path-dependent
annualization; see "Round 2" note at the end).

## 1. The measured problem (reproducible; runs.alpaca.db + ohlcv/SPY) — DESCRIPTIVE, not forward-looking

46 sessions (2026-04-24 → 07-01): average cash weight **75.5%**; the idle cash's foregone
SPY return over this SPECIFIC realized window = **2.88pp of book**, cumulative. This is a
**realized period attribution** for the window that actually occurred (SPY +5.3% over the
span) — a descriptive, backward-looking observation of "flat book vs one particular rallying
benchmark path," not an expected annual benefit. Scaling 46 sessions into a "16%/yr
annualized drag" figure extrapolates one realized market path as if it were the expected
path; the true expected opportunity cost depends on the full distribution of possible market
outcomes, not the one that happened. **This document does not carry an annualized-drag
number forward as an economic justification.**

## 2. The vehicle decision — a planning heuristic, not a derived authorization

The §4 institutional-gap route (research#230, "G107"/"G\*") states a max-DD ≤ 15% figure as
a **PROPOSED assessment target, explicitly NOT YET a preregistered authorization bar** — per
#230's own §5 honesty note, it becomes a preregistered target only once its metric
definitions are independently frozen and an immutable baseline exists; neither has happened.
Using it here is therefore a **planning reference point for sizing intuition only** — it does
not derive or authorize a specific sleeve split.

Stress convention used for the planning calculation below: a single hypothetical SPY −25%
scenario with regime-detection lag (5-day detector). This is ONE stress scenario among many
that should inform a real risk budget — not a complete stress suite.

```
β_max = DD_bar / stress = 0.15 / 0.25 = 0.6     [planning heuristic only, not a hard budget]
sleeve_spy_frac = max(0, (β_max − w_pos·β_pos) / w_sleeve)      [β_pos = 1.0 ASSUMED, not measured]
```

At the current mix (positions ≈ 43%, sleeve ≈ 57%), this heuristic produces **sleeve = 30%
SPY / 70% SGOV (book β ≈ 0.6)**. **This number is PROVISIONAL and not a defensible risk
budget as derived.** The calculation above has four uncorrected weaknesses that must be
closed before any capital sizing decision relies on it:

1. **`β_pos = 1.0` is an assumption, not a measurement.** The actual beta/covariance of
   current holdings has not been measured against SPY. Before this split can be treated as
   more than a planning sketch, measure current holdings' realized beta and covariance
   structure and substitute the real figure.
2. **SGOV beta/rate risk is implicitly assumed to be exactly 0.** SGOV (a short-duration
   T-bill ETF) has small but nonzero rate sensitivity; treating it as risk-free in the budget
   equation is a simplification that should be stated explicitly as such, not silently
   assumed away.
3. **Single stress scenario.** One hypothetical SPY −25% draw is not a stress *suite*. A real
   risk budget needs multiple historical and hypothetical scenarios (varying magnitude,
   correlation regime, and detection-lag assumptions) before a sizing number is defensible.
4. **No risk buffer.** The calculation as written consumes the ENTIRE 0.15 DD budget on the
   single modeled scenario, leaving zero allowance for idiosyncratic single-name loss,
   covariance/regime shift, price gaps, slippage, or model error — all of which stack on top
   of the modeled sleeve risk in a real drawdown. An explicit reserve fraction of the DD
   budget should be held back before deriving a sleeve weight from what remains.

None of these four points can be closed with the data available in this pass (real
beta/covariance measurement and a multi-scenario stress suite require dedicated analysis this
revision does not attempt). **The 30/70 split below is therefore PROVISIONAL — a planning
sketch pending that analysis, not a recommendation ready for capital authorization.**

| Variant | book β (today, planning estimate) | SPY−25% stress (single scenario) | realized-period attribution recovered | status |
|---|---|---|---|---|
| 100% SPY sleeve | ≈1.0 | ≈−25% — breaches the planning DD reference | ~100% (descriptive, this window only) | rejected — clearly excessive even before rigorous budgeting |
| 100% SGOV | ≈0.43 | ≈−11% | carry only (~4-5%/yr [verify-at-checkout]); relative shortfall persists in rallies | floor variant — kept as the BEAR/override state; lowest incremental risk |
| β-budgeted split (0.6), PROVISIONAL | 0.6 (planning estimate, not measured) | ≈−15% by construction of the single-scenario model | descriptive partial recovery in this window + SGOV-leg carry | PROVISIONAL — requires the §2 measurement gaps closed before treating as a sizing recommendation |

## 3. Risk-control participation — SPY is a real beta position, exactly per the merged #228 §1.3 correction

**This section previously called the SPY portion of the sleeve "cash-equivalent" and excluded
it from QP/exits/correlation caps. That was a direct regression against `renquant-orchestrator#228`
§1.3, which already went through this exact review correction on the same underlying design
question and settled the framing below. This revision reuses #228's corrected language rather
than reintroducing the same mistake in a second document.**

The SPY sleeve is **not cash-equivalent** — it is a large, real equity-beta position (raising
book beta from a baseline of roughly ~0.25-equivalent toward the planning target of ~0.6-1.0
depending on split). It **must participate in every risk control that governs real
positions**, with exactly one legitimate, narrow exclusion:

- **Total-book beta**: the sleeve's full beta contribution is included in the book-level beta
  calculation, not netted out or ignored.
- **Gross/net exposure**: sleeve notional counts fully toward both gross and net exposure
  limits.
- **Concentration**: the sleeve is a real, large single-position concentration in SPY and must
  be checked against whatever concentration ceiling governs any other single holding of
  comparable size — no "it's the benchmark" exemption.
- **Correlation caps**: the sleeve participates in correlation-based portfolio construction
  checks like any other position; it is not exempt because it's an index product.
- **Drawdown**: sleeve mark-to-market losses count toward book-level drawdown triggers exactly
  like any other position's losses.
- **Liquidity**: the sleeve is assumed liquid (SPY is highly liquid), but that assumption is
  stated explicitly, not implied by exemption from liquidity checks.
- **Liquidation / funding rules**: when the book needs to raise cash under stress, the sleeve
  is a normal, sellable position subject to the SAME liquidation-priority and funding rules as
  any other holding. It IS still sold FIRST to fund an admitted single-name buy under normal
  (non-stressed) operation — that ordering rule stays — but that is a distinct, narrower thing
  from being exempt from risk accounting.
- **Legitimate exclusion (unchanged, narrow)**: the sleeve is excluded ONLY from single-name
  alpha ranking and the panel-exit's alpha-driven rotation logic — it is not a stock pick and
  does not compete with one for a "best pick" slot.
- Regime interaction: the sleeve follows the regime gates — BEAR (`cash_reserve_pct = 1`)
  sweeps the sleeve OFF (to cash); CHOPPY/BULL_VOLATILE reserve percentages apply to the
  sleeve size.
- Margin/settlement: sell T+1 settlement precedes buy funding (verified margin account makes
  same-day re-use viable, per #223 A2).
- Wash-sale: SPY sleeve trades can wash-sale against nothing in the current book; noted for
  the ledger regardless.

**Only genuinely cash-like collateral — SGOV / short-duration T-bills — may receive narrow
special treatment** (e.g., a correlation-cap exemption that doesn't meaningfully apply to a
near-risk-free instrument), and even that exemption should be scoped narrowly and justified
explicitly per-control, not granted blanket to "the sleeve" as a whole.

## 4. Separate SGOV and SPY arms — independent gates, independent rollback, no live enablement in this RFC

The SGOV-only and SPY arms carry materially different risk (near-zero beta vs. real,
substantial beta exposure per §2-3 above) and must NOT be gated or enabled as one combined
proposal.

**SGOV arm.** Lower risk (near-zero beta, high liquidity). May proceed to a lighter-weight
validation path: a plumbing/mechanics shadow run confirming the sweep-to-SGOV / sell-SGOV-
first mechanics work correctly, followed by its own explicit capital-authorization decision
recorded separately from the SPY arm.

**SPY arm.** Requires the full one-change-at-a-time experiment structure `#228` §1.2
established for Lane A, applied here:
- **Baseline**: current all-cash idle-reserve behavior, held fixed for comparison.
- **Immutable session list**: sessions used for the shadow comparison must be fixed in advance
  of running it, not selected after seeing which sessions look favorable.
- **Estimand**: realized book beta, drawdown behavior under the sessions observed, turnover/
  cost delta, and tax treatment (short-term realized gains from cash-drag rebalancing) versus
  the cash baseline and versus the SGOV-only arm.
- **Non-inferiority / risk thresholds**: frozen numeric bounds on turnover/cost, concentration,
  and drawdown non-degradation (same discipline #228 §1.2 requires of every Lane A item) —
  to be set explicitly before the shadow run starts, not derived from its results afterward.
- **Stop rule**: an explicit, pre-committed condition for aborting the shadow run early if
  early results show the SPY arm materially degrading any of the above.
- **Rollback plan**: how to revert the sleeve to the SGOV floor variant if the SPY arm needs
  to be pulled post-enable.

**Per #228 §1.3's authorization-bar correction, a 10-session shadow run — for either arm —
validates operational/plumbing correctness ONLY.** It does not, by itself, authorize the
underlying economics or real capital exposure of either arm. Live enablement of the SPY arm
specifically requires, at minimum, the pre-registered replay/shadow comparison #228 §1.3
already specifies (cash vs. Treasury-sleeve vs. SPY-sleeve, covering beta, drawdown, turnover,
tax, settlement, and stressed sell-to-fund behavior) PLUS the §2 measurement gaps in this
document (real beta/covariance measurement, multi-scenario stress suite, explicit risk buffer)
closed. **This document proposes and designs; it does not authorize live capital deployment
of either arm.**

## 5. The recorded risk statement (what a future authorization decision would accept — not yet accepted)

If the SPY arm is later authorized at the PROVISIONAL 0.6 book-beta planning level (pending
§2's measurement gaps being closed and producing a real, defensible number): accepts up to
~15% book drawdown in a fast SPY −25% event before regime gates react, in exchange for
recovering an uncertain (not yet properly estimated) fraction of realized idle-cash
underperformance versus SPY in rallying regimes, plus T-bill carry on the SGOV leg. Rejects:
full benchmark tracking (100% SPY, clearly excessive per §2's table) and full T-bill parking
alone (locks in the full relative shortfall versus a rallying benchmark). Reversal trigger (if
later authorized): if the measured 3-month realized sleeve contribution is negative AND the
DD budget was consumed >50% at any point, the sleeve drops to the SGOV floor variant and the
decision is re-opened with the data.

---

**Round 2 (Codex CHANGES_REQUESTED, corrected 2026-07-02):** the r1 draft (a) called the SPY
sleeve "cash-equivalent" and excluded it from QP/exits/correlation caps — a direct regression
against the already-merged `#228` §1.3 correction on the identical underlying design question;
fixed by reusing #228's exact settled risk-participation language (§3 above). (b) Derived the
30/70 split from `β_pos = 1.0` (assumed, not measured), `SGOV beta = 0` (assumed), a single
stress scenario, and consumed the entire 15% DD budget with no reserve for idiosyncratic loss/
covariance shift/gaps/slippage/model error — the split is now explicitly labeled PROVISIONAL
pending real beta/covariance measurement, a multi-scenario stress suite, and an explicit risk
buffer (§2). (c) Treated G\*/G107's 15% DD figure as a preregistered authorization bar; #230's
own text states it is a PROPOSED planning target, not yet preregistered — corrected to
"planning reference point" throughout (§2). (d) Annualized a 46-session realized rally into a
"16%/yr drag" expected-benefit claim; corrected to report only the realized period attribution
for the window that actually occurred, with no forward annualization (§1). (e) Combined the
SGOV and SPY arms under one gate; split into independent gates/rollback, with the SPY arm
required to follow #228 §1.2's full one-change-at-a-time experiment structure, and explicit
confirmation that live enablement of either arm is out of scope for this RFC (§4).
