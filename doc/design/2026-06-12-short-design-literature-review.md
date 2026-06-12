# Deep Research — Short-Selling Design vs the Literature & Open-Source Practice (v5)

**Status:** research review. Companion to the **v5 design** and the **E5/E6/E8
experiment spec**. (Earlier versions referenced the v2 design and an E2–E7
suite; those experiments are dropped — see git history.)

## 1. The central adverse finding (changes our priors)

**Drechsler & Drechsler (2014/2016, NBER w20282):** short-side abnormal
returns concentrate in **expensive-to-borrow** stocks; within the ~80% of
stocks with low borrow fees, the classic anomalies effectively disappear.
**Muravyev, Pearson & Pollet (2025, J. Finance):** short-sale costs eliminate
the abnormal returns of anomaly long-short portfolios.

**Implication:** our mandate is ETB-only — exactly the low-fee universe where
single-name short alpha is ~zero. Our E1 backtest failure (lowest-score
shorts: negative P&L) is the literature's predicted outcome. Hence v5's
ordering: hedge (Phase A) > efficiency (Phase B) > conviction shorts
(shelved; reopen only on E5 evidence).

## 2. Literature-positive uses of shorting

- **Portfolio efficiency:** Clarke, de Silva & Thorley (2002, FAJ) — the
  long-only constraint caps the transfer coefficient; a small short sleeve
  (120/20-style) converts EXISTING long signal into more IR. Basis of
  Phase B / gate G-E8.
- **Hedging/de-risking:** Moreira & Muir (2017, JF); Faber (2007). Basis of
  Phase A. **The vol-managed hedge ratio (h ∝ vol gap) is an E6 sensitivity
  arm only — the v5 design ships ONE trigger (`hard_bear`).** Note both
  papers support de-risking generally, not specifically a short overlay —
  which is why E6's PASS bar requires the hedge to beat the same-trigger
  cash-de-risk arm, not merely beat doing nothing.
- **Informed shorting signals live in flow/ownership data,** not price ranks:
  Boehmer, Jones & Zhang (2008); Engelberg, Reed & Ringgenberg (2012);
  Asquith, Pathak & Ritter (2005); Rapach, Ringgenberg & Zhou (2016). This
  is why E5 (short-interest dynamics, point-in-time FINRA backfill) is the
  only single-name path kept alive.

## 3. Short-side risk literature → design consequences

- **Momentum crashes:** Daniel & Moskowitz (2016, JFE) — momentum's short
  leg crashes in post-decline rebound windows (our E1 worst cases: INTU
  +18%, LMT +19% rips). Recorded as a **mandatory entry veto for any future
  Phase-C design** (no new shorts when SPY 60d < −10% and 5d > +3%). Not an
  active experiment overlay — E2/E3/E4 are dropped in v5.
- **Crowded shorts / squeezes:** Hong & Stein (2003); supports E5's
  days-to-cover mid-band [2, 8] and the operator's 2-name cap.
- **Sentiment timing:** Stambaugh, Yu & Yuan (2012) — noted as optional
  future overlay; not required.

## 4. Open-source practice check

| Project | Practice v5 mirrors |
|---|---|
| **QuantConnect Lean** | `ShortableProvider`: shortability/borrow checked **at order time**, fail-closed — G-EXEC item 3; shortable quantity/fee/rebate modeled by symbol and time |
| **cvxportfolio** | borrow cost as an explicit optimizer term — Phase B prices borrow inside the QP |
| **Alphalens** | per-quantile forward-return framing — the E-suite metric design |
| **vectorbt / backtrader** | shorts accrue borrow and pay dividends in backtests — the E-protocol cost model |
| **Alpaca docs / FINRA Notice 26-10** | **intraday-margin framework** (PDT retired 2026-06-04): pre-trade margin impact checks, real-time intraday margin monitoring, broker pre-trade rejections — design §5 and G-EXEC item 5 |

## 5. Rigor verdict

Pre-registered primary cells, no-look-ahead next-open entry, conservative
stop-sim on highs, PIT publication-lag joins (E5), costs incl. dividends and
borrow, hedge-vs-cash-de-risk comparator with a named negative-control day
(2026-06-11) — at or above common OSS backtest practice. Where earlier
versions lagged the literature (treating ETB single-name short alpha as
plausible; missing the rebound-crash failure mode; ordering conviction
shorts ahead of efficiency), v5 has been corrected.

## References
Drechsler & Drechsler (2014) NBER w20282; Muravyev, Pearson & Pollet (2025)
J. Finance; Boehmer, Jones & Zhang (2008) JF; Engelberg, Reed & Ringgenberg
(2012) JFE; Asquith, Pathak & Ritter (2005) JFE; Rapach, Ringgenberg & Zhou
(2016) JFE; Daniel & Moskowitz (2016) JFE; Stambaugh, Yu & Yuan (2012) JFE;
Hong & Stein (2003) RFS; Clarke, de Silva & Thorley (2002) FAJ; Moreira &
Muir (2017) JF; Faber (2007); FINRA Notice 26-10; QuantConnect Lean
ShortableProvider docs; cvxportfolio; Alphalens; Qlib.
