# renquant105 — repointed direction: catch more + more-accurate multi-period TREND signals (evidence-graded)

This document supersedes the closed intraday framing of renquant105. The goal
is trend-signal **RECALL** + **PRECISION** on **multi-day holds** — explicitly
**NOT** intraday / day-trading.

## 1. Goal (operator-confirmed)

Catch MORE real trends (**recall** — currently the system barely trades: the
conviction gate admits ~0/84) and catch them MORE-ACCURATELY (**precision** —
fewer false signals), then trade them holding for the trend's duration
(multi-day). Explicitly **NOT** intraday, **NOT** high-frequency, **NOT**
day-trading.

## 2. Evidence base (GRADED — this is the point of the doc)

Grade legend:

- **[VERIFIED]** = adversarially vote-verified (3 independent verifiers,
  primary sources).
- **[SOURCED·UNVERIFIED]** = primary source + quote found, but the adversarial
  vote did NOT complete (deep-research hit a monthly spend limit mid-run —
  these were *abstained*, NOT refuted).
- **[THEORY]** = established theory.
- **[DATA·THIN]** = measured on our ledger but sample too thin to be
  conclusive.

| Grade | Claim | Sources / basis |
|---|---|---|
| **[VERIFIED]** | Raw minute / high-frequency input data is microstructure-NOISE-dominated; optimal sampling is finite (4 min–3 h), not "as fast as possible"; sampling faster makes even variance estimation worse. | Aït-Sahalia–Mykland–Zhang (2005, RFS 18:351): "very high frequency data are mostly composed of market microstructure noise, while the volatility of the price process is more apparent in longer horizon returns"; Zhang–Mykland–Aït-Sahalia (two-scales): "microstructure noise totally swamps the variance of the price signal"; Bandi–Russell (2008, REStud 75:339): realized variance "does not identify the daily integrated variance". |
| **[VERIFIED·scope]** | High-frequency data's PROVEN cross-sectional value is VOLATILITY / RISK estimation, NOT directional multi-day alpha. | Same microstructure literature draws this exact boundary. |
| **[SOURCED·UNVERIFIED]** | Multi-day / monthly cross-sectional returns are driven by SLOW predictors; momentum / reversal / liquidity dominate; baseline IC is structurally LOW. | Gu–Kelly–Xiu (2020, RFS 33:2223) use 94 characteristics (61 annual / 13 quarterly / 20 monthly, ZERO intraday); dominant predictors = momentum / reversal / liquidity; monthly stock-level R² only 0.33–0.40% → baseline IC structurally low. Momentum premium accrues OVERNIGHT not intraday (Lou–Polk–Skouras 2019, "Tug of War"). Intraday realized-skewness adds only MODEST weekly cross-sectional value (~24 bps/wk) → HF is "modest + short-horizon", not a multi-day step-change. |
| **[THEORY]** | At LOW baseline IC, adding a LOW-CORRELATION orthogonal signal raises IR more than refining one signal's input data → orthogonal alpha > input-frequency refinement. | Fundamental Law of Active Management (Grinold–Kahn, IR = IC·√breadth). |
| **[DATA·THIN]** | Our live ledger is too short to settle anything; directional IC sits at/below the shuffled-label floor; the MODEL (not the gate) is the dominant bottleneck; staleness sign matches a stale train-cutoff. | Our decision ledger (orchestrator PR #200, read-only): faithful LIVE history too short (fwd_20d = 11 aged dates, ~1–2 effective independent obs; fwd_60d = 0; sim rows unfaithful — NULL scorer provenance, raw_score up to +270 vs PatchTST's intrinsic ~−0.198 → excluded). Directional-only: short-horizon IC sits AT/BELOW the ~0.036 shuffled-label floor (fwd_5d +0.017, fwd_10d +0.051); killed-winner decomposition missed_by_model 0.755 vs killed_by_gate 0.209 → MODEL is the ~3.6× dominant bottleneck, gate secondary; staleness sign matches a stale train-cutoff. **Re-measure when live ages to ≥30 fwd_20d dates (~mid-Aug-2026) or faithful per-name PatchTST score history + provenance is wired (#133 follow-through).** |

## 3. Prioritized levers (evidence-graded)

1. **Fresher data + RETRAIN** — *[THEORY non-stationarity/decay + DATA·THIN
   staleness sign + known issue: model frozen ~train-cutoff 2024-11 / data
   2026-02-10]*. Cheapest, biggest lever AND a prerequisite for measuring
   anything else. NOTE: training internals live in `renquant-model`, NOT the
   orchestrator (CLAUDE.md hard boundary) — the orchestrator orchestrates +
   validates.

2. **TREND / MOMENTUM target** — *[goal-aligned + SOURCED·UNVERIFIED momentum
   dominance]*. The goal is trends; momentum is the most-replicated multi-day
   anomaly; the current cross-sectional snapshot ranker may not capture trend
   persistence. Use triple-barrier / multi-horizon trend labels.

3. **Orthogonal alpha = analyst-estimate revisions** — *[THEORY Fundamental Law
   + data ready: analyst data already harvested ~283/291 tickers]*. At low IC,
   low-correlation breadth beats refining the price signal.

4. **Gate / selective-prediction redesign** — *[DATA·THIN: secondary — model is
   3.6× the bigger bottleneck]*. Admitting ~0/84 throws away real trends, but
   opening the gate only recovers the ~21% the model already ranks high; do
   AFTER the model ranks better.

5. **Minute / intraday input data — NOT a lever** — *[VERIFIED]*. Park;
   noise-dominated for multi-day targets.

## 4. Reused methodology spine (from the closed intraday suite, repointed)

Validation discipline (purged CV / Deflated Sharpe / PBO / placebo / embargo /
triple-barrier / meta-label); decision-ledger + champion-challenger + daily
retrospective; recall/precision + IC-decay metrics. The target function is
repointed from "intraday cross-sectional alpha" → "multi-period TREND recall +
precision". This is "option A" (reuse the spine, don't re-derive).

## 5. Separate framing-agnostic track: 104 reliability fixes

Equities `client_order_id` dedup, run-lock, P&L daily-loss breaker,
intraday-granular freshness gate — worth landing regardless of the renquant105
framing; own PR track.

## 6. First concrete steps + what's still blocked

(a) Characterize the staleness lever (how much IC the stale model lost — partial
now, full ~mid-Aug); (b) scope a fresher-data retrain on a trend/momentum target
in `renquant-model`, validated by the spine; (c) prepare the analyst-revision
orthogonal signal as a parallel track; (d) re-run the PR #200 baseline at
~mid-Aug to settle model-vs-gate with faithful data.

**BLOCKED until then:** a conclusive model-vs-gate split, and any absolute
net-edge claim.
