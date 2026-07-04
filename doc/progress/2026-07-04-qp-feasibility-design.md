# QP feasibility fix design

DATE: 2026-07-04 (round 3)

STATUS: DESIGN — round 2's hypothesis-driven rewrite still smuggled two
overstated claims back in through the proposed-fix/risk sections; round 3
tightens those. Still not implemented; Stage 0.5 validation gate must pass
before Stage 1 pipeline work is authorized.

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

## Round 3 (Codex re-review after round 2)

WHAT: Codex's round-2 review found two claims in the "proposed fix" and
"risk assessment" sections still asserted more certainty than the
hypothesis-driven framing allowed. Fixed both:
1. Stage 3 (soft-turnover migration) claimed the reform "makes the QP
   always feasible." Rewrote as a hypothesis: turnover is *plausibly* the
   dominant binding constraint in observed infeasible runs, but budget,
   box, wash-sale, sector, and correlation constraints remain in the
   constraint set and can still conflict independent of turnover. Stage 3
   now explicitly states it targets *turnover-driven* infeasibility, not
   infeasibility in general, and points to Stage 4's fallback + the ~5%
   (not 0%) Full-stage projection as evidence the doc already expected
   residual infeasibility.
2. The Stage 2 risk-assessment line claimed "commission-free broker means
   no cost impact." Rewrote to name the real non-commission cost channels
   (slippage, spread-capture, possible realized-IR degradation from faster
   rebalancing) and tied monitoring to the existing TC time-series
   mechanism rather than asserting the risk away.

WHY-DIR: A memo whose entire discipline is "don't claim more than the
evidence supports" cannot let a proposed-fix section reintroduce
unqualified certainty just because the evidence-boundary section up top
is honest. Codex: "it should not smuggle new certainty back in through the
proposed-fix sections."

EVIDENCE: Grepped the full doc post-edit for "always feasible",
"no cost impact", "entirely", and "commission-free" to confirm no other
section still relies on either retired claim (the one remaining
"commission-free" mention, in the Stage 2 body text describing current
turnover-cap capacity math, is a factual statement about trade count, not
a cost-impact claim, so left as-is). [VERIFIED — read the entire doc
top-to-bottom after edits; Stage 4 and the Success-metric table's ~5%
Full(1-4) residual-infeasibility projection were already consistent with
the corrected Stage 3 framing, no further downstream changes needed]

NEXT: Same as round 2's NEXT — unchanged by this round's edits.
