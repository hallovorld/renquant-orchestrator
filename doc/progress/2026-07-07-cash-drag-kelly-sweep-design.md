# 2026-07-07 — Cash drag Kelly-fractional exploratory sweep design

**PR**: orchestrator design doc

## What

Exploratory 1D screening sweep for `kelly.fractional` (Kelly-sizing
aggression multiplier): 5 levels (0.2–0.7) plus A/A control. 18 sim runs
total.

## Why

`kelly.fractional` was changed 0.5→0.3 on 06-11 as a coupled change with
`sigma_horizon 252→60`. The 0.3 value was set by arithmetic projection,
not backtest. Whether it is optimal under the new sigma is unknown. This
document screens whether the coupled pair is worth a proper factorial
follow-up study — it is not itself a promotion-grade design.

## Scope

Design/framing doc only. No code, no behavior changes.

## Round 2 (codex review)

STATUS: fixed
WHAT: three issues — (1) "fractional" was dangerously overloaded with the
already-prioritized fractional-share-execution mechanical fix from the #406
program; (2) the doc framed this sweep and #405's concentration-cap sweep as
"together" answering the cash-drag question, silently recentering the
program around sizing-parameter research ahead of the #406 program's
established "expression first, residual idle-cash carry second, exposure
knobs later" execution order; (3) the doc's own coupling argument
(`kelly.fractional` was changed as a coupled move with `sigma_horizon_days`)
contradicted its proposed 1D (non-factorial) design, without acknowledging
the mismatch.
WHY-DIR: codex's read is correct on all three — conflating `kelly.fractional`
with fractional-share execution invites exactly the confusion codex
predicted; and a 1D sweep genuinely cannot validate a coupled pair's joint
optimality, so presenting it as anything but an exploratory screen overstates
what the study can support.
EVIDENCE: added an explicit terminology section up top distinguishing
`kelly.fractional` from fractional-share execution, with every subsequent
"fractional" occurrence now either fully-qualified or governed by that
opening disambiguation (grep-confirmed). Reframed the entire document as an
exploratory Phase-3 hypothesis screen explicitly downstream of the #406
program's Phase 1 (fractional-share execution) / Phase 2 (parking sleeve),
not a co-equal or replacement framing — updated the relationship-to-#405
language, the decision-criteria section (now "screening thresholds," not a
promotion gate), the "what this screen does NOT answer" section (led with
the sigma_horizon interaction as the central limitation, not a footnote),
and the execution plan (explicitly sequenced after Phase 1/2 land). Also
fixed an internal terminology collision: this doc's own "Phase 2" (the
factorial interaction follow-up) conflicted with the #406 program's "Phase
2" (parking sleeve) — renamed to "the factorial interaction study"
throughout.
NEXT: none — awaiting fresh review.
