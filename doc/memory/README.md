# Agent externalised memory — SPEC (机制 · SOP · 文档)

Three-layer definition of the memory structure. At session start, read **this spec once**
(the rules), then the live tiers **LONG → MID → SHORT** (the state), before acting.

---

## 1. 机制 / DESIGN — why it is built this way

**Problem:** the agent has no persistent executive across turns; in-context promises do
not bind (`../AGENT-RETROSPECTIVE.md` §1). **Solution:** externalise the executive into
files, split by two axes — *how long an item lives* × *who may change it*:

| tier | lifespan | change authority | shape | rationale for the shape |
|---|---|---|---|---|
| **LONG** | indefinite, binding | **operator only** (agent transcribes) | single file | a short list Codex loads **whole** to check violations |
| **MID** | weeks–months | agent **proposes**, operator **confirms** | folder, 1 file/workstream | parallel streams open/close/redirect independently |
| **SHORT** | this session | agent, **freely** | single snapshot file | disposable; a folder would become a forbidden log |

**Design invariants (the guarantees):**
- **Precedence LONG > MID > SHORT** — volatile state can never overwrite a binding agreement.
- **Enforcement is external** (Codex review per PR), never agent self-discipline.
- **Truth tags** `[VERIFIED <how>]` / `[GUESS]` on every factual line in MID/SHORT.
- **Shape follows tier nature** (binding→file, parallel→folder, snapshot→file).

---

## 2. SOP / IMPLEMENTATION — operating procedures

Each: **TRIGGER → STEPS → OUTPUT → ENFORCED BY.**

- **SOP-R (session start, READ).** *Trigger:* new session/task. *Steps:* read LONG→MID→SHORT;
  restate the binding constraints relevant to the task before acting. *Output:* none.
  *Enforced by:* Codex catches resulting violations downstream.
- **SOP-S (state change, WRITE SHORT).** *Trigger:* any finding/state change. *Steps:*
  **overwrite** `short-term-state.md` (never append); tag each line; keep it short.
  *Output:* refreshed snapshot. *Enforced by:* Codex checks no-contradiction-with-LONG + tags.
- **SOP-M (direction change, WRITE MID).** *Trigger:* a workstream opens/closes/redirects, or
  the north star changes. *Steps:* in a PR, edit/add the `mid-term/<workstream>.md`
  (STATUS·GOAL·NEXT·EVIDENCE); set `done` to close (don't delete). *Output:* updated MID file.
  *Enforced by:* Codex checks PR alignment, or the PR justifies the change.
- **SOP-L (operator decision, WRITE LONG).** *Trigger:* operator states a standing
  decision/veto/reversal. *Steps:* **append** a row to `long-term-agreements.md` citing where
  the operator said it; never edit an old agreement's meaning; a reversal is a new
  "superseded" row. The agent may **not** author a LONG item on its own judgment.
  *Output:* appended agreement. *Enforced by:* Codex rejects a LONG change with no cited operator decision.
- **SOP-P (promotion).** SHORT item → standing rule ⇒ propose to LONG (operator decision, then
  SOP-L). SHORT item → direction ⇒ open a MID workstream (SOP-M).
- **SOP-C (conflict).** SHORT contradicts LONG ⇒ SHORT is wrong; correct it immediately.
- **SOP-PR (every PR).** *Steps:* include `doc/progress/<date>-<slug>.md` (C5); update the
  touched tier per the SOPs above; PR description mirrors the progress doc. *Enforced by:*
  Codex review against `../AGENT-RETROSPECTIVE.md` §7.1 — approval is the merge gate.

---

## 3. 文档 / OP — artifacts & templates

**File map:**
```
doc/memory/
├── README.md                  ← this SPEC (机制 · SOP · 文档)
├── long-term-agreements.md    LONG — binding ledger (SOP-L)
├── mid-term/                   MID  — folder
│   ├── _north-star.md
│   └── <workstream>.md         (SOP-M)
└── short-term-state.md         SHORT — snapshot (SOP-S)
doc/progress/<date>-<slug>.md   per-PR record (SOP-PR / C5)
```

**Templates (op):**
- **LONG row:** `| # | agreement | since |` (append-only).
- **MID workstream:** `STATUS · GOAL · NEXT · EVIDENCE [· CONSTRAINT]`, lines truth-tagged.
- **SHORT snapshot:** short sections of tagged facts + a "next bounded action".
- **Progress doc:** `../AGENT-RETROSPECTIVE.md` §4(c).
- **Status / evidence block:** `../AGENT-RETROSPECTIVE.md` §4(a)/(b).

`../AGENT-STATE.md` is the front-door pointer to this directory.
