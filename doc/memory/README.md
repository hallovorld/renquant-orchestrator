# Agent externalised memory — three tiers (read every session)

The agent has **no persistent executive across turns** (`../AGENT-RETROSPECTIVE.md` §1).
This directory **is** that executive, split by *how long each item lives* and *who may
change it*, so volatile short-term state can never silently overwrite a binding agreement.

## Structure (file vs folder is chosen per tier's nature)

| tier | path | shape | why this shape |
|---|---|---|---|
| **LONG** | [`long-term-agreements.md`](long-term-agreements.md) | **single file** | a short binding list Codex loads **whole** to check violations; single file = easiest to enforce + read at once |
| **MID** | [`mid-term/`](mid-term/) | **folder, one file per workstream** + [`_north-star.md`](mid-term/_north-star.md) | parallel workstreams open/close/redirect independently; Codex checks alignment per-workstream |
| **SHORT** | [`short-term-state.md`](short-term-state.md) | **single file (snapshot)** | a current snapshot, overwritten each session; a folder would wrongly turn it into a log |

## Update rules (who · when · how · enforcement)

### LONG — `long-term-agreements.md`
- **Who:** the agent may only **transcribe an explicit operator decision** (cite where the
  operator said it). The agent may **not** add/change/remove an agreement on its own judgment.
- **When:** the operator makes a standing decision, veto, or reversal.
- **How:** **append-only** — add a row; never silently edit an existing agreement's meaning;
  a reversal is a new line marking the old one *superseded* + the new state (kept, not deleted).
- **Codex enforcement:** rejects a PR that (a) **violates** any agreement, or (b) **adds/edits**
  an agreement without a **cited operator decision**.

### MID — `mid-term/` (one file per workstream + `_north-star.md`)
- **Who:** the agent **proposes** (in a PR); the operator **confirms** by review/merge.
- **When:** a workstream opens, closes, or changes direction; the north star changes.
- **How:** each workstream file = `STATUS · GOAL · NEXT · EVIDENCE` (truth-tagged). Closing a
  workstream sets `STATUS: done`; do not delete it.
- **Codex enforcement:** checks each PR **aligns** with MID, or the PR **updates MID with a
  justification** for the change.

### SHORT — `short-term-state.md`
- **Who:** the agent, **freely**.
- **When:** every session start, and after any task that changes state or yields a finding.
- **How:** **OVERWRITE** the snapshot (do not append → never a log). Every factual line carries
  `[VERIFIED <how>]` or `[GUESS]`. Keep it short.
- **Codex enforcement:** non-binding; Codex only checks it **does not contradict LONG** and that
  claims are **tagged**.

## Cross-tier rules
1. **Precedence:** on any conflict, **LONG > MID > SHORT**. If SHORT contradicts LONG, SHORT is wrong.
2. **Read order each session:** LONG → MID → SHORT, before acting.
3. **Promotion:** a SHORT item that becomes a standing rule → propose adding to LONG (needs an
   operator decision); a SHORT item that becomes direction → open a MID workstream; a finished MID
   workstream's durable outcome → a LONG agreement and/or a `renquant-system-feature-map.md` entry.

`../AGENT-STATE.md` is the front-door pointer to this directory.
