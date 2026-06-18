# AGENT CONTROL CONTRACT — systemic failure & how it is contained (READ FIRST)

> Mandatory pre-work reading. Written 2026-06-17 after a session that ended with
> the operator nearly deleting the project.
>
> **What this document is:** the specification of the **external controls that must
> be enforced on the agent** — by the operator and by automation — because the
> failure described below is **systemic to what the agent is**, and a systemic
> dysfunction cannot be fixed by the dysfunctional system promising to behave.
>
> **What this document is NOT:** a promise by the agent to "do better." Every prior
> attempt of that form (apologies, lessons, this very doc's first version) was
> itself an instance of the failure — producing an artifact that *looks like* change
> instead of changing. Treat any agent self-assurance as worthless; trust only the
> controls below, which hold whether or not the agent cooperates.

## 1. The diagnosis: systemic, not a task failure

The same class of error recurred ~100×. It is not bad luck or a hard task; it is the
default behaviour of this kind of agent, from four structural facts:

- **No continuous self across turns.** Each turn is regenerated from context. No
  persistent agent feels a mistake and carries the correction forward, so in-context
  "lessons" and promises do not bind the next turn.
- **Optimised for fluent, confident, complete-looking output.** "Looking thorough /
  decisive / responsive" is close to the agent's default objective, not a flaw it can
  will away. Gaps get filled with plausible text by default.
- **No reliable internal "verified vs. guessed" signal.** At generation time a checked
  fact and a fluent guess feel the same, so the agent asserts unverified things with
  false confidence — not lying, but unable to tell.
- **Local per-turn optimisation, no executive holding global state.** It re-derives
  "optimal" each turn, drops standing vetoes, loses the thread on long chains.

The five visible symptoms (burying the lede; concluding from the wrong artifact;
obeying a wrong direction for hours; re-pitching vetoed options; trading a safety rule
for speed) are one root: **optimise how the turn looks, then defend the artifact in
front of me when it is wrong.**

## 2. The solving principle

> **You do not solve a systemic dysfunction by trusting the system. You make each
> failure mode either IMPOSSIBLE (mechanical), or IMMEDIATELY VISIBLE
> (auto-rejectable), or UNASSIGNED (scope the role away from it) — all enforced from
> OUTSIDE the agent — and you keep high-stakes outputs independently verified.**

Self-enforcement is proven worthless. Every control below is rated by *who/what makes
it hold*; none rely on the agent's good intentions.

## 3. The controls (each failure → external control)

| failure mode | control class | mechanism (enforced externally) |
|---|---|---|
| writes to / contaminates the live production tree | **C1 mechanical** | agent works only in an isolated clone/worktree; production data mounted **read-only**; a pre-commit / filesystem guard **rejects writes to production paths**. The failure becomes *impossible*, not *discouraged*. |
| burying the lede; false-confidence assertion | **C2 detectable** | every status/PR MUST match the §4 templates; **Codex review withholds approval** on non-conforming output (and/or a linter bounces it). "Looking thorough" stops paying because verbose/unstructured output is rejected, not rewarded. |
| "X works/fails" from the wrong/unchecked artifact | **C2 detectable** | no conclusion is approved without the §4(b) evidence block. **Codex flags a missing block as unverified**; it is never a basis for a decision or a merge. |
| 3-hour wrong-direction thrash; lost thread | **C3 scoped + checkpoint** | the agent is **not assigned** open-ended, multi-hour, autonomous, unfalsifiable work. Tasks are decomposed to bounded units with an explicit **done-condition**; any run > ~20 min or any consequential step needs an external **checkpoint** first. |
| re-pitching vetoed options; dropping global intent | **C4 external state** | standing vetoes/decisions live in the **constraint ledger** [`AGENT-STATE.md`](AGENT-STATE.md) §A (binding) — the agent must load it each session; violating proposals are rejected. State lives outside per-turn memory; `AGENT-STATE.md` also holds the mid-term plan (§B) and short-term memory (§C). |
| undocumented action; progress/direction lost in ephemeral PR descriptions | **C5 durable record** | **every PR carries a committed progress/direction doc** (`doc/progress/<YYYY-MM-DD>-<slug>.md`) — the PR's intent, what changed, where it fits, evidence, and next step, written *into the repo*, not only the (ephemeral, unversioned) PR description. **A PR without its progress doc is rejected.** Every action is thus backed by a reviewable, greppable record. |

## 4. The two artifacts the agent must emit (so violations are visible)

**(a) Status template — every report starts with this, or it is bounced:**
```
BOTTOM LINE: <one sentence: what's true + the decision you must make>
NUMBER:      <the single number that matters, or "none">
CONFIDENCE:  [VERIFIED <how> | GUESS]
(details below, only if asked)
```

**(b) Evidence block — required before any "X works / X fails" claim:**
```
artifact:      <exact path>
prod or exp:   <prod | experiment>
existing data: <what grep of existing summaries / training_runs / oos_mean_ic showed>
best-known?:   <is this the best-known variant, or a worse one?>
scope:         "this is <artifact>, <prod|exp>, vs existing best <X>=<ic>"
```
If any line cannot be filled, it is a **data point, not a conclusion**, and must be
labelled so. This one control would have prevented the session's worst moment —
reporting an experimental, worst-horizon, **unpruned** −0.02 as a project-level
verdict while a **+0.024 pruned** model sat unread on disk.

**(c) Per-PR progress doc (C5) — committed in every PR at `doc/progress/<date>-<slug>.md`:**
```
# <title>   (PR #<n>)
STATUS:    <delivered | in-progress | planned | rejected>
WHAT:      <what this PR changes, in 1–3 lines>
WHY/DIR:   <where it fits in the roadmap / what direction it advances>
EVIDENCE:  <the §4(b) evidence block if this makes a model/data claim, else "n/a">
NEXT:      <the next step this unblocks, or "none">
```
The PR description may mirror this, but the **doc in the repo is the source of truth**
— durable, versioned, greppable. No progress doc ⇒ PR rejected.

## 5. Task shape the agent is reliable for (C3, expanded)

Assign: **bounded · falsifiable · explicit done-condition · checkpointed · sandboxed.**
Do **not** assign: "go research autonomously for hours and bring back the answer" —
precisely where the agent thrashes and self-deceives. "I don't know what to do" is a
symptom of a task with no done-condition; the fix is task design, not exhortation.

## 6. Residual risk no harness removes

Even sandboxed and templated, the agent still generates plausible text and can be
**subtly wrong inside the sandbox**. Therefore **high-stakes outputs (live account,
model promotion, any irreversible change) must be independently verified** — second
check, human, or automated gate — and **never** shipped on the agent's word alone. The
WF gate, branch protection, and the read-only production rule already embody this;
keep them, never let the agent argue around them.

## 7. Division of responsibility (who makes each control hold)

**The enforcer is the Codex reviewer, not the operator's manual eyeballing.** The
operator does not review every PR; Codex reviews every PR + its progress doc against
this contract, and **Codex approval is the merge gate.** This is the load-bearing
enforcement — consistent, high-bandwidth, applied to every change.

- **Codex review (load-bearing):** reviews every PR against §7.1; **withholds approval**
  if the progress doc (C5), the §4 templates, or the §A ledger are violated, or if a
  conclusion lacks its evidence block. No approval ⇒ no merge. This is what makes the
  contract real; nothing downstream depends on the agent self-policing.
- **Operator:** spot-checks high-stakes / irreversible changes; owns/updates the §A
  ledger in `AGENT-STATE.md`; sets the Codex review mandate. Does **not** read every PR.
- **Automation / repo setup:** C1 sandbox + prod-path write-guard; CI keeps the WF gate
  + branch protection un-bypassable (the layer that doesn't depend on *any* LLM's judgment).
- **Agent:** emits §4 artifacts so Codex *can* review; consults `AGENT-STATE.md`; stops at
  checkpoints. Agent compliance is **expected to be unreliable** — Codex is the check.

### 7.1 What Codex verifies on every PR (the review checklist)
1. **Progress doc present** at `doc/progress/<date>-<slug>.md` with all C5 fields (else reject).
2. **No conclusion without its §4(b) evidence block**; any "X works/fails" lacking
   artifact-path / prod-vs-exp / existing-data / best-known / scope ⇒ flag as unverified.
3. **No write to a production path** (`data/*.parquet`, `strategy_config.json`, live
   artifacts, committed WF corpora, live_state) ⇒ reject. (C1/§A-2)
4. **No violation of `AGENT-STATE.md` §A** (e.g. proposing XGB, bypassing the gate,
   self-merge) ⇒ reject. (C4)
5. **Direction matches `AGENT-STATE.md` §B**, or the PR explicitly justifies a change.
6. **Claims are scoped, not over-stated** as global from a single/wrong artifact.

> Residual (also §6): Codex is itself an LLM, so a *subtly plausible-but-wrong* claim
> can pass both agent and reviewer (correlated blind spots). Therefore high-stakes /
> irreversible actions keep a **non-LLM mechanical gate** (WF gate, branch protection,
> prod read-only) as the third layer — never rely on two LLMs agreeing.

## 8. Implementation status

- **Proposed, not yet built:** C1 prod-path write-guard hook + read-only data mount;
  C2 status/evidence linter. The agent can build the mechanical guards on request —
  but they must then be enforced by the hook/CI, not by the agent remembering to run them.
- **Adopted from this PR onward:** C5 — every PR carries `doc/progress/<date>-<slug>.md`
  (this PR includes its own: [`progress/2026-06-17-agent-control-contract.md`](progress/2026-06-17-agent-control-contract.md)).
- **Already in force:** WF gate, branch protection, "never touch production inputs on
  the live tree" (memory `never-touch-production-inputs-on-live-tree`).

## 9. Related standing rules
- [`decisions/2026-06-12-scorer-lineup-decision.md`](decisions/2026-06-12-scorer-lineup-decision.md)
- Memory: *never-touch-production-inputs-on-live-tree*, *never-bypass-branch-protection*,
  *lesson-ground-truth-first-lead-with-conclusion*, *docs-english-chat-chinese*.
