# Workstream: model edge (the binding problem)

STATUS:   active — this is the one thing between us and live buys.
GOAL:     a PatchTST model with **positive real cross-sectional IC** that passes the WF gate.
NEXT:     seed45 of the Exp B recipe is running (build→gate, isolated /tmp); if it also misses,
          the marginal-edge finding stands → escalate to feature engineering / architecture, not
          a forced promotion. Promotion needs operator sign-off; never bypass the gate.
EVIDENCE: Exp A/B ran through the production WF gate (#158): both FAIL. Exp A (prune STD/MIN/IMIN)
          placebo_ic +0.0317; Exp B (+pure-placebo IMXD/CORR/RANK/RSV/IMAX) placebo_ic +0.0059 —
          a near-miss (thr +0.0050), aligned_real_ic positive (+0.0046→+0.0079). On these
          single-seed runs, pruning the pure-placebo families was ASSOCIATED with a −81% placebo
          drop; causal attribution PROVISIONAL (both FAIL, single-seed, WF-sim degraded in B,
          BULL_CALM monotonicity persists). `[VERIFIED — /tmp/exp_{A,B}_gate.log, ephemeral]`
CONSTRAINT: PatchTST is the chosen model (LONG #4); XGB is vetoed as a pitch (LONG #3).
