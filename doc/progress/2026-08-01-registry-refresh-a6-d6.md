# Registry refresh: A6 guarded, D6 re-graded, gate-design cross-link (GOAL-3, #623)

Bundles the two row updates promised on the #623 thread into one reviewed registry
touch `[本次实测 sources on #623]`:

* **A6** — twin guard live since #743 (pair named, 655 diff lines, dual-sha
  `model_diverged_pin`, 24 pass / 0 fail); the retire-vs-pin registry question stays
  open (#728).
* **D6** — re-graded **P1 → P2-cutover-pending**: deterministic schema dispatch (M6
  rule, no OR-accept) measured DEPLOYED in the pinned runtime; served artifact still
  legacy-stamped; residual exposure is fail-closed legacy-shim verification, not the
  original fail-open. Cutover rides the next artifact promotion.
* Addendum cross-links the WF-gate candidate/lineage-scoring design
  (renquant-backtesting#94) as the designed treatment for T1's evidence-vs-live
  divergence at the gate level.

Docs only; no code, no thresholds.
