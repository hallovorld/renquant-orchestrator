from __future__ import annotations

import hashlib
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


def _write_pt(path: Path, content: bytes = b"patchtst-weights") -> str:
    """Write a served ``.pt`` blob and return its sha256 (the receipt digest)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _promote_report(
    *,
    promoted_pin: str,
    candidate_sha256: str | None,
    data_cutoff: str = "2026-06-25",
    gate_version: str = "wf_gate@v3",
    rc: int | None = 0,
    fresh: bool = True,
    gates_ok: bool = True,
    n_gates: int = 2,
    labeled_non_fresh: bool = False,
) -> dict:
    """A #419 ``PromoteReport`` sidecar (the persisted promotion receipt schema)."""
    report = {
        "promoted_pin": promoted_pin,
        "candidate_pt": promoted_pin,
        "gate_version": gate_version,
        "rc": rc,
        "fresh": fresh,
        "labeled_non_fresh": labeled_non_fresh,
        "gates": [{"name": f"g{i}", "ok": gates_ok} for i in range(n_gates)],
        "source_verdicts": [{"source": "alpha158", "data_cutoff": data_cutoff}],
        "promoted_at": "2026-06-30T00:00:00Z",
    }
    if candidate_sha256 is not None:
        report["candidate_sha256"] = candidate_sha256
    return report


def _write_receipt(receipt_dir: Path, report: dict, *, stamp: str = "2026-06-30T00-00-00Z") -> Path:
    """Persist one promotion receipt under ``receipt_dir`` (newest == lexicographic max)."""
    receipt_dir.mkdir(parents=True, exist_ok=True)
    return _write_json(receipt_dir / f"{stamp}.json", report)


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
    # The wired promote gate (RFC #212 §3.2) needs a persisted, pin-bound receipt for the
    # shadow age tier to stand; otherwise the shadow fails closed to escalate. Write the
    # served .pt and a validated receipt bound to it (repo_root defaults to tmp_path).
    pin_rel = "shadow/seed_44/model.pt"
    sha = _write_pt(tmp_path / pin_rel)
    receipt_dir = mod.default_promote_receipt_dir(tmp_path)
    _write_receipt(receipt_dir, _promote_report(promoted_pin=pin_rel, candidate_sha256=sha))
    return {"models": models, "prod": prod, "shadow_cfg": shadow_cfg, "receipt_dir": receipt_dir}


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
        "--repo-root", str(tmp_path),
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
    # shadow is fresh + validated-promote (receipt bound), so prod panel 16d old (binding
    # DATA cutoff) -> warn dominates a healthy rest.
    assert payload["shadow_panel"]["promotion_status"] == mod.PROMOTE_OK
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
        "--repo-root", str(tmp_path),
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
        "--repo-root", str(tmp_path),
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
        "--repo-root", str(tmp_path),
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


def test_read_artifact_freshness_no_longer_reads_sidecar_promote_booleans(tmp_path: Path) -> None:
    # The pure age reader NEVER trusts a free sidecar boolean (spoofable/stale, #419);
    # promote status is decided by apply_promotion_gate from a persisted receipt only.
    art = _write_json(
        tmp_path / "s.json",
        {"effective_selection_cutoff_date": "2026-06-27", "validated_promote": True, "non_fresh": True},
    )
    shadow = mod.read_artifact_freshness("x", art, AS_OF, policy=mod.SHADOW_POLICY)
    assert shadow.promote_validated is None  # not read here
    assert shadow.non_fresh is False         # not read here
    assert shadow.tier == mod.TIER_HEALTHY   # 3d age, gate not applied by the reader


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


# --------------------------------------------------------------------------- #
# Shadow promote RECEIPT gate (umbrella #419 / RFC #212 §5): pin-bound, fail-closed.
# A fresh age never certifies healthy without a persisted, bound, validated receipt.
# --------------------------------------------------------------------------- #
def _shadow_setup(
    tmp_path: Path,
    *,
    shadow_cutoff: str = "2026-06-27",
    pin_rel: str = "shadow/seed_44/model.pt",
    pt_content: bytes = b"patchtst-weights",
) -> dict:
    sidecar = _write_json(
        tmp_path / (pin_rel + ".metadata.json"),
        {"kind": "hf_patchtst", "effective_selection_cutoff_date": shadow_cutoff},
    )
    sha = _write_pt(tmp_path / pin_rel, pt_content)
    cfg = _write_json(
        tmp_path / "strategy_config.shadow.json",
        {"ranking": {"panel_scoring": {"kind": "hf_patchtst", "artifact_path": pin_rel}}},
    )
    return {
        "sidecar": sidecar,
        "pin_rel": pin_rel,
        "sha": sha,
        "cfg": cfg,
        "served_pt": tmp_path / pin_rel,
        "receipt_dir": mod.default_promote_receipt_dir(tmp_path),
    }


def _apply_gate(tmp_path: Path, setup: dict) -> mod.ArtifactFreshness:
    fresh = mod.read_artifact_freshness("shadow-panel", setup["sidecar"], AS_OF, policy=mod.SHADOW_POLICY)
    return mod.apply_promotion_gate(
        fresh,
        receipt_dir=setup["receipt_dir"],
        served_pt=mod._blob_from_freshness_path(setup["sidecar"]),
        config_path=setup["cfg"],
        repo_root=tmp_path,
    )


def test_promote_receipt_validated_allows_age_tier(tmp_path: Path) -> None:
    setup = _shadow_setup(tmp_path)
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=setup["sha"]),
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_OK
    assert fresh.promote_validated is True
    assert fresh.tier == mod.TIER_HEALTHY  # 3d age stands
    assert fresh.promotion_receipt_path is not None


def test_promote_missing_receipt_fails_closed_escalate(tmp_path: Path) -> None:
    # THE production path today: #419 writes no receipt yet -> must NOT read healthy.
    setup = _shadow_setup(tmp_path)  # no receipt written
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_MISSING
    assert fresh.promote_validated is False
    assert fresh.tier == mod.TIER_ESCALATE  # age was healthy; gate raises to escalate
    assert "no promotion receipt" in fresh.detail


def test_promote_unreadable_receipt_escalate(tmp_path: Path) -> None:
    setup = _shadow_setup(tmp_path)
    setup["receipt_dir"].mkdir(parents=True, exist_ok=True)
    (setup["receipt_dir"] / "2026-06-30T00-00-00Z.json").write_text("{not json", encoding="utf-8")
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_UNREADABLE
    assert fresh.tier == mod.TIER_ESCALATE


def test_promote_unbound_receipt_escalate(tmp_path: Path) -> None:
    # A receipt for a DIFFERENT (superseded) pin must not certify the served pin.
    setup = _shadow_setup(tmp_path)
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin="shadow/seed_99/other.pt", candidate_sha256=setup["sha"]),
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_UNBOUND
    assert fresh.tier == mod.TIER_ESCALATE
    assert "does not bind served pin" in fresh.detail


def test_promote_incomplete_receipt_escalate(tmp_path: Path) -> None:
    # A partial receipt (a free boolean without the binding evidence) is not trusted.
    setup = _shadow_setup(tmp_path)
    report = _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=setup["sha"])
    report.pop("gate_version")
    _write_receipt(setup["receipt_dir"], report)
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_INCOMPLETE
    assert fresh.tier == mod.TIER_ESCALATE
    assert "gate_version" in fresh.detail


def test_promote_missing_digest_when_required_escalate(tmp_path: Path) -> None:
    setup = _shadow_setup(tmp_path)
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=None),
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_INCOMPLETE
    assert "candidate_sha256" in fresh.detail


def test_promote_non_fresh_receipt_breach(tmp_path: Path) -> None:
    setup = _shadow_setup(tmp_path)
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=setup["sha"], labeled_non_fresh=True),
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_NON_FRESH
    assert fresh.non_fresh is True
    assert fresh.tier == mod.TIER_BREACH  # non-fresh is actively bad, not just uncertain


def test_promote_validation_failed_breach(tmp_path: Path) -> None:
    setup = _shadow_setup(tmp_path)
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=setup["sha"], rc=1, gates_ok=False),
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_VALIDATION_FAILED
    assert fresh.tier == mod.TIER_BREACH


def test_promote_digest_mismatch_breach(tmp_path: Path) -> None:
    # The served .pt bytes were replaced out of band after the receipt was written.
    setup = _shadow_setup(tmp_path)
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256="deadbeef" * 8),
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_DIGEST_MISMATCH
    assert fresh.tier == mod.TIER_BREACH
    assert "candidate_sha256" in fresh.detail


def test_promote_gate_only_raises_severity(tmp_path: Path) -> None:
    # An already-breach age (40d) stays breach even with a validated receipt: the gate
    # only ever RAISES severity, it never launders a stale pin back to healthy.
    setup = _shadow_setup(tmp_path, shadow_cutoff="2026-05-21")  # 40d > 35d shadow ceiling
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=setup["sha"]),
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.age_days == 40
    assert fresh.promotion_status == mod.PROMOTE_OK
    assert fresh.tier == mod.TIER_BREACH


def test_promote_latest_receipt_wins(tmp_path: Path) -> None:
    # Two receipts: the newest (lexicographic-max stamp) is authoritative.
    setup = _shadow_setup(tmp_path)
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=setup["sha"], labeled_non_fresh=True),
        stamp="2026-06-28T00-00-00Z",  # older: non-fresh
    )
    _write_receipt(
        setup["receipt_dir"],
        _promote_report(promoted_pin=setup["pin_rel"], candidate_sha256=setup["sha"]),
        stamp="2026-06-30T00-00-00Z",  # newer: validated
    )
    fresh = _apply_gate(tmp_path, setup)
    assert fresh.promotion_status == mod.PROMOTE_OK
    assert fresh.tier == mod.TIER_HEALTHY


def test_main_cli_shadow_uses_its_own_policy(tmp_path: Path, capsys) -> None:
    # Full pipeline: a 30d-stale shadow is WARN under its 35d policy, NOT breach under
    # the prod 28d scalar. Per-population thresholds are explicit in the JSON.
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-25", shadow_cutoff="2026-05-31", ticker_cutoff="2026-06-25")
    argv = [
        "--as-of", "2026-06-30",
        "--repo-root", str(tmp_path),
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--watchlist", "AAPL,MSFT",
        "--quiet", "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["shadow_panel"]["age_days"] == 30
    # 30d age is WARN under the 35d shadow ceiling, and the validated receipt lets the
    # age tier stand (does not force it healthy nor escalate it).
    assert payload["shadow_panel"]["promotion_status"] == mod.PROMOTE_OK
    assert payload["shadow_panel"]["tier"] == mod.TIER_WARN
    assert payload["worst_tier"] == mod.TIER_WARN
    assert rc == 1
    assert payload["thresholds"]["shadow"]["breach_days"] == 35
    assert payload["thresholds"]["fast_axis"]["breach_days"] == 28
    assert payload["thresholds"]["shadow"]["require_validated_promote"] is True


# --------------------------------------------------------------------------- #
# Panel freshness axis (umbrella #423 ROUND-3, correcting this module's own round-2
# fix): key on ``label_observation_cutoff`` (the fwd_60d-clipped max LABELED row --
# the latest information that actually affected fitting), with its EXPECTED ~60 BD
# label-horizon lag WIDENING the tiering thresholds. NEVER key on the RAW feature
# frontier (``max_feature_anchor_date``): round-3 Codex review on #423 established
# that field is data-pipeline-HEALTH provenance only -- keying freshness on it lets
# fresh UNLABELED rows the model never trained on make a frozen panel read fresh.
# --------------------------------------------------------------------------- #
def test_label_observation_cutoff_is_the_freshness_axis(tmp_path: Path) -> None:
    # A genuinely fresh retrain: label_observation_cutoff sits exactly at the EXPECTED
    # 60-business-day frontier behind AS_OF (2026-06-30 -> 2026-04-07, 84 calendar
    # days). That 84d raw age reads HEALTHY only because the threshold is widened by
    # the same 84d lag (14 + 84 = 98 >= 84) -- unadjusted it would be born-BREACH.
    art = _write_json(
        tmp_path / "panel.json",
        {
            "kind": "xgb",
            "trained_date": "2026-06-30",
            "label_observation_cutoff": "2026-04-07",  # freshness axis, 84d raw age
            "max_feature_anchor_date": "2026-06-27",   # data-pipeline-health provenance only
        },
    )
    fresh = mod.read_artifact_freshness("prod-panel", art, AS_OF)
    assert fresh.binding_field == "label_observation_cutoff"
    assert fresh.age_days == 84  # literal, unadjusted calendar-day age
    assert fresh.tier == mod.TIER_HEALTHY
    assert fresh.max_feature_anchor_date == "2026-06-27"
    assert "provenance" in fresh.detail  # feature anchor flagged, not read as freshness
    assert "label horizon" in fresh.detail  # threshold widening is surfaced


def test_label_observation_cutoff_lag_threshold_boundary(tmp_path: Path) -> None:
    # The widened warn ceiling is EXACTLY 14 + 84 = 98 calendar days for AS_OF's
    # 60-BD lookahead: 98d reads healthy, 99d tips to warn.
    healthy = _write_json(tmp_path / "h.json", {"label_observation_cutoff": "2026-03-24"})  # 98d
    warn = _write_json(tmp_path / "w.json", {"label_observation_cutoff": "2026-03-23"})  # 99d
    fresh_healthy = mod.read_artifact_freshness("prod-panel", healthy, AS_OF)
    fresh_warn = mod.read_artifact_freshness("prod-panel", warn, AS_OF)
    assert fresh_healthy.age_days == 98
    assert fresh_healthy.tier == mod.TIER_HEALTHY
    assert fresh_warn.age_days == 99
    assert fresh_warn.tier == mod.TIER_WARN


def test_frozen_label_observation_cutoff_breaches_despite_lag_widening(tmp_path: Path) -> None:
    # A globally frozen panel (label cutoff far older than even the widened ceiling)
    # must still BREACH -- the lag widening accounts for the EXPECTED horizon, it does
    # not launder genuine staleness.
    art = _write_json(tmp_path / "frozen.json", {"label_observation_cutoff": "2025-05-01"})  # 425d
    fresh = mod.read_artifact_freshness("prod-panel", art, AS_OF)
    assert fresh.binding_field == "label_observation_cutoff"
    assert fresh.age_days == 425
    assert fresh.tier == mod.TIER_BREACH


def test_feature_anchor_no_longer_binds_freshness(tmp_path: Path) -> None:
    # max_feature_anchor_date is REMOVED from DATA_CUTOFF_FIELDS (round-3): a fresh
    # frontier must NOT bind over -- or launder -- an older generic data_cutoff_date.
    art = _write_json(
        tmp_path / "panel.json",
        {"max_feature_anchor_date": "2026-06-26", "data_cutoff_date": "2026-05-10"},  # 51d
    )
    fresh = mod.read_artifact_freshness("prod-panel", art, AS_OF)
    assert fresh.binding_field == "data_cutoff_date"
    assert fresh.age_days == 51
    assert fresh.tier == mod.TIER_BREACH  # stale on the REAL axis, fresh frontier ignored
    assert fresh.max_feature_anchor_date == "2026-06-26"  # still echoed as provenance


def test_max_feature_anchor_date_alone_is_not_a_freshness_axis(tmp_path: Path) -> None:
    # A panel carrying ONLY the raw feature frontier (no label-observation cutoff or
    # any other binding axis) has NO freshness axis -> fail closed to unknown.
    art = _write_json(
        tmp_path / "panel.json",
        {"kind": "xgb", "trained_date": "2026-06-30", "max_feature_anchor_date": "2026-06-27"},
    )
    fresh = mod.read_artifact_freshness("prod-panel", art, AS_OF)
    assert fresh.binding_field is None
    assert fresh.age_days is None
    assert fresh.tier == mod.TIER_UNKNOWN  # NOT healthy off a 3d-old feature frontier
    assert fresh.max_feature_anchor_date == "2026-06-27"  # echoed as provenance only


def test_fresh_unlabeled_rows_do_not_improve_panel_freshness(tmp_path: Path) -> None:
    # Regression for the Codex #423 round-3 review (mirrors
    # TestModelFreshnessAxisIntegration::test_fresh_unlabeled_rows_do_not_improve_model_freshness
    # in RenQuant): appending fresh UNLABELED feature rows advances
    # ``max_feature_anchor_date`` alone -- the labeled training frame (and therefore
    # ``label_observation_cutoff``) is unchanged, so the freshness READ must be
    # IDENTICAL even though the raw frontier genuinely moved.
    frozen = _write_json(
        tmp_path / "frozen.json",
        {"label_observation_cutoff": "2025-05-01", "max_feature_anchor_date": "2025-05-05"},
    )
    extended = _write_json(
        tmp_path / "extended.json",
        # Simulates the data pipeline catching up to just before AS_OF with fresh,
        # not-yet-labelable rows -- same frozen label cutoff, much fresher frontier.
        {"label_observation_cutoff": "2025-05-01", "max_feature_anchor_date": "2026-06-29"},
    )
    fresh_frozen = mod.read_artifact_freshness("prod-panel", frozen, AS_OF)
    fresh_extended = mod.read_artifact_freshness("prod-panel", extended, AS_OF)
    assert fresh_frozen.binding_field == fresh_extended.binding_field == "label_observation_cutoff"
    assert fresh_frozen.age_days == fresh_extended.age_days == 425
    assert fresh_frozen.tier == fresh_extended.tier == mod.TIER_BREACH
    # ...even though the raw frontier DID advance (a genuine, separate data-pipeline-
    # health signal) -- proving the two fields are decoupled, not that the panel
    # extension silently no-opped.
    assert fresh_extended.max_feature_anchor_date != fresh_frozen.max_feature_anchor_date


def test_main_cli_panel_fresh_on_label_cutoff_with_lag_accounted(tmp_path: Path, capsys) -> None:
    # End-to-end: a fresh panel whose label_observation_cutoff sits at the EXPECTED
    # ~60 BD frontier reads HEALTHY through the full pipeline once the threshold
    # widening is applied; the (fresher) feature anchor is echoed but never tiered.
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-25", shadow_cutoff="2026-06-27", ticker_cutoff="2026-06-25")
    _write_json(
        fx["prod"],
        {
            "kind": "xgb",
            "trained_date": "2026-06-30",
            "label_observation_cutoff": "2026-04-07",
            "max_feature_anchor_date": "2026-06-27",
        },
    )
    argv = [
        "--as-of", "2026-06-30",
        "--repo-root", str(tmp_path),
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--watchlist", "AAPL,MSFT",
        "--quiet", "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["prod_panel"]["binding_field"] == "label_observation_cutoff"
    assert payload["prod_panel"]["age_days"] == 84
    assert payload["prod_panel"]["max_feature_anchor_date"] == "2026-06-27"
    assert payload["prod_panel"]["tier"] == mod.TIER_HEALTHY
    assert payload["worst_tier"] == mod.TIER_HEALTHY
    assert rc == 0


# --------------------------------------------------------------------------- #
# Integration: run a #419 promotion output through the whole monitor (main()).
# --------------------------------------------------------------------------- #
def test_integration_419_receipt_makes_shadow_healthy(tmp_path: Path, capsys) -> None:
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-25", shadow_cutoff="2026-06-27", ticker_cutoff="2026-06-25")
    argv = [
        "--as-of", "2026-06-30",
        "--repo-root", str(tmp_path),
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--promote-receipt-dir", str(fx["receipt_dir"]),
        "--watchlist", "AAPL,MSFT",
        "--quiet", "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["shadow_panel"]["promotion_status"] == mod.PROMOTE_OK
    assert payload["shadow_panel"]["promote_validated"] is True
    assert payload["shadow_panel"]["promotion_receipt_path"] is not None
    assert payload["shadow_panel"]["tier"] == mod.TIER_HEALTHY
    assert payload["worst_tier"] == mod.TIER_HEALTHY
    assert rc == 0


def test_integration_no_receipt_shadow_fails_closed(tmp_path: Path, capsys) -> None:
    # The production path BEFORE #419 emits receipts: the served pin exists and is fresh
    # on age, but with no receipt the monitor must NOT read healthy (fail closed).
    fx = _build_fixture(tmp_path, prod_cutoff="2026-06-25", shadow_cutoff="2026-06-27", ticker_cutoff="2026-06-25")
    empty_receipts = tmp_path / "empty_receipts"
    argv = [
        "--as-of", "2026-06-30",
        "--repo-root", str(tmp_path),
        "--models-dir", str(fx["models"]),
        "--prod-panel", str(fx["prod"]),
        "--shadow-config", str(fx["shadow_cfg"]),
        "--promote-receipt-dir", str(empty_receipts),
        "--watchlist", "AAPL,MSFT",
        "--quiet", "--json",
    ]
    rc = mod.main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["shadow_panel"]["promotion_status"] == mod.PROMOTE_MISSING
    assert payload["shadow_panel"]["tier"] == mod.TIER_ESCALATE
    assert payload["worst_tier"] == mod.TIER_ESCALATE
    assert rc == 2
