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
measured against the reconciled one. The hypothesis: per-pod wall time
under the reconciled fan-out is lower than the retained `5558.0s` baseline
(dividing that figure by 3 is NOT a valid predicted value — see Control /
comparison below — the hypothesis is directional only, not a specific
number), which would let the timeout stay conservative while enabling
correction of the cost estimate and a validated concurrency cap.

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

A shape (3 variants × 3 seeds = 9 pods per repetition) is not itself a
reproducible workload — a concrete run proposal instantiating this plan
MUST pre-register, before operator approval, all of the following as
literal recorded values (not descriptions):

- The exact variant identifiers and their full config fingerprints (not
  "3 variants" — the specific config hash of each).
- The exact seed integer values used (not "3 seeds" — the literal
  integers).
- The exact bundle/artifact content fingerprint the run dispatches against.
- The exact data interval (start/end dates) the workload covers.

Region, image digest, and Volume revision (see Fixed pins above) are
REQUIRED recorded fields for the same reason: an unresolved or unknown
value in any of these fields is an abort condition before dispatch, not a
detail to fill in after the fact in the evidence memo. A run whose pins
were not fully resolved and recorded before dispatch produces no
decision-grade evidence regardless of what it measures.

## Cold/warm replication plan

At least 3 independent bounded repetitions, not 1. "Cold" and "warm" are
defined OPERATIONALLY from each pod's own observed telemetry, never from
run order alone (run order does not guarantee a given repetition actually
got cold or warm containers — Modal's scale-to-zero/idle-window behavior
can produce a cold container on a later repetition or a warm one on an
earlier one):
- **Cold**: container-start/image-pull latency present in the pod's own
  timing breakdown (non-trivial time between dispatch and workload start
  attributable to container provisioning, not queueing).
- **Warm**: container-reuse signal from Modal's execution metadata (or
  near-zero provisioning latency with queue time as the only measurable
  gap) — not merely "ran after repetition 1."
Each repetition's pods must be individually classified cold/warm from this
telemetry, not assumed from the repetition's position in the sequence.

## Control / comparison

Compare each repetition's per-pod wall-clock distribution DIRECTLY against
the retained conservative baseline, `DEFAULT_SECONDS_PER_POD_ESTIMATE =
5558.0` (the OLD architecture's one-pod-three-seeds serial time). Do not
derive an implied per-seed figure by dividing this by 3 — that ignores
fixed per-pod overhead (image pull, Volume mount, cold start) that does
not scale down linearly with fewer seeds per pod, which is exactly the
reasoning the current code's own comment already gives for why 5558.0 is
conservative rather than optimistic. Report per-pod component timing
(queue time, provisioning time, workload time) separately wherever the
telemetry makes that decomposition available, rather than only a single
wall-clock total per pod.

## Hard spend ceiling and no-live guard

- **BLOCKING PREREQUISITE — the ceiling is not enforceable today.**
  `ModalExecutor.preflight` (`modal_executor.py`) only knows the fixed
  `$20` `cost_reasonable` literal; there is no parameter through which an
  operator-approved cap (which may be lower) can be supplied or enforced.
  Before ANY run under this plan, a separate implementation PR must add an
  explicit, required operator-approved-cap input to `preflight`, enforced
  as `min(existing fixed safety gate, operator-approved cap)` — never the
  fixed gate alone — with its own tests proving (a) the tighter of the two
  bounds always governs and (b) an unresolved/missing cap fails the
  preflight closed rather than silently falling back to the fixed gate.
  That implementation PR is reviewed and merged on its own merits before
  any Modal call under this plan; it is not authorized by this design
  document merging.
- **Dollar ceiling value: OPERATOR TO SET**, once the above prerequisite
  exists. This document does not propose a number — the standing rule
  explicitly carves Modal spend out of the general "<$10 needs no prior
  ask" delegation, so the ceiling for this specific run is the operator's
  call.
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

With the minimum 3-repetition × 9-pod plan above (27 pod-samples total), a
p95 estimate carries too much sampling uncertainty to set a durable safety
default — do not use p95 at this sample size. Instead, pre-register ONE of
the following before the run (not chosen post-hoc from whichever looks
better):
- **Max plus margin**: `DEFAULT_SECONDS_PER_POD_ESTIMATE` = the single
  slowest observed pod across all repetitions × an explicit, pre-registered
  safety margin (for example 1.3×) — stated as a rule, not a number, until
  real data exists.
- **OR** increase the sample size to a level that supports a stated p95
  confidence/tolerance procedure (pre-register the target sample size and
  the specific tolerance-interval method before running), if a full
  distributional estimate is preferred over max-plus-margin.

Whichever rule is pre-registered governs; do not use the observed mean
under any circumstance — a raw mean is exactly what Codex rejected in the
unauthorized run's evidence, and is not a safe basis for a timeout/cost
default that production correctness depends on. Likewise `max_containers`
may only move to a new figure that was ACTUALLY run at that concurrency (a
9-pod run validates a concurrency claim only up to 9; raising
`max_containers` beyond what was exercised, as the unauthorized run's PR
text explicitly and correctly acknowledged for `max_containers=30`,
requires a separate, dedicated future validation at that concurrency).

## Explicitly out of scope for this document

- No production parameter values change as a result of this plan merging.
- The spend-ceiling enforcement prerequisite (see Hard spend ceiling above)
  is separate implementation work, reviewed and merged on its own merits;
  this design document does not implement or authorize it.
- The Modal run itself is a separate, future action requiring its own
  explicit operator approval at execution time — plan approval is not run
  approval, and is not authorized by the spend-ceiling prerequisite
  merging either.
- Any resulting parameter changes land in a distinct follow-up PR, built
  from this plan's actual evidence memo, reviewed on its own merits.
