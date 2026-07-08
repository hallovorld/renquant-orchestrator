"""End-to-end test of scripts/run_sweep_modal.py::run_sweep against the REAL
ResultStore API — not mocked-apart unit tests of each piece in isolation.

Before the fix, run_sweep_modal.py called ResultStore/insert_variant/
completed_variants/finalize with a signature that did not match the real
class (see doc/progress/2026-07-07-cloud-sweep-executor-phase1.md round 2)
— every unit test of ResultStore in isolation and of the executor protocol
in isolation still passed, because neither exercised the two integrated.
This test drives run_sweep() with a fake in-memory executor and a real,
tmp-path-backed ResultStore, so an API mismatch between the two fails here.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from renquant_orchestrator.cloud.executor import BacktestResult, BatchSummary, DataManifest
from renquant_orchestrator.cloud.result_store import ResultStore

from run_sweep_modal import run_sweep, stage_panel_history


FROZEN_SEEDS = (42, 43, 44)


@dataclass(frozen=True)
class _FakeVariantSpec:
    name: str
    role: str
    entry_cap: float
    drift_buffer: float
    topup_threshold: float
    config_path: Path
    seeds: tuple[int, ...] = FROZEN_SEEDS

    def as_json(self) -> dict:
        return {
            "name": self.name, "role": self.role, "entry_cap": self.entry_cap,
            "drift_buffer": self.drift_buffer, "topup_threshold": self.topup_threshold,
            "config_path": str(self.config_path), "seeds": list(self.seeds),
        }


def _seed_row(seed, *, sharpe, bull_calm_sharpe, bull_calm_dd=0.05, full_dd=0.08,
              turnover=0.30, net_positive=True):
    return {
        "seed": seed,
        "sharpe": sharpe,
        "sharpe_net_of_cost": sharpe,
        "apy": 0.10,
        "max_dd": full_dd,
        "calmar": 2.0,
        "per_regime": {
            "BULL_CALM": {"sharpe": bull_calm_sharpe, "sharpe_net_of_cost": bull_calm_sharpe,
                          "max_dd": bull_calm_dd, "apy": 0.12, "n_days": 200},
            "BEAR": {"sharpe": sharpe, "sharpe_net_of_cost": sharpe,
                     "max_dd": full_dd, "apy": -0.02, "n_days": 60},
            "BULL_VOLATILE": {"sharpe": sharpe, "sharpe_net_of_cost": sharpe,
                               "max_dd": full_dd, "apy": 0.05, "n_days": 80},
        },
        "turnover": {"turnover_annualized": turnover, "modeled_cost_bps": turnover * 10.0},
        "winner_continuation": {"net_positive": net_positive},
    }


class _FakeExecutor:
    """Deterministic in-memory BacktestExecutor — no real subprocess/Modal call."""

    def __init__(self, canned: dict[str, list[dict] | None]):
        self._canned = canned  # variant_name -> per_seed rows, or None for error

    def execute_batch(self, requests, *, on_result, on_error, max_concurrent=100):
        n_completed = n_failed = 0
        for req in requests:
            per_seed = self._canned.get(req.variant_name)
            if per_seed is None:
                on_error(req.variant_name, RuntimeError("canned failure"))
                n_failed += 1
                continue
            result = BacktestResult(
                variant_name=req.variant_name,
                role=req.role,
                config_fingerprint=hashlib.sha256(req.config_json.encode()).hexdigest(),
                worker_id="fake-worker-0",
                volume_commit_id=req.volume_commit_id,
                code_image_id="fake-image",
                started_at="2026-01-01T00:00:00Z",
                finished_at="2026-01-01T00:00:01Z",
                elapsed_seconds=1.0,
                peak_memory_mb=128.0,
                seeds=req.seeds,
                per_seed=per_seed,
            )
            on_result(result)
            n_completed += 1
        return BatchSummary(
            total_seconds=float(len(requests)), cost_usd=0.01 * len(requests),
            n_completed=n_completed, n_failed=n_failed,
        )


@pytest.fixture
def variants(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    def _write(name):
        p = config_dir / f"{name}.json"
        p.write_text(json.dumps({"watchlist": ["AAPL"]}))
        return p

    incumbent = _FakeVariantSpec(
        "incumbent", "incumbent", 0.10, 0.0, 0.05, _write("incumbent"),
    )
    winner = _FakeVariantSpec(
        "cap12_drift00_topup05", "candidate", 0.12, 0.0, 0.05, _write("winner"),
    )
    loser = _FakeVariantSpec(
        "cap20_drift00_topup05", "candidate", 0.20, 0.0, 0.05, _write("loser"),
    )
    failing = _FakeVariantSpec(
        "cap30_drift00_topup05", "candidate", 0.30, 0.0, 0.05, _write("failing"),
    )
    aa = _FakeVariantSpec(
        "aa_resplit", "aa_resplit", 0.10, 0.0, 0.05, _write("aa"),
    )
    return {"incumbent": incumbent, "winner": winner, "loser": loser,
            "failing": failing, "aa": aa}


@pytest.fixture
def store(tmp_path):
    s = ResultStore("test-modal-sweep", tmp_path / "store")
    s.init_sweep(
        backend="modal", backtest_start="2024-01-02", backtest_end="2026-03-28",
        initial_cash=100_000.0, grid_spec={"n": 4}, n_variants=4,
    )
    yield s
    s.close()


class TestRunSweepEndToEnd:
    def test_persists_variants_computes_verdicts_and_finalizes(self, tmp_path, variants, store):
        canned = {
            "incumbent": [
                _seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0) for s in FROZEN_SEEDS
            ],
            # dominates the incumbent on every criterion, every seed
            "cap12_drift00_topup05": [
                _seed_row(s, sharpe=1.3, bull_calm_sharpe=1.3, bull_calm_dd=0.04)
                for s in FROZEN_SEEDS
            ],
            # gross Sharpe looks fine but regresses vs incumbent on BULL_CALM
            "cap20_drift00_topup05": [
                _seed_row(s, sharpe=1.0, bull_calm_sharpe=0.5) for s in FROZEN_SEEDS
            ],
            "cap30_drift00_topup05": None,  # canned failure
            "aa_resplit": [
                _seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0) for s in FROZEN_SEEDS
            ],
        }
        executor = _FakeExecutor(canned)
        grid_variants = [variants["incumbent"], variants["winner"],
                          variants["loser"], variants["failing"]]
        aa_variant = variants["aa"]
        variant_by_name = {v.name: v for v in grid_variants}
        variant_by_name[aa_variant.name] = aa_variant

        data_manifest = DataManifest(
            commit_id="deadbeef", timestamp="2026-01-01T00:00:00Z", files={}, total_bytes=0,
        )

        result = run_sweep(
            executor=executor,
            store=store,
            grid_variants=grid_variants,
            aa_variant=aa_variant,
            placebo={"provided": True, "passed": True, "items": []},
            variant_by_name=variant_by_name,
            data_manifest=data_manifest,
            strat_dir=tmp_path,
            manifest_path="",
            start="2024-01-02",
            end="2026-03-28",
            initial_cash=100_000.0,
        )

        # every non-failing variant genuinely persisted through the real store
        completed = store.completed_variants()
        assert completed == {"incumbent", "cap12_drift00_topup05",
                              "cap20_drift00_topup05", "aa_resplit"}

        # the failure is recorded, not silently dropped
        error_row = store._conn.execute(
            "SELECT error FROM variant_results WHERE sweep_id = ? AND variant_name = ?",
            ("test-modal-sweep", "cap30_drift00_topup05"),
        ).fetchone()
        assert error_row is not None and error_row[0] == "canned failure"

        # verdicts were computed AND persisted via update_verdict (not just returned)
        winner_row = store._conn.execute(
            "SELECT tier3_ready, verdict_json FROM variant_results "
            "WHERE sweep_id = ? AND variant_name = ?",
            ("test-modal-sweep", "cap12_drift00_topup05"),
        ).fetchone()
        assert winner_row[0] == 1
        assert json.loads(winner_row[1])["tier3_ready"] is True

        loser_row = store._conn.execute(
            "SELECT tier3_ready FROM variant_results WHERE sweep_id = ? AND variant_name = ?",
            ("test-modal-sweep", "cap20_drift00_topup05"),
        ).fetchone()
        assert loser_row[0] == 0

        # per-seed and per-regime rows genuinely reached the store, not just variant_results
        seed_rows = store._conn.execute(
            "SELECT COUNT(*) FROM seed_metrics WHERE sweep_id = ? AND variant_name = ?",
            ("test-modal-sweep", "cap12_drift00_topup05"),
        ).fetchone()[0]
        assert seed_rows == len(FROZEN_SEEDS)

        # finalize() was actually called with real totals, not skipped
        sweep_row = store._conn.execute(
            "SELECT status, n_completed, n_failed, aa_sharpe_lift, aa_passed "
            "FROM sweep_runs WHERE sweep_id = ?",
            ("test-modal-sweep",),
        ).fetchone()
        assert sweep_row[0] == "partial"  # one canned failure
        assert sweep_row[1] == 4  # incumbent, winner, loser, aa
        assert sweep_row[2] == 1
        assert sweep_row[3] == pytest.approx(0.0, abs=1e-9)  # aa vs incumbent, identical sharpe
        assert sweep_row[4] == 1

        assert result["tier3_winners"] == ["cap12_drift00_topup05"]

    def test_resume_skips_already_completed_variants(self, tmp_path, variants, store):
        # Pre-populate the store as if the incumbent already ran in a prior attempt.
        store.insert_variant(
            "incumbent", "incumbent", "fp0",
            [_seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0) for s in FROZEN_SEEDS],
        )

        dispatched: list[str] = []

        class _RecordingExecutor(_FakeExecutor):
            def execute_batch(self, requests, *, on_result, on_error, max_concurrent=100):
                dispatched.extend(r.variant_name for r in requests)
                return super().execute_batch(
                    requests, on_result=on_result, on_error=on_error,
                    max_concurrent=max_concurrent,
                )

        canned = {
            "cap12_drift00_topup05": [
                _seed_row(s, sharpe=1.1, bull_calm_sharpe=1.1) for s in FROZEN_SEEDS
            ],
            "cap20_drift00_topup05": [
                _seed_row(s, sharpe=1.1, bull_calm_sharpe=1.1) for s in FROZEN_SEEDS
            ],
            "cap30_drift00_topup05": [
                _seed_row(s, sharpe=1.1, bull_calm_sharpe=1.1) for s in FROZEN_SEEDS
            ],
            "aa_resplit": [
                _seed_row(s, sharpe=1.0, bull_calm_sharpe=1.0) for s in FROZEN_SEEDS
            ],
        }
        executor = _RecordingExecutor(canned)
        grid_variants = [variants["incumbent"], variants["winner"],
                          variants["loser"], variants["failing"]]
        aa_variant = variants["aa"]
        variant_by_name = {v.name: v for v in grid_variants}
        variant_by_name[aa_variant.name] = aa_variant
        data_manifest = DataManifest(
            commit_id="deadbeef", timestamp="2026-01-01T00:00:00Z", files={}, total_bytes=0,
        )

        run_sweep(
            executor=executor, store=store, grid_variants=grid_variants,
            aa_variant=aa_variant, placebo={"provided": False, "passed": False, "items": []},
            variant_by_name=variant_by_name, data_manifest=data_manifest,
            strat_dir=tmp_path, manifest_path="", start="2024-01-02", end="2026-03-28",
            initial_cash=100_000.0,
        )

        # the already-completed incumbent must never be re-dispatched
        assert "incumbent" not in dispatched
        assert set(dispatched) == {
            "cap12_drift00_topup05", "cap20_drift00_topup05",
            "cap30_drift00_topup05", "aa_resplit",
        }



class TestStagePanelHistory:
    """Regression test for the missing-fundamentals-data Modal smoke-test
    failure (2026-07-08): SimAdapter._load_panel_history_cache() resolves
    panel_history_path relative to repo_root, but run_sweep_modal.py's
    local_paths dict never included a "data" label, so the fundamentals
    parquet was never synced to the Modal Volume. Every simulated day
    fail-closed on panel scoring until the remote task hit its 3600s
    timeout and was cancelled — a real, ~$0.95 failed cloud run.

    Round 2 (2026-07-08, same day): a second real smoke test with that fix
    in place confirmed the file-not-found error for
    alpha158_291_fundamental_dataset.parquet was gone, but
    panel_fundamentals_missing still fired every day via a SIBLING gap —
    renquant_pipeline's XGBoost fund-feature lookup reads a second,
    independent file (data/sec_fundamentals_daily.parquet) that was also
    never staged. stage_panel_history now covers both."""

    def test_default_panel_history_path_is_staged(self, tmp_path):
        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        src = data_dir / "alpha158_291_fundamental_dataset.parquet"
        src.write_bytes(b"fake parquet content")

        staging, _root_staging = stage_panel_history(repo_root, base_config={})

        staged = staging / "alpha158_291_fundamental_dataset.parquet"
        assert staged.exists(), "default panel_history_path must be staged"
        assert staged.read_bytes() == b"fake parquet content"

    def test_configured_panel_history_path_override_is_staged(self, tmp_path):
        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        src = data_dir / "custom_panel_history.parquet"
        src.write_bytes(b"custom content")

        staging, _root_staging = stage_panel_history(
            repo_root,
            base_config={"ranking": {"panel_scoring": {
                "panel_history_path": "data/custom_panel_history.parquet",
            }}},
        )

        staged = staging / "custom_panel_history.parquet"
        assert staged.exists()
        assert staged.read_bytes() == b"custom content"

    def test_staged_file_lands_at_the_path_simadapter_expects_on_the_volume(self, tmp_path):
        """End-to-end contract check against the real manifest builder:
        the staged file must appear in the sync manifest as
        "data/<filename>", so that with the Volume mounted at /data
        (see modal_executor.py), the remote path is /data/data/<filename>
        — exactly what SimAdapter's strategy_dir.parent.parent-relative
        resolution expects."""
        from renquant_orchestrator.cloud.sync_data import build_local_manifest

        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        (data_dir / "alpha158_291_fundamental_dataset.parquet").write_bytes(b"x")

        staging, _root_staging = stage_panel_history(repo_root, base_config={})
        manifest, _sources = build_local_manifest({"data": staging})

        assert "data/alpha158_291_fundamental_dataset.parquet" in manifest

    def test_sec_fundamentals_daily_is_also_staged_at_modern_path(self, tmp_path):
        """The XGBoost fund-feature sibling gap found in round 2 (fixed by
        staging under the "data" label, landing at /data/data/... once
        RENQUANT_DATA_ROOT=/data is pinned): still stage here too, in case
        any consumer genuinely uses renquant_pipeline's canonical
        _data_root_cached() resolver. Round 3's real smoke test proved the
        ACTUALLY-executing job_panel_scoring.py for this sweep is a stale
        bundled copy under kernel/panel_pipeline/ that does NOT use that
        resolver at all (see test_sec_fundamentals_daily_is_ALSO_staged_at_
        legacy_root_path below for the path that copy actually reads)."""
        from renquant_orchestrator.cloud.sync_data import build_local_manifest

        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        (data_dir / "alpha158_291_fundamental_dataset.parquet").write_bytes(b"x")
        (data_dir / "sec_fundamentals_daily.parquet").write_bytes(b"sec fund content")

        staging, root_staging = stage_panel_history(repo_root, base_config={})

        staged = staging / "sec_fundamentals_daily.parquet"
        assert staged.exists()
        assert staged.read_bytes() == b"sec fund content"

        manifest, _sources = build_local_manifest({"data": staging})
        assert "data/sec_fundamentals_daily.parquet" in manifest

    def test_sec_fundamentals_daily_is_also_staged_at_legacy_root_path(self, tmp_path):
        """Round 3 real-smoke-test finding: the file that ACTUALLY resolves
        panel_fundamentals_missing during this sweep is
        RenQuant/backtesting/renquant_104/kernel/panel_pipeline/job_panel_scoring.py
        (bundled into the Modal image via bundle_subrepos()'s kernel/ copy,
        imported by adapters/sim.py via `from kernel.panel_pipeline import
        PanelScorer` — a DIFFERENT top-level import path than
        renquant_pipeline.kernel.panel_pipeline). That bundled copy predates
        the _data_root.py refactor entirely and hardcodes
        `Path(__file__).resolve().parents[4]`, which for a file bundled at
        /data/app/kernel/panel_pipeline/job_panel_scoring.py resolves to "/"
        (the container filesystem root) — so it looks for the file at
        /data/sec_fundamentals_daily.parquet (ONE level shallower than the
        "data" label's /data/data/... path), completely independent of
        RENQUANT_DATA_ROOT. Confirmed by direct inspection of that bundled
        file's source — this is a genuine triple-impl divergence, not a
        caching/import-order bug in modal_app.py's env-var pin."""
        from renquant_orchestrator.cloud.sync_data import build_local_manifest

        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        (data_dir / "alpha158_291_fundamental_dataset.parquet").write_bytes(b"x")
        (data_dir / "sec_fundamentals_daily.parquet").write_bytes(b"sec fund content")

        staging, root_staging = stage_panel_history(repo_root, base_config={})

        assert root_staging is not None
        staged = root_staging / "sec_fundamentals_daily.parquet"
        assert staged.exists()
        assert staged.read_bytes() == b"sec fund content"

        # Empty label ("") means no path prefix — lands at Volume root,
        # i.e. absolute /data/sec_fundamentals_daily.parquet once mounted.
        manifest, _sources = build_local_manifest({"": root_staging})
        assert "sec_fundamentals_daily.parquet" in manifest
        assert "data/sec_fundamentals_daily.parquet" not in manifest

    def test_earnings_surprise_and_sentiment_dirs_staged_at_modern_path(self, tmp_path):
        """Round 7 finding: this sweep's actual XGBoost artifact (walk-forward
        manifest feature_cols) includes PEAD/SUE features (days_since_earnings,
        pead_signal, pead_quintile_rank, sue_signal, surprise_momentum,
        surprise_streak) and sentiment features — both job_panel_scoring.py
        implementations read data/earnings_surprise/ and
        data/news_sentiment_alpaca/ (per-ticker parquet dirs) for these,
        relative to the same repo/data_root as the fundamentals files. Neither
        dir was ever staged. Unlike the fund-feature check, this doesn't hard
        fail-closed (job_panel_scoring.py's feature-health check only warns on
        all-zero PEAD/SUE columns) — so it wouldn't cause another timeout, but
        would silently zero-impute these features, understating the sweep's
        real result quality."""
        from renquant_orchestrator.cloud.sync_data import build_local_manifest

        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        (data_dir / "alpha158_291_fundamental_dataset.parquet").write_bytes(b"x")
        earn_dir = data_dir / "earnings_surprise"
        earn_dir.mkdir()
        (earn_dir / "AAPL.parquet").write_bytes(b"earnings data")
        sent_dir = data_dir / "news_sentiment_alpaca"
        sent_dir.mkdir()
        (sent_dir / "AAPL.parquet").write_bytes(b"sentiment data")

        staging, _root_staging = stage_panel_history(repo_root, base_config={})

        assert (staging / "earnings_surprise" / "AAPL.parquet").read_bytes() == b"earnings data"
        assert (staging / "news_sentiment_alpaca" / "AAPL.parquet").read_bytes() == b"sentiment data"

        manifest, _sources = build_local_manifest({"data": staging})
        assert "data/earnings_surprise/AAPL.parquet" in manifest
        assert "data/news_sentiment_alpaca/AAPL.parquet" in manifest

    def test_earnings_surprise_and_sentiment_dirs_staged_at_legacy_root_path(self, tmp_path):
        """Same two dirs must ALSO land at the Volume root (no "data" prefix)
        for the stale bundled kernel/panel_pipeline/job_panel_scoring.py
        consumer, whose parents[4]-based repo resolves to "/" inside the
        container — same rationale as sec_fundamentals_daily.parquet's
        legacy-root staging above."""
        from renquant_orchestrator.cloud.sync_data import build_local_manifest

        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        (data_dir / "alpha158_291_fundamental_dataset.parquet").write_bytes(b"x")
        earn_dir = data_dir / "earnings_surprise"
        earn_dir.mkdir()
        (earn_dir / "AAPL.parquet").write_bytes(b"earnings data")
        sent_dir = data_dir / "news_sentiment_alpaca"
        sent_dir.mkdir()
        (sent_dir / "AAPL.parquet").write_bytes(b"sentiment data")

        _staging, root_staging = stage_panel_history(repo_root, base_config={})

        assert (root_staging / "earnings_surprise" / "AAPL.parquet").read_bytes() == b"earnings data"
        assert (root_staging / "news_sentiment_alpaca" / "AAPL.parquet").read_bytes() == b"sentiment data"

        manifest, _sources = build_local_manifest({"": root_staging})
        assert "earnings_surprise/AAPL.parquet" in manifest
        assert "news_sentiment_alpaca/AAPL.parquet" in manifest
        assert "data/earnings_surprise/AAPL.parquet" not in manifest

    def test_missing_earnings_surprise_dir_does_not_raise(self, tmp_path):
        """No local earnings_surprise/ or news_sentiment_alpaca/ dirs (e.g. a
        dev machine that only has the fundamentals files) must not crash
        sync — same fail-soft contract as the missing-file case below."""
        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        (data_dir / "alpha158_291_fundamental_dataset.parquet").write_bytes(b"x")

        staging, root_staging = stage_panel_history(repo_root, base_config={})

        assert not (staging / "earnings_surprise").exists()
        assert not (root_staging / "earnings_surprise").exists()

    def test_missing_source_file_does_not_raise_but_yields_empty_staging(self, tmp_path):
        """No local fundamentals files at all (e.g. a dev machine without
        the source datasets) must not crash sync — it should stage nothing
        and let the caller's own warning explain the resulting remote
        failure, rather than raising here."""
        repo_root = tmp_path  # no data/ dir created at all

        staging, root_staging = stage_panel_history(repo_root, base_config={})

        assert staging.exists()
        assert list(staging.iterdir()) == []
        assert root_staging.exists()
        assert list(root_staging.iterdir()) == []

    def test_one_missing_file_does_not_block_staging_the_other(self, tmp_path):
        """The two files are independent — if only one source exists
        locally, it must still be staged rather than the whole function
        bailing out because its sibling is absent."""
        repo_root = tmp_path
        data_dir = repo_root / "data"
        data_dir.mkdir()
        (data_dir / "sec_fundamentals_daily.parquet").write_bytes(b"sec only")
        # alpha158_291_fundamental_dataset.parquet deliberately absent

        staging, root_staging = stage_panel_history(repo_root, base_config={})

        assert (staging / "sec_fundamentals_daily.parquet").exists()
        assert not (staging / "alpha158_291_fundamental_dataset.parquet").exists()
        assert (root_staging / "sec_fundamentals_daily.parquet").exists()
