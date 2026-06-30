# renquant105 PEAD %-surprise — exploratory probe (event-driven long-only economics + orthogonality)

STATUS:   EXPLORATORY, open for discussion (NOT a promote / live-tilt request). After the
          faithful round-2 corrections this is a WEAK orthogonal candidate that is MOSTLY
          NON-MONETIZED after costs — NOT "a real lead."
WHAT:     takes one probe out of the trend/factor signal hunt — earnings %-surprise (PEAD) —
          past the cheap screen into a FAITHFUL follow-up: event-driven long-only economics +
          orthogonality. Lean candidate-style; no CPCV/FWER/DSR framework.
PIT:      NON-POINT-IN-TIME (downgraded per PR #203 review). The earnings parquet is a
          SINGLE CURRENT one-shot harvest; epsEstimated is today's value, NOT a captured
          pre-announcement consensus; lastUpdated is a generic floor pre-2024-09. The +1d
          convention controls ENTRY TIMING only. ALL results are exploratory, not PIT-clean.
WHY/DIR:  the cheap screen flagged %-surprise (winsorized %-surprise fwd_20d IC +0.0290,
          NW t=2.96, ~13x the WITHIN-DATE shuffle floor, placebo-clean — but the WF gate's
          separate ~+0.04 shuffled-label leakage floor on overlapping 60d labels means trust
          the placebo-clean DIFFERENCES, not the absolute IC). The short leg is unmonetizable
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

§4(b) EVIDENCE BLOCK (required before any data conclusion is accepted):
  artifact:      transient `--out` dir (default /tmp/pead/) from the two pinned scripts:
                 manifest_pead_test.json, manifest_pead_longonly.json,
                 pead_longonly_ic.csv, pead_orthogonality.csv. NOT committed (research-only,
                 /tmp). Reproduced by `scripts/pead_test.py --as-of 2026-06-26` then
                 `scripts/pead_longonly_orthogonality.py --as-of 2026-06-26`. Scripts +
                 finite-guard tests ARE committed (scripts/pead_test.py,
                 scripts/pead_longonly_orthogonality.py,
                 tests/test_research_pead_finite_guards.py).
  prod or exp:   EXP — research-only, NON-PIT, transient /tmp outputs. NOT production. No
                 canonical write, no live tilt, no PatchTST replacement.
  existing data: bars cache `/tmp/sighunt/bars.parquet`
                 sha256 db40d2b79c09795b37ff03f878bfb5019c71fb0e5fb877e050fe7a3eb7b31521
                 (134 single names, 2018-05-30..2026-06-26); earnings
                 `data/fmp_harvest/earnings_291.parquet`
                 sha256 dba04ac1c372c2f8cfb56a1683a4b1e95924c2fe1098f885c7be1fbd2b5f3948
                 (SINGLE current one-shot FMP harvest, not a PIT consensus snapshot). Both
                 hashes are recorded in the script manifests. Prior factor scan (cheap screen,
                 the 2026-06-27 trend-signal baseline audit) had this as the only probe to
                 clear the IC floor placebo-clean; the live-model-score cross-section is NOT
                 available (decision-ledger too thin/impaired, ≈0.45 overlap-ratio).
  best-known?:   YES for THIS non-PIT exploratory question (winsorized %-surprise @20d IC
                 +0.0290 / NW t 2.96 is the best of the surprise variants vs raw_surprise
                 null +0.0050 / SUE +0.0216), but the WF-gate IC carries a ~+0.04
                 shuffled-label leakage floor on the 60d label, so trust the placebo-clean
                 DIFFERENCES (scaled vs raw, %-surprise vs SUE) not the absolute IC. MISSING
                 before any PIT use: a real captured pre-announcement estimate-vintage source
                 (the current harvest is not PIT); a long-only 60d placebo; a wider/longer
                 universe; the live-model-score orthogonality.
  scope:         current-watchlist (134 names) / current-harvest RETROSPECTIVE only. NON-PIT
                 exploratory. NO live use, NO PIT claim, NO PatchTST replacement, NO 20d tilt
                 (20d is net-negative after faithful costs). At most a directional,
                 insignificant (daily t≈0.92) 60d long-side read, gated behind the MISSING
                 items above.

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
