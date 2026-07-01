# Agent-automation control plane (Phase-0/1) — #209

STATUS: delivered (control-plane core; sandbox executor stubbed as explicit follow-up)

WHAT: Implemented the SAFE deterministic control plane from the merged design
`doc/design/2026-06-30-agent-automation-closed-loop.md` (§5 flow, §6 atomic
state/lease store, §6.3 single-owner transitions, §9 phased rollout), WITHOUT
any untrusted-code execution. New module
`src/renquant_orchestrator/agent_automation_poller.py`:

- **Atomic SQLite state/lease store** keyed by `(repo, pr_number, head_sha,
  review_id)`: compare-and-set `acquire` (two acquirers → one wins), lease +
  TTL/expiry, event idempotency via `processed_events` (a duplicate delivery id
  is processed once), stale-run cancellation on `head_sha` advance, PR-busy
  coalescing (`pending_rerun`), and crash-recovery `reconcile_expired_leases`
  (reconciles against optional ground truth before reclaiming). One writer owns
  each transition; poller transitions require holding the lease.
- **State machine** `ALERT_RECEIVED → TRIAGING → PR_OPEN → AWAIT_REVIEW ⇄
  FIXING → MERGE_ELIGIBLE → HUMAN_GATE → {MERGED|HELD}` + terminals
  `DROPPED/ADVISORY_ONLY/ESCALATED/PAUSED`, as an actor-scoped edge table
  (`POLLER` / `MERGE_AUTHORITY` / `HUMAN`). **Human-gate wall by construction:**
  NO edge into `MERGED` admits the poller, and the poller's authority ends at
  `MERGE_ELIGIBLE` — ordinary approved PRs are still merged by the existing
  deterministic authority in `agent_workflows.py`; the high-risk set (§2.1) is
  surfaced to a human. `classify_merge_risk` reuses
  `agent_workflows.PROD_PATH_RULES`/`STOP_LABELS` (composes, does not weaken the
  distinct-identity/self-review protections).
- **Event ingestion + poller loop** (read-only): `AutomationPoller.ingest`
  filters by allowlist → idempotency → stale-cancel → drives the legal
  transition. The `FIXING` executor is a `StubSandboxExecutor.run_fix_in_sandbox`
  raising `NotImplementedError("ephemeral sandbox executor — follow-up PR")`; a
  fix attempt therefore ESCALATES rather than running anything untrusted. NO
  push, NO merge, NO credentials wired.
- **Config-driven allowlists + `--dry-run`**: `PollerConfig`
  (tracked repos/PRs, lease TTL, `max_rounds_per_pr`), an offline replay harness
  (`run_replay`, design §9 Phase-0 shadow/replay), and a new `agent-automation`
  CLI subcommand.

WHY/DIR: The design merged as docs-only; this lands the Phase-0/1 spine the
operator currently drives by hand, with the dangerous hops (untrusted-code
sandbox, auto-merge, push) deliberately excluded/stubbed behind clear
interfaces so nothing untrusted can run yet.

EVIDENCE:
- artifact: `tests/test_agent_automation_poller.py` (43 tests) —
  `/Users/renhao/git/github/RenQuant/.venv/bin/python -m pytest
  tests/test_agent_automation_poller.py -q` → 43 passed. Covers atomic lease
  (two acquirers → one wins), idempotency (duplicate id), stale-cancel on
  `head_sha` change, legal/illegal transitions, human-gate wall (no auto edge to
  MERGED), crash-recovery reconcile, round-cap/escalation, dry-run (executor
  never invoked), allowlist filtering, and merge-risk classification. All time
  injected via `FakeClock` (no wall-clock dependence); no network.
- prod or exp: exp — new control-plane module + CLI; not wired to any live poll,
  no push/merge path, sandbox stubbed. Nothing touches the live umbrella tree.
- existing data: n/a — pure control-plane logic over in-memory/SQLite state and
  synthetic event fixtures; no market/model data.
- best-known?: yes — composes with `agent_workflows.py` (reuses its
  `PROD_PATH_RULES`/`STOP_LABELS`, does not duplicate the merge authority) and
  matches `doc/agent-pr-workflows.md`'s deterministic-merge-for-ordinary /
  human-hold-for-high-risk policy.
- scope: `renquant-orchestrator` control plane only; ephemeral sandbox executor,
  live GitHub polling, and any push/merge wiring are explicit follow-up PRs.

NEXT: (1) ephemeral OS/container/VM sandbox executor behind
`run_fix_in_sandbox` (design §7.5) + Phase-0 escape/exfiltration suite; (2) live
GitHub read-only event feed into `ingest`; (3) integrate the existing
deterministic merge authority for ordinary-PR `MERGE_ELIGIBLE→MERGED` and the
surface-to-human path for the §2.1 high-risk set.
