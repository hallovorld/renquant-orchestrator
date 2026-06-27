# renquant105 — OSS leverage, champion-challenger (shadow model) & validation

2026-06-27. Part of the renquant105 suite. What to borrow from open source, the
shadow-model (champion-challenger) pattern, and the intraday validation discipline.

## Keystone dependency (the thread tying everything together)
The shadow-model comparison, the gate counterfactual, and the implementation-shortfall
attribution **all** require a persisted **decision-ledger** (per-verdict + pre-gate
intended size) — collect-only today (the known "gate validation blocked by unwired
ledger" issue). **Wiring `GateRegistry.persist()` / the #133 ledger is the single
prerequisite that unblocks M2 (shadow) + the daily 复盘 + DSR.** Add a **trials ledger**
alongside it (count every variant/retrain → feed the Deflated Sharpe its real N).

## 1. Open-source frameworks (CODE = vendor · PATTERN = re-implement · IDEA = concept)
| Project | For intraday | Borrow | Why |
|---|---|---|---|
| **Qlib** (already in stack) | `NestedExecutor` (joint daily↔intraday fill backtest); `qlib.workflow.online` (`OnlineManager`+`RollingGen`+`RollingStrategy`) rolling retrain + champion history | **CODE+PATTERN** | exactly 105's walk-forward + intraday-fill gap; HFT handlers need rework (CN microstructure) |
| **Lean/QuantConnect** | pluggable `SlippageModel`/`FeeModel`/`FillModel` | **PATTERN** | best realistic-fill abstraction; port + calibrate an **Alpaca cost model**; do NOT copy the zero-slippage default |
| **Freqtrade/FreqAI** | sliding-window retrain, cache-then-hyperopt-the-gate, dry-run→live parity | **PATTERN (ops)** | cleanest retrain/champion loop; maps onto tuning the QP/conviction gate on a frozen score |
| **NautilusTrader** | event-driven, backtest==live semantics, `FillModel` | **IDEA** | right north star, heavy to adopt for one $10.6k account |
| **vectorbt/VBT PRO** | fast vectorized sweeps | **IDEA** | PRO proprietary; vectorized form fits a stateful QP gate poorly |
| **mlfinlab** | triple-barrier, meta-label, CPCV, PBO, DSR | **IDEA only** | **now commercial / all-rights-reserved — do NOT vendor**; re-implement de Prado's published methods |
| **FinRL** | deep-RL agents | **AVOID** | sample-hungry, unstable, sim-to-real gap; wrong tool at $10.6k. A supervised ranker + explicit QP gate (what we have) is more sample-efficient + auditable |

## 2. Champion-challenger / shadow model
**Patterns:** *shadow* (challenger scores same inputs, outputs logged, **zero** live risk —
the default; proves the pipeline runs, NOT PnL) → *canary* (small live capital, bounded) →
A/B / interleaving (N/A at retail — too few independent orders for power; do interleaving
offline on the score log). 104's `alpaca_shadow`/`readonly-alpaca` no-order run IS the
zero-risk shadow tier — 105 formalizes it into a registry-backed loop.

**MLflow mechanics — aliases, NOT stages** (stages deprecated MLflow 2.9+): register both
models as versions of one registered model; `@champion`/`@challenger` aliases +
`validation_status` tag (`pending→shadow→canary→approved`); live + shadow **load by alias**;
**promotion = one atomic alias swap** (old binary intact); rollback = reassign + keep a
`last_known_good` alias. Mirrors Uber Michelangelo (registry → auto-shadow → replay gate →
canary → auto-rollback); financial-services champion/challenger promote only on *consistent*
out-performance, **human-in-the-loop, never automatic**.

**Promotion bar (challenger → champion)** — thresholds are defensible starting points, calibrate:
- min live-shadow window sized by **MinTRL in effective-independent observations** (block
  scheme on overlapping labels; ~40–60 sessions is indicative, the BINDING quantity is the
  power/MinTRL-derived effective-N, finding 3) with **0 parity/contract failures**;
- **PSR on the difference of Sharpes ≥ 0.95** (corrects length+skew+kurtosis);
- **Probabilistic Deflated Sharpe ≥ 0.95** (Bailey & López de Prado — a probability, not the
  vacuous "DSR>0") fed the **full trial universe N** (horizons×labels×features×seeds×models×
  gates **+ the prior ~70–81 PatchTST trials**; that N must be carried in, finding 3);
- rank-IC superiority Z-test + higher ICIR;
- net (not gross) turnover ≤ 1.25× champion, max-DD ≤ champion;
- 104 fingerprint/config-parity + placebo/leakage WF sanity must pass before shadow numbers count;
- human sign-off + atomic rollback.

**Honesty caveat for $10.6k:** whole-share lumpiness + a few names/day means realized account
PnL almost never reaches MinTRL in weeks. **Primary promotion evidence = the per-name IC of the
shadow SCORES (hundreds of name-days), not realized account PnL** (a few dozen trades). This is
the only route to statistical power at this scale.

## 3. Daily retrospective — Implementation Shortfall attribution (Perold 1988)
```
IS = Delay + Trading(impact+spread) + Opportunity + Fees ;  Alpha = paper-portfolio return
Delay       = Side·Σ s_filled·(P_arrival − P_decision)
Trading     = Side·Σ s_i·(P_fill − P_arrival)        # arrival→fill = spread + impact (TCA)
Opportunity = Side·S_unfilled·(P_close − P_decision) # unfilled, marked to horizon
```
Benchmark = **arrival price** (IS-native, isolates own footprint; VWAP/TWAP gameable on size).
At $10.6k notional **impact ≈ 0** (square-root law) → dominant controllable cost is **spread +
adverse selection**; don't over-engineer an impact model. Give execution its own PnL line so the
model isn't blamed for execution drag.
**Gate counterfactual:** persist every veto + mark its rejected leg to horizon
(`gate_cost = Side·qty_intended·(P_close − P_decision)`); persistently positive aggregate ⇒
loosen, negative ⇒ validated; **slice by regime** (the panel-exit BULL_CALM finding). Report as
an **upper bound** (whole-share lumpiness means taking A blocks B).
**OSS to reuse:** alphalens-reloaded (IC + IC-by-horizon decay), pyfolio/empyrical/quantstats
(portfolio metrics) — **none do IS attribution / gate counterfactual / realized-vs-expected
slippage**; those are bespoke (formulae above). Build order: per-trade log → quantstats tearsheet
→ IS + gate counterfactual → alphalens IC monitoring.

## 4. Intraday validation discipline (mandatory)
- **CPCV** (López de Prado AFML Ch.7) as the default selector — a *distribution* of OOS Sharpes,
  not one number; **purge** overlapping-label train obs, **embargo ≥ max label horizon rounded to
  a session boundary**.
- **Split by trading day, never by row index** (Heston-Korajczyk-Sadka: same-time-of-day returns
  autocorrelate ≥40 days).
- **Deseasonalize** 5-min returns by intraday-periodic vol (Andersen-Bollerslev / Admati-Pfleiderer
  U-shape) so the model targets residual alpha, not the clock.
- **Separate overnight from intraday** (Lou-Polk-Skouras) — if 105 doesn't hold overnight, exclude
  the close→open gap from label + features + PnL.
- **No opening-auction look-ahead** — never key a 9:30 trade off the 9:30 print.
- **Microstructure noise** (Zhang-Mykland-Aït-Sahalia): label on mid/VWAP, noise-robust vol or
  5-min sampling; finer is worse; validate **net of cost**.
- **Multiple testing:** log the trial count, deflate via **DSR**; require **PBO < ~0.5** (CSCV);
  haircut new factors at **t≈3 not 2** (Harvey-Liu-Zhu); White Reality Check / Hansen SPA over the
  family before declaring a champion.
- **Weight overlapping labels by average uniqueness** + sequential bootstrap.
- Point-in-time universe incl. delisted/halted (survivorship).

Sources: Qlib/Lean/Freqtrade/Nautilus/vectorbt/mlfinlab docs; MLflow registry (aliases); Uber
Michelangelo; Perold 1988 + Kissell (IS/TCA); Almgren-Chriss / Gatheral (impact); López de Prado
AFML 2018 (CPCV/purge/embargo/uniqueness); Bailey & López de Prado 2014 (PSR/DSR/MinTRL);
Bailey-Borwein-LdP-Zhu 2016 (PBO/CSCV); Harvey-Liu-Zhu 2016 (t≈3); Heston-Korajczyk-Sadka 2010;
Lou-Polk-Skouras 2019; Admati-Pfleiderer 1988; Zhang-Mykland-Aït-Sahalia 2005; alphalens/pyfolio/
empyrical/quantstats.
