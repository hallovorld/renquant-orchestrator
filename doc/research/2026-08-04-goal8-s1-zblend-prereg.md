# GOAL-8 S1 preregistration — z(prod) + z(slow momentum) shadow lane

STATUS: FROZEN ON MERGE. This document preregisters the S1 rung of the
GOAL-8 ladder (operator-promoted 2026-08-03) BEFORE the lane's first scored
run. S1 is an OPERATIONAL rung: it measures serving reliability only. No
performance readout happens at S1; the S2 comparison has its own prereg,
frozen before unblinding. Amending any FROZEN section after the lane's
first scored run voids S1 and restarts its clock.

## Object under test

A shadow profile whose PRIMARY scorer is `kind: "blend"` with exactly two
components, in this order (order is identity-bearing):

| # | component | kind | identity pin |
|---|---|---|---|
| 0 | prod panel model (alpha158, reversal/fundamental-leaning) | panel (default) | `expected_content_sha256` (abbrev, of the artifact file at profile creation) + `expected_config_fingerprint` (recipe) |
| 1 | slow momentum residual v0 (12-1, weekly ledger-served) | `momentum_residual` | `expected_config_fingerprint = momentum-v0-fd65161a20b29314` `[measured 2026-08-04 from the live genesis ledger tail: cutoff 2026-08-02, artifact a824c480…, n_scored 144, params window=252/skip=21]`; content pin REFUSED by the loader (append-only ledger) |

Loader surface: pipeline#261 (`load_blend_scorer` kind dispatch). The
momentum leg loads through the one existing ledger-chain loader (chain →
tail dated artifact → sha both directions → parity → golden reproduction).

## FROZEN semantics (inherited verbatim from the certified clf-blend — no new knobs)

1. Equal-weight sum of per-leg cross-sectional z-scores; z uses ddof=0
   over each leg's own finite-scored universe at scoring time.
2. NaN propagates through the sum: the composite scores the
   **INTERSECTION** of the legs' scored universes. A name the momentum
   leg does not cover gets NO blend score (dropped as unscored), never a
   half-blend fallback.
3. A degenerate leg (std=0 or <2 scored names) contributes 0 and stamps
   `degraded_reason`. For S1 accounting a degraded session is **NOT
   green** (visible failure, counted).
4. Composite `config_fingerprint` = the existing recipe
   (`sha256(fp0 + "\n" + fp1)`, stored forms verbatim, order-bearing).

## FROZEN S1 acceptance (AC1 of GOAL-8)

Window: 20 scheduled daily-full sessions, starting with the FIRST
SCHEDULED SESSION AFTER THE DEPLOYMENT BOUNDARY. The boundary is the
FIRST COMPLETED RUNTIME SYNC that verifies the profile/lane commits are
ACTIVE on the run surface (the s104 runtime checkout at the profile
commit + the rail present in the live tree), with its timestamp AND the
verified commit shas recorded in the deployment record (grants trail +
the profile PR's progress doc) so the window is reproducible. Neither
alternative survives review: a merge timestamp counts pre-deployment
sessions as failures in an architecture where merge does not deploy and
the documented sync can lag `[codex on orch#777 round 2]`; a
first-scored-run start censors deployment/load failures — exactly the
availability failures S1 exists to measure `[codex round 1]`. From the
boundary, EVERY scheduled session counts, including sessions where the
lane never produced a record or the scorer failed to load. Green
session =
- the lane's identity-stamped shadow record exists for the session, AND
- the blend scorer LOADED (no `panel_scorer_load_failed`, no unresolved
  artifact), AND
- the record's composite `config_fingerprint` equals the frozen expected
  value computed at profile creation, AND
- `degraded_reason` is empty.

**PASS = ≥19/20 green.** FAIL = ladder pauses at S1; the failure classes
get named and fixed; the 20-session clock restarts. No peeking at return
outcomes during the window (returns belong to S2's prereg).

## Named operational risk, frozen resolution

The panel leg REQUIRES a byte content pin, and RFC#210 (armed 2026-08-04)
makes the prod artifact change on promotion weekends after a 44-day
freeze. Every prod promotion therefore STALES the profile's leg-0 pin and
the lane fail-closes until the profile is re-pinned. FROZEN default:
**accept the fail-close + re-pin PR cadence** — the fail-close is the
designed identity guard, a red session it causes counts as NOT green, and
that operational cost is exactly what S1 exists to measure. (A
recipe-only pin mode for the panel leg would be a pipeline change; if it
is ever built, it lands as a NEW prereg, not an amendment to this one.)

## Prerequisites (all must land BEFORE the profile PR; none affect the frozen content above)

1. pipeline#261 merged + pinned to the deployed runtime.
2. s104 profile PR (delta on the momentum-profile precedent) that in the
   SAME batch wires the consuming lane — never an inert config file.
3. The lane's sentinel watch entry (the momentum/fast precedent, orch#776
   pattern) added in the same batch or earlier.

## Rollback

Remove the profile + lane wiring in one revert; the blend loader itself
is inert without a consuming profile.
