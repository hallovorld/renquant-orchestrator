# Autonomous ops loops — design proposal

2026-06-27.

## What & why
Operator asked for two self-driving, subagent-executed loops, all changes via PR +
Codex review (never self-merge, never git in the live tree, never auto-touch live
state/model/data):
1. ntfy ERROR → auto-investigate → (code bug) fix in a clone + PR + ntfy; (operational/live) ntfy a human, don't auto-change.
2. post-daily-full → verify the decision tree → if sound, run a fundamentals/technical/analyst trade-reliability review → ntfy only when a change is warranted.

This PR is the **design proposal for Codex to discuss/review** — no code yet.

## How it was grounded
Three read-only Explore subagents mapped the existing infra so the design is
assembly, not invention: (a) the `agent-pr-loop` pattern (launchd → wrapper →
headless `claude -p` via stdin + `agent_workflows.py` control-plane); (b) the ntfy
publisher + the verified poll signal `logs/alerts/alert_log.jsonl` (status/taxonomy/
dedup-key); (c) the post-daily completion marker + `validate_decision_trace_integrity`
+ `gate_verdicts`/`decision_ledger` + the `trade-review` skill scripts.

## Deliverable
- `doc/design/2026-06-27-autonomous-ops-loops.md` — full proposal: shared
  foundation, each loop's trigger/classification/action, cross-cutting guardrails,
  where code lands, open questions, phased rollout (dry-run → Loop 2 → Loop 1).

## Key safety stance (from this session's lessons)
- Loops only OPEN PRs / send ntfy — they never merge (the existing agent-pr-loop
  does codex review + merge).
- The error-responder auto-fixes CODE bugs only (with a regression test, in a /tmp
  clone); anything touching live state/model/data → ntfy a human, never auto-change.
- Verify-before-asserting baked in: every emitted finding must cite its data/log.

## Next
Codex review on the open questions (classifier conservatism, auto-fix vs draft-only,
rate/cost caps, rollout). Implementation follows in separate PRs after sign-off.
