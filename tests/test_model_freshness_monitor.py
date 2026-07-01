from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from renquant_orchestrator import model_freshness_monitor as mod


AS_OF = datetime(2026, 6, 30, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_policy(models_dir: Path, ticker: str, **fields) -> Path:
    return _write_json(models_dir / ticker / f"{ticker}-policy-metadata.json", fields)


# --------------------------------------------------------------------------- #
# Pure tiering (bounded on both sides, deterministic)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "age, expected",
    [
        (0, mod.TIER_HEALTHY),
        (14, mod.TIER_HEALTHY),
        (15, mod.TIER_WARN),
        (21, mod.TIER_WARN),
        (22, mod.TIER_ESCALATE),
        (28, mod.TIER_ESCALATE),
        (29, mod.TIER_BREACH),
        (61, mod.TIER_BREACH),
        (None, mod.TIER_BREACH),  # no cutoff -> fail closed
    ],
)
def test_tier_for_age_boundaries(age, expected) -> None:
    assert mod.tier_for_age(age) == expected


def test_worst_tier_picks_highest_rank() -> None:
    assert mod.worst_tier([mod.TIER_HEALTHY, mod.TIER_BREACH, mod.TIER_WARN]) == mod.TIER_BREACH
    assert mod.worst_tier([mod.TIER_HEALTHY, mod.TIER_HEALTHY]) == mod.TIER_HEALTHY


def test_pipeline_shape() -> None:
    pipeline = mod.build_pipeline()
    assert pipeline.name == "model-freshness-monitor"
    assert [type(job).__name__ for job in pipeline.jobs] == [
        "ResolveWatchlistJob",
        "ComputeFreshnessJob",
        "FreshnessAlertJob",
    ]


# --------------------------------------------------------------------------- #
# read_artifact_freshness: binding data cutoff, not trained_date
# --------------------------------------------------------------------------- #
def test_data_cutoff_binds_over_fresh_trained_date(tmp_path: Path) -> None:
    # A fresh trained_date over stale data is NOT fresh (design §2).
    art = _write_json(
        tmp_path / "shadow.json",
        {"trained_date": "2026-06-29", "effective_selection_cutoff_date": "2026-05-20"},
    )
    fresh = mod.read_artifact_freshness("shadow", art, AS_OF)
    assert fresh.present is True
    assert fresh.binding_field == "effective_selection_cutoff_date"
    assert fresh.binding_cutoff == "2026-05-20"
    assert fresh.age_days == 41
    assert fresh.tier == mod.TIER_BREACH  # data is stale despite a 1d-old trained_date


def test_selection_cutoff_preferred_over_train_cutoff(tmp_path: Path) -> None:
    art = _write_json(
        tmp_path / "a.json",
        {
            "trained_date": "2026-05-22",
            "effective_train_cutoff_date": "2024-11-13",
            "effective_selection_cutoff_date": "2026-06-20",
        },
    )
    fresh = mod.read_artifact_freshness("a", art, AS_OF)
    assert fresh.binding_field == "effective_selection_cutoff_date"
    assert fresh.age_days == 10
    assert fresh.tier == mod.TIER_HEALTHY


def test_trained_date_fallback_when_no_cutoff(tmp_path: Path) -> None:
    art = _write_json(tmp_path / "prod.json", {"trained_date": "2026-06-14"})
    fresh = mod.read_artifact_freshness("prod", art, AS_OF)
    assert fresh.binding_field == "trained_date"
    assert fresh.age_days == 16
    assert fresh.tier == mod.TIER_WARN
    assert "trained_date fallback" in fresh.detail


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    fresh = mod.read_artifact_freshness("prod", tmp_path / "nope.json", AS_OF)
    assert fresh.present is False
    assert fresh.tier == mod.TIER_BREACH
    assert "missing" in fresh.detail


def test_no_path_fails_closed() -> None:
    fresh = mod.read_artifact_freshness("shadow", None, AS_OF)
    assert fresh.present is False
    assert fresh.tier == mod.TIER_BREACH


def test_cutoffless_artifact_fails_closed(tmp_path: Path) -> None:
    art = _write_json(tmp_path / "bad.json", {"kind": "xgb"})
    fresh = mod.read_artifact_freshness("prod", art, AS_OF)
    assert fresh.present is True
    assert fresh.tier == mod.TIER_BREACH
    assert fresh.age_days is None


# --------------------------------------------------------------------------- #
# Shadow artifact resolution (blob -> sidecar; json direct)
# --------------------------------------------------------------------------- #
def test_shadow_resolves_pt_sidecar(tmp_path: Path) -> None:
    cfg = _write_json(
        tmp_path / "strategy_config.shadow.json",
        {"ranking": {"panel_scoring": {"kind": "hf_patchtst", "artifact_path": "artifacts/seed_44/model.pt"}}},
    )
    resolved = mod.resolve_shadow_artifact_path(cfg)
    assert resolved == (tmp_path / "artifacts" / "seed_44" / "model.pt.metadata.json").resolve()


def test_shadow_resolves_json_directly(tmp_path: Path) -> None:
    cfg = _write_json(
        tmp_path / "strategy_config.shadow.json",
        {"ranking": {"panel_scoring": {"kind": "xgb", "artifact_path": "artifacts/prod/panel.json"}}},
    )
    resolved = mod.resolve_shadow_artifact_path(cfg)
    assert resolved == (tmp_path / "artifacts" / "prod" / "panel.json").resolve()


def test_shadow_missing_config_returns_none(tmp_path: Path) -> None:
    assert mod.resolve_shadow_artifact_path(tmp_path / "absent.json") is None


# --------------------------------------------------------------------------- #
# Tournament coverage + age spread
# --------------------------------------------------------------------------- #
def test_tournament_uses_live_train_end_over_trained_date(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_policy(models, "AAPL", trained_date="2026-06-30", live_train_end="2026-06-14")
    tf = mod.read_tournament_freshness(models, ["AAPL"], AS_OF)
    assert tf.per_ticker[0].binding_field == "live_train_end"
    assert tf.per_ticker[0].age_days == 16
    assert tf.tier == mod.TIER_WARN


def test_tournament_coverage_and_ages_and_missing(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_policy(models, "AAPL", live_train_end="2026-06-20")  # 10d healthy
    _write_policy(models, "MSFT", live_train_end="2026-06-06")  # 24d escalate
    # NVDA intentionally absent -> fail closed
    tf = mod.read_tournament_freshness(models, ["AAPL", "MSFT", "NVDA"], AS_OF)
    assert tf.n_expected == 3
    assert tf.n_present == 2
    assert tf.n_missing == 1
    assert tf.missing == ["NVDA"]
    assert tf.min_age_days == 10
    assert tf.max_age_days == 24
    assert tf.median_age_days == 17  # median(10, 24)
    assert tf.tier == mod.TIER_BREACH  # missing NVDA fails closed


def test_tournament_all_present_healthy(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_policy(models, "AAPL", live_train_end="2026-06-25")
    _write_policy(models, "MSFT", live_train_end="2026-06-20")
    tf = mod.read_tournament_freshness(models, ["AAPL", "MSFT"], AS_OF)
    assert tf.n_missing == 0
    assert tf.tier == mod.TIER_HEALTHY


def test_empty_watchlist_fails_closed(tmp_path: Path) -> None:
    tf = mod.read_tournament_freshness(tmp_path / "models", [], AS_OF)
    assert tf.tier == mod.TIER_BREACH
    assert "empty watchlist" in tf.detail


# --------------------------------------------------------------------------- #
# End-to-end pipeline + main()
# --------------------------------------------------------------------------- #
def _build_fixture(tmp_path: Path, *, prod_cutoff: str, shadow_cutoff: str, ticker_cutoff: str) -> dict:
    models = tmp_path / "models"
    _write_policy(models, "AAPL", trained_date="2026-06-30", live_train_end=ticker_cutoff)
    _write_policy(models, "MSFT", trained_date="2026-06-30", live_train_end=ticker_cutoff)
    prod = _write_json(
        tmp_path / "artifacts" / "prod" / "panel-ltr.alpha158_fund.json",
        {"kind": "xgb", "trained_date": prod_cutoff},
    )
    _write_json(
        tmp_path / "shadow" / "seed_44" / "model.pt.metadata.json",
        {"kind": "hf_patchtst", "trained_date": "2026-05-22", "effective_selection_cutoff_date": shadow_cutoff},
    )
    shadow_cfg = _write_json(
        tmp_path / "strategy_config.shadow.json",
        {"ranking": {"panel_scoring": {"kind": "hf_patchtst", "artifact_path": "shadow/seed_44/model.pt"}}},
    )
    return {"models": models, "prod": prod, "shadow_cfg": shadow_cfg}


def test_pipeline_all_healthy_exit_zero(tmp_path: Path) -> None:
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-25", shadow_cutoff="2026-06-25", ticker_cutoff="2026-06-25")
    ctx = mod.ModelFreshnessContext(
        now=AS_OF,
        repo_root=tmp_path,
        github_root=tmp_path,
        models_dir=fx["models"],
        prod_panel_path=fx["prod"],
        shadow_config_path=fx["shadow_cfg"],
        strategy_config_path=tmp_path / "absent.json",
        explicit_watchlist=["AAPL", "MSFT"],
        quiet=True,
    )
    result = mod.build_pipeline().run(ctx)
    assert result.ok is True
    assert ctx.worst_tier == mod.TIER_HEALTHY
    assert ctx.exit_code == 0
    assert ctx.alert_title is None


def test_pipeline_worst_tier_is_breach(tmp_path: Path) -> None:
    # Tournament + prod healthy, but shadow data cutoff is 41d stale -> breach dominates.
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-25", shadow_cutoff="2026-05-20", ticker_cutoff="2026-06-25")
    ctx = mod.ModelFreshnessContext(
        now=AS_OF,
        repo_root=tmp_path,
        github_root=tmp_path,
        models_dir=fx["models"],
        prod_panel_path=fx["prod"],
        shadow_config_path=fx["shadow_cfg"],
        strategy_config_path=tmp_path / "absent.json",
        explicit_watchlist=["AAPL", "MSFT"],
        quiet=True,
    )
    mod.build_pipeline().run(ctx)
    assert ctx.shadow_panel.age_days == 41
    assert ctx.worst_tier == mod.TIER_BREACH
    assert ctx.exit_code == 3
    assert ctx.alert_title == "RenQuant 104 model freshness BREACH"
    assert ctx.alert_body == ctx.summary


def test_main_json_is_deterministic_via_as_of(tmp_path: Path, capsys) -> None:
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-14", shadow_cutoff="2026-06-25", ticker_cutoff="2026-06-25")
    argv = [
        "--as-of", "2026-06-30",
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--watchlist", "AAPL,MSFT",
        "--quiet",
        "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert rc == payload["exit_code"]
    # prod panel 16d old (trained_date fallback) -> warn dominates a healthy rest.
    assert payload["worst_tier"] == mod.TIER_WARN
    assert rc == 1
    assert payload["prod_panel"]["binding_field"] == "trained_date"
    assert payload["prod_panel"]["age_days"] == 16
    assert payload["tournament"]["n_present"] == 2
    assert payload["watchlist_source"] == "explicit"


def test_main_as_of_bounds_both_sides(tmp_path: Path, capsys) -> None:
    # Same fixture, two different injected 'now' values -> different tiers (no wall clock).
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-20", shadow_cutoff="2026-06-20", ticker_cutoff="2026-06-20")
    base = [
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--watchlist", "AAPL,MSFT",
        "--quiet", "--json",
    ]
    rc_near = mod.main(["--as-of", "2026-06-27", *base])  # 7d -> healthy
    near = json.loads(capsys.readouterr().out)
    rc_far = mod.main(["--as-of", "2026-08-01", *base])  # 42d -> breach
    far = json.loads(capsys.readouterr().out)
    assert (rc_near, near["worst_tier"]) == (0, mod.TIER_HEALTHY)
    assert (rc_far, far["worst_tier"]) == (3, mod.TIER_BREACH)
