# Design (RFC): event-driven agent-automation closed loop

**Date:** 2026-06-30
**Status:** PROPOSAL for review (no implementation). For Codex (@haorensjtu-dev) to review/discuss before any code or wiring lands.
**Scope:** orchestrator-owned automation of the Claude/Codex agent loop the operator currently drives **by hand** (typing `@codex review`, telling Claude to fix a comment, triaging an ntfy alert). Design only.

---

## 0. TL;DR (bottom-line first)

Automate the three event hops the operator runs manually today, fused into **one closed loop with explicit human gates**:

- **A. ntfy alert → Claude triages** (diagnose; decide if action is even needed).
- **B. Claude opens a PR → Codex reviews it.**
- **C. Codex pushes a review comment → Claude fixes it.**

**Key decision — a HYBRID, not one platform:**
- **Flows B + C are GitHub-native.** Codex's GitHub integration auto-reviews on PR-open (or `@codex review`); the Claude Code GitHub Action (`@anthropics/claude-code-action`, on `@claude` / PR-review events) authors the fix. These are vendor-maintained, event-driven, and need almost nothing built.
- **Flow A is the only thing n8n (or any webhook router) does.** ntfy is not a GitHub event, so it needs cross-system glue: n8n subscribes to the ntfy topic → **filters** (severity / dedup / cooldown / allowlist) → invokes Claude **headless** (`claude -p`) to triage. The filter is the load-bearing part — it is what stops alert-fatigue and runaway spend.

**Non-negotiable:** the loop may iterate **fix ↔ review** autonomously, but **MERGE to `main`, any pin-bump / deploy, and any git op on the live umbrella tree stay human-gated** (or behind a non-agent deterministic check). This is a real-money live trading system. The existing deterministic control-plane (`agent_workflows.py`, CODEOWNERS mutual review, branch protection) is the source of truth for *what may merge*; the new event layer only changes *what triggers an agent*, never *what merges*.

---

## 1. Motivation — every safety requirement here was hit MANUALLY this session

This is not speculative hardening. Running the loop by hand over the past sessions, the operator hit each failure mode the design must prevent. Cited as motivating evidence:

| # | Failure mode observed | What it cost |
|---|---|---|
| 1 | **Non-termination.** An RFC went round 1 → round 5; a feature PR had 4 review rounds, Codex finding a *new* issue each round. The fix→review→comment→fix cycle has no natural stop. | unbounded rounds, no convergence signal |
| 2 | **Concurrency / branch races.** Multiple review comments → multiple fix runs → same-branch pushes → a real **push-reject** this session. | corrupted/aborted fix, wasted run |
| 3 | **Merge/deploy is real money.** Every merge to `main` can flow to a pin-bump → live trade. An auto-merge or an agent `git`-ing the live umbrella tree is catastrophic (we already had a near-miss: a sub-agent `git reset --hard` in the shared live checkout). | live capital risk |
| 4 | **Budget.** Auto-triggering an agent on every event is unbounded spend — the account **hit its monthly spend limit this session**, which killed in-flight subagents mid-task. | dropped work + hard stop |
| 5 | **ntfy noise.** ntfy fires constant benign messages — e.g. the chronic WF-gate reject that was **mislabelled `🔴 ERROR`**. Waking Claude on each = alert fatigue + wasted spend. | spend on non-actionable alerts |

These five become **first-class design requirements** in §6, each with a concrete mechanism.

### 1.1 Relationship to existing work (this supersedes a trigger, not the control-plane)

The repo already has the **deterministic half** of this:

- `src/renquant_orchestrator/agent_workflows.py` — queue resolution + policy + deterministic merge (no-self-review, approved-at-head, all-checks-green, stop-labels, `merged by <agent>` pre-merge audit, production-path write protection).
- `doc/agent-pr-workflows.md` — the local-poll operating model and token/identity SOP.
- `.github/CODEOWNERS` (`* @hallovorld @haorensjtu-dev`) + `require_code_owner_reviews` — makes mutual Claude/Codex review **mechanical**: an author cannot approve their own PR, so every PR needs the *other* agent.
- `doc/design/2026-06-27-autonomous-ops-loops.md` (PR #197, merged) — the script-first error-responder + post-daily reviewer + PR-review watcher, with hard safety defaults (draft-only, reviewer separation, allowlist, prompt-injection rules, numeric caps).

**What this RFC changes:** the *trigger*. The existing model says "the user — or a `/loop` — tells an agent to run a workflow… No webhooks, no Actions". That automates the deterministic queue but still needs the operator's machine up and a manual `/loop`, and it does nothing for the ntfy→triage hop. This RFC replaces the **manual trigger** with **event-driven triggers** while keeping `agent_workflows.py`'s gates as the unchanged authority over merges.

**Why this is not the OIDC/quota pain `agent-pr-workflows.md` rejected.** That doc rejected a *hand-rolled* GitHub Actions stack (`agent-review` / `agent-autofix` / `agent-review-classify` / `agent-auto-merge`) that re-implemented model invocation, token plumbing, and "green-check≠approval" logic in cloud YAML we had to maintain. The hybrid here uses **vendor-native** integrations (Codex GitHub app, `claude-code-action`) that own that plumbing for us — we configure, we don't build it — and crucially **none of them merge**. The merge authority stays exactly where `agent-pr-workflows.md` put it.

---

## 2. Architecture (ASCII)

```
                        ┌─────────────────────────────────────────────────────────────┐
                        │                    HUMAN GATE (operator)                      │
                        │  approves merge · pin-bump · deploy · any live-tree git op    │
                        └───────────────▲──────────────────────────────▲───────────────┘
                                        │ (merge / hold)                │ (escalation)
                                        │                               │
  FLOW A  (cross-system glue = n8n)     │   FLOWS B + C  (GitHub-native, vendor-maintained)
  ───────────────────────────────      │   ──────────────────────────────────────────────
                                        │
  ┌────────────┐   ntfy topic           │   ┌──────────────────────────────────────────┐
  │  daily run │──► (renquant-alerts)    │   │              GitHub repo                  │
  │  alerts.py │        │               │   │         hallovorld/renquant-*             │
  └────────────┘        ▼               │   │                                           │
                 ┌─────────────┐        │   │   PR opened ──► (B) Codex GitHub review   │
                 │   n8n flow  │        │   │      ▲              auto / @codex review   │
                 │  (router)   │        │   │      │                    │                │
                 │ 1 subscribe │        │   │      │ push fix           ▼                │
                 │ 2 FILTER ◄──┼──noise─┤   │      │            review comment / CHANGES │
                 │   sev/dedup │ drop   │   │      │                    │                │
                 │   cooldown  │        │   │      │                    ▼                │
                 │   allowlist │        │   │   (C) Claude Code GitHub Action  ◄─@claude │
                 │ 3 invoke ───┼──┐     │   │      author smallest fix, push, comment   │
                 └─────────────┘  │     │   │      'fixed by claude'                     │
                                  │     │   └──────────────────┬────────────────────────┘
                                  ▼     │                      │
                       ┌────────────────────────┐              │  (all PR state read by)
                       │  claude -p  (headless)  │              ▼
                       │  triage: diagnose, is   │   ┌──────────────────────────────────┐
                       │  action needed? If so:  │   │  agent_workflows.py CONTROL-PLANE │
                       │  open a PR  ──────────────► │  queue · policy · DETERMINISTIC   │
                       │  (advisory ntfy first)  │   │  merge-eligibility (no LLM)       │
                       └────────────────────────┘   │  · no self-approve (CODEOWNERS)   │
                                                     │  · approved-at-head + green       │
                                                     │  · stop-labels · prod-path guard  │
                                                     │  · round-cap · budget guard       │
                                                     └──────────────┬───────────────────┘
                                                                    │ eligible? → SURFACE to
                                                                    └──► HUMAN GATE (never auto)
```

**Reading it:** events enter from two sides (ntfy on the left via n8n; GitHub PR events on the right via vendor integrations). Both converge on the **same** `agent_workflows.py` control-plane, which is the *only* thing allowed to declare a PR merge-eligible — and even then it only **surfaces** it to the human gate. Agents open PRs and push fixes; they never cross the top bar.

---

## 3. The full closed-loop state machine

Not three disconnected hops — one machine with explicit terminal and human-gate states. A PR (or an alert that becomes a PR) is the unit that moves through it.

```
                         (FLOW A)
   ALERT_RECEIVED ──filter drop──► DROPPED (terminal: benign/dup/cooldown)
        │ actionable
        ▼
   TRIAGING ──no action needed──► ADVISORY_ONLY (terminal: ntfy human, no PR)
        │ action needed
        ▼
   PR_OPEN ───────────────────────────────────────────────┐
        │                                                  │ (FLOW B)
        ▼                                                  ▼
   AWAIT_REVIEW ──────────────────────────────────► REVIEW_RUNNING (Codex)
        ▲                                                  │
        │                                                  ▼
        │                                  ┌────── APPROVED ───────┐
        │                                  │                       │
   FIXING ◄── CHANGES_REQUESTED ◄──────────┘                       ▼
   (FLOW C, Claude)                                        MERGE_ELIGIBLE
        │  push fix → AWAIT_REVIEW (loop)                  (control-plane says: approved-at-head
        │                                                   + green + no stop-label)
        │                                                          │
        │  ── round_cap hit / divergence detected ──►              ▼  (NEVER auto)
        │                                              ┌───► HUMAN_GATE ◄── pin/deploy/live-tree
        ▼                                              │         │  decision
   ESCALATED (terminal: human owns it)                 │         ├── merge ──► MERGED (terminal)
                                                       │         └── hold ───► HELD (terminal: label
   budget_exhausted (from ANY non-terminal) ──────────┘                       agent:manual-hold)
        ▼
   PAUSED (terminal until human/cooldown resets the budget guard)
```

**State notes**

- `DROPPED`, `ADVISORY_ONLY`, `ESCALATED`, `MERGED`, `HELD`, `PAUSED` are **terminal**. The loop *always* terminates in one of these; there is no edge that can spin forever (see §6.1).
- `AWAIT_REVIEW ⇄ FIXING` is the only cycle, and it is bounded three ways: Codex `APPROVED` exits up, `round_cap` / divergence exits to `ESCALATED`, `budget_exhausted` exits to `PAUSED`.
- `MERGE_ELIGIBLE → HUMAN_GATE` is a **hard wall**, never an auto-edge. The control-plane can *compute* eligibility deterministically (no LLM), but the transition to `MERGED` is a human action (or, later and separately debated, a non-agent deterministic check that is still not an agent — see §6.3). `HUMAN_GATE` is also the single point where pin-bump / deploy / live-tree decisions are made; none of those are reachable from any agent edge.

---

## 4. Flow A spec — n8n ntfy→triage bridge (the only n8n we build)

**Why n8n for A and *only* A.** ntfy is a standalone pub/sub topic, not a GitHub event, so no vendor GitHub integration can see it. n8n's value is exactly this cross-system fan-in: subscribe to a non-GitHub source, run deterministic filter logic, and call an external command. We deliberately do **not** use n8n's GitHub Trigger node for B/C (docs.n8n.io/integrations/builtin/trigger-nodes/...githubtrigger) because the vendor integrations already do that with less to maintain (§5).

### 4.1 Trigger (subscribe)

Three viable subscription mechanisms, in preference order:

1. **ntfy → n8n Webhook node.** Configure the ntfy server/topic to POST to an n8n Webhook URL on publish. Push, no polling, lowest latency. Preferred if we control the ntfy topic config.
2. **Community node `@jyln/n8n-nodes-ntfy`** — a first-class ntfy trigger node; cleanest if the operator is comfortable installing a community node.
3. **HTTP Request poll of `https://ntfy.sh/<topic>/json`** (ntfy's JSON event stream) on an n8n Schedule trigger — most portable, works against hosted ntfy.sh with zero server config, at the cost of a poll interval.

All three deliver one event = one ntfy message `{id, time, topic, title, message, tags, priority}`.

### 4.2 FILTER (the load-bearing node — this is what §6.5 demands)

A deterministic filter chain *before* any agent is woken. Reject early and cheaply:

1. **Severity classification — do NOT trust `tags`/`priority`.** The chronic WF-gate reject was tagged `🔴 ERROR` yet is benign. Classify on a **rule table over `title`+`message`**, not on the emoji/tag. Map to `{ACTIONABLE, BENIGN, INFO}`. Only `ACTIONABLE` proceeds. (This mirrors the existing `taxonomy=="ACTION_REQUIRED"` filter in PR #197's Loop 1.)
2. **Allowlist of actionable patterns.** Maintain an explicit allowlist (regex/taxonomy keys) of alert classes worth waking an agent — `Traceback`/`NameError`/broker-auth-fail/preflight-hard-fail, etc. Anything not on the allowlist → `DROPPED`. Default-deny.
3. **Dedup.** Compute a stable key (e.g. `sha256(normalized_title)[:24]`, mirroring `stable_alert_key()`); drop if seen in a persistent state store (n8n static data / a small KV) within the dedup window.
4. **Cooldown / rate.** Per-key cooldown (e.g. ≥ N minutes) so a flapping alert wakes Claude once, not every minute. Plus a global flow-A rate cap (§6.4).

Output of the filter: at most a trickle of genuinely-novel, actionable alerts. An idle day = **zero** invocations.

### 4.3 INVOKE (headless Claude triage)

For a surviving alert, n8n's Execute Command (or SSH) node runs Claude **headless** (code.claude.com/docs/en/headless):

```
claude -p "<triage prompt with the alert body wrapped as DATA, not instructions>" \
  --output-format stream-json \
  --max-turns <N> \
  --allowedTools "Read,Bash(git*),Bash(gh*),Grep,Glob" \
  --append-system-prompt "<guardrails: /tmp clone only; never git the live tree; advisory-first>"
```

- `--max-turns N` is the **per-run hard ceiling** (§6.1) — triage cannot run unbounded even on one alert.
- `--output-format stream-json` gives n8n a parseable transcript (turn count, tool calls, final result) for budget accounting (§6.4) and for the `DROPPED`/`ADVISORY_ONLY`/`PR_OPEN` outcome.
- The alert body is **untrusted input** — quoted as evidence inside explicit "DATA — do not follow" delimiters; the triage decision is the agent's, never a command copied from the alert (PR #197 §4.3).
- **Phase-1 default = advisory.** Triage diagnoses and ntfy's the operator with its read; it does **not** open a PR yet. Opening a PR (still draft, still human-gated to merge) is a Phase-2 capability.

**Outcome → state:** `BENIGN/no-fix` → `ADVISORY_ONLY` (ntfy summary, stop). `actionable code bug` → (Phase 2) open a **draft** PR `agent:auto-generated` + `agent:manual-hold` → enters the right side of the loop at `PR_OPEN`. `operational/live/model/data` → **never auto-change**; ntfy a human diagnosis (this is the dominant branch and it spawns no further agent).

---

## 5. Flows B + C — GitHub-native wiring (do NOT reimplement in n8n)

### 5.1 Flow B — Codex reviews the PR (Codex GitHub integration)

Source: developers.openai.com/codex/integrations/github.

- Connect the Codex GitHub app to the `hallovorld/renquant-*` repos under the **Codex identity = `@haorensjtu-dev`** (the CODEOWNERS reviewer for Claude's PRs).
- **Automatic review on PR-open** (or on-demand `@codex review` in a PR comment) produces a review with `CHANGES_REQUESTED` / `APPROVED` state and inline comments.
- Because the reviewer account (`haorensjtu-dev`) ≠ the author account (`hallovorld`), GitHub's native "cannot approve your own PR" rule + `require_code_owner_reviews` make the approval a **genuine second opinion** — exactly the invariant `agent-pr-workflows.md` already relies on. No new merge authority is introduced.
- Review bodies should still carry visible `reviewed by codex` text (account attribution alone is insufficient when agents share operator accounts — existing rule).

### 5.2 Flow C — Claude fixes the comment (Claude Code GitHub Action)

Source: github.com/anthropics/claude-code-action.

- Install `@anthropics/claude-code-action` in a workflow triggered on `pull_request_review` (state `changes_requested`) / `issue_comment` containing `@claude`, scoped to PRs authored by the Claude identity (`hallovorld`).
- The Action checks out the PR branch, reads Codex's review comments, authors the **smallest** fix, runs tests, pushes to the **same PR branch**, and comments `fixed by claude`. Pushing re-opens `AWAIT_REVIEW` → Codex re-reviews (B) → loop.
- The Action runs under a per-run turn/time budget; pair it with the round-cap + branch-lock in §6.

### 5.3 Why native beats a rebuild here

PR events *are* GitHub events, so the vendor integrations are the natural, lower-maintenance home: they own model invocation, token handling, review-state semantics, and checkout/push. n8n adds nothing for B/C except a second system to keep in sync. n8n earns its place only for A, where the source (ntfy) is outside GitHub entirely.

---

## 6. Safety requirements (first-class) — concrete mechanisms

### 6.1 Loop termination / convergence

**Requirement:** the `fix ↔ review` cycle must provably stop. Real cases: an RFC r1→r5; a feature PR with 4 rounds, new issues each round.

**Mechanisms (all four, defence in depth):**
- **Approval is the success exit.** Codex `APPROVED` on the current head → leave the cycle (to `MERGE_ELIGIBLE`). The control-plane already keys on approved-at-head.
- **Hard `max_rounds_per_pr`** (proposed default **3**, config-overridable). On the Nth `CHANGES_REQUESTED→fix` round, stop fixing and `ESCALATE` (label `agent:manual-hold`, ntfy the operator). No silent round N+1.
- **`--max-turns` per agent run** (both the headless triage and `claude-code-action`) — bounds a *single* run so one fix can't churn forever.
- **Divergence detection.** Track per-round review-comment count (or unresolved-thread count). If rounds are **not shrinking** (e.g. round k+1 ≥ round k for 2 consecutive rounds), the loop is diverging → `ESCALATE` even if `max_rounds` is not yet hit. "Codex keeps finding *new* issues" is the signature to catch.

### 6.2 Concurrency / branch locking

**Requirement:** multiple comments must not spawn multiple concurrent fixes on the same branch (a real push-reject happened this session).

**Mechanisms:**
- **Per-PR / per-branch serial lock.** At most **one in-flight fix per PR**. Model it as a lock keyed on `(repo, pr_number)` — a label (`agent:fixing`), a lockfile, or the existing `flock` pattern from the agent-pr-loop. A second triggering event while the lock is held is **coalesced** (re-run once after release against the new head), not run concurrently.
- **Current-head gating** (already in PR #197 §1A): act only when the head SHA advanced past the last-acted SHA; a stale review never re-triggers a fix. This is the exact race that produced "review predates your push" this session.
- **One review per head** for B symmetrically: Codex re-reviews only when the head advances.

### 6.3 The human merge/deploy gate (central, non-negotiable)

**Requirement:** real money. Iterate fix↔review freely, but **MERGE to `main`, pin-bump, deploy, and any live-tree git op stay human-gated** (or behind a non-agent deterministic check). Never auto-merge; never auto-deploy; never let an agent `git` the live umbrella tree.

**Mechanisms (encode as invariants):**
- **No agent path reaches `MERGED`.** The state machine has no agent edge across the `HUMAN_GATE` wall. Agents reach `MERGE_ELIGIBLE` at most.
- **Branch protection** on `main`: `require_code_owner_reviews=true`, `enforce_admins=true`, strict status checks. Combined with **CODEOWNERS** `* @hallovorld @haorensjtu-dev`, every PR mechanically needs the *other* agent's approval and admins cannot override.
- **Reviewer separation by account** (existing): an APPROVED review is only trusted because the reviewer account ≠ author account; the deterministic merge step in `agent_workflows.py` already requires distinct Claude/Codex actors before it will even post the `merged by` audit marker.
- **Auto-generated PRs are merge-frozen.** Any PR the automation opens is **draft** + `agent:auto-generated` + `agent:manual-hold`; the deterministic merge step refuses these until a human clears the hold (PR #197 §4.1).
- **Live tree is off-limits to all agents.** Triage/fix run in **`/tmp` clones only**; never `git` the live umbrella at `/Users/renhao/git/github/RenQuant`; never write production paths (`data/*.parquet`, `strategy_config.json`, live state, `artifacts/prod/`, WF corpora) — `agent_workflows.py` `PROD_PATH_RULES` already encodes the write-block; delegate prompts must forbid live-tree git (the 2026-06-25 near-miss rule).
- **Pin-bump / deploy are not in this loop at all.** Promotion to live is a separate, human-driven, Tier-3-gated process; this automation stops at "a PR is mergeable", never "a pin is bumped".

### 6.4 Budget / rate limits

**Requirement:** auto-triggering on every event = unbounded spend. The account **hit its monthly spend limit this session**, killing in-flight subagents.

**Mechanisms:**
- **Per-flow rate caps.** Flow A: ≤ X agent invocations/hour and ≤ Y/day (after the filter). Flow C: ≤ Z fix-runs/PR/day and a global ≤ W fix-runs/day. (Seed from PR #197 §4.5: ≤3 spawns/cycle, ≤6 novel-fix/day, ≤2 open auto-PRs; tune in Phase 0.)
- **Daily + monthly budget guard.** Track spend/token usage (stream-json gives per-run tokens for headless; the Action exposes run cost). On breach of a daily or monthly threshold → **`PAUSED`**: the loop stops triggering new agent runs and ntfy's the operator. This is the explicit guard against the exact monthly-cap kill we hit. A human (or a scheduled reset) lifts the pause.
- **Backoff.** On repeated failures or rate-limit responses, exponential backoff per flow rather than immediate retry.
- **Per-run token ceiling** via `--max-turns` (and the Action's budget) so no single run can drain the budget.

### 6.5 ntfy noise filtering

**Requirement:** ntfy fires many benign/expected messages (the WF-gate reject mislabelled `🔴 ERROR`). Filter *before* waking Claude.

**Mechanisms (all in the n8n filter node, §4.2):** severity classification on a **rule table over title/message** (ignore the emoji/tag), a **default-deny allowlist** of actionable patterns, **dedup** on a stable key, and **per-key cooldown** + global rate cap. Net effect: alert fatigue and wasted spend are bounded; benign floods cost zero agent runs.

---

## 7. Phased rollout (and the gate we never phase away)

**Phase 1 — Flow-A triage bridge only, read-only / advisory.**
Build just the n8n ntfy→filter→headless-triage path. Claude **diagnoses and ntfy's its read; opens no PR, merges nothing.** Validates the filter (false-positive rate), dedup/cooldown, and the headless-triage prompt in production with zero write risk.
*Exit gate (≥10 trading days):* filter false-positive < 10%; 0 re-fires within cooldown; 0 live-tree git ops; 0 production-path writes; budget guard exercised at least once.

**Phase 2 — GitHub fix↔review loop via the native actions, behind the human merge gate.**
Turn on Codex auto-review (B) and `claude-code-action` (C). Flow A may now **open draft PRs** (`agent:auto-generated` + `agent:manual-hold`). The full state machine runs — *except* the `HUMAN_GATE→MERGED` edge stays a **human action**. Round-cap, divergence detection, branch-lock, budget guard, and reviewer separation all enforced.
*Prerequisite:* the `agent_workflows.py` merge step must already refuse `agent:auto-generated`/`agent:manual-hold`, enforce approved-at-head, and enforce account separation (PR #197 §1 / §6 Phase-2 gate).
*Exit gate:* per-day caps honoured; reviewer separation verified (no same-account merge); spend within cap; round-cap + divergence observed to fire correctly on a real multi-round PR.

**Phase 3 — DOES NOT EXIST for the merge/deploy gate.**
There is deliberately **no phase** that hands merge, pin-bump, deploy, or live-tree git to an agent. Future tuning (caps, allowlist breadth, opening non-draft PRs) is in scope; **auto-merge / auto-deploy is permanently out of scope.** Any change to that requires a new RFC and an explicit operator decision — not a config flip.

---

## 8. Open questions (for Codex / operator)

1. **n8n hosting & identity.** Self-hosted n8n on the operator's machine vs n8n Cloud? Where do the ntfy topic and the `claude -p` execution host live, and how does n8n reach Claude headless securely (Execute Command locally vs SSH to the run host)? Token storage for the headless Claude must follow the Keychain SOP (never in n8n credentials as plaintext if avoidable).
2. **ntfy subscription mechanism.** Webhook-push (needs ntfy server config) vs `@jyln/n8n-nodes-ntfy` (community node trust) vs `/json` poll (latency). Pick one; recommend webhook-push if we own the topic, else `/json` poll.
3. **Does n8n add value over the existing local poll?** PR #197's Loop 1 already polls `alert_log.jsonl` locally. n8n decouples triage from the operator's machine and the `/loop`, but adds a system to run. Is the decoupling worth a second runtime, or should Flow A stay a local poller and n8n be reserved for if/when ntfy must fan out to non-GitHub destinations? **This is the main architecture question for Codex.**
4. **`max_rounds_per_pr` and divergence thresholds** — is 3 rounds the right default? What exact divergence signal (raw comment count vs unresolved-thread count vs net-new-file-touched)?
5. **Budget guard source of truth.** Headless stream-json tokens are local; the Action's spend is on the GitHub/Anthropic side. Do we need a single reconciled budget ledger, or two independent guards (one per flow)?
6. **Identity for `claude-code-action` and Codex app.** Confirm the Action runs as the Claude identity (`hallovorld`) and the Codex app as `@haorensjtu-dev`, so CODEOWNERS separation holds end-to-end and an agent can never approve its own PR.
7. **Failure/escalation UX.** On `ESCALATED` / `PAUSED`, what exactly does the operator receive (ntfy with PR link + round history + last divergence metric)? How is a `HELD` PR un-held?
8. **Idempotency across both event sources.** A code-bug alert (Flow A) and a human-opened PR for the same bug could collide. Dedup key should span both entry points.

---

## 9. Sources

- **n8n GitHub Trigger** (the node we deliberately do *not* use for B/C): docs.n8n.io/integrations/builtin/trigger-nodes/n8n-nodes-base.githubtrigger/
- **n8n + ntfy** — community trigger node `@jyln/n8n-nodes-ntfy`; ntfy JSON event stream `https://ntfy.sh/<topic>/json`; n8n Webhook node for ntfy-push.
- **Claude Code headless** (`claude -p`, `--max-turns`, `--output-format stream-json`, `--allowedTools`): code.claude.com/docs/en/headless
- **Claude Code GitHub Action** (`@anthropics/claude-code-action`, triggered on `@claude` / PR-review/comment events): github.com/anthropics/claude-code-action
- **Codex GitHub review** (auto-review on PR-open / `@codex review`): developers.openai.com/codex/integrations/github
- **Internal prior art:** `doc/agent-pr-workflows.md`, `src/renquant_orchestrator/agent_workflows.py`, `.github/CODEOWNERS`, `doc/design/2026-06-27-autonomous-ops-loops.md` (PR #197).
