# M8 cluster wave-1 — measurement complete, VERDICT: NO-GO

DATE:     2026-07-03
SCOPE:    master-plan Term BR row M8 (doc/design/2026-07-02-unified-107-
          master-plan.md) — cluster-based breadth wave 1 (+100 quality
          names), E34 resume condition operationalized. Research measurement
          ONLY; read-only on all production data; no watchlist/config change
          (admission is a D-gate decision and this NO-GO removes it).
STATUS:   DONE — spec frozen and committed BEFORE selection/measurement;
          stage A (selection) + stage B (paired WF) + verdict all completed
          in-session; full WF was tractable (62s), so no staged deferral.

WHAT:
- `scripts/m8_cluster_wave1.py` — freeze / select / evaluate / verdict.
- `doc/research/evidence/2026-07-03-m8/` — frozen spec, wave-1 list (100
  names, sector-balanced to incumbent GICS mix), paired 7-cut WF results
  (both arms, fwd_60d + fwd_20d, placebos on qualifying cuts), per-date
  ICs, verdict JSON.
- `doc/research/2026-07-03-m8-cluster-wave1.md` — the memo (D3 synthesis
  input for Term BR).

RESULT (frozen gate: mean paired Δ over qualifying cuts ≥ −0.010 on
fwd_60d_excess):
- Mean paired Δ (aug 233 vs base 133; qualifying cuts 5/6/7 = tests
  2023/2024/2025) = **−0.0477 ⇒ NO-GO**. Wave wins 1/3 cuts.
- Consistent everywhere: fwd_20d −0.0171; placebo-clean Δ −0.0328 (60d) /
  −0.0288 (20d); date-level pooled Δ −0.0476 (naive SE 0.0037, n=691).
- Mechanism: incumbent-subset diagnostic shows the augmented model is worse
  ON THE INCUMBENT BOOK (cut5 +0.140→+0.066, cut7 +0.128→+0.061) — training
  dilution, i.e. E34's transfer-coefficient collapse reproduced even under
  outcome-free structure-similarity selection.

CONSEQUENCE (frozen, not re-arguable): waves STOP; no wave-2; Term BR falls
back to Plan B — BR via the D3 down-cap decision (master-plan L1). E34 stays
STANDS; its resume condition has now been tested once and failed its gate.

INTEGRITY: selection criterion is outcome-free (feature-rank-structure
similarity) — no selection-on-outcome by construction; the E34-literal
"top-IC per bucket" alternative was rejected as structurally untestable
(512/683 candidates start 2021-05-03, no disjoint selection window) and this
is recorded in the frozen spec. Survivorship bias favors the wave, making
the NO-GO conservative. Costs not modeled (IC-level gate per plan row).
