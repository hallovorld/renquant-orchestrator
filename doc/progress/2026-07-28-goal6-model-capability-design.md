# Progress: GOAL-6 design — model capability (resolution before architecture)

STATUS:   design proposed for review; no experiment run. Operator decision requested on
          the staging and on opening the MID workstream.

WHAT:     Adds `doc/research/2026-07-28-goal6-model-capability-design.md` (thesis, a
          per-lever value table, a 4-stage gated ladder, 5 ACs, and a repo-boundary
          table) plus the MID workstream `doc/memory/mid-term/model-capability.md`.

WHY/DIR:  Operator directive after tonight's PatchTST read: build experiments that
          actually yield a more capable model. The diagnosis is that our verdicts are
          unresolvable rather than negative, and two of the three causes cost nothing
          to fix. Ladder: Stage 0 re-baseline the ruler (free) → Stage 1 build the
          830-name PIT panel with a stamped freshness contract → Stage 2 retrain the
          CERTIFIED top-decile recipe on breadth through the same frozen chain →
          Stage 3 capacity/ensembling only once 0-2 make results interpretable.

EVIDENCE: `[VERIFIED — direct parquet/artifact reads, 2026-07-28]` training panel
          **142 tickers** 2016-01-04 → 2026-04-28 (353,548 rows); fund panel 292;
          SEC fundamentals coverage **830** — we train on 17% of the cross-section
          already owned and rebuilt as-filed (base-data#52). Fresh PatchTST val read
          (33,370 rows, 235 dates): IC +0.0430, naive t +5.39, **block-adjusted
          t +0.70**, within-date placebo −0.0008. Prior measured facts reused: tail
          spread t=2.92 vs IC t=1.15 (2026-07-24 capacity memo); intraday open→close
          net edge −6.4bp at IC 0.03 with σ_oc ≈ 152bp (Phase −1), which is why hourly
          data is explicitly out of scope. Arithmetic in the lever table (1/√N
          sampling-noise decomposition; 14 → 83 names in the top decile) is derived
          from those measurements and is labelled as projection, not measurement. No
          new IC/Sharpe claim is made here, so the §4(b) sanity triad applies to the
          Stage-0 results doc, not to this design.

NEXT:     Operator confirms staging → Stage 0 runs under its own frozen prereg
          (zero new data, zero training). Stage 1 is the first stage that writes an
          artifact, and it lands in renquant-base-data — not here.
