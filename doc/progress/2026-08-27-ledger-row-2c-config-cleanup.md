# LONG-ledger row 2c — one-time authority for the dangling-walkforward removal (strategy-104#102)

STATUS: ledger-only PR, row-2a/2b precedent: the authority row lands on
orchestrator `main` BEFORE the config PR merges.

## The decision being recorded

Operator authorization 2026-08-26, verbatim **「授权 row 2c」** (item 3 of the
five-item authorization batch, Claude operator session), for exactly
**renquant-strategy-104#102**: remove the dangling `walkforward.manifest_path`
key from the eight config carriers its diff touches.

## Why a row is required at all (per codex review of #102)

The change is behaviorally equivalent — the key is read nowhere
[VERIFIED: code-path analysis in #102] — but NOT fingerprint-inert:
`strategy_config.json` bytes change, so run-bundle and provenance-gate
fingerprints of strategy config change intentionally. Row 2 makes production
configs read-only with no no-op exception; hence this narrow, single-use,
PR-named row.

## Scope

Exactly the eight carriers in #102's diff; the golden config never carried
the key (test-covered only). No other key, file, or PR. Expires on merge of
#102. Deployment = the normal ordered umbrella pin advance + runtime sync as
separate reviewed steps.
