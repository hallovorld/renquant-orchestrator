# Vol-gate opportunity-cost research (theory + rigorous data)

2026-06-25. Trigger: 2026-06-25 daily-full no-trade — `RealizedVolGateTask` dropped 21/97
buy candidates over the 60% annualized-vol cap. Operator: high-vol is opportunity too, but
demand **theory + rigorous data**, not a hot take. Research/discussion PR — NO behavior change.

## Deliverables
- `doc/research/2026-06-25-vol-gate-opportunity-cost.md` — theory (Kelly/Merton continuous
  sizing; Moreira–Muir vol-managed; low-vol anomaly / BAB), then a survivorship-aware,
  cost-net, drawdown-aware, regime-split cap-sweep backtest.
- `scripts/research_vol_gate_opportunity_cost.py` — reproducible.

## Theory (one line)
With a `1/σ²` sizer downstream (which the live Kelly already is, clip [0.05,1.50]), a hard cap
far below that clip is redundant in calm/bull regimes and should only bind in stress — so the
right design is a **regime-aware** cap, not a uniform 60% line.

## Findings (net of cost, excess vs SPY, monthly)
- **The 60% cap is the worst point**: Sharpe +0.20 at 0.6 → +0.70 at cap ≥1.0, then saturates.
  NOT a risk trade-off — vol (~7.5%) and maxDD are flat-to-better when relaxing (the sizer
  controls risk). Survives dropping the top-1% survivor winners (0.6→0.10 vs 1.2→0.60) and the
  median month agrees.
- **Regime split (theory-consistent)**: relaxing helps in calm/recovery (2020: 0.25→2.68) but
  the cap HELPS in the 2022 bear (−0.26 capped vs −0.72 uncapped) — the low-vol anomaly in stress.

## Proposal (discuss, NOT deployed)
Make `risk_gates.realized_vol.max_annualized` **regime-aware**: ~1.0 in BULL_CALM/BULL_VOLATILE,
~0.6 in BEAR; keep a ~1.5 hard ceiling. Validate with live PatchTST scores + shadow-test before
any graduate. Survivorship mitigated (drop-top-1%, median) not eliminated; 2022 is one bear
episode; proxy ranker not live model — all stated in the research doc.

## Note
Supersedes the first (weaker) version of this PR that leaned on a survivorship-biased mean and
had no theory — replaced after operator pushback ("理论 + 数据支持; 重新做").
