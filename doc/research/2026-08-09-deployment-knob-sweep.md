# The deployment knobs, swept — in this frame the objective already wants full deployment; only the turnover cap binds

REVISED (review r2 — the r1 headline "λ is dead; the levers are
min_invested × turnover cap" OVERCLAIMED and is withdrawn; the r1 text
follows the corrected reading below as an audit trail).

## What the sweep can and cannot say `[VERIFIED — committed JSON, 4 usable runs 2026-05-18..21; every later run unusable per orch#931]`

Scenarios (all on real run inputs, simplified constraints — per-name cap
only, the committed script's scope note):

| scenario | deployed across λ ∈ {0,.01,.02,.05,.1} |
|---|---|
| A: production (min_inv=0, tcap 0.15) | 0.706 flat |
| B: min_inv ON × tcap {0.15,0.2,0.3,0.5} | 0.706 / 0.755 / 0.856 / 1.000 — identical at every λ |
| C: min_inv ON, loose tcap | 1.000 flat |
| D (r2, constructed λ-sensitivity: min_inv=0.5 floor, loose tcap) | **1.000 flat INCLUDING λ=0** |

Scenario D dissolves the r1 story: with a loose turnover cap the optimizer
fully deploys at λ=0 with no min_invested push — **the objective on these
inputs already wants full deployment; the only binding constraint among
those modeled is the turnover cap**, which paces the path monotonically
(B row). λ shows no marginal effect anywhere, but that is UNRESOLVED as a
general claim: no tested configuration isolates a case where λ must act
(where the unconstrained optimum under-deploys). min_invested likewise
shows no effect beyond what the cap already permits.

## The redirection this forces

If the simplified QP wants full deployment even with every knob at zero,
then WITHIN THIS FRAME the knobs cannot explain the live book's
non-deployment — the non-deployment is UNEXPLAINED by the modeled
constraints. That directs (but does not prove) the next investigation at
what this replica does NOT model: the upstream floors and the full QP's
additional terms — consistent with the funnel Pareto (orch#943 merged):
rank-score floor veto 2,390 events, conviction mu-floor 277, and the
full-QP not_selected stage. **The next evidence target is therefore the upstream
admission floors and the full in-pipeline QP — a hypothesis this frame
motivates but cannot itself establish.** The 2026-05-23 re-enable condition (WF alpha evidence)
remains the governing contract for ANY relaxation.

## Standing limits

Four May sessions; simplified constraints; target-weight w_cur
approximation; no P&L claim; the in-pipeline 10-session shadow sweep
remains the enable-gating AC (script scope note, verbatim).

---

### r1 text (superseded, kept for the audit trail)

# The deployment knobs, swept — λ is dead; the levers are min_invested × turnover cap

The measured answer to "which reviewed change lets the QP deploy capital",
run 2026-08-09 on real run inputs. Derivation = the committed
`scripts/poc_lambda_sweep.py` machinery with three run-scoped repairs
(zero-width guard; usable-candidate run selection — the orch#931 sigma
drift makes every post-05-21 live run UNUSABLE for this sweep; threshold
60), committed as
`doc/research/data/2026-08-09-deployment-knob-sweep-derivation.py` with raw
output `doc/research/data/2026-08-09-deployment-knob-sweep.json`.

## Result `[VERIFIED — committed JSON; 4 usable runs, 2026-05-18..21, the last full-featured era]`

| scenario | λ=0 | λ=0.01 | λ=0.02 | λ=0.05 | λ=0.1 |
|---|---|---|---|---|---|
| A production (min_inv=0), mean deployed | 0.706 | 0.706 | 0.706 | 0.706 | 0.706 |
| C min_inv ON, loose turnover cap | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

2D (min_inv ON): deployed = 0.706 / 0.755 / 0.856 / 1.000 at turnover cap
0.15 / 0.2 / 0.3 / 0.5 — **identical at every λ**.

1. **λ (qp_cash_drag_lambda) has zero measurable effect at any tested
   value in any scenario** — the min_invested CONSTRAINT dominates the λ
   objective term wherever both act. The #942 framing "λ=0 is the last
   lock" is corrected: the lock is `qp_min_invested_pct = 0`; λ is
   decoration on these inputs.
2. **The lever pair is min_invested_pct (on-switch) × turnover cap
   (throttle)**: switching min_invested on moves deployment 0.706 → 1.0
   under a loose cap; the turnover cap then sets the pace monotonically.
3. **The orch#931 serving drift caps the evidence**: no run after
   2026-05-21 carries the mu/sigma the solver needs — the producer fix is
   a hard prerequisite for ANY current-data deployment evidence.

## What this does not decide

The 2026-05-23 re-enable condition stands verbatim ("re-enable only after
WF shows benchmark-relative alpha survives the strict admission gate") —
this sweep prices the MECHANICS, not the alpha evidence; the committed
script's own scope note stands (simplified constraints, per-name cap only;
the in-pipeline 10-session shadow sweep remains the enable-gating AC).
Proposal shape for when the evidence lands: min_invested restored to its
historical value with turnover cap 0.2-0.3 as the pace dial — a
strategy-104 config PR, one reviewed change.
