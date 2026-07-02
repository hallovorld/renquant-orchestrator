# RS-1: parking-sleeve vehicle — β-BUDGETED SPY/SGOV split, derived from the G* drawdown bar

STATUS: research recommendation (delegated per the 2026-07-02 grant; operator NOTIFIED). This
is the decision memo S7 implements; the config PR follows the normal review lane.
DATE: 2026-07-02

## 1. The measured problem (reproducible; runs.alpaca.db + ohlcv/SPY)

46 sessions (2026-04-24 → 07-01): average cash weight **75.5%**; the idle cash's foregone
SPY return = **2.88pp of book** cumulative ≈ **16%/yr annualized drag** in this period
(SPY +5.3% over the span). This is the mechanical core of "flat book vs rallying
benchmark" — measured, not asserted.

## 2. The vehicle decision — derived, not chosen by taste

The G\* bar (merged #230 §4) requires **max DD ≤ 15%**. Stress convention: SPY −25% with
regime-detection lag (the BEAR gate helps only after detection; 5-day detector). That fixes
a **book β budget**:

```
β_max = DD_bar / stress = 0.15 / 0.25 = 0.6
sleeve_spy_frac = max(0, (β_max − w_pos·β_pos) / w_sleeve)      [β_pos = 1.0 conservative]
```

At the current mix (positions ≈ 43%, sleeve ≈ 57%): **sleeve = 30% SPY / 70% SGOV**
(book β ≈ 0.6). The formula is the recommendation — **not a constant**: as lane A lifts
single-name deployment toward its measured ~40–43% ceiling and beyond, the SPY fraction
auto-shrinks so the β budget is never breached; when positions are risk-off (BEAR reserve
=100%), the sleeve is already swept off by the existing regime gates.

| Variant | book β (today) | SPY−25% stress | drag recovered (rally regime) | verdict |
|---|---|---|---|---|
| 100% SPY sleeve | ≈1.0 | ≈−25% — **breaches the bar** | ~100% | rejected (needs an operator override of G\*) |
| 100% SGOV | ≈0.43 | ≈−11% | carry only (~4–5%/yr [verify-at-checkout]) — relative shortfall persists in rallies | floor variant, kept as the BEAR/override state |
| **β-budgeted split (0.6)** | **0.6** | **≈−15% — at the bar by construction** | ~45–55% of the measured drag + carry on the SGOV leg | **RECOMMENDED** |

## 3. Contract points (unchanged from the merged #228 §1.3 design)

Sleeve excluded from QP/exits/correlation caps (cash-equivalent); sold FIRST to fund
admitted buys; regime reserve gates apply (BEAR ⇒ cash); margin account ⇒ same-day
re-use viable (verified regime, #223 A2); wash-sale non-issue (no SPY/SGOV overlap with the
book); the sweep plumbing gets its 10-session shadow before enable (S7 AC).

## 4. The recorded risk statement (what this decision accepts)

Accepts: up to ~15% book drawdown in a fast SPY −25% event before regime gates react, in
exchange for recovering roughly half of a measured 16%/yr idle-cash drag plus T-bill carry
on the rest. Rejects: full benchmark tracking (would breach the pre-registered DD bar) and
full T-bill parking (locks in the relative shortfall the operator explicitly wants closed).
Reversal trigger: if the measured 3-month realized sleeve contribution is negative AND the
DD budget was consumed >50% at any point, the sleeve drops to the SGOV floor variant and
the decision is re-opened with the data.
