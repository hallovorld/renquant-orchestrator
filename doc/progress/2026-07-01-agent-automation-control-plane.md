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

REVIEW ROUND 2 (Codex CHANGES_REQUESTED — the round-1 lease/fence fixes were
accepted, but the EVENT/STATE crash boundary was still not exactly-once; the
event claim had no owner/lease, and cancellation was in-memory only):

1. **Claim + state mutation + applied marker were separate commits.** A crash
   after a transition but before `mark_event_applied` re-drove the event from
   the NEW state on redelivery → a non-idempotent handler could raise an illegal
   transition or bump the round counter twice. FIX: every FINAL transition is
   now FOLDED with the applied marker in ONE `BEGIN IMMEDIATE` transaction
   (`transition_and_apply`), and the fix round's counter-bump + `FIXING`/
   `ESCALATED` decision is folded too (`begin_fix_round`). `_process_claimed` is
   resume-idempotent: it dispatches off the CURRENT durable state — a row found
   at `FIXING` RESUMES the executor without a second `begin_fix_round` (counter
   never inflated), a terminal/`MERGE_ELIGIBLE` row short-circuits + applies.
   The terminal action (outcome/detail) is persisted with the marker
   (`result_json`) so a true duplicate is answered from the ledger.
2. **Concurrent deliveries could both enter `_process_claimed`.** The processing
   row had no owner/lease. FIX: `claim_event(event, owner, ttl)` gives the event
   an EXCLUSIVE processing lease — a concurrent delivery by a DIFFERENT owner is
   refused (`in_progress`), reclaimable only after that lease expires; the SAME
   owner may resume its own claim at once (so an in-process redelivery re-drives
   immediately instead of stalling). Two-owner exclusion is what makes state
   application at-most-once, not merely coalesced.
3. **Cancellation was cooperative/in-memory only.** FIX: durable ownership +
   heartbeat + hard-kill seam — `heartbeat` (only the live `owner`+`fence` holder
   renews; a hung executor stops heart-beating and its lease expires),
   `request_cancellation`/`is_cancellation_requested` (a PERSISTED flag is the
   cross-restart source of truth an executor polls, not a poller token), and
   `list_uncooperative_cancellations` + a `TerminationHook` the poller invokes at
   `startup_recover` for any run whose retained lease expired without ack — a
   SQLite flag alone cannot stop untrusted work, so the hard kill is an explicit,
   observable mechanism (default hook records the obligation; no real executor
   yet). Sandbox stays stubbed; NO push/merge; human-gate wall unchanged.

Crash-injection tests added at every boundary the reviewer enumerated — after
claim (supersede), after supersede (ensure_row), at lease-acquire, after the
state transition (executor crash → resume from `FIXING`, counter not double-
bumped), after the executor result (`transition_and_apply` crash → resume), and
before the applied marker (round-cap `mark_event_applied` crash) — plus
two-concurrent-deliveries (an owner-held claim refuses a second poller; a
threaded race drives exactly once). Evidence updated:
`tests/test_agent_automation_poller.py` now 64 tests →
`… -m pytest tests/test_agent_automation_poller.py -q` → 64 passed;
`git diff --check` clean.

REVIEW ROUND 3 (Codex CHANGES_REQUESTED — the exact-once path from round 2
still could LOSE valid work under contention/crash, distinct from the event-id
duplicate bug round 2 fixed):

1. **PR-lease coalescing marked the source event `applied` regardless of
   whether its work ran.** When `acquire` coalesced an event (another live
   lease already held for a DIFFERENT `(head_sha, review_id)` row of the same
   PR — `pending_rerun` flagged) — or lost the same-key CAS race
   (`"lease already held"`) — all three drivers (`_drive_merge_eligible`,
   `_drive_fixing`, `_resume_fix`) unconditionally called
   `mark_event_applied`. The event's OWN intended transition never ran, but it
   was now permanently a "duplicate" on any redelivery — if the blocking
   holder then crashed, or was doing DIFFERENT work, that work was silently
   lost forever. FIX: a new `AutomationPoller._handle_lease_contention`
   distinguishes the acquire-failure reason. `"superseded: ..."` (a NEWER
   head already cancelled this row via `supersede_stale`) is the ONLY case
   safe to mark applied — the newer head's own event drives the equivalent
   work under a different, non-superseded row, and this row can never be
   un-superseded, so leaving it un-applied would just make it a permanent
   no-op reprocessed on every redelivery for nothing. `"coalesced: ..."` /
   `"lease already held"` are left UN-applied — the event stays `processing`
   in the idempotency ledger (never a false `duplicate`) and the row keeps
   `pending_rerun=1`, so a later redelivery (the same owner's next poll tick,
   or — after the blocking holder crashes — once `reconcile_expired_leases`
   (via `startup_recover`) clears its dangling lease) re-examines and
   actually executes it. `acquire`'s successful CAS also now clears
   `pending_rerun` (it was previously set-only, dead for observability).
2. Tests added (3, exactly the review's required scenarios): (1) two
   concurrent events on the same PR where the second coalesces — asserts it is
   NOT applied at coalesce time and a later redelivery actually executes its
   fix round (`test_coalesced_event_not_applied_and_redelivery_completes_it`);
   (2) the current lease holder crashes while a coalesced event is pending —
   asserts `startup_recover`'s expiry-sweep frees the dangling PR lease so
   redelivery completes the coalesced event, never permanently stuck
   `applied`-without-execution
   (`test_startup_recover_lets_coalesced_event_complete_after_holder_crash`);
   (3) a coalesced event genuinely superseded by a newer head's equivalent
   transition correctly ends up applied — proving the fix does not over-correct
   into "never mark applied"
   (`test_coalesced_event_superseded_by_newer_head_ends_applied`).

Evidence updated: `tests/test_agent_automation_poller.py` now 67 tests →
`/Users/renhao/git/github/RenQuant/.venv/bin/python -m pytest
tests/test_agent_automation_poller.py -q` → 67 passed; `git diff --check`
clean.

NEXT: (1) ephemeral OS/container/VM sandbox executor behind
`run_fix_in_sandbox` (design §7.5) + Phase-0 escape/exfiltration suite; (2) live
GitHub read-only event feed into `ingest`; (3) integrate the existing
deterministic merge authority for ordinary-PR `MERGE_ELIGIBLE→MERGED` and the
surface-to-human path for the §2.1 high-risk set.
