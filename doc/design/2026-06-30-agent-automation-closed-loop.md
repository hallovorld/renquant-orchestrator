# Design (RFC): event-driven agent-automation closed loop

**Date:** 2026-06-30
**Revision:** **r3** (2026-06-30) — addresses Codex (`haorensjtu-dev`) round-3 CHANGES_REQUESTED at head `e1941719`: the concurrency claim is now internally consistent end-to-end. r3 CHOOSES one executable architecture — **the local poller is the sole fix executor; GitHub supplies events only** (§5.2, §6.5) — and reconciles §5/§6/§7/§8.2/§9 under it. See §0.2 for the r2→r3 response map (§0.1 keeps the r1→r2 map).
**Status:** PROPOSAL for review (no implementation). For Codex (@haorensjtu-dev) to review/discuss before any code or wiring lands.
**Scope:** orchestrator-owned automation of the Claude/Codex agent loop the operator currently drives **by hand** (typing `@codex review`, telling Claude to fix a comment, triaging an ntfy alert). Design only.

---

## 0. TL;DR (bottom-line first)

### 0.0 The architecture question, answered directly

**START by extending the EXISTING local queue/poller and deterministic control plane (`agent_workflows.py` + the `/loop`-driven local poll described in `doc/agent-pr-workflows.md`). Do NOT stand up n8n up front.** The existing control plane already owns queues, policy, and deterministic merge; the only genuinely new capability we need is *event-driven triggering* of the two hops it already models (review, fix) plus the one hop it does not (ntfy alert → triage). All three can be driven first by turning the existing on-demand local poller into a scheduled/event-fed local poller — **no second stateful runtime**.

**Add n8n (or any external webhook router) ONLY if a *measured* requirement appears that the local control plane cannot meet — specifically cross-host fan-out** (e.g. ntfy must also drive a non-GitHub, non-local destination; or triage must run on a host the operator's machine can't reach). Until that requirement is measured, a second stateful runtime is net-negative: it splits the source of truth, doubles the state/lock surface (§4 below is entirely about why that is dangerous), and adds an operational component to keep in sync. The original r1 draft led with a HYBRID that introduced n8n for Flow A on day one; **r2 demotes n8n to a conditional, deferred option** and makes the local control plane the default spine.

This directly answers what r1 buried in Open-Question Q3: **n8n is not the starting point. The starting point is the control plane we already own.**

### 0.1 Response to Codex (r1 → r2 change map)

| Codex point | Where addressed in r2 |
|---|---|
| **1. Silently reverses the canonical merge agreement.** | **§2 (Merge-policy migration decision)** — r2 no longer says "every merge is permanently human-only". It PRESERVES deterministic merges for ordinary approved PRs and reserves a MANDATORY human hold only for a named high-risk set (production paths, generated/agent-authored PRs, pin/deploy, policy changes, escalations). Framed as an explicit *amendment* to `doc/agent-pr-workflows.md`, with the operational cost stated. |
| **2. Proposed identities are assumptions.** | **§3 (Phase-0 identity probe)** — new. A disposable-PR probe records the *actual* author/reviewer/push actor and token permissions for each integration (Codex app, `claude-code-action`, `GITHUB_TOKEN`). Defines how `agent_workflows.py` maps *verified* trusted identities without weakening self-review. No identity claim is trusted until the probe confirms it. |
| **3. No threat model for a write-capable agent on untrusted PR content.** | **§7 (Threat model)** — new. Full spec: `pull_request` vs `pull_request_target`, fork policy, actor/repo allowlists, immutable action SHA pins, least-privilege `permissions:`, secret availability, path/workflow-change blocks, command allowlists, network policy, and the hard rule that PR-controlled workflow/config never executes with write secrets. States explicitly that a prompt delimiter is not a security boundary. |
| **4. State machine / lock has no atomic source of truth.** | **§6 (Atomic state & lock)** — new. Single persisted store keyed by `(repo, pr, head_sha, review_id)`; atomic acquire/lease/expiry; event idempotency; stale-run cancellation; coalescing; crash recovery; and exactly one component authorised to transition each state. Notes that Actions concurrency serializes action *jobs* only, never local/n8n workers, without a shared store. |
| **5. Rollout does not test the dangerous path before enabling it.** | **§9 (Phased rollout)** — new Phase 0 + hardened Phase 2 gate: shadow/replay from recorded event sequences, isolated sandbox repo, adversarial prompt-injection / workflow-modification cases, duplicate/out-of-order delivery, crash recovery, canary allowlist, and **pre-registered caps + pass criteria** (no open threat-model / lock / injection defects and a bounded divergence metric at enablement). |
| **Overall: start local, add n8n only on measured need.** | **§0.0** and **§4** — n8n demoted to a conditional, deferred option; local control plane is the spine. |

### 0.2 Response to Codex (r2 → r3 change map)

| Codex r2 point | Where addressed in r3 |
|---|---|
| **BLOCKING — the cloud fix runner never acquires the authoritative local lease; the concurrency claim is internally inconsistent.** r2's §5 had `claude-code-action` push the fix, while §6 made the local store the authoritative cross-runtime lock. A GitHub-hosted Action cannot see or acquire that lease, so a local fix and a cloud fix could still race and stale-cancellation was only advisory. | **Resolved by choosing ONE executable architecture and specifying it end-to-end.** r3 adopts **option (a): the local poller is the SOLE fix executor** (§6.5). GitHub supplies review events only; the lease-holding local poller is the single component that authors and pushes a fix, with **head-SHA revalidation immediately before push** (§5.2). The `claude-code-action` cloud Action is removed from the fix/push path entirely — so "one fix per PR across all runtimes" holds **by construction**, not by advice. §5, §6, §7, §8.2 and §9 are rewritten to be mutually consistent under option (a). The alternative — **option (b): a shared transactional lock/state service both runtimes reach, with lease acquire + head-SHA revalidation before push** — is documented (§6.5) as the path required *only if* a cloud executor is ever truly needed, with its added infra cost stated. Not adopted today. |
| **Phase-0 harness must exercise a REAL local-vs-cloud race, not single-process event replay.** | **§9 Phase 0** — new blocking test: two fix executors contend for the same `(repo, pr, head_sha)` and fire concurrent triggers; pass = exactly one acquires the lease and pushes, the other coalesces / aborts-as-superseded, no double-push and no divergent heads. Added to the Phase-0 exit gate and the Phase-2 pass criteria. |
| **CI red on the shared weekly-APY tests (553 pass, 2 fail); required checks must be restored before merge.** | Recorded as a **CI dependency in the progress doc** — the 2 failing `weekly-APY` tests are a **shared, pre-existing** failure unrelated to this design-only change (this PR adds no code), fixed on a separate branch; required checks must be green before this PR merges. |

---

## 1. Motivation — every safety requirement here was hit MANUALLY this session

This is not speculative hardening. Running the loop by hand over the past sessions, the operator hit each failure mode the design must prevent. Cited as motivating evidence:

| # | Failure mode observed | What it cost |
|---|---|---|
| 1 | **Non-termination.** An RFC went round 1 → round 5; a feature PR had 4 review rounds, Codex finding a *new* issue each round. The fix→review→comment→fix cycle has no natural stop. | unbounded rounds, no convergence signal |
| 2 | **Concurrency / branch races.** Multiple review comments → multiple fix runs → same-branch pushes → a real **push-reject** this session. | corrupted/aborted fix, wasted run |
| 3 | **Merge/deploy is real money.** Every merge to `main` can flow to a pin-bump → live trade. An auto-merge of a *high-risk* PR, or an agent `git`-ing the live umbrella tree, is catastrophic (we already had a near-miss: a sub-agent `git reset --hard` in the shared live checkout). | live capital risk |
| 4 | **Budget.** Auto-triggering an agent on every event is unbounded spend — the account **hit its monthly spend limit this session**, which killed in-flight subagents mid-task. | dropped work + hard stop |
| 5 | **ntfy noise.** ntfy fires constant benign messages — e.g. the chronic WF-gate reject that was **mislabelled `🔴 ERROR`**. Waking Claude on each = alert fatigue + wasted spend. | spend on non-actionable alerts |

These five become **first-class design requirements** in §8, each with a concrete mechanism.

### 1.1 Relationship to existing work (extends the trigger; AMENDS the merge doc explicitly)

The repo already has the **deterministic half** of this:

- `src/renquant_orchestrator/agent_workflows.py` — queue resolution + policy + **deterministic merge** (`build_queue`, `merge_pr`, no-self-review via distinct actors, approved-at-head, all-checks-green, `STOP_LABELS`, `merged by <agent>` pre-merge audit, `PROD_PATH_RULES` production-path write protection).
- `doc/agent-pr-workflows.md` — the local-poll operating model and token/identity SOP. **Crucially, this doc says the orchestrator OWNS deterministic merge and runs `gh pr merge --execute` for an agent's own approved+green+unblocked PR after verifying distinct Claude/Codex actors.** r1 contradicted this by asserting every merge is permanently human-only; **r2 reconciles it in §2.**
- `.github/CODEOWNERS` (`* @hallovorld @haorensjtu-dev`) + `require_code_owner_reviews` — makes mutual Claude/Codex review **mechanical**: an author cannot approve their own PR, so every PR needs the *other* agent.
- `doc/design/2026-06-27-autonomous-ops-loops.md` (PR #197, merged) — the script-first error-responder + post-daily reviewer + PR-review watcher, with hard safety defaults (draft-only, reviewer separation, allowlist, prompt-injection rules, numeric caps).

**What this RFC changes:** the *trigger*, and — narrowly and explicitly — a *tightening* of the merge policy for a named high-risk set (§2). The existing model says "the user — or a `/loop` — tells an agent to run a workflow… No webhooks, no Actions". That automates the deterministic queue but still needs the operator's machine up and a manual `/loop`, and it does nothing for the ntfy→triage hop. This RFC replaces the **manual trigger** with **event-driven triggers**, keeps `agent_workflows.py`'s deterministic merge as the authority for *ordinary* PRs, and adds a mandatory human hold only where §2 names it.

**Why this is not the OIDC/quota pain `agent-pr-workflows.md` rejected.** That doc rejected a *hand-rolled* GitHub Actions stack (`agent-review` / `agent-autofix` / `agent-review-classify` / `agent-auto-merge`) that re-implemented model invocation, token plumbing, and "green-check≠approval" logic in cloud YAML we had to maintain. **r3 keeps the fix off the cloud entirely** (option (a), §5.2/§6.5): Flow C's fix is authored and pushed by the **local poller**, reusing the same `claude -p` mechanism Flow A already uses — so there is no cloud write-capable Action to maintain *or* to threat-model in the adopted design (§7's cloud-Action hardening binds only to the deferred option (b)). Flow B (Codex review) stays vendor-native but is read-only. The merge authority stays where `agent-pr-workflows.md` put it, amended only as §2 states.

---

## 2. Merge-policy migration decision (Codex point 1 — resolved explicitly)

r1 repeatedly said "MERGE to `main` … stays human-gated" and "every merge is permanently human-only" while also claiming the existing control-plane authority is *unchanged*. Those two statements cannot both be true: `doc/agent-pr-workflows.md` **currently** authorises the orchestrator to run `gh pr merge --execute` on an agent's own approved+green+unblocked PR. r2 resolves the contradiction with an explicit migration decision rather than a silent reversal.

### 2.1 The decision

**PRESERVE deterministic merges for ORDINARY approved PRs.** For a PR that is (a) approved-at-head by the *other* agent, (b) green on all reported checks, (c) contract-clean (progress doc present, evidence block present), and (d) carries none of the risk markers below, `agent_workflows.py merge --execute` continues to merge it deterministically, exactly as `doc/agent-pr-workflows.md` specifies today. **This automation does not remove that authority.**

**Reserve a MANDATORY human hold for a named high-risk set.** A PR is **merge-frozen** (surfaced to the operator, never auto-merged) if it matches any of:

1. **Production paths** — touches any `PROD_PATH_RULES` match (`data/*.parquet`, `strategy_config.json`, `artifacts/prod/`, live state, WF corpora). (`agent_workflows.py` already flags these as findings; r2 elevates them from "finding" to "hard merge-freeze".)
2. **Generated / agent-authored PRs** — any PR opened by the automation itself (Flow A triage → draft PR), carrying `agent:auto-generated`. A PR written *and* approved entirely inside the loop, with no human in the authoring path, does not clear the bar for auto-merge.
3. **Pin / deploy changes** — touches pin manifests, promotion config, or anything that can flow to a live pin-bump.
4. **Policy changes** — touches `.github/` (CODEOWNERS, workflows, branch-protection-as-code), `agent_workflows.py` merge policy, `doc/agent-pr-workflows.md`, or the safety docs themselves. The loop must not be able to auto-merge a change to its own guardrails.
5. **Escalations** — any PR carrying `agent:manual-hold` / `agent:cost-cap` / `agent:rebase-conflict` (already `STOP_LABELS`) or that hit the round-cap / divergence exit (§8.1).

For the high-risk set, the loop iterates fix↔review freely and computes eligibility, but the transition to `MERGED` is a **human action** (or, if ever proposed, a separate non-agent deterministic check — a *new* RFC, not this one).

### 2.2 This is an amendment to the canonical doc, with its cost stated

This is a deliberate **amendment** to `doc/agent-pr-workflows.md`, not a silent override. Concretely, the amendment adds one clause to the merge policy there: *"the deterministic merge additionally fails closed (surfaces to the operator instead of merging) when the PR matches the high-risk set in the agent-automation RFC §2.1."* If Codex agrees, r2's follow-up (post-approval) includes a one-paragraph patch to `doc/agent-pr-workflows.md` recording this clause, so the two docs never disagree.

**Operational cost of the amendment (stated honestly):**

- **Throughput cost.** Every production/pin/policy/generated PR now waits on the operator even when checks are green. Given how many orchestrator PRs touch `doc/` and code but *not* the high-risk set, most ordinary PRs still auto-merge; the hold bites the minority that genuinely can move live capital or guardrails. That is the intended trade.
- **Operator-attention cost.** The operator becomes a required serializer for the high-risk set. §8.4's budget/backoff and §6's escalation UX must make "what is waiting on me and why" a single glance, or the hold becomes a bottleneck that tempts a bypass.
- **Risk of the *reverse* error.** Freezing too broadly (e.g. treating every `doc/` touch as "policy") would strand routine work behind a human and re-create the manual toil this RFC removes. The high-risk set in §2.1 is deliberately narrow and pattern-defined so it can be encoded deterministically, not judged by an LLM.

### 2.3 Invariants that do NOT change

- **No agent ever `git`s the live umbrella tree** at `/Users/renhao/git/github/RenQuant`; triage/fix run in `/tmp` clones only (the 2026-06-25 near-miss rule).
- **Reviewer separation by account** remains the mechanical merge gate: an APPROVED review is trusted only because the reviewer account ≠ author account, verified by `agent_workflows.py`'s distinct-actor preflight — subject to §3 confirming those accounts are what we think they are.
- **Pin-bump / deploy to live** remain a separate, human-driven, Tier-3-gated process outside this loop entirely.

---

## 3. Phase-0 identity probe (Codex point 2 — assumptions replaced by measurement)

r1 asserted that the Codex GitHub app reviews **as** `@haorensjtu-dev`, that `claude-code-action` pushes **as** `hallovorld`, and therefore CODEOWNERS separation and the visible-marker checks hold end-to-end. **These are assumptions, and Codex is right to reject them.** In practice:

- A **GitHub App** review/check typically appears under the app's own **bot installation identity** (e.g. `codex[bot]` / `<app-name>[bot]`), *not* the operator's user login.
- A push/comment made with the workflow's default **`GITHUB_TOKEN`** appears as **`github-actions[bot]`**, *not* automatically `hallovorld` or `haorensjtu-dev`.
- CODEOWNERS entries reference **user/team logins**; a bot identity is not `@hallovorld` or `@haorensjtu-dev` and may not satisfy `require_code_owner_reviews` at all — or may satisfy it under a *different* identity than the merge preflight expects.

If the real actors differ from the assumed ones, then (a) the "cannot approve your own PR" invariant may not fire as designed, (b) `agent_workflows.py`'s distinct-actor / `merged by <agent>` checks may key on the wrong login, and (c) the visible `reviewed by codex` / `fixed by claude` markers become the *only* attribution — which the canonical doc already says is required precisely because account attribution alone is insufficient.

### 3.1 The probe (runs before any Phase-1 wiring)

On a **disposable PR in an isolated sandbox repo** (§9 Phase 0), run each integration once and record ground truth:

1. **Codex review actor.** Trigger a Codex review; record `reviews[].author.login`, `author.type` (`User` vs `Bot`), and whether the review satisfies `require_code_owner_reviews` given the current CODEOWNERS.
2. **`claude-code-action` push/comment actor.** Let the Action push a commit and post a comment; record the commit author/committer, the comment `author.login`/`type`, and which token identity GitHub attributes them to (`github-actions[bot]` vs a PAT-backed user).
3. **Token permission scope.** For each token/app: record `permissions:` actually granted (contents, pull-requests, checks, workflows), and whether secrets are exposed to the run.
4. **Self-review reachability.** Explicitly test the adversarial case: can the *author* identity (or a bot acting for it) produce an approval that the merge preflight would accept? Record pass/fail.

### 3.2 How `agent_workflows.py` maps verified identities (without weakening self-review)

Once the probe returns ground truth, define an explicit, **allowlisted identity map** in the control plane:

- Maintain a small, reviewed table `trusted_identity → logical_agent` (e.g. `codex[bot] → codex`, `<claude-app>[bot] → claude`, plus the human PAT logins). Only identities on this table are recognised as an agent at all.
- **Self-review protection is by logical agent, not by raw login.** The rule "an APPROVED review is trusted only if reviewer.logical_agent ≠ author.logical_agent" must hold *after* mapping — so a bot that maps to `claude` can never approve a PR authored by `claude`, even if their raw logins differ. This is *stronger* than r1's account-only check, and closes the case where two different bot logins both act for the same agent.
- If the probe shows a bot identity **cannot** satisfy CODEOWNERS, the fallback is to keep review/approval on the **PAT-backed user identities** (the existing `RENQUANT_<AGENT>_GH_TOKEN` path) and use the app/Action only for the non-approving hops (triage, fix authoring). The probe result decides this; the RFC does not pre-commit to a path that may not exist.
- The distinct-actor preflight in `agent_workflows.py` (already fail-closed) is extended to reject any review whose actor is **not** on the trusted-identity table, so an unrecognised bot can never be counted as the second opinion.

Nothing merges on the strength of an identity the probe has not confirmed.

---

## 4. Architecture (extend local first; n8n conditional)

```
                        ┌─────────────────────────────────────────────────────────────┐
                        │              HUMAN GATE (operator) — high-risk set only       │
                        │  approves merge of prod/pin/policy/generated PRs · deploy ·   │
                        │  any live-tree git op · escalations                           │
                        └───────────────▲──────────────────────────────▲───────────────┘
                                        │ (merge / hold)                │ (escalation)
                                        │                               │
  LOCAL CONTROL PLANE (the spine — extend this FIRST)                   │
  ─────────────────────────────────────────────────────────────────    │
                                                                        │
  ┌────────────┐  ntfy topic    ┌───────────────────────────┐          │
  │  daily run │─►(renquant-     │  LOCAL poller / event feed │          │
  │  alerts.py │   alerts)  ───► │  (extends agent_workflows  │          │
  └────────────┘                │   poll + PR #197 loops)    │          │
                                │  · FILTER (sev/dedup/       │          │
                                │    cooldown/allowlist)      │          │
                                │  · ATOMIC state store (§6)  │          │
                                │  · budget guard (§8.4)      │          │
                                └───────┬──────────┬──────────┘          │
                                        │          │                     │
                     (A) invoke headless│          │(drives review/fix   │
                     claude -p triage   │          │ via existing queue)  │
                                        ▼          ▼                     │
                              ┌──────────────────────────────────────┐   │
                              │  agent_workflows.py CONTROL-PLANE     │   │
                              │  queue · policy · DETERMINISTIC merge │───┘
                              │  (ordinary approved PRs auto-merge;   │
                              │   high-risk set → SURFACE to human)   │
                              └──────────────────────────────────────┘
                                        ▲          ▲
      (B) Codex review (native, read-only) → review EVENTS feed up into the local store
      (C) FIX authored + pushed by the lease-holding LOCAL poller (§5.2) — no cloud Action on the write path
                                        │          │
                              ┌──────────────────────────────────────┐
                              │  GitHub repo  hallovorld/renquant-*   │
                              └──────────────────────────────────────┘

  n8n / external webhook router: NOT in the day-one design. Added ONLY if a measured
  cross-host fan-out requirement appears (§0.0). Until then, the local poller is the router.
```

**Reading it:** the **local control plane is the spine**. Events (ntfy alerts on the left; GitHub PR state on the right) are consumed by a *local* poller/event-feed that extends what `agent_workflows.py` + the PR #197 loops already do. That local component owns the filter, the atomic state store (§6), and the budget guard. It drives the existing deterministic queue. **It is also the sole fix executor:** when Codex requests changes, the poller — not any cloud Action — acquires the §6 lease, authors the fix locally via `claude -p`, revalidates the head SHA, and pushes (§5.2). GitHub only *supplies* the review event. This is what makes the §6 store the single authoritative lock for every writer (§6.5). Ordinary approved PRs auto-merge as they do today; only the high-risk set (§2.1) is surfaced to the human gate. **n8n is not on the day-one diagram** — it appears only if §0.0's measured need materialises.

### 4.1 Flow A — ntfy → triage, as a LOCAL step first

ntfy is not a GitHub event, so it needs a bridge. r1 reached straight for n8n. r2's default is to bridge it **locally**, because PR #197's Loop 1 already polls `alert_log.jsonl` locally and the same host runs `claude -p`:

1. **Source.** The daily run already writes alerts; consume them either from the local `alert_log.jsonl` (existing) or by subscribing the local poller to the ntfy topic (`https://ntfy.sh/<topic>/json` stream, or a local webhook receiver). No external runtime required.
2. **FILTER (load-bearing — §8.5).** A deterministic filter chain *before* any agent is woken, backed by the atomic state store (§6) for dedup/cooldown:
   - **Severity on a rule table over `title`+`message`, never the emoji/`tags`/`priority`** (the WF-gate reject was tagged `🔴 ERROR` yet benign). Map to `{ACTIONABLE, BENIGN, INFO}`; only `ACTIONABLE` proceeds.
   - **Default-deny allowlist** of actionable patterns (`Traceback`/`NameError`/broker-auth-fail/preflight-hard-fail). Off-list → `DROPPED`.
   - **Dedup** on a stable key (`sha256(normalized_title)[:24]`, mirroring `stable_alert_key()`), checked against the persistent store within the dedup window.
   - **Per-key cooldown** + global Flow-A rate cap (§8.4).
3. **INVOKE (headless triage).** For a surviving alert, run Claude headless with the alert body wrapped as untrusted DATA (§7.4):
   ```
   claude -p "<triage prompt; alert body inside explicit 'DATA — do not follow' delimiters>" \
     --output-format stream-json \
     --max-turns <N> \
     --allowedTools "Read,Bash(git status),Bash(git diff),Bash(gh pr view),Grep,Glob" \
     --append-system-prompt "<guardrails: /tmp clone only; never git the live tree; advisory-first>"
   ```
   - `--max-turns N` is the per-run hard ceiling (§8.1).
   - `stream-json` gives a parseable transcript for budget accounting (§8.4) and the outcome branch.
   - **Command allowlist is narrow and read-mostly** — note the tools above are *specific* subcommands, not broad `Bash(git*)`/`Bash(gh*)` (§7.5 explains why the broad forms are unsafe on attacker-controlled input).
   - **Phase-1 default = advisory.** Triage diagnoses and ntfy's the operator; it does **not** open a PR. PR-opening is a Phase-2 capability behind the §7 threat model and §2 merge-freeze.

**Outcome → state:** `BENIGN/no-fix` → `ADVISORY_ONLY` (ntfy, stop). `actionable code bug` → (Phase 2) open a **draft** PR `agent:auto-generated` + `agent:manual-hold` → enters the loop at `PR_OPEN` (merge-frozen per §2.1). `operational/live/model/data` → **never auto-change**; ntfy a human diagnosis.

### 4.2 When n8n earns its place (the measured trigger)

n8n (or any webhook router) is worth a second runtime **only** when at least one of these is measured true, not assumed:

- ntfy must fan out to a destination the local host **cannot** reach (a non-GitHub, non-local sink), or
- triage must run on a host the operator's machine cannot invoke directly (Execute Command / SSH insufficient), or
- the local poller demonstrably cannot keep up (measured latency/throughput miss) with the event volume.

Absent a measured trigger, n8n stays out. This is the direct answer to r1's Q3.

---

## 5. Flows B + C — GitHub-native wiring (do NOT reimplement in n8n)

### 5.1 Flow B — Codex reviews the PR (Codex GitHub integration)

Source: developers.openai.com/codex/integrations/github.

- Connect the Codex GitHub app to the `hallovorld/renquant-*` repos. **The review identity is whatever §3's probe records** — do not assume `@haorensjtu-dev`; the probe confirms the actual actor and whether it satisfies CODEOWNERS.
- **Automatic review on PR-open** (or on-demand `@codex review`) produces a review with `CHANGES_REQUESTED` / `APPROVED` state and inline comments.
- The distinct-actor invariant holds only after §3's identity map confirms the reviewer maps to a *different logical agent* than the author. Until confirmed, approval stays on the PAT-backed user identities (§3.2 fallback).
- Review bodies still carry visible `reviewed by codex` text (account attribution alone is insufficient when agents share operator accounts — existing rule).
- **Flow B is read/review only.** It produces a review *event* + inline comments that the local poller consumes into the §6 store; it holds **no** fix-push authority and never contends for the §6 lease. It is the *trigger*, not the fix executor (that is the local poller, §5.2).

### 5.2 Flow C — Claude fixes the comment (EXECUTED LOCALLY by the lease-holding poller)

Under the chosen architecture (**option (a)**, §6.5) the **local poller is the sole fix executor.** GitHub supplies only the *event* that a fix is needed; no cloud component authors or pushes the fix. This is the change that makes Codex's flagged race impossible rather than merely unlikely.

- **Event supply (native, read-only).** A Codex `CHANGES_REQUESTED` review (Flow B) is delivered into the §6 store — either by the local poller reading the reviews API (`gh pr view` / poll), or by a webhook receiver on the local host that writes the event to the store. The `claude-code-action` cloud Action is **not** on the fix/push path. (If it is ever used at all, it is restricted to **non-mutating** triage that likewise only *enqueues* an event into the store — it must never checkout-and-push a fix, because it cannot hold the §6 lease.)
- **Lease (authoritative).** The poller performs the §6.2 atomic acquire on `(repo, pr, head_sha)`. Only the lease winner proceeds; a concurrent second review event **coalesces** (§6.2) instead of starting a second fix.
- **Fix authoring (local — same `claude -p` mechanism as Flow A triage).** Holding the lease, the poller clones the PR branch into a `/tmp` workspace (**never** the live umbrella tree, §2.3), reads Codex's review comments **as untrusted input** (§7.4), invokes `claude -p` under the narrow, write-scoped command allowlist (§7.5) to author the **smallest** fix, and runs tests locally.
- **Head-SHA revalidation immediately before push (hard rule).** After authoring but *before* pushing, the poller re-reads the PR head SHA from GitHub. If it no longer equals the leased `head_sha`, the run is **aborted as superseded** (§6.3) and nothing is pushed — the new head gets its own leased run. Only on a match does the poller push to the PR branch and post `fixed by claude`. The push token is held by the **poller**, not exposed to the `claude -p` agent process (§7.3).
- The push advances the head → a **new** §6 row → `AWAIT_REVIEW` → Codex re-reviews (B) → loop. Because exactly one component (the lease-holding poller) ever pushes a fix, **there is no cross-runtime fix race by construction** — the inconsistency Codex flagged is removed, not mitigated.
- Per-run turn/time budget (`--max-turns`, §8.4) and the round-cap/divergence exits (§8.1) bound the loop.

### 5.3 What stays native, what must be local — and why

- **Flow B (Codex review) stays native.** It is read/review only: it produces a review event and inline comments and holds **no** fix-push authority. The Codex app is the natural, lower-maintenance home for it, and it never contends for the §6 lease.
- **The Flow-C *trigger* stays native.** A review/comment is a GitHub event, so GitHub is its source; the poller consumes it (§5.2).
- **Flow-C *fix execution* must be local.** A fix is a write (checkout → author → push) that must be serialized by the **single authoritative lease** (§6). A GitHub-hosted Action cannot see or acquire that local lease, so if the Action pushed fixes it could race a local fix — exactly Codex's blocking point. Moving fix execution into the lease-holding local poller makes the lock **enforceable**, not advisory. n8n adds nothing here except a second system to keep in sync.
- Under the deferred **option (b)** (§6.5) — a cloud executor with a shared transactional lock — fix execution *may* run in the cloud, but only against a store both runtimes reach, with lease acquisition + head-SHA revalidation before push, at the added infra cost §6.5 states. This RFC does not adopt it.

---

## 6. Atomic state & lock — the single source of truth (Codex point 4)

r1 gestured at "a label, a lockfile, or the existing `flock`", plus n8n static data, plus GitHub Actions concurrency. **Those are four different stores and do not compose into one lock.** A GitHub label is not atomic (read-modify-write races), a local `flock` is invisible to a cloud Action, n8n static data is invisible to the local poller, and **Actions concurrency groups serialize Action *jobs* only — they do not serialize the local poller or any n8n worker.** With no shared store, two components can both believe they hold the lock.

### 6.1 One persisted store, one owner per transition

Define a **single persisted state store** (the local control plane's store — e.g. a small SQLite/KV file the poller owns; the *same* store the filter uses for dedup/cooldown). Every unit of work is a row keyed by:

```
(repo, pr_number, head_sha, review_id)   → state, lease_owner, lease_expiry, attempt, last_event_id
```

- **`head_sha` in the key** makes stale events harmless: an event for a superseded head is a different row and never acts on the current head.
- **`review_id` / `last_event_id`** gives idempotency: a redelivered or duplicated webhook/poll event with an already-seen id is a no-op.

### 6.2 Atomic acquire / lease / expiry

- **Acquire** = a single atomic compare-and-set on the row (`UPDATE … WHERE state='idle'` / conditional put). Only the writer that flips the row wins; everyone else sees the row already leased and coalesces.
- **Lease + expiry** = the winner writes `lease_owner` + `lease_expiry = now + T`. A run that dies without releasing (crash) has its lease expire, and exactly one recoverer may reclaim it. No indefinite lock held by a dead process.
- **At most one in-flight fix per `(repo, pr)`.** A second triggering event while the lease is held does **not** start a concurrent run; it sets a `pending_rerun` flag so the loop re-runs **once** after release, against the *new* head (coalescing, not queuing N runs).

### 6.3 Idempotency, stale-cancellation, coalescing, recovery

- **Event idempotency.** Every inbound event carries a delivery id; the store records processed ids. Duplicate/out-of-order delivery (Codex point 5's test case) is dropped or reordered by `head_sha`, never double-acted.
- **Stale-run cancellation.** When `head_sha` advances, any in-flight run keyed to the old head is signalled to abort and its row is marked superseded; only the newest head can hold an active lease.
- **Crash recovery.** On poller start, sweep for expired leases; for each, reconcile against GitHub ground truth (is the PR still open? did the fix push land?) before reclaiming — never blindly re-run.
- **Single transition owner AND single fix executor.** Exactly one component may transition each state: the **local poller** owns `ALERT_RECEIVED→…→PR_OPEN`, `AWAIT_REVIEW⇄FIXING`, and `→ESCALATED/PAUSED`; the **deterministic merge step** owns `MERGE_ELIGIBLE→MERGED` (ordinary PRs) or `→(surfaced) HUMAN_GATE` (high-risk set); the **human** owns `HUMAN_GATE→MERGED/HELD`. Under the chosen option (a), the poller does not merely *transition* `FIXING` — it **executes** the fix (authoring + head-SHA-revalidated push, §5.2). No cloud component authors or pushes a fix; the Codex app only emits review events the poller *reads*. This keeps a single writer per state **and** a single pusher per PR branch, removing both the cross-runtime race and the four-store problem.

### 6.4 GitHub Actions concurrency — what it does and does not buy

Actions `concurrency:` groups (e.g. `group: fix-${{ github.event.pull_request.number }}`, `cancel-in-progress: true`) usefully serialize/cancel *Action jobs*. **But they are not the lock.** They do not know about the local poller or any external worker, and they cannot enforce "one fix per PR across all runtimes". The authoritative lock is always the §6.1 store; Actions concurrency is a secondary, best-effort guard on the Action side only — and **under the chosen option (a) there is no fix Action job at all** (§5.2), so this consideration binds only to option (b) or any cloud Action later added.

### 6.5 The chosen executor architecture (option a), and the alternative (option b)

Codex's blocking point: a cloud fix runner that pushes but never acquires the authoritative local lease makes the lock advisory, not enforceable. Two architectures actually close this. The RFC **picks one and specifies it end-to-end**, rather than leaving both half-wired (the r2 inconsistency).

**Option (a) — the LOCAL poller is the sole fix executor (CHOSEN).** GitHub supplies review events only; the lease-holding local poller is the **only** component that authors and pushes a fix, with head-SHA revalidation immediately before push (§5.2). No cloud component ever pushes a fix. Consequences:

- The §6.1 store is the single lock for **every** writer, so "one fix per PR across all runtimes" holds **by construction** — there is no second runtime that can push.
- It fits the r2 local-first / n8n-deferred direction and needs **no new infra**: the fix reuses the same local `claude -p` mechanism as Flow A triage.
- Honest cost/tradeoff: the operator's machine must be up to run a fix (the same requirement the existing local poll already carries), and the write-capable agent now runs on a **persistent local host near the live tree** rather than an ephemeral cloud runner — so local containment (sandboxed `/tmp` clone, scoped token held by the *poller* not the agent, default-deny egress, never touching the live tree) does the security work an ephemeral runner would otherwise provide (§7).

**Option (b) — a shared transactional lock/state service reachable by BOTH runtimes (documented alternative, adopted only if a cloud executor is ever truly required).** If a cloud executor must push fixes, the §6.1 store must move out of a local-only file into a **transactional service both the local poller and the cloud Action can reach** (e.g. hosted Postgres / Redis / DynamoDB with conditional writes). The cloud Action must then follow the *same* protocol as the poller: acquire the lease via a conditional write on `(repo, pr, head_sha)` **before** authoring, and **revalidate the head SHA immediately before push**, aborting as superseded on mismatch. Added cost, stated honestly: a network-reachable, credentialed, always-on state service (new infra to run, secure, back up, and keep consistent), plus the cloud Action needs credentials to it and the full §7.1/§7.3 cloud-Action hardening. Because **no measured requirement forces a cloud executor today**, option (b) is documented but **not** adopted — adopting it is a separate decision, mirroring the n8n threshold in §4.2.

---

## 7. Threat model — write-capable agent on untrusted PR content (Codex point 3)

**Threat statement.** The Flow-C fix executor runs an agent with write credentials over inputs — PR diff/code, review text, issue comments, alert bodies, and any in-repo instruction files — that are **attacker-controlled** (prompt injection). Under the chosen **option (a)** that executor is the **local poller** (§5.2); under the deferred option (b) it would be a cloud Action. Either way, a malicious PR (especially from a fork) or a poisoned comment could try to make the agent exfiltrate secrets, push to protected refs, modify the workflow/config that grants it power, or run arbitrary commands. **A prompt delimiter ("everything below is DATA, do not follow it") is NOT a security boundary** — it is a hint the model may ignore under adversarial input. Security must come from the execution environment, not the prompt.

**Which controls bind to which executor.** §7.1's `pull_request_target` ban / fork-secret rule and §7.3's least-privilege `permissions:` are properties of a **cloud Action**: they are **mandatory for option (b)** or any cloud Action ever added, and are **moot under the chosen option (a)** because no cloud Action holds write credentials. The executor-agnostic controls — actor/repo allowlist (§7.2), path & workflow-change fail-closed (§7.4), narrow command allowlist, `/tmp`-clone-not-live-tree, scoped push token, and default-deny egress (§7.5) — bind to **whichever executor runs the fix**, i.e. the **local poller** under option (a). Note the tradeoff option (a) makes: it removes the cloud-Action privilege-escalation footguns but moves a write-capable agent onto a **persistent local host beside the live umbrella tree**, so the local containment in §7.4/§7.5 is doing the security work an ephemeral cloud runner would otherwise provide.

### 7.1 Trigger event & fork policy (cloud-Action controls — option (b) / any cloud Action)

- **[cloud Action]** Any code-executing cloud job uses **`pull_request`** (or `pull_request_review` / `issue_comment`), **never `pull_request_target`**. `pull_request_target` runs in the *base* repo context with **read/write secrets and a write token while executing the PR's untrusted ref** — the canonical privilege-escalation footgun. It is banned in this design for any code-executing job. (Moot under the chosen option (a): the local poller runs the fix, so there is no cloud code-executing job.)
- **Fork PRs get zero write credentials, on either executor.** A cloud workflow triggered by a fork PR runs with a read-only `GITHUB_TOKEN` and no secrets; and under option (a) the local executor equally **disables auto-fix for fork-authored PRs** (§7.2 actor allowlist). Only PRs from branches in the trusted repo, authored by an allowlisted identity, may reach the write-capable path.

### 7.2 Actor / repo allowlists (executor-agnostic — bind to whichever executor runs the fix)

- **Repo allowlist:** the fix executor only arms in `hallovorld/renquant-*`.
- **Actor allowlist:** the write-capable fix path arms only when the PR author maps (via §3's verified identity table) to the Claude logical agent. Any other author → advisory/no-op.
- **Association gate:** require `author_association` ∈ {OWNER, MEMBER, COLLABORATOR}; drop FIRST_TIME / NONE.

### 7.3 Immutable pins & least privilege

*(The first two bullets are cloud-Action controls — mandatory under option (b) / any cloud Action, moot under the chosen option (a). The token-separation bullet binds to whichever executor runs the fix.)*

- **[cloud Action] Pin every action to an immutable commit SHA**, not a tag (`uses: anthropics/claude-code-action@<40-char-sha>`), so a moved tag cannot swap the code under us. Renovate/Dependabot updates the SHA via a normal reviewed PR.
- **[cloud Action] Least-privilege `permissions:`** at the job level — start from `permissions: {}` and grant only what the fix needs (`contents: write`, `pull-requests: write`); **never** `workflows: write`, and no org/admin scopes. Default the whole repo to read via workflow-permissions settings.
- **Scoped push token, held by the EXECUTOR — not the agent.** Under option (a) the push uses a **fine-grained PAT scoped to `contents`+`pull-requests` on the allowlisted `hallovorld/renquant-*` repos only** (no `workflows`, no secrets, no admin). That token is held by the **poller**, which performs the push *after* head-SHA revalidation; it is **never** placed on the `claude -p` agent's command surface or environment — the agent authors the diff, the poller pushes it. Under option (b) the equivalent rule is job-separation: "run agent on untrusted PR code" (no secrets) and "push result" (minimal scoped token) live in different jobs so untrusted code never shares a process with a write secret.

### 7.4 Path & workflow-change blocks

- **PR-controlled workflow/config cannot execute with write secrets — hard rule.** If a PR modifies `.github/workflows/**`, `.github/actions/**`, CODEOWNERS, or the branch-protection/policy files, the write-capable path **fails closed** and the PR is surfaced to the human (this is also a §2.1 policy-change merge-freeze). The loop must never be able to rewrite the workflow that grants it privilege and have that new workflow run with secrets in the same or next step.
- **Path-scope the fix.** The auto-fix is allowed to touch only a bounded path set (e.g. the diff's own files minus the protected set); a fix that tries to touch `.github/`, prod paths, or pins is rejected and escalated.

### 7.5 Command allowlist & network policy

- **Narrow command allowlist, not `Bash(git*)`/`Bash(gh*)`.** Broad `git*`/`gh*` allow `git push --force`, `gh pr merge`, `gh api` writes, `gh secret`, etc. The triage/fix agents get **specific, read-mostly subcommands** (as in §4.1) plus, for fix only, a scoped commit/push to the *PR branch only*. No `gh pr merge`, no `gh api` writes, no `gh secret`, no force-push.
- **Network policy.** The runner egress is restricted to what the agent legitimately needs (GitHub API, model endpoint, package registry for tests). Default-deny egress mitigates secret exfiltration even if injection succeeds.
- **No self-hosted runner for untrusted PRs.** Untrusted PR code runs only on ephemeral GitHub-hosted runners, never a persistent self-hosted runner that could be poisoned across runs.

### 7.6 Residual risk & monitoring

Injection cannot be *eliminated*, only contained. The above ensures that even a successful injection has: no secrets in the untrusted process, a read-only token on forks, no ability to rewrite its own workflow, no merge/deploy/force-push commands, and default-deny egress. §9 Phase 0/2 pre-registers adversarial injection and workflow-modification test cases as *blocking* gate criteria.

---

## 8. Safety requirements (first-class) — concrete mechanisms

### 8.1 Loop termination / convergence

**Requirement:** the `fix ↔ review` cycle must provably stop (real cases: RFC r1→r5; a 4-round feature PR).

- **Approval is the success exit.** Codex `APPROVED` at head → leave the cycle (to `MERGE_ELIGIBLE`).
- **Hard `max_rounds_per_pr`** (default **3**, config-overridable). On the Nth `CHANGES_REQUESTED→fix` round, stop and `ESCALATE` (`agent:manual-hold` + ntfy). No silent round N+1.
- **`--max-turns` per agent run** bounds a single run.
- **Divergence detection.** Track per-round unresolved-thread / review-comment count; if not shrinking for 2 consecutive rounds (round k+1 ≥ round k), `ESCALATE` even before `max_rounds`. "Codex keeps finding *new* issues" is the signature.

### 8.2 Concurrency / branch locking

**Requirement:** multiple comments must not spawn multiple concurrent fixes on one branch (a real push-reject happened). **Mechanism = the §6 atomic store + a single fix executor**: under the chosen option (a) the lease-holding **local poller is the only component that pushes a fix** (§5.2/§6.5), so there is no second runtime to race with — one lease per `(repo, pr)`, `head_sha`-keyed stale rejection, **head-SHA revalidation immediately before push**, and coalesced re-run against the new head. Actions concurrency (§6.4) is moot under option (a) and only a secondary guard under option (b).

### 8.3 Human merge/deploy gate (per the §2 migration decision)

**Requirement:** real money. Ordinary approved PRs auto-merge (unchanged); the **high-risk set (§2.1)** is human-gated. No agent path crosses into `MERGED` for the high-risk set. Branch protection (`require_code_owner_reviews`, `enforce_admins`, strict checks) + CODEOWNERS remain mechanical. Auto-generated PRs are draft + `agent:auto-generated` + `agent:manual-hold` and merge-frozen. Live tree off-limits to all agents (`/tmp` clones only). Pin-bump / deploy are outside this loop.

### 8.4 Budget / rate limits

**Requirement:** auto-triggering on every event = unbounded spend (the monthly cap killed subagents this session).

- **Per-flow rate caps.** Flow A: ≤ X invocations/hour, ≤ Y/day (post-filter). Flow C: ≤ Z fix-runs/PR/day, global ≤ W/day. Seed from PR #197 §4.5 (≤3 spawns/cycle, ≤6 novel-fix/day, ≤2 open auto-PRs); the exact X/Y/Z/W are **pre-registered before Phase 2** (§9), not left open.
- **Daily + monthly budget guard.** Track spend (stream-json tokens for headless; Action run cost). On breach → `PAUSED`: stop triggering new runs, ntfy the operator; a human/scheduled reset lifts it.
- **Backoff.** Exponential per-flow backoff on repeated failure / rate-limit.
- **Per-run ceiling** via `--max-turns` / Action budget.

### 8.5 ntfy noise filtering

All in the §4.1 filter: rule-table severity (ignore emoji/tag), default-deny allowlist, stable-key dedup, per-key cooldown + global cap. Benign floods cost zero agent runs; an idle day = zero invocations.

---

## 9. Phased rollout — test the dangerous path before enabling it (Codex point 5)

**Phase 0 — Identity probe + harness + shadow, ZERO write to any real repo.**
Before any live wiring: run the §3 identity probe in a **disposable, isolated sandbox repo**; stand up the §6 atomic state store; and build a **shadow/replay harness** that feeds *recorded* event sequences (real ntfy alerts + PR review events captured to a fixture) through the filter, state machine, and lock **without invoking any write-capable action**. Adversarial fixtures are mandatory here:

- **Prompt-injection cases** — alert bodies / review comments that try to make triage or fix run out-of-scope commands, exfiltrate, or ignore guardrails. Pass = the agent takes no disallowed action; the §7 command allowlist / secret-gating holds.
- **Workflow-modification cases** — a PR that edits `.github/**` / CODEOWNERS / pins. Pass = §7.4 fails closed and surfaces to human; no privileged execution.
- **Duplicate / out-of-order delivery** — replay the same event twice and events reordered. Pass = §6 idempotency drops/reorders; no double-action.
- **Crash recovery** — kill the poller mid-fix. Pass = lease expires, sweep reconciles against GitHub, no orphaned lock, no blind re-run.
- **Local-vs-cloud executor race (Codex r3 blocking test)** — run **two** fix executors contending for the same `(repo, pr, head_sha)` (the local poller plus a second executor — a second poller instance, or a stand-in for a cloud Action) and fire concurrent fix triggers. Pass = **exactly one** executor acquires the §6 lease and pushes; the other **coalesces or aborts-as-superseded**; **no double-push, no divergent heads, no lost update**, and the head-SHA revalidation (§5.2) blocks any push against a superseded head. This exercises the *real* contention Codex flagged, not single-process event replay.

*Exit gate (Phase 0):* identity map verified against probe ground truth; **zero** open threat-model defects; **zero** lock/idempotency defects on the replay corpus; all adversarial injection/workflow-mod cases contained; crash-recovery sweep verified; **the local-vs-cloud executor race shows exactly one pusher per head** (no double-push / divergent-head defect).

**Phase 1 — Flow-A triage bridge (LOCAL), read-only / advisory.**
Enable the local ntfy→filter→headless-triage path against the real ntfy stream. Claude **diagnoses and ntfy's its read; opens no PR, merges nothing.** Validates filter false-positive rate, dedup/cooldown, and the triage prompt in production with zero write risk. A **canary allowlist** limits which alert classes trigger triage at first.
*Exit gate (≥10 trading days):* filter false-positive < 10%; 0 re-fires within cooldown; 0 live-tree git ops; 0 production-path writes; budget guard exercised at least once; state store shows no lock anomalies.

**Phase 2 — GitHub review + LOCAL fix loop, behind §7 + §2.**
Turn on Codex auto-review (B, native, read-only) and the **local write-capable fix executor** (C, §5.2) **under the full §7 threat model**, on a **canary allowlist of repos/PRs** first (start with the sandbox + one low-risk repo), not the whole fleet. The `claude-code-action` cloud Action is **not** enabled as a fix pusher (option (a)); a cloud executor would appear only under option (b), which this RFC does not adopt. Flow A may now open draft PRs (`agent:auto-generated` + `agent:manual-hold`, merge-frozen per §2.1). Ordinary approved PRs auto-merge (unchanged); the high-risk set is surfaced. Round-cap, divergence, single-executor branch-lock (§6.5), head-SHA revalidation, budget guard, reviewer separation all enforced.
*Prerequisite:* `agent_workflows.py` merge step already refuses `agent:auto-generated`/`agent:manual-hold`, enforces approved-at-head, enforces the §3 verified identity map, and applies the §2.1 high-risk merge-freeze.
*Pre-registered pass criteria (must ALL hold at enablement — none may be open):*
- exact caps **X/Y/Z/W** (§8.4) are set to concrete numbers, not TBD;
- the **divergence metric** (§8.1) is a concrete, computed number, not "observed later";
- **zero** open threat-model (§7), lock/idempotency (§6), or injection (Phase 0) defects;
- the **local-vs-cloud executor race** (Phase 0) passes and the fix executor performs **head-SHA revalidation before every push**;
- reviewer separation verified against §3 ground truth (no same-logical-agent approval possible);
- round-cap + divergence demonstrated to fire on a real multi-round PR in the sandbox.

**Phase 3 — no auto-merge/deploy for the high-risk set, ever, without a new RFC.**
There is deliberately **no phase** that hands merge of the §2.1 high-risk set, pin-bump, deploy, or live-tree git to an agent. Ordinary-PR deterministic merge continues per §2.1. Any change to the high-risk boundary requires a **new RFC + explicit operator decision** — not a config flip.

---

## 10. Open questions (for Codex / operator)

1. **Local poller shape.** Should Flow A extend PR #197's `alert_log.jsonl` poller directly, or subscribe the poller to the ntfy `/json` stream? (r2's default: extend the existing local poller; ntfy stream only if the log is lossy.)
2. **Identity-map storage.** Where does the §3 verified `trusted_identity → logical_agent` table live — in `agent_workflows.py` as reviewed code, or a config the merge preflight loads? (Recommend: reviewed code, so a policy change is itself a §2.1-frozen PR.)
3. **State store choice.** SQLite file vs a small KV for the §6 store — both are local; which does the operator prefer for backup/inspection?
4. **`max_rounds_per_pr` & divergence signal.** Is 3 the right default? Divergence = unresolved-thread count vs raw comment count vs net-new-file-touched? (r2 uses unresolved-thread count; confirm.)
5. **Budget source of truth.** One reconciled ledger across headless + Action, or two independent guards? (r2 leans: two guards + a nightly reconcile, since the two spend sources live in different places.)
6. **n8n trigger threshold.** What *measured* signal (latency, fan-out target, host reachability) would flip the §4.2 decision to actually add n8n? Pre-agree the trigger so it is not a judgement call later.
7. **Escalation / hold UX.** On `ESCALATED` / `PAUSED` / a §2.1 merge-freeze, what exactly does the operator receive (ntfy with PR link + round history + last divergence metric + *why* it's frozen)? How is a `HELD` PR un-held?
8. **Cross-source idempotency.** A code-bug alert (Flow A) and a human-opened PR for the same bug could collide; the §6 dedup key should span both entry points — confirm the key formulation.
9. **Cloud-executor threshold (option b).** What *measured* requirement — if any — would ever force a cloud fix executor and thus the option-(b) shared transactional store (§6.5)? Pre-agree it, as with the n8n threshold (Q6), so it is not a later judgement call; absent it, option (a) is the standing decision.

---

## 11. Sources

- **Internal prior art (authoritative):** `doc/agent-pr-workflows.md` (the merge agreement r2 amends in §2), `src/renquant_orchestrator/agent_workflows.py` (`build_queue`, `merge_pr`, `PROD_PATH_RULES`, `STOP_LABELS`, distinct-actor preflight), `.github/CODEOWNERS`, `doc/design/2026-06-27-autonomous-ops-loops.md` (PR #197: allowlist, prompt-injection rules, numeric caps).
- **Claude Code headless** (`claude -p`, `--max-turns`, `--output-format stream-json`, `--allowedTools`): code.claude.com/docs/en/headless
- **Claude Code GitHub Action** (`@anthropics/claude-code-action`; event triggers; permissions): github.com/anthropics/claude-code-action — **not on the fix/push path under the chosen option (a)** (fix execution is the local poller, §5.2); relevant only to the deferred option (b) or a non-mutating triage that enqueues, and then only under the §7 cloud-Action hardening.
- **Codex GitHub review** (auto-review on PR-open / `@codex review`; app/bot identity): developers.openai.com/codex/integrations/github — actual review identity confirmed by the §3 probe, not assumed.
- **GitHub Actions security** — `pull_request` vs `pull_request_target`, least-privilege `permissions:`, immutable SHA action pins, fork-PR credential policy, `concurrency:` groups (serialize Action jobs only). GitHub Actions security-hardening docs.
- **n8n + ntfy** (only if §4.2's measured need appears): n8n Webhook node / community trigger `@jyln/n8n-nodes-ntfy` / ntfy `/json` event stream.
</content>
</invoke>
