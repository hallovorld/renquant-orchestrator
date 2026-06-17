"""Tests for roadmap_driver (#108 automation)."""
from __future__ import annotations

import json

import pytest

from renquant_orchestrator.roadmap_driver import (
    RoadmapItem,
    build_implementation_prompt,
    blocked_items,
    load_backlog,
    mark,
    next_item,
    save_backlog,
    status_table,
)


def _items() -> list[RoadmapItem]:
    return [
        RoadmapItem("a", "A", "cat", "repo", "do A"),
        RoadmapItem("b", "B", "cat", "repo", "do B", blocked_by=["a"]),
        RoadmapItem("c", "C", "cat", "repo", "do C", consequential=True),
        RoadmapItem("d", "D", "cat", "repo", "do D"),
    ]


def test_next_item_returns_first_pending_nonconsequential_unblocked():
    assert next_item(_items()).id == "a"


def test_next_item_skips_consequential():
    items = _items()
    mark(items, "a", "done")
    # b unblocked now (a done); c is consequential -> skipped; b is next
    assert next_item(items).id == "b"


def test_next_item_respects_blocked_by():
    items = _items()
    # a still pending -> b (blocked_by a) must NOT be returned before a
    nxt = next_item(items)
    assert nxt.id == "a"  # not b


def test_blocked_until_blocker_done():
    items = _items()
    assert "b" in {i.id for i in blocked_items(items)}
    mark(items, "a", "done")
    mark(items, "d", "done")
    assert blocked_items(items) == []
    assert next_item(items).id == "b"


def test_consequential_pickable_only_when_allowed():
    items = [RoadmapItem("c", "C", "cat", "repo", "do C", consequential=True)]
    assert next_item(items) is None
    assert next_item(items, allow_consequential=True).id == "c"


def test_next_item_none_when_all_done_or_blocked():
    items = [RoadmapItem("a", "A", "c", "r", "x", status="done"),
             RoadmapItem("c", "C", "c", "r", "x", consequential=True)]
    assert next_item(items) is None


def test_prompt_has_guardrails():
    p = build_implementation_prompt(_items()[0])
    assert "do A" in p
    assert "Do NOT merge" in p
    assert "consequential" in p


def test_round_trip(tmp_path):
    items = _items()
    mark(items, "a", "done")
    p = tmp_path / "backlog.json"
    save_backlog(p, items)
    again = load_backlog(p)
    assert [i.id for i in again] == ["a", "b", "c", "d"]
    assert next(i for i in again if i.id == "a").status == "done"


def test_load_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"items": [
        {"id": "x", "title": "t", "category": "c", "repo": "r", "prompt": "p"},
        {"id": "x", "title": "t2", "category": "c", "repo": "r", "prompt": "p"},
    ]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_backlog(p)


def test_load_rejects_unknown_blocker(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"items": [
        {"id": "x", "title": "t", "category": "c", "repo": "r", "prompt": "p",
         "blocked_by": ["nope"]},
    ]}))
    with pytest.raises(ValueError, match="unknown id"):
        load_backlog(p)


def test_invalid_status_rejected():
    with pytest.raises(ValueError, match="invalid status"):
        RoadmapItem("x", "t", "c", "r", "p", status="bogus")


def test_status_table_renders():
    t = status_table(_items())
    assert "roadmap backlog: 4 items" in t
    assert "[consequential]" in t


def test_seeded_backlog_is_valid():
    """The shipped doc/roadmap-backlog.json must load + have an actionable item."""
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    items = load_backlog(repo / "doc" / "roadmap-backlog.json")
    assert len(items) >= 5
    assert next_item(items) is not None  # at least one auto-actionable item
