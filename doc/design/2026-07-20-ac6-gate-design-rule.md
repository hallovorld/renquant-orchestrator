# AC6 — Gate design rule: every HARD capital-admission gate ships its governed override path

**Status:** RULE — claude draft, codex review. This PR delivers the **canonical
rule** + its **orchestrator-local instance** (the orchestrator PR-template item).
It does **not** by itself complete AC6: full enforcement requires the multi-repo
rollout (§Enforcement) + a shared run-bundle validator. AC6 is **partially met**
(rule defined + one repo wired), not met/enforced fleet-wide.
**Goal:** GOAL-5 P0 AC6.

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
provenance was **not** captured in the run bundle. This rule closes that: when an
override is active for a session, the run bundle records the override's identity,
scope-binding fingerprint, reason, and expiry. A run whose result was shaped by an
override but whose bundle does not name it is an AC6 violation, caught in review.

## Enforcement — current state and multi-repo rollout (revised per review)

**Honest current state:** a checklist item in the *orchestrator* PR template only
applies to orchestrator PRs, and a checklist is *manually attestable* — it does
not itself enforce provenance-in-run-bundle. HARD capital gates commonly land in
**strategy-104, pipeline, execution, and model** repos, so an orchestrator-only
item leaves most gate PRs ungoverned. This PR is therefore the *canonical rule +
orchestrator instance*, and AC6 completes only when the rollout below lands.

**R1 — canonical home (umbrella).** Reference this rule from the umbrella
architecture contract (`RenQuant` `doc/arch/` operating model), so it is the
single source of truth every subrepo points at, not an orchestrator-local doc.
(Follow-up umbrella PR.)

**R2 — every gate-owning repo carries the checklist.** Add the same in-scope-gate
override-path item to the PR template (or CONTRIBUTING) of **renquant-strategy-104,
renquant-pipeline, renquant-execution, renquant-model** (and any repo that can
introduce a hard capital-admission block). One small PR per repo, referencing R1.
Until a repo has it, its gate PRs are governed by reviewer heuristic only (below).

**R3 — provenance as a per-gate acceptance criterion (interim).** Because the
checklist cannot *mechanically* guarantee override provenance lands in the run
bundle, each in-scope gate PR must, until R4 exists, carry that provenance as an
explicit acceptance criterion in its own progress doc (the override's identity /
scope-binding fingerprint / reason / expiry is written to the run bundle, with a
test). This is a gate-by-gate obligation, not a system guarantee yet.

**R4 — mechanical enforcement (the real close).** A shared run-bundle
schema/validator (owned where the bundle schema lives) that *fails* a run whose
result was shaped by an override the bundle does not name, plus a
`contract_findings`-style lint flagging new hard-block sites (a `raise` /
`return []` / `skip_buys`/`sell_only` flip / funnel-zeroing threshold) lacking a
referenced override path. R4 is what turns AC6 from review-checklist to enforced.

**Reviewer heuristic (active now, all repos):** if a diff adds a hard-block site
as above, the reviewer asks for the three-property override path before approving —
this is the stopgap until R2/R4 make it mechanical.

**AC6 done = R1 + R2 across all gate-owning repos + R4 live.** This PR is R0 (rule
+ orchestrator instance).

## Relationship to other GOAL-5 ACs

AC3 (containment protocol) governs *emergency* mutations after the fact; AC6
governs *design-time* so the emergency path is unnecessary. AC4 (transactional
bundles) makes the binding/override survive promote/rollback atomically. Together:
a HARD gate lands only with a governed, expiring, bound, audit-visible way to lift
it.

[[incident-20260716-book-drained-to-cash]] [[goal-5-daily-run-reliability]]
[[check-existing-contract-before-adding-gate]] [[deployed-but-dark-is-not-done]]
