"""Deterministic tests for the agent-automation control plane.

Covers the design's safety-critical invariants (doc/design/2026-06-30-agent-
automation-closed-loop.md §6 atomic store, §6.3 single-owner transitions, §9):

  * atomic lease (two acquirers → exactly one wins);
  * event idempotency (a duplicate review/event id is processed once);
  * stale-run cancellation when ``head_sha`` advances;
  * state-machine legal / illegal transitions;
  * the human-gate wall — NO automated edge reaches ``MERGED``;
  * crash-recovery reconcile of an expired lease.

All time is injected (no wall-clock dependence), and no test touches the
network — the FIXING executor is stubbed and never runs untrusted code.
"""
from __future__ import annotations

import sqlite3

import pytest

from renquant_orchestrator.agent_automation_poller import (
    Actor,
    AutomationPoller,
    CancellationToken,
    ClaimResult,
    Event,
    ExecutorCancelled,
    FixResult,
    IllegalTransition,
    NoopTerminationHook,
    PollerConfig,
    RecoverySummary,
    State,
    StateStore,
    StubSandboxExecutor,
    WorkKey,
    assert_transition,
    classify_merge_risk,
    is_high_risk,
    merged_is_wall_protected,
    run_poll_loop,
    run_replay,
    transition_allowed,
)


class FakeClock:
    """Deterministic, manually-advanced clock (seconds)."""

    def __init__(self, start: float = 1_000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


def _config(**over) -> PollerConfig:
    base = dict(
        tracked_repos=("hallovorld/renquant-orchestrator",),
        tracked_prs={},
        lease_ttl_seconds=100.0,
        max_rounds_per_pr=3,
        dry_run=False,
        owner="poller-1",
    )
    base.update(over)
    return PollerConfig(**base)


def _event(**over) -> Event:
    base = dict(
        event_id="evt-1",
        repo="hallovorld/renquant-orchestrator",
        pr_number=42,
        head_sha="sha-a",
        kind="review",
        state="CHANGES_REQUESTED",
        review_id="rev-1",
        body="please fix",
    )
    base.update(over)
    return Event(**base)


# ─────────────────────────── atomic lease ───────────────────────────────


def test_atomic_lease_two_acquirers_one_wins(tmp_path):
    """Two acquirers on the SAME key → exactly one wins (CAS on the row)."""
    clock = FakeClock()
    db = str(tmp_path / "state.db")
    store_a = StateStore(db, clock=clock)
    store_b = StateStore(db, clock=clock)  # a second worker, same file
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store_a.ensure_row(key, State.AWAIT_REVIEW)

    first = store_a.acquire(key, "worker-a", ttl=100.0)
    second = store_b.acquire(key, "worker-b", ttl=100.0)

    assert first.acquired is True
    assert second.acquired is False
    assert store_a.holds_lease(key, "worker-a") is True
    assert store_b.holds_lease(key, "worker-b") is False
    store_a.close()
    store_b.close()


def test_lease_reacquirable_after_release():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.AWAIT_REVIEW)
    assert store.acquire(key, "w1", ttl=100.0).acquired is True
    assert store.release(key, "w1") is True
    assert store.acquire(key, "w2", ttl=100.0).acquired is True


def test_expired_lease_is_reclaimable_by_cas():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.AWAIT_REVIEW)
    assert store.acquire(key, "w1", ttl=100.0).acquired is True
    # a second acquirer cannot take a live lease
    assert store.acquire(key, "w2", ttl=100.0).acquired is False
    clock.advance(101.0)  # lease expires
    assert store.acquire(key, "w2", ttl=100.0).acquired is True


def test_second_fix_on_different_head_coalesces():
    """A live lease on one head → a fix on a DIFFERENT head/review of the same
    PR coalesces (pending_rerun) instead of starting a concurrent run."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    key_a = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    key_b = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-2")
    store.ensure_row(key_a, State.AWAIT_REVIEW)
    assert store.acquire(key_a, "w1", ttl=100.0).acquired is True

    result = store.acquire(key_b, "w2", ttl=100.0)
    assert result.acquired is False
    assert "coalesced" in result.reason
    row_b = store.get_row(key_b)
    assert row_b["pending_rerun"] == 1


# ─────────────────────────── idempotency ────────────────────────────────


def test_claim_event_exclusive_then_apply():
    """Claim/apply ledger (review point 3): the FIRST delivery gets an EXCLUSIVE
    processing claim (owner + lease); a concurrent delivery by a DIFFERENT owner
    is refused (in_progress); the SAME owner may resume its own claim at once;
    and only a fully APPLIED id is a true duplicate — carrying its recorded
    terminal result so it is answered from the ledger, not re-driven."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    evt = _event(event_id="rev-1")

    first = store.claim_event(evt, owner="poller-A", ttl=100.0)
    assert isinstance(first, ClaimResult)
    assert first.proceed is True and first.disposition == "new"

    # a DIFFERENT owner cannot claim while poller-A's processing lease is LIVE —
    # this is what makes two concurrent deliveries at-most-once, not coalesced
    contend = store.claim_event(evt, owner="poller-B", ttl=100.0)
    assert contend.proceed is False and contend.disposition == "in_progress"

    # the SAME owner may reclaim immediately (its own crash / redelivery) rather
    # than stall until its own lease TTL elapses
    same = store.claim_event(evt, owner="poller-A", ttl=100.0)
    assert same.proceed is True and same.disposition == "reclaimed"

    # not yet applied → still re-drivable, never a silent "duplicate" that loses
    # work (the point-3 bug)
    assert store.event_applied("rev-1") is False
    store.mark_event_applied("rev-1", result_json='{"outcome": "escalated"}')

    # now truly applied → a genuine duplicate, and the recorded result is carried
    dup = store.claim_event(evt, owner="poller-A", ttl=100.0)
    assert dup.proceed is False and dup.disposition == "applied"
    assert dup.result_json == '{"outcome": "escalated"}'
    assert store.event_seen("rev-1") is True
    assert store.event_applied("rev-1") is True


def test_claim_event_reclaimable_by_other_owner_only_after_lease_expiry():
    """A crashed owner's processing claim is reclaimed by ANOTHER owner ONLY
    after the processing lease TTL — never while the prior owner might be live."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    evt = _event(event_id="rev-x")
    assert store.claim_event(evt, owner="A", ttl=100.0).proceed is True
    assert store.claim_event(evt, owner="B", ttl=100.0).proceed is False  # A live
    clock.advance(101.0)  # A's processing lease expires (A crashed mid-flight)
    reclaimed = store.claim_event(evt, owner="B", ttl=100.0)
    assert reclaimed.proceed is True and reclaimed.disposition == "reclaimed"


def test_poller_drops_duplicate_review_event():
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)
    evt = _event(event_id="rev-dup", state="CHANGES_REQUESTED")

    first = poller.ingest(evt)
    second = poller.ingest(evt)

    assert first.outcome == "escalated"  # stubbed sandbox → escalate
    assert second.outcome == "duplicate"
    # only one work-item row, attempted exactly once
    rows = store.snapshot()
    assert len(rows) == 1
    assert rows[0]["attempt"] == 1


# ─────────────────────── stale-run cancellation ─────────────────────────


def test_stale_cancel_retains_lease_until_ack():
    """Supersede requests cancellation and RETAINS the PR-level lease until the
    in-flight executor acknowledges (design §6.3 / review point 4)."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    old = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    store.ensure_row(old, State.AWAIT_REVIEW)
    acq = store.acquire(old, "w1", ttl=100.0)

    superseded = store.supersede_stale("hallovorld/renquant-orchestrator", 42, "sha-new")

    assert old in superseded
    assert store.is_superseded(old) is True
    row = store.get_row(old)
    assert row["lease_owner"] == "w1"       # lease RETAINED until acknowledged
    assert row["cancel_requested"] == 1
    # the stale run's exported output is fenced out regardless
    assert store.fence_ok(old, acq.fence, "sha-old") is False
    # once the executor acknowledges, the retained lease is dropped
    assert store.acknowledge_cancellation(old) is True
    assert store.get_row(old)["lease_owner"] is None


def test_poller_supersedes_old_head_on_new_event():
    clock = FakeClock()
    store = StateStore(clock=clock)
    # dry-run leaves the row at AWAIT_REVIEW (non-terminal) without mutating
    # durable state, so a new head can still supersede the old head's row.
    poller = AutomationPoller(_config(dry_run=True), store)

    poller.ingest(_event(event_id="e-old", head_sha="sha-old", review_id="rev-1"))
    old = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    assert store.get_state(old) == State.AWAIT_REVIEW  # dry-run: no wedge

    poller.ingest(_event(event_id="e-new", head_sha="sha-new", review_id="rev-2"))
    new = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-new", "rev-2")
    assert store.is_superseded(old) is True   # stale head cancelled
    assert store.is_superseded(new) is False


def test_superseded_row_cannot_transition():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    store.ensure_row(key, State.AWAIT_REVIEW)
    store.supersede_stale("hallovorld/renquant-orchestrator", 42, "sha-new")
    store.acquire(key, "w1", ttl=100.0)
    with pytest.raises(IllegalTransition):
        store.transition(key, State.FIXING, actor=Actor.POLLER, owner="w1",
                         require_lease=False)


# ───────────────────── state-machine legal / illegal ────────────────────


@pytest.mark.parametrize(
    "frm,to,actor",
    [
        (State.ALERT_RECEIVED, State.TRIAGING, Actor.POLLER),
        (State.TRIAGING, State.PR_OPEN, Actor.POLLER),
        (State.PR_OPEN, State.AWAIT_REVIEW, Actor.POLLER),
        (State.AWAIT_REVIEW, State.FIXING, Actor.POLLER),
        (State.FIXING, State.AWAIT_REVIEW, Actor.POLLER),
        (State.AWAIT_REVIEW, State.MERGE_ELIGIBLE, Actor.POLLER),
        (State.HUMAN_GATE, State.MERGED, Actor.HUMAN),
        (State.HUMAN_GATE, State.HELD, Actor.HUMAN),
        (State.MERGE_ELIGIBLE, State.HUMAN_GATE, Actor.MERGE_AUTHORITY),
    ],
)
def test_legal_transitions(frm, to, actor):
    assert transition_allowed(frm, to, actor) is True
    assert_transition(frm, to, actor)  # does not raise


@pytest.mark.parametrize(
    "frm,to,actor",
    [
        # skipping states
        (State.ALERT_RECEIVED, State.MERGE_ELIGIBLE, Actor.POLLER),
        (State.AWAIT_REVIEW, State.MERGED, Actor.POLLER),
        # wrong actor
        (State.HUMAN_GATE, State.MERGED, Actor.POLLER),
        (State.MERGE_ELIGIBLE, State.MERGED, Actor.POLLER),
        (State.MERGE_ELIGIBLE, State.HUMAN_GATE, Actor.POLLER),
        # out of a terminal state
        (State.MERGED, State.AWAIT_REVIEW, Actor.HUMAN),
        (State.DROPPED, State.TRIAGING, Actor.POLLER),
    ],
)
def test_illegal_transitions(frm, to, actor):
    assert transition_allowed(frm, to, actor) is False
    with pytest.raises(IllegalTransition):
        assert_transition(frm, to, actor)


def test_store_transition_requires_lease_for_poller():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.AWAIT_REVIEW)
    # no lease held → poller transition rejected
    with pytest.raises(IllegalTransition):
        store.transition(key, State.FIXING, actor=Actor.POLLER, owner="w1")
    store.acquire(key, "w1", ttl=100.0)
    assert store.transition(key, State.FIXING, actor=Actor.POLLER, owner="w1") == State.FIXING


# ────────────────────────── human-gate wall ─────────────────────────────


def test_human_gate_wall_no_automated_edge_to_merged():
    """The core safety invariant: NO transition into MERGED admits the poller,
    and the poller can never leave MERGE_ELIGIBLE."""
    assert merged_is_wall_protected() is True
    # exhaustive: from every state, the poller cannot reach MERGED
    for frm in State:
        assert transition_allowed(frm, State.MERGED, Actor.POLLER) is False
    # the poller's authority stops at MERGE_ELIGIBLE
    assert transition_allowed(State.MERGE_ELIGIBLE, State.MERGED, Actor.POLLER) is False
    assert transition_allowed(State.MERGE_ELIGIBLE, State.HUMAN_GATE, Actor.POLLER) is False
    # only a human crosses the gate
    assert transition_allowed(State.HUMAN_GATE, State.MERGED, Actor.HUMAN) is True


def test_poller_stops_at_merge_eligible_on_approval():
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)
    action = poller.ingest(_event(event_id="appr-1", state="APPROVED", review_id="rev-9"))
    assert action.outcome == "merge_eligible"
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-9")
    assert store.get_state(key) == State.MERGE_ELIGIBLE
    # nothing progressed past the wall
    assert not any(r["state"] in (State.MERGED.value, State.HUMAN_GATE.value)
                   for r in store.snapshot())


def test_store_rejects_poller_merge_attempt():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.MERGE_ELIGIBLE)
    store.acquire(key, "w1", ttl=100.0)
    with pytest.raises(IllegalTransition):
        store.transition(key, State.MERGED, actor=Actor.POLLER, owner="w1")
    with pytest.raises(IllegalTransition):
        store.transition(key, State.HUMAN_GATE, actor=Actor.POLLER, owner="w1")


# ───────────────────── stubbed sandbox executor ─────────────────────────


def test_sandbox_executor_is_stubbed():
    with pytest.raises(NotImplementedError, match="ephemeral sandbox executor"):
        StubSandboxExecutor().run_fix_in_sandbox(
            repo="r", pr_number=1, head_sha="s", review_comments=["x"]
        )


def test_fixing_event_escalates_because_sandbox_stubbed():
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)
    action = poller.ingest(_event(event_id="cr-1", state="CHANGES_REQUESTED"))
    assert action.outcome == "escalated"
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    assert store.get_state(key) == State.ESCALATED


def test_dry_run_never_invokes_executor():
    clock = FakeClock()
    store = StateStore(clock=clock)

    class ExplodingExecutor:
        def run_fix_in_sandbox(self, **kwargs):
            raise AssertionError("executor must not run in dry-run")

    poller = AutomationPoller(_config(dry_run=True), store, executor=ExplodingExecutor())
    action = poller.ingest(_event(event_id="cr-dry", state="CHANGES_REQUESTED"))
    assert action.outcome == "fixing_dry_run"
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    # dry-run must NOT mutate durable workflow state: no FIXING wedge, no attempt
    assert store.get_state(key) == State.AWAIT_REVIEW
    assert store.get_row(key)["attempt"] == 0


def test_dry_run_repeated_changes_requested_no_illegal_transition():
    """Regression (review point 5): a dry-run must not wedge the row in FIXING,
    so a SECOND changes-requested event does not attempt an illegal
    FIXING -> FIXING and blow up."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(dry_run=True), store)

    a1 = poller.ingest(_event(event_id="cr-1", state="CHANGES_REQUESTED"))
    a2 = poller.ingest(_event(event_id="cr-2", state="CHANGES_REQUESTED"))

    assert a1.outcome == "fixing_dry_run"
    assert a2.outcome == "fixing_dry_run"  # not an IllegalTransition crash
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    assert store.get_state(key) == State.AWAIT_REVIEW  # never wedged in FIXING


def test_round_cap_escalates():
    clock = FakeClock()
    store = StateStore(clock=clock)
    # a well-behaved executor that always "produces a patch" so we can loop
    class NoopExecutor:
        def run_fix_in_sandbox(self, **kwargs):
            return FixResult(patch="", evidence="ok")

    poller = AutomationPoller(_config(max_rounds_per_pr=3), store, executor=NoopExecutor())
    outcomes = []
    for i in range(4):
        # same head/review across rounds so attempt increments on one row
        outcomes.append(
            poller.ingest(_event(event_id=f"cr-{i}", state="CHANGES_REQUESTED")).outcome
        )
    # design §8.1: fix on rounds 1..N-1, escalate ON round N (=3), then terminal
    assert outcomes == ["fixed", "fixed", "escalated", "terminal"]
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    assert store.get_state(key) == State.ESCALATED


# ──────────────────────── allowlist / config ────────────────────────────


def test_untracked_repo_is_ignored():
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)
    action = poller.ingest(_event(event_id="x", repo="evil/repo"))
    assert action.outcome == "ignored_untracked"
    assert store.snapshot() == []


def test_untracked_pr_is_ignored_when_pr_allowlist_set():
    clock = FakeClock()
    store = StateStore(clock=clock)
    cfg = _config(tracked_prs={"hallovorld/renquant-orchestrator": (1, 2, 3)})
    poller = AutomationPoller(cfg, store)
    action = poller.ingest(_event(event_id="x", pr_number=99))
    assert action.outcome == "ignored_untracked"


def test_config_from_dict_roundtrip():
    cfg = PollerConfig.from_dict(
        {
            "tracked_repos": ["a/b"],
            "tracked_prs": {"a/b": [1, 2]},
            "lease_ttl_seconds": 42,
            "max_rounds_per_pr": 5,
            "dry_run": True,
            "owner": "poller-x",
        }
    )
    assert cfg.is_tracked("a/b", 1) is True
    assert cfg.is_tracked("a/b", 9) is False
    assert cfg.is_tracked("c/d", 1) is False
    assert cfg.dry_run is True
    assert cfg.max_rounds_per_pr == 5


# ─────────────────── merge-risk classification (§2.1) ───────────────────


def test_classify_merge_risk_flags_production_and_policy_paths():
    pr = {
        "labels": [{"name": "agent:claude"}],
        "files": [
            {"path": "data/prices.parquet"},
            {"path": ".github/CODEOWNERS"},
            {"path": "src/renquant_orchestrator/agent_workflows.py"},
        ],
    }
    reasons = classify_merge_risk(pr)
    assert is_high_risk(pr) is True
    joined = " ".join(reasons)
    assert "production path" in joined
    assert "policy/guardrail" in joined


def test_classify_merge_risk_ordinary_pr_is_empty():
    pr = {
        "labels": [{"name": "agent:claude"}],
        "files": [{"path": "doc/progress/2026-07-01-x.md"}, {"path": "src/x/util.py"}],
    }
    assert classify_merge_risk(pr) == []
    assert is_high_risk(pr) is False


def test_classify_merge_risk_flags_generated_and_stop_labels():
    pr = {
        "labels": [{"name": "agent:auto-generated"}, {"name": "agent:manual-hold"}],
        "files": [{"path": "src/x/util.py"}],
    }
    reasons = classify_merge_risk(pr)
    assert any("auto-generated" in r for r in reasons)
    assert any("agent:manual-hold" in r for r in reasons)


# ───────────────────────── crash-recovery ───────────────────────────────


def test_crash_recovery_reconciles_expired_lease():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.FIXING)
    store.acquire(key, "dead-worker", ttl=100.0)

    # worker crashes; lease not released; time passes beyond TTL
    clock.advance(101.0)
    reclaimed = store.reconcile_expired_leases()

    assert key in reclaimed
    row = store.get_row(key)
    assert row["lease_owner"] is None  # reclaimable
    # a fresh worker can now acquire and continue
    assert store.acquire(key, "recoverer", ttl=100.0).acquired is True


def test_crash_recovery_does_not_touch_live_lease():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.FIXING)
    store.acquire(key, "alive", ttl=100.0)
    clock.advance(10.0)  # still within TTL
    assert store.reconcile_expired_leases() == []
    assert store.holds_lease(key, "alive") is True


def test_crash_recovery_ground_truth_drops_gone_pr():
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.FIXING)
    store.acquire(key, "dead", ttl=100.0)
    clock.advance(101.0)

    # ground truth: PR is gone → do not re-run, drop it
    reclaimed = store.reconcile_expired_leases(ground_truth=lambda k: False)
    assert reclaimed == []
    assert store.get_state(key) == State.DROPPED


# ───────────── point 1: cross-key PR lease race (two connections) ────────


def test_cross_key_same_pr_two_connections_only_one_acquires(tmp_path):
    """Review point 1: two workers on DIFFERENT ``(head_sha, review_id)`` rows
    of the SAME ``(repo, pr)`` must NOT both acquire. A barrier releases both
    into ``acquire`` simultaneously; because the PR-busy check + row acquisition
    run in ONE ``BEGIN IMMEDIATE`` transaction, exactly one wins and the other
    coalesces (this fails on the pre-fix separate-transaction code)."""
    import threading

    db = str(tmp_path / "race.db")
    store_a = StateStore(db)
    store_b = StateStore(db)
    key_a = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    key_b = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-2")  # same PR
    store_a.ensure_row(key_a, State.AWAIT_REVIEW)
    store_b.ensure_row(key_b, State.AWAIT_REVIEW)

    results: dict = {}
    errors: list = []
    barrier = threading.Barrier(2)

    def worker(store, key, name):
        try:
            barrier.wait()  # release both threads into acquire together
            results[name] = store.acquire(key, name, ttl=100.0)
        except Exception as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=(store_a, key_a, "wa"))
    t2 = threading.Thread(target=worker, args=(store_b, key_b, "wb"))
    t1.start(); t2.start()
    t1.join(); t2.join()
    store_a.close(); store_b.close()

    assert errors == []
    acquired = [r for r in results.values() if r.acquired]
    coalesced = [r for r in results.values() if not r.acquired]
    assert len(acquired) == 1        # exactly one holds the PR-level lease
    assert len(coalesced) == 1       # the other coalesced — no concurrent run
    assert "coalesced" in coalesced[0].reason


# ────────────── point 2: transition fenced by the lease ──────────────────


def test_transition_rejected_when_lease_expired_before_commit():
    """Review point 2: a poller whose lease has expired cannot transition — the
    state UPDATE requires ``lease_expiry > now`` atomically."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.AWAIT_REVIEW)
    acq = store.acquire(key, "w1", ttl=100.0)
    clock.advance(101.0)  # lease expired, not yet reclaimed
    with pytest.raises(IllegalTransition):
        store.transition(key, State.FIXING, actor=Actor.POLLER, owner="w1", fence=acq.fence)


def test_transition_fenced_reclaimed_lease_cannot_commit():
    """Review point 2: after a reclaim + re-acquire (even by the SAME ``owner``
    id), the OLD holder's stale fence is refused; only the current lease
    generation can commit. This is the fencing token that plain owner+expiry
    cannot provide when the reclaimer reuses the owner id."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.AWAIT_REVIEW)
    acq1 = store.acquire(key, "poller-1", ttl=100.0)
    clock.advance(101.0)  # lease expires
    assert store.reconcile_expired_leases() == [key]
    acq2 = store.acquire(key, "poller-1", ttl=100.0)  # same owner id reclaims
    assert acq2.fence != acq1.fence
    # the OLD in-flight worker (holding the stale fence) must never commit
    with pytest.raises(IllegalTransition):
        store.transition(
            key, State.FIXING, actor=Actor.POLLER, owner="poller-1", fence=acq1.fence
        )
    # the current generation transitions fine
    assert store.transition(
        key, State.FIXING, actor=Actor.POLLER, owner="poller-1", fence=acq2.fence
    ) == State.FIXING


# ─────────── point 3: crash-injection idempotency at each boundary ────────


class _CrashInjected(RuntimeError):
    """Simulated process crash at a specific boundary."""


def _crash_once(store, method_name):
    """Make ``store.<method_name>`` raise :class:`_CrashInjected` on its next
    call, then self-heal so the redelivery uses the real method."""
    original = getattr(store, method_name)

    def wrapper(*args, **kwargs):
        setattr(store, method_name, original)  # heal for redelivery
        raise _CrashInjected(method_name)

    setattr(store, method_name, wrapper)


class _CrashOnceExecutor:
    """Delegates to ``inner`` but raises :class:`_CrashInjected` on its FIRST
    call — a crash AFTER the FIXING hop committed, BEFORE the terminal result —
    then heals so the redelivery's resume path runs the real executor."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def run_fix_in_sandbox(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise _CrashInjected("executor")
        return self.inner.run_fix_in_sandbox(**kwargs)


_KEY = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")


@pytest.mark.parametrize("boundary", ["supersede_stale", "ensure_row", "acquire"])
def test_crash_injection_before_drive_is_redrivable(boundary):
    """Review point 3: a crash AFTER CLAIM but before the fix is driven (at the
    supersede / ensure-row / lease-acquire boundaries) leaves the event
    RE-DRIVABLE — never a permanent 'duplicate' that silently drops the work."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)
    evt = _event(event_id="cr-crash", state="CHANGES_REQUESTED")

    _crash_once(store, boundary)
    with pytest.raises(_CrashInjected):
        poller.ingest(evt)

    # claimed but NOT applied → still re-drivable, not a silent duplicate
    assert store.event_seen("cr-crash") is True
    assert store.event_applied("cr-crash") is False

    # redelivery re-drives the work to completion (stub → ESCALATED)
    action = poller.ingest(evt)
    assert action.outcome != "duplicate"
    assert store.get_state(_KEY) == State.ESCALATED
    assert store.event_applied("cr-crash") is True
    # exactly one round was ever recorded — idempotent, no double work
    assert store.get_row(_KEY)["attempt"] == 1


def test_crash_after_state_transition_resumes_without_double_round():
    """Review point 3: a crash AFTER the FIXING transition committed (round
    counter already bumped) resumes from FIXING on redelivery WITHOUT a second
    begin_fix_round — the counter is never inflated and no illegal FIXING ->
    FIXING is attempted."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    executor = _CrashOnceExecutor(StubSandboxExecutor())
    poller = AutomationPoller(_config(), store, executor=executor)
    evt = _event(event_id="cr-mid", state="CHANGES_REQUESTED")

    with pytest.raises(_CrashInjected):
        poller.ingest(evt)
    # the FIXING hop committed (round bumped) but the event is NOT applied
    assert store.get_state(_KEY) == State.FIXING
    assert store.get_row(_KEY)["attempt"] == 1
    assert store.event_applied("cr-mid") is False

    action = poller.ingest(evt)  # resume from FIXING → stub → ESCALATE
    assert action.outcome == "escalated"
    assert store.get_state(_KEY) == State.ESCALATED
    assert store.get_row(_KEY)["attempt"] == 1  # NOT bumped a second time
    assert store.event_applied("cr-mid") is True


def test_crash_after_executor_result_before_apply_resumes():
    """Review point 3: a crash AFTER the executor produced a result but BEFORE
    the terminal transition+apply committed re-drives cleanly on redelivery
    (fold means the row never moved, so no duplicate side effect)."""
    clock = FakeClock()
    store = StateStore(clock=clock)

    class NoopExecutor:
        def run_fix_in_sandbox(self, **kwargs):
            return FixResult(patch="", evidence="ok")

    poller = AutomationPoller(_config(), store, executor=NoopExecutor())
    evt = _event(event_id="cr-post", state="CHANGES_REQUESTED")

    _crash_once(store, "transition_and_apply")
    with pytest.raises(_CrashInjected):
        poller.ingest(evt)
    # executor ran, but the fold did NOT commit → row still FIXING, un-applied
    assert store.get_state(_KEY) == State.FIXING
    assert store.event_applied("cr-post") is False
    assert store.get_row(_KEY)["attempt"] == 1

    action = poller.ingest(evt)  # resume → executor → fold commits
    assert action.outcome == "fixed"
    assert store.get_state(_KEY) == State.AWAIT_REVIEW
    assert store.event_applied("cr-post") is True
    assert store.get_row(_KEY)["attempt"] == 1  # still exactly one round


def test_crash_before_applied_marker_on_roundcap_is_redrivable():
    """Review point 3: a crash BEFORE the applied marker on the round-cap
    ESCALATED path (whose transition is not folded) re-drives into the terminal
    short-circuit on redelivery — idempotent, counter unchanged, then applied."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(max_rounds_per_pr=1), store)
    evt = _event(event_id="cr-cap", state="CHANGES_REQUESTED")

    _crash_once(store, "mark_event_applied")
    with pytest.raises(_CrashInjected):
        poller.ingest(evt)
    # begin_fix_round transitioned to ESCALATED (cap=1) but the marker crashed
    assert store.get_state(_KEY) == State.ESCALATED
    assert store.get_row(_KEY)["attempt"] == 1
    assert store.event_applied("cr-cap") is False

    action = poller.ingest(evt)  # terminal short-circuit → apply
    assert action.outcome == "terminal"
    assert store.event_applied("cr-cap") is True
    assert store.get_row(_KEY)["attempt"] == 1


def test_poller_refuses_event_claimed_by_another_owner():
    """Review point 3 (concurrency): a live processing claim held by a DIFFERENT
    owner refuses this poller (in_progress) — two owners never both enter the
    drive for one event id, so the state mutation is at-most-once."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    evt = _event(event_id="held", state="CHANGES_REQUESTED")
    # another poller process claimed it and is mid-flight (lease live, un-applied)
    assert store.claim_event(evt, owner="other-poller", ttl=100.0).proceed is True

    poller = AutomationPoller(_config(owner="poller-1"), store)
    action = poller.ingest(evt)
    assert action.outcome == "in_progress"
    # this poller drove NOTHING
    assert store.get_state(_KEY) is None
    assert store.event_applied("held") is False


def test_two_concurrent_deliveries_drive_exactly_once(tmp_path):
    """Review point 3: two poller processes (DISTINCT owners) racing the SAME
    event id — exactly one drives it to a terminal outcome; the other is refused
    (in_progress) or sees a true duplicate. The work item is driven ONCE."""
    import threading

    db = str(tmp_path / "concurrent.db")
    store_a = StateStore(db)
    store_b = StateStore(db)
    poller_a = AutomationPoller(_config(owner="poller-A"), store_a)
    poller_b = AutomationPoller(_config(owner="poller-B"), store_b)
    evt = _event(event_id="race", state="CHANGES_REQUESTED")

    results: dict = {}
    errors: list = []
    barrier = threading.Barrier(2)

    def worker(poller, name):
        try:
            barrier.wait()
            results[name] = poller.ingest(evt)
        except Exception as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=(poller_a, "a"))
    t2 = threading.Thread(target=worker, args=(poller_b, "b"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert errors == []
    outcomes = [r.outcome for r in results.values()]
    # exactly one delivery drove the fix to a terminal escalation
    assert outcomes.count("escalated") == 1
    other = [o for o in outcomes if o != "escalated"][0]
    assert other in ("in_progress", "duplicate")
    # the work item was driven exactly once (one round, no double side effect)
    assert store_a.get_row(_KEY)["attempt"] == 1
    store_a.close()
    store_b.close()


def test_crash_after_apply_is_a_true_duplicate():
    """The positive control: once an event is APPLIED, redelivery is a genuine
    duplicate (idempotency window closes only after the mutation commits)."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)
    evt = _event(event_id="cr-applied", state="CHANGES_REQUESTED")
    first = poller.ingest(evt)
    assert first.outcome == "escalated"
    assert store.event_applied("cr-applied") is True
    assert poller.ingest(evt).outcome == "duplicate"


# ────── PR #214 review: coalesced work must never be lost or wedged ───────
#
# The exact-once path (claim → drive → fold applied-marker with the
# transition) closed the crash window for a SINGLE event's own transition.
# But a PR-level lease coalesce (AcquireResult.acquired is False because
# ANOTHER row for the same PR holds a live lease) is a DIFFERENT event whose
# intended transition never ran at all. Marking that event "applied" anyway
# would silently and permanently drop its work — the bug these tests guard.


def test_coalesced_event_not_applied_and_redelivery_completes_it():
    """(1) Two concurrent events on the SAME PR where the SECOND coalesces
    behind the first: the second must NOT be marked applied merely because it
    lost the PR-lease race, and once the blocker is done, redelivering it must
    actually execute its intended fix round — never a silent no-op."""
    clock = FakeClock()
    store = StateStore(clock=clock)

    evt_a = _event(event_id="evt-a", head_sha="sha-a", review_id="rev-a",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b", head_sha="sha-a", review_id="rev-b",
                    state="CHANGES_REQUESTED")
    key_b = evt_b.row_key

    class ConcurrentThenStubExecutor:
        """A holds the PR-level lease while running; from INSIDE that run, B
        (a different review of the SAME PR/head) is ingested — it must
        coalesce, not run concurrently. Behaves like the plain stub
        otherwise (including on B's own later, separate invocation)."""

        def __init__(self):
            self.calls = 0
            self.captured_b_action = None
            self.poller = None  # AutomationPoller, wired after construction

        def run_fix_in_sandbox(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                self.captured_b_action = self.poller.ingest(evt_b)
            raise NotImplementedError("stub")

    executor = ConcurrentThenStubExecutor()
    poller = AutomationPoller(_config(), store, executor=executor)
    executor.poller = poller

    action_a = poller.ingest(evt_a)
    assert action_a.outcome == "escalated"  # A's own round: stub → escalate

    # B coalesced while A's lease was live — NOT applied (the bug).
    b_first = executor.captured_b_action
    assert b_first.outcome == "coalesced"
    assert store.event_applied("evt-b") is False
    assert store.event_seen("evt-b") is True
    assert store.get_row(key_b)["pending_rerun"] == 1

    # Redeliver B now that A is terminal and its lease is released: the
    # intended fix round must actually execute this time.
    b_retry = poller.ingest(evt_b)
    assert b_retry.outcome == "escalated"
    assert store.event_applied("evt-b") is True
    assert store.get_state(key_b) == State.ESCALATED
    assert store.get_row(key_b)["attempt"] == 1       # the round DID run
    assert store.get_row(key_b)["pending_rerun"] == 0  # cleared on acquire


def test_startup_recover_autonomously_completes_coalesced_event_after_holder_crash():
    """(2) The CURRENT lease holder (A) crashes WHILE a coalesced event (B) is
    pending. B is NEVER externally redelivered — no external source, no
    webhook retry, ever redelivers evt-b2 again. `startup_recover`'s
    durable-inbox recovery pass must reclaim + AUTONOMOUSLY drive B itself the
    instant A's dangling lease is reconciled; relying on 'a later redelivery'
    is exactly the gap this closes."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)

    evt_a = _event(event_id="evt-a2", head_sha="sha-a", review_id="rev-a2",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b2", head_sha="sha-a", review_id="rev-b2",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    key_b = evt_b.row_key

    # A acquires the PR-level lease and "crashes": it never transitions out of
    # FIXING or releases.
    store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = store.acquire(key_a, poller.config.owner, poller.config.lease_ttl_seconds)
    assert acq_a.acquired is True
    store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)

    # B arrives while A's lease is still live → coalesces, must NOT be applied.
    b_first = poller.ingest(evt_b)
    assert b_first.outcome == "coalesced"
    assert store.event_applied("evt-b2") is False
    assert store.get_row(key_b)["pending_rerun"] == 1
    # the durable inbox carries B's FULL payload — a recovery pass needs no
    # external redelivery to reconstruct and drive it.
    inbox = {r["event_id"]: r for r in store.list_processing_events()}
    assert inbox["evt-b2"]["state"] == "CHANGES_REQUESTED"
    assert inbox["evt-b2"]["review_id"] == "rev-b2"

    # A's lease TTL elapses without ever releasing (the crash).
    clock.advance(poller.config.lease_ttl_seconds + 1)

    # Crash-recovery sweep on poller start — NO external redelivery of B is
    # ever involved. startup_recover alone must autonomously complete it.
    summary = poller.startup_recover()
    assert isinstance(summary, RecoverySummary)
    assert store.get_row(key_a)["lease_owner"] is None
    assert key_a in summary.reclaimed_leases

    recovered_b = [a for a in summary.recovered_actions if a.event_id == "evt-b2"]
    assert len(recovered_b) == 1
    assert recovered_b[0].outcome == "escalated"
    assert store.event_applied("evt-b2") is True
    assert store.get_state(key_b) == State.ESCALATED
    assert store.get_row(key_b)["attempt"] == 1       # the round DID run

    # If a delivery ever DID arrive after the fact, it must see a true
    # duplicate — never a second execution.
    b_late = poller.ingest(evt_b)
    assert b_late.outcome == "duplicate"
    assert store.get_row(key_b)["attempt"] == 1


def test_poll_tick_autonomously_completes_coalesced_event_after_holder_releases():
    """The blocking holder (A) COMPLETES NORMALLY — releases its lease, no
    crash, no expiry — so there is nothing for a crash-only sweep to find. B
    is, again, NEVER externally redelivered. A plain periodic poll tick
    (`recover_pending`, not `startup_recover`) must alone autonomously
    complete it the moment A's lease clears."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)

    evt_a = _event(event_id="evt-a7", head_sha="sha-a", review_id="rev-a7",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b7", head_sha="sha-a", review_id="rev-b7",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    key_b = evt_b.row_key

    store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = store.acquire(key_a, poller.config.owner, poller.config.lease_ttl_seconds)
    assert acq_a.acquired is True
    store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)

    b_first = poller.ingest(evt_b)
    assert b_first.outcome == "coalesced"
    assert store.event_applied("evt-b7") is False

    # A completes normally: transitions out of FIXING and releases its
    # PR-level lease. No time passes, nothing ever expires.
    store.transition(key_a, State.AWAIT_REVIEW, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)
    assert store.release(key_a, poller.config.owner, fence=acq_a.fence) is True
    assert store.reconcile_expired_leases() == []  # nothing was expired

    # A plain poll tick — NOT startup, NO external redelivery of B — must
    # alone finish the job.
    actions = poller.recover_pending()
    recovered_b = [a for a in actions if a.event_id == "evt-b7"]
    assert len(recovered_b) == 1
    assert recovered_b[0].outcome == "escalated"
    assert store.event_applied("evt-b7") is True
    assert store.get_state(key_b) == State.ESCALATED
    assert store.get_row(key_b)["attempt"] == 1


def test_recovery_and_external_redelivery_race_is_exactly_once(tmp_path):
    """Exactly-once under the NEW recovery path: once A's blocking lease
    clears, race a GENUINE external redelivery of B (`ingest`) against this
    poller's OWN autonomous recovery poll tick (`recover_pending`) —
    two distinct connections/threads released together by a barrier so they
    contend for the SAME event id at the SAME instant. Exactly one of them
    must drive B's fix round to completion; the other must be refused
    (`in_progress`/`duplicate`), never a double execution."""
    import threading

    db = str(tmp_path / "race-recovery.db")
    cfg = _config(owner="poller-1")

    setup_store = StateStore(db)
    evt_a = _event(event_id="evt-a8", head_sha="sha-a", review_id="rev-a8",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b8", head_sha="sha-a", review_id="rev-b8",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    key_b = evt_b.row_key

    # A holds the PR-level lease (simulating in-flight work).
    setup_store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = setup_store.acquire(key_a, cfg.owner, cfg.lease_ttl_seconds)
    assert acq_a.acquired is True
    setup_store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                            owner=cfg.owner, fence=acq_a.fence)

    poller_setup = AutomationPoller(cfg, setup_store)
    b_first = poller_setup.ingest(evt_b)
    assert b_first.outcome == "coalesced"
    assert setup_store.event_applied("evt-b8") is False

    # A "completes" — releases its lease — WITHOUT B ever being redelivered
    # through any normal channel up to this point.
    assert setup_store.release(key_a, cfg.owner, fence=acq_a.fence) is True
    setup_store.close()

    # Race a genuine external redelivery of B against this poller's own
    # recovery pass.
    store_ext = StateStore(db)
    store_rec = StateStore(db)
    poller_ext = AutomationPoller(cfg, store_ext)  # simulates external redelivery -> ingest()
    poller_rec = AutomationPoller(cfg, store_rec)  # simulates a poll tick -> recover_pending()

    results: dict = {}
    errors: list = []
    barrier = threading.Barrier(2)

    def redeliver():
        try:
            barrier.wait()
            results["external"] = poller_ext.ingest(evt_b)
        except Exception as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    def recover():
        try:
            barrier.wait()
            actions = poller_rec.recover_pending()
            results["recovery"] = next(
                (a for a in actions if a.event_id == "evt-b8"), None
            )
        except Exception as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    t1 = threading.Thread(target=redeliver)
    t2 = threading.Thread(target=recover)
    t1.start(); t2.start()
    t1.join(); t2.join()
    store_ext.close(); store_rec.close()

    assert errors == []
    outcomes = [r.outcome for r in results.values() if r is not None]
    # exactly one of {external redelivery, recovery poll} drove B's fix round
    # to a terminal escalation
    assert outcomes.count("escalated") == 1
    others = [o for o in outcomes if o != "escalated"]
    assert all(o in ("in_progress", "duplicate") for o in others)

    final = StateStore(db)
    assert final.get_state(key_b) == State.ESCALATED
    assert final.get_row(key_b)["attempt"] == 1   # exactly one fix round, never double
    final.close()


def test_coalesced_event_superseded_by_newer_head_ends_applied():
    """(3) A coalesced event that IS genuinely superseded by an equivalent
    later transition (a newer head's own event) must correctly end up
    applied — the fix must not over-correct into 'never mark applied'."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)

    key_a = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-a4")
    evt_b = _event(event_id="evt-b4", head_sha="sha-a", review_id="rev-b4",
                    state="CHANGES_REQUESTED")
    evt_c = _event(event_id="evt-c4", head_sha="sha-new", review_id="rev-c4",
                    state="CHANGES_REQUESTED")
    key_b = evt_b.row_key

    # A holds the PR-level lease on the OLD head (simulating an in-flight run).
    store.ensure_row(key_a, State.AWAIT_REVIEW)
    assert store.acquire(
        key_a, poller.config.owner, poller.config.lease_ttl_seconds
    ).acquired is True

    # B coalesces behind A — not applied, pending work recorded.
    b_first = poller.ingest(evt_b)
    assert b_first.outcome == "coalesced"
    assert store.event_applied("evt-b4") is False

    # A NEWER head lands: its event supersedes every non-terminal row on the
    # old head (A and B alike) and drives the equivalent work itself.
    c_action = poller.ingest(evt_c)
    assert c_action.outcome == "escalated"
    assert store.is_superseded(key_a) is True
    assert store.is_superseded(key_b) is True

    # B, redelivered, discovers it is genuinely superseded — correctly ends up
    # applied (never re-attempted; C already did the equivalent work). Not
    # permanently stuck un-applied, and not re-processed forever either.
    b_retry = poller.ingest(evt_b)
    assert b_retry.outcome == "superseded"
    assert store.event_applied("evt-b4") is True
    assert store.get_state(key_b) == State.AWAIT_REVIEW  # never actually driven


# ──────────── point 4: supersede cancels the in-flight executor ───────────


def test_poller_executor_receives_cancel_token_and_acknowledges():
    """Review point 4: the executor is handed a cancellation token; a
    cooperative executor cancelled mid-run acknowledges, and the poller reports
    'cancelled' and drops the PR-level lease (no patch applied)."""
    clock = FakeClock()
    store = StateStore(clock=clock)

    class CooperativeExecutor:
        def __init__(self):
            self.token = None

        def run_fix_in_sandbox(self, *, cancel_token=None, **kwargs):
            self.token = cancel_token
            # a newer head superseded us while we were computing:
            cancel_token.cancel()
            cancel_token.raise_if_cancelled()  # cooperative checkpoint → ack + abort
            return FixResult(patch="p", evidence="e")  # unreachable

    ex = CooperativeExecutor()
    poller = AutomationPoller(_config(), store, executor=ex)
    action = poller.ingest(_event(event_id="cr-cancel", state="CHANGES_REQUESTED"))

    assert action.outcome == "cancelled"
    assert isinstance(ex.token, CancellationToken)  # plumbing: token handed in
    assert ex.token.acknowledged is True            # executor acknowledged
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    # cancelled run winds down: retained lease dropped, patch never applied
    assert store.get_row(key)["lease_owner"] is None


def test_poller_fences_stale_patch_when_head_advances_mid_run():
    """Review point 4: an executor output computed against a head that advanced
    (superseded) mid-run is FENCED OUT — never applied/pushed. The row does not
    progress to AWAIT_REVIEW."""
    clock = FakeClock()
    store = StateStore(clock=clock)

    class SupersedingExecutor:
        def __init__(self, store):
            self.store = store

        def run_fix_in_sandbox(self, *, repo, pr_number, head_sha, review_comments,
                               cancel_token=None):
            # a newer head lands while we compute → our row is superseded
            self.store.supersede_stale(repo, pr_number, "sha-new")
            return FixResult(patch="p", evidence="e")

    poller = AutomationPoller(_config(), store, executor=SupersedingExecutor(store))
    action = poller.ingest(_event(event_id="cr-fence", state="CHANGES_REQUESTED"))

    assert action.outcome == "fenced_stale"
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    assert store.get_state(key) == State.FIXING     # patch discarded, not applied
    assert store.is_superseded(key) is True


def test_reconcile_clears_dangling_superseded_lease():
    """A superseded old run that crashed WITHOUT acknowledging has its retained
    cancellation lease swept once it expires — no permanent PR occupation."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    store.ensure_row(key, State.FIXING)
    store.acquire(key, "w1", ttl=100.0)
    store.supersede_stale("hallovorld/renquant-orchestrator", 42, "sha-new")
    assert store.get_row(key)["lease_owner"] == "w1"  # retained (cancel pending)
    clock.advance(101.0)  # old executor never acked; its lease expired
    store.reconcile_expired_leases()
    assert store.get_row(key)["lease_owner"] is None  # dangling lease swept


# ─────── point 4: durable cancellation ownership / heartbeat / kill ───────


def test_heartbeat_renews_only_for_the_live_holder():
    """Review point 4: a durable liveness heartbeat keeps the lease alive for
    the CURRENT holder only; a wrong owner or a stale fence cannot renew, so a
    crashed/hung executor stops heart-beating and its lease expires."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.FIXING)
    acq = store.acquire(key, "w1", ttl=100.0)

    clock.advance(50.0)
    assert store.heartbeat(key, "w1", acq.fence, ttl=100.0) is True
    clock.advance(80.0)  # would have expired at t+100 without the renew
    assert store.holds_lease(key, "w1") is True  # renewed to t+130

    assert store.heartbeat(key, "w1", acq.fence + 1, ttl=100.0) is False   # stale fence
    assert store.heartbeat(key, "intruder", acq.fence, ttl=100.0) is False  # wrong owner


def test_request_cancellation_is_durable_and_retains_lease():
    """Review point 4: cancellation is a PERSISTED flag (the cross-restart
    source of truth an executor polls), not an in-memory token; the lease is
    RETAINED until the executor acknowledges, and terminal rows cannot be
    flagged."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-1")
    store.ensure_row(key, State.FIXING)
    store.acquire(key, "w1", ttl=100.0)

    assert store.is_cancellation_requested(key) is False
    assert store.request_cancellation(key) is True
    assert store.is_cancellation_requested(key) is True     # durable flag
    assert store.get_row(key)["lease_owner"] == "w1"        # lease retained

    term = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-a", "rev-term")
    store.ensure_row(term, State.ESCALATED)
    assert store.request_cancellation(term) is False        # terminal → no-op


def test_list_uncooperative_cancellations_flags_expired_unacked_only():
    """Review point 4: only a run whose cancellation was durably requested AND
    whose retained lease expired WITHOUT acknowledgement is 'uncooperative' —
    the set a hard termination mechanism must forcibly tear down."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    store.ensure_row(key, State.FIXING)
    store.acquire(key, "w1", ttl=100.0)
    store.supersede_stale("hallovorld/renquant-orchestrator", 42, "sha-new")

    assert store.list_uncooperative_cancellations() == []   # lease still live
    clock.advance(101.0)
    assert key in store.list_uncooperative_cancellations()  # expired w/o ack
    store.acknowledge_cancellation(key)
    assert store.list_uncooperative_cancellations() == []   # acked → cleared


def test_startup_recover_hard_terminates_uncooperative_runs():
    """Review point 4: at startup, an uncooperative run is handed to the hard
    TerminationHook BEFORE its dangling lease is reconciled — a retained SQLite
    flag by itself does not stop untrusted work, so the kill is an explicit,
    observable mechanism (here: recorded)."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    hook = NoopTerminationHook()
    poller = AutomationPoller(_config(), store, termination_hook=hook)
    key = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    store.ensure_row(key, State.FIXING)
    store.acquire(key, "dead", ttl=100.0)
    store.supersede_stale("hallovorld/renquant-orchestrator", 42, "sha-new")
    clock.advance(101.0)  # dead executor never acked; its lease expired

    poller.startup_recover()
    assert key in hook.terminated                       # hard-kill obligation surfaced
    assert store.get_row(key)["lease_owner"] is None    # dangling lease then swept


# ─────────── upgrade-safe schema migration (PR #214 review) ─────────────
#
# CREATE TABLE IF NOT EXISTS (in _SCHEMA) does nothing to a table an EARLIER
# revision of this module already created with fewer columns. These tests
# open a db file built with the PRE-"durable inbox" processed_events shape
# (git rev b6b7c03f / 2074eccd: has status/owner/lease_expiry/result_json/
# applied_at, but NOT review_id/kind/state/body — those four were added
# together by the "durable inbox" round, git rev 945ce844) — exactly the
# "database created with the PREVIOUS schema" scenario the review asks to be
# tested, and verify claim_event's INSERT (which names all current columns)
# does not hard-fail with "no column named review_id" on it.


def _write_pre_durable_inbox_db(path: str) -> None:
    """Build a db file with the processed_events shape from BEFORE the
    "durable inbox" round (git rev b6b7c03f / 2074eccd) — the exact prior
    schema PR #214's review flagged as unreadable by the current claim_event
    INSERT."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE work_items (
            repo         TEXT    NOT NULL,
            pr_number    INTEGER NOT NULL,
            head_sha     TEXT    NOT NULL,
            review_id    TEXT    NOT NULL,
            state        TEXT    NOT NULL,
            lease_owner  TEXT,
            lease_expiry REAL,
            fence        INTEGER NOT NULL DEFAULT 0,
            attempt      INTEGER NOT NULL DEFAULT 0,
            last_event_id TEXT,
            superseded   INTEGER NOT NULL DEFAULT 0,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            pending_rerun INTEGER NOT NULL DEFAULT 0,
            created_at   REAL    NOT NULL,
            updated_at   REAL    NOT NULL,
            PRIMARY KEY (repo, pr_number, head_sha, review_id)
        );
        CREATE TABLE processed_events (
            event_id     TEXT PRIMARY KEY,
            repo         TEXT NOT NULL,
            pr_number    INTEGER NOT NULL,
            head_sha     TEXT,
            status       TEXT NOT NULL DEFAULT 'processing',
            owner        TEXT,
            lease_expiry REAL,
            result_json  TEXT,
            processed_at REAL NOT NULL,
            applied_at   REAL
        );
        """
    )
    conn.commit()
    conn.close()


def _write_oldest_v1_db(path: str) -> None:
    """Build a db file with the ORIGINAL processed_events shape (git rev
    059c5652, before ANY of status/owner/lease_expiry/result_json/
    applied_at/review_id/kind/state/body existed — a bare "seen" marker) and
    the original work_items shape (before fence/cancel_requested). Proves the
    migration is not special-cased to just the immediately-prior revision."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE work_items (
            repo         TEXT    NOT NULL,
            pr_number    INTEGER NOT NULL,
            head_sha     TEXT    NOT NULL,
            review_id    TEXT    NOT NULL,
            state        TEXT    NOT NULL,
            lease_owner  TEXT,
            lease_expiry REAL,
            attempt      INTEGER NOT NULL DEFAULT 0,
            last_event_id TEXT,
            superseded   INTEGER NOT NULL DEFAULT 0,
            pending_rerun INTEGER NOT NULL DEFAULT 0,
            created_at   REAL    NOT NULL,
            updated_at   REAL    NOT NULL,
            PRIMARY KEY (repo, pr_number, head_sha, review_id)
        );
        CREATE TABLE processed_events (
            event_id     TEXT PRIMARY KEY,
            repo         TEXT NOT NULL,
            pr_number    INTEGER NOT NULL,
            head_sha     TEXT,
            processed_at REAL NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def test_migration_adds_missing_columns_without_dropping_existing_rows(tmp_path):
    """Opening a db built with the pre-'durable inbox' schema must not raise,
    must add exactly the missing columns, and must not touch the row already
    there."""
    db = str(tmp_path / "legacy.db")
    _write_pre_durable_inbox_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO processed_events "
        "(event_id, repo, pr_number, head_sha, status, result_json, processed_at, applied_at) "
        "VALUES ('evt-legacy-1','hallovorld/renquant-orchestrator',42,'sha-a',"
        "'applied','{\"outcome\": \"escalated\"}', 1000.0, 1000.0)"
    )
    conn.commit()
    conn.close()

    store = StateStore(db)  # must NOT raise "no column named review_id"
    cols = store.table_columns("processed_events")
    assert {"review_id", "kind", "state", "body"} <= cols
    seen = store.event_row("evt-legacy-1")
    assert seen["status"] == "applied"                 # existing row untouched
    assert seen["result_json"] == '{"outcome": "escalated"}'
    assert seen["review_id"] is None                    # added, NULL (never guessed)
    assert seen["kind"] is None
    store.close()


def test_migration_handles_oldest_v1_schema_too(tmp_path):
    """The introspection-based migration is not special-cased to just the
    immediately-prior revision: it also opens the ORIGINAL (git rev
    059c5652) shape cleanly. Review r6 correction: a v1 "seen" row must NOT
    be guessed as already-applied — 059c5652's own ``record_event`` committed
    the delivery id BEFORE the real state transition ran, so presence alone
    never proved the work was done (that ordering bug is exactly what the
    FIRST #214 review flagged). It migrates to 'processing' instead, and
    a recovery pass flags it fail-closed (see
    ``test_legacy_v1_row_flagged_fail_closed_regardless_of_downstream_work_state``
    for both the "work actually happened" and "work never happened" cases)."""
    db = str(tmp_path / "v1-legacy.db")
    _write_oldest_v1_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO processed_events (event_id, repo, pr_number, head_sha, processed_at) "
        "VALUES ('evt-v1-1','hallovorld/renquant-orchestrator',42,'sha-a', 1000.0)"
    )
    conn.commit()
    conn.close()

    store = StateStore(db)  # must NOT raise on the even-older shape either
    cols = store.table_columns("processed_events")
    assert {"status", "owner", "lease_expiry", "result_json", "applied_at",
            "review_id", "kind", "state", "body"} <= cols
    wi_cols = store.table_columns("work_items")
    assert {"fence", "cancel_requested"} <= wi_cols

    assert store.event_seen("evt-v1-1") is True
    # NOT guessed as applied — the migration cannot tell whether v1's own
    # crash window means this row's real work ran or not.
    assert store.event_applied("evt-v1-1") is False
    row = store.event_row("evt-v1-1")
    assert row["status"] == "processing"

    poller = AutomationPoller(_config(), store)
    actions = poller.recover_pending()
    flagged = [a for a in actions if a.event_id == "evt-v1-1"]
    assert len(flagged) == 1
    assert flagged[0].outcome == "legacy_unrecoverable"
    assert store.event_legacy_unrecoverable("evt-v1-1") is True

    evt = _event(event_id="evt-v1-1")
    dup = store.claim_event(evt, owner="poller-1", ttl=100.0)
    assert dup.proceed is False and dup.disposition == "legacy_unrecoverable"
    store.close()


def test_legacy_v1_row_flagged_fail_closed_regardless_of_downstream_work_state(tmp_path):
    """Review r6 requirement: "Add fixtures for both an old row with and
    without corresponding durable work state and prove neither is guessed as
    applied." A v1 ``processed_events`` row predates ``review_id`` entirely,
    so a recovery pass structurally cannot even look up a matching
    ``work_items`` row to decide — it must flag EVERY v1 row
    'legacy_unrecoverable' uniformly, whether or not the associated work
    happened to actually complete."""
    for label, work_item_state in (
        ("work_completed", State.MERGE_ELIGIBLE.value),
        ("work_never_ran", None),
    ):
        db = str(tmp_path / f"v1-legacy-{label}.db")
        _write_oldest_v1_db(db)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO processed_events (event_id, repo, pr_number, head_sha, processed_at) "
            f"VALUES ('evt-v1-{label}','hallovorld/renquant-orchestrator',42,'sha-a', 1000.0)"
        )
        if work_item_state is not None:
            # Simulate "the work really did complete downstream" — a
            # terminal-ish work_items row exists for this repo/pr/head_sha
            # (under SOME review_id the legacy ledger row cannot name).
            conn.execute(
                "INSERT INTO work_items (repo, pr_number, head_sha, review_id, "
                "state, attempt, superseded, pending_rerun, created_at, updated_at) "
                "VALUES ('hallovorld/renquant-orchestrator',42,'sha-a','rev-unknown',"
                f"'{work_item_state}',1,0,0,900.0,950.0)"
            )
        conn.commit()
        conn.close()

        store = StateStore(db)
        poller = AutomationPoller(_config(), store)
        actions = poller.recover_pending()
        flagged = [a for a in actions if a.event_id == f"evt-v1-{label}"]
        assert len(flagged) == 1, label
        assert flagged[0].outcome == "legacy_unrecoverable", label
        # never guessed 'applied' in either scenario, regardless of whether
        # downstream work state looks complete.
        assert store.event_applied(f"evt-v1-{label}") is False, label
        assert store.event_legacy_unrecoverable(f"evt-v1-{label}") is True, label
        store.close()


def test_legacy_applied_row_remains_a_recognized_duplicate_after_migration(tmp_path):
    """Review requirement (a): an already-'applied' row from the PREVIOUS
    schema must remain correctly recognized as a duplicate/no-op — never
    re-driven, never crashing — after the migration runs."""
    db = str(tmp_path / "legacy-applied.db")
    _write_pre_durable_inbox_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO processed_events "
        "(event_id, repo, pr_number, head_sha, status, result_json, processed_at, applied_at) "
        "VALUES ('evt-applied-1','hallovorld/renquant-orchestrator',42,'sha-a',"
        "'applied','{\"outcome\": \"merge_eligible\", \"detail\": \"approved\"}', 1000.0, 1000.0)"
    )
    conn.commit()
    conn.close()

    store = StateStore(db)
    poller = AutomationPoller(_config(), store)
    # a genuine redelivery of the SAME event id — must be a true duplicate,
    # not an attempt to re-drive it (which would crash: this legacy row has
    # no review_id/kind/state/body to reconstruct anyway).
    redelivered = _event(event_id="evt-applied-1", head_sha="sha-a")
    action = poller.ingest(redelivered)
    assert action.outcome == "duplicate"
    assert "merge_eligible" in action.detail
    # no work item was created/mutated by the duplicate redelivery
    assert store.snapshot() == []
    store.close()


def test_legacy_processing_row_is_flagged_fail_closed_not_guessed_or_dropped(tmp_path):
    """Review requirement (b): a row still 'processing' under the PREVIOUS
    schema (a genuine crash mid-flight, before review_id/kind/state/body
    existed) cannot be autonomously reconstructed — it must get a
    WELL-DEFINED fail-closed disposition, never silently dropped (i.e. never
    just disappear) and never silently guessed at (i.e. never driven as if
    it were a real reconstructed Event)."""
    db = str(tmp_path / "legacy-processing.db")
    _write_pre_durable_inbox_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO processed_events "
        "(event_id, repo, pr_number, head_sha, status, owner, lease_expiry, processed_at) "
        "VALUES ('evt-stuck-1','hallovorld/renquant-orchestrator',42,'sha-a',"
        "'processing','dead-legacy-owner', 500.0, 400.0)"
    )
    conn.commit()
    conn.close()

    clock = FakeClock(start=2_000.0)  # well past the legacy lease_expiry=500.0
    store = StateStore(db, clock=clock)
    poller = AutomationPoller(_config(), store)

    # no work item exists for this legacy ledger row (review_id was never
    # persisted under the old schema, so it can't even be located) — the
    # recovery pass must not crash trying to touch one.
    actions = poller.recover_pending()
    flagged = [a for a in actions if a.event_id == "evt-stuck-1"]
    assert len(flagged) == 1
    assert flagged[0].outcome == "legacy_unrecoverable"
    assert "manual review" in flagged[0].detail

    # durably terminal: never re-appears in the durable inbox scan again...
    assert store.list_processing_events() == []
    # ...distinct from a true 'applied' duplicate (never conflated)...
    assert store.event_applied("evt-stuck-1") is False
    assert store.event_legacy_unrecoverable("evt-stuck-1") is True
    # ...and a SECOND recovery tick is a stable no-op, not a repeat flag/spam.
    assert poller.recover_pending() == []

    # if a genuine external redelivery ever did arrive for this id, it must
    # see the SAME fail-closed signal — never re-attempt with guessed data,
    # never a plain silent "duplicate" that hides it was never actually run.
    redelivered = _event(event_id="evt-stuck-1", head_sha="sha-a")
    late = poller.ingest(redelivered)
    assert late.outcome == "legacy_unrecoverable"
    store.close()


def test_new_events_after_migration_recover_autonomously_via_full_payload(tmp_path):
    """Review requirement (c): a database migrated up from the PREVIOUS
    schema must, for a NEW event ingested afterwards, still deliver the full
    durable-inbox autonomous-recovery behaviour (design §6.3) — no
    degradation from having been opened against a legacy file."""
    db = str(tmp_path / "legacy-then-new.db")
    _write_pre_durable_inbox_db(db)
    # an unrelated legacy applied row, just to prove migration + new activity
    # coexist in the same migrated file.
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO processed_events "
        "(event_id, repo, pr_number, head_sha, status, processed_at, applied_at) "
        "VALUES ('evt-old','hallovorld/renquant-orchestrator',1,'sha-x','applied', 1.0, 1.0)"
    )
    conn.commit()
    conn.close()

    clock = FakeClock()
    store = StateStore(db, clock=clock)
    poller = AutomationPoller(_config(), store)

    evt_a = _event(event_id="evt-new-a", head_sha="sha-a", review_id="rev-new-a",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-new-b", head_sha="sha-a", review_id="rev-new-b",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    key_b = evt_b.row_key

    store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = store.acquire(key_a, poller.config.owner, poller.config.lease_ttl_seconds)
    assert acq_a.acquired is True
    store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)

    # B coalesces behind A — claimed with its FULL payload under the NOW-
    # CURRENT schema (the migrated file has every column claim_event needs).
    b_first = poller.ingest(evt_b)
    assert b_first.outcome == "coalesced"
    inbox = {r["event_id"]: r for r in store.list_processing_events()}
    assert inbox["evt-new-b"]["kind"] == "review"
    assert inbox["evt-new-b"]["state"] == "CHANGES_REQUESTED"

    # A completes normally; NO external redelivery of B ever happens.
    store.transition(key_a, State.AWAIT_REVIEW, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)
    assert store.release(key_a, poller.config.owner, fence=acq_a.fence) is True

    recovered = poller.tick()
    recovered_b = [a for a in recovered if a.event_id == "evt-new-b"]
    assert len(recovered_b) == 1
    assert recovered_b[0].outcome == "escalated"
    assert store.event_applied("evt-new-b") is True
    assert store.get_state(key_b) == State.ESCALATED
    store.close()


# ───────────────────── periodic tick (PR #214 review) ────────────────────


def test_tick_autonomously_completes_coalesced_event_without_process_restart():
    """Review point 2: 'wire recover_pending into an actual periodic tick
    before claiming long-lived autonomous recovery; startup-only invocation
    is insufficient for coalescing that resolves while the process stays
    up.' A coalesced event whose blocker clears WHILE the process keeps
    running (no restart, so startup_recover never runs again) must still be
    picked up — via the repeatedly-callable AutomationPoller.tick(), not
    just recover_pending() called ad hoc by a test."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)

    evt_a = _event(event_id="evt-a9", head_sha="sha-a", review_id="rev-a9",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b9", head_sha="sha-a", review_id="rev-b9",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    key_b = evt_b.row_key

    store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = store.acquire(key_a, poller.config.owner, poller.config.lease_ttl_seconds)
    assert acq_a.acquired is True
    store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)

    b_first = poller.ingest(evt_b)
    assert b_first.outcome == "coalesced"

    # A plain tick BEFORE A's lease clears still finds A's lease live, so B
    # stays coalesced (not driven) — ticking is safe to call even when there
    # is genuinely nothing recoverable yet.
    still_blocked = poller.tick()
    assert [a.outcome for a in still_blocked] == ["coalesced"]
    assert store.event_applied("evt-b9") is False

    # A completes normally — no crash, no restart, the process just keeps
    # running (nothing calls startup_recover again).
    store.transition(key_a, State.AWAIT_REVIEW, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)
    assert store.release(key_a, poller.config.owner, fence=acq_a.fence) is True

    actions = poller.tick()
    recovered_b = [a for a in actions if a.event_id == "evt-b9"]
    assert len(recovered_b) == 1
    assert recovered_b[0].outcome == "escalated"
    assert store.event_applied("evt-b9") is True
    assert store.get_state(key_b) == State.ESCALATED

    # a subsequent tick is a stable no-op — never re-drives a finished event.
    assert poller.tick() == []


def test_tick_is_a_safe_noop_with_nothing_pending():
    """A live loop calls tick() every interval regardless of whether
    anything is actually pending; it must never raise and must be a true
    no-op (no phantom actions, no mutation) when the durable inbox is
    empty."""
    store = StateStore(clock=FakeClock())
    poller = AutomationPoller(_config(), store)
    assert poller.tick() == []
    assert store.snapshot() == []


# ────────────────────────── run_poll_loop wiring ─────────────────────────
#
# Review r6, finding 2: "tick() is a callable wrapper around recover_pending,
# but neither run_cli nor any service/loop invokes it repeatedly ... a
# long-lived process in this PR still has no periodic recovery behavior."
# run_poll_loop is the actual periodic-loop mechanism; these tests prove it
# calls tick() on a cadence, is bounded/interruptible, and genuinely
# recovers a coalesced event WHILE staying up (no restart, no test code
# calling tick() by hand between iterations).


def test_poll_loop_bounded_by_max_iterations_and_sleeps_between_ticks():
    store = StateStore(clock=FakeClock())
    poller = AutomationPoller(_config(), store)
    sleeps = []
    actions = run_poll_loop(
        poller, interval_seconds=5.0, max_iterations=3, sleep=sleeps.append
    )
    assert actions == []  # nothing pending on any of the 3 ticks
    # 3 ticks, only 2 sleeps — never sleeps after the LAST iteration.
    assert sleeps == [5.0, 5.0]


def test_poll_loop_rejects_non_positive_max_iterations():
    store = StateStore(clock=FakeClock())
    poller = AutomationPoller(_config(), store)
    with pytest.raises(ValueError):
        run_poll_loop(poller, interval_seconds=1.0, max_iterations=0)


def test_poll_loop_stop_predicate_halts_before_next_tick():
    """``stop`` is checked at the TOP of every iteration (before that
    iteration's tick), so a supervised process can request shutdown between
    ticks without killing one mid-flight."""
    store = StateStore(clock=FakeClock())
    poller = AutomationPoller(_config(), store)
    tick_calls = []
    poller.tick = lambda: (tick_calls.append(1) or [])

    stop_calls = []

    def stop():
        stop_calls.append(1)
        return len(stop_calls) > 2  # let 2 ticks run, then halt

    sleeps = []
    result = run_poll_loop(poller, interval_seconds=1.0, stop=stop, sleep=sleeps.append)
    assert result == []
    assert len(tick_calls) == 2
    assert len(stop_calls) == 3  # the 3rd check is the one that halts it
    assert sleeps == [1.0, 1.0]


def test_poll_loop_autonomously_recovers_coalesced_event_across_iterations():
    """The actual periodic-loop mechanism review r6 required: a coalesced
    event whose blocker clears WHILE run_poll_loop keeps ticking — no
    restart, no external redelivery, and no test code calling tick() or
    recover_pending() directly between iterations — is recovered on a LATER
    iteration of the SAME run_poll_loop call."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)

    evt_a = _event(event_id="evt-a-loop", head_sha="sha-a", review_id="rev-a-loop",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b-loop", head_sha="sha-a", review_id="rev-b-loop",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    key_b = evt_b.row_key

    store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = store.acquire(key_a, poller.config.owner, poller.config.lease_ttl_seconds)
    assert acq_a.acquired is True
    store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)

    b_first = poller.ingest(evt_b)
    assert b_first.outcome == "coalesced"

    def release_a_then_sleep(seconds):
        # Simulate A's blocking lease clearing WHILE the process stays up,
        # between two ticks of the SAME run_poll_loop call — exactly the gap
        # the review flagged (startup-only recovery would never see this).
        store.transition(key_a, State.AWAIT_REVIEW, actor=Actor.POLLER,
                          owner=poller.config.owner, fence=acq_a.fence)
        store.release(key_a, poller.config.owner, fence=acq_a.fence)

    actions = run_poll_loop(
        poller, interval_seconds=10.0, max_iterations=2, sleep=release_a_then_sleep
    )
    b_actions = [a for a in actions if a.event_id == "evt-b-loop"]
    # tick 1: still blocked (A live) → "coalesced" again; tick 2 (after A's
    # lease clears mid-sleep): actually driven → "escalated".
    assert [a.outcome for a in b_actions] == ["coalesced", "escalated"]
    assert store.get_state(key_b) == State.ESCALATED
    assert store.event_applied("evt-b-loop") is True


def test_poll_loop_unbounded_mode_does_not_retain_actions_in_memory():
    """Review r7 finding 1: run_poll_loop's REAL production mode is
    max_iterations=None (never returns) — accumulating every tick's actions
    into the return value there is an unbounded memory leak whenever a
    durable-inbox event stays blocked/coalesced tick after tick (a realistic,
    not hypothetical, case — see the two tests above). Build EXACTLY that
    permanently-blocked case (clock never advances, so A's lease never
    expires and B re-coalesces every tick, forever) and prove the returned
    list does NOT grow with tick count in unbounded mode, while `on_tick` —
    the sanctioned sink for that mode — genuinely observes every one of
    them."""
    clock = FakeClock()
    store = StateStore(clock=clock)
    poller = AutomationPoller(_config(), store)

    evt_a = _event(event_id="evt-a-mem", head_sha="sha-a", review_id="rev-a-mem",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b-mem", head_sha="sha-a", review_id="rev-b-mem",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = store.acquire(key_a, poller.config.owner, poller.config.lease_ttl_seconds)
    store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)
    assert poller.ingest(evt_b).outcome == "coalesced"

    seen_via_callback = []
    n_target = 200
    calls = {"n": 0}

    def stop():
        return calls["n"] >= n_target

    def count_sleep(seconds):
        calls["n"] += 1

    # NOTE: max_iterations is deliberately NOT passed — this is the
    # unbounded/production code path; only `stop` (a test-only affordance)
    # ends the loop, exactly as review r7 required this scenario be proven.
    result = run_poll_loop(
        poller, interval_seconds=1.0, stop=stop,
        sleep=count_sleep, on_tick=seen_via_callback.append,
    )
    assert result == []  # unbounded: never accumulates, however many ticks ran
    assert len(seen_via_callback) == n_target
    assert all(
        a.event_id == "evt-b-mem" and a.outcome == "coalesced"
        for tick_actions in seen_via_callback
        for a in tick_actions
    )


# ─────────────────────────── replay harness ─────────────────────────────


def test_run_replay_summary_is_deterministic_and_wall_safe():
    cfg = _config()
    events = [
        Event("e1", "hallovorld/renquant-orchestrator", 1, "s1", "review",
              "CHANGES_REQUESTED", "r1", "fix me"),
        Event("e1", "hallovorld/renquant-orchestrator", 1, "s1", "review",
              "CHANGES_REQUESTED", "r1", "fix me"),  # duplicate
        Event("e2", "hallovorld/renquant-orchestrator", 2, "s2", "review",
              "APPROVED", "r2", "lgtm"),
        Event("e3", "evil/repo", 3, "s3", "review", "APPROVED", "r3", "nope"),
    ]
    summary = run_replay(cfg, events)
    assert summary["human_gate_wall_ok"] is True
    outcomes = [a["outcome"] for a in summary["actions"]]
    assert outcomes == ["escalated", "duplicate", "merge_eligible", "ignored_untracked"]
    # no work item ever reaches MERGED / HUMAN_GATE
    assert all(
        w["state"] not in (State.MERGED.value, State.HUMAN_GATE.value)
        for w in summary["work_items"]
    )


def test_run_replay_poll_interval_folds_tick_actions_into_summary():
    """``run_replay``/``run_cli``'s opt-in wiring to :func:`run_poll_loop`
    (review r6): with ``poll_interval_seconds`` set, the one-shot replay's
    actions are followed by however many bounded ticks were requested, all
    folded into the same ``"actions"`` list — the CLI's real entry point
    into the live recovery loop."""
    cfg = _config()
    events = [
        Event("e1", "hallovorld/renquant-orchestrator", 1, "s1", "review",
              "APPROVED", "r1", "lgtm"),
    ]
    sleeps = []
    summary = run_replay(
        cfg, events,
        poll_interval_seconds=7.0, poll_max_iterations=2, poll_sleep=sleeps.append,
    )
    outcomes = [a["outcome"] for a in summary["actions"]]
    # the one-shot replay action, then 2 empty ticks (nothing pending after
    # the single event above already reached a terminal state) contribute no
    # further outcomes — but the loop still ran, proving the wiring fires.
    assert outcomes == ["merge_eligible"]
    assert sleeps == [7.0]  # 2 ticks → 1 sleep between them, none after


def test_run_replay_wires_startup_recover_before_ingest_and_poll(tmp_path):
    """Review r7 finding 2: ``run_cli -> run_replay`` constructed
    ``AutomationPoller`` and went straight to ``ingest_all``/``run_poll_loop``,
    NEVER calling :meth:`AutomationPoller.startup_recover` — so on a genuine
    process restart against a PERSISTENT db, an uncooperative cancellation
    was never hard-terminated, a plain crashed lease was never reconciled,
    and a coalesced durable-inbox event was never autonomously recovered
    before new work started.

    Build exactly that persisted state with a real poller, close the store
    (the crash/restart boundary), then drive the SAME db file through
    ``run_replay`` — the CLI's actual entry point, not ``poller.
    startup_recover()`` called directly by test code — and prove the
    cold-start recovery contract now runs there too, with its actions folded
    into the returned summary."""
    db = str(tmp_path / "cold-start.db")
    clock = FakeClock()
    store = StateStore(db, clock=clock)
    poller = AutomationPoller(_config(), store, termination_hook=NoopTerminationHook())

    # (a) an uncooperative cancellation: a FIXING run superseded by a newer
    # head, whose dangling lease expires with the (dead) executor never
    # acknowledging.
    key_uncoop = WorkKey("hallovorld/renquant-orchestrator", 91, "sha-old", "rev-uncoop")
    store.ensure_row(key_uncoop, State.FIXING)
    store.acquire(key_uncoop, "dead-owner-uncoop", ttl=100.0)
    store.supersede_stale("hallovorld/renquant-orchestrator", 91, "sha-new")
    clock.advance(101.0)

    # (b)+(c): A holds the PR-42 lease and "crashes" without ever releasing;
    # B coalesces behind it — a pending durable-inbox row with no external
    # redelivery, and A's own dangling lease is a second, independent
    # plain-expired-lease case.
    evt_a = _event(event_id="evt-a-cold", head_sha="sha-a", review_id="rev-a-cold",
                    state="CHANGES_REQUESTED")
    evt_b = _event(event_id="evt-b-cold", head_sha="sha-a", review_id="rev-b-cold",
                    state="CHANGES_REQUESTED")
    key_a = evt_a.row_key
    store.ensure_row(key_a, State.AWAIT_REVIEW)
    acq_a = store.acquire(key_a, poller.config.owner, poller.config.lease_ttl_seconds)
    assert acq_a.acquired is True
    store.transition(key_a, State.FIXING, actor=Actor.POLLER,
                      owner=poller.config.owner, fence=acq_a.fence)
    assert poller.ingest(evt_b).outcome == "coalesced"
    clock.advance(poller.config.lease_ttl_seconds + 1)  # A's lease TTL elapses; no release

    store.close()  # the crash / process exit — nothing more happens to this file
    # until a NEW process (run_replay below, with its own fresh StateStore)
    # opens it — exactly the cold-start scenario startup_recover exists for.

    summary = run_replay(_config(), [], db_path=db)

    outcomes_by_event = {a["event_id"]: a["outcome"] for a in summary["actions"]}
    # B was autonomously recovered as part of run_replay's now-wired cold-
    # start pass — never redelivered as an `events` item, never driven by
    # test code calling startup_recover/tick directly.
    assert outcomes_by_event.get("evt-b-cold") == "escalated"

    # Observable side effects confirm the FULL documented ordering ran (hard-
    # terminate uncooperative -> reconcile expired leases -> recover_pending),
    # not just the recovery half: both dangling leases were reconciled.
    reopened = StateStore(db)
    assert reopened.get_row(key_a)["lease_owner"] is None
    assert reopened.get_row(key_uncoop)["lease_owner"] is None
    assert reopened.event_applied("evt-b-cold") is True
    reopened.close()
