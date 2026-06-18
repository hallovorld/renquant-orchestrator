# AGENT STATE — front door to the three-tier externalised memory

> The agent has **no persistent executive across turns** (`AGENT-RETROSPECTIVE.md` §1).
> The externalised executive is the **[`memory/`](memory/) directory**, split into three
> tiers by how long each lives and who may change it. Read all three every session,
> in order **LONG → MID → SHORT**, before acting.

| tier | file | holds | enforcement |
|---|---|---|---|
| **LONG** | [`memory/long-term-agreements.md`](memory/long-term-agreements.md) | binding constraints / vetoes / decisions | Codex **rejects** PRs that violate it |
| **MID** | [`memory/mid-term-plan.md`](memory/mid-term-plan.md) | north star, direction, open workstreams | Codex checks PRs **align** or justify a change |
| **SHORT** | [`memory/short-term-state.md`](memory/short-term-state.md) | current state, findings, next bounded action | non-binding; tagged `[VERIFIED]`/`[GUESS]` |

Protocol, precedence (LONG > MID > SHORT), and update cadence per tier:
[`memory/README.md`](memory/README.md).
