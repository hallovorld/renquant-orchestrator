# L2 online allocation — a backtest of the Hedge engine over point-in-time replay arms

The empirical companion to orch#918 §2 and the merged engine (orch#923). Every
parameter was frozen before any output; the deployed values are unchanged by
anything below. Structure per the operator's standard: formal setup → theorem
instantiation → enumerated assumptions → results → sensitivity → failure
modes → what this does not show.

Reproducibility: `data/2026-08-09-l2-backtest-daily.csv` (541 daily rows: the
three arms' book returns, the Hedge book return, and the full weight path) +
`data/2026-08-09-l2-backtest-verify.py` (recomputes every reported statistic
AND re-runs the Hedge recursion from the arm columns alone, verifying the
committed weight path) + `data/2026-08-09-l2-backtest-derivation.py`
(provenance-only: machine-local OHLCV, the emitted panel replay matrix, and
the dense momentum rescore) + `data/2026-08-09-l2-backtest-inputs.manifest.json`
(r1 P1: every machine-local input hash-pinned — momentum scores sha256, panel
replay matrix digest-of-digests ×1685, OHLCV universe ×157, sector-map sha,
sibling repo HEADs; the derivation verifies every digest BEFORE deriving and
refuses on mismatch) + `data/l2_staleness.py` (r1 P2: the singular
7-calendar-day staleness rule, pinned by `tests/test_l2_backtest_staleness.py`).

## 1 · Formal setup

Arms `i ∈ {panel, mom_slow, mom_fast}`, N = 3. Each arm holds, each trading
day `t`, the equal-weighted **investable top-3** of its own score
cross-section: names ranked by the arm's most recent score dated ≤ t−1 (age ≤ 7
CALENDAR days — the single staleness rule; the derivation header and code
both carry it), restricted FIRST to names with a live price return at
`t`, THEN ranked (§6 records the failure that ordering the other way causes).
Arm returns `r_i(t)` are total-return, from the production TR primitive.

Weights follow the merged engine's exact recursion (orch#923
`hedge_step`/`apply_champion_floor`):

```
w̃_i(t+1) = w_i(t) · exp(η · clip(r_i(t), −C, +C))         η = 0.21, C = 0.05
w(t+1)   = Floor_{0.5, panel}( w̃(t+1) / Σ w̃(t+1) )
```

The portfolio realizes `Σ_i w_i(t) · r_i(t)` with weights formed strictly
from information through `t−1` (rule 2 of the §2 contract). Baselines:
champion-only (`w ≡ e_panel`), uniform (`w ≡ 1/3`), and each arm standalone.

## 2 · The theorem — corrected after review (r1 P0), and the correction is a proof

**The first draft claimed the unconstrained Hedge bound while deploying a
champion floor. Codex's counterexample is exact**: with clipped returns
panel = −0.05 and mom_slow = +0.05 every day, the floored portfolio earns at
most 0/day while the best arm earns +0.05/day — regret 27.05 at T = 541,
far above any O(√T)-flavoured claim. **No bound versus the unconstrained
best arm exists for this algorithm.** The unconstrained comparison is kept
below as description only.

**What the deployed algorithm actually is — and the guarantee it actually
has.** `apply_champion_floor` rescales non-champion weights proportionally
onto the face `{w_panel = 0.5}`. That rescale IS the Bregman (KL) projection
onto the constraint set `K = {w ∈ Δ² : w_panel ≥ 0.5}`: minimising
`Σ w_i ln(w_i/w̃_i)` subject to `w_panel = c, Σ w_i = 1` gives, by the
Lagrangian first-order condition `ln(w_i/w̃_i) + 1 + λ = 0` for `i ≠ panel`,
`w_i ∝ w̃_i` — proportional rescaling exactly. (Numerically confirmed against
an SLSQP projection to solver tolerance this session.)

The engine is therefore **online mirror descent with the KL divergence and
Bregman projection onto K**, and the standard OMD guarantee applies against
the best comparator IN K:

```
∀ u ∈ K:  Σ_t u·clip(r_t) − Σ_t w_t·clip(r_t)
          ≤ D_KL(u‖w₁)/η + η·T·(2C)²/8
          ≤ ln2/0.21 + 0.21·541·(0.1)²/8      (D_KL max at vertex (1,0,0))
          = 3.301 + 0.142 = 3.443
```

`[knowledge anchor — projected OMD / exponentiated gradient regret; the
D_KL(u‖w₁) ≤ ln 2 step maximises over K's vertices (1,0,0), (½,½,0),
(½,0,½) with w₁ = (½,¼,¼)]`

**Measured** `[VERIFIED — verifier recomputation from the committed CSV]`:

| comparator | cumulative clipped regret | valid bound |
|---|---|---|
| best fixed weights IN K (the theorem's benchmark) | **0.0754** | **3.443** |
| best unconstrained single arm (DESCRIPTION ONLY — no theorem) | 0.1194 | none exists (counterexample above) |

The same two honest notes stand: the bound is adversarial worst-case, so
"well inside" is expected in benign markets; and at η = 0.21 the divergence
term dominates — slow adaptation bought against a bounded worst case.

## 3 · Assumptions, enumerated

1. **Arm scores are point-in-time.** Panel: per-fold WF replay, each fold's
   booster trained only on dates ≤ its train end (bt#110, structural).
   Momentum: frozen-constant composites — nothing fitted, nothing to leak.
2. **Score-to-trade lag ≥ 1 day**, staleness cap 7 calendar days.
3. **Top-3 concentration** mirrors the book's actual `panel_buy_top_n = 3`.
4. **No transaction costs inside the arms** (top-3 books turn over; §6 item 3).
   The HEDGE layer'S OWN reallocation is cost-free here because weights are
   paper-capital splits; a live phase charges costs inside `r_i` per contract.
5. **Equal-weight within top-3**; the live book's Kelly sizing is not modelled.
6. **The champion arm is a PROXY** (panel replay top-3), not the live book
   (which is a blend with different sizing and gates). All "vs champion"
   readings inherit this gap.
7. **Survivorship**: the investable filter drops names without OHLCV today —
   names that delisted are absent from history where their files are absent.
8. **One seed, no resampling** — the recursion is deterministic; the CSV is
   the complete sample, not a draw.
9. **Calendar** = the 541 days where all three arms had fresh scores and ≥3
   investable names (2024-01-03..2026-05-14 `[VERIFIED — committed CSV
   span]`; the panel replay's fold boundaries thin the Januaries, but the
   7-day staleness window carries late-December scores across the year
   boundary, so early January days survive).
10. **fwd label horizon irrelevant here** — arms are marked daily on realized
    TR returns; no 20-day overlap issue applies to this experiment.

## 4 · Results `[VERIFIED — verifier output from the committed CSV]`

| book | ann | vol | Sharpe | maxDD |
|---|---|---|---|---|
| **Hedge (η=0.21, floor 0.5)** | **+45.9%** | 34.4% | **1.33** | **−29.2%** |
| uniform 1/3 | +47.9% | 32.2% | 1.49 | −27.3% |
| champion only | +39.2% | 45.2% | 0.87 | −37.6% |
| mom_slow standalone | +48.6% | 42.2% | 1.15 | −31.0% |
| mom_fast standalone | +43.4% | 32.5% | 1.33 | −27.4% |
| panel standalone (= champion) | +39.2% | 45.2% | 0.87 | −37.6% |

Final weight path endpoint: panel 0.512, mom_slow 0.252, mom_fast 0.236.

**Reading 1 — the engine beats the champion decisively on this history:**
+6.7pp annualized, Sharpe 0.87 → 1.33, maxDD −37.6% → −29.2%. The mechanism
is mostly diversification across imperfectly-correlated arm books, plus mild
adaptation.

**Reading 2 — the floor's measured price: ≈ 2pp/yr** (uniform +47.9% vs
Hedge +45.9%). Half the capital is chained to the weakest-Sharpe arm; that is
the cost of "the worst case is today's system", now a number rather than a
slogan. The promotion decision may judge it worth paying; this record only
prices it.

**Reading 3 — a frame-dependence result that must temper earlier records:**
`mom_fast`, judged HARMFUL in blend-IC space (orch#911/#913, negative paired
ΔIC), runs a **1.33 Sharpe as a standalone top-3 book** here. Rank-blend IC
and concentrated-book return are different functionals of the same scores;
conclusions do not transfer between them. The #913 kill remains valid FOR THE
BLEND CONSTRUCTION it tested; it must not be quoted against the top-3 frame.

## 5 · Sensitivity (descriptive; the deployed η stays 0.21)

| η | 0.05 | 0.10 | 0.21 | 0.50 | 1.00 |
|---|---|---|---|---|---|
| Hedge ann | +46.4% | +46.3% | +45.9% | +45.1% | +43.7% |

Flat to η within a factor of 20 — on THIS history the floor, not the learning
rate, is the binding design choice. (Higher η also loosens the §2 worst-case
term linearly; nothing here motivates moving it.)

## 6 · Failure modes surfaced while building this (each is a finding)

1. **Rank-then-filter collapsed the calendar 541 → 135.** Taking top-3 over
   the full score cross-section and THEN intersecting with investable names
   dropped every day whose unfiltered top-3 contained a delisted/off-universe
   name. Filter-first is also the economically correct book. The first run's
   all-negative arms (−47% "panel") were entirely this artifact.
2. **Sparse-label calendars masquerade as history.** The first attempt used
   momentum scores only on fwd-label dates (383 sparse days) — 78 usable
   scattered days that produced meaningless annualizations. The dense rescore
   (652 consecutive trading days) was required before any number here could
   be trusted.
3. **Costless top-3 books flatter high-turnover arms.** mom_fast's daily
   top-3 churns hardest; assumption 4 therefore biases IN ITS FAVOR. A cost
   pass is required before any cross-arm ranking is quoted as decision-grade.

## 7 · What this record does NOT show

* Not that the Hedge book's +45.9% is achievable live — arms are cost-free
  paper top-3 books on a replay champion proxy (assumptions 4–6).
* Not that mom_fast "works" — Reading 3 is a frame-dependence datum, and the
  cost bias of §6.3 lands mostly on it.
* Not that adaptation adds value at this horizon — the Hedge's edge over the
  champion is mostly diversification; uniform beat it. What the engine adds
  over uniform is the FLOOR (worst-case containment) and the CONTRACT — paid
  for with the measured 2pp.
* Not a promotion case by itself. The promotion path stays: shadow weights
  publishing daily (merged engine), this record as the offline reference, an
  operator decision on whether 2pp/yr is the right price for the guarantee.
