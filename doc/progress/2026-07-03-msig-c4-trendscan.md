# 2026-07-03 — M-SIG C4 (trend-scan label) measured against the frozen spec — INCONCLUSIVE

Durable record for the C4 research PR (single source; details live in the memo).

## What happened

- C4 (#243 r4 §1.4) was measured for the first time under its frozen rule, the same day
  its S3 precondition landed (renquant-backtesting#61: v2 still enforcing, v3
  genuine-IC difference shadow-only — C4's pre-registered rule uses the difference
  semantics).
- Freeze-first (M8/C2 pattern): `c4_frozen_addendum.json` committed before the harness
  ran — gating cell BULL_CALM, seed rule, embargo-repaired 8-cut WF (test 2018-2025),
  2×-horizon score-placebo semantics mirrored from the production runner, PC acceptance
  criteria, fail-closed sim-secondary consequence.
- **Verdict: INCONCLUSIVE on all 3 seeds** — BULL_CALM Δgenuine point estimates
  +0.0378/+0.0258/+0.0353 (all above the 0.02 margin) but 98.33% one-sided lower bounds
  −0.018/−0.017/−0.010. Robust across the frozen margin bracket {0.015,0.02,0.025} and
  the pooled sensitivity reading. Neither GO nor KILL; C4 casts no stack vote.
- Positive controls all PASS (planted 2×-bar effect → GO ×3; permuted candidate → never
  GO; true-zero paired null → mechanical KILL ×3, proving the KILL branch fires).
- Window-artifact check: the edge concentrates PRE-2021 (+0.074) and is ≈flat 2021+
  (+0.006) — NOT the mom_12_1 2021-26 artifact pattern, but the deployment-relevant era
  shows no advantage. BULL_VOLATILE reads a diagnostic mechanical KILL ×3 (trend-scan
  hurts there); pooled ≈ 0.
- Power is the binding constraint (structural): MDE at the Bonferroni bar ≈ +0.07 vs
  observed +0.033; accrual cannot close this by 2027-Q3 → C4 tracks
  INCONCLUSIVE-at-deadline absent a re-frozen protocol (reopening conditions §13 of the
  memo).
- Run-time discovery, disclosed: three UNMERGED follow-ups on
  `feat/drift-free-label-trial` (embargo-hypothesis refuted; naive P&L reject; hardened
  P&L walk-back to inconclusive) — retrospective context the spec did not cite; no
  frozen parameter affected.

## Stack state after this run (V4 composition, #268)

{C2,C3,C4} = {non-voting/open (#275), unadjudicated/open (#268), INCONCLUSIVE (this)}.
N_resolved = 0, GO count = 0. No early KILL (spec §3), but G106 currently tracks the
kill branch (benchmark-sleeve default + PIT accrual + 107 execution-only) unless a
reopening lands; the V4 composite ≈0.45–0.50 is stale-high (memo §12 estimates
P(≥2 GO) ≈ 0.01–0.03 under current protocols).

## Files

- `scripts/msig_c4_trendscan.py` (harness, one-command reproduce)
- `tests/test_msig_c4_trendscan.py` (S-REL R2 committed fixture, 9 tests)
- `doc/research/2026-07-03-msig-c4-trendscan.md` (verdict memo)
- `doc/research/evidence/2026-07-03-c4/` (frozen addendum + results + per-date series)

Read-only on all production data; scratchpad worktree only; no git near any primary
checkout; no config/order/production change.
