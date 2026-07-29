# Progress: LONG ledger entry 10 — every number carries a provenance tag

STATUS:   transcribed on explicit operator decision (LONG tier = operator decides,
          agent transcribes). Docs only; becomes a Codex-enforced constraint on merge.

WHAT:     Adds entry 10 to `doc/memory/long-term-agreements.md`: every quantity in a
          claim, PR, design doc or memory entry carries `[VERIFIED — command/file]`,
          `[VERIFIED — prior work, ref]`, `[DERIVED — formula/inputs]`, or
          `[ASSUMED — why]`; an untaggable number is not stated; decision-driving
          numbers are re-measured in-session; figure changes reconcile the whole file
          and corrections are visible, never silent overwrites.

WHY/DIR:  Operator, 2026-07-28: "跟你对话觉得你幻觉太严重" → "这个原则要计入永久性memory".
          The rule is written from an actual failure the same day, not a hypothetical.

EVIDENCE: GOAL-6 design rev0 asserted "MDE today = 0.052" and "roughly half the
          per-date IC dispersion is sampling noise". Both rested on one measured
          number plus an unvalidated `1/(N−3)` independence assumption. Direct
          measurement — subsampling the cross-section at N'=20..140 over the 43-fold
          OOS scores (88,750 rows, 625 dates) and fitting `Var(IC) = a + b/N` — gave
          **`Var(N) = 0.01877 + 1.065/N`** `[VERIFIED — computed 2026-07-28 from
          wf-eval/scores.parquet]`: the sampling share is **29%** at N=142, not half,
          and the MDE is **0.053–0.069** across two measured variance estimates, not a
          single 0.052. The stale 0.052 also survived in the executive summary after
          §2 was corrected, leaving the document self-contradictory — which is why the
          rule includes whole-file reconciliation. Same day, same class: a "model
          capability is insufficient" conclusion was drawn from a run in which a
          raw-vs-probability unit bug meant the model was never asked (pipeline#219).

          This PR does not itself assert a new IC/Sharpe claim about a live/candidate
          model, so the standard §4(b) model-evidence triad doesn't apply verbatim;
          the equivalent disclosure for the measurement above is:
          artifact: wf-eval/scores.parquet (43-fold OOS corpus, 88,750 rows / 625 dates)
          prod or exp: experimental — a GOAL-6 design-doc reconciliation, no production
          path touched, no live model claim made
          existing data: reused the already-generated 43-fold OOS corpus; no new run
          best-known?: supersedes GOAL-6 rev0's single-number/unvalidated-assumption
          estimate with a two-estimator measured range (0.053-0.069)
          scope: this PR's own doc + `doc/memory/long-term-agreements.md`; does not
          re-open or re-verify the GOAL-6 design doc itself (tracked separately)

NEXT:     Codex review. Once merged the rule is mechanically enforceable: a PR quoting
          an untagged decision-driving number can be rejected against entry 10.
