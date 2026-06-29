# renquant105 — DIRECTION DECISION

Status: **DECISION RECORD (for Codex + operator discussion)** — 2026-06-28.
Author: Ren Hao (with Claude Opus 4.8). The operator delegated this call to me;
this PR is the discussion vehicle. It is the single durable record of the pivot.

This is a **decision record, not a research framework**. It transcribes the
evidence this session established and states the resulting decision. It does
**not** stand up a CPCV/FWER validation cathedral — the per-signal scans that
produced the evidence below already shipped (`scripts/sighunt.py`,
`scripts/robustness.py`, `scripts/regimemom.py`, `scripts/fundamentals_scan.py`)
and are documented in the §1 references.

---

## §1 The rigorous finding (the keystone)

**Directional cross-sectional alpha is exhausted on the current 134-large-cap
universe + current data** — across every regime / signal / combination /
盘中·盘后 we tested this session, read-only, with proper OOS / CI / placebo
injection. The binding constraint is **DATA + UNIVERSE, not validation method or
model architecture.** Stated honestly: these are faithful read-only diagnostics
on a *current-watchlist, survivorship-biased* panel; they cannot prove the
universal absence of edge, but every direct test points the same way, and the
null is exactly what the literature predicts for large-cap cross-sectional
anomalies. On the current inputs, the answer is NO.

The evidence, with numbers:

- **A1 — the existing model's directional skill is a thin slice, not a book.**
  Read-only audit of the live model's per-name scores: genuine (leak-controlled)
  IC has a **CI that includes 0**, and it is **not leak-free** — predictor-side
  persistence balloons the naive IC. The apparent skill is **entirely a ~10%
  BEAR-slice artifact**; in BULL_CALM, which is **~79% of live time**, the
  genuine IC is **≈ −0.003 (a coin flip)**. Tradable net Sharpe ≈ 0. (Consistent
  with the ledger diagnostic `doc/research/2026-06-27-renquant105-trend-signal-baseline.md`,
  whose own faithful-cohort verdict is **UNDETERMINED** on ≈1 overlap-ratio of
  live data — i.e. the live ledger cannot yet *prove* skill either; the
  read-only model audit and the ledger both fail to surface a usable directional
  edge.)

- **A2 — ML combination buys nothing (Gu–Kelly–Xiu style).** Sector+beta
  neutralized, walk-forward, **1002 OOS dates**: every multi-factor combination
  is **dominated by a single momentum factor**, and that momentum is itself a
  **recent-bull regime artifact** (null on the full sample). **No multi-factor
  synergy** — combining the available factors does not manufacture an edge that
  the best single factor lacks.

- **Single factors — null, negative, or net-negative under faithful costs.**
  - Price-trend (`sighunt.py` / `robustness.py`, 8y 2018→2026, 134 names,
    11 bps round-trip): five canonical factors show **no robust unconditional
    20/60d edge**. mom_12_1 clears the placebo floor **only at h=5** (un-deflated
    t≈1.9); at the h=20 target it has positive net L/S (+87 bps) but an **IC that
    does not clear the floor (0.74×)**. The 5-year momentum "signal" is a
    **bull-regime artifact** — IC fell from 1.24× to 0.74× the moment the panel
    extended to the full 8 years.
  - Regime-conditioned momentum (`regimemom.py`): **NO.** The yearly sign-flip
    **survives inside UP-trend** (2021 was 100% UP yet momentum IC = −0.065,
    the worst year), so a trend gate cannot isolate the momentum-paying state.
  - Fundamentals (`fundamentals_scan.py`, value/quality/growth): **nothing is a
    usable long edge.** Value is the strongest signal and points the **wrong way
    (negative)** and is only **soft** once overlap is respected (EY-252d
    non-overlapping t ≈ −2.4, down from an overlap-inflated −7.9); quality/growth
    are **null**. Regime-conditional, large-cap-weak.
  - PEAD / minute: null or net-negative under faithful costs.

- **BEAR / short audit — not a short edge either.** The BEAR-slice skill is a
  **V-recovery LONG-ranking** (config-forbidden to act on as a short), the short
  leg is **net-negative**, effective **N ≈ 6**, the bootstrap **CI includes 0**,
  and 盘中 (intraday) adds nothing. There is no harvestable directional edge on
  the short side.

**Conclusion of §1.** The binding constraint is the **inputs** — ~134 liquid US
large-caps + the current price/fundamental data. Cross-sectional anomalies are
documented to be *weak* in large-caps; our consistent null is exactly what that
literature predicts. This is not a validation failure and not a model-architecture
failure: more rigorous validation or a fancier model will not change a coin-flip
primary on these inputs.

---

## §2 The decision — two tracks

### Track A (immediate, NO new inputs) — non-directional improvement of the EXISTING book

Test a **meta-label entry filter** (López de Prado): a secondary model that
predicts **P(a given primary model pick is profitable)** and only takes the
high-confidence subset, to improve the existing book's **EXPECTANCY** — *not* to
create new alpha.

**Honest caveat, stated plainly:** meta-labeling improves the **precision of
acting on a primary signal**; it **cannot manufacture edge from a coin-flip
primary.** Given §1 (BULL_CALM genuine IC ≈ −0.003), the **first step is to
confirm there is a *conditional* signal worth filtering** — i.e. that the model
is measurably better in some identifiable state (regime, surprise window,
liquidity, dispersion). **If there is no conditional state where pick quality is
materially higher, Track A is also null, and we say so.** No over-claim.

Secondary non-directional levers (note, do not start): **vol / risk-timing**
(minute data is verified to improve volatility estimation — sizing, not
direction) and **execution / cost** reduction. These "lose less / size better /
enter better" levers improve realized expectancy without any directional edge.

### Track B (the real directional path — OPERATOR-level decision; FLAG, don't start)

A genuine directional 105 requires **changing an input.** Two candidates:

- **Broaden / down-cap the universe.** Cross-sectional anomalies are **strong in
  small/mid-cap, weak in large-cap**. This is the most literature-supported path
  to real directional edge — but it **conflicts with the large-cap liquidity
  design** of renquant-104 and is a structural change.
- **Acquire new data.** The estimate-revision snapshotter (#205) is already
  accruing **point-in-time revision history**; alt-data is a further option.
  New orthogonal, PIT-clean inputs are the other documented large-cap path.

Both are **bigger decisions that take months and conflict with the current
design** — explicitly **the operator's call**, not something I start under this
PR.

---

## §3 Why this decision (honest)

The original 105 goal — **"catch more / more-accurate trends"** — requires a
**directional edge**, which the §1 evidence says is **not available on the
current inputs.** Therefore a real, directional 105 needs **Track B (an input
change).**

**Track A is the immediate, low-cost thing that can help the LIVE book NOW
without new inputs — but it is "lose less / size better / enter better", NOT
"new alpha."** This distinction is the crux of the decision and must not be
blurred: **do not mistake Track A for solving the directional problem.** Track A
raises the expectancy of acting on whatever conditional edge already exists (if
any); Track B is the only path that creates directional edge that isn't there
today.

---

## §4 Proposed first concrete step

**Track A, step 1 — test conditional pick-quality, before building any filter.**
Rigorously test whether the existing model's pick quality is **conditionally
predictable**: is there a measurable state (regime / dispersion / surprise
window / liquidity) where its **hit-rate / expectancy is materially higher**?

- **If YES:** build the meta-label filter on that conditioning, and measure the
  **EXISTING book's expectancy improvement net of cost** — proper OOS, CI,
  net-of-turnover. Promote only if the lift is real and net-positive.
- **If NO:** report that **Track A is also null**, and that **Track B (an input
  change) is the only remaining path** to a directional 105.

Same rigor as A1 / A2: OOS, CI, net-of-cost, no over-claim. The cheap conditional
test is run **before** any filter is built, so we don't construct a filter on a
non-existent conditional signal.

---

## §5 References (this session's evidence — already shipped, read-only)

- `doc/design/2026-06-28-renquant105-alpha-discovery.md` — price-trend candidate
  table + regime-conditioning lead (`sighunt.py`, `robustness.py`,
  `regimemom.py`).
- `doc/research/2026-06-28-renquant105-fundamentals-scan.md` — value/quality/growth
  scan (`fundamentals_scan.py`).
- `doc/research/2026-06-27-renquant105-trend-signal-baseline.md` — live-ledger
  trend-signal diagnostic (verdict UNDETERMINED on ≈1 overlap-ratio).

All scans are **read-only**: no orders, no git in the live tree, no canonical
writes. Every panel is **current-watchlist / survivorship-biased**, so each
verdict is "no robust edge surfaced **under this diagnostic**", not a universal
proof of exhaustion — but the diagnostics agree, and the inputs (large-cap
cross-section) are the documented reason.
