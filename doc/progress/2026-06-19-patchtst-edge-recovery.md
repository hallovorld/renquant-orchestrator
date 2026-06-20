# PatchTST edge-recovery experiment — pre-registration

STATUS:   in-progress (experiment-prep PR; the runs launch concurrently in /tmp, isolated)
WHAT:     pre-registers two concurrent 60d PatchTST experiments + their reliability checks:
          A = reproduce B2 (exclude MIN/STD/IMIN); B = B2 + prune the pure-placebo drivers
          (IMXD/CORR/RANK/RSV/IMAX/gross_profitability/sue_signal). Judge = production WF gate.
WHY/DIR:  north star = a gate-passing 60d model so daily-full can trade again. B2 is the ONLY
          config with positive val IC (+0.024); hypothesis = prune the remaining pure-placebo
          features to clean the gate placebo while keeping the signal.
EVIDENCE: 20d/60d-unpruned both FAIL the gate (real_ic -0.0196 / -0.0227); B2 best_val_ic
          +0.0040/+0.0239; B2 excluded STD/MIN/IMIN; audit pure-placebo = IMXD/CORR/RANK/RSV/IMAX.
          `[VERIFIED — summary.json + gate logs + feat_ic_audit + B2 metadata diff]`
NEXT:     run A+B (isolated /tmp, multi-seed) → gate each → report verdicts. Promotion only on
          a clean gate PASS + operator sign-off; never bypass the gate.
