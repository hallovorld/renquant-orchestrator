# 2026-08-05 — GOAL-7: Arm A run under the frozen prereg

Result document: `doc/research/2026-08-05-goal7-arm-a-result.md`.

**Bottom line:** all four §6 conditions hold on the primary regime
(BULL_CALM, n=1684, E1 +0.0298, genuine_shuffle +0.0291, genuine_shift
+0.0067) — and **Arm A certifies nothing**. Decision asked for: run Arm B when
the ledger matures (~2027); re-weight nothing now.

The tight leg is the shift placebo: the 2×-shifted label alone reproduces
+0.0230 of the +0.0298, so most of the raw IC is label persistence. The shuffle
leg is nearly free (+0.0006).

The registration was frozen **before** the arm ran, and the three choices it
did not fix (window, universe, the helper's ±0.5 label clip) were declared in
the producer's docstring before any number existed.

The producer is a separate file from the runner deliberately — the harness that
judges cannot be the harness that chooses — and it refuses outright if the
served params stop matching the packaged construction (§1).

Suites: 13 new tests · full suite green.
