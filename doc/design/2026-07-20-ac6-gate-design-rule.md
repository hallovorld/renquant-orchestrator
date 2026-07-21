# AC6 — Gate design rule: every HARD capital-admission gate ships its governed override path

**Status:** RULE — claude draft, codex review. This PR delivers the
**provisional, orchestrator-local rule** below + wires it into this repo's PR
template. It is **not** the canonical rule while its only source lives here:
the canonical cross-repo source is `RenQuant` `doc/arch/subrepo-operating-model.md`
Universal Rule 7, added by companion umbrella PR
[`hallovorld/RenQuant#522`](https://github.com/hallovorld/RenQuant/pull/522)
(open, pending review — not yet merged as of this revision). Once that PR
merges, this document becomes the *detail* (rationale, scope, reviewer
heuristic, rollout state) that the umbrella entry points at; until then,
this file is the rule's only source and should be read as provisional.
This PR does **not** by itself complete AC6: full enforcement requires the
multi-repo rollout (§Enforcement) + a shared run-bundle validator, neither of
which exists yet. AC6 is **partially met** (rule drafted, one repo's PR
template wired), not met/enforced fleet-wide.
**Goal:** GOAL-5 P0 AC6. **Rollout tracking:** `renquant-orchestrator`#564.

## Why this rule exists

Every fail-closed gate we add to protect capital is also a way to **silently
starve the book**. The 07-16 incident drained the live account to 94% cash for
three days because a HARD diagnostic-only admission gate had **no governed way to
override it** — so the only "override" available was undocumented hand-surgery on
live files ([[incident-20260716-book-drained-to-cash]],
[[check-existing-contract-before-adding-gate]]). A HARD gate without a *governed*
override path is not a safety feature; it is a latent outage with no off-switch.

This rule makes the override path a **design-time requirement**, reviewed on the
same PR that introduces the gate — not something improvised during an incident.

## Scope — what counts as a "HARD capital-admission gate"

Any change that can, on its own, take a name (or the whole book) from *tradeable*
to *not-tradeable* by **raising an exception / returning zero candidates / forcing
sell-only / blocking a buy**, where the block is not itself a market/economic
decision. Examples: a fingerprint-binding assert, a freshness/staleness gate, a
data-availability gate, an admission threshold, a vol/risk gate whose breach
hard-blocks rather than sizes down. Pure sizing/economic ranking is **out of
scope** (it decides *how much*, not *whether the system may act at all*).

## The rule

> A PR that adds or tightens a HARD capital-admission gate MUST document, in its
> `doc/progress/<date>-<slug>.md` (or a linked design doc), a **governed override
> path** with all three properties:
>
> 1. **Identity** — *who* may lift/relax the gate: a named authenticated identity
>    or role, and through *what reviewed surface* (a config field, a launchd
>    manifest entry, a governed flag) — never "whoever can edit the live tree."
> 2. **Expiry** — the override carries an explicit **expiry or restore condition**
>    ("until pin X is deployed", "until the retrain of Y lands"), not an open-ended
>    "temporary." An expiry that passes must **auto-alarm** (ties to the
>    CONTAINMENT PROTOCOL + the run-surface drift scan).
> 3. **Binding** — the override is bound to the *specific* gate/artifact/state it
>    relaxes (by fingerprint/id), so it cannot silently widen to other names or
>    survive the artifact it was scoped to; and its **provenance is recorded in
>    the run bundle** for that session (who/when/why/expiry), so an audit of any
>    run shows the override was in effect.

If a gate genuinely must be un-overridable (a true kill-switch), the PR states
that explicitly and says what the operator's recovery action is instead — silence
is not allowed.

## Provenance-in-run-bundle sub-requirement

The 07-16 adversarial re-review (memory: #203 SOUND + MED) found override
provenance was **not** captured in the run bundle. **This PR does not close
that gap** — it adds no schema, producer, or validator. It requires that each
*future* gate PR close it under R3 (below): the override's identity,
scope-binding fingerprint, reason, and expiry must be written to the run
bundle for that gate, with a test proving it, until R4 makes it mechanical.
Until R4 lands, "a run whose result was shaped by an override but whose
bundle does not name it" is caught only by human review, not by any
automated check.

**What already exists, and what R4 has to reconcile (checked 2026-07-21):**
there is no single "the run bundle" in this codebase today — two different,
disconnected things share the name:
- `renquant_common.contracts.schemas.LiveRunBundle` +
  `validate_live_run_bundle()` — a real Pydantic v2 schema with a
  `model_validator` that mechanically rejects malformed input (wrong
  `schema_version`, missing state source). It is wired into this repo's
  `native_live_bundle.py` / `bridge_live_bundle.py` (native-vs-bridge parity
  path only). It has **no override-provenance field today**.
- `PersistDailyRunBundleTask` in `daily.py` — writes the daily orchestration
  `run_bundle.json` (`decision_trace`, `order_intents`, `execution_audit`,
  etc., `"schema_version": 1`) as a **plain dict with no schema validation at
  all** — it is never passed through `LiveRunBundle` or any other validator.
- (A third, unrelated "run-bundle" concept — `RunBundleProvenance` in
  `bundle_seal.py` — records *artifact publication* provenance for the AC4
  transactional-bundle RFC, not gate-override provenance. Do not conflate it
  with this rule's provenance requirement.)

R4 therefore is not "build a validator from scratch": the mechanical pattern
(Pydantic, `model_validator`, raise-on-violation) already exists in
`renquant-common`. R4's actual work is (a) deciding whether override
provenance belongs on `LiveRunBundle`, on a new schema for the daily
`run_bundle.json`, or both, and (b) actually wiring `PersistDailyRunBundleTask`
through schema validation, which it does not go through today.

## Enforcement — current state and multi-repo rollout (revised per review)

**Honest current state:** a checklist item in the *orchestrator* PR template only
applies to orchestrator PRs, and a checklist is *manually attestable* — it does
not itself enforce provenance-in-run-bundle. This PR is the *provisional,
orchestrator-local instance* of the rule (R0), and AC6 completes only when the
rollout below lands.

**R1 — canonical home (umbrella).** Reference this rule from the umbrella
architecture contract as Universal Rule 7 — companion PR
[`hallovorld/RenQuant#522`](https://github.com/hallovorld/RenQuant/pull/522)
(open, pending review as of this revision). Once merged, that entry is the
single cross-repo source of truth every subrepo points at; this document
stays the detail doc it references.

**R2 — every gate-owning repo carries the checklist.** Grep-grounded scan
(2026-07-21, shallow clones, pattern `admission|_veto|sell_only|hard.?gate|
fail.?closed`) rather than a guess at which repos "commonly" land gates:

| Repo | Matching files | In scope? |
|---|---|---|
| `renquant-pipeline` | 85 | Yes — primary owner of hard-gate/admission code (e.g. `panel_scoring.py`, `decision_ledger.py`, `bundle_contract.py`). Highest priority. |
| `renquant-execution` | 10 | Yes — order-level hard blocks (e.g. `order_state_machine.py`, `alpaca_broker.py`). |
| `renquant-strategy-104` | 0 (code) | Yes, but config-only — 0 gate-code hits (~8 Python files, mostly config-drift tests); it holds the threshold *config values* (`configs/strategy_config*.json`) pipeline gates read, so a config PR that tightens a threshold is in scope even with no matching code pattern. |
| `renquant-model` | 7 | Uncertain — hits are mostly training/research-time (`fee_gate.py`, `oos_ic_export.py`), not obviously live capital admission. Verify case-by-case before wiring; may be out of scope. |

Add the same in-scope-gate override-path item to the PR template (or
CONTRIBUTING) of each in-scope repo above, one small PR per repo, referencing
R1. Until a repo has it, its gate PRs are governed by reviewer heuristic only
(below). Tracked in `renquant-orchestrator`#564.

**R3 — provenance as a per-gate acceptance criterion (interim).** Because the
checklist cannot *mechanically* guarantee override provenance lands in the run
bundle, each in-scope gate PR must, until R4 exists, carry that provenance as an
explicit acceptance criterion in its own progress doc (the override's identity /
scope-binding fingerprint / reason / expiry is written to the run bundle, with a
test). This is a gate-by-gate obligation, not a system guarantee yet.

**R4 — mechanical enforcement (the real close).** Extend the existing
Pydantic-validated `renquant_common.contracts.schemas.LiveRunBundle` (and/or a
new equivalent schema for the daily `run_bundle.json`, which today bypasses
validation entirely — see §Provenance-in-run-bundle) with a required
override-provenance field, and actually wire `PersistDailyRunBundleTask`
through it so a run whose bundle omits required provenance *fails to
persist* rather than merely looking wrong in review. Pair with a
`contract_findings`-style lint flagging new hard-block sites (a `raise` /
`return []` / `skip_buys`/`sell_only` flip / funnel-zeroing threshold) lacking a
referenced override path. R4 is what turns AC6 from review-checklist to enforced.

**Reviewer heuristic (active now, all repos):** if a diff adds a hard-block site
as above, the reviewer asks for the three-property override path before approving —
this is the stopgap until R2/R4 make it mechanical.

**AC6 done = R1 + R2 across all in-scope gate-owning repos + R4 live.** This PR
is R0 (the provisional rule + orchestrator-local instance) only.

## Relationship to other GOAL-5 ACs

AC3 (containment protocol) governs *emergency* mutations after the fact; AC6
governs *design-time* so the emergency path is unnecessary. AC4 (transactional
bundles) makes the binding/override survive promote/rollback atomically. Together:
a HARD gate lands only with a governed, expiring, bound, audit-visible way to lift
it.

[[incident-20260716-book-drained-to-cash]] [[goal-5-daily-run-reliability]]
[[check-existing-contract-before-adding-gate]] [[deployed-but-dark-is-not-done]]
