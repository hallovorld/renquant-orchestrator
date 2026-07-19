# F-7 canonical provenance integration — RFC (design only)

STATUS: RFC drafted (design review required before any implementation).
WHAT: `doc/design/2026-07-18-f7-canonical-provenance-integration.md` — the
authoritative integration design for wiring the F-7 canonical-provenance
registry (built + merged in artifacts#29) into production. Task #55.
WHY/DIR: artifacts#29 landed the registry side "fails closed until the
integration exists"; verified across all repos that the registry is entirely
UNWIRED (0 producer call sites, 0 validator call sites) and that the F-7
parent design doc it references does not exist on any main. This RFC fills
that gap: producer (umbrella) writes run_intent + registers publication;
orchestrator daily-run admission supplies CanonicalPublicationSnapshot +
calls validate_artifact_manifest — introduced behind a GOVERNED rollout
(opt-in `RQ_REQUIRE_CANONICAL_PROVENANCE` → dated
`CANONICAL_PROVENANCE_REQUIRED_AFTER` window, consumer suites in review,
never a flag-day — the artifacts#24 lesson), coordinated with AC4 P2 on the
shared hydration surface, and deployment-gated by the artifacts pin-gate.
EVIDENCE: design-only; no code, no production path, no live artifact touched.
SCOPE: orchestrator doc/design + doc/progress only; producer-hook portion is
umbrella-owned (named in the RFC, not implemented). No LONG-ledger change.
OPEN QUESTION (operator): sequence the admission gate AFTER the AC4 P1-seal
cutover (recommended) vs independently on the flat pair now.
