# Modal bounded-run experiment plan (pre-registered, awaiting operator approval)

Date: 2026-07-11
Status: PROPOSAL — no production values change as a result of this document;
Modal API/CLI execution requires separate, explicit operator approval and is
NOT authorized by merging this plan.

## Why this document exists

`#450` originally carried both a proposed set of Modal capacity/cost
parameters AND the claim that a bounded run had validated them. That run
was executed without the operator's explicit agreement to a plan (a
reviewer's suggested experiment design is not operator sign-off) — see
`doc/progress/2026-07-10-modal-capacity-cost-params.md`'s 2026-07-11
addendum for the incident record. All resulting parameter changes were
reverted; `#450`'s code is currently byte-identical to `main`.

Per Codex's request, this document replaces the parameter-change framing
with a **pre-registered experiment plan only** — parameters remain
unchanged until a properly authorized run produces decision-grade evidence
and a *separate* follow-up PR implements the resulting numbers.

## Hypothesis under test

The reconciled per-seed fan-out architecture (`#435`, merged
`086ffe22ac70a28118e7f97090524c22ddbe5858`) changed the Modal worker's unit
of work from "all 3 seeds serially in one pod" to "exactly one
(variant, seed) pair per pod." The current conservative defaults
(`DEFAULT_TIMEOUT_SECONDS=3600`, `DEFAULT_SECONDS_PER_POD_ESTIMATE=5558.0`,
`cost_reasonable` threshold `20.0`, no `max_containers` override) were
carried forward from the OLD architecture's smoke test and have never been
measured against the reconciled one. The hypothesis: per-pod wall time is
lower under the reconciled fan-out (closer to `5558/3`), which would let
the timeout stay conservative while enabling correction of the cost
estimate and a validated concurrency cap.

## Fixed pins (must be recorded verbatim in the run's evidence memo)

- **Code**: exact commit SHA of `main` (or the specific feature branch, if
  the run validates in-flight work) at run time — not "reconciled
  architecture" as a description, the literal SHA.
- **Image**: the Modal image digest actually built and used (Modal image
  layers can drift between builds of the "same" `_BASE_IMAGE` definition if
  any pinned package version resolves differently) — capture via
  `modal.Image` build output, not assumed from source.
- **Volume**: `renquant-sweep-data` (`VOLUME_NAME` in `modal_app.py`) —
  record the Volume's current revision/committed-file-list at run start
  (`modal volume ls`/equivalent) so a later Volume mutation can't silently
  invalidate the run's data-freshness assumption.
- **Region**: the Modal workspace's effective execution region at run time
  (not currently pinned in code — confirm and record the actual value,
  don't assume a default).

## Representative workload and seed/variant matrix

3 variants × 3 seeds = 9 pods, matching the smallest matrix that exercises
real cross-pod Volume-read concurrency without approaching the full sweep
size (the previous, unauthorized run happened to use this same shape —
re-validate it under authorization rather than assuming its numbers are
reusable, since the run's other pins were never verified against this
document's requirements).

## Cold/warm replication plan

At least 3 independent bounded repetitions, not 1:
- 1 repetition from a cold Modal app (no warm containers from a prior run
  within the container idle window).
- >=2 repetitions immediately following (warm-container reuse), to
  characterize the cold-start tax separately from steady-state per-pod
  time.

A single 9-pod run (as the unauthorized run was) cannot distinguish
cold-start variance from steady-state variance — this is the single
biggest gap in the rejected evidence, independent of the authorization
question.

## Control / comparison

Compare each repetition's per-pod wall-clock distribution against the
current conservative estimate (`5558.0s` for the OLD one-pod-three-seeds
shape, i.e. an implied ~1853s/seed ceiling) to confirm the reconciled
per-seed pods are indeed faster, not merely differently distributed.

## Hard spend ceiling and no-live guard

- **Dollar ceiling: OPERATOR TO SET.** This document does not propose a
  number — the standing rule explicitly carves Modal spend out of the
  general "<$10 needs no prior ask" delegation, so the ceiling for this
  specific run is the operator's call, not a default this plan assumes.
  Whatever ceiling is set must be enforced by the run's own preflight
  (`ModalExecutor.preflight`'s `cost_reasonable` gate, evaluated against
  the CURRENT unmodified `20.0` threshold and the projected pod count,
  before dispatch) — the run must abort before dispatch if projected cost
  exceeds the operator-set ceiling, not merely warn.
- **No-live/deploy assertion**: confirm (and if absent, add as a
  pre-run check, in a separate PR, before the run — not invented ad hoc
  during the run) that the Modal execution path cannot reach any live
  broker credential, live strategy config, or production data path — it
  must run exclusively against the sweep bundle's own isolated inputs.

## Raw artifact and billing retention

Every pod's raw stdout/stderr, per-pod wall/queue/cold-start timestamps,
and the exact Modal dashboard billing export (not a formula-estimated
figure) must be retained in a durable evidence memo, keyed by the run's
app ID(s), committed to `doc/progress/` alongside the resulting parameter
PR — not left in a session scratchpad log file only.

## Abort criteria

Abort the run (not just flag in evidence) if, at any point: any pod fails
for a reason other than the deliberately-tested fault class; wall-clock
for any single pod exceeds 2x the current conservative estimate; or
realized cost trajectory (extrapolated from completed pods) would exceed
the operator-set ceiling before all pods finish.

## A priori decision rule

Set `DEFAULT_SECONDS_PER_POD_ESTIMATE` from the observed **p95 (or max, if
the sample is too small for a stable p95 — 9 pods per repetition is not)**
per-pod time across ALL repetitions, not the mean — a raw mean is exactly
what Codex rejected in the unauthorized run's evidence, and is not a safe
basis for a timeout/cost default that production correctness depends on.
Likewise `max_containers` may only move to a new figure that was ACTUALLY
run at that concurrency (a 9-pod run validates a concurrency claim only up
to 9; raising `max_containers` beyond what was exercised, as the
unauthorized run's PR text explicitly and correctly acknowledged for
`max_containers=30`, requires a separate, dedicated future validation at
that concurrency).

## Explicitly out of scope for this document

- No production parameter values change as a result of this plan merging.
- The Modal run itself is a separate, future action requiring its own
  explicit operator approval at execution time — plan approval is not run
  approval.
- Any resulting parameter changes land in a distinct follow-up PR, built
  from this plan's actual evidence memo, reviewed on its own merits.
