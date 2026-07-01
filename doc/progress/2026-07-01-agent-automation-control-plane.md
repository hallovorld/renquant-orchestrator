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

REVIEW ROUND 1 (Codex CHANGES_REQUESTED — 5 distributed-systems correctness
bugs in the lease/state core; all fixed, the core must be correct because the
follow-up sandbox/push executor relies on it):

1. **Cross-key PR lease race.** `acquire` did the PR-busy SELECT and the row
   UPDATE as SEPARATE transactions, so two workers on different
   `(head_sha, review_id)` rows of the same PR could both see `busy=0` and each
   acquire. FIX: the store now runs in autocommit + an explicit
   `_immediate()` (`BEGIN IMMEDIATE`) critical section wraps the busy check AND
   the row acquisition in ONE serialised transaction. Test:
   barrier-based two-connection race on DIFFERENT keys of the same PR → exactly
   one acquires, the other coalesces.
2. **Transition not fenced by the lease.** `transition` checked `holds_lease`
   then UPDATEd on old-state only. FIX: the POLLER state UPDATE is atomic —
   `state=frm AND superseded=0 AND lease_owner=owner AND lease_expiry>now` in one
   statement — PLUS a monotonic `fence` generation (bumped on every acquire,
   threaded through `transition`/`release`) so a reclaimed old worker reusing the
   same `owner` id carries a stale fence and can never commit. Tests:
   expiry-during-transition + reclaim-then-stale-fence.
3. **Event idempotency could lose events on crash.** `record_event` committed
   the delivery id BEFORE the mutation → a crash left it "duplicate forever".
   FIX: a `received/processing/applied` inbox — `record_event` CLAIMS
   `processing` (a mid-flight redelivery is re-drivable), and
   `mark_event_applied` closes the window only AFTER the driven transition
   commits. Tests: crash-injection at each boundary (supersede / ensure_row /
   mark_applied) + applied-is-true-duplicate control.
4. **Supersede did not cancel the in-flight executor.** FIX: `CancellationToken`
   plumbed into `run_fix_in_sandbox`; supersede RETAINS the PR-level lease
   (`cancel_requested`) until the executor acknowledges
   (`acknowledge_cancellation` / fenced `release`), a crashed old run's dangling
   lease is swept once expired, and every exported patch is fenced by
   `fence_ok(fence, head_sha)` — a stale/superseded run's output is discarded,
   never applied. Tests: token acknowledged, stale-patch fenced, dangling-lease
   sweep.
5. **Dry-run wedged state in `FIXING`.** FIX: dry-run no longer mutates durable
   workflow state (no attempt bump, no `FIXING` transition) — the row stays at
   `AWAIT_REVIEW`. Test: repeated changes-requested no longer hits an illegal
   `FIXING → FIXING`.

Evidence updated: `tests/test_agent_automation_poller.py` now 54 tests →
`… -m pytest tests/test_agent_automation_poller.py -q` → 54 passed;
`git diff --check` clean.

NEXT: (1) ephemeral OS/container/VM sandbox executor behind
`run_fix_in_sandbox` (design §7.5) + Phase-0 escape/exfiltration suite; (2) live
GitHub read-only event feed into `ingest`; (3) integrate the existing
deterministic merge authority for ordinary-PR `MERGE_ELIGIBLE→MERGED` and the
surface-to-human path for the §2.1 high-risk set.
