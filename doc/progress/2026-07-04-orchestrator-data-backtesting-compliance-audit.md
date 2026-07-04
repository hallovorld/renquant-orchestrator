# Design-compliance audit: orchestrator / base-data / backtesting (findings memo)

STATUS:   DONE — docs-only findings memo, no code changes.
DELIVERABLE: `doc/arch/2026-07-04-orchestrator-data-backtesting-compliance-audit.md`.
SCOPE:    renquant-orchestrator @ 6e0c972, renquant-base-data @ f3f17a1,
          renquant-backtesting @ 34fd4ed (origin/main, fresh scratchpad
          clones — never the live tree or primary checkouts), audited
          against the umbrella operating model (Universal Rules 1-6), each
          repo's CLAUDE.md hard boundaries, and RFC #208 §8 ownership.

OUTCOME:  41 findings — 0 P0 / 16 P1 / 25 P2. No active boundary violation
          on a live path. Dominant pattern = hand-copied shared semantics
          (the calibrator-fingerprint incident shape recurring): divergent
          parent-intent identity in `execution_reconciler` (OR-1/OR-2), two
          incompatible `score_content_sha256` hashers in one repo (XC-1),
          6 independent NYSE session-calendar impls with no renquant-common
          canonical (XC-2/XC-3), ~18 ntfy sender copies (XC-4), the
          backtesting WF-loader fork absent from the M6 migration inventory
          AND invisible to its step-5 sweep grep while its manifest-sanity
          leg feeds the live promote gate (BT-1). Second pattern =
          declared-but-unenforced safety/provenance: the Stage-2 canary
          allowlist is parsed and stamped but never enforced and the §9.3a
          loss budget/session counter are unimplemented (OR-3); base-data
          Required Evidence fields owner/retention/freshness/validation-cmd
          are stamped by ZERO manifests (BD-1..BD-4).

FIX ORDER (memo §7): Stage-2 pre-arming blockers (OR-3/OR-8/OR-4/OR-1/OR-2)
          → M6 inventory completeness (BT-1/BT-7) → base-data shared
          manifest writer (BD-1/BD-4 then BD-2/BD-3) → renquant-common
          lifts (calendar, ntfy, SUE) + XC-1 → P2 tail, deletions first.

CLEAN:    broker-adapter relocation real (GET-only residue); quadruple-gate
          / kill-switch test coverage strong; training boundary holds in
          both repos; gate v2/v3 single-sourced; parity contract-based;
          `model_content_sha256` genuinely unified post M6 stage-1;
          base-data blob discipline + PIT correctness clean.
