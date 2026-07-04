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
