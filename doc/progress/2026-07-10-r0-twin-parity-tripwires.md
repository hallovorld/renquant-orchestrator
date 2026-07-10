# R0 twin-parity tripwires (#454 remediation stage R0)

STATUS:    in-progress (PR open, awaiting Codex review)
WHAT:      Mechanical drift alarms for the KNOWN duplicated-contract (T3)
           instances: `scripts/check_twin_parity.py` + committed pin
           manifest `data/twin_parity_manifest.json` +
           `tests/test_twin_parity.py`. Zero behavior change — R0 only
           makes silent twin drift VISIBLE before any R1–R6 migration
           moves code.
WHY/DIR:   #454 registry (design:
           `doc/design/2026-07-10-architecture-compliance-registry.md`
           T3 + R0 + §5.1; evidence:
           `doc/research/evidence/arch_audit_2026_07/` audit C §1/§3,
           audit B §3/§4). "A contract that exists in two repos without a
           mechanical parity/drift test is a latent production incident"
           — the fingerprint-triple-impl / `self._config` incident class.
EVIDENCE:  [VERIFIED] all 14 live checks pass against the real sibling
           checkouts (2026-07-10); alerts.py + ibkr_broker.py byte-identical,
           4 broker twins diverged and now sha-pinned; 23/23 new tests pass;
           full `make test` green (see PR).
NEXT:      Codex review + merge; remaining R0 items from the roadmap
           (boundary AST tests for base-data/artifacts live in THOSE repos;
           unknown-key warning counter is a pipeline-side item) are separate
           PRs in their owning repos.

## Bottom line

Every T3 duplicated-contract instance the audit catalogued now has a tripwire
that fails `make test` on the deploy machine if EITHER side changes without a
deliberate, reviewed manifest re-pin:

1. **Umbrella `live/` ↔ renquant-execution twins** (audit C §1.1, C1-a):
   - `alerts.py`, `ibkr_broker.py` — byte-identical today ("only by luck" per
     the audit); now asserted byte-equal. A lockstep change to both sides
     still passes (parity preserved); a one-sided hotfix fails.
   - `broker.py`, `alpaca_broker.py`, `paper_broker.py`,
     `broker_readonly.py`/`readonly_broker.py` — KNOWN diverged; the CURRENT
     divergence is pinned (sha256 of each side in
     `data/twin_parity_manifest.json`). Any further change on either side
     fails until the manifest is regenerated
     (`--write-manifest`) and the diff reviewed in the same PR. No more
     silent drift; the manifest update is the deliberate review act.
2. **`MIN_FRACTIONAL_NOTIONAL_USD`** (audit C1-c): AST-parsed from execution
   `broker.py` and pipeline `kernel/sizing.py`, asserted equal to each other
   AND to the manifest pin (1.0) — a lockstep change still requires the
   review act.
3. **`compute_parent_intent_id` ×2** (audit B §3): function source sha-pinned
   per side (pipeline `intraday_decisioning.py`, execution
   `order_state_machine.py`), plus a cross-side equality assertion on the
   behavior-critical `_FIELD_SEP` constant both implementations hash with
   (the function-source sha alone would not catch a `_FIELD_SEP` edit).
4. **Tax-convention trio** (audit B §4, pipeline-internal): rotation
   `tax_drag` defaults 0.50/0.32 (×3 call sites each), QP bridge 0.30/0.15,
   selection flat 0.30 (×2) snapshot in the manifest. R6 unifies; this pin
   makes further silent drift fail — including NEW hand-copied call sites
   (counts are pinned too, because a new site with today's value is exactly
   the duplication class the audit flags).

## Runner semantics + known limitation

Sibling repos resolve per the RENQUANT_REPOS.md sibling-checkout convention
(same derivation as `scripts/mirror_drift_inventory.py`), overridable via
`RENQUANT_SIBLINGS_ROOT` / `--siblings-root`. Absent siblings make the
affected check groups SKIP with a loud "twin parity NOT verified here"
message (exit 0) — never a silent green. Two enforcement environments:

- **Orchestrator GitHub CI** (ci.yml) checks out renquant-execution +
  renquant-pipeline @ main → the constant/function/tax pins ARE enforced at
  merge time (#454 §5.1 twin-drift CI). The umbrella `RenQuant` is NOT
  checked out in CI, so the `live/`-twin checks (the audit's HIGH-latent
  item) SKIP there — CI green does NOT certify umbrella-twin parity.
- **Deploy machine `make test`** has all siblings → ALL checks run. This is
  authoritative, and it is exactly where the umbrella drift matters: the
  live path executes from the deploy machine's umbrella checkout ("merged
  is not deployed").

A CI-vs-deploy-machine disagreement (siblings @ main vs @ deployed pin) is
the T1 evidence-vs-live lag made visible — resolve by syncing pins, not by
loosening the pin. `--strict-missing` turns SKIP into FAIL for environments
where siblings MUST exist.

## Files

- `scripts/check_twin_parity.py` — checker + `--write-manifest` re-pin CLI
  (spec of WHAT is checked lives in code; pinned STATE lives in the manifest)
- `data/twin_parity_manifest.json` — committed pins (same placement
  convention as `data/c1_drift_baseline.json`)
- `tests/test_twin_parity.py` — 22 synthetic-fixture tests (every
  pass/fail/skip path; run everywhere incl. CI) + 1 live integration test
  (THE tripwire — granular: enforces whatever siblings exist)

## Non-overlap with existing guards

`scripts/check_mirror_drift.py` (C1 campaign) polices the pipeline↔umbrella
`kernel/` mirror; this R0 checker covers the DIFFERENT twin sets the #454
audit added (live/-broker twins across the execution boundary, cross-repo
constants/functions, pipeline-internal tax trio). No duplicated coverage;
both follow the same sibling-resolution + committed-baseline conventions.
