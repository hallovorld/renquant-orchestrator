# Decision Record — Scorer Lineup: PatchTST Primary, XGB Shadow, Ensemble Shelved

**Date:** 2026-06-12
**Decider:** operator
**Status:** ACTIVE decision — supersedes the adoption path of
`doc/research/2026-06-12-ensemble-primary-proposal.md` (the proposal remains
as analysis; its adoption is declined)

## Decision

1. **PatchTST (pt07 strict seed44 lineage) remains the primary scorer.**
2. **XGB (alpha158_fund) remains shadow-only** (the #114-revived shadow rail
   keeps producing the daily primary-vs-shadow comparison).
3. **The ensemble candidate is NOT adopted.** No further ensemble
   implementation work unless a *major change* occurs.

## Operator rationale (recorded verbatim in spirit)

- XGB's mechanism is not trusted as a primary ("dated"; suited to
  shadow/ensemble roles at most); the market keeps producing new patterns.
- The ensemble's measured improvements (backfill v0: full-year IC +0.081 vs
  +0.071; dead-window top-8 edge −0.124 → +0.244) and the analyst-consensus
  check were reviewed and judged insufficient to change the lineup.

## What would count as a "major change" (reopening triggers)

Any of:
- The WF gate **fails** a fresh-cutoff PatchTST retrain while an ensemble or
  alternative candidate **passes** the same gate on the same evidence windows.
- The shadow rail shows the shadow scorer dominating the primary on rolling
  60-day live IC for a sustained period (≥ 1 quarter), measured fairly
  (same-cutoff, strict OOS).
- A regime of sustained calm-tape losses attributable to the primary's
  measured calm-window weakness (capability-boundary doc §1.3) with real PnL
  impact.

## What continues unchanged

- WS-1 data hygiene, WS-2 point-in-time retrains (now training), quarterly
  fresh-cutoff retrain institutionalization, information-expansion screens,
  daily data pipeline, provenance stamps — all serve the PatchTST primary.
- The WF gate remains the sole promotion authority; buys stay blocked until a
  PatchTST artifact passes it.
- Experimental work stays on `epic/model-edge-experiments`, never on main.
