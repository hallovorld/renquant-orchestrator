# 2026-07-18 — shadow-ab per-epoch/per-role paired-session telemetry

STATUS: built + tested (dark until manifests exist — safe by construction)

WHAT: `src/renquant_orchestrator/shadow_ab_epoch_telemetry.py` — the v5
prereg (RenQuant#494) §4.7 rule 4 "mechanical checkability" counters:
`n_paired_sessions` per epoch and per role (pilot / terminal / burned),
derived read-only from recorded harness state (deduplicated session
records + the epoch freeze registry: archived `epoch<N>-freeze-*` scopes +
the live root freeze) and COMMITTED registration/activation manifest
files. Safe default: **no registration manifest → every session is
burned**; and a session whose epoch attribution is not PROVEN by a freeze
fingerprint match (location-only fallback) can never carry a pilot/terminal
role. Strict postdating of the registration commit uses the sealed
`decision_snapshot.as_of` when present, else the conservative 00:00 UTC
reading (a registration-day session without a sealed as-of burns).
Exposure is the harness's EXISTING reporting surface: the runner attaches
`epoch_role_counters` to the returned session payload (printed into
`session_<date>.json` by the daily wrapper) and writes a
`shadow_ab_epoch_role_counters.json` sidecar next to the counters file,
derived AFTER the session record lands so the current session is included;
derivation failures are recorded, never raised (telemetry is not
load-bearing for the session verdict; the module import itself sits inside
the try). New read-only audit CLI:
`renquant-orchestrator shadow-ab-epoch-report`. The daily wrapper forwards
optional `RENQUANT_SHADOW_AB_REGISTRATION_MANIFEST` /
`RENQUANT_SHADOW_AB_ACTIVATION_MANIFEST` (fail-closed if set but missing)
plus the `*_SHA256` binding pins (fail-closed if set without the manifest).

REVIEW FIXES (Codex, both 2026-07-18 reviews):
- **telemetry_status fail-closed stamping** — every successful report
  stamps `telemetry_status: "complete"` only after the per-epoch/per-role
  buckets re-reconcile against per-session role assignments
  (`counts_reconciled`); the runner's recorded derivation-error payload
  stamps `telemetry_status: "unavailable"`. Contract: the activation
  validator MUST require `complete` + reconciled counts — no partial/error
  report may support the >=40-pilot condition. (The full activation
  validator itself belongs to the activation-commit work.)
- **Immutable manifest binding** — a path is mutable, so: a supplied
  registration manifest must carry `source_repository` + `source_commit`
  (or `pilot_registration_commit`) and, when referencing an external
  burned-sessions manifest, a `burned_sessions_manifest_sha256` the loaded
  raw bytes must hash to; an activation manifest must additionally carry
  `registration_manifest_sha256` binding the exact registration content;
  callers can pin either file with `--registration-manifest-sha256` /
  `--activation-manifest-sha256` (wrapper env `*_SHA256`). Actual digests
  are recorded in the report's `manifest_bindings` block. Any resolve or
  verify failure raises — no report, all sessions stay burned, activation
  ineligible.
- **M9 baseline regenerated** — `scripts/generate_strategy_snapshot.py
  --update` for the new CLI subcommand + module (the earlier claim that
  `test_snapshot_not_stale` was pre-existing was WRONG — it was this PR's
  own regression; corrected).
- **Branch provenance** — rebuilt from current `main` as a single
  hallovorld-authored commit, no co-author/session trailers.

WHY/DIR: §4.7 requires the ≥40-pilot prerequisite and every hygiene
exclusion to be auditable at activation from recorded manifests alone. The
legacy root counter is epoch-blind — it demonstrably continued across the
epoch-2→3 refreeze (attempted 1→2 across worlds), which is exactly the
cross-epoch pooling rule 2 forbids. Role boundaries deliberately come ONLY
from committed manifests (registration: `epoch_id`, `registered_at`,
`burned_sessions[_manifest]`; activation: `epoch_id`, `activated_at`;
activation without registration, or a differing epoch, is rejected — §4.7
two-stage start + rule 2). The burned-manifest format matches the PART-A
enumeration (`RenQuant doc/experiments/g1-pilot/burned-sessions-manifest.json`,
`sessions[].session_date/epoch_id`).

TESTS: `tests/test_shadow_ab_epoch_telemetry.py` — 34 (safe default;
strict postdating incl. the as-of-less registration-day case; cross-epoch
burn; burned-list precedence incl. relative-path manifest + malformed
fail-closed; activation pilot/terminal split + two-stage/same-epoch
rejections; printed-copy/bundle dedup vs distinct same-date attempts;
freeze-fingerprint vs location attribution, unproven-world-never-pilot;
runner surface exposure + failure-recorded-not-raised with the
`unavailable` stamp; telemetry_status complete + reconciled; manifest
bindings recorded; missing-provenance / missing-commitment /
digest-mismatch / stale-activation-binding / pin-without-path all fail
closed; CLI print/write + malformed-manifest + pinned-digest-mismatch
rejections). Full suite after the snapshot regen: `test_snapshot_not_stale`
GREEN (it was this PR's own regression, now fixed); the one remaining
failure `test_live_twin_parity_manifest_current` is the pre-existing
environment-dependent one (twin file absent in scratch checkouts),
reproduced on pristine main.

NEXT: at pilot registration, commit the registration manifest (with
`source_repository`/commit + the `burned_sessions_manifest_sha256`
commitment to the PART-A burned manifest) and set the env vars INCLUDING
the `*_SHA256` binding pins in the shadow-ab plist batch (operator landing
step); the report then flips from all-burned to counting pilot sessions
with zero code change. The activation-commit work must implement the
validator that requires `telemetry_status == "complete"` + reconciled
counts before the >=40 condition can be evaluated.
