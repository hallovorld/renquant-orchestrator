# Design v3 — Short Capability, Restructured Around the Evidence

**Status:** design / awaiting review (no code change)
**v3 rationale:** v2 kept v1's skeleton (single-name shorts as the
centerpiece) and merely annotated it with the literature findings. The
findings warrant a restructure: in an ETB-only universe, single-name short
alpha is the literature's *predicted failure* (Drechsler & Drechsler;
Muravyev et al. 2025 JF) and our own E1 backtest agrees. v3 reorders the
design around what shorting is actually FOR in this account.

---

## 1. The three uses of shorting, ranked by evidence (the spine of v3)

| Rank | Use | Evidence basis | Phase |
|---|---|---|---|
| 1 | **Insurance** — hedge the book in risk-off states (short SPY / long SH) | Moreira–Muir 2017 (vol-managed exposure raises Sharpe); Faber 2007; needs NO stock-picking skill | **Phase A — the core deliverable** |
| 2 | **Efficiency** — a small short leg (e.g. 110/10→120/20) finances long overweights, converting EXISTING long signal into more IR via a higher transfer coefficient | Clarke–de Silva–Thorley 2002; cvxportfolio practice (borrow cost inside the QP) | **Phase B — second** |
| 3 | **Conviction shorts** — picking fallers | Predicted to fail in ETB universe; E1 confirmed (24–36% hit, −3.7%..−7.5% P&L) | **Phase C — SHELVED by default** |

## 2. Phase A — Index hedge (the deliverable)

- **Instruments:** short SPY (margin) or long SH (cash, no borrow, daily-reset
  drag) — operator choice pending (Q1).
- **Triggers (any active → hedge on):** (a) drawdown breaker armed;
  (b) hard_bear; (c) **vol-managed**: realized 20d vol > target ⇒ hedge ratio
  h ∝ (vol/target − 1), capped.
- **Sizing:** notional = h·β_book·NAV, β = 60d rolling OLS; h primary 0.5;
  hedge notional within the ≤20%-NAV margin budget.
- **Exit:** trigger state clears for ≥2 consecutive sessions → unwind (debounce
  both ways). PDT-aware (multi-day by construction).
- **Gate:** E6 replay (2022 bear; 2025-04 dip; dead window; full year):
  PASS = MaxDD cut ≥25% in stress windows AND bull-window drag ≤2% NAV/yr.
- **Plumbing:** minimal — one instrument, no per-name borrow checks, reuses
  breaker/regime states. Config: `risk.hedge.{enabled, mode, h, vol_target}`.

## 3. Phase B — Efficiency extension (110/10 first)

- **Mechanism:** allow the QP a bounded negative-weight sleeve (gross ≤120%,
  short leg ≤10–20% NAV, borrow cost priced inside the objective per
  cvxportfolio practice). The short leg holds the *lowest-rank liquid names*
  not for their fall, but to finance bigger top-rank longs.
- **Why it can work where Phase C can't:** it monetizes the LONG side's
  proven IC (top-8 selection edge +0.264z) through relaxed constraints —
  no claim that shorts fall, only that they lag (which IS what bottom ranks
  do: 46–48% underperformance vs SPY is unhelpful for naked shorts but fine
  as a financing leg paired against stronger longs).
- **Gate (new E8):** replay the QP with and without the short sleeve on
  identical inputs; PASS = net IR improvement with turnover/borrow priced,
  plus drawdown not worsened. Runs after the WF-gate machinery for longs is
  green (it reuses it).
- **Guards:** same exit chain (§5), squeeze guard, 2-name... n/a — sleeve is
  rank-driven and small; per-name short cap 3% NAV; rebound veto applies.

## 4. Phase C — Conviction shorts (shelved)

Kept only as a documented option. Reopening requires **E5** (short-interest
dynamics, post-FINRA-backfill — the one single-name signal with literature
support) to pass the pre-registered bar. Operator mandate if ever reopened:
bottom-5% + N-of-N μ + all vetoes, **max 2 names**, default NO. E2/E3/E4
from the v2 spec are **deprioritized to optional sensitivity studies** — the
literature says their prior is near-zero in our universe; we do not spend
compute on them before E6/E8/E5.

## 5. Exit chain — per-phase applicability (v3.1 fix)

The v2 chain was designed for conviction shorts; applied wholesale it is
WRONG for a hedge (stopping out insurance while it is doing its job) and
redundant for a QP sleeve (fights the daily re-optimization). Applicability:

| Trigger | A hedge | B sleeve | C conviction |
|---|---|---|---|
| 1 hard stop | **off** (hedge loss = book gain) | on | on |
| 2 borrow/buy-in | n/a (SPY) | on | on |
| 3 event vetoes + 3b rebound veto (entries) | n/a / rebound n/a | on | on |
| 4 trailing profit lock | **off** (insurance ≠ trade) | off (QP owns) | on |
| 5 signal exit (hysteresis) | n/a | off (QP owns) | on |
| 6 rank exit | n/a | off (QP owns) | on |
| 7 time barrier 20d | **off** (trigger-state governed) | off (QP owns) | on |
| 8 account margin breaker | on | on | on |
| A-only: trigger-state clear ≥2 sessions → unwind | **on** | — | — |

## 5.1 Chain detail (Phase C reference, unchanged from v2 §4.5)

Hard stop (EOD + intraday rail, gap-through next-open) → borrow/buy-in risk →
event vetoes (earnings, ex-div) + **rebound veto on entries** (Daniel–Moskowitz:
no new shorts when SPY 60d < −10% and 5d > +3%) → trailing profit lock
(15%-arm, ⅓ giveback) → signal exit with hysteresis → rank exit → 20d time
barrier (E7) → account margin breaker (>70% maintenance ⇒ cover all).
PDT: same-day cover only for hard-risk triggers; anti-martingale daily cap
re-check (losing shorts grow themselves; trim back to cap).

## 6. Execution order

1. **E6 hedge replay** (can run now) → review → Phase A implementation
   (config-gated, paper-shadow ≥2 weeks) → live.
2. **E8 efficiency replay** after long-side WF gate is green.
3. FINRA backfill → **E5** → only then any Phase-C discussion.
4. All experiments on `epic/model-edge-experiments`; production changes via
   normal PR + pin flow; WF gate remains the promotion authority.

## 7. Operator questions (unchanged)
1. Phase-A instrument: short SPY vs long SH?  2. Margin budget 20% or 10%?
3. Short-term-gains tax on covers acceptable?

*Companions: experiment spec (E2–E8) and the literature review doc.*
