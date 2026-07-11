# 2026-07-11 — session outage monitor (funnel_integrity.v1 / data_availability.v1 consumer)

## Bottom line

New orchestrator monitor `outage_monitor.py` (+ `renquant-orchestrator outage-monitor`
CLI): reads a run bundle's `funnel_integrity` + `data_availability` blocks (pipeline
#186/#187, merged 2026-07-11) and renders the operator-facing ntfy page with the
**OUTAGE / DEGRADED / NO-TRADE / TRADE** title-tag vocabulary — so a 07-08-class
engineering outage can never again be reported as a normal quiet no-trade.
**Wire-ready but DARK**: invoked by no scheduled job; daily-automation wiring is a
separate landing (machine-landing, ask-first).

## Ownership context

- Pipeline #186 (`FunnelIntegrityTask`) and #187 (`DataAvailabilityGateTask`)
  publish versioned verdict blocks and deliberately emit no notification —
  #186's earlier `notification_headline()` helper was removed at Codex's request
  as a boundary violation.
- Codex closed the umbrella alert PR (RenQuant#463) ruling alert rendering
  belongs to the repo that owns notification delivery. This module is that
  orchestrator-side consumer; it owns the headline/rendering contract.

## Rendering contract (owned here)

| Source verdict | Title tag |
|---|---|
| funnel `STRUCTURAL_BLOCK` | `OUTAGE` (priority 5) |
| funnel `DEGRADED` | `DEGRADED` (priority 4) |
| funnel `ECONOMIC_NO_TRADE` | `NO-TRADE` (priority 3) |
| funnel `ECONOMIC_TRADE` | `TRADE` (priority 3) |
| data `BLOCKED` | `OUTAGE` |
| data `DEGRADED` | `DEGRADED` |
| data `AVAILABLE` | (no contribution) |

Combined tag = worst of both blocks. Body: leads with the universe-collapse
`admitted/watchlist` + per-cause counts (from the `universe_admission_collapse`
finding's `evidence.top_rejection_reasons` — insert-at-0 so ntfy truncation can
never hide it, same discipline as umbrella #463), then other fired invariants,
funnel counts, data-availability axis failures (axis, policy, reason, age/coverage),
undeclared axes, and any block-level errors.

## Behavior and safety

- Read-only, fail-soft: missing/partial blocks degrade to a recorded
  `missing_blocks` note (with a best-effort hint from the `counters` integer
  mirrors, which the pipeline stamps even before bundle-level block stamping
  lands); the monitor never invents a session verdict — both blocks absent means
  no title tag and no page.
- ntfy via the canonical `renquant_common.notify.send` (honors
  `RENQUANT_NO_NOTIFY`); `--quiet` suppresses, `--only-alerts` restricts paging
  to OUTAGE/DEGRADED for an eventual scheduled wiring.
- Exit codes: 2 OUTAGE, 1 DEGRADED, 0 clean, 3 unreadable bundle /
  (with `--require-blocks`) neither block present.
- No trading-behavior change of any kind; no broker/live-state/production-path
  access.

## Artifacts

- `src/renquant_orchestrator/outage_monitor.py` — report builder, block
  summarizers, tag combiner, bundle discovery (`find_latest_bundle`), alert
  seam, CLI.
- `src/renquant_orchestrator/cli.py` — `outage-monitor` subcommand
  (REMAINDER pass-through, house pattern).
- `data/strategy_snapshot.json` — regenerated per the documented M9 workflow
  (new module + subcommand).
- `tests/test_outage_monitor.py` — 31 tests.

## Evidence

- `tests/test_outage_monitor.py`: **31 passed** — includes the exact 07-08
  outage shape (STRUCTURAL_BLOCK, 4/145 admitted,
  `stale_76d_limit_60=133 / no_artifact=9` cause counts, DEGRADED
  admission-coverage axis), clean TRADE/NO-TRADE sessions, data-BLOCKED
  escalation, tag-combination matrix, missing-block fail-soft + counters hint,
  alert gating (quiet / only-alerts / default), bundle discovery, CLI exit
  codes. `[VERIFIED]`
- Full suite in the isolated worktree: **3528 passed, 9 failed, 3 skipped** —
  the 9 failures (`test_shadow_ab_daily_script.py` ×8, `test_twin_parity.py` ×1)
  are byte-identical to the clean `origin/main` baseline run in a second
  untouched worktree (9 failed, 3497 passed) — pre-existing
  environment/manifest-dependent failures, unrelated to this change.
  `[VERIFIED]`
- Work done in an isolated worktree; no git operations in the live tree or
  primary checkouts; no production paths touched. `[VERIFIED]`

## Follow-ups (not this PR)

- Umbrella/orchestrator bundle builders: stamp `ctx.funnel_integrity` /
  `ctx.data_availability` into the persisted run bundle (pipeline #186's noted
  gap — `build_run_bundle` does not reference them yet). This monitor already
  tolerates their absence and reads the counter mirrors as a hint.
- Daily-automation wiring (scheduled invocation after the daily run) — a
  separate landing requiring operator go-ahead.
- Render the F4 `override_degraded` disclosure block here once that design
  amendment (separate design PR) is approved and stamped.
