# GOAL-1 closeout: measurement complete, decision handed over

STATUS:   delivered — AC2 + AC4; GOAL-1's four ACs all discharged.
WHAT:     doc/research/2026-08-24-goal1-closeout.md. AC2's finding is
          structural, not statistical: counterfactual cap entries have no
          realized outcomes, and even the fwd-return proxy covers 50/467
          names with n_eff(h=20)=1. AC4 (r2) recommends cap 8->10 NOW,
          fractional SEPARATELY under its own contract — the r1 coupling
          was wrong (destroys attribution + the readiness claim was
          incorrect: zero is_fractionable implementations on the active
          tree [VERIFIED 2026-08-24]).
WHY/DIR:  the model finds 20-27 buyable names per session against 0-2 free
          slots; this is the only lever that changes how much model output
          reaches capital, and the decision is the operator's by hard gate.
EVIDENCE:
  artifact:      the closeout doc (r2).
  prod or exp:   exp — read-only measurements.
  existing data: 467/50/10/n_eff=1 proxy measurement [VERIFIED 2026-08-24];
                 AC1 v3 grid: cap-10 integer tilt 1.20x < today's 1.28x,
                 median deployment 17.3%->32.6% [VERIFIED — grid output].
  best-known?:   yes — cap 10 captures the bulk of unmet admissible demand
                 at minimum structural change; 15 buys +12pp with worst
                 tilt regime (1.40x).
  r2 staged plan: (1) cap only now, authority = LONG row 2b (orch#1049);
                  monitoring gates (first 10 sessions): median deployment
                  toward ~32%, realized integer price-tilt <= 1.28x,
                  wash-sale block-session rate no rise vs trailing baseline;
                  any gate failing -> revert PR.
                  (2) fractional separately: umbrella broker-adapter PR
                  implementing is_fractionable on the ACTIVE adapter,
                  software-stops stage-3 arming, then one-bit flip under
                  its own ledger row.
  scope:        documentation. NO config change (AC3).
REVIEW:    codex (haorensjtu-dev).
