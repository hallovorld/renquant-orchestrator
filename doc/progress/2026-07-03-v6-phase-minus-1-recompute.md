# Progress — S-REL V6 step 2: Phase −1 adversarial recompute (UPHELD)

DATE: 2026-07-03. Executes the verification step of S-REL audit item V6
(`doc/design/2026-07-03-s-rel-experiment-reliability.md` §V6; step 1 was the #267
durability recommit). Brief: try to OVERTURN the standing Phase −1 soft NO-GO on intraday
open→close directional alpha with an independent implementation on a different substrate.

## Outcome

**UPHELD.** σ_oc reproduces to 0.01 bps (std median 152.51 vs 152.5; MAD 114.00 vs 114.0;
IQR 115.1 vs 115.1) from fresh code on the durable local 1d bars (not the Alpaca API);
the net-edge algebra and 367/220 bps breakevens reproduce exactly; window/universe
sensitivity holds everywhere (most favorable cut still net-negative at both anchors);
positive control (+30 bps planted on the real cross-section) detected at t = 8.7 with a
clean null arm. Flip boundary made precise: net > 0 ⟺ IC × σ_oc × factor > cost; at the
11 bps floor IC\* = 0.072 (frozen factor-1.0 rule) / 0.041 (top-decile ideal) / 0.031
(idealized top-3 ceiling). The one refinement: at maximal concentration the boundary is
NOT "an order of magnitude" away (the S-REL queue's phrasing) — but no evidenced intraday
IC exists at any level (S9 NULL, minute-feature NULL, live IC ≈ 0), so no plausible IC
flips it. Reopening condition sharpened in the memo §6.

## Deliverables

- `scripts/v6_phase_minus_1_recompute.py` — independent harness (stdlib pure helpers;
  lazy pandas/numpy only in loader/MC).
- `doc/research/2026-07-03-v6-phase-minus-1-recompute.md` — verification memo (R3
  evidence-boundary block + R4 reopening condition).
- `doc/research/evidence/2026-07-03-v6-phase-minus-1-recompute/verification.json` — input
  hashes (142 parquet files + configs) + code sha + all results.
- `tests/test_v6_phase_minus_1_recompute.py` — 22 network/data-free tests incl. the R2
  positive-control fixture and the mechanism-off arm.
- `doc/research/VERDICTS.md` — Phase −1 row: PROVISIONAL → **UPHELD**; reopening condition
  updated to the quantitative boundary.

Guardrails: read-only umbrella access (bars + configs only); no git in any primary
checkout; work done in a fresh worktree on `research/v6-phase-minus-1-recompute`.
