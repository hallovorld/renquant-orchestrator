# renquant105 — alpha-discovery plan (candidate table first, proportionate validation)

Status: **PROPOSAL** — 2026-06-28.

Reorganized around *finding* alpha, not vetoing it. Supersedes the closed
validation-heavy RFC #201 (which led with a CPCV/FWER/DSR framework before any
signal had been measured). The signal hunt already produced real numbers; this
doc transcribes and structures them.

Scan product shipped with this PR: `scripts/sighunt.py` (raw cross-sectional
rank-IC vs a within-date shuffle floor) and `scripts/robustness.py`
(Newey-West HAC t-stat + half-sample + yearly breakdown). Both are READ-ONLY:
no orders, no git, no canonical writes.

---

## §1 Candidate alpha table — TESTED

Panel: 8-year daily, **2018-05-30 → 2026-06-26**, 127-name renquant-104 golden
watchlist (ETFs dropped, coverage-filtered), non-overlapping forward windows,
split/dividend-adjusted Alpaca daily bars. IC = cross-sectional Spearman
rank-IC; t-stat on **non-overlapping** windows (independent samples); net L/S =
top-decile minus bottom-decile per-rebalance return minus 11 bps round-trip
cost; "× floor" = |mean IC| ÷ placebo noise floor.

**Placebo noise floor** (200 within-date shuffles, |mean-IC| 95th-pct):
h5 = 0.0101, h20 = 0.0174, h60 = 0.0337. A signal must clear its horizon's
floor to be worth anything.

| signal | formula | horizon | mechanism | raw fields | exp. sign | mean IC | t | hit | net L/S | × floor | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **mom_12_1** | trailing 252d ret, skip last 21d | h5 | momentum / underreaction (Jegadeesh-Titman) | adj close | + | **+0.0274** | 1.88 | 0.575 | **+31 bps** | **2.73×** | **clears — but at h5 only; un-deflated t≈1.9** |
| mom_12_1 | (same) | h20 | (same, target horizon) | adj close | + | +0.0130 | 0.51 (NW≈0.87) | 0.557 | +87 bps | **0.74×** | **FAILS at target horizon** |
| mom_6_1 | trailing 126d ret, skip last 21d | h5 | shorter-window momentum | adj close | + | +0.0180 | 1.29 | 0.552 | +22 bps | 1.79× | weak echo of 12-1 |
| ma200_dist | price / 200d SMA − 1 | h5 | trend / distance-from-mean | adj close | + | +0.0145 | 1.00 | 0.552 | +30 bps | 1.45× | weak |
| short_term_reversal | −1 × trailing 21d ret | h5 | 1-month reversal (Jegadeesh 1990) | adj close | + | +0.0055 | 0.44 | 0.485 | −43 bps | 0.55× | flat / wrong-sign at multi-day |
| pct_52w_high | price / trailing-252d high | h20 | 52w-high anchoring (George-Hwang) | adj close | + | −0.0216 | −0.78 | 0.455 | −124 bps | (wrong sign) | wrong sign on this universe |

**Momentum regime-flips sign yearly** (mom_12_1 yearly mean IC):
positive +0.046 / +0.046 / +0.031 / +0.173 in 2022 / 2023 / 2024 / 2026,
**negative** −0.064 / −0.065 / −0.028 in 2019 / 2021 / 2025. The edge is
conditional, not constant.

---

## §2 Verdict

Canonical price-based trend factors have **NO stable multi-day (20/60d)
cross-sectional edge** on this universe. mom_12_1 is the only pulse, and it
clears the floor **only at h = 5** (short-term drift, borderline un-deflated
t ≈ 1.9), then **fails at the target h = 20** (0.74× floor).

The apparent 5-year (2021–26) h20 momentum edge was a **bull-momentum REGIME
ARTIFACT**: it cleared the floor (1.24×) when fit on 2021–26, but collapsed to
0.74× the moment the panel was extended to the full 8 years. The lightweight
screen — minutes of compute — caught this. That is the evidence that
proportionate validation is sufficient: a heavyweight CPCV/FWER/DSR rig was
never needed to reject this signal.

---

## §3 Forward leads — the discovery loop continues here

1. **Regime-conditioned momentum.** The yearly sign-flip shows 12-1 is
   *conditional*, not dead. Gate the momentum tilt on a regime signal (existing
   HMM regime labels) so the tilt fires only in regimes that pay momentum.
   **Cheap test:** split mom_12_1 IC by regime label — does it become stable and
   positive *within* momentum-on regimes? If yes, the conditional signal is
   real and the unconditional null is just regime-averaging.

2. **Orthogonal signals (different family — price-trend is exhausted).**
   Analyst-estimate revisions / fundamentals, which carry low correlation to
   price-trend. **Prerequisite, non-negotiable:** a point-in-time data audit
   first — publication timestamps, revision history, coverage, lag, survivorship
   — *before* any IC claim. No IC number on this family is trustworthy until the
   data is proven point-in-time.

---

## §4 Proportionate screen

Every candidate gets the **same cheap screen** the hunt used: raw
cross-sectional IC vs a within-date shuffle floor, plus regime / half-sample
stability, plus net-of-cost top-decile L/S. Only a candidate that survives this
cheaply — **stable across regimes and net-positive** — earns heavier
validation, and only then. We do **not** pre-build CPCV / FWER / DSR. This is a
solo agile project; validation is proportionate to it.
