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
