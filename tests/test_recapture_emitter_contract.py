"""The re-capture tool must fix POSITIONS and refuse everything else."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ops.renquant104.recapture_emitter_contract import recapture  # noqa: E402


def _fixture(tmp_path: Path, script_lines: list[str], rows: list[dict]):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "w.sh").write_text("\n".join(script_lines) + "\n")
    return {"lines": rows, "wrappers": {"scripts/w.sh": "0" * 16}}


def test_a_shifted_line_is_repinned_and_the_digest_refreshed(tmp_path):
    c = _fixture(tmp_path, ["#!/bin/bash", "", "", 'echo "=== DONE at $(date) ==="'],
                 [{"job": "j", "kind": "action",
                   "template": "=== DONE at $(date) ===",
                   "source": "scripts/w.sh:2"}])
    changed = recapture(c, tmp_path)
    assert c["lines"][0]["source"] == "scripts/w.sh:4"
    assert c["wrappers"]["scripts/w.sh"] != "0" * 16
    assert any("scripts/w.sh:2 -> :4" in x for x in changed)


def test_duplicate_emit_sites_are_repinned_in_order_not_collapsed(tmp_path):
    c = _fixture(tmp_path,
                 ["a", 'echo "=== X ==="', "b", "c", 'echo "=== X ==="'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"},
                  {"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:4"}])
    recapture(c, tmp_path)
    assert sorted(r["source"] for r in c["lines"]) == [
        "scripts/w.sh:2", "scripts/w.sh:5"]


def test_a_VANISHED_template_refuses_it_is_not_a_line_shift(tmp_path):
    c = _fixture(tmp_path, ["a", "b"],
                 [{"job": "j", "kind": "action", "template": "=== GONE ===",
                   "source": "scripts/w.sh:1"}])
    with pytest.raises(SystemExit) as exc:
        recapture(c, tmp_path)
    assert "0 emit site(s)" in str(exc.value)


def test_an_ADDED_emit_site_refuses_rather_than_silently_pinning_one(tmp_path):
    """A second site means the lane can now emit from a branch nobody classified."""
    c = _fixture(tmp_path, ['echo "=== X ==="', 'echo "=== X ==="'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    with pytest.raises(SystemExit) as exc:
        recapture(c, tmp_path)
    assert "2 emit site(s)" in str(exc.value) and "1 row(s)" in str(exc.value)


def test_it_never_edits_a_template(tmp_path):
    c = _fixture(tmp_path, ["", 'echo "=== DONE at $(date) ==="'],
                 [{"job": "j", "kind": "action",
                   "template": "=== DONE at $(date) ===",
                   "source": "scripts/w.sh:1"}])
    recapture(c, tmp_path)
    assert c["lines"][0]["template"] == "=== DONE at $(date) ==="


def test_the_live_contract_is_in_sync_with_the_live_wrappers():
    """Same assertion the local drift test makes, reachable as one command."""
    umbrella = Path("/Users/renhao/git/github/RenQuant")
    if not umbrella.exists():
        pytest.skip("umbrella absent — the CI-enforced contract tests still ran")
    path = (Path(__file__).resolve().parent.parent / "ops" / "renquant104"
            / "emitter_contract.json")
    contract = json.loads(path.read_text())
    assert recapture(contract, umbrella) == [], (
        "emitter contract drifted — run "
        "`python -m ops.renquant104.recapture_emitter_contract --note '<why>'`")


# ── [codex on orch#804] a template substring is not an emit site ──────────────

def test_a_COMMENT_quoting_the_template_is_not_an_emit_site(tmp_path):
    """codex's repro verbatim: the emitter is GONE and the only remaining match
    is a comment. Re-pinning to the obituary is worse than refusing."""
    c = _fixture(tmp_path,
                 ["# comment mentions === X === but is not an emitter",
                  'echo "other"'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:9"}])
    with pytest.raises(SystemExit) as exc:
        recapture(c, tmp_path)
    assert "0 emit site(s)" in str(exc.value)
    assert c["lines"][0]["source"] == "scripts/w.sh:9", "must not be rewritten"


def test_a_TRAILING_comment_quoting_the_template_is_not_an_emit_site(tmp_path):
    c = _fixture(tmp_path, ['ls    # echo "=== X ===" used to live here'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    with pytest.raises(SystemExit):
        recapture(c, tmp_path)


def test_a_GREP_PATTERN_quoting_the_template_is_not_an_emit_site(tmp_path):
    """The sentinel-adjacent shape: wrappers grep their own log for these lines.
    A pattern list must never be mistaken for the emitter."""
    c = _fixture(tmp_path,
                 ['PATTERN="=== X ===|=== Y ==="', 'grep -E "$PATTERN" "$LOG"',
                  'echo "=== X ==="'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    recapture(c, tmp_path)
    assert c["lines"][0]["source"] == "scripts/w.sh:3", "must pin the echo, not the pattern"


def test_printf_and_notify_also_count_as_emitters(tmp_path):
    for cmd in ('printf "=== X ===\\n"', 'notify "title" "=== X ==="'):
        c = _fixture(tmp_path, ["", cmd],
                     [{"job": "j", "kind": "action", "template": "=== X ===",
                       "source": "scripts/w.sh:1"}])
        recapture(c, tmp_path)
        assert c["lines"][0]["source"] == "scripts/w.sh:2", cmd


def test_the_live_contract_still_resolves_under_the_TIGHTER_matcher():
    """Anti-regression: tightening must not orphan a real contracted line."""
    umbrella = Path("/Users/renhao/git/github/RenQuant")
    if not umbrella.exists():
        pytest.skip("umbrella absent")
    path = (Path(__file__).resolve().parent.parent / "ops" / "renquant104"
            / "emitter_contract.json")
    contract = json.loads(path.read_text())
    assert recapture(contract, umbrella) == []


# ── [codex on orch#804] round 2: quote-aware, here-doc-aware ────────────────

def test_a_HASH_inside_the_emitted_string_is_not_a_comment(tmp_path):
    """False-NEGATIVE guard, and the dangerous one: refusing a legitimate
    emitter means the tool can never re-capture that line again."""
    c = _fixture(tmp_path, ["", 'echo "#tag === X ==="'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    recapture(c, tmp_path)
    assert c["lines"][0]["source"] == "scripts/w.sh:2"


def test_a_single_quoted_hash_is_also_not_a_comment(tmp_path):
    c = _fixture(tmp_path, ["", "echo '# === X ==='"],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    recapture(c, tmp_path)
    assert c["lines"][0]["source"] == "scripts/w.sh:2"


def test_a_REAL_trailing_comment_is_still_a_comment(tmp_path):
    """The quote-awareness must not undo the round-1 fix."""
    c = _fixture(tmp_path, ['ls   # echo "=== X ===" used to live here'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    with pytest.raises(SystemExit):
        recapture(c, tmp_path)


def test_an_echo_inside_a_HEREDOC_block_comment_never_executes(tmp_path):
    """`: <<'BLOCK' ... BLOCK` is the idiomatic shell block comment. An echo in
    there never runs; re-pinning to it is the same error as a `#` comment."""
    c = _fixture(tmp_path,
                 [": <<'BLOCK'", 'echo "=== X ==="', "BLOCK", 'echo "other"'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:9"}])
    with pytest.raises(SystemExit) as exc:
        recapture(c, tmp_path)
    assert "0 emit site(s)" in str(exc.value)
    assert c["lines"][0]["source"] == "scripts/w.sh:9"


def test_a_REAL_emitter_after_a_heredoc_closes_is_still_found(tmp_path):
    """Here-doc state must not leak past its delimiter."""
    c = _fixture(tmp_path,
                 ["cat <<EOF", "some payload", "EOF", 'echo "=== X ==="'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    recapture(c, tmp_path)
    assert c["lines"][0]["source"] == "scripts/w.sh:4"


def test_a_quoted_and_a_dash_heredoc_delimiter_both_close(tmp_path):
    for opener, closer in ((["cat <<-'PY'"], "PY"), (['cat <<"EOF"'], "EOF")):
        c = _fixture(tmp_path,
                     [*opener, 'echo "=== X ==="', closer, 'echo "=== X ==="'],
                     [{"job": "j", "kind": "action", "template": "=== X ===",
                       "source": "scripts/w.sh:1"}])
        recapture(c, tmp_path)
        assert c["lines"][0]["source"] == "scripts/w.sh:4", opener
