# 2026-07-11 — F4 design: regime-scoped consequences for freshness overrides

## Bottom line

Design-only amendment to the operator's 2026-06-30 model-freshness directive
(RFC #210 lineage): when a freshness override promotes a gate-FAILING model, the
regimes that model FAILED in carry consequences — (C) always-on OVERRIDE-DEGRADED
disclosure in run bundle + ntfy, (B) optional buy-budget haircut in degraded
regimes, (A) optional shadow-demote (deferred to its own design). Operator picks
the terminal level at merge; nothing is implemented in this PR.

## Why now

PR #476 H4 (re-verified 2026-07-11 from the live artifact's `wf_gate_metadata`,
sealed in renquant-artifacts#19): the live XGB was promoted 2026-07-06 via
`manual_override=true` with `wf_reason` FAIL + `sanity_regime_ic` FAIL in
BULL_CALM + `trade_monotonicity` FAIL (BULL_CALM top-vs-bottom entry spread
inverted −13.7pp). Four days later the META misread coincided with a BULL_CALM
session — an observed temporal/regime association, not a demonstrated causal
mechanism (PR #476's H2/H3 remain unvalidated hypotheses). The argument does not
depend on that causal link: the gate named the failing regime before promotion,
and the regime-blind override discarded that information regardless. This
amendment keeps the override (the 06-30 directive stands) but stops it from
granting full authority in the regimes the gate specifically failed.

## What this PR contains

- `doc/design/2026-07-11-freshness-override-regime-consequences.md` — the
  amendment: mechanical failed-regime extraction stamped at promotion
  (`override_consequences.v1`), decision-time predicate on `ctx.regime`
  (stamped by RegimeJob before scoring/admission; per-regime config precedent =
  `governor_sizing.e_ceil_by_regime`), option set C/B/A with config schema
  (`freshness_override_consequences.v1`, safe default = disclose, exits never
  touched), ownership map, staged shadow-first rollout, open questions.
- This progress note.

## Verification

- Docs-only: no code, config, broker, risk, or sizing change in this PR.
  `[VERIFIED]` — diff touches two markdown files.
- Evidence citations checked against PR #476's body + the pipeline #186/#187
  progress docs this session. `[VERIFIED]`

## Decision needed

Operator sign-off on the amendment + choice of terminal consequence level
(design §6). Do not merge without operator review; not self-merging.

## Correction (Codex review, 2026-07-11)

Three fixes applied to the design doc: (1) the "META misread happened exactly
in BULL_CALM" phrasing was softened to an explicit observed-association-not-
causal-mechanism framing, matching PR #476's own H2/H3 caveats; (2) Option B/A
in the staged rollout now explicitly require a SEPARATELY APPROVED,
preregistered shadow evaluation protocol (predeclared session minimum,
comparison metric, stop/rollback rule) before shadow logging counts toward
advancement — an ad hoc session count is no longer sufficient; (3) this PR's
status line and title/body were changed from "design for review" to an
explicit DISCUSSION DRAFT, and the PR itself converted to a GitHub draft, so
it cannot be read as awaiting only a Codex approval — the operator decision
(§6) is the actual gate.
