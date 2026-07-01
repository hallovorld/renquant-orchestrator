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
from contextlib import closing
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Iterable, Optional, Protocol, Sequence

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
class AcquireResult:
    acquired: bool
    reason: str = ""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_items (
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
CREATE TABLE IF NOT EXISTS processed_events (
    event_id     TEXT PRIMARY KEY,
    repo         TEXT NOT NULL,
    pr_number    INTEGER NOT NULL,
    head_sha     TEXT,
    processed_at REAL NOT NULL
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
        # check_same_thread=False so a test can simulate a second worker via a
        # second StateStore over the same file; SQLite serialises the writes.
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout = 5000")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # ── rows ──────────────────────────────────────────────────────────────

    def ensure_row(self, key: WorkKey, state: State) -> None:
        """Insert the work-item row at ``state`` if it does not yet exist."""
        now = self._clock()
        self._db.execute(
            "INSERT OR IGNORE INTO work_items "
            "(repo, pr_number, head_sha, review_id, state, attempt, superseded, "
            " pending_rerun, created_at, updated_at) "
            "VALUES (?,?,?,?,?,0,0,0,?,?)",
            (*key.as_tuple(), State(state).value, now, now),
        )
        self._db.commit()

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

    # ── event idempotency (§6.3) ───────────────────────────────────────────

    def record_event(self, event: Event) -> bool:
        """Record a delivery id. Return True if NEW, False if already seen.

        Atomic via ``INSERT OR IGNORE`` + ``changes()`` so a duplicate or
        out-of-order redelivery of the same ``event_id`` is dropped exactly
        once, even across connections.
        """
        with closing(self._db.cursor()) as cur:
            cur.execute(
                "INSERT OR IGNORE INTO processed_events "
                "(event_id, repo, pr_number, head_sha, processed_at) VALUES (?,?,?,?,?)",
                (event.event_id, event.repo, event.pr_number, event.head_sha, self._clock()),
            )
            self._db.commit()
            return cur.rowcount == 1

    def event_seen(self, event_id: str) -> bool:
        cur = self._db.execute(
            "SELECT 1 FROM processed_events WHERE event_id=?", (event_id,)
        )
        return cur.fetchone() is not None

    # ── lease acquire / release (§6.2) ─────────────────────────────────────

    def acquire(self, key: WorkKey, owner: str, ttl: float) -> AcquireResult:
        """Atomically acquire the lease on a work item (compare-and-set).

        Semantics (design §6.2):
          * two acquirers on the SAME key → exactly one wins (CAS on the row);
          * a second live lease on a DIFFERENT head/review of the SAME
            ``(repo, pr)`` → coalesce: flag ``pending_rerun`` and do not start
            a concurrent run;
          * an expired lease (crashed owner) is reclaimable.
        """
        self.ensure_row(key, State.AWAIT_REVIEW)
        now = self._clock()

        # PR-busy coalescing: another non-terminal, non-superseded row for the
        # same (repo, pr) holds a live lease on a different head/review.
        busy = self._db.execute(
            f"SELECT count(*) AS n FROM work_items "
            f"WHERE repo=? AND pr_number=? "
            f"AND NOT (head_sha=? AND review_id=?) "
            f"AND superseded=0 AND state NOT IN ({_TERMINAL_SQL}) "
            f"AND lease_owner IS NOT NULL AND lease_expiry > ?",
            (key.repo, key.pr_number, key.head_sha, key.review_id, now),
        ).fetchone()["n"]
        if busy:
            self._db.execute(
                "UPDATE work_items SET pending_rerun=1, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
                (now, *key.as_tuple()),
            )
            self._db.commit()
            return AcquireResult(False, "coalesced: another fix in-flight for this PR")

        with closing(self._db.cursor()) as cur:
            cur.execute(
                "UPDATE work_items SET lease_owner=?, lease_expiry=?, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? "
                "AND superseded=0 "
                "AND (lease_owner IS NULL OR lease_expiry <= ?)",
                (owner, now + ttl, now, *key.as_tuple(), now),
            )
            self._db.commit()
            if cur.rowcount == 1:
                return AcquireResult(True, "acquired")
            return AcquireResult(False, "lease already held")

    def holds_lease(self, key: WorkKey, owner: str) -> bool:
        row = self.get_row(key)
        if not row or row["lease_owner"] != owner:
            return False
        return (row["lease_expiry"] or 0) > self._clock()

    def release(self, key: WorkKey, owner: str) -> bool:
        with closing(self._db.cursor()) as cur:
            cur.execute(
                "UPDATE work_items SET lease_owner=NULL, lease_expiry=NULL, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? AND lease_owner=?",
                (self._clock(), *key.as_tuple(), owner),
            )
            self._db.commit()
            return cur.rowcount == 1

    # ── stale-run cancellation (§6.3) ──────────────────────────────────────

    def supersede_stale(self, repo: str, pr_number: int, current_head: str) -> list[WorkKey]:
        """Mark every non-terminal row for ``(repo, pr)`` on an OLD head as
        superseded when the head advances. Returns the superseded keys.

        Only the newest head can hold an active lease; a stale in-flight run is
        signalled superseded and drops its lease.
        """
        now = self._clock()
        cur = self._db.execute(
            f"SELECT repo, pr_number, head_sha, review_id FROM work_items "
            f"WHERE repo=? AND pr_number=? AND head_sha != ? "
            f"AND superseded=0 AND state NOT IN ({_TERMINAL_SQL})",
            (repo, pr_number, current_head),
        )
        stale = [WorkKey(r["repo"], r["pr_number"], r["head_sha"], r["review_id"]) for r in cur]
        if stale:
            self._db.execute(
                f"UPDATE work_items SET superseded=1, lease_owner=NULL, lease_expiry=NULL, "
                f"updated_at=? WHERE repo=? AND pr_number=? AND head_sha != ? "
                f"AND superseded=0 AND state NOT IN ({_TERMINAL_SQL})",
                (now, repo, pr_number, current_head),
            )
            self._db.commit()
        return stale

    def is_superseded(self, key: WorkKey) -> bool:
        row = self.get_row(key)
        return bool(row and row["superseded"])

    # ── transitions (§6.3, single owner) ───────────────────────────────────

    def transition(
        self,
        key: WorkKey,
        to: State,
        *,
        actor: Actor,
        owner: Optional[str] = None,
        require_lease: bool = True,
    ) -> State:
        """Atomically move a work item to ``to`` under a single writer.

        Enforces the legal transition graph AND actor authorisation (the
        human-gate wall lives here). For ``POLLER`` transitions the caller
        must hold the lease (single writer), unless ``require_lease=False``.
        """
        row = self.get_row(key)
        if row is None:
            raise IllegalTransition(f"no work item for {key.as_tuple()}")
        if row["superseded"]:
            raise IllegalTransition(f"work item {key.as_tuple()} is superseded")
        frm = State(row["state"])
        assert_transition(frm, to, actor)

        if require_lease and Actor(actor) is Actor.POLLER:
            if not self.holds_lease(key, owner or ""):
                raise IllegalTransition(
                    f"poller must hold the lease to transition {frm.value} → {to.value}"
                )

        now = self._clock()
        with closing(self._db.cursor()) as cur:
            cur.execute(
                "UPDATE work_items SET state=?, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=? AND state=?",
                (State(to).value, now, *key.as_tuple(), frm.value),
            )
            self._db.commit()
            if cur.rowcount != 1:
                raise IllegalTransition(
                    f"lost race transitioning {frm.value} → {to.value} for {key.as_tuple()}"
                )
        return State(to)

    def bump_attempt(self, key: WorkKey) -> int:
        now = self._clock()
        self._db.execute(
            "UPDATE work_items SET attempt=attempt+1, updated_at=? "
            "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
            (now, *key.as_tuple()),
        )
        self._db.commit()
        row = self.get_row(key)
        return int(row["attempt"]) if row else 0

    # ── crash recovery (§6.3) ──────────────────────────────────────────────

    def reconcile_expired_leases(
        self, *, ground_truth: Optional[Callable[[WorkKey], bool]] = None
    ) -> list[WorkKey]:
        """Sweep expired leases on poller start (crash recovery).

        For each row whose lease has expired without release, reconcile against
        ground truth (if provided — e.g. is the PR still open / did the push
        land?) BEFORE reclaiming; then clear the lease so exactly one recoverer
        may re-acquire. Never blindly re-runs. Returns the reclaimed keys.
        """
        now = self._clock()
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
                self._db.commit()
                continue
            self._db.execute(
                "UPDATE work_items SET lease_owner=NULL, lease_expiry=NULL, updated_at=? "
                "WHERE repo=? AND pr_number=? AND head_sha=? AND review_id=?",
                (now, *key.as_tuple()),
            )
            self._db.commit()
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


class SandboxExecutor(Protocol):
    """Interface for the ephemeral fix executor (design §5.2/§7.5).

    A real implementation runs the fix agent + PR-controlled tests inside an
    ephemeral OS/container/VM sandbox (only the disposable checkout mounted,
    no host home/creds/live tree, default-deny egress) and returns ONLY a
    bounded patch + test evidence. The poller — outside the sandbox — then
    validates paths, revalidates the head SHA, and pushes. NONE of that is
    implemented in this PR.
    """

    def run_fix_in_sandbox(
        self, *, repo: str, pr_number: int, head_sha: str, review_comments: Sequence[str]
    ) -> FixResult: ...


class StubSandboxExecutor:
    """Fail-closed stub. Executing untrusted PR code is an explicit follow-up.

    Raises ``NotImplementedError`` so nothing untrusted ever runs from this
    control-plane PR. The poller catches this and ESCALATES (never merges,
    never pushes).
    """

    def run_fix_in_sandbox(
        self, *, repo: str, pr_number: int, head_sha: str, review_comments: Sequence[str]
    ) -> FixResult:
        raise NotImplementedError("ephemeral sandbox executor — follow-up PR")


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
    ):
        self.config = config
        self.store = store
        self.executor: SandboxExecutor = executor or StubSandboxExecutor()

    # ── ingestion ──────────────────────────────────────────────────────────

    def ingest(self, event: Event) -> Action:
        """Ingest one event and drive its resulting transition (deterministic).

        Order (design §6.3): allowlist filter → idempotency → stale-cancel →
        state-machine drive.
        """
        if not self.config.is_tracked(event.repo, event.pr_number):
            return Action(event.event_id, event.repo, event.pr_number,
                          "ignored_untracked", "repo/PR not on allowlist")

        if not self.store.record_event(event):
            return Action(event.event_id, event.repo, event.pr_number,
                          "duplicate", "event id already processed")

        # A newer head supersedes any in-flight run on an older head.
        self.store.supersede_stale(event.repo, event.pr_number, event.head_sha)

        key = event.row_key
        self.store.ensure_row(key, State.AWAIT_REVIEW)

        current = self.store.get_state(key)
        if current in TERMINAL_STATES:
            return Action(event.event_id, event.repo, event.pr_number,
                          "terminal", f"work item already {current.value}")

        state = event.state or ""
        if event.kind == "review" and state.upper() == "APPROVED":
            return self._drive_merge_eligible(event, key)
        if event.kind == "review" and state.upper() == "CHANGES_REQUESTED":
            return self._drive_fixing(event, key)
        if event.kind == "comment":
            return self._drive_fixing(event, key)
        return Action(event.event_id, event.repo, event.pr_number,
                      "await_review", f"tracked {event.kind} recorded")

    def ingest_all(self, events: Iterable[Event]) -> list[Action]:
        return [self.ingest(e) for e in events]

    # ── transition drivers ─────────────────────────────────────────────────

    def _drive_merge_eligible(self, event: Event, key: WorkKey) -> Action:
        """APPROVED at head → MERGE_ELIGIBLE. The poller STOPS here.

        Crossing the human-gate wall (to MERGED or HUMAN_GATE) is the separate
        MERGE_AUTHORITY's job, never the poller's.
        """
        if self.store.get_state(key) is State.MERGE_ELIGIBLE:
            return Action(event.event_id, event.repo, event.pr_number,
                          "merge_eligible", "already merge-eligible (idempotent)")
        acq = self.store.acquire(key, self.config.owner, self.config.lease_ttl_seconds)
        if not acq.acquired:
            return Action(event.event_id, event.repo, event.pr_number, "coalesced", acq.reason)
        try:
            self.store.transition(
                key, State.MERGE_ELIGIBLE, actor=Actor.POLLER, owner=self.config.owner
            )
        finally:
            self.store.release(key, self.config.owner)
        return Action(event.event_id, event.repo, event.pr_number,
                      "merge_eligible",
                      "approved at head; poller authority ends at the human-gate wall")

    def _drive_fixing(self, event: Event, key: WorkKey) -> Action:
        """CHANGES_REQUESTED / comment → attempt a fix (stubbed → ESCALATE)."""
        acq = self.store.acquire(key, self.config.owner, self.config.lease_ttl_seconds)
        if not acq.acquired:
            return Action(event.event_id, event.repo, event.pr_number, "coalesced", acq.reason)
        try:
            attempt = self.store.bump_attempt(key)
            # Design §8.1: escalate ON the Nth round (no silent round N+1) —
            # so the loop fixes on rounds 1..N-1 and escalates on round N.
            if attempt >= self.config.max_rounds_per_pr:
                self.store.transition(
                    key, State.ESCALATED, actor=Actor.POLLER, owner=self.config.owner
                )
                return Action(event.event_id, event.repo, event.pr_number,
                              "escalated", f"round cap {self.config.max_rounds_per_pr} reached")

            self.store.transition(
                key, State.FIXING, actor=Actor.POLLER, owner=self.config.owner
            )

            if self.config.dry_run:
                # Do not invoke the executor at all in dry-run; record intent.
                return Action(event.event_id, event.repo, event.pr_number,
                              "fixing_dry_run", "would invoke sandbox executor (dry-run)")

            try:
                self.executor.run_fix_in_sandbox(
                    repo=event.repo,
                    pr_number=event.pr_number,
                    head_sha=event.head_sha,
                    review_comments=[event.body],
                )
            except NotImplementedError as exc:
                self.store.transition(
                    key, State.ESCALATED, actor=Actor.POLLER, owner=self.config.owner
                )
                return Action(event.event_id, event.repo, event.pr_number,
                              "escalated", f"sandbox stubbed: {exc}")
            # A real executor path is intentionally unreachable in this PR.
            self.store.transition(
                key, State.AWAIT_REVIEW, actor=Actor.POLLER, owner=self.config.owner
            )
            return Action(event.event_id, event.repo, event.pr_number,
                          "fixed", "patch produced; awaiting re-review")
        finally:
            self.store.release(key, self.config.owner)

    def startup_recover(
        self, *, ground_truth: Optional[Callable[[WorkKey], bool]] = None
    ) -> list[WorkKey]:
        """Crash-recovery sweep to run on poller start (design §6.3)."""
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
