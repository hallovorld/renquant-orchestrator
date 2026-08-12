# orch#799 blend-substitution WF-promote gate — FROZEN preregistration

STATUS: frozen preregistration (design record; must be codex-approved BEFORE any
umbrella `weekly_wf_promote.sh` / `run_wf_gate.py` gate change implements it)

WHAT: commits `doc/design/2026-08-12-orch799-blend-substitution-prereg.md`
verbatim — the binding spec for orch#799 option B (blend-substitution). The
weekly WF-promote gate refuses every cycle because the served prod primary is a
`kind=blend` z-blend while the retrain yields a solo `xgb` candidate leg, so
`_find_gbdt_config` finds no kind-matched xgb prod reference and the chain
refuses. The prereg's rule: promote the fresh xgb leg iff it improves the SERVED
BLEND, measured directly — `B_cand = Σ z(xgb_leg_new), z(momentum_residual)` vs
`B_ref = Σ z(xgb_leg_cur), z(momentum_residual)`, paired per-fold on the same
walk-forward manifest, with the momentum leg and the combine rule held FIXED and
all §4 leakage guards fail-closed. **There is no weight vector and no stored
z-normalization state** — an earlier draft froze `W` and `N`; both are fictions
and are removed. This PR changes NO code.

WHY/DIR: option A (bare-leg, #589 — compare the candidate xgb leg vs the current
xgb leg in isolation) was codex-rejected: a leg's standalone WF metric need not
describe its contribution inside the served blend, so promoting on a
standalone-leg metric is a scientifically invalid criterion for a served blend.
This prereg establishes the valid estimand ("does the served blend improve")
and freezes every threshold to the existing gate's bar (no new threshold
invented) so the implementation cannot drift the criterion after the fact.

EVIDENCE:
  artifact:      `doc/design/2026-08-12-orch799-blend-substitution-prereg.md`
                 (the frozen spec) + this record. **No code.**
  prod or exp:   neither — a preregistration for a future production-gate rule.
                 It changes nothing today and authorizes no promotion; the gate
                 change it governs is separately operator-gated.
  existing data: yes — the frozen values were READ from the pinned system, not
                 chosen here: the combine rule from
                 `renquant_pipeline/kernel/panel_pipeline/blend_scorer.py`; the
                 served blend's shape from `strategy_config.json` at
                 strategy-104 `e00d935`; and the gate's own bar from
                 `scripts/run_wf_gate.py` — placebo mode **`absolute`**
                 (`DEFAULT_PLACEBO_MODE`), whose authoritative bar is the
                 time-shift ceiling `max(0.005, 0.5×|aligned_real_ic|)` ALONE
                 `[VERIFIED — `run_wf_gate.py:276,500-520`, read 2026-08-12]`.
                 An earlier draft of this record also listed `margin +0.01` and
                 the real-IC floor as part of the bar; those feed the opt-in
                 `difference` verdict only, so listing them froze a hybrid rule
                 the gate never applies. Corrected in the design doc's §3 table.
                 No run performed, no data generated.
  best-known?:   yes among the four options, CONDITIONAL on §4.6. Option A
                 (bare-leg) is invalid for a served blend; this measures the
                 object that is actually served. The one quantity not readable
                 from the system — the degenerate-leg tolerance — is set to
                 **zero**, which is the only value defensible without a power
                 calibration this document does not have.
  scope:         "this is the orch#799 blend-substitution promote rule (frozen
                 prereg, not implemented), vs existing best = the gate's current
                 structural refusal, which returns no verdict at all. The
                 estimand is 'does replacing the served blend's xgb leg improve
                 the frozen WF metric', paired per-fold on the existing WF
                 manifest, restricted to folds where BOTH legs scored
                 non-degenerately — and a single degenerate fold fails the run
                 rather than shrinking the sample. It makes no alpha claim."

REMOVED FROM AN EARLIER DRAFT, deliberately: this record previously asserted
`exits 2`, `3 jobs stuck`, and `25/145 watchlist names` while its EVIDENCE line
said "no runtime claim". Those are operational measurements and this document
has no reproducible source for them, so they are gone rather than tagged. If
they are load-bearing for prioritization they belong in the document that
measures them, cited from there.

NEXT: the umbrella gate change is GATED ON this PR's codex approval and MUST NOT
merge before it. The prereg §6 feasibility gate must be settled first: if the
existing WF gate cannot score a blend over per-fold blend artifacts without new
blend-eval machinery, the implementation STOPS and the gap is reported rather
than falling back to option A or any banned reference source (umbrella working
copy / sibling checkout). The weekly not-acting alarm stays until a valid gate
DECIDES — that alarm is preferable to a scientifically invalid promote.
