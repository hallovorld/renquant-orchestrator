"""Deterministic control-plane for the agent-automation closed loop.

This is the SAFE, deterministic half of the event-driven agent-automation
design (``doc/design/2026-06-30-agent-automation-closed-loop.md``, §5 flow,
§6 atomic state/lease store, §6.3 single-owner transitions, §9 phased
rollout). It is **Phase-0/1 control plane only**:

  * an atomic SQLite state/lease store (§6) keyed by
    ``(repo, pr_number, head_sha, review_id)``;
  * the state machine (§4/§6.3) with a hard **human-gate wall** — no
    automated edge ever reaches ``MERGED``;
  * a read-only event ingestion + poller loop that drives transitions;
  * config-driven repo/PR allowlists and a ``--dry-run`` mode.

What this module deliberately does **NOT** do (explicit follow-ups, per the
design's §9 phased rollout and this PR's safety scope):

  * It never executes untrusted PR code. The ``FIXING`` executor is a stub
    (:class:`StubSandboxExecutor`) that raises ``NotImplementedError`` — the
    ephemeral OS/container/VM sandbox (§5.2/§7.5) is a follow-up PR.
  * It never merges. There is **no** automated transition into ``MERGED``;
    the poller's authority ends at ``MERGE_ELIGIBLE`` (§6.3). Ordinary
    approved PRs are still merged by the existing deterministic merge
    authority in :mod:`renquant_orchestrator.agent_workflows`; the high-risk
    set (§2.1) is surfaced to a human. This module composes with that merge
    authority and does not duplicate or weaken its distinct-identity /
    self-review protections.
  * It wires no push credentials.

Determinism / testability: every wall-clock read goes through an injectable
``clock`` callable, so leases/expiry are reproducible without real time.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Iterable, Iterator, Optional, Protocol, Sequence

from .agent_workflows import (
    PROD_PATH_RULES,
    STOP_LABELS,
)

# ───────────────────────────── state machine ─────────────────────────────


class State(str, Enum):
    """States in the closed-loop machine (design §4/§6.3)."""

    ALERT_RECEIVED = "ALERT_RECEIVED"
    TRIAGING = "TRIAGING"
    PR_OPEN = "PR_OPEN"
    AWAIT_REVIEW = "AWAIT_REVIEW"
    FIXING = "FIXING"
    MERGE_ELIGIBLE = "MERGE_ELIGIBLE"
    HUMAN_GATE = "HUMAN_GATE"
    # terminal / absorbing
    MERGED = "MERGED"
    HELD = "HELD"
    DROPPED = "DROPPED"
    ADVISORY_ONLY = "ADVISORY_ONLY"
    ESCALATED = "ESCALATED"
    PAUSED = "PAUSED"


#: Terminal states that never transition further under automation. ``PAUSED``
#: is intentionally NOT terminal — a human/scheduled reset resumes it (§8.4).
TERMINAL_STATES = frozenset(
    {
        State.MERGED,
        State.HELD,
        State.DROPPED,
        State.ADVISORY_ONLY,
        State.ESCALATED,
    }
)


class Actor(str, Enum):
    """Who is authorised to perform a transition (design §6.3).

    * ``POLLER`` — this deterministic control plane. Its authority ENDS at
      ``MERGE_ELIGIBLE``; it can never cross the human-gate wall.
    * ``MERGE_AUTHORITY`` — the SEPARATE deterministic merge step in
      ``agent_workflows.py`` (ordinary approved PRs) / the surface-to-human
      step for the high-risk set. Not wired by this module.
    * ``HUMAN`` — the operator. Sole owner of ``HUMAN_GATE → {MERGED,HELD}``.
    """

    POLLER = "poller"
    MERGE_AUTHORITY = "merge_authority"
    HUMAN = "human"


#: Legal transitions → the set of actors permitted to make each one.
#:
#: The human-gate wall (design §6.3, ``doc/agent-pr-workflows.md``): NO edge
#: into ``MERGED`` admits ``POLLER``. The poller's reach stops at
#: ``MERGE_ELIGIBLE``; only ``MERGE_AUTHORITY`` (ordinary PRs, a distinct
#: deterministic step) or a ``HUMAN`` (via ``HUMAN_GATE``) can reach a merge.
_TRANSITIONS: dict[tuple[State, State], frozenset[Actor]] = {
    (State.ALERT_RECEIVED, State.TRIAGING): frozenset({Actor.POLLER}),
    (State.ALERT_RECEIVED, State.DROPPED): frozenset({Actor.POLLER}),
    (State.TRIAGING, State.PR_OPEN): frozenset({Actor.POLLER}),
    (State.TRIAGING, State.ADVISORY_ONLY): frozenset({Actor.POLLER}),
    (State.TRIAGING, State.DROPPED): frozenset({Actor.POLLER}),
    (State.PR_OPEN, State.AWAIT_REVIEW): frozenset({Actor.POLLER}),
    (State.AWAIT_REVIEW, State.FIXING): frozenset({Actor.POLLER}),
    (State.AWAIT_REVIEW, State.MERGE_ELIGIBLE): frozenset({Actor.POLLER}),
    (State.AWAIT_REVIEW, State.ESCALATED): frozenset({Actor.POLLER}),
    (State.FIXING, State.AWAIT_REVIEW): frozenset({Actor.POLLER}),
    (State.FIXING, State.ESCALATED): frozenset({Actor.POLLER}),
    # ── the human-gate wall ──────────────────────────────────────────────
    # MERGE_ELIGIBLE onward is NEVER a poller edge. Ordinary PRs are merged
    # by the separate MERGE_AUTHORITY; the high-risk set is surfaced to the
    # human gate by that same authority. This module drives neither.
    (State.MERGE_ELIGIBLE, State.MERGED): frozenset({Actor.MERGE_AUTHORITY}),
    (State.MERGE_ELIGIBLE, State.HUMAN_GATE): frozenset({Actor.MERGE_AUTHORITY}),
    (State.HUMAN_GATE, State.MERGED): frozenset({Actor.HUMAN}),
    (State.HUMAN_GATE, State.HELD): frozenset({Actor.HUMAN}),
    # ── budget guard (§8.4): pause active work; human/scheduled reset ─────
    (State.PR_OPEN, State.PAUSED): frozenset({Actor.POLLER}),
    (State.AWAIT_REVIEW, State.PAUSED): frozenset({Actor.POLLER}),
    (State.FIXING, State.PAUSED): frozenset({Actor.POLLER}),
    (State.TRIAGING, State.PAUSED): frozenset({Actor.POLLER}),
    (State.PAUSED, State.AWAIT_REVIEW): frozenset({Actor.HUMAN, Actor.POLLER}),
    (State.PAUSED, State.TRIAGING): frozenset({Actor.HUMAN, Actor.POLLER}),
}


class IllegalTransition(RuntimeError):
    """Raised when a state transition is not in the legal graph / actor set."""


def transition_allowed(frm: State, to: State, actor: Actor) -> bool:
    """True iff ``frm → to`` is a legal edge AND ``actor`` may perform it."""
    actors = _TRANSITIONS.get((State(frm), State(to)))
    return bool(actors) and Actor(actor) in actors


def assert_transition(frm: State, to: State, actor: Actor) -> None:
    """Raise :class:`IllegalTransition` unless the transition is permitted."""
    if State(frm) in TERMINAL_STATES:
        raise IllegalTransition(f"{frm.value} is terminal; cannot transition to {to.value}")
    if (State(frm), State(to)) not in _TRANSITIONS:
        raise IllegalTransition(f"no legal edge {frm.value} → {to.value}")
    if not transition_allowed(frm, to, actor):
        raise IllegalTransition(
            f"actor {Actor(actor).value!r} may not perform {frm.value} → {to.value}"
        )


def merged_is_wall_protected() -> bool:
    """Invariant check: NO transition into ``MERGED`` admits the poller.

    Used by tests and observability to assert the human-gate wall holds by
    construction — the poller can never auto-merge.
    """
    for (frm, to), actors in _TRANSITIONS.items():
        if to == State.MERGED and Actor.POLLER in actors:
            return False
    return True


# ─────────────────────────── merge-risk policy ──────────────────────────

# Additional high-risk patterns beyond agent_workflows.PROD_PATH_RULES,
# per design §2.1 (pin/deploy + policy/guardrail changes). Kept as plain
# substring/prefix checks so the classification is deterministic, never an
# LLM judgement.
_PIN_DEPLOY_HINTS = (
    "subrepos.lock.json",
    "promote",
    "pin_manifest",
    "pins/",
    "deploy/",
)
_POLICY_PATH_HINTS = (
    ".github/",
    "src/renquant_orchestrator/agent_workflows.py",
    "src/renquant_orchestrator/agent_automation_poller.py",
    "doc/agent-pr-workflows.md",
)
_GENERATED_LABELS = ("agent:auto-generated",)


def classify_merge_risk(pr: dict) -> list[str]:
    """Return the design §2.1 high-risk reasons a PR is merge-frozen.

    Empty list ⇒ ordinary PR (the existing deterministic merge authority may
    merge it). Non-empty ⇒ mandatory human hold. Reuses
    ``agent_workflows.PROD_PATH_RULES`` / ``STOP_LABELS`` rather than
    re-deriving them, so this composes with the existing merge policy.
    """
    reasons: list[str] = []
    labels = {lbl.get("name") for lbl in (pr.get("labels") or [])}
    paths = [
        str(row.get("path") or "")
        for row in (pr.get("files") or [])
        if str(row.get("path") or "")
    ]

    for path in paths:
        for label, pattern in PROD_PATH_RULES:
            if pattern.search(path):
                reasons.append(f"production path `{path}` ({label})")
                break

    for path in paths:
        low = path.lower()
        if any(hint in low for hint in _PIN_DEPLOY_HINTS):
            reasons.append(f"pin/deploy path `{path}`")
        if any(path == hint or path.startswith(hint) for hint in _POLICY_PATH_HINTS):
            reasons.append(f"policy/guardrail path `{path}`")

    if any(lbl in labels for lbl in _GENERATED_LABELS):
        reasons.append("agent-authored / auto-generated PR")

    for stop in STOP_LABELS:
        if stop in labels:
            reasons.append(f"escalation label `{stop}`")

    # de-dup while preserving order
    seen: set[str] = set()
    return [r for r in reasons if not (r in seen or seen.add(r))]


def is_high_risk(pr: dict) -> bool:
    """True if the PR falls in the design §2.1 human-hold set."""
    return bool(classify_merge_risk(pr))


# ───────────────────────────── event model ──────────────────────────────


@dataclass(frozen=True)
class Event:
    """An inbound trigger the poller ingests (design §5/§6).

    ``event_id`` is the delivery id used for idempotency (a redelivered event
    with a seen id is a no-op). ``review_id`` scopes the work-item row along
    with ``(repo, pr_number, head_sha)`` so a stale-head event is a different
    row and never acts on the current head.
    """

    event_id: str
    repo: str
    pr_number: int
    head_sha: str
    kind: str  # "review" | "comment" | "alert"
    state: Optional[str] = None  # CHANGES_REQUESTED / APPROVED for reviews
    review_id: str = ""
    body: str = ""

    @property
    def row_key(self) -> "WorkKey":
        return WorkKey(self.repo, self.pr_number, self.head_sha, self.review_id)


@dataclass(frozen=True)
class WorkKey:
    repo: str
    pr_number: int
    head_sha: str
    review_id: str = ""

    def as_tuple(self) -> tuple[str, int, str, str]:
        return (self.repo, self.pr_number, self.head_sha, self.review_id)


# ─────────────────────────── atomic state store ─────────────────────────


@dataclass(frozen=True)
class ClaimResult:
    """Outcome of an EXCLUSIVE event claim (design §6.3, review point 3).

    * ``proceed`` — the caller owns the processing claim and must drive the
      event (a brand-new claim, or a reclaim of a crashed owner's expired
      processing lease).
    * ``disposition`` — ``"new"`` | ``"reclaimed"`` | ``"applied"`` |
      ``"in_progress"``. ``"applied"`` is a true duplicate (already fully
      applied); ``"in_progress"`` means another owner currently holds a LIVE
      processing lease, so the caller must NOT process it — it will be
      redelivered and reclaimed once that lease expires. This is what makes two
      concurrent deliveries at-most-once, not merely coalesced.
    * ``result_json`` — the recorded terminal action for a duplicate.
    """

    proceed: bool
    disposition: str = ""
    result_json: Optional[str] = None


@dataclass(frozen=True)
class AcquireResult:
    acquired: bool
    reason: str = ""
    #: Monotonic fencing token for the lease generation (design §6.2). The
    #: holder MUST thread this back into :meth:`StateStore.transition` /
    #: :meth:`StateStore.release`; a reclaimed old holder carries a stale fence
    #: and can therefore never commit against a re-acquired lease — even when
    #: the reclaimer re-uses the same ``owner`` id.
    fence: int = 0


_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_items (
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
CREATE TABLE IF NOT EXISTS processed_events (
    event_id     TEXT PRIMARY KEY,
    repo         TEXT NOT NULL,
    pr_number    INTEGER NOT NULL,
    head_sha     TEXT,
    -- 'processing' = claimed but the state mutation is not yet applied;
    -- 'applied'    = the driven transition committed. Only 'applied' is a
    -- true duplicate: a crash mid-flight leaves 'processing', which is
    -- re-drivable on redelivery (never a silent "duplicate" that loses work).
    status       TEXT NOT NULL DEFAULT 'processing',
    -- EXCLUSIVE processing claim (design §6.3): the owner that claimed the
    -- event and the lease under which it is being processed. A second delivery
    -- of the SAME event id (a redelivery / a concurrent worker) can only take
    -- over once this processing lease EXPIRES — so two owners can never both
    -- enter ``_process_claimed`` for one event. Distinct poller processes MUST
    -- use distinct ``owner`` ids (the same invariant as the work-item lease).
    owner        TEXT,
    lease_expiry REAL,
    -- the recorded terminal :class:`Action` (outcome/detail) for this event id,
    -- persisted atomically with the applied marker, so a true duplicate can be
    -- answered from the ledger instead of re-driving.
    result_json  TEXT,
    processed_at REAL NOT NULL,
    applied_at   REAL
);
"""

_TERMINAL_SQL = ",".join(f"'{s.value}'" for s in TERMINAL_STATES)


class StateStore:
    """Single-owner atomic SQLite state/lease store (design §6).

    One writer owns each state transition; the ``(repo, pr, head_sha,
    review_id)`` key makes stale events harmless, ``processed_events`` gives
    idempotency, and the lease CAS gives at-most-one in-flight fix per PR.
    All time comes from an injected ``clock`` for deterministic tests.
    """

    def __init__(self, path: str = ":memory:", *, clock: Callable[[], float] = time.time):
        self._clock = clock
        # ``isolation_level=None`` puts the driver in autocommit mode: single
        # statements commit immediately, and every multi-statement critical
        # section runs inside an EXPLICIT ``BEGIN IMMEDIATE`` (see ``_immediate``)
        # so the whole read-then-write is one serialised transaction. This is
        # what makes PR-level lease exclusion atomic across connections.
        # check_same_thread=False so a test can simulate a second worker via a
        # second StateStore over the same file; SQLite serialises the writes.
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout = 5000")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def _immediate(self) -> Iterator[sqlite3.Connection]:
        """Run a ``BEGIN IMMEDIATE … COMMIT`` critical section.

        ``BEGIN IMMEDIATE`` takes the write (RESERVED) lock up front, so two
        connections can never interleave the read-then-write inside — the
        second blocks (``busy_timeout``) until the first commits. Any exception
        rolls the whole section back, leaving no partial state.
        """
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield self._db
        except BaseException:
            self._db.rollback()
            raise
        else:
            self._db.commit()

    # ── rows ──────────────────────────────────────────────────────────────

    def ensure_row(self, key: WorkKey, state: State) -> None:
        """Insert the work-item row at ``state`` if it does not yet exist."""
        now = self._clock()
        self._db.execute(
            "INSERT OR IGNORE INTO work_items "
            "(repo, pr_number, head_sha, review_id, state, fence, attempt, superseded, "
            " cancel_requested, pending_rerun, created_at, updated_at) "
            "VALUES (?,?,?,?,?,0,0,0,0,0,?,?)",
            (*key.as_tuple(), State(state).value, now, now),
        )

    def get_row(self, key: WorkKey) -> Optional[dict]:
        cur = self._db.execute(
            "SELECT * FROM work_items WHERE repo=? AND pr_number=? "
            "AND head_sha=? AND review_id=?",
            key.as_tuple(),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_state(self, key: WorkKey) -> Optional[State]:
        row = self.get_row(key)
        return State(row["state"]) if row else None

    # ── event idempotency (§6.3, review point 3) ───────────────────────────

    def claim_event(self, event: Event, owner: str, ttl: float) -> ClaimResult:
        """EXCLUSIVELY claim an inbound event for processing (idempotency ledger).

        The whole claim runs in ONE ``BEGIN IMMEDIATE`` transaction, so two
        deliveries of the same ``event_id`` — a redelivery or a concurrent
        worker — cannot both win it:

          * brand-new id → inserted ``processing`` with an owner + lease →
            ``proceed=True`` (``"new"``);
          * already ``applied`` → a true duplicate → ``proceed=False``
            (``"applied"``), carrying the recorded terminal action;
          * ``processing`` with a LIVE lease held by ANOTHER owner → a
            concurrent worker is mid-flight → ``proceed=False``
            (``"in_progress"``): the caller must NOT process it (that is what
            makes two concurrent deliveries at-most-once, not merely coalesced);
            it is redelivered and reclaimed after that lease expires;
          * ``processing`` whose lease is EXPIRED, or is held by THIS SAME
            ``owner`` → the prior attempt (a crash, or an immediate same-worker
            redelivery) is ours to resume → reclaimed → ``proceed=True``
            (``"reclaimed"``). Same-owner reclaim is safe because one worker
            drives its own deliveries serially — it can never race itself — and
            it is what lets an in-process redelivery re-drive at once instead of
            stalling until its own lease TTL elapses.

        Recovery of a crashed in-flight event is therefore lease-driven, exactly
        like the work-item lease: a DIFFERENT owner re-drives only on the first
        redelivery after the processing lease TTL, never while the prior owner
        might still be live.
        """
        now = self._clock()
        with self._immediate() as db:
            cur = db.execute(
                "INSERT OR IGNORE INTO processed_events "
                "(event_id, repo, pr_number, head_sha, status, owner, lease_expiry, "
                " processed_at) "
                "VALUES (?,?,?,?, 'processing', ?, ?, ?)",
                (event.event_id, event.repo, event.pr_number, event.head_sha,
                 owner, now + ttl, now),
            )
            if cur.rowcount == 1:
                return ClaimResult(True, "new")
            row = db.execute(
                "SELECT status, owner, lease_expiry, result_json FROM processed_events "
                "WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            if row is not None and row["status"] == "applied":
                return ClaimResult(False, "applied", result_json=row["result_json"])
            # Still 'processing': reclaim iff the prior processing lease has
            # expired (crashed owner) OR it is already held by THIS owner (our
            # own crash / immediate redelivery). A LIVE lease held by a DIFFERENT
            # owner is exclusive — refuse.
            expiry = row["lease_expiry"] if row is not None else None
            same_owner = row is not None and row["owner"] == owner
            if expiry is None or expiry <= now or same_owner:
                taken = db.execute(
                    "UPDATE processed_events SET owner=?, lease_expiry=? "
                    "WHERE event_id=? AND status='processing' "
                    "AND (lease_expiry IS NULL OR lease_expiry <= ? OR owner=?)",
                    (owner, now + ttl, event.event_id, now, owner),
                ).rowcount
                if taken == 1:
                    return ClaimResult(True, "reclaimed")
                # lost the reclaim race to another owner in the same instant
                return ClaimResult(False, "in_progress")
            return ClaimResult(False, "in_progress")

    def mark_event_applied(self, event_id: str, result_json: Optional[str] = None) -> None:
        """Mark a claimed event as fully applied and record its terminal action.

        Idempotent and first-writer-wins: ``COALESCE`` preserves the
        ``applied_at`` / ``result_json`` written by a folded
        :meth:`transition_and_apply`, so calling this again from ``ingest`` (the
        no-mutation paths) never overwrites the atomic record. Clears the
        processing lease — the event is done.
        """
        now = self._clock()
        self._db.execute(
            "UPDATE processed_events SET status='applied', "
            "applied_at=COALESCE(applied_at, ?), result_json=COALESCE(result_json, ?), "
            "owner=NULL, lease_expiry=NULL "
            "WHERE event_id=?",
            (now, result_json, event_id),
        )

    def event_seen(self, event_id: str) -> bool:
        cur = self._db.execute(
            "SELECT 1 FROM processed_events WHERE event_id=?", (event_id,)
        )
        return cur.fetchone() is not None

    def event_applied(self, event_id: str) -> bool:
        cur = self._db.execute(
            "SELECT 1 FROM processed_events WHERE event_id=? AND status='applied'",
            (event_id,),
        )
        return cur.fetchone() is not None

    # ── lease acquire / release (§6.2) ─────────────────────────────────────

    def acquire(self, key: WorkKey, owner: str, ttl: float) -> AcquireResult:
        """Atomically acquire the lease on a work item (compare-and-set).

        The PR-busy coalescing check AND the row acquisition run inside ONE
        ``BEGIN IMMEDIATE`` transaction, so two workers targeting DIFFERENT
        ``(head_sha, review_id)`` rows of the SAME ``(repo, pr)`` can never both
        observe ``busy=0`` and each acquire — the second serialises behind the
        first's commit and coalesces.

        Semantics (design §6.2):
          * two acquirers on the SAME key → exactly one wins (CAS on the row);
          * a second live lease on a DIFFERENT head/review of the SAME
            ``(repo, pr)`` → coalesce: flag ``pending_rerun`` and do not start
            a concurrent run;
          * an expired lease (crashed owner) is reclaimable, and the lease
            ``fence`` is bumped so the reclaimed owner cannot commit.

        A successful acquire clears ``pending_rerun`` — the row is no longer
        merely "waiting to be picked up", it is now actually being driven. The
        caller (:meth:`AutomationPoller._handle_lease_contention`) is what
        guarantees a coalesced event's ``pending_rerun=1`` row is eventually
        re-examined by a later acquirer rather than silently dropped.
        """
        now = self._clock()
        with self._immediate() as db:
            db.execute(
                "INSERT OR IGNORE INTO work_items "
                "(repo, pr_number, head_sha, review_id, state, fence, attempt, superseded, "
                " cancel_requested, pending_rerun, created_at, updated_at) "
                "VALUES (?,?,?,?,?,0,0,0,0,0,?,?)",
                (*key.as_tuple(), State.AWAIT_REVIEW.value, now, now),
            )

            row = db.execute(
                "SELECT superseded FROM work_items WHERE repo=? AND pr_number=? "
                "AND head_sha=? AND review_id=?",
                key.as_tuple(),
            ).fetchone()
            if row is not None and row["superseded"]:
                return AcquireResult(False, "superseded: row cancelled by a newer head")

            # PR-busy coalescing: another non-terminal, non-superseded row for
            # the same (repo, pr) holds a live lease on a different head/review.
            busy = db.execute(
                f"SELECT count(*) AS n FROM work_items "
                f"WHERE repo=? AND pr_number=? "
                f"AND NOT (head_sha=? AND review_id=?) "
                f"AND superseded=0 AND state NOT IN ({_TERMINAL_SQL}) "
                f"AND lease_owner IS NOT NULL AND lease_expiry > ?",
                (key.repo, key.pr_number, key.head_sha, key.review_id, now),
            ).fetchone()["n"]
            if busy:
                db.execute(
                    "UPDATE work_items SET pending_rerun=1, updated_at=? "
                    "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
                    (now, *key.as_tuple()),
                )
                return AcquireResult(False, "coalesced: another fix in-flight for this PR")

            cur = db.execute(
                "UPDATE work_items SET lease_owner=?, lease_expiry=?, fence=fence+1, "
                "cancel_requested=0, pending_rerun=0, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? "
                "AND superseded=0 "
                "AND (lease_owner IS NULL OR lease_expiry <= ?)",
                (owner, now + ttl, now, *key.as_tuple(), now),
            )
            if cur.rowcount == 1:
                fence = db.execute(
                    "SELECT fence FROM work_items WHERE repo=? AND pr_number=? "
                    "AND head_sha=? AND review_id=?",
                    key.as_tuple(),
                ).fetchone()["fence"]
                return AcquireResult(True, "acquired", fence=int(fence))
            return AcquireResult(False, "lease already held")

    def holds_lease(self, key: WorkKey, owner: str) -> bool:
        row = self.get_row(key)
        if not row or row["lease_owner"] != owner:
            return False
        return (row["lease_expiry"] or 0) > self._clock()

    def release(self, key: WorkKey, owner: str, *, fence: Optional[int] = None) -> bool:
        """Release the lease held by ``owner``.

        When ``fence`` is supplied the release is fenced: a stale holder whose
        generation was superseded/reclaimed (possibly re-using the same
        ``owner`` id) will NOT clobber the current holder's lease.
        """
        sql = (
            "UPDATE work_items SET lease_owner=NULL, lease_expiry=NULL, updated_at=? "
            "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? AND lease_owner=?"
        )
        params: list = [self._clock(), *key.as_tuple(), owner]
        if fence is not None:
            sql += " AND fence=?"
            params.append(int(fence))
        cur = self._db.execute(sql, params)
        return cur.rowcount == 1

    # ── stale-run cancellation (§6.3) ──────────────────────────────────────

    def supersede_stale(self, repo: str, pr_number: int, current_head: str) -> list[WorkKey]:
        """Request cancellation of every non-terminal row on an OLD head when
        the head advances. Returns the superseded keys.

        The row is flagged ``superseded=1, cancel_requested=1`` but its lease is
        RETAINED (the PR-level lease is not dropped) until the in-flight
        executor ACKNOWLEDGES cancellation via
        :meth:`acknowledge_cancellation` / a fenced :meth:`release`. This is
        what stops an old executor from racing the new head: the new head is a
        different (non-superseded) row and proceeds, while any output the old
        run exports is fenced out by :meth:`fence_ok`. A crashed old executor
        that never acknowledges has its dangling lease swept once it expires by
        :meth:`reconcile_expired_leases`.
        """
        now = self._clock()
        with self._immediate() as db:
            cur = db.execute(
                f"SELECT repo, pr_number, head_sha, review_id FROM work_items "
                f"WHERE repo=? AND pr_number=? AND head_sha != ? "
                f"AND superseded=0 AND state NOT IN ({_TERMINAL_SQL})",
                (repo, pr_number, current_head),
            )
            stale = [
                WorkKey(r["repo"], r["pr_number"], r["head_sha"], r["review_id"]) for r in cur
            ]
            if stale:
                db.execute(
                    f"UPDATE work_items SET superseded=1, cancel_requested=1, updated_at=? "
                    f"WHERE repo=? AND pr_number=? AND head_sha != ? "
                    f"AND superseded=0 AND state NOT IN ({_TERMINAL_SQL})",
                    (now, repo, pr_number, current_head),
                )
        return stale

    def acknowledge_cancellation(self, key: WorkKey) -> bool:
        """The in-flight executor acknowledges a supersede: drop its lease.

        Only meaningful for a ``cancel_requested`` row; clears the retained
        lease so the PR is fully released once the old run has wound down.
        """
        now = self._clock()
        cur = self._db.execute(
            "UPDATE work_items SET lease_owner=NULL, lease_expiry=NULL, "
            "cancel_requested=0, updated_at=? "
            "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
            (now, *key.as_tuple()),
        )
        return cur.rowcount == 1

    def is_superseded(self, key: WorkKey) -> bool:
        row = self.get_row(key)
        return bool(row and row["superseded"])

    def fence_ok(self, key: WorkKey, fence: int, head_sha: str) -> bool:
        """True iff an exported patch/push may still be applied.

        Fences every executor output by lease generation + current head SHA
        (design §6.3): the row must be un-superseded, still carry the acquiring
        ``fence`` generation, and match the head the fix was computed against. A
        superseded run, a head that advanced, or a reclaimed lease all fail —
        so a stale run's patch is discarded, never pushed.
        """
        row = self.get_row(key)
        if row is None:
            return False
        if row["superseded"]:
            return False
        if row["head_sha"] != head_sha:
            return False
        return int(row["fence"]) == int(fence)

    # ── transitions (§6.3, single owner) ───────────────────────────────────

    def _do_transition(
        self,
        db: sqlite3.Connection,
        key: WorkKey,
        to: State,
        *,
        actor: Actor,
        owner: Optional[str],
        fence: Optional[int],
        require_lease: bool,
    ) -> State:
        """Enforce + apply one transition on ``db`` (autocommit OR inside a
        ``BEGIN IMMEDIATE``). Split out so :meth:`transition` and
        :meth:`transition_and_apply` share exactly one fenced-UPDATE code path.
        """
        row = db.execute(
            "SELECT state, superseded FROM work_items "
            "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
            key.as_tuple(),
        ).fetchone()
        if row is None:
            raise IllegalTransition(f"no work item for {key.as_tuple()}")
        if row["superseded"]:
            raise IllegalTransition(f"work item {key.as_tuple()} is superseded")
        frm = State(row["state"])
        assert_transition(frm, to, actor)

        now = self._clock()
        if require_lease and Actor(actor) is Actor.POLLER:
            sql = (
                "UPDATE work_items SET state=?, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? "
                "AND state=? AND superseded=0 "
                "AND lease_owner=? AND lease_expiry>?"
            )
            params: list = [
                State(to).value, now, *key.as_tuple(), frm.value, owner or "", now,
            ]
            if fence is not None:
                sql += " AND fence=?"
                params.append(int(fence))
            cur = db.execute(sql, params)
            if cur.rowcount != 1:
                raise IllegalTransition(
                    f"poller cannot transition {frm.value} → {to.value} for "
                    f"{key.as_tuple()}: lease lost, expired, reclaimed (stale fence), "
                    f"or state changed under it"
                )
            return State(to)

        cur = db.execute(
            "UPDATE work_items SET state=?, updated_at=? "
            "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? "
            "AND state=? AND superseded=0",
            (State(to).value, now, *key.as_tuple(), frm.value),
        )
        if cur.rowcount != 1:
            raise IllegalTransition(
                f"lost race transitioning {frm.value} → {to.value} for {key.as_tuple()}"
            )
        return State(to)

    def transition(
        self,
        key: WorkKey,
        to: State,
        *,
        actor: Actor,
        owner: Optional[str] = None,
        fence: Optional[int] = None,
        require_lease: bool = True,
    ) -> State:
        """Atomically move a work item to ``to`` under a single writer.

        Enforces the legal transition graph AND actor authorisation (the
        human-gate wall lives here). For a ``POLLER`` transition the state
        UPDATE is FENCED BY THE LEASE in one statement: it requires the current
        row to still be at the expected ``frm`` state, un-superseded, and leased
        to ``owner`` with ``lease_expiry`` in the future — plus, when supplied,
        the acquiring ``fence`` generation. So if the lease expires or is
        reclaimed (even by the same ``owner`` id) between check and commit, the
        stale owner's transition simply fails; it can never commit.
        """
        return self._do_transition(
            self._db, key, to, actor=actor, owner=owner, fence=fence,
            require_lease=require_lease,
        )

    def transition_and_apply(
        self,
        key: WorkKey,
        to: State,
        *,
        actor: Actor,
        event_id: str,
        result_json: Optional[str],
        owner: Optional[str] = None,
        fence: Optional[int] = None,
        require_lease: bool = True,
    ) -> State:
        """Apply an event's FINAL transition AND mark the event applied in ONE
        transaction (design §6.3, review point 3).

        Folding the two commits closes the exact crash window the reviewer
        flagged: a crash can never leave the row transitioned but the event
        un-applied (which would RE-DRIVE and duplicate the side effect on
        redelivery), nor the event applied but the row not transitioned. Either
        both commit or neither does — so redelivery after this point is a true
        duplicate, and redelivery before it re-drives cleanly from the prior
        state.
        """
        now = self._clock()
        with self._immediate() as db:
            result = self._do_transition(
                db, key, to, actor=actor, owner=owner, fence=fence,
                require_lease=require_lease,
            )
            db.execute(
                "UPDATE processed_events SET status='applied', "
                "applied_at=COALESCE(applied_at, ?), "
                "result_json=COALESCE(result_json, ?), "
                "owner=NULL, lease_expiry=NULL "
                "WHERE event_id=?",
                (now, result_json, event_id),
            )
        return result

    def begin_fix_round(
        self, key: WorkKey, *, owner: str, fence: int, max_rounds: int
    ) -> tuple[str, int]:
        """Atomically bump the attempt counter AND make the round decision +
        transition in ONE transaction (design §8.1, review point 3).

        Folding the bump with the transition means a crash can never leave the
        attempt incremented without the matching state change (an inflated round
        counter that would escalate early) or vice versa — so a resumed
        redelivery, which finds the row already at ``FIXING``, must NOT call this
        again. Requires the row at ``AWAIT_REVIEW``, un-superseded, and still
        leased to ``owner`` at the acquiring ``fence`` generation. Returns
        ``("fixing", attempt)`` (drive into the executor) or
        ``("escalated", attempt)`` (round cap reached; the row is now
        ``ESCALATED``, a terminal state).
        """
        now = self._clock()
        with self._immediate() as db:
            row = db.execute(
                "SELECT state, superseded, attempt, lease_owner, lease_expiry, fence "
                "FROM work_items WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
                key.as_tuple(),
            ).fetchone()
            if row is None:
                raise IllegalTransition(f"no work item for {key.as_tuple()}")
            if row["superseded"]:
                raise IllegalTransition(f"work item {key.as_tuple()} is superseded")
            frm = State(row["state"])
            if frm is not State.AWAIT_REVIEW:
                raise IllegalTransition(
                    f"begin_fix_round requires AWAIT_REVIEW, got {frm.value} "
                    f"for {key.as_tuple()}"
                )
            if (
                row["lease_owner"] != owner
                or (row["lease_expiry"] or 0) <= now
                or int(row["fence"]) != int(fence)
            ):
                raise IllegalTransition(
                    f"begin_fix_round: lease lost/expired/reclaimed for {key.as_tuple()}"
                )
            attempt = int(row["attempt"]) + 1
            to = State.ESCALATED if attempt >= max_rounds else State.FIXING
            assert_transition(frm, to, Actor.POLLER)
            cur = db.execute(
                "UPDATE work_items SET attempt=?, state=?, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? "
                "AND state=? AND superseded=0 AND lease_owner=? AND lease_expiry>? AND fence=?",
                (attempt, to.value, now, *key.as_tuple(), State.AWAIT_REVIEW.value,
                 owner, now, int(fence)),
            )
            if cur.rowcount != 1:
                raise IllegalTransition(f"begin_fix_round CAS failed for {key.as_tuple()}")
            return ("escalated" if to is State.ESCALATED else "fixing", attempt)

    # ── durable cancellation ownership / heartbeat (§6.3, review point 4) ───

    def heartbeat(self, key: WorkKey, owner: str, fence: int, ttl: float) -> bool:
        """Renew the executor lease (durable liveness / ownership heartbeat).

        A long-running (real) executor MUST call this periodically to keep its
        lease alive. Only the CURRENT live holder — matching ``owner`` and the
        acquiring ``fence`` generation, not yet expired — can renew. If the
        executor crashes or hangs it stops heart-beating, the lease expires, and
        :meth:`reconcile_expired_leases` reclaims the work — so liveness is
        durable state, never an in-memory token. Returns ``True`` on renew.
        """
        now = self._clock()
        cur = self._db.execute(
            "UPDATE work_items SET lease_expiry=?, updated_at=? "
            "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? "
            "AND lease_owner=? AND fence=? AND lease_expiry>?",
            (now + ttl, now, *key.as_tuple(), owner, int(fence), now),
        )
        return cur.rowcount == 1

    def request_cancellation(self, key: WorkKey) -> bool:
        """Durably request cancellation of an in-flight run (operator / budget
        abort), independent of a head advance. Sets the persisted
        ``cancel_requested`` flag; the lease is RETAINED until the executor
        acknowledges (or its lease expires and is reclaimed). Returns ``True``
        if a non-terminal row was flagged.
        """
        now = self._clock()
        cur = self._db.execute(
            f"UPDATE work_items SET cancel_requested=1, updated_at=? "
            f"WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? "
            f"AND state NOT IN ({_TERMINAL_SQL})",
            (now, *key.as_tuple()),
        )
        return cur.rowcount == 1

    def is_cancellation_requested(self, key: WorkKey) -> bool:
        """True iff cancellation is durably requested for this row.

        This is the SOURCE OF TRUTH an executor (in ANY process, after ANY
        restart) polls — a persisted flag, not the poller's in-memory token. It
        is what makes cancellation survive a poller restart.
        """
        row = self.get_row(key)
        return bool(row and (row["cancel_requested"] or row["superseded"]))

    def list_uncooperative_cancellations(self) -> list[WorkKey]:
        """Rows whose cancellation was durably requested but whose retained
        lease has EXPIRED without the executor acknowledging — i.e. a run that
        did not stop cooperatively within its lease. These are the runs a hard
        termination mechanism must forcibly tear down (see
        :class:`TerminationHook`); a retained flag alone cannot stop untrusted
        work.
        """
        now = self._clock()
        cur = self._db.execute(
            "SELECT repo, pr_number, head_sha, review_id FROM work_items "
            "WHERE cancel_requested=1 AND lease_owner IS NOT NULL AND lease_expiry <= ?",
            (now,),
        )
        return [WorkKey(r["repo"], r["pr_number"], r["head_sha"], r["review_id"]) for r in cur]

    # ── crash recovery (§6.3) ──────────────────────────────────────────────

    def reconcile_expired_leases(
        self, *, ground_truth: Optional[Callable[[WorkKey], bool]] = None
    ) -> list[WorkKey]:
        """Sweep expired leases on poller start (crash recovery).

        Two sweeps: (a) a SUPERSEDED row whose retained cancellation lease has
        expired — the old executor crashed without acknowledging — just has its
        dangling lease cleared; (b) an ACTIVE row whose lease expired without
        release is reconciled against ground truth (if provided — e.g. is the
        PR still open / did the push land?) BEFORE reclaiming, then its lease is
        cleared so exactly one recoverer may re-acquire (with a bumped fence).
        Never blindly re-runs. Returns the reclaimed (re-runnable) keys.
        """
        now = self._clock()
        # (a) dangling cancellation lease from a crashed, superseded old run.
        self._db.execute(
            "UPDATE work_items SET lease_owner=NULL, lease_expiry=NULL, "
            "cancel_requested=0, updated_at=? "
            "WHERE lease_owner IS NOT NULL AND lease_expiry <= ? AND superseded=1",
            (now, now),
        )
        # (b) active rows whose lease expired without release.
        cur = self._db.execute(
            f"SELECT repo, pr_number, head_sha, review_id FROM work_items "
            f"WHERE lease_owner IS NOT NULL AND lease_expiry <= ? "
            f"AND superseded=0 AND state NOT IN ({_TERMINAL_SQL})",
            (now,),
        )
        expired = [WorkKey(r["repo"], r["pr_number"], r["head_sha"], r["review_id"]) for r in cur]
        reclaimed: list[WorkKey] = []
        for key in expired:
            if ground_truth is not None and not ground_truth(key):
                # ground truth says the PR is gone / already resolved — drop it.
                self._db.execute(
                    "UPDATE work_items SET state=?, lease_owner=NULL, lease_expiry=NULL, "
                    "superseded=1, updated_at=? "
                    "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
                    (State.DROPPED.value, now, *key.as_tuple()),
                )
                continue
            self._db.execute(
                "UPDATE work_items SET lease_owner=NULL, lease_expiry=NULL, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
                (now, *key.as_tuple()),
            )
            reclaimed.append(key)
        return reclaimed

    def snapshot(self) -> list[dict]:
        """Return all work-item rows (observability / test assertions)."""
        cur = self._db.execute("SELECT * FROM work_items ORDER BY created_at, pr_number")
        return [dict(r) for r in cur]


# ─────────────────────── stubbed sandbox executor ───────────────────────


@dataclass(frozen=True)
class FixResult:
    """Bounded output a real sandbox would export (patch + evidence)."""

    patch: str
    evidence: str


class ExecutorCancelled(RuntimeError):
    """Raised by a cooperative executor that acknowledged a cancellation."""


class CancellationToken:
    """One-shot cancellation signal handed to an in-flight executor (design
    §6.3 / §5.2).

    A supersede on a newer head calls :meth:`cancel`; the executor cooperatively
    polls :attr:`cancelled` (or calls :meth:`raise_if_cancelled` at checkpoints)
    and, when cancelled, :meth:`acknowledge`\\ s and aborts. The poller keeps the
    PR-level lease until the executor has acknowledged, so an old run can never
    quietly keep computing/pushing against a head that has moved on.
    """

    def __init__(self) -> None:
        self._cancelled = False
        self._acknowledged = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def acknowledge(self) -> None:
        self._acknowledged = True

    @property
    def acknowledged(self) -> bool:
        return self._acknowledged

    def raise_if_cancelled(self) -> None:
        """Cooperative checkpoint: acknowledge + abort if cancellation was
        requested. A well-behaved executor calls this before exporting output."""
        if self._cancelled:
            self._acknowledged = True
            raise ExecutorCancelled("executor acknowledged cancellation")


class SandboxExecutor(Protocol):
    """Interface for the ephemeral fix executor (design §5.2/§7.5).

    A real implementation runs the fix agent + PR-controlled tests inside an
    ephemeral OS/container/VM sandbox (only the disposable checkout mounted,
    no host home/creds/live tree, default-deny egress) and returns ONLY a
    bounded patch + test evidence. The poller — outside the sandbox — then
    validates paths, revalidates the head SHA, fences the output by lease
    generation + current head, and pushes. NONE of that is implemented in this
    PR. The ``cancel_token`` lets a supersede on a newer head abort a stale run.
    """

    def run_fix_in_sandbox(
        self,
        *,
        repo: str,
        pr_number: int,
        head_sha: str,
        review_comments: Sequence[str],
        cancel_token: Optional[CancellationToken] = None,
    ) -> FixResult: ...


class StubSandboxExecutor:
    """Fail-closed stub. Executing untrusted PR code is an explicit follow-up.

    Raises ``NotImplementedError`` so nothing untrusted ever runs from this
    control-plane PR. The poller catches this and ESCALATES (never merges,
    never pushes).
    """

    def run_fix_in_sandbox(
        self,
        *,
        repo: str,
        pr_number: int,
        head_sha: str,
        review_comments: Sequence[str],
        cancel_token: Optional[CancellationToken] = None,
    ) -> FixResult:
        raise NotImplementedError("ephemeral sandbox executor — follow-up PR")


# ─────────────────────── hard termination mechanism ─────────────────────


class TerminationHook(Protocol):
    """Hard, out-of-band teardown of a run that ignored cooperative cancel
    (design §6.3 / review point 4).

    A durable ``cancel_requested`` flag alone CANNOT stop untrusted work — a
    hung or malicious executor may never poll it. So a real deployment must own
    a hard kill (terminate the sandbox container/VM, revoke its lease + creds)
    for any run whose retained lease expired without acknowledging. This
    interface is that mechanism's seam; the poller hands it every uncooperative
    run found at startup (see :meth:`AutomationPoller.startup_recover`).
    """

    def terminate(self, key: "WorkKey") -> None: ...


class NoopTerminationHook:
    """Default hook: RECORD the kill requirement instead of pretending to kill.

    This control-plane PR wires no real executor, so there is no live process to
    tear down — but leaving the requirement implicit is exactly the overclaim
    the reviewer flagged. Recording each uncooperative key makes the unmet
    hard-termination obligation explicit and observable (and asserted in tests)
    rather than silently assumed satisfied by a SQLite flag.
    """

    def __init__(self) -> None:
        self.terminated: list["WorkKey"] = []

    def terminate(self, key: "WorkKey") -> None:
        self.terminated.append(key)


# ───────────────────────────── poller config ────────────────────────────


@dataclass(frozen=True)
class PollerConfig:
    """Config-driven allowlists + safety knobs (design §7.2/§8)."""

    tracked_repos: tuple[str, ...] = ()
    #: optional per-repo PR-number allowlist; a repo absent here (but present
    #: in ``tracked_repos``) tracks all of its PRs.
    tracked_prs: dict[str, tuple[int, ...]] = field(default_factory=dict)
    lease_ttl_seconds: float = 900.0
    max_rounds_per_pr: int = 3
    dry_run: bool = False
    owner: str = "poller-1"

    def is_tracked(self, repo: str, pr_number: int) -> bool:
        if repo not in self.tracked_repos:
            return False
        allowed = self.tracked_prs.get(repo)
        return allowed is None or pr_number in allowed

    @classmethod
    def from_dict(cls, data: dict) -> "PollerConfig":
        prs_raw = data.get("tracked_prs") or {}
        tracked_prs = {repo: tuple(nums) for repo, nums in prs_raw.items()}
        return cls(
            tracked_repos=tuple(data.get("tracked_repos") or ()),
            tracked_prs=tracked_prs,
            lease_ttl_seconds=float(data.get("lease_ttl_seconds", 900.0)),
            max_rounds_per_pr=int(data.get("max_rounds_per_pr", 3)),
            dry_run=bool(data.get("dry_run", False)),
            owner=str(data.get("owner", "poller-1")),
        )

    @classmethod
    def from_json_file(cls, path: str) -> "PollerConfig":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


# ───────────────────────────── the poller ───────────────────────────────


@dataclass(frozen=True)
class Action:
    """A single deterministic decision the poller made (observability)."""

    event_id: str
    repo: str
    pr_number: int
    outcome: str  # e.g. "ignored_untracked", "duplicate", "escalated", "fixing_dry_run"
    detail: str = ""


class AutomationPoller:
    """The deterministic control-plane loop (design §5/§6).

    Ingests read-only review/comment events, drives legal state transitions
    through the atomic store, and hands the ``FIXING`` hop to the sandbox
    executor — which is stubbed here, so a fix attempt ESCALATES rather than
    running any untrusted code. Performs NO push and NO merge.
    """

    def __init__(
        self,
        config: PollerConfig,
        store: StateStore,
        *,
        executor: Optional[SandboxExecutor] = None,
        termination_hook: Optional[TerminationHook] = None,
    ):
        self.config = config
        self.store = store
        self.executor: SandboxExecutor = executor or StubSandboxExecutor()
        #: hard-termination seam (review point 4). Handed every uncooperative
        #: run at startup — one whose cancellation was durably requested but
        #: whose retained lease expired without acknowledgement. The default
        #: hook RECORDS the unmet kill obligation instead of pretending a SQLite
        #: flag stopped untrusted work.
        self.termination_hook: TerminationHook = termination_hook or NoopTerminationHook()
        #: in-flight cancellation tokens keyed by work item (design §6.3). A
        #: supersede on a newer head cancels the matching token so a threaded /
        #: async executor for the stale head is told to stop. This is the
        #: in-memory FAST signal; the DURABLE ``cancel_requested`` flag (set by
        #: :meth:`StateStore.supersede_stale`) is the cross-restart source of
        #: truth the executor also polls.
        self._inflight: dict[WorkKey, CancellationToken] = {}

    # ── ingestion ──────────────────────────────────────────────────────────

    @staticmethod
    def _result_json(action: Action) -> str:
        """Compact record of an event's terminal action, persisted WITH the
        applied marker (review point 3) so a true duplicate is answered from the
        ledger and the recorded decision is returned, not re-driven."""
        return json.dumps({"outcome": action.outcome, "detail": action.detail})

    def ingest(self, event: Event) -> Action:
        """Ingest one event and drive its transition (deterministic, exactly-once).

        Order (design §6.3, review point 3): allowlist filter → EXCLUSIVE claim
        (owner + processing lease) → resume-idempotent drive. The claim is the
        first half of exactly-once: a concurrent delivery held by a DIFFERENT
        owner is refused (``in_progress``) rather than double-driven, and an
        already-``applied`` id is a true duplicate. The second half is that
        every FINAL transition is FOLDED with the applied marker
        (:meth:`StateStore.transition_and_apply`) — so a crash can never leave
        the row moved but the event un-applied, and redelivery either re-drives
        cleanly from the CURRENT durable state or is a genuine duplicate.
        """
        if not self.config.is_tracked(event.repo, event.pr_number):
            return Action(event.event_id, event.repo, event.pr_number,
                          "ignored_untracked", "repo/PR not on allowlist")

        claim = self.store.claim_event(
            event, self.config.owner, self.config.lease_ttl_seconds
        )
        if not claim.proceed:
            if claim.disposition == "applied":
                detail = "event id already applied"
                recorded = self._recorded_outcome(claim.result_json)
                if recorded:
                    detail += f" (recorded outcome: {recorded})"
                return Action(event.event_id, event.repo, event.pr_number,
                              "duplicate", detail)
            # a DIFFERENT owner holds a live processing lease — do NOT double
            # drive; it will be redelivered and reclaimed after that lease ends.
            return Action(event.event_id, event.repo, event.pr_number,
                          "in_progress", "another owner holds the processing claim")

        return self._process_claimed(event)

    @staticmethod
    def _recorded_outcome(result_json: Optional[str]) -> str:
        if not result_json:
            return ""
        try:
            return str(json.loads(result_json).get("outcome", ""))
        except (ValueError, TypeError):
            return ""

    def _apply(self, event: Event, action: Action) -> Action:
        """Mark ``event`` applied (recording ``action``) for a path that did NOT
        fold the marker into a durable transition — the no-mutation / already-
        terminal / idempotent cases. Folded transitions use
        :meth:`StateStore.transition_and_apply` and never reach here."""
        self.store.mark_event_applied(event.event_id, self._result_json(action))
        return action

    def _process_claimed(self, event: Event) -> Action:
        """Drive a claimed event through the state machine (crash-safe, resume-
        idempotent). Anything that raises here propagates WITHOUT marking the
        event applied, so redelivery re-drives it from the CURRENT durable state
        — never a double round-increment or an illegal repeat transition.
        """
        # A newer head supersedes any in-flight run on an older head; signal
        # cancellation via the in-memory token AND the durable cancel_requested
        # flag (set inside supersede_stale) to any executor still on the stale
        # head.
        superseded_keys = self.store.supersede_stale(
            event.repo, event.pr_number, event.head_sha
        )
        for stale_key in superseded_keys:
            token = self._inflight.get(stale_key)
            if token is not None:
                token.cancel()

        key = event.row_key
        self.store.ensure_row(key, State.AWAIT_REVIEW)

        current = self.store.get_state(key)
        # ── resume idempotently from the CURRENT durable state ──────────────
        if current in TERMINAL_STATES:
            return self._apply(event, Action(
                event.event_id, event.repo, event.pr_number,
                "terminal", f"work item already {current.value}"))
        if current is State.MERGE_ELIGIBLE:
            # a re-driven approval whose fold committed the state — idempotently
            # re-affirm + apply (never crosses the human-gate wall).
            return self._apply(event, Action(
                event.event_id, event.repo, event.pr_number,
                "merge_eligible", "already merge-eligible (idempotent)"))
        if current is State.FIXING:
            # a prior attempt committed the FIXING hop (round counter already
            # bumped) then crashed before finishing — RESUME the executor
            # WITHOUT a second begin_fix_round, so the counter is never inflated.
            return self._resume_fix(event, key)

        state = (event.state or "").upper()
        if event.kind == "review" and state == "APPROVED":
            return self._drive_merge_eligible(event, key)
        if event.kind == "review" and state == "CHANGES_REQUESTED":
            return self._drive_fixing(event, key)
        if event.kind == "comment":
            return self._drive_fixing(event, key)
        return self._apply(event, Action(
            event.event_id, event.repo, event.pr_number,
            "await_review", f"tracked {event.kind} recorded"))

    def ingest_all(self, events: Iterable[Event]) -> list[Action]:
        return [self.ingest(e) for e in events]

    # ── transition drivers ─────────────────────────────────────────────────

    def _handle_lease_contention(self, event: Event, acq: AcquireResult) -> Action:
        """Handle a failed :meth:`StateStore.acquire` WITHOUT marking the event
        applied unless a durably-recorded EQUIVALENT transition actually
        completed (design §6.3, review follow-up: the exact-once path must
        never lose valid work under contention/crash).

        ``acq.reason`` distinguishes two very different situations:

        * ``"superseded: ..."`` — THIS row was cancelled because a NEWER head
          already landed (:meth:`StateStore.supersede_stale`). That newer
          head's own event is what drives the equivalent (superseding) work
          going forward, under a DIFFERENT, non-superseded row; this row can
          never be un-superseded, so redelivering this event will hit the same
          "superseded" reason forever. It is therefore both safe AND correct
          to mark it applied now — the alternative (never applying it) would
          make it a permanent no-op that is reprocessed on every redelivery
          for nothing.
        * ``"coalesced: ..."`` (a live PR-level lease held by another,
          possibly still-in-flight run) or ``"lease already held"`` (an
          exact-key CAS race) — the current holder may be doing DIFFERENT
          work for a DIFFERENT event, or may crash before ever driving THIS
          event's intended transition. Marking this event applied here would
          silently and PERMANENTLY drop the work (the bug this fixes: the
          coalesced/in-progress outcome is not itself proof that an
          equivalent transition happened). So the event is left un-applied —
          it stays ``processing`` in the idempotency ledger (never
          ``duplicate`` on redelivery) and the row keeps ``pending_rerun=1``
          — so a LATER worker re-examines it: either the same owner's next
          poll tick (an immediate reclaim, see :meth:`StateStore.
          claim_event`), or, after the blocking holder crashes, once
          :meth:`StateStore.reconcile_expired_leases` (driven from
          :meth:`startup_recover`) clears its dangling lease so the retry's
          ``acquire`` can finally succeed.
        """
        if acq.reason.startswith("superseded"):
            return self._apply(event, Action(
                event.event_id, event.repo, event.pr_number, "superseded", acq.reason))
        return Action(event.event_id, event.repo, event.pr_number, "coalesced", acq.reason)

    def _drive_merge_eligible(self, event: Event, key: WorkKey) -> Action:
        """APPROVED at head → MERGE_ELIGIBLE. The poller STOPS here.

        Crossing the human-gate wall (to MERGED or HUMAN_GATE) is the separate
        MERGE_AUTHORITY's job, never the poller's. The transition is FOLDED with
        the event's applied marker so approval is exactly-once across a crash.
        """
        acq = self.store.acquire(key, self.config.owner, self.config.lease_ttl_seconds)
        if not acq.acquired:
            return self._handle_lease_contention(event, acq)
        action = Action(event.event_id, event.repo, event.pr_number,
                        "merge_eligible",
                        "approved at head; poller authority ends at the human-gate wall")
        try:
            self.store.transition_and_apply(
                key, State.MERGE_ELIGIBLE, actor=Actor.POLLER,
                event_id=event.event_id, result_json=self._result_json(action),
                owner=self.config.owner, fence=acq.fence,
            )
        finally:
            self.store.release(key, self.config.owner, fence=acq.fence)
        return action

    def _drive_fixing(self, event: Event, key: WorkKey) -> Action:
        """CHANGES_REQUESTED / comment → attempt a fix (stubbed → ESCALATE)."""
        acq = self.store.acquire(key, self.config.owner, self.config.lease_ttl_seconds)
        if not acq.acquired:
            return self._handle_lease_contention(event, acq)
        fence = acq.fence
        try:
            if self.config.dry_run:
                # A dry-run must NOT mutate durable workflow state: no round
                # bump, no FIXING transition. Otherwise the row would be wedged
                # in FIXING and a later CHANGES_REQUESTED event would attempt an
                # illegal FIXING → FIXING. Record intent only; row stays at
                # AWAIT_REVIEW.
                return self._apply(event, Action(
                    event.event_id, event.repo, event.pr_number,
                    "fixing_dry_run", "would invoke sandbox executor (dry-run)"))

            # Atomically bump the round counter AND make the FIXING/ESCALATED
            # decision (design §8.1, review point 3) in ONE transaction — a
            # crash can never inflate the counter without the matching
            # transition, so a resumed redelivery (which finds the row already
            # FIXING) never bumps twice.
            decision, _attempt = self.store.begin_fix_round(
                key, owner=self.config.owner, fence=fence,
                max_rounds=self.config.max_rounds_per_pr,
            )
            if decision == "escalated":
                # begin_fix_round already committed the ESCALATED (terminal)
                # transition; mark the event applied. A crash before this marker
                # re-drives into the terminal short-circuit (idempotent):
                # ESCALATED cannot be re-entered, so the counter stays put.
                return self._apply(event, Action(
                    event.event_id, event.repo, event.pr_number,
                    "escalated", f"round cap {self.config.max_rounds_per_pr} reached"))
            # decision == "fixing": row is now at FIXING, counter bumped once.
            return self._execute_fix(event, key, fence)
        finally:
            self.store.release(key, self.config.owner, fence=fence)

    def _resume_fix(self, event: Event, key: WorkKey) -> Action:
        """Resume a crashed fix that already committed the FIXING hop.

        Re-acquires the lease (the crashed attempt's was released/expired) but
        does NOT call :meth:`StateStore.begin_fix_round`, so the round counter is
        never bumped a second time. This is the resume-idempotent handler the
        reviewer asked for at the state-transition boundary.
        """
        acq = self.store.acquire(key, self.config.owner, self.config.lease_ttl_seconds)
        if not acq.acquired:
            return self._handle_lease_contention(event, acq)
        try:
            return self._execute_fix(event, key, acq.fence)
        finally:
            self.store.release(key, self.config.owner, fence=acq.fence)

    def _execute_fix(self, event: Event, key: WorkKey, fence: int) -> Action:
        """Run the (stubbed) executor for a row already at FIXING under a lease
        the CALLER holds at ``fence``, and drive its terminal transition FOLDED
        with the applied marker. The caller owns acquire + release.
        """
        token = CancellationToken()
        self._inflight[key] = token
        try:
            self.executor.run_fix_in_sandbox(
                repo=event.repo,
                pr_number=event.pr_number,
                head_sha=event.head_sha,
                review_comments=[event.body],
                cancel_token=token,
            )
        except ExecutorCancelled:
            # The run acknowledged cancellation: drop the retained PR-level
            # lease and stop. Its output (if any) is fenced anyway.
            self.store.acknowledge_cancellation(key)
            return self._apply(event, Action(
                event.event_id, event.repo, event.pr_number,
                "cancelled", "executor acknowledged supersede cancellation"))
        except NotImplementedError as exc:
            # Stubbed sandbox → ESCALATE, folded with the applied marker.
            action = Action(event.event_id, event.repo, event.pr_number,
                            "escalated", f"sandbox stubbed: {exc}")
            self.store.transition_and_apply(
                key, State.ESCALATED, actor=Actor.POLLER,
                event_id=event.event_id, result_json=self._result_json(action),
                owner=self.config.owner, fence=fence,
            )
            return action
        finally:
            self._inflight.pop(key, None)

        # FENCE the exported patch by lease generation + current head SHA
        # (design §6.3): if the head advanced / the row was superseded / the
        # lease was reclaimed while the executor ran, DISCARD the patch — it must
        # never be applied or pushed against a moved-on PR. The row stays at
        # FIXING (still superseded) and is swept by reconcile.
        if not self.store.fence_ok(key, fence, event.head_sha):
            return self._apply(event, Action(
                event.event_id, event.repo, event.pr_number,
                "fenced_stale",
                "patch discarded: head advanced / superseded / lease reclaimed"))
        # A real executor path is intentionally unreachable in this PR.
        action = Action(event.event_id, event.repo, event.pr_number,
                        "fixed", "patch produced; awaiting re-review")
        self.store.transition_and_apply(
            key, State.AWAIT_REVIEW, actor=Actor.POLLER,
            event_id=event.event_id, result_json=self._result_json(action),
            owner=self.config.owner, fence=fence,
        )
        return action

    def startup_recover(
        self, *, ground_truth: Optional[Callable[[WorkKey], bool]] = None
    ) -> list[WorkKey]:
        """Crash-recovery sweep to run on poller start (design §6.3, review
        point 4).

        BEFORE reclaiming leases, hand every UNCOOPERATIVE cancellation — a run
        whose cancellation was durably requested but whose retained lease
        expired without acknowledgement — to the hard :class:`TerminationHook`.
        A retained SQLite flag alone cannot stop untrusted work; the kill is a
        DISTINCT, explicit mechanism. Then reconcile expired leases.
        """
        for key in self.store.list_uncooperative_cancellations():
            self.termination_hook.terminate(key)
        return self.store.reconcile_expired_leases(ground_truth=ground_truth)


# ───────────────────────── offline replay harness ───────────────────────
#
# A deterministic, network-free replay of a recorded event sequence through
# the filter → state machine → lock (design §9 Phase-0 shadow/replay). This is
# the safe way to exercise the control plane and the ``--dry-run`` mode with no
# GitHub writes. Live GitHub polling is intentionally not wired in this PR.


def event_from_dict(data: dict) -> Event:
    return Event(
        event_id=str(data["event_id"]),
        repo=str(data["repo"]),
        pr_number=int(data["pr_number"]),
        head_sha=str(data["head_sha"]),
        kind=str(data.get("kind", "review")),
        state=data.get("state"),
        review_id=str(data.get("review_id", "")),
        body=str(data.get("body", "")),
    )


def load_events_file(path: str) -> list[Event]:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload.get("events", payload) if isinstance(payload, dict) else payload
    return [event_from_dict(row) for row in rows]


def run_replay(
    config: PollerConfig,
    events: Sequence[Event],
    *,
    db_path: str = ":memory:",
) -> dict:
    """Replay ``events`` through a fresh poller; return a JSON-ready summary."""
    store = StateStore(db_path)
    try:
        poller = AutomationPoller(config, store)
        actions = poller.ingest_all(events)
        rows = store.snapshot()
    finally:
        store.close()
    return {
        "dry_run": config.dry_run,
        "tracked_repos": list(config.tracked_repos),
        "max_rounds_per_pr": config.max_rounds_per_pr,
        "human_gate_wall_ok": merged_is_wall_protected(),
        "n_events": len(events),
        "actions": [
            {
                "event_id": a.event_id,
                "repo": a.repo,
                "pr_number": a.pr_number,
                "outcome": a.outcome,
                "detail": a.detail,
            }
            for a in actions
        ],
        "work_items": [
            {
                "repo": r["repo"],
                "pr_number": r["pr_number"],
                "head_sha": r["head_sha"],
                "review_id": r["review_id"],
                "state": r["state"],
                "attempt": r["attempt"],
                "superseded": bool(r["superseded"]),
                "pending_rerun": bool(r["pending_rerun"]),
            }
            for r in rows
        ],
    }


def run_cli(
    *,
    config_path: str,
    events_path: Optional[str] = None,
    db_path: str = ":memory:",
    dry_run: bool = False,
) -> dict:
    """Entry point used by the ``agent-automation`` CLI command."""
    config = PollerConfig.from_json_file(config_path)
    if dry_run and not config.dry_run:
        config = replace(config, dry_run=True)
    if events_path is None:
        # No replay corpus: just validate config + report the allowlist/wall.
        return {
            "dry_run": config.dry_run,
            "tracked_repos": list(config.tracked_repos),
            "tracked_prs": {k: list(v) for k, v in config.tracked_prs.items()},
            "max_rounds_per_pr": config.max_rounds_per_pr,
            "human_gate_wall_ok": merged_is_wall_protected(),
            "n_events": 0,
            "actions": [],
            "work_items": [],
        }
    return run_replay(config, load_events_file(events_path), db_path=db_path)
