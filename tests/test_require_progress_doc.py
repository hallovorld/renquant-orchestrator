"""Unit tests for the require-progress-doc CI matcher."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "require_progress_doc.py"
_spec = importlib.util.spec_from_file_location("reqdoc", _SCRIPT)
reqdoc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reqdoc)


def test_present_passes():
    assert reqdoc.has_progress_doc(["src/x.py", "doc/progress/2026-06-23-foo-bar.md"])


def test_absent_fails():
    assert not reqdoc.has_progress_doc(["src/x.py", "README.md", "tests/test_x.py"])


def test_research_doc_is_not_a_progress_doc():
    assert not reqdoc.has_progress_doc(["doc/research/2026-06-23-foo.md"])


def test_progress_doc_without_date_fails():
    assert not reqdoc.has_progress_doc(["doc/progress/foo.md"])


def test_only_a_progress_doc_passes():
    # a docs-only PR that just adds the record is fine
    assert reqdoc.has_progress_doc(["doc/progress/2026-06-23-x.md"])


def test_blank_lines_ignored():
    assert not reqdoc.has_progress_doc(["", "  ", "src/x.py"])
