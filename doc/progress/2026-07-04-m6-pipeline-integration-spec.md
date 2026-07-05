# M6 stage-2: pipeline integration specification

DATE: 2026-07-04
TYPE: Design specification (no code changes)

## What

Authored `doc/design/2026-07-04-m6-pipeline-integration-spec.md` -- the
pipeline integration spec for the M6 stage-2 fingerprint migration.

Documents the as-built state of step-1 (version-dispatched verification code)
across all five pipeline files changed (sites 1-4, 9 from the parent design
doc), the config key contract, the dispatch logic at both fail-closed checks,
PanelScorer.load dual-stamp resolution, test fixture coverage, and the
remaining integration checklist for steps 2-5.

## Why

The parent design doc (`2026-07-03-m6-stage2-fingerprint-migration.md`)
describes the full five-step sequence but does not enumerate the specific
pipeline-side code changes with file paths, line numbers, and function
signatures. The pipeline integration spec fills that gap -- same role as the
S5 decision-ledger pipeline integration spec relative to S5's orchestrator
modules.

Step-1 code is implemented; steps 2-5 remain gated. This spec is the
reference for reviewing the step-1 implementation and for planning the
remaining steps.

## Status

Design only -- no code changes in this PR.

## Round 2 (Codex review)

Codex blocked: the spec named pipeline files/line-ranges/functions without
recording which exact pipeline commit that describes, so the doc would drift
into a non-auditable narrative as soon as the pipeline pin moved.

Fixed: added a "Version boundary" section anchoring the spec to pipeline
commit `0dfc070cec82bb27089909f28eb764730ccdd844` (`renquant-pipeline` v0.4.0)
-- verified via `git log --oneline -- <file>` that this is the single commit
introducing/last-touching all five files section 1 documents. Also recorded
the orchestrator-run pin expectation: `renquant-pipeline>=0.1.0` is an open
range, not a strict lock (this repo runs against the sibling checkout via
`PYTHONPATH`, not an installed pinned package) -- so there's no
machine-checkable lock to point at, only the operator-checkable "does your
local pipeline checkout's file history resolve to this commit" test recorded
in the new section. Added a re-anchoring caveat: this snapshot goes stale the
moment a later pipeline commit touches any of the five files, and must be
re-verified before being treated as current at that point.
