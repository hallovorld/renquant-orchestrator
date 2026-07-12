"""Tests for scripts/shadow_ab_daily.sh's environment/safety contract:
no umbrella runtime defaults (every input explicit, fail-closed when
absent — Codex r2), a market snapshot with real prices whose derived
universe is asserted against the pinned watchlist (Codex r1), and a
portable timeout that marks a hung session paired-invalidated (exit 4)
even when neither ``timeout`` nor ``gtimeout`` is on PATH (Codex r1).

These exercise the script via subprocess against a fully hermetic fake
multi-repo layout (temp dirs, each a REAL git checkout so the run-manifest
verification in shadow_ab_runner.verify_run_manifest exercises real git
plumbing) — no umbrella checkout, no real broker, no network. The four
repos in the market-snapshot Python import closure (renquant-common,
renquant-base-data, renquant-artifacts, and renquant-pipeline) point at
this machine's real sibling checkouts (read-only; never written to) rather
than fake git repos.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "shadow_ab_daily.sh"

#: Real sibling-checkouts root: defaults to REPO_ROOT's own parent — the
#: layout CI's checkout steps produce (each sibling repo checked out next to
#: renquant-orchestrator). Overridable for local runs from an isolated
#: review worktree, where the worktree's parent is NOT where the real
#: sibling checkouts live.
REAL_SIBLINGS_ROOT = Path(
    os.environ.get("RENQUANT_TEST_REAL_SIBLINGS_ROOT") or REPO_ROOT.parent
)

_ALL_REPOS = (
    "renquant-common", "renquant-base-data", "renquant-artifacts",
    "renquant-model", "renquant-pipeline", "renquant-execution",
    "renquant-strategy-104", "renquant-backtesting",
)
# Importing ``renquant_pipeline.kernel.data`` initializes the package first.
# The exercised snapshot path imports these sibling source trees. Model extras
# are lazy imports and do not participate in this path.
_REAL_IMPORT_REPOS = (
    "renquant-common",
    "renquant-base-data",
    "renquant-artifacts",
    "renquant-pipeline",
)


def _real_repo_head(name: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REAL_SIBLINGS_ROOT / name), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _init_fake_repo(path: Path) -> str:
    """A minimal REAL git repo (one commit) — satisfies verify_run_manifest's
    existence/commit/clean-tree checks without needing real package code."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "src").mkdir(exist_ok=True)
    (path / "README.md").write_text("fake pinned checkout for tests\n")
    _git("init", "-q", cwd=path)
    _git("config", "user.email", "test@example.com", cwd=path)
    _git("config", "user.name", "Test", cwd=path)
    _git("add", "-A", cwd=path)
    _git("commit", "-q", "-m", "init", cwd=path)
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _stub_python(tmp_path: Path, *, real_python: str, sleep_seconds: float | None, exit_code: int,
                  argv_capture_path: Path | None = None) -> Path:
    """A ``$PYTHON`` stand-in: passes native-live-market-snapshot calls
    through to the REAL interpreter (so the market-snapshot/universe
    assertion logic runs for real), but intercepts ``shadow-ab`` itself so
    the test never needs a full pinned-model/broker stack. When
    ``argv_capture_path`` is given, the intercepted invocation's OWN argv is
    written there first — lets a test assert on exactly what CLI arguments
    (e.g. ``--strategy-dir``) the wrapper actually passed downstream,
    independent of what the (stubbed-out) runner would have done with them."""
    stub = tmp_path / "stub_python.sh"
    capture_line = (
        f'printf "%s\\n" "$@" > "{argv_capture_path}"' if argv_capture_path is not None else ""
    )
    body = f"""#!/usr/bin/env bash
    if [[ "$*" == *"renquant_orchestrator shadow-ab"* ]]; then
        {capture_line}
        {"sleep " + str(sleep_seconds) + " &" if sleep_seconds is not None else ""}
        {"wait $!" if sleep_seconds is not None else ""}
        echo '{{"exit_hint": {exit_code}}}'
        exit {exit_code}
    fi
    exec "{real_python}" "$@"
    """
    stub.write_text(textwrap.dedent(body))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _build_manifest(tmp_path: Path, *, watchlist: list[str], dirty: str | None = None,
                     wrong_commit: str | None = None) -> tuple[Path, Path]:
    """Builds the immutable run manifest + the pinned strategy-104 configs it
    points at. ``dirty``/``wrong_commit`` name a repo to deliberately break,
    for the rejection tests."""
    repos_dir = tmp_path / "repos"
    manifest_repos: dict[str, dict] = {}
    for name in _ALL_REPOS:
        if name in _REAL_IMPORT_REPOS:
            path = REAL_SIBLINGS_ROOT / name
            commit = _real_repo_head(name)
        elif name == "renquant-strategy-104":
            # Configs must exist BEFORE the initial commit — writing them
            # afterward would leave this checkout permanently "dirty" per
            # verify_run_manifest's clean-tree check, masking the deliberate
            # dirty/wrong-commit cases this fixture exists to test.
            path = repos_dir / name
            configs = path / "configs"
            configs.mkdir(parents=True, exist_ok=True)
            config = {"watchlist": watchlist}
            (configs / "strategy_config.shadow_a.json").write_text(json.dumps(config))
            (configs / "strategy_config.shadow_b.json").write_text(json.dumps(config))
            (configs / "xgb_prod_artifact_manifest.json").write_text(json.dumps({}))
            commit = _init_fake_repo(path)
        else:
            path = repos_dir / name
            commit = _init_fake_repo(path)
        if name == wrong_commit:
            commit = "0" * 40
        manifest_repos[name] = {"path": str(path), "commit": commit}

    if dirty is not None:
        target = Path(manifest_repos[dirty]["path"])
        (target / "dirty_marker.txt").write_text("uncommitted\n")

    strategy_104 = Path(manifest_repos["renquant-strategy-104"]["path"])
    manifest = {"repos": manifest_repos, "data_revision": "test-rev-1"}
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path, strategy_104


def _env_for(tmp_path: Path, *, python: Path, run_manifest: Path,
             timeout_sec: int, path_override: str | None = None,
             skip_manifest_verify: bool = False) -> dict:
    ohlcv_dir = tmp_path / "ohlcv"
    env = dict(os.environ)
    env.update({
        "RENQUANT_SHADOW_AB_PYTHON": str(python),
        "RENQUANT_SHADOW_AB_RUN_MANIFEST": str(run_manifest),
        "RENQUANT_SHADOW_AB_REPO_ROOT": str(tmp_path / "runtime_root"),
        "RENQUANT_SHADOW_AB_DATA_ROOT": str(ohlcv_dir),
        "RENQUANT_SHADOW_AB_ROOT": str(tmp_path / "out"),
        "RENQUANT_SHADOW_AB_SESSION_DATE": "2026-07-10",
        "RENQUANT_SHADOW_AB_TIMEOUT_SEC": str(timeout_sec),
    })
    if skip_manifest_verify:
        env["RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY"] = "1"
    if path_override is not None:
        env["PATH"] = path_override
    return env


def _write_close_price(ohlcv_dir: Path, symbol: str, close: float) -> None:
    d = ohlcv_dir / symbol.upper()
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {"close": [close]},
        index=pd.DatetimeIndex(["2026-07-09"], name="date"),
    )
    df.to_parquet(d / "1d.parquet")


@pytest.fixture
def real_python() -> str:
    return sys.executable


def _log_text(tmp_path: Path) -> str:
    return (tmp_path / "out" / "logs" / "2026-07-10_session.log").read_text()


def _run_script(env, timeout=30):
    """Invoke the wrapper and, on ANY completion, print the session log tail —
    pytest shows it on failure, turning a bare 'exit 2' into a diagnosis
    (three 2026-07-11 CI flakes were undiagnosable without this)."""
    result = subprocess.run(
        [str(SCRIPT)], env=env, capture_output=True, text=True, timeout=timeout,
    )
    root = env.get("RENQUANT_SHADOW_AB_ROOT")
    if root:
        for log in sorted(Path(root).glob("logs/*_session.log")):
            print(f"--- wrapper log {log} (rc={result.returncode}) ---")
            print("\n".join(log.read_text().splitlines()[-25:]))
    print(f"--- wrapper stderr ---\n{result.stderr}")
    return result


class TestExplicitRuntimeInputs:
    def test_missing_required_env_fails_closed(self, tmp_path, real_python):
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = _env_for(tmp_path, python=Path(real_python), run_manifest=manifest,
                        timeout_sec=60)
        del env["RENQUANT_SHADOW_AB_REPO_ROOT"]
        result = _run_script(env)
        assert result.returncode != 0
        assert "RENQUANT_SHADOW_AB_REPO_ROOT" in result.stderr

    def test_no_umbrella_path_default_in_script(self):
        # The concept may be named in comments (explaining WHY there's no
        # default); what must never exist is an actual fallback VALUE
        # pointing at the umbrella tree (the "${VAR:-/path/to/RenQuant}"
        # shape the old script used for REPO_DIR/PYTHON/etc).
        text = SCRIPT.read_text()
        assert "/RenQuant}" not in text, "no default value may point at the umbrella tree"
        assert ":-/Users" not in text, "no runtime input may default to a hardcoded absolute path"

    def test_umbrella_concept_only_appears_in_prose(self):
        for line in SCRIPT.read_text().splitlines():
            stripped = line.strip()
            if "RenQuant" in line:
                assert stripped.startswith("#"), f"non-comment line references RenQuant: {line!r}"

    def test_rogue_strategy_dir_env_var_cannot_diverge_the_cli_argument(self, tmp_path, real_python):
        # Codex re-review of #460 r2: a separate RENQUANT_SHADOW_AB_STRATEGY_DIR
        # input let a caller pair manifest-verified configs with artifacts
        # resolved from an arbitrary, UNVERIFIED checkout for --strategy-dir
        # (run_shadow_ab_session's artifact-fingerprint-resolution anchor) --
        # a pin-integrity hole even though the watchlist/configs themselves
        # were already correctly manifest-derived. The fix removes the input
        # entirely. Captures the stub's OWN argv (rather than asserting on
        # anything the stubbed-out runner would have done with it) to prove
        # the wrapper passes the value it itself resolved from the verified
        # manifest to --strategy-dir, regardless of what a rogue env var of
        # the old (now-unused) name claims.
        manifest, strategy_dir = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = _env_for(tmp_path, python=Path(real_python), run_manifest=manifest, timeout_sec=5,
                        skip_manifest_verify=True)
        _write_close_price(Path(env["RENQUANT_SHADOW_AB_DATA_ROOT"]), "AAPL", 190.0)

        rogue_dir = tmp_path / "rogue_unverified_checkout"
        rogue_dir.mkdir(parents=True)
        env["RENQUANT_SHADOW_AB_STRATEGY_DIR"] = str(rogue_dir)

        argv_capture = tmp_path / "captured_argv.txt"
        stub = _stub_python(tmp_path, real_python=real_python, sleep_seconds=None, exit_code=0,
                             argv_capture_path=argv_capture)
        env["RENQUANT_SHADOW_AB_PYTHON"] = str(stub)
        result = _run_script(env)
        assert result.returncode == 0
        argv_lines = argv_capture.read_text().splitlines()
        idx = argv_lines.index("--strategy-dir")
        passed_strategy_dir = argv_lines[idx + 1]
        assert passed_strategy_dir == str(strategy_dir)
        assert passed_strategy_dir != str(rogue_dir)


class TestRunManifestVerification:
    """Real Python runs `-m renquant_orchestrator shadow-ab` here (no stub) —
    verify_run_manifest must reject BEFORE the stubbed-out broker/model stack
    would even matter, so these exercise the actual verification code path,
    not a stand-in that would trivially "pass" regardless of the manifest."""

    def test_wrong_commit_repo_fails_closed_before_either_arm(self, tmp_path, real_python):
        manifest, _ = _build_manifest(
            tmp_path, watchlist=["AAPL"], wrong_commit="renquant-execution",
        )
        env = _env_for(tmp_path, python=Path(real_python), run_manifest=manifest,
                        timeout_sec=60)
        _write_close_price(Path(env["RENQUANT_SHADOW_AB_DATA_ROOT"]), "AAPL", 190.0)
        result = _run_script(env)
        assert result.returncode == 3, "run-manifest verification failure is a precheck abort"
        assert not list((tmp_path / "out").glob("prices_*.json"))
        assert not list((tmp_path / "out").glob("market_snapshot_*.json"))

    def test_dirty_repo_fails_closed_before_either_arm(self, tmp_path, real_python):
        manifest, _ = _build_manifest(
            tmp_path, watchlist=["AAPL"], dirty="renquant-execution",
        )
        env = _env_for(tmp_path, python=Path(real_python), run_manifest=manifest,
                        timeout_sec=60)
        _write_close_price(Path(env["RENQUANT_SHADOW_AB_DATA_ROOT"]), "AAPL", 190.0)
        result = _run_script(env)
        assert result.returncode == 3, "run-manifest verification failure is a precheck abort"
        assert not list((tmp_path / "out").glob("prices_*.json"))
        assert not list((tmp_path / "out").glob("market_snapshot_*.json"))


class TestMarketSnapshotIntegrity:
    def test_missing_local_close_price_fails_closed(self, tmp_path, real_python):
        manifest, _ = _build_manifest(tmp_path, watchlist=["ZZZZ_NO_DATA"])
        env = _env_for(tmp_path, python=Path(real_python), run_manifest=manifest,
                        timeout_sec=60, skip_manifest_verify=True)
        result = _run_script(env)
        assert result.returncode == 2
        log = _log_text(tmp_path)
        assert "no local close price" in log
        assert "ZZZZ_NO_DATA" in log

    def test_sealed_snapshot_universe_matches_pinned_watchlist(self, tmp_path, real_python):
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL", "MSFT"])
        env = _env_for(tmp_path, python=Path(real_python), run_manifest=manifest,
                        timeout_sec=5, skip_manifest_verify=True)
        _write_close_price(Path(env["RENQUANT_SHADOW_AB_DATA_ROOT"]), "AAPL", 190.0)
        _write_close_price(Path(env["RENQUANT_SHADOW_AB_DATA_ROOT"]), "MSFT", 410.0)
        stub = _stub_python(tmp_path, real_python=real_python, sleep_seconds=None, exit_code=0)
        env["RENQUANT_SHADOW_AB_PYTHON"] = str(stub)
        result = _run_script(env)
        snapshot = json.loads((tmp_path / "out" / "market_snapshot_2026-07-10.json").read_text())
        assert sorted(snapshot["prices"]) == ["AAPL", "MSFT"]
        assert snapshot["prices"]["AAPL"] == 190.0
        log = _log_text(tmp_path)
        assert "universe assertion OK: 2 symbols" in log
        assert result.returncode == 0


class TestPortableTimeout:
    def _minimal_path_without_timeout(self) -> str:
        """A PATH with the usual shell tools but neither ``timeout`` nor
        ``gtimeout`` — simulates a bare macOS host with no GNU coreutils."""
        candidates = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        return ":".join(p for p in candidates if os.path.isdir(p))

    def test_hung_session_is_killed_and_marked_pair_invalidated(self, tmp_path, real_python):
        # Portable across hosts: whether this host's PATH actually excludes
        # timeout/gtimeout (bash-watchdog fallback fires) or not (a real
        # GNU timeout — e.g. Linux CI's /usr/bin/timeout — fires instead
        # despite the "minimal" PATH below), the OUTCOME must be identical:
        # killed well within the bound and marked exit=4.
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = _env_for(
            tmp_path, python=Path(real_python), run_manifest=manifest,
            timeout_sec=2,
            path_override=self._minimal_path_without_timeout(),
            skip_manifest_verify=True,
        )
        _write_close_price(Path(env["RENQUANT_SHADOW_AB_DATA_ROOT"]), "AAPL", 190.0)
        stub = _stub_python(tmp_path, real_python=real_python, sleep_seconds=120, exit_code=0)
        env["RENQUANT_SHADOW_AB_PYTHON"] = str(stub)
        start = time.monotonic()
        result = _run_script(env)
        elapsed = time.monotonic() - start
        assert result.returncode == 4
        assert elapsed < 15, "must be killed well before the stub's 120s sleep completes"
        log = _log_text(tmp_path)
        assert "SHADOW-AB TIMEOUT" in log
        assert "shadow-ab exit=4" in log

    def test_fast_session_exit_code_passes_through_under_watchdog(self, tmp_path, real_python):
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = _env_for(
            tmp_path, python=Path(real_python), run_manifest=manifest,
            timeout_sec=30,
            path_override=self._minimal_path_without_timeout(),
            skip_manifest_verify=True,
        )
        _write_close_price(Path(env["RENQUANT_SHADOW_AB_DATA_ROOT"]), "AAPL", 190.0)
        stub = _stub_python(tmp_path, real_python=real_python, sleep_seconds=None, exit_code=3)
        env["RENQUANT_SHADOW_AB_PYTHON"] = str(stub)
        result = _run_script(env)
        assert result.returncode == 3
        log = _log_text(tmp_path)
        assert "shadow-ab exit=3" in log


class TestSessionCalendarGate:
    """Codex review of #488: the D6 experiment unit is a trading SESSION,
    not a calendar weekday — the launchd Mon-Fri ``StartCalendarInterval``
    filter is a cost optimization only, never the correctness mechanism.
    These exercise the script's own session-calendar guard directly against
    the REAL, canonical ``renquant_common.market_calendar`` (backed by
    ``pandas_market_calendars`` — no hand-rolled holiday list, no umbrella
    path), using real 2026 NYSE calendar dates:

    * 2026-07-04 is a Saturday (weekend, not a session).
    * 2026-11-26 (Thanksgiving Day, a Thursday) is a real NYSE full-closure
      holiday: pandas_market_calendars' NYSE ``schedule()`` has NO row for
      that date at all.
    * 2026-11-27 (the day after Thanksgiving, a Friday) is a real NYSE
      early-close/half-day SESSION: it has a schedule row, with
      ``market_close`` at 18:00 UTC (13:00 ET) instead of the normal 21:00
      UTC (16:00 ET) — confirmed via
      ``pandas_market_calendars.get_calendar("NYSE").early_closes(schedule)``
      for 2026, which lists exactly 2026-11-27 and 2026-12-24. A half day is
      a valid paired session and must NOT be skipped.
    """

    @staticmethod
    def _env_for_date(tmp_path, *, python, run_manifest, session_date, timeout_sec=60,
                      skip_manifest_verify=True):
        env = _env_for(tmp_path, python=python, run_manifest=run_manifest,
                        timeout_sec=timeout_sec, skip_manifest_verify=skip_manifest_verify)
        env["RENQUANT_SHADOW_AB_SESSION_DATE"] = session_date
        return env

    @staticmethod
    def _log_text_for(tmp_path, session_date):
        return (tmp_path / "out" / "logs" / f"{session_date}_session.log").read_text()

    @staticmethod
    def _assert_no_observation_written(tmp_path):
        out = tmp_path / "out"
        # No run bundle, price snapshot, or paired-session record of any
        # kind — the guard must exit before the script's existing
        # market-snapshot / run-manifest / shadow-ab-invocation logic runs.
        assert not list(out.glob("prices_*.json"))
        assert not list(out.glob("market_snapshot_*.json"))
        assert not list(out.glob("session_*.json"))
        assert not list(out.glob("session_*_stderr.log"))

    def test_saturday_is_skipped_with_no_observation(self, tmp_path, real_python):
        session_date = "2026-07-04"
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = self._env_for_date(tmp_path, python=Path(real_python), run_manifest=manifest,
                                  session_date=session_date)
        result = _run_script(env)
        assert result.returncode == 0
        log = self._log_text_for(tmp_path, session_date)
        assert "SKIP:" in log
        assert "not an NYSE trading session" in log
        self._assert_no_observation_written(tmp_path)

    def test_weekday_nyse_holiday_is_skipped_with_no_observation(self, tmp_path, real_python):
        session_date = "2026-11-26"  # Thanksgiving Day (Thursday)
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = self._env_for_date(tmp_path, python=Path(real_python), run_manifest=manifest,
                                  session_date=session_date)
        result = _run_script(env)
        assert result.returncode == 0
        log = self._log_text_for(tmp_path, session_date)
        assert "SKIP:" in log
        assert "not an NYSE trading session" in log
        self._assert_no_observation_written(tmp_path)

    def test_early_close_half_day_is_not_skipped(self, tmp_path, real_python):
        # 2026-11-27 (day after Thanksgiving) — a real half-day session.
        # "Preserve early-close sessions" (Codex): the gate must let this
        # proceed exactly like any other trading day.
        session_date = "2026-11-27"
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = self._env_for_date(tmp_path, python=Path(real_python), run_manifest=manifest,
                                  session_date=session_date)
        _run_script(env)
        log = self._log_text_for(tmp_path, session_date)
        assert "SKIP:" not in log

    def test_normal_weekday_is_not_skipped(self, tmp_path, real_python):
        # 2026-07-10 (Friday) — a normal NYSE trading day, and this test
        # file's existing default RENQUANT_SHADOW_AB_SESSION_DATE. Fuller
        # end-to-end progression past the gate on this same date (sealed
        # snapshot, universe assertion, full stubbed session) is already
        # exercised by TestMarketSnapshotIntegrity /
        # TestExplicitRuntimeInputs / TestPortableTimeout above; this test
        # only pins down that the NEW session-calendar guard itself does
        # not fire for it.
        session_date = "2026-07-10"
        manifest, _ = _build_manifest(tmp_path, watchlist=["AAPL"])
        env = self._env_for_date(tmp_path, python=Path(real_python), run_manifest=manifest,
                                  session_date=session_date)
        _run_script(env)
        log = self._log_text_for(tmp_path, session_date)
        assert "SKIP:" not in log

    def test_dirty_manifest_on_non_session_date_fails_closed_not_skip(self, tmp_path, real_python):
        # P0 ordering fix (Codex round 3 on #488): the run-manifest / pin-
        # identity precheck (verify_run_manifest, see TestRunManifestVerification
        # above) must run BEFORE the trading-session calendar check, because
        # that check imports renquant_common.market_calendar from a
        # manifest-pinned sibling checkout. Pair a real non-session date
        # (Saturday, same as test_saturday_is_skipped_with_no_observation
        # above) with a DIRTY pinned repo (same _build_manifest(dirty=...)
        # fixture as test_dirty_repo_fails_closed_before_either_arm) and
        # assert the identity failure (PRECHECK, exit 3) wins — the script
        # must NEVER reach the calendar check and silently SKIP as if the
        # dirty checkout were irrelevant because "today isn't a trading day
        # anyway."
        session_date = "2026-07-04"  # Saturday (non-session)
        manifest, _ = _build_manifest(
            tmp_path, watchlist=["AAPL"], dirty="renquant-execution",
        )
        env = self._env_for_date(tmp_path, python=Path(real_python), run_manifest=manifest,
                                  session_date=session_date, skip_manifest_verify=False)
        result = _run_script(env)
        assert result.returncode == 3, "run-manifest identity failure must win over a SKIP"
        log = self._log_text_for(tmp_path, session_date)
        assert "PRECHECK" in log
        assert "SKIP:" not in log
        self._assert_no_observation_written(tmp_path)
