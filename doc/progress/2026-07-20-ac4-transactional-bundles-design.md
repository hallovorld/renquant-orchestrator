# Progress — AC4 transactional artifact bundles (design)

**Date:** 2026-07-20
**Goal:** GOAL-5 P0 AC4 (month-1). **Type:** design RFC (no code).

## STATUS:
Design/RFC, reviewed through codex r2 — the r2 migration-order bug (§4.5 step 3
dangled the flat path before `active` existed) is fixed in this branch. Ready
for codex re-review; no implementation PR should open until that lands. Not
merged yet.

## WHAT:
A design/RFC for making the live serving-pair promote/rollback an **atomic
pointer flip** so a mid-promote crash can never leave a mixed panel+calibrator
pair (the binding-orphan class that fail-closed the book 4×, incl. the 07-16
book-drain incident). Includes the M6 fingerprint-unification finish. Full RFC:
`doc/design/2026-07-20-ac4-transactional-bundles.md`.

Key decisions (for codex review):
1. **Generation dir + single atomic symlink flip** (`os.replace` on a symlink =
   one syscall) as the P2 mechanism, over routing daily readers through the
   artifacts store (deferred P3) — minimises new failure surface on the 13:55
   capital path.
2. **Reader single-resolve** (`realpath(active)` once, read both members from
   the concrete immutable gen dir) to kill the open-panel-then-flip-then-open-cal
   TOCTOU.
3. **M6 behaviour flip (`accept_legacy_stamps=false`) is a separate,
   shadow-gated PR**, sequenced after the behaviour-invariant plumbing — per
   fix-wave-protects-production.
4. **Acceptance = kill-injection test matrix** (crash at each promote/rollback
   point → never a mixed pair) + a live-shadow promote/rollback drill.

## WHY/DIR:
Scoped the current state by direct read (subagent map, verified against
`origin/main` + the umbrella working tree), not guessed:
- Located the exact non-atomic window: `weekly_wf_promote.sh` Step 5 lines
  361→362 (panel replace, then calibrator replace) — fs evidence: prod pair
  mtimes 3h apart on the incident day.
- Confirmed the transactional substrate already exists (renquant-artifacts
  store PREPARE/ACTIVATE/rollback_to; orchestrator `bundle_seal.py`
  regenerate_flat_views + crash_hook seam) **but is scoped to byte-identical
  genesis and refuses changing pairs** — the changing-content publisher is the
  documented AC4 P2/P3 deferral.
- Enumerated the 4 fingerprint impls + `accept_legacy_stamps` default-True
  window (census green 47/47 → M6 flip unblocked).

Review rounds:
- **r1** (codex CHANGES_REQUESTED): I1 overclaimed (§4.2 straddle concession),
  un-fsync'd flip durability overclaimed, no initial-migration protocol. →
  addressed in `24ed7566` (reader-inventory gate, OLD-or-NEW crash semantics,
  §4.5 migration protocol).
- **r2** (codex): major issues resolved; **one migration-order bug** — §4.5
  step 3 replaced the flat files with `→ active/<member>` symlinks *before*
  `active` existed → the first replacement dangles. → fixed in this branch:
  split step 3 into **3a create+fsync `active` first, then 3b flip each compat
  path** (gen-0001 is byte-identical so every intermediate state resolves
  consistently), and added a **no-dangling / no-missing assertion after every
  migration step** to §4.5 + §6.

## EVIDENCE:
n/a
(Design/RFC doc — no runtime or data claims to ground here. The design's own
grounding — incident fs evidence, existing substrate scope, review-round
history — is under WHY/DIR above.)

## NEXT:
- Awaiting codex re-review (r2 migration-order fix) before any implementation
  PR opens.
- Design only; implementation is 4 separate reviewed PRs named in RFC §7
  (orchestrator entry point + tests; umbrella promote-script rewire +
  migration; kernel reader single-resolve; pipeline/common M6 import
  unification).
