# Are the order / portfolio-construction settings reasonable? (2026-06-11)

**Status:** discussion / RFC for operator review. No code change in this PR — this is the analysis behind a proposed retune. Numbers are grounded in the prod config, the verified model facts, and standard active-portfolio theory; the recommendations need a backtest/WF validation before any live change.

**Prod model facts this builds on** (verified 2026-06-10/11):
- PatchTST is a cross-sectional ranker, **label = `fwd_60d_excess`** (60-trading-day forward excess return), **OOS IC ≈ 0.13**, universe = **142 names**, regime that trades = **BULL_CALM**, book = **$100k**.
- The signal's natural horizon is **~60 trading days**. This single number is the yardstick for almost every setting below.

## The settings under review

| setting | value | what it controls |
|---|---|---|
| `max_concurrent_positions` | **8** | max names held |
| slot-fill | open slots only | new buys only fill `8 − held` |
| `qp_turnover_max` (BULL_CALM) | **0.15 / day** | L1 daily turnover cap |
| `min_hold_days` | **5** | hard floor before any sell |
| `min_reentry_days` | **5** | cooldown before rebuying a sold name |
| `qp_min_dw_pct` | **0.02** | no-trade band (suppress tiny Δw) |
| `top_up_threshold` | **0.05** | add to a held name only if Kelly target − current > 5% |
| `rotation_advantage` | **0** | score edge required to rotate held → candidate |

## The central tension: the settings permit far more turnover than a 60-day signal justifies

A signal that predicts **60-day** forward returns has a natural holding period of ~60 days, i.e. a natural daily turnover of **~1/60 ≈ 1.7%**. Trading faster than that doesn't harvest more of *this* signal — it just pays more cost for the same alpha (and trades on noise between signal updates).

Now look at what the settings *allow*:
- `qp_turnover_max = 0.15/day` → if the cap binds, the **whole book turns over in ~1/0.15 ≈ 6.7 days** → an implied holding period of **~7 days**, about **9× faster** than the 60-day signal.
- `min_hold_days = 5` → a 60-day-thesis position can be sold after just **5 days**.
- `rotation_advantage = 0` → a held name is swapped for a candidate on **any** positive score edge — i.e. on noise, every day.

Put together, the construction layer is tuned for a **~1-2 week** holding regime while the alpha is a **~3-month** signal. That horizon mismatch is the same class of bug we just fixed in Kelly sizing (σ@252 vs μ@60) and that the earlier IC→Sharpe work (E2) flagged ("the allocator must be horizon-held, daily is too churny"). **The most likely consequence: transaction-cost and tax drag erode a real (IC 0.13) signal.**

### Per-setting assessment

**1. `rotation_advantage = 0` — too low (highest-priority concern).** A zero barrier means rotation fires whenever a candidate out-scores a holding by an epsilon, which for a noisy daily score is most days. It is bounded by the turnover cap + min-hold + min-reentry, so it can't run away — but it pushes the book to churn up to the 15% cap on score *noise*, not signal. **Recommend:** set the rotation barrier to clear (a) round-trip cost and (b) the score's own noise — e.g. require the candidate's calibrated μ to beat the holding's by a margin (a few σ of daily score noise, or ≥ ~1–2% expected-return edge). This is the single change most likely to cut wasted turnover.

**2. `qp_turnover_max = 0.15/day` — too loose for a 60-day signal.** A daily cap that permits a 7-day full turnover is ~9× the signal's natural pace. **Recommend:** tie it to the horizon — e.g. ~**0.02–0.04/day** (a 25–50 day implied turnover), or better, target a holding-period rather than a flat daily cap. Caveat: the cap also governs initial deployment from cash; too tight and it takes many days to build the book (already ~3–4 days at 0.15). A horizon-aware design would allow faster *initial* deployment but slow *steady-state* churn.

**3. `min_hold_days = 5` — short relative to the thesis.** Five days is an anti-whipsaw floor, not a thesis-respecting hold. For a 60-day signal the *soft*-exit thesis-age guard (`min_holding_days_by_regime: {BULL_CALM: 60}`) is the horizon-aligned control — but note that guard was silently OFF outside BULL_CALM / for seeded positions until pipeline #100. The hard 5-day floor is fine as a floor; the real hold discipline should come from the (now-fixed) 60-day soft guard. **Recommend:** keep 5 as the hard floor, ensure the 60-day soft guard is actually active (set its `default`), and consider whether model-driven exits before ~20–60 days should require a stronger thesis-break signal.

**4. `max_concurrent_positions = 8` — concentrated; likely under-uses the signal's breadth.** By the Fundamental Law of Active Management (Grinold), `IR ≈ IC · √breadth`. The signal ranks 142 names with IC 0.13; restricting to the top 8 harvests only a slice of that breadth and leaves the book exposed to single-name idiosyncratic risk (each name ~12% at the concentration cap; one −50% name = −6% book). 8 names can be justified if the alpha is strongly top-concentrated (only the very top ranks carry signal) and for a small book, but for a broad cross-sectional ranker it is on the aggressive end. **Recommend:** backtest **15–25 names** vs 8 on risk-adjusted return (Sharpe/IR), holding the σ-aware Kelly sizing fixed. More names = more breadth + lower idiosyncratic variance, at the cost of smaller per-name conviction.

**5. slot-fill (open slots only) — acceptable, but its stickiness is undone by `rotation_advantage=0`.** Pure slot-filling makes the book sticky (incumbents stay until sold); aggressive rotation (current) makes it fluid. They partly cancel. Once rotation has a real barrier (#1), slot-fill becomes a sensible turnover-reducer. No change needed beyond #1.

**6. `min_reentry_days = 5` — reasonable.** Prevents wash-trading the same name; also interacts with the tax wash-sale window. Fine; arguably could be longer to discourage churn, but not a problem.

**7. `qp_min_dw_pct = 0.02` (no-trade band) — reasonable.** Suppresses sub-2% Δw (≈17% of a 12% position). A sensible cost filter; could even be a touch higher to further cut churn. Keep.

**8. `top_up_threshold = 0.05` — reasonable.** Avoids dribbling top-ups. Keep.

## Interactions worth noting
- `rotation_advantage=0` × loose `qp_turnover_max` × short `min_hold_days` **compound** into a high-churn regime for a slow signal. Fixing #1 and #2 together is the high-value move; either alone is partly defeated by the other.
- Concentration (8 names) interacts with the now-fixed Kelly σ-horizon: with correct sizing, 8 names land near the 12% cap (≈ equal-weight at the cap), so the *sizing* signal is largely lost to the cap. More names would let conviction differentiate weights again.

## Recommendation summary

| setting | current | proposed (to validate) | priority |
|---|---|---|---|
| `rotation_advantage` | 0 | μ-edge barrier (~1–2% ER, or k·σ_score) | **HIGH** |
| `qp_turnover_max` (BULL_CALM) | 0.15/day | ~0.03–0.05/day (horizon-aware) | **HIGH** |
| `max_concurrent_positions` | 8 | backtest 15–25 | MED |
| `min_hold_days` + 60d soft guard | 5 / silently-off | 5 floor + activate 60d `default` | MED (guard fixed in #100) |
| `min_reentry_days` | 5 | keep (maybe ↑) | LOW |
| `qp_min_dw_pct` | 0.02 | keep | — |
| `top_up_threshold` | 0.05 | keep | — |

## Validation plan (before any live change)
1. Backtest each proposed change **in isolation** then jointly, on the WF replay manifold, measuring net (post-cost, post-tax) Sharpe / IR and realized turnover — not gross IC.
2. Specifically measure **realized daily turnover** under current settings vs proposed: confirm the hypothesis that the book churns far faster than 60 days today.
3. Use the step-4g A/B harness so the change earns a promotion verdict rather than a hand-wave (the same gate discipline as the allocator work). Note the WF manifold's known constraint-fidelity gaps; a turnover/cost study is more robust to those than an allocator promotion.

## Open questions for the operator
- Is the 8-name concentration a deliberate conviction stance, or an untested default? (Decides whether MED #4 is worth a backtest.)
- Is the intent to trade the 60-day signal *as* a 60-day signal (low turnover), or to use it as a faster momentum proxy (higher turnover)? The settings currently imply the latter; the label implies the former.
- Appetite for a holding-period-targeted turnover model vs a flat daily cap?

**Bottom line:** the *anti-churn* guards (no-trade band, top-up, min-reentry) are reasonable. The *turnover-enabling* settings (`rotation_advantage=0`, `qp_turnover_max=0.15`, and to a lesser degree `min_hold_days=5`) are mis-aligned with the 60-day signal horizon and most likely cost performance through over-trading; and 8 names probably under-uses the signal's breadth. None of this should change live without a cost-aware backtest — but the direction (slow the construction layer down to the signal's horizon, widen the book) is well-motivated.

Agent-Origin: Claude
