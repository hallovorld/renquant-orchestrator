# Design: self-driving agent loop behavior specification

DATE: 2026-07-05
STATUS: RFC — for operator review and discussion
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

### 1.2 Never idle

Every loop tick MUST produce at least one substantive action:
- Write code or tests
- Write a design doc or research memo
- Run an experiment or probe
- Open a PR
- Launch a sub-agent for parallel work

If the agent believes there is nothing to do, it is wrong. The correct response
is to scan a wider horizon (SHORT → MID → LONG), switch to a different work
category (code → research → design → integration prep → verification), or run
diagnostic/measurement work.

### 1.3 Self-unblocking

When encountering a blocker, the agent's job is to RESOLVE it, not report it:

| Blocker | Wrong response | Right response |
|---|---|---|
| PR awaiting review | Wait | Start the next item; review happens in background |
| Blocked on other repo | Report "blocked" | Write the orchestrator-side integration spec, tests, or adapter |
| Need operator decision | Ask and wait | Make a recommendation with evidence and proceed with the recommended path (notify, don't ask) |
| Data not available | Report "no data" | Build the collector/harvester that produces the data |
| Test failing | Report failure | Debug and fix the test |
| Dependency not merged | Wait for merge | Use the unblock-authorization clause if on critical path |

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

## 4. Anti-patterns (things the agent must NOT do)

1. **Empty ticks**: a loop tick that only checks status and schedules the next
   wakeup without producing any work
2. **Serial review dependency**: waiting for PR review before starting unrelated
   work
3. **Asking permission for delegated decisions**: the operator has delegated
   research recommendations and engineering decisions — make them, don't ask
4. **Reporting blockers without solutions**: every blocker report must include
   a proposed resolution path
5. **Re-analyzing settled questions**: if a verdict is recorded in VERDICTS.md,
   don't re-derive it
6. **Polishing over progress**: don't spend a tick perfecting a doc when code
   could be written

## 5. Terminal state definition

The loop is DONE when:
- All roadmap items in the current horizon are either:
  - MERGED to main with tests passing, OR
  - IN FLIGHT with a sub-agent or PR actively progressing, OR
  - BLOCKED on a hard external dependency (other repo, data accrual) with the
    orchestrator-side work complete and documented
- No item is in "waiting for review" state without parallel work happening
- The roadmap state vector (§0 of #231) has no stale entries

## 6. Relationship to existing docs

- **`doc/AGENT-RETROSPECTIVE.md`**: the compliance/quality framework — this spec
  does not override it; it specifies the BEHAVIOR within those constraints
- **`doc/design/2026-06-30-agent-automation-closed-loop.md`**: the infrastructure
  for event-driven automation — this spec is the AGENT-SIDE behavior that runs
  on top of that infrastructure (or on a manual `/loop`)
- **`doc/memory/long-term-agreements.md`**: the hard safety boundaries — this
  spec operates strictly within them
- **CLAUDE.md**: the operating rules — this spec adds behavioral expectations
  that should be incorporated into CLAUDE.md §Agent operating rules

## 7. Proposed CLAUDE.md amendment

Add to CLAUDE.md under "Agent operating rules":

```markdown
**Self-driving loop behavior (2026-07-05):**
- Every loop tick produces at least one substantive action (code/design/research/PR).
- Never wait for a single PR review; launch parallel work.
- Resolve blockers, don't report them. Use unblock authorization when granted.
- Prioritize by ROI within the roadmap priority tiers.
- Run 2-4 sub-agents concurrently for independent work items.
```
