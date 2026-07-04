# S12 shadow freshness root-cause diagnosis

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: S12 (shadow freshness impl + panel-refresh root-cause memo)

## What

Root-cause diagnosis memo for the stale shadow PatchTST serve pin.
Two candidate causes identified:

- **A: builder-not-run** — the shadow retrain launchd job is not loaded or
  is failing silently; no staged artifact produced for the promote chain.
- **B: dropna clip** — the shadow retrain pipeline may still couple its
  feature axis to the training label clip (the same class of bug as #26);
  separately, config-fingerprint drift causes promote-time fail-close.

Includes 6 read-only investigation steps the operator can execute to
distinguish the two causes. This is the "diagnosis FIRST" deliverable
that the master plan requires before implementing shadow freshness phases 2–4.

## Not included

No code changes. The diagnosis identifies what to investigate; the fix
depends on which cause is active.
