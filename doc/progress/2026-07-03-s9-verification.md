# S9 verification — independent adversarial recomputation: verdict UPHELD

STATUS:   COMPLETE — **UPHELD**. The S9 Track A NULL (PR #262) survives an
          adversarial independent re-computation whose explicit mandate was to
          overturn it. Every load-bearing number reproduces exactly
          (deterministic) or within Monte-Carlo noise (bootstrap CIs); no
          undisclosed spec deviation found; three adversarial fragility
          variants (floor split, strict-median C3, literal standardized-units
          label) all leave the verdict NULL. Read-only on all inputs; no git
          anywhere near the live tree.
WHAT:     `scripts/s9_independent_verification.py` — independent code paths, not
          a rerun: own duplicate-validated `m:1` join (0 dup keys, 0 NaN labels
          in the whole 715,629-row panel, row count stable — no silent y-label
          inflation/deflation); own IRLS logistic (reproduces sklearn's τ=0.5107
          and all C1 gate decisions); C3 recomputed directly from within-date
          score medians (drop = **891/2,078 = 42.88%, exact match** to the
          binding gate-(e) kill); own bootstrap (seed 71, 4,000 resamples): C3
          book lift **+1158.3 bps/yr point-exact**, CI [+598.0, +1698.9] vs
          their [+631.7, +1713.0] — MC noise, gate (a) ✓ both. New checks their
          script never did: (i) label semantics proven — raw label minus own
          60-trading-session forward return is a per-date constant, residual
          spread 0.0 across 72 probes (60-session horizon + return units +
          common benchmark confirmed); (ii) embargo leak test on the panel grid
          — last train label window ends 2025-07-18, one session before test
          start 2025-07-21, no overlap; (iii) independent transport hash of the
          substrate parquet matches the sidecar. C2/(d): test window verified to
          hold exactly 1 BEAR date; §4's (d) is mechanically evaluable and its
          FAIL is spec-faithful (no §4 provision to extend/re-weight a window).
          Evidence: `doc/research/evidence/2026-07-03-s9-verification/verification.json`;
          memo: `doc/research/2026-07-03-s9-verification.md`.
WHY/DIR:  Full-decision-delegation standard requires adversarial verification
          before the S9 NULL's consequence (Track B is the only remaining
          directional path) is treated as settled. It now is. Caveats recorded,
          none verdict-relevant: C2's gate-(c) CI is conditional-on-active
          (~34% of resamples empty and dropped — overstates C2's (c) ✓, but C2
          fails (d)/(e) decisively); embargo has exactly 1 session of slack
          (don't reuse blindly with a longer horizon); `round` vs floor on the
          60% split was an undisclosed micro-choice (verified immaterial).
          Kill-distance on the only near-miss: C3 passing (e) would need a
          66.5% conditioned hit-rate vs the actual 57.0% — not a
          tolerance-level miss; no recomputation path flips it.
