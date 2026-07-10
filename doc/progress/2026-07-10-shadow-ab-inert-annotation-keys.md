# Shadow A/B treatment-diff: _-prefixed keys are inert annotations   (PR #455)

STATUS:    delivered
WHAT:      `_flatten_config`'s treatment-key-isolation check (D6-§2a's
           config-diff validator, orchestrator#451) now drops every
           `_`-prefixed key at any depth, not just keys ending in
           `_reason`. Fixes a real fail-closed false positive: the first
           plan-only run of the merged two-arm runner against the REAL
           pinned `shadow_a.json`/`shadow_b.json` configs (strategy-104#53)
           was invalidated solely by their `_arm` annotation strings
           differing — a documented, inert delta that codex's review on
           #53 explicitly endorsed as non-functional.
WHY/DIR:   Last blocker before the first real two-arm session: plan-only
           mode now clears artifact resolution, same-world fingerprints,
           pin checks, and sealing, and reaches (and passes) the treatment
           check.
EVIDENCE:  n/a (code-structure/contract-enforcement fix; no model/data
           claim — see Tests below for the regression evidence)
NEXT:      Codex re-review; on approval this clears the way for the first
           two-arm plan-only session against the real pinned configs.

## Bottom line

`_flatten_config` previously stripped only keys ending in `_reason` when
computing the treatment-key isolation diff between the two shadow arms'
configs. The house-wide config convention — already established by the
strategy-104 active==golden semantic-match test, and by the `_arm`
annotation strategy-104#53 added to both arm configs (codex-endorsed as
inert on that PR) — is broader: EVERY `_`-prefixed key at any depth is an
inert annotation that no reader in any repo consumes as behavior. The
narrower `_reason`-only rule caused a real fail-closed false positive on
the first plan-only run against the actual pinned configs, since `_arm`
doesn't match the `_reason` suffix pattern.

## Fix

- `_flatten_config` (`src/renquant_orchestrator/shadow_ab_runner.py`) now
  drops keys matching `key.endswith("_reason") or key.startswith("_")`,
  with the docstring updated to cite both the §2a protocol's `_reason`
  carve-out and the house-wide `_`-prefix convention.
- New positive test exercising the real `_arm` shape from the pinned
  configs.
- New **laundering-guard negative test**: a functional delta introduced
  alongside differing `_`-prefixed annotations must still be caught —
  proving the broadened inert-key rule doesn't accidentally widen the
  isolation check's blind spot.

## Tests

`tests/test_shadow_ab_runner.py`: 48/48 passed. Full suite: 3345 passed.
