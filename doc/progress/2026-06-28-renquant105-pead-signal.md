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
          aggregated into a daily-rebalanced EW portfolio, cost on actual |Δw| turnover):
          top-quintile @20d = NET-NEGATIVE −705 bps/yr (daily t −0.22) — the prior +42.8 bps
          was a single-phase/fixed-cost artifact; top-quintile @60d = +398 bps/yr net but
          daily t ≈ 1.27 (insignificant). Top-decile mirrors it (−663/yr @20d, +843/yr @60d
          t 1.33). 63-phase sweep of the OLD design: @20d net −30..+211 bps (std 46) — the
          single reported phase was one wide-distribution draw. Long-only IC +0.026 @20d /
          +0.030 @60d. Orthogonality: rank-corr vs mom_12_1/mom_6_1/ma200_dist =
          +0.15/+0.14/+0.18 (low-to-moderate diversifier as a rank signal).
          `[VERIFIED — scripts/pead_test.py + scripts/pead_longonly_orthogonality.py
          --as-of 2026-06-26, READ-ONLY bars + fmp_harvest earnings, this session]`
CAVEATS:  NON-PIT exploratory; long leg does NOT monetize at 20d after faithful costs; 60d
          positive but insignificant; modest ~2.6-3% IC; scaling load-bearing (raw null);
          NOT regime-stable; phase-sensitive / small-N economics.
PENDING:  correlation vs LIVE model scores — blocked on faithful decision-ledger data
          (ledger too thin/impaired, ≈0.45 overlap-ratio scorer-mixture per the 2026-06-27
          trend-signal baseline audit). Flagged as follow-up, NOT fabricated.
REPRO:    both scripts take --as-of/--bars-cache/--earnings/--out, are pinned (no
          datetime.now), hash inputs, and write manifest_pead_test.json /
          manifest_pead_longonly.json. Winsorized %-surprise denominator (|est| floored at
          p05=0.110) so tiny estimates can't dominate top-positive selection.
PROPOSE:  no clean case for a 20d tilt (loses money after costs); at most a low-turnover
          ~60d LONG-side overweight (+398 bps/yr, daily t≈1.3 — directional, insignificant),
          which would need a real PIT estimate-vintage source + a long-only placebo before
          any live use. Orthogonal complement candidate at best, NOT a core signal.
SAFETY:   READ-ONLY on data/live tree; no canonical writes; no git in the live tree; no
          order placed; no self-merge / no self-approve.
NEXT:     operator + Codex discussion: given the faithful 20d-net-negative / 60d-insignificant
          economics and NON-PIT status, is there any version worth a placebo-grade follow-up,
          or is this lead closed?
