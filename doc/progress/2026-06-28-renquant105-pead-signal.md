# renquant105 PEAD %-surprise — candidate signal (event-driven long-only economics + orthogonality)

STATUS:   EXPLORATORY, open for discussion (NOT a promote / live-tilt request).
WHAT:     develops the one lead from the trend/factor signal hunt — earnings %-surprise
          (PEAD) — past the cheap screen into a FAITHFUL follow-up: event-driven long-only
          economics + orthogonality. Lean candidate-style; no CPCV/FWER/DSR framework.
PIT:      NON-POINT-IN-TIME (downgraded per PR #203 review). The earnings parquet is a
          SINGLE CURRENT one-shot harvest; epsEstimated is today's value, NOT a captured
          pre-announcement consensus; lastUpdated is a generic floor pre-2024-09. The +1d
          convention controls ENTRY TIMING only. ALL results are exploratory, not PIT-clean.
WHY/DIR:  the cheap screen flagged %-surprise (winsorized %-surprise fwd_20d IC +0.0290,
          NW t=2.96, ~13x the shuffle floor, placebo-clean). The short leg is unmonetizable
          under our shorting mandate, so usability hinges on the LONG leg + orthogonality.
EVIDENCE: FAITHFUL event-driven long-only (enter +1d, hold to horizon, overlapping holdings
          aggregated into a daily-rebalanced EW portfolio, cost on actual |Δw| turnover).
          CORRECTED per PR #203 round-2 review: (1) excess/significance restricted to ACTIVE
          days (idle=cash@0 reported separately) — idle days were being scored as a portfolio
          shorting a rising market; (2) event selection now uses an EXPANDING strictly-prior-
          history %-surprise threshold (no full-sample look-ahead). Result:
          top-quintile @20d = NET-NEGATIVE −865 bps/yr ACTIVE (−1111 total, daily t −0.34) —
          the old −705 figure is corrected (NOT preserved) and is actually WORSE on active
          days because active-day GROSS excess is itself −2058 bps; top-quintile @60d =
          +259 bps/yr net active (+200 total) but daily t ≈ 0.92 (BELOW 1, insignificant; was
          +398/yr t 1.27 under the buggy framing). Top-decile mirrors it (−93/yr @20d,
          +748/yr @60d t 1.18). 63-phase sweep of the OLD design: @20d net −30..+211 bps
          (std 46). Long-only IC +0.026 @20d / +0.030 @60d. Orthogonality: rank-corr vs
          mom_12_1/mom_6_1/ma200_dist = +0.15/+0.14/+0.18 (low-to-moderate diversifier).
          `[VERIFIED — scripts/pead_test.py + scripts/pead_longonly_orthogonality.py
          --as-of 2026-06-26, READ-ONLY bars + fmp_harvest earnings, this session]`
CAVEATS:  NON-PIT exploratory; long leg does NOT monetize at 20d after faithful costs
          (net-negative on active days); 60d positive but insignificant (t < 1 at quintile);
          modest ~2.6-3% IC; scaling load-bearing (raw null); NOT regime-stable;
          phase-sensitive / small-N economics.
PENDING:  correlation vs LIVE model scores — blocked on faithful decision-ledger data
          (ledger too thin/impaired, ≈0.45 overlap-ratio scorer-mixture per the 2026-06-27
          trend-signal baseline audit). Flagged as follow-up, NOT fabricated.
REPRO:    both scripts take --as-of/--bars-cache/--earnings/--out, are pinned (no
          datetime.now), hash inputs, and write manifest_pead_test.json /
          manifest_pead_longonly.json. Winsorized %-surprise denominator (|est| floored at
          p05=0.110) so tiny estimates can't dominate top-positive selection. Round-2 fixes:
          active-day economics + total-strategy split (idle=cash@0); expanding look-ahead-free
          selection threshold; finite-guarded IC/HAC (fail-loud, no spurious NumPy warnings) —
          tests/test_research_pead_finite_guards.py.
PROPOSE:  no clean case for a 20d tilt (loses money after costs, net-negative on active
          days); at most a low-turnover ~60d LONG-side overweight (+259 bps/yr active, daily
          t≈0.92 — below 1, directional + insignificant), which would need a real PIT
          estimate-vintage source + a long-only placebo before any live use. Orthogonal
          complement candidate at best, NOT a core signal.
SAFETY:   READ-ONLY on data/live tree; no canonical writes; no git in the live tree; no
          order placed; no self-merge / no self-approve.
NEXT:     operator + Codex discussion: given the faithful 20d-net-negative / 60d-insignificant
          economics and NON-PIT status, is there any version worth a placebo-grade follow-up,
          or is this lead closed?
