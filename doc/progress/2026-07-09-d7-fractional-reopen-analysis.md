# D7 fractional reopen analysis — research

**Date**: 2026-07-09
**Status**: Research memo (no behavior change)

## Bottom line

Fractional-shares reopen (RFC #443 deliverable D7): the reopen already happened as
S-FRAC v2 (2026-07-02, RFC #254) and stages 0–2 + software-stop registry are merged
AND live-pinned. Remaining: one integer-cast fix (`runner_execmath.py:36`), merge of
approved strategy-104 #46 + software_stops key, pin bumps, and the stage-3 shadow /
pager / sign-off process gate. Recommendation: PROCEED — marginal cost is small and
success criteria are already frozen.

## Changes

- `doc/research/2026-07-09-d7-fractional-reopen-analysis.md` — full audit: 06-30
  objections resolved/bounded, gap inventory, Governor interaction, risk surface,
  four operator decision asks
