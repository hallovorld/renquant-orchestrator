# orch#799 blend-substitution WF-promote gate — FROZEN preregistration

STATUS: frozen preregistration (design record; must be codex-approved BEFORE any
umbrella `weekly_wf_promote.sh` / `run_wf_gate.py` gate change implements it)

WHAT: commits `doc/design/2026-08-12-orch799-blend-substitution-prereg.md`
verbatim — the binding spec for orch#799 option B (blend-substitution). The
weekly WF-promote gate refuses every cycle because the served prod primary is a
`kind=blend` z-blend while the retrain yields a solo `xgb` candidate leg, so
`_find_gbdt_config` finds no kind-matched xgb prod reference and exits 2
(3 jobs stuck; the served model cannot refresh; 25/145 watchlist names remain
un-coverable). The prereg's rule: promote the fresh xgb leg iff it improves the
SERVED BLEND, measured directly — `B_cand = z-blend(xgb_leg_new,
momentum_residual, W, N)` vs `B_ref = z-blend(xgb_leg_cur, momentum_residual, W,
N)`, paired per-fold on the same walk-forward manifest, momentum leg + weights W
+ z-norm N held FIXED, all §4 leakage guards fail-closed. This PR changes NO
code.

WHY/DIR: option A (bare-leg, #589 — compare the candidate xgb leg vs the current
xgb leg in isolation) was codex-rejected: a leg's standalone WF metric need not
describe its contribution inside the served blend, so promoting on a
standalone-leg metric is a scientifically invalid criterion for a served blend.
This prereg establishes the valid estimand ("does the served blend improve")
and freezes every threshold to the existing gate's bar (no new threshold
invented) so the implementation cannot drift the criterion after the fact.

EVIDENCE: doc-only (prereg + this progress doc); no runtime claim. Byte-identical
copy of the operator-lead's authored source confirmed by matching sha256 before
commit. The separate READ-ONLY feasibility investigation that accompanies this
prereg (prereg §6 implementation-feasibility gate) is reported to the lead
directly, not asserted here.

NEXT: the umbrella gate change is GATED ON this PR's codex approval and MUST NOT
merge before it. The prereg §6 feasibility gate must be settled first: if the
existing WF gate cannot score a blend over per-fold blend artifacts without new
blend-eval machinery, the implementation STOPS and the gap is reported rather
than falling back to option A or any banned reference source (umbrella working
copy / sibling checkout). The weekly not-acting alarm stays until a valid gate
DECIDES — that alarm is preferable to a scientifically invalid promote.
