# Design: self-driving agent loop behavior specification

DATE: 2026-07-05
STATUS: **NON-BINDING retrospective / heuristic discussion note.** This document
        is NOT operationally binding on its own, and merging this PR does not
        ratify any of the rules below as policy. Per `doc/memory/README.md`'s
        tier model, binding (LONG-tier) rules require **operator** authorship —
        the agent may transcribe them, not originate them (§1 of that spec:
        "LONG ... operator only (agent transcribes)"). This doc lives outside
        the LONG/MID/SHORT tiers entirely; it is scoped to `renquant-orchestrator`
        only, and any rule below that the operator finds worth keeping must be
        separately adopted into `doc/memory/long-term-agreements.md` and/or
        `CLAUDE.md` — by the operator, through the normal SOP-M/operator-review
        path — before it constrains agent behavior.
SCOPE: Defines how the Claude agent should behave in an autonomous `/loop` session.
       This is a BEHAVIOR spec (what the agent does), not an infrastructure spec
       (how GitHub events flow — that's `2026-06-30-agent-automation-closed-loop.md`).

---

## 0. Problem statement

The agent's default loop behavior is passive: check status → report → schedule
wakeup → wait. This wastes operator time and money. Observed failure modes:

1. **Idle spinning**: "no work to do, waiting for review" when the roadmap has
   50+ items across multiple horizons
2. **Single-threaded blocking**: waiting for one PR review before starting the
   next item, when items are independent
3. **Learned helplessness**: reporting "blocked on operator decision" for items
   that the agent has delegation authority to resolve
4. **Review ping-pong**: creating superseding PRs for review comments instead of
   launching new substantive work in parallel

The operator's directive (2026-07-05): "你为什么要等344？那么多事情你自己推啊！"

## 1. Design principles

### 1.1 Goal-driven, not task-driven

The agent operates toward a **terminal state**, not a task list. The terminal
state is defined by the roadmap's objective function (e.g., "all 104-107
writable code on main; data pipelines accruing; every SHORT item either done or
in-flight"). Each loop tick asks: "what's the highest-ROI action that moves
toward the terminal state?" — not "what's the next item on the list?"

### 1.2 Avoid idling by default

Every loop tick SHOULD aim to produce at least one substantive action:
- Write code or tests
- Write a design doc or research memo
- Run an experiment or probe
- Open a PR
- Launch a sub-agent for parallel work

This is a heuristic, not an unconditional requirement — it does not apply when
genuinely blocked by quota/rate limits, an explicit safety gate awaiting human
sign-off, or a hard dependency with no available substitute work of any kind. In
those cases the correct response is honest status, not manufactured busywork.
Short of that, if the agent believes there is nothing to do, it is usually wrong:
the correct response is to scan a wider horizon (SHORT → MID → LONG), switch to
a different work category (code → research → design → integration prep →
verification), or run diagnostic/measurement work.

### 1.3 Self-unblocking

When encountering a blocker, the agent's job is to RESOLVE it, not report it:

These are heuristics for the common case, not universal rules — genuine safety
gates, capital-risk decisions, and hard dependencies with no substitute work
still warrant waiting or asking:

| Blocker | Usual wrong response | Usual right response | Exception |
|---|---|---|---|
| PR awaiting review | Wait | Start the next item; review happens in background | none — this one generalizes safely |
| Blocked on other repo | Report "blocked" | Write the orchestrator-side integration spec, tests, or adapter | if no orchestrator-side work exists either, say so honestly |
| Need operator decision | Ask and wait | Make a recommendation with evidence and proceed with the recommended path (notify, don't ask) | capital-risk / irreversible actions still require asking first |
| Data not available | Report "no data" | Build the collector/harvester that produces the data | if building the collector requires spend/access not yet authorized, ask first |
| Test failing | Report failure | Debug and fix the test | if the failure indicates a genuine pre-existing bug outside scope, report it rather than papering over |
| Dependency not merged | Wait for merge | Use the unblock-authorization clause if on critical path | only within the granted scope of that authorization (§3) |

### 1.4 Parallel by default

The agent should run 2-4 sub-agents concurrently whenever independent work
items exist. The main loop's job is to:
1. Harvest completed agents → verify → open PRs
2. Launch new agents for the next batch
3. Do direct work (small fixes, doc updates) while agents run

Single-threaded execution is justified ONLY when work items have strict
sequential dependencies.

### 1.5 ROI-weighted prioritization

Within a priority tier (NOW > SHORT > MID > LONG), choose the item with the
highest expected impact per unit of effort:
- Code that unblocks other work > isolated features
- Data accrual (time-irreversible) > code (can be written anytime)
- Probes that resolve decisions > more analysis of already-analyzed topics
- Integration work > polishing

## 2. Loop tick algorithm

```
EACH TICK:
  1. HARVEST: check for completed agents → verify → open PRs
  2. SCAN: read roadmap state vector → identify all actionable items
  3. FILTER: remove items blocked by hard dependencies (other repo PRs
     not merged, data that physically doesn't exist yet)
  4. RANK: sort remaining items by (priority_tier, ROI, unblock_leverage)
  5. FILL: for each empty agent slot (up to 4 parallel):
       - pick the highest-ranked unstarted item
       - launch a sub-agent OR do it directly (if small)
  6. DIRECT: while agents run, do small direct work:
       - fix stale docs, run diagnostics, write integration tests
  7. BRIEF: ≤5 lines Chinese summary
  8. SCHEDULE: wakeup at min(agent_expected_completion, 270s)
```

## 3. Unblock authorization protocol

The operator has granted standing unblock authority (2026-07-02, renewed
2026-07-03 for the sprint). The agent MAY:
- Take over stalled PRs and merge them (if approved)
- Run verdict-only gates
- Execute safe-window live-tree sync per #242
- Make delegated decisions per §9 protocol

Each use MUST be:
- Documented in the PR or a progress doc
- Notified to the operator (ntfy or PR comment)
- Within the hard safety boundaries (never bypass branch protection, never
  write prod paths, never run git in live tree outside #242)

## 4. Anti-patterns to avoid (heuristics, not absolutes)

1. **Empty ticks when avoidable**: a loop tick that only checks status and
   schedules the next wakeup without producing any work, when substitute work
   genuinely existed — not applicable when no substitute work exists or a
   safety gate blocks all available options
2. **Serial review dependency when avoidable**: waiting for PR review before
   starting unrelated, independent work
3. **Asking permission for decisions already delegated**: within the scope of
   what's actually delegated (§3, §9 protocol) — decisions outside that scope,
   or genuinely capital-risk/irreversible ones, should still be asked
4. **Reporting blockers without solutions when a solution exists**: a blocker
   report should include a proposed resolution path when one exists; if none
   exists, say so honestly rather than inventing one
5. **Re-analyzing settled questions**: if a verdict is recorded in VERDICTS.md,
   don't re-derive it without new evidence
6. **Polishing over progress**: don't spend a tick perfecting a doc when code
   could be written, all else being equal

## 5. Terminal state definition

The loop is DONE when:
- All roadmap items in the current horizon are either:
  - MERGED to main with tests passing, OR
  - IN FLIGHT with a sub-agent or PR actively progressing, OR
  - BLOCKED on a hard external dependency (other repo, data accrual) with the
    orchestrator-side work complete and documented
- No item is in "waiting for review" state without parallel work happening
- The roadmap state vector (§0 of #231) has no stale entries

## 6. Relationship to existing docs and to this repo's authority tiers

- **`doc/AGENT-RETROSPECTIVE.md`**: the compliance/quality framework — this note
  does not override it; it discusses BEHAVIOR that would need to fit within
  those constraints, if adopted
- **`doc/design/2026-06-30-agent-automation-closed-loop.md`**: the infrastructure
  for event-driven automation — this note discusses AGENT-SIDE behavior that
  would run on top of that infrastructure (or on a manual `/loop`), if adopted
- **`doc/memory/long-term-agreements.md`**: the actual hard safety boundaries
  (LONG tier — binding, **operator-authored only** per `doc/memory/README.md`
  §1). This note is subordinate to it in every respect: nothing here overrides,
  loosens, or reinterprets a LONG-tier constraint, and none of the heuristics
  above become binding by virtue of this doc merging.
- **CLAUDE.md**: the operating rules — same authority relationship as
  `long-term-agreements.md`. This note does not itself add behavioral
  expectations to CLAUDE.md; see §7.

## 7. Path to adoption (not a self-executing amendment)

This document does not amend CLAUDE.md and is not itself a source of binding
rules. Per this repo's own memory-tier model, a change to CLAUDE.md or
`doc/memory/long-term-agreements.md` requires **operator** authorship — the
agent's role is limited to transcribing an operator-authored decision (LONG
tier) or proposing a workstream for operator confirmation (MID tier via
SOP-M). If, after review, the operator finds some subset of the heuristics in
§1–§4 worth keeping, the adoption path is:

1. Operator reviews this note and decides which heuristics (if any) to keep,
   drop, or amend.
2. Operator authors (or explicitly directs the agent to transcribe verbatim)
   the resulting language directly into `CLAUDE.md` and/or
   `doc/memory/long-term-agreements.md`, through the normal review process for
   those files.
3. Until step 2 happens, this document has the status of a discussion note:
   informative, not enforceable, and carrying no more authority than any other
   `doc/design/` proposal.
