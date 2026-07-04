# Phase 3: four-system documentation normalization

**Date**: 2026-07-04
**PR**: docs/phase3-system-normalization

## Intent

Fulfill the operator directive to normalize 104/105/106/107 documentation. Part of
the compliance fix campaign Phase 3 (`doc/design/2026-07-04-compliance-fix-campaign.md`).

## What changed

Created four as-built architecture documents documenting what is ACTUALLY
implemented (verified by reading source code), not what was designed:

- `doc/design/renquant-104-as-built.md` — production daily batch decisioning
- `doc/design/renquant-105-as-built.md` — intraday session decisioning (shadow-only)
- `doc/design/renquant-106-as-built.md` — signal evolution and experiment framework
- `doc/design/renquant-107-as-built.md` — governance and risk infrastructure

Updated `doc/INDEX.md` to use these as the canonical system architecture reference,
with stale docs marked as superseded.

## Direction

Each doc follows a consistent structure: Purpose → Architecture → Key Modules
(with repo + path) → Gates/Contracts → Current Status → Open Items →
Cross-references. All four are cross-linked.

## Evidence

- Verified module existence and structure by reading actual source across all repos
- Module counts, test counts, and feature status cross-checked against code
- VERDICTS.md row count and verification statuses verified against origin/main

## Next

- These docs should be updated as systems evolve (they document current state)
- C1 mirror-drift inventory will provide quantitative data for the 104 as-built's
  kernel dual-home section

## Round 2 (codex review)

Codex held this PR for two concrete reasons:

1. **`doc/INDEX.md` demoted the agent control contract.** The reorganization dropped
   `AGENT-RETROSPECTIVE.md` and `AGENT-STATE.md` entirely — not demoted, removed
   outright, not even carried into the "Superseded / Historical" section. These are
   the active control contract and executive-memory checklist for the whole agent
   loop, not historical decoration. Restored: the original top-of-file "READ FIRST"
   warning block (verbatim, both files) plus their table rows in "Active Governance"
   (added at the top of that table, ahead of `VERDICTS.md`). The broader
   reorganization (as-built docs as the new architecture-reference authority,
   superseded-doc consolidation) is otherwise unchanged.
2. **The 104 as-built doc hard-coded a stale, now-conflicting drift count.** The
   original text froze `78/169 materially drifted` as a manually-typed number. That
   number already disagreed with `renquant-orchestrator#303`'s own C1 inventory
   baseline (`73/168` as of that PR's current branch, commit `f68bbd5a`) — two
   hand-maintained copies of one fact, guaranteed to drift apart again. Replaced with
   a link to the actual source-of-truth artifact
   (`data/c1_drift_baseline.json`, produced by `#303`'s `scripts/mirror_drift_inventory.py`),
   stating the number is current AS OF that commit rather than freezing it a third
   time. Once `#303` merges, that link resolves; until then it's forward-referencing
   a sibling PR by design (the two PRs are meant to land together per the compliance
   campaign's dependency order).
