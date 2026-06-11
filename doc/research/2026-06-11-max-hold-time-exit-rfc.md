# RFC — Does a `max_hold` time-exit make sense? (and the CHOPPY=40 incident)

**Status:** RFC / awaiting review (no code change here)
**Trigger:** 2026-06-11 — after the regime fix flipped the book BEAR→CHOPPY, the
daily tried to **sell MU** (a strong momentum holding) via `max_hold`. Operator:
*"does max_hold make sense at all?"*
**Companion:** `2026-06-11-false-bear-buy-suppression-cascade.md`,
`2026-06-11-regime-detection-hmm-markov-switching-rfc.md`.

---

## 0. Verdict (short answer)

A **hard, calendar-day `max_hold` is the wrong primary exit** for a 60-day
cross-sectional momentum ranker. It is **signal-blind**: it sells winners and
losers identically on a clock, fighting the very momentum edge the model
harvests. It makes sense in exactly **two** narrow forms:

1. **As a "vertical barrier" at the thesis horizon** (de Prado's triple-barrier):
   the bet is *defined* over a 60-day forward horizon, so a time-exit **at 60d**
   is principled — past the horizon the label/thesis is stale.
2. **As a far, non-binding zombie-position backstop** (≥ horizon, e.g. 252–500d):
   a safety net against a position with no governing signal (pipeline break).

It does **not** make sense as a **tight, sub-horizon, per-current-regime timer** —
which is exactly what `regime_params.CHOPPY.max_hold_days = 40` is. **40 < 60**
guarantees cutting the bet **before it is evaluated**. That is what force-sold MU.

---

## 1. The MU incident — two compounding fragilities

`check_max_hold` (exits.py) is a **hard path-risk exit**, calendar-day, exempt
from the 60-day thesis protection:
```python
days_held = (today - state.entry_date).days   # CALENDAR days
if days_held >= max_hold: exit("max_hold")     # unconditional
```
Config (per *current* regime fallback): BULL_CALM / BULL_VOLATILE / BEAR = **500**;
**CHOPPY = 40**; default 500.

`max_hold_days` is meant to be **anchored to the ENTRY regime**
(`exits.py:169`, `trade_events.py:489` stamp `max_hold_anchor_regime`). MU
entered 2026-04-27 in **BULL_CALM → max_hold 500**, so it should *never* have
fired at 45 days. It fired because:

- **Fragility A (anchor missing):** MU's persisted `entry_signals` =
  `{rank_score, panel_score, kelly_target_pct}` — **no `regime` field**. With the
  entry-regime anchor absent, resolution **falls back to the *current* regime**
  (CHOPPY) → max_hold = **40**. (This may be aggravated by a live_state revert
  during today's deploy; regardless, the fallback target is wrong.)
- **Fragility B (CHOPPY=40 < 60d thesis):** even with a correct current-regime
  read, 40 days is shorter than the horizon the model is trained on.

Net: a hard timer, reading the wrong regime, sold a **+momentum winner** 15 days
before its own thesis horizon. This is the same family as the ORCL stop-loss
complaint — a path rule destroying value the signal still endorses.

---

## 2. The conceptual case against a hard time-exit (for THIS strategy)

1. **Signal-blindness contradicts the edge.** The model is momentum
   (`corr(returns, μ) ≈ +0.19`): winners exhibit positive autocorrelation, so
   force-selling on a clock truncates the right tail — it sells the names most
   likely to keep working. Exits should be driven by **signal decay** (rank/μ
   falls) or **risk** (stops), never by tenure alone.
2. **Horizon conflict.** Training/calibration is on a 60-day forward excess
   return. A `max_hold < 60` exits before the thesis can resolve; a
   `max_hold ≫ 60` essentially never binds — so the only *defensible* fixed value
   is **= horizon (60d)**, and it should be a property of the **model**, not of
   the **current regime** (a regime label has nothing to do with the bet's
   evaluation horizon).
3. **Cost & tax.** Forced time-exits raise turnover → transaction costs, plus
   short-term-gain tax and wash-sale entanglement, with **no alpha** to pay for
   them. (MU would have been a realized short-term gain + a re-entry cost.)
4. **Antithetical to the aim-portfolio.** This book references Gârleanu–Pedersen
   (2013): trade *toward* a cost-aware target. A hard timer forces a trade with
   **no reference to the aim** — pure noise turnover.
5. **We already have the right exits.** Panel/conviction exit (cross-sectional
   rank decay), rotation (thesis-degradation vs entry baseline), `model_protection`
   (thesis-aware N-of-N μ-breach — built 2026-06), and the risk stops
   (stop_loss / trailing / SDL) are **signal-and-risk-driven**. `max_hold` is the
   one exit that ignores all information.

## 3. The narrow legitimate uses — and whether they apply

| Rationale | Applies here? |
|---|---|
| **Vertical barrier at horizon** (de Prado triple-barrier) | ✅ at **60d**, as a model property — *not* 40, *not* per-regime |
| **Zombie/stale-position backstop** (pipeline broke, no signal) | ✅ but better served by an explicit **stale-signal guard**; a far `max_hold` (≥ horizon) is an acceptable crude proxy |
| Mean-reversion with known reversion horizon | ✗ this model is momentum, not mean-reversion |
| Pairs/stat-arb half-life; options theta/expiry | ✗ long-only equities |
| Behavioral "don't marry a position" | ✗ a systematic model needs no behavioral guard |

de Prado (AFML ch.3, triple-barrier) is the one respected method that *includes*
a time exit — but as the **vertical barrier = the bet's evaluation horizon**.
That endorses `max_hold = 60d` (uniform), and **refutes** a sub-horizon
per-regime `40`.

---

## 4. Recommendation

1. **Remove the per-current-regime `max_hold` tightening.** Tenure is not a
   regime property. Set a **single** `max_hold_days` = the **thesis horizon
   (60d)** as a de-Prado vertical barrier, **or** a far zombie backstop
   (e.g. 252) — but **never < horizon**. Delete `CHOPPY: 40`.
2. **Fix the anchor fallback (Fragility A):** when the entry-regime anchor is
   missing, default to the **safe far/horizon value**, never to the *current*
   regime's (possibly tight) value. And stamp `entry_regime` reliably at entry.
3. **Let signal/risk own real exits:** panel/rotation + `model_protection` +
   stops. `max_hold` stays only as the rarely-binding backstop.
4. **(Optional, principled) add a stale-signal guard:** exit if a name has had no
   fresh score for K bars — the *correct* "dead position" catch, replacing the
   crude time proxy.

**Concrete config change (for the implement step, after review):** in
`renquant-strategy-104`, set every `regime_params.*.max_hold_days` to one value
(recommend **60** as the vertical barrier, or 252 as a pure backstop) and remove
the `CHOPPY: 40` outlier; keep active/golden in lockstep.

## 5. A/B validation
Replay the trailing window with `max_hold ∈ {40 (current CHOPPY), 60, 252, off}`
measuring **net-of-cost PnL / Sharpe**, **turnover**, **winner-truncation rate**
(exits of names whose μ/rank was still top-quartile), and **tax drag**. Promote
only on improvement. Expect 60/252/off to dominate 40 by avoiding winner
truncation.

## 6. Risk
Loosening `max_hold` could let a genuinely dead position linger if the signal
pipeline silently breaks. **Mitigation:** the stale-signal guard (4) + the
existing data-freshness gate + `model_protection` catch dead theses far more
precisely than a blanket timer.

## References
- López de Prado, M. (2018). *Advances in Financial Machine Learning*, ch.3
  (triple-barrier / vertical barrier).
- Jegadeesh, N. & Titman, S. (1993). *Returns to Buying Winners and Selling
  Losers.* J. Finance. (Formation/holding periods are a research methodology,
  not a per-position liquidation rule.)
- Moskowitz, Ooi, Pedersen (2012). *Time Series Momentum.* JFE.
- Gârleanu, N. & Pedersen, L. (2013). *Dynamic Trading with Predictable Returns
  and Transaction Costs.* J. Finance.
