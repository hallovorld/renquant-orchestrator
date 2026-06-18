# Agent externalised memory — three tiers (read every session)

The agent has **no persistent executive across turns** (`../AGENT-RETROSPECTIVE.md` §1).
This directory **is** that executive, split by *how long it lives* and *who may change
it*, so the volatile short-term state can never silently overwrite a binding agreement.

| tier | file | holds | who may change it | update cadence | enforcement |
|---|---|---|---|---|---|
| **LONG** | [`long-term-agreements.md`](long-term-agreements.md) | binding constraints / vetoes / decisions | **operator only** (explicit decision) | rarely | Codex **rejects** any PR that violates it (C4) |
| **MID** | [`mid-term-plan.md`](mid-term-plan.md) | north star, direction, open workstreams | agent proposes, operator confirms | per roadmap change | Codex checks PRs **align** with it, or the PR justifies a change |
| **SHORT** | [`short-term-state.md`](short-term-state.md) | current state, latest findings, next bounded action | agent, freely | every session | non-binding; tagged `[VERIFIED]`/`[GUESS]` |

## Rules

1. **Precedence:** on any conflict, **LONG > MID > SHORT**. If short-term state
   contradicts a long-term agreement, the short-term state is *wrong* and is corrected.
2. **Read order each session:** LONG → MID → SHORT, before acting.
3. **Truth tags:** every factual line in MID/SHORT carries `[VERIFIED <how>]` or
   `[GUESS]`. An unverified line may not be the basis of a decision (`AGENT-RETROSPECTIVE.md` §4b).
4. **Append-only spirit for LONG:** agreements are added; a *reversal* requires an
   explicit operator decision recorded in the same file — never silently dropped.
5. **SHORT is disposable:** rewrite it freely; do not let it accrete into a log. If a
   short-term item becomes a standing rule, promote it to LONG (with operator sign-off);
   if it becomes direction, promote it to MID.

`AGENT-STATE.md` (one level up) is the front-door pointer to this directory.
