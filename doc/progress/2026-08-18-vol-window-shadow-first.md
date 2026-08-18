# Vol-gated bull deployment window — shadow-first design (doc only)

STATUS:    design for review. Docs only — NO code / config / behavior change. This PR is
           exactly the artifact the CONFIRMED verdict authorizes, and nothing more.

WHAT:      Commit `doc/design/2026-08-18-vol-window-shadow-first.md`: the vol-window buy
           license (ON ⇔ SPY vol20 > 0.135, the CERTIFIED fixed threshold; window =
           ON ∧ ¬BEAR; license only substitutes for the missing bull regime-admission
           evidence — all downstream sizing/caps/tax/QP unchanged; outside the window
           byte-identical to today), deployed as a `shadow_vol_window` lane FIRST whose
           hash-chained ledger accrues the frozen activation burden (≥20 ON-state live
           sessions with positive realized spread) before any operator ask. AC1-AC4;
           honesty ledger (corpus-bound certification, calm-bull unchanged, ON∧BEAR
           excluded by policy precedence, activation = separate operator decision).
           Review round 1 (2026-08-18): AC3's counter readout re-pinned to the
           CERTIFIED h=60 horizon (h=20 demoted to a non-decisive velocity diagnostic
           recorded in the same rows; universe-mean baseline declared as a deviation
           from the certified DGTW construction); LONG-row-10 provenance tags added to
           every restated number; §6 gained the tail-driven-variance bullet
           (winsorized ON mean +0.0361 vs +0.1840) — see the design doc's visible
           Corrections section.

WHY/DIR:   The frozen consequence of the CONFIRMED vol-switch verdict (#1003, prereg
           #1001): "authorizes ONLY a design PR for a vol-gated bull deployment window
           (shadow/sizing-first, operator-gated; no direct production change)". The
           mechanism converts the program's first never-seen-data CONFIRMED finding
           into the bull deployment the operator has demanded, at shadow risk only.

EVIDENCE:
  artifact:      the design + this doc. No code, no config, no live change.
  prod or exp:   neither — design only.
  existing data: [VERIFIED — #1003 committed results, spot-verified] P1 ON spread
                 +0.184/60d, NW t=+1.952, bootstrap q05=+0.021; P2 ON−OFF +0.128
                 t=+2.378; control passed first; vol-cohort-matched clean; the
                 expanding-tercile variant FAILED (recorded bound → prohibited as an
                 activation key). [VERIFIED — #1001 formation artifact] bull-only ON
                 also cleared (t=+3.10).
  best-known?:   yes — shadow-first with a pre-committed live activation burden is the
                 survivor-free leg the corpus cannot supply; the license is additive-
                 only inside ON∧¬BEAR (BEAR precedence + G-B ownership untouched);
                 the window key is a raw PIT scalar independent of the regime-repair
                 program; sizing multipliers explicitly deferred.
  scope:         "authorizes the SHADOW lane implementation only (two codex-gated impl
                 PRs; deploys operator-gated). Activation of live buying is a separate
                 operator decision gated on the pre-committed shadow evidence. No
                 production behavior changes from this design or its Stage-S
                 implementation."

TESTS:     none — doc-only PR.

NEXT:      codex review → impl PR 1 (lane config + license behind the lane flag, prod
           byte-identity tests) → impl PR 2 (lane wiring + ledger/readout) →
           operator-gated deploy → the lane accrues ON-session evidence → activation
           proposal to the operator when the burden is met.
