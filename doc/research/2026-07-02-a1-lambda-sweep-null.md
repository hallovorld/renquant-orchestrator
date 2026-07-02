# A-1 λ dose-response: NULL — the QP turnover cap binds first (valuable negative result)

STATUS: research evidence (read-only sensitivity study; the in-pipeline 10-session shadow
sweep remains the S6 enable-gating AC). Task: pre-enable evidence for RS-2's A-1 lane.
DATE: 2026-07-02
SCRIPT: `scripts/poc_lambda_sweep.py` · EVIDENCE: `doc/research/evidence/2026-07-02-roadmap-pocs/poc_lambda_sweep.json`

## Result

Driving the REAL pipeline solver (`solve_portfolio_qp_from_snapshot`) on the latest two
full runs' actual (mu, σ) vectors under simplified constraints (per-name cap 0.12, no
sector/corr groups, turnover_max 0.30):

**`cash_drag_lambda` ∈ {0, 0.01, 0.02, 0.05, 0.10} produces IDENTICAL solutions** —
deployed fraction flat (0.422 on 06-30 inputs), n_names flat, **turnover pinned at
exactly 0.30 at every λ**: the turnover cap binds before the cash-drag penalty can act.

## Reading (three consequences)

1. **A-1's expected deployment contribution drops to ≈0.** RS-2's "enable now" stands —
   un-disabling the solver's shipped default is harmless and may matter at other operating
   points — but the deployment AC now rests ENTIRELY on lane B (the sleeve). The #231 S6
   row's Δ-expectation is revised accordingly.
2. **A design finding: the QP turnover cap counts CASH-DEPLOYMENT as churn.** Deploying
   idle cash into first-time positions consumes the same 0.30/session budget as
   position-swapping — so a 75%-cash book mechanically needs multiple sessions to redeploy
   regardless of conviction, top_n, or λ. Whether deployment legs should be
   cap-exempt (or the cap staged) is a RISK-GATE design question for the S6/S7
   implementation PR — flagged, not decided here (the guardrail: never loosen a risk gate
   to force trades; the sleeve makes loosening unnecessary).
3. **Caveats**: w_current approximated (equal-weight holdings), no sector/corr constraints;
   binding-at-exactly-0.30 across all λ is structural, not an artifact of those
   simplifications, but magnitudes are indicative only.
