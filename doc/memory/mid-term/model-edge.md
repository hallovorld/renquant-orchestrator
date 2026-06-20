# Workstream: model edge (the binding problem)

STATUS:   active — this is the one thing between us and live buys.
GOAL:     a PatchTST model with **positive real cross-sectional IC** that passes the WF gate.
NEXT:     bounded, checkpointed: evaluate B2 (the only positive-val-IC variant) through the
          gate, OR train one smart-pruned 60d variant from the per-feature audit keep/prune
          list. Promotion needs operator sign-off; never bypass the gate.
EVIDENCE: PatchTST prod + fresh rebuilds have *negative* recent OOS IC; B2 pruned 60d is the
          only positive (best_val_ic +0.024). Lever = prune the slow-drift family (drives the
          placebo + drags IC negative). `[VERIFIED — gate logs, summaries; placebo ratio GUESS]`
CONSTRAINT: PatchTST is the chosen model (LONG #4); XGB is vetoed as a pitch (LONG #3).
