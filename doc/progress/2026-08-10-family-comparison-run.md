# Family comparison executed — served vs replay indistinguishable at 5d/k=5

STATUS:    the ONE execution of the merged freeze (orch#951); no verdict
           authority; task #26 outcome increment.

WHAT:      doc/research/2026-08-10-family-comparison-run.md — 31 days
           (5 skipped) on the frozen table: SERVED top-5 mean excess-z
           +0.113 vs REPLAY +0.096; daily diff +0.017 (median +0.024);
           bootstrap 95% CI [−0.154, +0.189] — statistically
           indistinguishable. Oracle plumbing control +1.668 (sane).
           UNITS: per-day cross-sectional σ (CSZScoreNorm labels,
           builder docstring line 66) — the raw-return misreading was
           caught pre-publication and is recorded in the note (§2).

WHY/DIR:   With the record validated (#948-#950), the operator's "which
           family should serve" question needed realized outcomes. The
           answer on this window: no measurable separation at k=5/5d —
           a LOW-POWER window (31 autocorrelated days), stated as such.
           Diagnostic input to the qp re-enable chain; NOT the required
           WF-alpha evidence, which remains unbuilt. Any serving-change
           proposal runs its own prereg (frozen doc).

EVIDENCE:  artifact:      data/2026-08-10-family-comparison-runner.py +
                          …-family-comparison_daily.csv / _coverage.csv
                          / _summary.json — the runner's VERBATIM
                          outputs [VERIFIED — run 2026-08-10 after the
                          design merged, exit 0; corpus sha + SEEDS +
                          fold-8 train end asserted at startup]
           prod or exp:   read-only measurement; fold-8 training in
                          memory only, no artifact written
           existing data: design doc (merged #951, incl. two pre-merge
                          amendments); extension corpus (orch#948);
                          synthetic-fixture rehearsal (4 controls PASS,
                          4 bugs fixed pre-run, session scratch)
           best-known?:   yes — §4 states the power limit, the two
                          fixed computable readings, and what this is
                          NOT (the qp re-enable evidence)
           scope:         runner + 3 evidence files + note + this doc;
                          no verdict, no serving change proposed

TESTS:     make test not run — docs+research-data only; runner exit 0;
           pre-run synthetic controls all PASS.

NEXT:      (a) codex review; (b) the 60d-horizon version becomes a NEW
           dated design when extension labels realize (~Oct); (c) the
           qp re-enable chain still needs its own WF-alpha evidence
           design.
