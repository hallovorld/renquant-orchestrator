# Design: PR-review sweep loop — workflow note for this repo

DATE: 2026-07-05

STATUS: **NON-BINDING retrospective / heuristic discussion note.** This document
        is NOT operationally binding on its own, and merging this PR does not
        ratify any of the heuristics below as policy. Per `doc/memory/README.md`'s
        tier model, binding (LONG-tier) rules require **operator** authorship —
        the agent may transcribe them, not originate them (§1 of that spec:
        "LONG ... operator only (agent transcribes)"). This doc lives outside
        the LONG/MID/SHORT tiers entirely.

SCOPE: **Narrowed (round 2, per Codex review).** This note is about ONE concrete,
       orchestrator-repo-owned workflow: how a `/loop` session sweeping this
       repo's (and its pinned subrepos') open PRs for Codex review findings
       should sequence and parallelize that specific task. It is NOT a general
       agent-operating-policy document — it does not discuss loop behavior for
       arbitrary tasks, cross-repo authorization grants, or system-wide roadmap
       prioritization. Those are out of scope for a `renquant-orchestrator`
       design doc, because this repo does not own or enforce policy across the
       whole agent/session system (see §4 below). Content of that kind that
       was in round 1 of this doc has been cut, not merely re-hedged.

---

## 0. Problem statement (PR-review-sweep specific)

The recurring PR-review-sweep task (check all open PRs across the repos this
session touches → fix genuine Codex findings → merge when ready → repeat) has
two concrete failure modes worth a workflow note:

1. **Single-threaded blocking**: waiting for one PR's review before starting
   work on another PR, when the PRs are independent.
2. **Review ping-pong**: opening a new "v2" PR to address review feedback
   instead of pushing a fix to the existing branch, fragmenting the review
   history across superseding PRs.

## 1. Sweep-tick workflow

For this specific task (not a general loop-behavior claim):

1. **List** open PRs across the repos in scope (this repo + relevant pinned
   subrepos, per `RENQUANT_REPOS.md`).
2. **Check both** `reviews` and plain `comments` for each PR — Codex sometimes
   leaves findings as comments rather than formal reviews (a real gap this
   session had to correct for after several sweep passes missed comment-only
   findings — see `doc/progress/` entries from 2026-07-04 for the incident).
3. **Fan out**: for independent PRs with genuine findings, dispatch parallel
   fixes rather than fixing one PR fully before starting the next — reviews
   happen in the background regardless of which PR is being worked on next.
4. **Verify before reporting**: confirm a dispatched fix's commit actually
   landed (`gh pr view <n> --json headRefOid`, and prefer the raw
   `git/refs/heads/<branch>` API when the PR-object cache lags) before
   describing it as fixed — a worker reporting completion is not the same as
   a worker having pushed a commit.
5. **Merge only when genuinely ready**: current-head approval, green CI, no
   self-review deadlock — this repo's existing merge protocol (see
   `doc/AGENT-RETROSPECTIVE.md`) already governs this; this note does not
   redefine it.

## 2. Anti-patterns specific to this workflow

1. **Serial review dependency when avoidable**: waiting for one PR's review
   before starting unrelated, independent PR work in this same sweep.
2. **Opening a superseding PR instead of pushing a fix**: fragments review
   history; push to the existing branch unless the existing PR is genuinely
   unrecoverable (e.g. rebasing onto an incompatible branch state).
3. **Reporting "fixed" without re-verifying the commit landed**: a dispatched
   worker's own summary is not proof of a push — check the actual ref.

## 3. What this note does NOT claim

This note does not propose or describe: general task prioritization across the
roadmap, cross-repo authorization grants, terminal-state definitions for
non-PR-review work, or any change to how loop wakeups/scheduling work outside
this specific sweep task. Prior drafts of this document (round 1) discussed
those topics; per Codex's round-2 review, that content is out of scope for a
`renquant-orchestrator` design doc and has been removed rather than re-framed
as non-binding. If any of that broader material is still considered valuable,
it needs a different home — proposed through the umbrella repo's actual
instruction-source files (`doc/memory/long-term-agreements.md` / `CLAUDE.md`),
by the operator, not authored here.

## 4. Relationship to this repo's authority tiers

- **`doc/AGENT-RETROSPECTIVE.md`**: the compliance/quality framework — this
  note does not override it.
- **`doc/memory/long-term-agreements.md`** / **`CLAUDE.md`**: the actual hard
  safety boundaries and operating rules (LONG tier — binding, operator-authored
  only per `doc/memory/README.md` §1). This note is subordinate to both in
  every respect and does not become binding by merging.
- This repo (`renquant-orchestrator`) orchestrates pinned subrepos and
  schedules/verifies workflows; it does not own or enforce policy for how
  agent sessions behave in general, across repos, or across tasks unrelated
  to this PR-review sweep. That authority question is explicitly out of
  scope here (see §3).
