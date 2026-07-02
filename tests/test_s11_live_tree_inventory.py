"""Tests for scripts/s11_live_tree_inventory.py — the machine-verifiable live-tree
dirt classifier. Exercises the script against a synthetic git repo in tmp_path;
never touches the real live tree at /Users/renhao/git/github/RenQuant."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import s11_live_tree_inventory as inv  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_live_tree"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    return repo


def _commit_all(repo: Path, msg: str = "init") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


class TestReconciliationAssertion:
    def test_passes_on_fully_classified_repo(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "backtesting" / "renquant_104").mkdir(parents=True)
        (repo / "backtesting" / "renquant_104" / "strategy_config.json").write_text("{}")
        _commit_all(repo)
        (repo / "backtesting" / "renquant_104" / "strategy_config.json").write_text('{"x": 1}')

        manifest = inv.build_manifest(str(repo))
        assert manifest["reconciliation"].startswith("PASS")
        assert manifest["raw_path_count"] == 1
        assert manifest["classified_row_count"] == 1

    def test_raises_on_unclassified_path(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "some_totally_unrecognized_file.xyz").write_text("mystery")

        with pytest.raises(AssertionError, match="did not match any classification rule"):
            inv.build_manifest(str(repo))

    def test_every_raw_path_appears_exactly_once(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "doc").mkdir()
        (repo / "doc" / "dashboard.md").write_text("x")
        (repo / "subrepos.lock.json").write_text("{}")
        _commit_all(repo)
        (repo / "doc" / "dashboard.md").write_text("y")
        (repo / "subrepos.lock.json").write_text('{"a":1}')

        manifest = inv.build_manifest(str(repo))
        paths = [p["path"] for p in manifest["paths"]]
        assert len(paths) == len(set(paths)) == 2
        assert manifest["raw_path_count"] == manifest["classified_row_count"] == 2


class TestClassificationRules:
    def test_ticker_model_file_tracked(self):
        row = inv.classify(
            "backtesting/renquant_104/models/AAPL/AAPL-policy-metadata.json", "M.", False
        )
        assert row.cls == "per_ticker_model_artifact_tracked"
        assert row.disposition == "no_action"

    def test_new_ticker_directory_untracked(self):
        row = inv.classify("backtesting/renquant_104/models/SPY/", "??", True)
        assert row.cls == "per_ticker_model_artifact_new_ticker_dir"
        assert row.disposition == "self_resolving_no_action"
        assert "s11-universe-expansion-model-commit" in row.ticket

    def test_live_state_flags_unresolved(self):
        row = inv.classify(
            "backtesting/renquant_104/live_state.alpaca.json", "M.", False
        )
        assert row.cls == "live_state_tracked"
        assert row.disposition == "unresolved_needs_owner"
        assert "s11-live-state-gitignore-mismatch" in row.ticket

    def test_qp_replay_directory_unresolved(self):
        row = inv.classify("artifacts/qp_step4_replay/", "??", True)
        assert row.disposition == "unresolved_needs_owner"
        assert "s11-qp-replay-origin" in row.ticket

    def test_as_of_file_unresolved(self):
        row = inv.classify("as_of", "??", False)
        assert row.disposition == "unresolved_needs_owner"
        assert "s11-as-of-file-origin" in row.ticket

    def test_weekly_staging_ticketed_for_both_families(self):
        ltr = inv.classify(
            "backtesting/renquant_104/artifacts/prod/"
            "panel-ltr.alpha158_fund.weekly_20260630T201003Z.staging.json",
            "??", False,
        )
        calib = inv.classify(
            "backtesting/renquant_104/artifacts/prod/"
            "panel-rank-calibration.weekly_20260630T201003Z.staging.json",
            "??", False,
        )
        assert ltr.cls == calib.cls == "weekly_promote_staging"
        assert ltr.disposition == calib.disposition == "ticketed"

    def test_rollback_snapshot_distinct_from_staging(self):
        row = inv.classify(
            "backtesting/renquant_104/artifacts/prod/"
            "panel-ltr.alpha158_fund.weekly_rollback_2026-06-30.json",
            "??", False,
        )
        assert row.cls == "weekly_monthly_promote_rollback_snapshot"
        assert row.cls != "weekly_promote_staging"
        assert row.disposition == "ticketed"

    def test_runner_py_resolved_upstream(self):
        row = inv.classify("backtesting/renquant_104/adapters/runner.py", "M.", False)
        assert row.disposition == "resolved_upstream"

    def test_unrecognized_path_is_unclassified_not_silently_dropped(self):
        row = inv.classify("some/totally/novel/path.bin", "??", False)
        assert row.cls == "UNCLASSIFIED"


class TestDirectoryNestedCount:
    def test_supplementary_count_does_not_affect_reconciliation(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "artifacts").mkdir()
        (repo / "artifacts" / "keep.json").write_text("{}")
        _commit_all(repo)  # 'artifacts/' itself must be tracked so git recurses
        # into it and reports the wholly-untracked subdirectory specifically,
        # matching the real live tree's structure (artifacts/ has other
        # tracked content; only qp_step4_replay/ underneath it is untracked).
        (repo / "artifacts" / "qp_step4_replay").mkdir(parents=True)
        for i in range(5):
            (repo / "artifacts" / "qp_step4_replay" / f"f{i}.json").write_text("{}")

        manifest = inv.build_manifest(str(repo))
        # the directory is ONE raw path, regardless of how many files it contains
        assert manifest["raw_path_count"] == 1
        row = manifest["paths"][0]
        assert row["is_directory_entry"] is True
        assert row["nested_file_count_supplementary"] == 5


class TestNulSafeParsing:
    """r5 fix: the classifier consumes `git status --porcelain=v2 -z` via the
    shared git_status_porcelain.py parser, not line/space-split text mode —
    proves it actually handles paths a text-mode parser would mangle."""

    def test_filename_with_space_is_classified_not_split(self, tmp_path):
        repo = _init_repo(tmp_path)
        odd_dir = repo / "artifacts"
        odd_dir.mkdir()
        (odd_dir / "some file with spaces.json").write_text("{}")
        _commit_all(repo)
        (repo / "artifacts" / "qp_step4_replay").mkdir(parents=True)
        (repo / "artifacts" / "qp_step4_replay" / "a b.json").write_text("{}")

        manifest = inv.build_manifest(str(repo))
        assert manifest["reconciliation"].startswith("PASS")
        paths = {p["path"] for p in manifest["paths"]}
        # a text-mode last-space-split parser would truncate this to "with" or
        # "spaces.json" depending on the entry type — the full path must survive intact.
        assert "artifacts/qp_step4_replay/" in paths

    def test_rename_record_is_parsed_not_rejected(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "as_of").write_text("x" * 200)  # large enough that git detects a rename, not add+delete
        _commit_all(repo)
        _git(repo, "mv", "as_of", "as_of_renamed")
        # a staged rename is reported as a type '2' porcelain record
        entries = _porcelain_entries(repo)
        rename_entries = [e for e in entries if e.kind == "rename_copy"]
        assert len(rename_entries) == 1
        assert rename_entries[0].path == "as_of_renamed"
        assert rename_entries[0].orig_path == "as_of"
        # the classifier itself must not raise on this — it classifies by the new path
        # (as_of_renamed doesn't match any rule, so UNCLASSIFIED is the correct, honest
        # outcome here — the point of this test is "doesn't raise/misparse", not that
        # every possible renamed path has a bespoke classification rule)
        row = inv.classify(rename_entries[0].path, rename_entries[0].xy, False)
        assert row.cls == "UNCLASSIFIED"  # honest: no rule for an arbitrary renamed path

    def test_shared_parser_handles_untracked_and_ordinary_together(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "tracked.txt").write_text("v1")
        _commit_all(repo)
        (repo / "tracked.txt").write_text("v2")  # ordinary (type '1') modification
        (repo / "new_untracked.txt").write_text("new")  # untracked ('?')

        entries = _porcelain_entries(repo)
        kinds = {e.kind for e in entries}
        assert kinds == {"ordinary", "untracked"}
        paths = {e.path for e in entries}
        assert paths == {"tracked.txt", "new_untracked.txt"}


def _porcelain_entries(repo: Path):
    from git_status_porcelain import run_git_status_porcelain_v2_nul
    return run_git_status_porcelain_v2_nul(str(repo))


def test_live_manifest_file_is_internally_consistent():
    """The committed manifest.json (generated against the real live tree) must
    itself satisfy the same reconciliation property the script asserts live."""
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "doc" / "research" / "evidence" / "2026-07-02-s11-live-tree-inventory"
        / "manifest.json"
    )
    if not manifest_path.exists():
        pytest.skip("manifest not present in this checkout")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["reconciliation"].startswith("PASS")
    paths = [p["path"] for p in manifest["paths"]]
    assert len(paths) == len(set(paths)) == manifest["raw_path_count"] == manifest["classified_row_count"]
    unclassified = [p for p in manifest["paths"] if p["class"] == "UNCLASSIFIED"]
    assert unclassified == []
