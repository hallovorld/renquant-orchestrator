# renquant105 intraday system — design proposal

2026-06-27.

## What & why
Operator asked for a complete, professional, scientific design for an INTRADAY
trading system (renquant105) on the ~$10.6k Alpaca account: how to train the model,
get intraday data, decide; whether data/model/logic must change; speed/GPU; stricter
gating for unreliable trades; expected trade-count rise. This PR is the **design
proposal for Codex review** — no code.

## How it was grounded
Five parallel read-only research sweeps (regulatory/cost feasibility, 104→105 delta,
intraday data/latency, intraday model/training/GPU, stricter trade-vetting) + a
direct live-account check. All read-only; no git in the live tree.

## Headline findings (these shape the design)
- **PDT is gone (verified):** the $25k/3-trade rule was eliminated 2026-06-04; the
  live account shows `pattern_day_trader=False`, 4× intraday BP $37.7k. Regulation
  is no longer the blocker — **economics (cost vs tiny intraday edge) is.**
- **Not greenfield:** the intraday data + feature + model-swap infrastructure is
  already built and parked (disabled 2026-05-04). 105 is re-activation + an intraday
  model + tighter gates + a buy path.
- **No GPU needed; latency isn't the bottleneck.** The bottlenecks are IEX data
  coverage (~50% of universe lacks intraday history → liquid coverage-gated universe;
  $99/mo SIP only for live NBBO fills) and incremental ingestion.
- **QUANTITATIVE FEASIBILITY = likely NO-GO for intraday alpha at this size/data
  (§A):** RT cost ~11 bps vs ~1 bp single-bar edge (underwater ~10×); net-Sharpe
  band −2.0 to +0.5 (centered negative); 104's own realized Sharpe is sub-1. So the
  design pivots to a **measurement-grade cost-charged shadow harness** (no real
  money) + intraday **execution-timing/risk** on the daily book — NOT a new-alpha
  churn machine. Live intraday alpha stays OFF unless Phase-1 empirically clears
  net-Sharpe ≥1.0 + OOS IC ≥0.03 placebo-clean + DSR>0.
- **The decisioning is** a strict conjunctive fail-closed gate stack (cost-edge,
  conformal lower-bound, entry meta-label, CHOPPY no-trade, P&L circuit breaker,
  top-k under scarcity), with a
  **kill condition** if Phase-1 net-of-cost edge isn't placebo-clean.

## Deliverable
- `doc/design/2026-06-27-renquant105-intraday-system.md` — the full design: honest
  feasibility verdict, what's reusable vs new, data/model/logic deltas, GPU verdict,
  the gate stack, shadow-first deploy, a validation-gated phased rollout with a kill
  condition, and the open decisions for the operator.

## Next
Operator decisions (universe size, label horizon, SIP go/no-go, cost-edge bar,
single-horizon scope, kill condition) → then a Phase-0 (data) implementation PR.
Codex review on feasibility + the validation/kill discipline.

## Revision 2 — Codex CHANGES_REQUESTED resolved (2026-06-27)
Codex (haorensjtu-dev) requested changes on PR #198 with 8 blocking findings + an
execution-plan-gaps section. Addressed substantively, not papered over:
1. **Feasibility reproducibility + math** — added `scripts/research_intraday_feasibility.py`
   (READ-ONLY, runnable; every number from explicit formulas with units: RT cost,
   `E[edge]=IC·σ_xs·factor`, cost-clearing horizon via the explicit `σ_cum(h)=σ_xs·√h`
   random-walk + independence assumption, Fundamental-Law net Sharpe, an IC×σ_xs×cost
   sensitivity grid, a block-bootstrap CI) + `tests/test_research_intraday_feasibility.py`
   (17 tests). Fixed the arithmetic: `11/(0.05·1.75)=125.7 bps` is the *required cumulative
   dispersion*, and the doc's "~3.6%/2.5-day" = the IC=0.03,k=1.75 cell (3.67%/2.76d), now
   derived. §A rewritten to cite the script as the reproducible artifact. **Still NO-GO.**
2. **One primary horizon** — standardized the whole suite on **open→close (intraday-only)**;
   every contract (label, embargo-in-bars/session-aware, cost, IC, hit-rate, killed-winner,
   shadow, DSR/PBO, attribution, monitoring) uses it; flagged daily `ticker_forward_returns`
   as insufficient → M0 builds a session-horizon return surface.
3. **Statistical bar + power** — DSR pinned as the probabilistic Deflated Sharpe (Bailey &
   LdP), require **PSR/DSR ≥ 0.95** (dropped vacuous "DSR>0"); defined the full trial
   universe carried into N; replaced raw run/date counts with a **power/MinTRL-derived
   minimum in effective-independent observations**; phase gates use CIs + effective N.
4. **Point-in-time M0 universe** — rewrote selection to as-of-date-only info (lagged ADV,
   listing eligibility, halt/delist, corp-action mapping, IPO seasoning, fail-closed
   missingness), frozen + fingerprinted per date; removed the look-ahead "complete history
   over the window" rule.
5. **Feed/cost provenance** — M0/M1 fingerprint feed/tier/venue/adjustments/bar-rule/
   retrieval; cost model from MEASURED arrival/quote/fill data (11 bps = explicit
   placeholder); historical-vs-live IEX parity asserted; SIP = fresh shadow parity/cost
   experiment before live.
6. **Triplication removed** — replaced "touch all 3 copies" with the pinned-subrepo
   ownership/paired-PR matrix (base-data owns the primitive, pipeline consumes the contract,
   umbrella pins), contract tests, pin order, compat-shim retirement; specified where
   `renquant-strategy-105` is created + the manifest/fingerprint flow.
7. **Kill-switch state machine** — defined `NO_NEW_RISK` (exits allowed) / `CANCEL_OPEN_ORDERS`
   / `FULL_HALT` (integrity only); daily-loss breaker → `NO_NEW_RISK` (NOT all-orders-off);
   pinned exit price authority + max staleness + broker/feed-disagreement behavior; made the
   loss threshold a consistent **−5%** across FMEA/metrics/M2/M3.
8. **Broker-contract milestone** — added **M0.5**: current `buying_power`/intraday-margin
   fields, rejection/deficit handling in paper/shadow, leverage caps independent of broker
   max, fail-closed on Alpaca field migration; stopped claiming "operationally clear" until
   encoded; caveated the verified live flags.
**Execution-plan gaps:** split H1 (intraday alpha) from H2 (execution-timing/risk) with
independent acceptance; defined the two comparators (pipeline parity vs strategy lift);
required per-gate ablations with multiplicity correction (gate proliferation ≠ validation);
added a minimum-live-sample + exposure-schedule ladder for M3 scaling; replaced off-PR
"research transcripts" with the committed script + primary references as the auditable inputs.
