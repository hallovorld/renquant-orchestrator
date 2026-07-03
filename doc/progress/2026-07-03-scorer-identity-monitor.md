# Progress — run-over-run scorer-identity diff alarm (#274 monitoring gap)

Date: 2026-07-03
Scope: the monitoring fix named by the 06-26 diagnosis
(`doc/research/2026-07-03-raw-jump-0626-diagnosis.md` §4-ii, PR #274): the
silent 06-26 prod model rollback ran undetected for 7 days because the only
alarm on the surface (PSI drift) is saturated — 247/247 rows CRITICAL since
birth, 8 near-identical incidents in 10 days, zero information. Identity
fields exist in every run bundle; nothing diffed them run-over-run. Now
something does.

## What

`src/renquant_orchestrator/scorer_identity_monitor.py` — observe-only,
strictly read-only (runs DB `mode=ro`; artifacts only read and hashed):

- Extracts a per-lane identity tuple from consecutive canonical run bundles
  (`pipeline_runs.run_bundle_json`): `prod_panel` = stamped artifact sha +
  `panel_contract.details.trained_date` + booster CONTENT hash (sha256 of the
  artifact's `booster_raw_json`, resolved by matching the stamped file sha
  against prod/staging/rollback copies — re-stamps collapse to the same
  booster family, the diagnosis's artifact archaeology); `calibrator`;
  each `shadow_models[i]`.
- Any lane change between consecutive runs must be legitimized by a recorded
  promote/rollback event on the boundary window (filename-dated staging /
  rollback markers under `artifacts/prod`, dated weekly-promote logs, shadow
  promotion receipts; dates from FILENAMES, never mtime — the prod dir is
  bulk-touched). Unexplained ⇒ CRITICAL, exit 1, ntfy with BOTH identities;
  explained ⇒ INFO, exit 0. Shadow-only changes accept only receipts; an
  explained prod promote legitimizes the same-boundary lane swap atomically.
- Separate WARN (exit 2): served `trained_date` over the 28d freshness
  directive (operator 2026-06-30 / RFC #210). One-directional per the #423
  doctrine — trained_date proves STALE, never certifies fresh. Complementary
  to `model_freshness_monitor` (disk artifacts, data-cutoff-keyed): this keys
  on what a run actually SERVED, which is how the 05-18 model hid.
- Fail-closed: missing DB / <2 usable runs / bundle without a stamped panel
  hash ⇒ CRITICAL.
- Saturation immunity by construction: edge-triggered on CHANGE; a stable
  identity — however old — never fires it. An unexplained boundary re-pages
  until it ages out of `--lookback-days` (5) or a record appears.
- Backfill: `--backfill N` replays the last N bundles into an identity
  timeline. Against prod it reproduces the diagnosis exactly: one UNEXPLAINED
  boundary at `2026-06-25-live-6c3aa3fa → 2026-06-26-live-14e45d8d`
  (prod_panel `04d7a381…/2026-06-21` → `5ce63326…/2026-05-18`, calibrator
  swapped too, zero events in window); the 06-22 operator promotion reads
  explained (staging + rollback + logs on 06-21/22/23).

Ops (files only, NOT installed — landing is an operator action):
`ops/renquant104/run_scorer_identity_monitor.sh` +
`com.renquant.rq104-scorer-identity.plist` (14:30 PT Mon–Fri, after the 14:06
daily-full) + README. Wrapper alerts separately if the monitor itself crashes
before reaching a verdict.

Tests: `tests/test_scorer_identity_monitor.py` — 35 cases: unexplained-change
fires with both identities; explained-by-promote passes; family matching
(calibration records don't excuse panel swaps); events outside window don't
explain; shadow receipt / atomic-swap logic; age>28d WARN (+ missing
trained_date warns, never passes); WARN never masks CRITICAL; missing
DB/bundle/panel-hash fail closed; saturation immunity + boundary age-out +
window-edge diff base; booster resolution (and non-resolution is never a
phantom change); filename-vs-mtime; ntfy gating; exit codes; backfill
timeline; sim runs excluded.

## Verified against prod (read-only)

- `--backfill 460`: timeline shows the 06-26 event as the only UNEXPLAINED
  prod-panel boundary (output in the PR body).
- default check (5d lookback): WARN exit 2 — served model trained 2026-05-18,
  45d old (#210 breach, the diagnosis's flagged violation); the two 07-01
  calibrator changes read explained via the 07-01 monthly rollback marker.
- `--lookback-days 9`: CRITICAL exit 1 on the 06-26 boundary — the alarm
  would have paged same-day had it existed.

## Known granularity limits (documented in-module)

- Events are calendar-day matched (rollback markers and promote logs are
  dated, not timestamped): a manual swap on the same day as genuine promote
  activity of the same family reads explained. The 07-01 manual calibrator
  re-stamp is an instance (masked by the same-day monthly rollback marker).
- Pre-receipt-era shadow churn (06-22) backfills as unexplained — honest:
  those were unrecorded operator actions; receipts (#419) now exist.
