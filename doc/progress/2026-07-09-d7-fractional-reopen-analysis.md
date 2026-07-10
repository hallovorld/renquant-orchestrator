# D7 fractional reopen analysis — research

**Date**: 2026-07-09
**Status**: Research memo (no behavior change)

## Bottom line

Fractional-shares reopen (RFC #443 deliverable D7): the reopen already happened as
S-FRAC v2 (2026-07-02, RFC #254) and stages 0–2 + software-stop registry are merged
AND live-pinned. The integer-cast gap (`runner_execmath.py:36`) is now CLOSED: per
Codex's r2 objection, the cash-cap math moved to its correct owning repo
(`renquant-execution#25`, merged) instead of staying under an umbrella "migration
exception"; `RenQuant#454` (merged) is now a thin delegating call-site with a
fail-closed fallback. Remaining: merge approved strategy-104 #46 + software_stops
key, pin bumps, and the stage-3 shadow / pager / sign-off process gate.
Recommendation: PROCEED — marginal cost is small and success criteria are already
frozen.

## Changes

- `doc/research/2026-07-09-d7-fractional-reopen-analysis.md` — r2 update: gap #1
  (execmath ownership) reclassified from "pending exception approval" to CLOSED,
  now that renquant-execution#25 + RenQuant#454 have both merged; operator asks
  reduced from 4 to 3
