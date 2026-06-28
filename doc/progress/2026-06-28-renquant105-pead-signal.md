# renquant105 PEAD %-surprise — candidate signal (long-side economics + orthogonality)

STATUS:   CANDIDATE signal, open for discussion (NOT a promote / live-tilt request).
WHAT:     develops the one real lead from the trend/factor signal hunt — earnings
          %-surprise (PEAD) — past the cheap screen into the proportionate follow-up it
          earned: long-side-only economics + orthogonality. Lean candidate-style; no
          CPCV/FWER/DSR framework.
WHY/DIR:  the cheap screen passed (%-surprise fwd_20d IC +0.0313, NW t=3.12, 14.5× the
          shuffle floor, placebo-clean, low-turnover). The short leg is unmonetizable
          under our shorting mandate, so usability hinges on the LONG leg + on whether
          it is orthogonal to what we already trade.
EVIDENCE: LONG-only top-quintile excess vs equal-weight universe, net of 11 bps one-way:
          +42.8 bps @20d (per-rebalance t≈1.30, 28 quarters, median +20.7), +298.7 bps
          @60d (t≈2.36, std ≈683 bps). Top-DECILE @20d is net-NEGATIVE (−9.1 bps) — use
          the quintile. Long-only IC +0.030 @20d / +0.038 @60d. Orthogonality: rank-corr
          vs mom_12_1/mom_6_1/ma200_dist = +0.15/+0.14/+0.18 (low-to-moderate → a genuine
          diversifier). `[VERIFIED — scripts/pead_test.py + scripts/pead_longonly_orthogonality.py,
          READ-ONLY bars + fmp_harvest earnings, this session]`
CAVEATS:  modest ~2-3% IC; scaling load-bearing (raw null, %/SUE only); short-skewed;
          NOT regime-stable (negative IC 2022 & 2024); PIT-clean epsEstimated but
          lastUpdated meaningful only 2024-09+ so pre-2024 PIT rests on the +1d timing
          convention; long-only economics on only 28 quarterly rebalances (directional).
PENDING:  correlation vs LIVE model scores — blocked on faithful decision-ledger data
          (ledger too thin/impaired, ≈0.45 overlap-ratio scorer-mixture per the
          2026-06-27 trend-signal baseline audit). Flagged as follow-up, NOT fabricated.
PROPOSE:  a low-turnover 20d %-surprise LONG-side tilt / overweight on the 104 book — an
          orthogonal complement, size-capped + regime-aware, NOT a core signal.
SAFETY:   READ-ONLY on data/live tree; no canonical writes; no git in the live tree; no
          order placed; no self-merge / no self-approve.
NEXT:     operator + Codex discussion on the 4 PR questions (tilt justification, regime
          handling, integration without disturbing the book, proportionate validation).
