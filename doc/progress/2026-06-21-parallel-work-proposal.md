# Parallel-work proposal (while seed45 runs) — for discussion

STATUS:   in-progress (discussion PR; nothing started — operator/Codex to prioritize)
WHAT:     proposes 3 bounded parallel-work candidates that don't need seed45 and don't touch
          the running experiment: P1 diagnose BULL_CALM monotonicity gate failure (read-only);
          P2 build the C1 prod-path write-guard hook; P3 pre-design feature-eng escalation.
WHY/DIR:  KEY finding — BULL_CALM trade-monotonicity FAILS in every experiment independently of
          placebo, so it blocks promotion even if seed45 cleans the placebo → it's a separate,
          parallel blocker on the daily-full critical path. Recommend starting P1.
EVIDENCE: monotonicity "failed in active regime(s): BULL_CALM" in all 4 gate logs (60d, 20d,
          Exp A, Exp B). `[VERIFIED — /tmp/{patchtst,patchtst_20d,exp_A,exp_B}_gate.log, ephemeral]`
NEXT:     operator/Codex pick P1/P2/P3 → I open the chosen one as a worked PR.
