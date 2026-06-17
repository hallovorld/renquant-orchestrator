"""Roadmap implementation driver (#108 automation).

The agent-pr-loop already does **review → fix → merge** on existing PRs. What was
missing is the **implement** half: something that reads the roadmap, picks the
next item, and dispatches an agent to build it + open a PR — which the loop then
reviews and merges. This closes the loop so the feature-map self-drives instead
of needing a human to prompt each item.

Backlog: a structured JSON list (seeded from `doc/renquant-system-feature-map.md`)
of items with id / title / category / repo / prompt / status / blocked_by /
consequential.

Guardrails (baked into selection):
  * items flagged ``consequential`` (live deploy, GPU retrain, anything
    outward-facing / hard to reverse) are NEVER auto-picked — they stay for the
    operator;
  * an item is only actionable when every ``blocked_by`` id is ``done``;
  * the emitted prompt tells the agent to open a PR and NEVER merge — the
    existing merge gate owns merging.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUSES = ("pending", "in_progress", "done", "blocked")


@dataclass
class RoadmapItem:
    id: str
    title: str
    category: str
    repo: str
    prompt: str
    status: str = "pending"
    blocked_by: list[str] = field(default_factory=list)
    consequential: bool = False

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid status {self.status!r} for {self.id}")


def load_backlog(path: str | Path) -> list[RoadmapItem]:
    data = json.loads(Path(path).read_text())
    items = [RoadmapItem(**it) for it in data["items"]]
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate roadmap item id(s)")
    known = set(ids)
    for it in items:
        unknown = [b for b in it.blocked_by if b not in known]
        if unknown:
            raise ValueError(f"{it.id} blocked_by unknown id(s): {unknown}")
    return items


def save_backlog(path: str | Path, items: list[RoadmapItem]) -> None:
    path = Path(path)
    data = json.loads(path.read_text()) if path.exists() else {}
    data["items"] = [asdict(i) for i in items]
    path.write_text(json.dumps(data, indent=2) + "\n")


def _done_ids(items: list[RoadmapItem]) -> set[str]:
    return {i.id for i in items if i.status == "done"}


def next_item(items: list[RoadmapItem], *,
              allow_consequential: bool = False) -> RoadmapItem | None:
    """First actionable item: pending, all blockers done, not consequential
    (unless explicitly allowed). Returns None when nothing is actionable."""
    done = _done_ids(items)
    for it in items:
        if it.status != "pending":
            continue
        if it.consequential and not allow_consequential:
            continue
        if any(b not in done for b in it.blocked_by):
            continue
        return it
    return None


def blocked_items(items: list[RoadmapItem]) -> list[RoadmapItem]:
    """Pending items held back only by unfinished blockers (not consequential)."""
    done = _done_ids(items)
    return [it for it in items
            if it.status == "pending" and not it.consequential
            and any(b not in done for b in it.blocked_by)]


def mark(items: list[RoadmapItem], item_id: str, status: str) -> list[RoadmapItem]:
    if status not in STATUSES:
        raise ValueError(f"invalid status {status!r}")
    if not any(i.id == item_id for i in items):
        raise KeyError(f"unknown roadmap item id: {item_id}")
    for it in items:
        if it.id == item_id:
            it.status = status
    return items


def build_implementation_prompt(item: RoadmapItem) -> str:
    """The agent task text for one item. Self-contained so the agent-pr-loop can
    feed it straight to codex/claude."""
    return (
        f"Implement roadmap item `{item.id}` — {item.title}\n"
        f"Category: {item.category}. Target repo: {item.repo}.\n\n"
        f"Task:\n{item.prompt}\n\n"
        "Rules:\n"
        "- Branch off origin/main; write the code AND focused tests; run the tests.\n"
        "- Open a pull request. Do NOT merge anything — the merge gate owns merging.\n"
        "- Keep the change focused and reviewable; honor existing decisions/contracts.\n"
        "- If the item turns out to be consequential (touches live state, deploys to\n"
        "  the live account, burns significant GPU, or is hard to reverse), STOP and\n"
        "  flag the operator instead of proceeding.\n"
    )


def status_table(items: list[RoadmapItem]) -> str:
    by_status: dict[str, int] = {}
    for it in items:
        by_status[it.status] = by_status.get(it.status, 0) + 1
    lines = [f"roadmap backlog: {len(items)} items "
             + " ".join(f"{k}={v}" for k, v in sorted(by_status.items())), ""]
    for it in items:
        flag = " [consequential]" if it.consequential else ""
        blk = f" blocked_by={it.blocked_by}" if it.blocked_by else ""
        lines.append(f"  [{it.status:11}] {it.id} — {it.title}{flag}{blk}")
    return "\n".join(lines)
