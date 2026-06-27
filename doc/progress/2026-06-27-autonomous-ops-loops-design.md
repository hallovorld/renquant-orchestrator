# Autonomous ops + PR-review loops — design proposal

2026-06-27.

## What & why
Operator asked for self-driving, subagent-executed loops, **script-first** (an LLM
subagent only where judgment is irreducible), every change via PR + Codex review
(never self-merge, never git in the live tree, never auto-touch live
state/model/data). Three loops, one operating model:
0. **Loop 0 — PR-review watcher**: discover new/updated PRs → review Codex's, fix
   Codex's comments on mine, merge good ones (account-separated). The operator's
   main repeated workflow, now first-class.
1. **Loop 1 — error-responder**: ntfy ERROR → code bug: fix in a /tmp clone + PR;
   operational/live: ntfy a human, do NOT auto-change.
2. **Loop 2 — post-daily reviewer**: validate the decision tree → if sound, run the
   trade-review (fundamentals/technical/analyst) → ntfy only when a change is warranted.

This PR is the **design for Codex to discuss/review** — no code yet.

## Decided safety contracts (NOT open questions)
The risky decisions are pinned as hard defaults in the design (§4, §6):
- **Draft-PR-only + reviewer separation by account**: loop PRs are drafts labeled
  `agent:auto-generated`+`agent:manual-hold`; the agent-pr-loop must be **amended +
  audited** (a Phase-2 prerequisite, NOT inherited) to refuse those labels, enforce
  current-head approval, and never let the creating account merge — closing the
  error→PR→auto-merge path.
- **Hard allowlist** of auto-fix surfaces (tests/docs/non-wired scripts only);
  anything live (trade logic, gates, broker, state, model/data provenance,
  freshness) is diagnosis-only even for a "code bug".
- **Prompt-injection**: logs/alerts/artifacts/trade-review are untrusted DATA,
  quoted as evidence only, never instructions; classifier is a fixed rule table.
- **Loop-2 freshness/provenance gate** → "insufficient evidence" on stale/missing.
- **Numeric caps**: per-loop agent-spawn caps, ≤2 open auto-PRs, ≤120k tokens/spawn,
  ≤1M/day hard-stop.
- **Measurable per-phase acceptance gates** (§6): FP rate, dedup, max PRs/day,
  spend, audited 0 live-tree git + 0 live writes, reviewer separation.

## How it was grounded
Three read-only Explore subagents mapped the existing infra (agent-pr-loop pattern;
the `alert_log.jsonl` poll signal + dedup keys; the decision-trace integrity +
gate_verdicts + trade-review assets) so the build is assembly, not invention.

## Deliverable
- `doc/design/2026-06-27-autonomous-ops-loops.md` — the full proposal (Loop 0/1/2,
  script-first, the safety contracts above, where code lands, phased rollout).

## Next
Codex review → implementation in separate PRs after sign-off, starting with the
agent-pr-loop amendment (the prerequisite) and Phase-0 dry-run.
