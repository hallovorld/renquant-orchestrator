# M6 pre-deploy model bundle consistency check

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: M6 (one shared content-fingerprint impl), S11 (durable hotfix)

## What

Commits `scripts/check_model_bundle_consistency.py` — a pre-deploy offline
self-consistency checker for strategy-104 model bundles. Catches the four
contract failures that hit production on 2026-06-23 BEFORE deploy:

1. **Config fingerprint mismatch**: config hash in artifact != live config hash
2. **Watchlist count mismatch**: artifact trained on N tickers, config has M
3. **Calibrator/scorer fingerprint mismatch**: the triple-impl bug (3 independent
   model_content_sha256 implementations hash different field sets)
4. **WF gate metadata absent**: artifact missing wf_gate_metadata entirely

## Why

The 2026-06-23 XGB deploy hit all four contracts ONE BY ONE, each patched by
hand in production. Every one is checkable offline. This script runs all four
against a candidate config + resolved artifacts and reports deploy-readiness:
exit 0 = deploy-ready, exit 1 = contract failure, exit 2 = cannot evaluate.

Reuses the SAME authorities the live preflight uses (config fingerprint from
renquant_common, scorer fingerprint from the panel scorer, calibrator binding
from calibrator metadata) so a PASS here guarantees the runtime P-* gates pass.

## Tests

7 tests: consistent bundle passes, config fp mismatch, watchlist mismatch,
calibrator/scorer mismatch, wf metadata absent, wf metadata failed,
wf metadata missing numerics.
