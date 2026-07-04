# QP feasibility fix design

DATE: 2026-07-04 (round 2)

STATUS: DESIGN — revised to hypothesis-driven per Codex review; still not
implemented; Stage 0.5 validation gate must pass before Stage 1 pipeline
work is authorized.

WHAT: Round 1 presented a 4-stage pipeline fix plan for QP infeasibility
(68% of runs, TC -0.43 → projected +0.57) as an already-established root
cause. Round 2 rewrites `doc/design/2026-07-04-qp-feasibility-fix.md` as a
hypothesis-driven note: added an explicit evidence boundary (n=22 live
runs, small sample, and the infeasible/optimal breakdown itself depends on
#308's in-flight taxonomy fix), enumerated 4 competing explanations
(feasibility, gating loss, stale holdings, status-mapping ambiguity), added
an explicit falsification criterion, inserted a new Stage 0.5 telemetry-
validation gate (cross-checking orchestrator TC measurement against
pipeline-side `qp_trace_maps` / solver status) that Stages 1-4 are now
conditional on passing, and softened the title/headline claims (dropped
the "-0.43 to +0.57" framing as established, marked the success-metric
table as projected-not-committed).

WHY-DIR: Codex held the PR — the original doc promoted a still-fragile
diagnostic into a staged fix plan with more certainty than the underlying
measurement (small live sample, taxonomy not yet strict enough to
distinguish "optimal" from "merely not flagged infeasible") supports. A
design memo can be opinionated but needs an evidence boundary and a
falsification statement; the recovery path should be conditional on
validating the diagnosis in pipeline-side telemetry, not presented as
already established.

EVIDENCE: Diffed the doc against origin/main; confirmed PR #308 (the
taxonomy-fix PR this design's numbers depend on) is still at its original
pre-fix commit (`26bac422`, no correction pushed yet at time of this
revision) — so this revision does not fabricate "corrected" numbers, it
instead makes the dependency and its current unresolved state explicit in
the evidence-boundary section, and gates the staged plan on that
correction landing. Read `kernel/decision_trace.py` in renquant-pipeline
to ground Stage 0.5's validation step in a real, existing telemetry
interface (`qp_trace_maps`) rather than a hand-wavy "check pipeline
telemetry" instruction. [VERIFIED — doc reviewed end-to-end after edits;
progress-doc-schema CI gate (`scripts/require_progress_doc.py`) only
requires a touched `doc/progress/<date>-<slug>.md` file, which this PR has]

NEXT: Once #308's taxonomy correction lands, re-run the root-cause
decomposition with corrected numbers and update this design doc's Stage
0.5 section with the actual result (pass → proceed to Stage 1 pipeline PR;
fail → narrow/abandon per the falsification criterion). Do not merge this
PR as a green light to start Stage 1 pipeline work — it is a design doc,
not an implementation authorization, until Stage 0.5 is satisfied.
