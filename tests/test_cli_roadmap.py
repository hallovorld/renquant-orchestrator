"""CLI smoke tests for the `roadmap` subcommand (the loop's implement interface)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import cli


def _backlog(tmp_path):
    p = tmp_path / "backlog.json"
    p.write_text(json.dumps({
        "_note": "keep me",
        "items": [
            {"id": "a", "title": "A", "category": "c", "repo": "r", "prompt": "do A"},
            {"id": "c", "title": "C", "category": "c", "repo": "r", "prompt": "do C",
             "consequential": True},
        ],
    }))
    return str(p)


def test_roadmap_status(tmp_path, capsys):
    rc = cli.main(["roadmap", "status", "--backlog", _backlog(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "roadmap backlog: 2 items" in out
    assert "[consequential]" in out


def test_roadmap_next_emits_task(tmp_path, capsys):
    rc = cli.main(["roadmap", "next", "--backlog", _backlog(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Implement roadmap item `a`" in out
    assert "Do NOT merge" in out


def test_roadmap_next_skips_consequential_returns_1_when_none(tmp_path, capsys):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"items": [
        {"id": "c", "title": "C", "category": "c", "repo": "r", "prompt": "x",
         "consequential": True}]}))
    rc = cli.main(["roadmap", "next", "--backlog", str(p)])
    assert rc == 1
    assert "no actionable roadmap item" in capsys.readouterr().out


def test_roadmap_mark_persists(tmp_path, capsys):
    bp = _backlog(tmp_path)
    rc = cli.main(["roadmap", "mark", "a", "done", "--backlog", bp])
    assert rc == 0
    saved = json.loads(Path(bp).read_text())
    assert saved["_note"] == "keep me"
    assert saved["items"][0]["status"] == "done"
    # next now skips 'a' (done) and 'c' (consequential) -> none actionable
    assert cli.main(["roadmap", "next", "--backlog", bp]) == 1
