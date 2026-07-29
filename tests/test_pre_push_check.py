"""Each test reconstructs a defect that actually reached review on 2026-07-29.

Five separate pre-push mistakes in one session, every one mechanically
detectable at the time, every one caught by a reviewer instead. These tests
build a real git repo per case and assert the check fires — so the script is
pinned against the incidents rather than against my idea of them.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import pre_push_check as P  # noqa: E402

GOOD_DOC = """\
# Progress: something

STATUS:   delivered.
WHAT:     a thing.
WHY/DIR:  a reason.
EVIDENCE: artifact: x
  prod or exp:   exp
  existing data: yes
  best-known?:   yes
  scope:         here
NEXT:     nothing.
"""


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _run(r, "init", "-q", "-b", "main")
    _run(r, "config", "user.email", "t@example.com")
    _run(r, "config", "user.name", "t")
    (r / "seed.txt").write_text("seed\n")
    _run(r, "add", "-A")
    _run(r, "commit", "-q", "-m", "seed")
    # a local ref standing in for origin/main
    _run(r, "branch", "base")
    return r


def _commit(repo: Path, msg: str) -> None:
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", msg)


def _checks(findings, name):
    return [f for f in findings if f.check == name]


# --- incident 1: authored on main instead of a worktree --------------------

def test_authoring_on_main_is_blocked(tmp_path):
    r = _repo(tmp_path)
    assert _run(r, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    f = P.check_not_authoring_on_a_protected_branch(str(r))
    assert len(f) == 1 and f[0].gate
    assert "worktree" in f[0].message


def test_a_feature_branch_passes(tmp_path):
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-b", "feat/x")
    assert P.check_not_authoring_on_a_protected_branch(str(r)) == []


# --- incident 2: stale base turned a merge into a deletion -----------------

def test_a_stale_base_is_blocked(tmp_path):
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-b", "feat/x")
    (r / "mine.txt").write_text("mine\n")
    _commit(r, "my work")
    # someone else merges into base after I branched
    _run(r, "checkout", "-q", "base")
    (r / "theirs.txt").write_text("theirs\n")
    _commit(r, "their work")
    _run(r, "checkout", "-q", "feat/x")

    f = P.check_base_is_current(str(r), "base")
    assert len(f) == 1 and "1 commit(s) behind" in f[0].message

    # and this is exactly why: their file reads as a deletion in my diff
    scope = P.check_diff_is_scoped(str(r), "base")
    assert any("theirs.txt" in s.message for s in scope)
    assert any("DELETED" in s.message for s in scope)


def test_a_current_base_passes(tmp_path):
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-b", "feat/x")
    (r / "mine.txt").write_text("mine\n")
    _commit(r, "my work")
    assert P.check_base_is_current(str(r), "base") == []


# --- incident 3: a one-entry JSON edit reformatted the whole file ----------

def test_a_whole_file_reformat_is_flagged(tmp_path):
    r = _repo(tmp_path)
    jobs = {f"job{i}": {"program_args": ["/bin/zsh", f"/x/{i}.sh"]}
            for i in range(60)}
    (r / "manifest.json").write_text(json.dumps({"jobs": jobs}, indent=2))
    _commit(r, "add manifest")
    _run(r, "branch", "-f", "base")
    _run(r, "checkout", "-q", "-b", "feat/x")
    # change ONE entry, but reserialize at a different indent
    jobs["job0"]["program_args"] = ["/bin/zsh", "/x/CHANGED.sh"]
    (r / "manifest.json").write_text(json.dumps({"jobs": jobs}, indent=1))
    _commit(r, "swap one job")

    f = _checks(P.check_diff_is_scoped(str(r), "base"), "scope")
    assert any("whole-file rewrite" in x.message for x in f)


def test_a_targeted_edit_is_not_flagged(tmp_path):
    r = _repo(tmp_path)
    jobs = {f"job{i}": {"program_args": ["/bin/zsh", f"/x/{i}.sh"]}
            for i in range(60)}
    text = json.dumps({"jobs": jobs}, indent=2)
    (r / "manifest.json").write_text(text)
    _commit(r, "add manifest")
    _run(r, "branch", "-f", "base")
    _run(r, "checkout", "-q", "-b", "feat/x")
    (r / "manifest.json").write_text(text.replace("/x/0.sh", "/x/CHANGED.sh"))
    _commit(r, "swap one job")

    assert not any("whole-file rewrite" in x.message
                   for x in P.check_diff_is_scoped(str(r), "base"))


# --- incident 4: `EVIDENCE (§4(b)):` failed the contract ------------------

def _branch_with_doc(tmp_path: Path, body: str) -> Path:
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-b", "feat/x")
    d = r / "doc" / "progress"
    d.mkdir(parents=True)
    (d / "2026-07-29-x.md").write_text(body)
    _commit(r, "doc")
    return r


def test_the_section_numbered_evidence_header_is_caught(tmp_path):
    bad = GOOD_DOC.replace("EVIDENCE:", "EVIDENCE (§4(b)):")
    r = _branch_with_doc(tmp_path, bad)
    f = P.check_progress_doc(str(r), "base")
    assert f and "EVIDENCE:" in f[0].message


def test_a_compliant_doc_passes(tmp_path):
    r = _branch_with_doc(tmp_path, GOOD_DOC)
    assert P.check_progress_doc(str(r), "base") == []


def test_a_missing_progress_doc_is_caught(tmp_path):
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-b", "feat/x")
    (r / "code.py").write_text("x = 1\n")
    _commit(r, "code")
    f = P.check_progress_doc(str(r), "base")
    assert f and "no doc/progress" in f[0].message


def test_the_contract_is_imported_not_reimplemented():
    """If these ever diverge, the pre-push gate becomes a second opinion."""
    from renquant_orchestrator import agent_workflows
    assert P.progress_doc_findings is agent_workflows.progress_doc_findings


# --- incident 5: repo placement — INFO, deliberately not a gate ------------

def test_placement_is_reported_but_never_blocks(tmp_path):
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-b", "feat/x")
    (r / "doc").mkdir()
    (r / "doc" / "research.md").write_text("x\n")
    _commit(r, "research")
    notes = P.placement_notes(str(r), "base")
    assert len(notes) == 1
    assert notes[0].gate is False
    assert "CLAUDE.md" in notes[0].message


def test_informational_findings_do_not_fail_the_run(tmp_path, capsys):
    r = _branch_with_doc(tmp_path, GOOD_DOC)
    rc = P.main(["--repo", str(r), "--base", "base"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[info ]" in out and "clean" in out


def test_a_blocking_finding_fails_the_run(tmp_path, capsys):
    bad = GOOD_DOC.replace("EVIDENCE:", "EVIDENCE (§4(b)):")
    r = _branch_with_doc(tmp_path, bad)
    rc = P.main(["--repo", str(r), "--base", "base"])
    assert rc == 1
    assert "[BLOCK]" in capsys.readouterr().out


def test_skip_progress_doc_flag(tmp_path):
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-b", "feat/x")
    (r / "code.py").write_text("x = 1\n")
    _commit(r, "code")
    assert P.main(["--repo", str(r), "--base", "base",
                   "--skip-progress-doc"]) == 0


@pytest.mark.parametrize("branch", ["main", "master"])
def test_both_protected_branch_names(tmp_path, branch):
    r = _repo(tmp_path)
    _run(r, "checkout", "-q", "-B", branch)
    assert P.check_not_authoring_on_a_protected_branch(str(r))


def test_unreadable_repo_is_reported_not_silently_clean(tmp_path):
    missing = str(tmp_path / "nope")
    assert P.check_not_authoring_on_a_protected_branch(missing)
    assert P.check_base_is_current(missing, "base")
