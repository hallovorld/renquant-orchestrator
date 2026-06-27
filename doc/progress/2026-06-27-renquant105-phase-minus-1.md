# renquant105 Phase -1 — cheap feasibility gate (measured σ_oc + STOP/GO)

2026-06-27.

## What & why
Ran the renquant105 **Phase -1** read-only feasibility gate — the FIRST gate in the 105 master DAG,
a bounded go/no-go that must run BEFORE the 10-17-week M0->M3 build. Spec + pre-registered STOP/GO:
`doc/design/2026-06-27-renquant105-Phase-minus-1-cheap-feasibility.md` (design PR #198). The single
load-bearing 105 assumption is the open->close cross-sectional dispersion `σ_oc ≈ 150-250 bps`, which
§A only *assumes*. Phase -1 **measures** it (and three siblings) cheaply so the full stack is not
built on an unmeasured prior. Thresholds applied EXACTLY — no post-hoc tuning.

## Findings (read-only Alpaca data API, SIP tape; 142-name live strategy-104 universe; 1258 sessions 2021-06→2026-06)
- **σ_oc (THE number):** std-based **median 152.5 bps** (p25 130.3 / p75 186.7) — *just inside* the
  assumed 150-250 band's lower edge. Robust (MAD/IQR) estimates **114-115 bps** sit *below* 150 (the
  std is tail-lifted). Causal/event-time check (entry ≥09:35 ET, 30-session sample) = **200.2 bps**,
  so the daily-OHLC proxy is **not** inflated by the opening cross. -> criterion (b) PASS, knife-edge.
- **Breadth:** 142/142 names valid every session -> criterion (c) PASS by a mile (floor is ~4).
- **Intraday coverage:** **142/142 names have minute history, 0.0% missing** -> the design's
  "~50% had no intraday history" (2026-05-04 disable cause) is **REFUTED today** -> criterion (a) PASS.
- **Cost:** measured midday RTH half-spreads 0.5-6.8 bps (~6 bps round-trip), floored at the §A
  11 bps prior -> 11 bps `≤` 17 bps -> criterion (d) PASS (prior is conservative-not-optimistic).
- **Net-edge band (reported, NOT a pre-registered gate):** gross = IC·σ_oc·1.0, net = gross − 11 bps:
  **IC 0.03 -> −6.4 bps; IC 0.05 -> −3.4 bps — NEGATIVE at both anchors.**

## Verdict: **GO to M0** (all four pre-registered conditions met) — with a pinned caveat
Applying the doc's STOP/GO table EXACTLY, (a)-(d) all pass -> GO. **But** the GO is fragile: σ_oc is
knife-edge (robust estimators below the floor) and the **measured net-edge is negative at plausible
IC**. A Phase -1 GO only authorizes standing up M0; it does NOT assert tradability. M0 (calibrated
cost + point-in-time universe) and M1 (frozen-policy replay) must clear the net-edge hurdle that
Phase -1's cheap bounds do not. Net-edge is the decisive risk M0 must confront first.

## Deliverables
- `scripts/research_phase_minus_1_feasibility.py` — reproducible, read-only (data API only, no
  orders, no writes outside the repo), pinned thresholds, `--json` / `--offline` modes; SIP feed
  (end-capped for the recent-SIP restriction) with IEX fallback; cost from historical RTH quotes
  (not stale latest-quotes).
- `tests/test_research_phase_minus_1_feasibility.py` — 18 network-free pure-function tests locking
  the pinned thresholds + the STOP/GO decision logic.
- `doc/research/2026-06-27-renquant105-phase-minus-1-results.md` — full measured report
  (σ_oc distribution vs assumed, breadth, coverage finding, cost, net-edge band, verdict, sources,
  run timestamp, universe snapshot).

## Guardrails
Zero writes / zero git to `/Users/renhao/git/github/RenQuant` (`.env` + strategy config READ only);
no canonical data path touched; data API read-only (no orders); `≤5-day / ≤1-week` cap met with huge
margin (sub-minute run). PR opened for review only — NOT self-approved/merged.
