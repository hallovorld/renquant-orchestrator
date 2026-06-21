# WF-gate calibration audit — pre-registration (discussion)

STATUS:   in-progress (pre-reg discussion PR; nothing run yet — for operator + Codex to approve
          the design before execution, like #157)
WHAT:     pre-registers an audit of whether the WF gate (not the model) is the binding constraint.
          T1: run the EXACT 05-22 live-trading model (git 2b930ee) through today's gate — does it
          fail only the post-05-24 fail-closed additions? T2: is the placebo threshold floor sound
          at IC≈0? T3: is BULL_CALM monotonicity a <30-sample artifact?
WHY/DIR:  operator-raised — PatchTST made 78 live buys on 05-22, then a wave of fail-closed gate
          checks landed 05-24/25 (placebo threshold, regime sanity, monotonicity); 0 buys since.
          The bar moved right when the model traded. Resolves model-vs-gate, the central ambiguity.
EVIDENCE: 05-22 = 78 live buys (last n_buys>0 run), commit 2b930ee; placebo threshold formula
          first appears 05-25, regime sanity 05-24, monotonicity 05-21/25 — all around/after 05-22.
          `[VERIFIED — git log run_wf_gate.py + runs.alpaca.db live trades]`
NEXT:     operator/Codex approve the design → run T1/T2/T3 (read-only, isolated /tmp, no gate code
          changed) → results PR. Any calibration fix is a separate reviewed PR; NEVER a bypass.
