# Deep Research — Short-Selling Design vs the Literature & Open-Source Practice

**Status:** research review / awaiting review. Companion to the v2 design and
the E2–E7 spec. This is the rigor audit the operator asked for: what the
literature CONFIRMS, what it CONTRADICTS, and the design changes that follow.

## 1. The central adverse finding (changes our priors)

**Drechsler & Drechsler (2014/2016, NBER w20282), "The Shorting Premium and
Asset Pricing Anomalies":** short-side abnormal returns concentrate in
**expensive-to-borrow** stocks. The cheap-minus-expensive (CME) portfolio
earns ~1.31%/mo gross; crucially, **within the ~80% of stocks with low borrow
fees, the classic anomalies effectively disappear** — anomaly shorts pay only
where borrowing is hard. **Muravyev, Pearson & Pollet (2025, J. Finance),
"Anomalies and Their Short-Sale Costs":** short-sale costs eliminate the
abnormal returns of anomaly long-short portfolios; anomalies persist on paper
but **cannot be exploited net of borrow fees**.

**Implication for us:** our mandate is **ETB-only** (Alpaca, no manual
locates) — i.e., we are *constrained to exactly the low-fee universe where the
literature says single-name short alpha is ~zero*. Our E1 backtest failure
(20/50 lowest scores: negative short P&L) is not an accident of our model; it
is what the literature predicts for this universe. **Design change: Phase 1's
prior is downgraded to "likely fails"; its pass bar stays, but the burden of
proof is on the experiments — and Phase 0 (hedging) plus portfolio-efficiency
uses of shorting are promoted to the primary economic rationale.**

## 2. Why keep any short capability at all (literature-positive uses)

- **Portfolio efficiency, not stock-picking:** Clarke, de Silva & Thorley
  (2002, FAJ) — the long-only constraint caps the transfer coefficient
  (~0.5–0.7); relaxing it (120/20-style) converts EXISTING signal into more
  IR without new alpha. This favors our Phase 2 (small L/S extension) over
  Phase 1 (conviction shorts) — the opposite of the intuitive ordering.
- **Hedging/de-risking:** Moreira & Muir (2017, JF), "Volatility-Managed
  Portfolios" — scaling exposure down in high-vol states raises Sharpe;
  Faber (2007) 200-DMA de-risking. Both support Phase-0 index hedging as the
  highest-expected-value use of short capability. **E6 gains a vol-managed
  variant: hedge ratio h ∝ (target_vol / realized_vol − 1)+ as a third
  trigger besides breaker/hard_bear.**
- **Informed shorting signals exist** — but in flow/ownership data, not price
  ranks: Boehmer, Jones & Zhang (2008, JF) (institutional short flow);
  Engelberg, Reed & Ringgenberg (2012, JFE) (shorts process public news);
  Asquith, Pathak & Ritter (2005, JFE) (high SI + low institutional
  ownership underperforms); Rapach, Ringgenberg & Zhou (2016, JFE)
  (aggregate SI predicts the market). This is why E5 (short-interest
  dynamics) is the only single-name experiment with strong literature priors
  — and it requires the FINRA point-in-time backfill.

## 3. Short-side risk literature → new vetoes

- **Momentum crashes:** Daniel & Moskowitz (2016, JFE) — the SHORT leg of
  momentum crashes violently in rebound states (post-decline, rising market):
  exactly our E1 worst cases (INTU +18%, LMT +19% rips). **Design change
  (§4.5 + E2/E3 overlay): rebound veto — no new shorts when SPY 60d return
  < −10% AND SPY 5d return > +3% (panic-rebound window); sensitivity in E4.**
- **Crowded shorts / squeezes:** Hong & Stein (2003) (short constraints &
  crashes); the GME episode literature. Confirms the DTC mid-band [2,8]
  squeeze guard and the 2-name cap.
- **Sentiment timing:** Stambaugh, Yu & Yuan (2012, JFE) — anomaly short legs
  pay mainly in high-sentiment periods. Optional E-overlay if a sentiment
  index is wired in later; noted, not required.

## 4. Open-source practice check (are we technically current?)

| Project | Practice we mirror |
|---|---|
| **QuantConnect Lean** | `ShortableProvider` pattern: shortability + borrow checked **at order time**, not at signal time — matches our ETB-at-order check; their margin models mirror our Reg-T preflight |
| **cvxportfolio** (Stanford/BlackRock lineage) | borrow cost as an explicit term in the optimizer's cost model — the Phase-2 L/S extension should price borrow inside the QP, not as a post-filter |
| **Alphalens** | short-leg quantile analysis = our E-suite metric framing (per-quantile forward returns, not just IC) |
| **vectorbt / backtrader** | short backtests price dividends-paid and borrow accrual — our E-protocol's dividend subtraction follows this |
| **Qlib** | evaluates alpha as long-short spreads but ships long-only TopK execution — consistent with our finding that the short leg is evaluation scaffolding, not free money |

## 5. Verdict on "logic rigorous, technically advanced?"

- **Rigorous:** pre-registered primary cells, no-look-ahead next-open entry,
  conservative stop-sim on highs, PIT publication-lag joins (E5), cost model
  incl. dividends — these match or exceed common OS backtest practice.
- **Where v2 was behind the literature (now fixed):** (a) it treated Phase-1
  single-name short alpha as plausible in an ETB universe — the
  Drechsler/Muravyev results say that is the one place it reliably is NOT;
  (b) it lacked the momentum-crash rebound veto; (c) it under-weighted the
  transfer-coefficient argument that makes Phase 2 (efficiency) more
  promising than Phase 1 (conviction shorts).
- **Net design ordering after this review: Phase 0 (hedge) > Phase 2
  (efficiency extension) > Phase 1 (conviction shorts)** — Phase 1 retained
  only because the operator's high-bar protocol makes it self-limiting.

## References
Drechsler & Drechsler (2014) NBER w20282; Muravyev, Pearson & Pollet (2025)
J. Finance; Boehmer, Jones & Zhang (2008) JF; Engelberg, Reed & Ringgenberg
(2012) JFE; Asquith, Pathak & Ritter (2005) JFE; Rapach, Ringgenberg & Zhou
(2016) JFE; Daniel & Moskowitz (2016) JFE; Stambaugh, Yu & Yuan (2012) JFE;
Hong & Stein (2003) RFS; Clarke, de Silva & Thorley (2002) FAJ; Moreira &
Muir (2017) JF; Faber (2007); QuantConnect Lean ShortableProvider docs;
cvxportfolio; Alphalens; Qlib.
