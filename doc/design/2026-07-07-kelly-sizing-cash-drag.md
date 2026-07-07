# Kelly sizing is the binding constraint for cash drag

**Status**: DESIGN — for cross-agent review
**PR**: orchestrator
**Supersedes**: Earlier analysis that misidentified VetoWeakBuys as the #1 lever

## Bottom line

62% cash is NOT caused by filtering too many candidates. 6+ candidates pass
all gates daily — enough to fill 2 open slots. The binding constraint is
**Kelly sizing parameters**: even if all 8 slots fill at kelly target, the
book deploys only 55.6%.

## Data-backed decomposition

Source: `data/runs.alpaca.db`, 07-06 daily-full run.

| Component | Cash drag contribution | Mechanism |
|---|---|---|
| Structural Kelly sizing | **44.4%** | 8 × avg kelly(6.9%) = 55.6% max |
| Empty slots | ~13.8% | 6/8 filled (AVGO/MCHP/GRMN pending at broker) |
| Underweight positions | ~3.7% | Positions below kelly, gap < top_up_threshold |
| **Total** | **~62%** | Matches observed cash |

### Why VetoWeakBuys is NOT the binding constraint

The previous analysis (PR #408) was wrong. VetoWeakBuys blocks 81.6% of
candidates (28/34 on 07-06), but:
- 6 candidates pass all gates — more than enough for 2 open slots
- AVGO and MCHP were selected and have pending buy orders at broker
- ZM, NFLX, CRM, CAT passed but hit `candidate_not_selected` (no slots)
- **Candidate scarcity is not the problem; position sizing is.**

VetoWeakBuys correctly filters low-conviction names. The floor should NOT
be loosened to "fix" cash drag — it's doing its job.

## Lever analysis with theory

### Lever 1: Kelly fractional (0.3 → 0.5) — **+27% deployment**

**Current**: `fractional: 0.3` (30% Kelly).
Set on 2026-06-11 when sigma_horizon was corrected from 252d → 60d.
The rationale was "keep total deployment sane (~56% vs ~96% at caps)."
But 56% deployment = 44% structural cash drag.

**Theory**: Half-Kelly (f=0.5) is the institutional standard (Thorp 1975,
MacLean et al. 2011). It sacrifices 25% of expected log-growth for 50%
reduction in variance. 30% Kelly is more conservative than any published
institutional recommendation for a diversified book.

**Projected impact** (07-06 holdings, same mu/sigma):

| fractional | MU | PANW | CSCO | SOFI | GRMN | AMZN | Total | Cash |
|---|---|---|---|---|---|---|---|---|
| 0.3 (now) | 5.2% | 7.3% | 7.3% | 7.2% | 7.3% | 7.3% | 41.7% | 58.3% |
| 0.4 | 7.0% | 9.7% | 9.7% | 9.6% | 9.7% | 9.7% | 55.6% | 44.4% |
| **0.5** | **8.7%** | **12.0%** | **12.0%** | **12.0%** | **12.0%** | **12.0%** | **68.7%** | **31.3%** |
| 0.7 | 12.0% | 12.0% | 12.0% | 12.0% | 12.0% | 12.0% | 72.0% | 28.0% |

At fractional=0.5, 5 of 6 names hit `max_concentration=12%`, meaning
`max_concentration` becomes the new binding cap. Going past 0.5 yields
diminishing returns without raising `max_concentration`.

**Risk**: Higher sizing = higher drawdowns. Must validate via backtest sweep
(fractional × max_concentration grid) with strict per-regime drawdown checks.

### Lever 2: max_concentration (12% → 15-20%) — unbinds cap at frac≥0.5

At fractional=0.5, the 12% cap is binding for 5/6 names. Raising to 15%
would allow full half-Kelly expression.

**Theory**: Kelly with max_concentration acts as a truncated Kelly. Truncation
at levels well below f* (which averages ~18% for current holdings) wastes
information. The standard approach is to cap at f*/2 or higher (half-Kelly
is already half of optimal).

**Risk**: Concentration risk. Higher per-name weight = larger single-name
drawdown impact. Must pair with:
- Sector weight cap (currently 35% — sufficient)
- Correlation check (already active)
- Portfolio-level drawdown halt (35% max DD)

### Lever 3: top_up_threshold (5% → 2%) — +9.8% deployment

Current threshold requires a 5% gap-to-kelly before top-up fires. Most
positions have 2-3% gaps — just below the threshold.

| Threshold | Eligible | Top-up volume | Names |
|---|---|---|---|
| 5% (now) | 1 | 5.0% | GRMN |
| 3% | 1 | 5.0% | GRMN |
| **2%** | **3** | **9.8%** | **CSCO, SOFI, GRMN** |
| 1% | 3 | 9.8% | CSCO, SOFI, GRMN |

Diminishing returns below 2% (same set eligible). 2% is the right target.

**Risk**: Low. Top-up only fires for names already held and passing conviction.
No new name risk, only sizing risk — bounded by max_concentration.

### Why NOT 50% in one name

The operator asked: "MU和FTNT如果买了50%不就发达了吗"

Kelly theory (Thorp 1975, Vince 1992): f* = mu / sigma^2. For MU:
- mu = 0.046 (60d calibrator expected return)
- sigma ≈ 0.50 (60d annualized realized vol)
- f* = 0.046 / 0.25 = 18.4%
- 50% = 2.7× full Kelly → **negative expected log-growth** (overbetting)
- The geometric growth rate g(f) = mu·f - sigma^2·f^2/2 peaks at f*. At
  f=50%, g drops below zero.

But 0.3 × f* = 5.5% IS too conservative. Half-Kelly (9.2%) is standard.

## Proposed validation sweep

**2D grid**: fractional × max_concentration

| | max_conc=12% | max_conc=15% | max_conc=20% |
|---|---|---|---|
| frac=0.3 (incumbent) | ✓ | ✓ | ✓ |
| frac=0.4 | ✓ | ✓ | ✓ |
| frac=0.5 | ✓ | ✓ | ✓ |
| frac=0.7 | ✓ | ✓ | ✓ |

12 variants × 3 seeds {42, 43, 44} = 36 sim runs.
Add 1 A/A control (incumbent config, offset seeds {1042, 1043, 1044}).

**Decision criteria** (unanimous across 3 seeds):
1. Sharpe ≥ incumbent Sharpe (no risk-adjusted degradation)
2. Max DD ≤ 1.2 × incumbent Max DD (≤20% drawdown inflation)
3. Per-regime check: no regime shows >2σ Sharpe degradation
4. Turnover ≤ 1.5 × incumbent (no excessive churn)
5. Cash % reduction ≥ 10pp vs incumbent
6. Placebo (shuffled-label) gap maintained

**Secondary sweep**: top_up_threshold {0.05, 0.03, 0.02, 0.01} at the
winning (fractional, max_concentration) point. 4 × 3 seeds = 12 runs.

## Execution order

1. Build sweep runner (this PR)
2. Run 2D grid (~2-4h)
3. Results memo with §7.4 Tier 3 verdict
4. If a variant wins: config-only change to strategy_config.json via PR
5. Then: top_up_threshold sweep at the winning point
6. VetoWeakBuys sweep (PR #408/#409) remains useful for breadth research
   but is NOT the cash-drag fix

## What about 105?

105 is a 盘中 engineering evolution (memory: renquant105-is-trend-signal-quality).
It inherits 104's Kelly sizing parameters. Fixing Kelly sizing here
automatically fixes 105's structural cash drag too.
