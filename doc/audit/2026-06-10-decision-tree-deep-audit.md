# RenQuant decision-tree deep audit — synthesis (2026-06-10)

**Trigger:** operator: "I feel there are at least 20 bugs in the decision tree — deep self audit and review."
**Method:** three parallel read-only audits, one per decision-tree region, every finding backed by file:line + a reproduction (live calibrator artifacts, `runs.alpaca.db`, or live logs). No code changed by the audit; fixes are separate.
**Result: 35 findings — 4 BLOCKER, 11 HIGH, 12 MED, 8 LOW.** The operator's estimate was an undercount.

| Region | Findings | Blocker | High | Audit PR |
|---|---|---|---|---|
| Scoring + calibrator | 10 | 2 | 3 | renquant-pipeline #85 |
| QP + emission + stops + preflight + state | 14 | 1 | 5 | renquant-pipeline #86 |
| Admission + selection + sizing | 11 | 1 | 3 | renquant-pipeline #87 |

## The 4 BLOCKERS (fix first)

**BL-1 · Inference cross-section contamination → all PatchTST scores negative** (scoring F2). CSRankNorm at inference ranks features over only the live candidate subset (3 tickers in the DB) while training ranks over 142–291. Rank-pct on 3 names is wildly out-of-distribution → uniformly negative scores (min −0.299, max −0.042). This is the *sibling* of the PR #82 frozen-window fix on the cross-section axis; XGB guards it via `_stable_feature_context_tickers`, PatchTST does not. **This is the root of "every score is negative".**

**BL-2 · Calibrator maps bearish scores to positive μ** (scoring F1). Because scores are all negative (BL-1), the calibrator's neutral (P=0.5) crossing sits at raw ≈ −0.13, not 0. 935 live rows have `raw_panel<0 AND mu>0`. Consequence: today's signal-direction gate (which assumes 0 = neutral) is built on a shifted distribution, and hold-side rotation/QP still consume wrong-sign μ. No stored "neutral raw" anchor.

**BL-3 · One holding with a missing config field disables ALL risk stops that bar** (QP B-1). `apply_stop_loss_anchor_policy` raises `ValueError` inside an un-guarded list comprehension (`pp_inference.py:293`); a single holding whose entry-regime config lacks `stop_loss_pct` aborts sell evaluation for *every* holding → exit path fails closed, no stops fire. Real-money risk control can silently go dark.

**BL-4 · Per-regime knob silently falls through to the permissive global** (admission B1). `_qp_admission_gate_value` (`portfolio_qp/tasks.py:2487`) returns the global value when the `_by_regime` map lacks the live regime. Prod sets `min_expected_return_by_regime: {BULL_CALM: 0.01}` with **no global**, so the ER floor + its coupled horizon check are **silently OFF in BULL_VOLATILE / CHOPPY / BEAR**. Directly violates the PRIME DIRECTIVE (every knob resolves per-regime).

## The HIGH findings (system-level, fix next)

- **H · Single-day-loss stop is culling WINNERS** (QP H-2): `sdl_skip_if_unrealized_above=0` (off) → a noise gap-down stops out big winners. Evidence: NVTS exited via `single_day_loss` at **+113%** after 8d; `single_day_loss` exits average **+9%** pnl. The "stop" systematically sells gains.
- **H · Stops are regime-unconditional** (QP H-1): SDL/trailing/σ-stops read the *current* regime; a BULL_CALM 60d thesis re-labeled BULL_VOLATILE inherits a tight 6% single-day stop — the whipsaw pattern, on the sell side.
- **H · Oversize fallback busts the cap on expensive stocks** (sizing B2): `compute_position_size` falls back to 25%/1-share with no max_pct re-check. **LLY's 8.2% Kelly target became a 22% position on 2026-06-10 purely because LLY is $1138.** The greedy path has no post-fill cap assertion (BEAR path does).
- **H · Signal-direction gate has single-path coverage** (admission B3/B4): today's "no long on bearish raw signal" gate lives ONLY in `SizeAndEmitTask`. QP, rotation buy-leg, and top-up bypass it and rely on `min_panel_score` (null in prod) → negative-panel longs still pass there.
- **H · Calibrator er_y entirely positive in CHOPPY** (scoring F3): structurally long-only μ surface; even the most bearish score maps to positive expected return. No fit/load guard requires er_y to cross zero.
- **H · Exit-suppression class still live** (QP H-3/H-4/H-5): proportional-trade 1/N shrink collides with the min_dw band; no-trade band suppresses small QP de-risking trims (the ORCL "+1.9% couldn't exit"); intra-bar buys can't use cash freed by later sells.

## Cross-cutting themes (the bugs share roots)

1. **Calibration/inference distribution mismatch** (BL-1, BL-2, F3): PatchTST scores are systematically negative because of a cross-section normalization bug, and the calibrator then launders that into positive μ. *Today's fixes (#81 gate, #82 time-axis) are correct but partial — BL-1/BL-2 are the deeper layer.*
2. **Regime-unconditional logic** (BL-4, H-1, and the stop family): the PRIME DIRECTIVE ("every knob per-regime") is violated in both the admission ER floor and the stop anchors — knobs silently use a global or the wrong regime.
3. **Fail-closed gaps in risk paths** (BL-3, M-4): an exception or a wall-clock date in an un-guarded risk path takes down the whole bar's risk evaluation.
4. **Single-point gate coverage** (B3/B4): safety gates added at one task don't cover the QP / rotation / top-up siblings.

## Recommended fix order (operator to approve)

1. **BL-3** (stops can go fully dark) — smallest, highest real-money risk; guard the list comprehension.
2. **BL-1 + BL-2** (the negative-score root + calibrator sign) — fix the PatchTST cross-section context (mirror XGB's stable-context guard) and anchor the calibrator neutral point; this is what makes PatchTST tradeable at all.
3. **BL-4 + B3/B4** (per-regime fallthrough + gate coverage) — close the silent-OFF floors and extend the signal gate to QP/rotation/top-up.
4. **H-2 + H-1** (stops culling winners, regime-unconditional) — the sell-side of the operator's original "傻单" complaint.
5. The MED/LOW tail per the three PRs.

**Live remains sell-only / unchanged throughout.** No fix ships without its own PR + review; this synthesis is the map, the three PRs (#85/#86/#87) are the detailed findings with reproductions.

Agent-Origin: Claude
