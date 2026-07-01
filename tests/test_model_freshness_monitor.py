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


def test_trained_date_never_certifies_freshness_unknown_failclosed(tmp_path: Path) -> None:
    # A fresh trained_date with NO binding data cutoff must NOT read as freshness.
    # This is the #210 incident: retrain-today-on-stale-data -> age 0 -> "healthy".
    # It must fail closed to a DISTINCT unknown state, not fall back to trained_date.
    art = _write_json(tmp_path / "prod.json", {"trained_date": "2026-06-14"})
    fresh = mod.read_artifact_freshness("prod", art, AS_OF)
    assert fresh.present is True
    assert fresh.binding_field is None
    assert fresh.binding_cutoff is None
    assert fresh.age_days is None
    assert fresh.tier == mod.TIER_UNKNOWN
    assert fresh.tier != mod.TIER_BREACH  # reported SEPARATELY from "cutoff old"
    assert "unknown" in fresh.detail
    # trained_date is echoed as informational context only, never as a freshness axis.
    assert "informational" in fresh.detail
    # unknown fails closed at breach severity for exit code / alerting.
    assert mod._TIER_EXIT_CODE[fresh.tier] == 3


def test_unknown_outranks_breach_but_exits_breach_severity() -> None:
    # unknown is the headline worst (you can't even tell how stale it is)...
    assert mod.worst_tier([mod.TIER_BREACH, mod.TIER_UNKNOWN]) == mod.TIER_UNKNOWN
    assert mod.worst_tier([mod.TIER_UNKNOWN, mod.TIER_HEALTHY]) == mod.TIER_UNKNOWN
    # ...but both fail closed to exit code 3.
    assert mod._TIER_EXIT_CODE[mod.TIER_UNKNOWN] == mod._TIER_EXIT_CODE[mod.TIER_BREACH] == 3


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    fresh = mod.read_artifact_freshness("prod", tmp_path / "nope.json", AS_OF)
    assert fresh.present is False
    assert fresh.tier == mod.TIER_BREACH
    assert "missing" in fresh.detail


def test_no_path_fails_closed() -> None:
    fresh = mod.read_artifact_freshness("shadow", None, AS_OF)
    assert fresh.present is False
    assert fresh.tier == mod.TIER_BREACH


def test_cutoffless_artifact_fails_closed_unknown(tmp_path: Path) -> None:
    # Present artifact, no cutoff field AND no trained_date -> unknown (fail closed).
    art = _write_json(tmp_path / "bad.json", {"kind": "xgb"})
    fresh = mod.read_artifact_freshness("prod", art, AS_OF)
    assert fresh.present is True
    assert fresh.tier == mod.TIER_UNKNOWN
    assert fresh.age_days is None
    assert mod._TIER_EXIT_CODE[fresh.tier] == 3


# --------------------------------------------------------------------------- #
# Future / look-ahead cutoff: fail closed (windows bounded on BOTH sides, #211)
# --------------------------------------------------------------------------- #
def test_future_cutoff_fails_closed_not_healthy(tmp_path: Path) -> None:
    # A cutoff LATER than 'now' yields a negative age; it must be rejected, never
    # accepted as healthy (a replay at June 1 must not consume a June 15 cutoff).
    art = _write_json(tmp_path / "future.json", {"data_cutoff_date": "2026-07-15"})
    fresh = mod.read_artifact_freshness("prod", art, AS_OF)  # AS_OF = 2026-06-30
    assert fresh.present is True
    assert fresh.binding_cutoff == "2026-07-15"
    assert fresh.age_days == -15  # negative == future
    assert fresh.tier == mod.TIER_BREACH  # fail closed, NOT healthy
    assert "future cutoff" in fresh.detail
    assert "look-ahead" in fresh.detail


def test_future_shadow_cutoff_fails_closed(tmp_path: Path) -> None:
    art = _write_json(tmp_path / "shadow.json", {"effective_selection_cutoff_date": "2026-08-01"})
    fresh = mod.read_artifact_freshness("shadow", art, AS_OF, policy=mod.SHADOW_POLICY)
    assert fresh.tier == mod.TIER_BREACH
    assert "future cutoff" in fresh.detail


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
        # A real binding DATA cutoff (trained_date alone no longer certifies freshness).
        {"kind": "xgb", "trained_date": "2026-06-30", "data_cutoff_date": prod_cutoff},
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
    # prod panel 16d old (binding DATA cutoff) -> warn dominates a healthy rest.
    assert payload["worst_tier"] == mod.TIER_WARN
    assert rc == 1
    assert payload["prod_panel"]["binding_field"] == "data_cutoff_date"
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


def test_main_cli_future_cutoff_rejected(tmp_path: Path, capsys) -> None:
    # CLI regression (point 2): a cutoff LATER than --as-of must fail closed as a
    # look-ahead, never accepted as a healthy negative age. The PR's "windows bounded
    # on both sides" claim is only true for cutoff evaluation once this passes.
    fx = _build_fixture(tmp_path, prod_cutoff="2026-07-15", shadow_cutoff="2026-06-25", ticker_cutoff="2026-06-25")
    argv = [
        "--as-of", "2026-06-30",
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--watchlist", "AAPL,MSFT",
        "--quiet", "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["prod_panel"]["age_days"] == -15  # 15d in the future
    assert payload["prod_panel"]["tier"] == mod.TIER_BREACH  # rejected, not healthy
    assert "future cutoff" in payload["prod_panel"]["detail"]
    assert payload["worst_tier"] == mod.TIER_BREACH
    assert rc == 3


def test_main_cli_missing_cutoff_is_unknown_failclosed(tmp_path: Path, capsys) -> None:
    # CLI regression (point 1): a prod panel with only trained_date (no binding data
    # cutoff) must report unknown and exit at breach severity, never certify healthy.
    _write_policy(tmp_path / "models", "AAPL", live_train_end="2026-06-25")
    prod = _write_json(tmp_path / "prod.json", {"kind": "xgb", "trained_date": "2026-06-30"})
    shadow_cfg = _write_json(
        tmp_path / "strategy_config.shadow.json",
        {"ranking": {"panel_scoring": {"kind": "xgb", "artifact_path": "prod.json"}}},
    )
    argv = [
        "--as-of", "2026-06-30",
        "--models-dir", str(tmp_path / "models"),
        "--prod-panel", str(prod),
        "--shadow-config", str(shadow_cfg),
        "--watchlist", "AAPL",
        "--quiet", "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["prod_panel"]["tier"] == mod.TIER_UNKNOWN
    assert payload["prod_panel"]["age_days"] is None
    assert payload["worst_tier"] == mod.TIER_UNKNOWN  # headline is distinct from breach
    assert rc == 3  # but exits at breach severity (fail closed)


# --------------------------------------------------------------------------- #
# Shadow population uses RFC #212's policy (35d + promote status), not prod 28d
# --------------------------------------------------------------------------- #
def test_shadow_policy_looser_than_prod_at_30d(tmp_path: Path) -> None:
    # Same 30d-stale artifact: prod policy BREACHes (>28d), shadow policy is only WARN.
    art = _write_json(tmp_path / "s.json", {"effective_selection_cutoff_date": "2026-05-31"})
    prod = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.PROD_FAST_POLICY)
    shadow = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.SHADOW_POLICY)
    assert prod.age_days == shadow.age_days == 30
    assert prod.tier == mod.TIER_BREACH   # prod 28d fast ceiling
    assert shadow.tier == mod.TIER_WARN   # shadow 35d ceiling (RFC #212 §3.2)


def test_shadow_policy_breach_only_past_35d(tmp_path: Path) -> None:
    art = _write_json(tmp_path / "s.json", {"effective_selection_cutoff_date": "2026-05-25"})  # 36d
    shadow = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.SHADOW_POLICY)
    assert shadow.age_days == 36
    assert shadow.tier == mod.TIER_BREACH


def test_shadow_non_fresh_label_forces_breach(tmp_path: Path) -> None:
    # RFC #212 §3.2: a served pin labeled non-fresh is breach even with a fresh age.
    art = _write_json(
        tmp_path / "s.json",
        {"effective_selection_cutoff_date": "2026-06-27", "non_fresh": True},
    )
    shadow = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.SHADOW_POLICY)
    assert shadow.age_days == 3  # healthy on age alone
    assert shadow.non_fresh is True
    assert shadow.tier == mod.TIER_BREACH
    assert "non-fresh" in shadow.detail


def test_shadow_unvalidated_promote_caps_at_escalate(tmp_path: Path) -> None:
    # RFC #212 §3.2: a fresh age does not certify healthy without a validated promote.
    art = _write_json(
        tmp_path / "s.json",
        {"effective_selection_cutoff_date": "2026-06-27", "validated_promote": False},
    )
    shadow = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.SHADOW_POLICY)
    assert shadow.promote_validated is False
    assert shadow.tier == mod.TIER_ESCALATE  # not healthy despite 3d age
    assert "promote not validated" in shadow.detail


def test_shadow_validated_promote_allows_healthy(tmp_path: Path) -> None:
    art = _write_json(
        tmp_path / "s.json",
        {"effective_selection_cutoff_date": "2026-06-27", "validated_promote": True},
    )
    shadow = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.SHADOW_POLICY)
    assert shadow.promote_validated is True
    assert shadow.tier == mod.TIER_HEALTHY
    assert "validated promote" in shadow.detail


def test_prod_policy_ignores_promote_status(tmp_path: Path) -> None:
    # The prod fast axis has no promote gate: promote fields are not consulted.
    art = _write_json(
        tmp_path / "p.json",
        {"data_cutoff_date": "2026-06-27", "validated_promote": False, "non_fresh": True},
    )
    prod = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.PROD_FAST_POLICY)
    assert prod.promote_validated is None
    assert prod.non_fresh is False
    assert prod.tier == mod.TIER_HEALTHY  # 3d age, no promote gate applied


def test_main_cli_shadow_uses_its_own_policy(tmp_path: Path, capsys) -> None:
    # Full pipeline: a 30d-stale shadow is WARN under its 35d policy, NOT breach under
    # the prod 28d scalar. Per-population thresholds are explicit in the JSON.
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-25", shadow_cutoff="2026-05-31", ticker_cutoff="2026-06-25")
    argv = [
        "--as-of", "2026-06-30",
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--watchlist", "AAPL,MSFT",
        "--quiet", "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["shadow_panel"]["age_days"] == 30
    assert payload["shadow_panel"]["tier"] == mod.TIER_WARN
    assert payload["worst_tier"] == mod.TIER_WARN
    assert rc == 1
    assert payload["thresholds"]["shadow"]["breach_days"] == 35
    assert payload["thresholds"]["fast_axis"]["breach_days"] == 28
    assert payload["thresholds"]["shadow"]["require_validated_promote"] is True
