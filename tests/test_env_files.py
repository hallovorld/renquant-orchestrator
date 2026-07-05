"""Tests for env_files — read_env_file and load_env_file."""
from __future__ import annotations

import os

import pytest

from renquant_orchestrator.env_files import load_env_file, read_env_file


class TestReadEnvFile:
    def test_none_path_returns_empty(self):
        assert read_env_file(None) == {}

    def test_missing_file_missing_ok_true(self, tmp_path):
        assert read_env_file(tmp_path / "nonexistent.env") == {}

    def test_missing_file_missing_ok_false(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="env file not found"):
            read_env_file(tmp_path / "nonexistent.env", missing_ok=False)

    def test_skips_comments_and_blank_lines(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# comment\n\nFOO=bar\n  # indented comment\nBAZ=qux\n")
        result = read_env_file(env)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_strips_export_prefix(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("export MY_KEY=my_value\n")
        result = read_env_file(env)
        assert result == {"MY_KEY": "my_value"}

    def test_strips_single_and_double_quotes(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("A='single'\nB=\"double\"\nC=noquotes\n")
        result = read_env_file(env)
        assert result == {"A": "single", "B": "double", "C": "noquotes"}

    def test_splits_on_first_equals_only(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("URL=https://host.com?a=1&b=2\n")
        result = read_env_file(env)
        assert result == {"URL": "https://host.com?a=1&b=2"}

    def test_skips_lines_without_equals(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("VALID=ok\nno_equals_here\n")
        result = read_env_file(env)
        assert result == {"VALID": "ok"}

    def test_empty_key_skipped(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("=emptykey\nGOOD=yes\n")
        result = read_env_file(env)
        assert result == {"GOOD": "yes"}


class TestLoadEnvFile:
    def test_sets_environ(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("TEST_ENV_FILES_X=hello\n")
        monkeypatch.delenv("TEST_ENV_FILES_X", raising=False)
        result = load_env_file(env)
        assert result == {"TEST_ENV_FILES_X": "hello"}
        assert os.environ["TEST_ENV_FILES_X"] == "hello"

    def test_override_false_does_not_overwrite(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_ENV_FILES_Y", "original")
        env = tmp_path / ".env"
        env.write_text("TEST_ENV_FILES_Y=overwritten\n")
        load_env_file(env, override=False)
        assert os.environ["TEST_ENV_FILES_Y"] == "original"

    def test_override_true_does_overwrite(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_ENV_FILES_Z", "original")
        env = tmp_path / ".env"
        env.write_text("TEST_ENV_FILES_Z=overwritten\n")
        load_env_file(env, override=True)
        assert os.environ["TEST_ENV_FILES_Z"] == "overwritten"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_env_file(tmp_path / "missing.env")
