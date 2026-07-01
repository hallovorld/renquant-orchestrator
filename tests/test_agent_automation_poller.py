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

import pytest

from renquant_orchestrator.agent_automation_poller import (
    Actor,
    AutomationPoller,
    Event,
    FixResult,
    IllegalTransition,
    PollerConfig,
    State,
    StateStore,
    StubSandboxExecutor,
    WorkKey,
    assert_transition,
    classify_merge_risk,
    is_high_risk,
    merged_is_wall_protected,
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


def test_event_idempotency_duplicate_id_processed_once():
    clock = FakeClock()
    store = StateStore(clock=clock)
    evt = _event(event_id="rev-1")
    assert store.record_event(evt) is True
    assert store.record_event(evt) is False  # duplicate delivery id
    assert store.event_seen("rev-1") is True


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


def test_stale_cancel_on_head_sha_change():
    clock = FakeClock()
    store = StateStore(clock=clock)
    old = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    store.ensure_row(old, State.AWAIT_REVIEW)
    store.acquire(old, "w1", ttl=100.0)

    superseded = store.supersede_stale("hallovorld/renquant-orchestrator", 42, "sha-new")

    assert old in superseded
    assert store.is_superseded(old) is True
    row = store.get_row(old)
    assert row["lease_owner"] is None  # stale run drops its lease


def test_poller_supersedes_old_head_on_new_event():
    clock = FakeClock()
    store = StateStore(clock=clock)
    # dry-run keeps the fix in-flight at FIXING (non-terminal) so a new head can
    # supersede a genuinely in-flight run.
    poller = AutomationPoller(_config(dry_run=True), store)

    poller.ingest(_event(event_id="e-old", head_sha="sha-old", review_id="rev-1"))
    old = WorkKey("hallovorld/renquant-orchestrator", 42, "sha-old", "rev-1")
    assert store.get_state(old) == State.FIXING  # in-flight

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
    assert store.get_state(key) == State.FIXING


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
