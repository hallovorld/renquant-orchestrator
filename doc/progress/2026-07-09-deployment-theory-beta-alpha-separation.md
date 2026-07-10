# Deployment theory: beta/alpha separation — research

**Date**: 2026-07-09
**Status**: Research memo r3 (theory + tuning-subset results; EXPLORATORY —
nothing herein authorizes a behavior change)

## Bottom line

The 65% cash drag is a CATEGORY error (beta exposure conditional on alpha
confidence) — but the tuning-subset experiment (149 sessions, full
stateful/tax/integer conventions) REFUTED this memo's own vol-targeting prior
(voltarget −3.8..−5.1% vs fully-deployed naive +4.7%; nothing significant,
PBO 0.61) and surfaced the structural finding: deployment is hard-ceilinged by
`admitted breadth × per-name cap` (median 4 names × 12% = 48%; even the 95%-
target arm achieved only 52% deployed). The two real levers — per-name cap and
admission breadth — become the locked D6 Phase-2 treatment grid; the L1
candidate simplifies to regime-ceiling-riding. Cap raise = operator risk
decision after confirmatory evidence. The committed freeze record is relabeled
EXPLORATORY and its eval subset RETIRED; a fresh freeze follows the amended
protocol.

## Changes

- `doc/research/2026-07-09-deployment-theory-beta-alpha-separation.md` — the
  memo: thesis, four theory pillars, proposed L1 revision, 6-arm experiment
  design (tuning subset, nested selection), decision asks for codex

## Discipline notes

- Empirical results land in this PR before merge (tuning subset only; eval
  subset reserved for the post-approval confirmatory run)
- The earlier config-only "bridge" proposal is audited by the `kelly_raw` arm
  rather than asserted
