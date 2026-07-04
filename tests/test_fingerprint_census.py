"""Tests for scripts/fingerprint_census.py (M6 stage-2 step 3).

Fixture umbrella tree only — NEVER the live tree. Hash values always come
from renquant_common.model_fingerprint (imports only). Mirrors the
fixture conventions of test_prestamp_legacy_fingerprints.py (the census
reuses that tool's inventory resolution by import).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import warnings
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "fingerprint_census.py"
)
_spec = importlib.util.spec_from_file_location("fingerprint_census", _SCRIPT)
census = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(census)

mf = pytest.importorskip(
    "renquant_common.model_fingerprint",
    reason="sibling renquant-common checkout not on PYTHONPATH",
)
if not hasattr(mf, "model_content_sha256_from_path"):  # pragma: no cover
    pytest.skip(
        "renquant-common lacks the 0.8.1 legacy surface",
        allow_module_level=True,
    )

HAS_V1 = hasattr(mf, "FINGERPRINT_SCHEMA_VERSION")
#: The stage-2 audit fields are classified OPERATIONAL from renquant-common
#: 0.9.2 (the step-1 prerequisite PR). Audit-field tests skip on older
#: siblings instead of failing — the dependency is directional, not broken.
HAS_092_TABLES = HAS_V1 and "restamp_provenance" in getattr(
    mf, "OPERATIONAL_KEYS", frozenset()
)

STRATEGY = "backtesting/renquant_104"


def _legacy(path: Path) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return mf.model_content_sha256_from_path(path)


def _scorer_payload(seed: str) -> dict:
    return {
        "kind": "panel_ltr",
        "version": 3,
        "booster_raw_json": json.dumps({"trees": [1, 2, 3], "seed": seed}),
        "feature_cols": ["f1", "f2"],
        "feature_means": [0.1, 0.2],
        "feature_stds": [1.0, 1.1],
        "params": {"eta": 0.1, "objective": "rank:pairwise"},
        "label_col": "fwd_60d_excess",
        "lookahead_days": 60,
        "trained_date": "2026-06-15",
        "metadata": {"score_sample_range": [-0.5, 0.2]},
    }


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def _legacy_stamped(path: Path, payload: dict) -> Path:
    _write(path, payload)
    payload = dict(payload)
    payload["model_content_fingerprint"] = _legacy(path)
    return _write(path, payload)


def _make_root(
    tmp_path: Path,
    *,
    prod_state: str = "legacy",       # legacy | unstamped | tampered
    fold_state: str = "legacy",       # legacy | v1 | v1_corrupt
    cal_state: str = "match",         # match | mismatch | cross_schema
) -> Path:
    root = tmp_path / "umbrella"
    sd = root / STRATEGY

    # prod artifact (data/ + config-resolved copy share content).
    prod_payload = _scorer_payload("prod")
    prod_data = root / "data/panel-ltr-prod-alpha158-fund-fwd60d.json"
    prod_art = sd / "artifacts/prod/panel-ltr.alpha158_fund.json"
    if prod_state == "unstamped":
        _write(prod_data, prod_payload)
        _write(prod_art, prod_payload)
    else:
        _legacy_stamped(prod_data, prod_payload)
        _legacy_stamped(prod_art, prod_payload)
        if prod_state == "tampered":
            tampered = json.loads(prod_data.read_text())
            tampered["feature_means"] = [9.9, 9.9]  # PREDICTIVE drift
            _write(prod_data, tampered)
            _write(prod_art, tampered)

    _legacy_stamped(
        root / "data/shadow_analyst/panel-ltr-shadow-analyst-rev3-fwd60d.json",
        _scorer_payload("shadow-analyst"),
    )
    _legacy_stamped(
        root / "data/shadow_analyst/panel-ltr-shadow-baseline-noan-fwd60d.json",
        _scorer_payload("shadow-noan"),
    )

    # prod calibrator bound to the config-resolved prod artifact.
    prod_identity = (
        json.loads(prod_art.read_text()).get("model_content_fingerprint")
        or _legacy(prod_art)
    )
    _write(sd / "artifacts/prod/panel-rank-calibration.json", {
        "method": "platt",
        "metadata": {
            "scorer_artifact": "artifacts/prod/panel-ltr.alpha158_fund.json",
            "scorer_model_content_fingerprint": prod_identity,
        },
    })
    # Regime calibrator: out of scope (§5 row 8).
    _write(sd / "artifacts/prod/panel-calibration-BEAR.json",
           {"method": "platt", "metadata": {}})

    # One WF fold + its calibrator + the manifest.
    cutoff = "2026-03-02"
    fold = sd / f"artifacts/walkforward_gbdt_prod_recipe_v2/{cutoff}/panel-ltr.json"
    fold_payload = _scorer_payload(f"fold-{cutoff}")
    if fold_state == "legacy":
        _legacy_stamped(fold, fold_payload)
        fold_identity = json.loads(fold.read_text())["model_content_fingerprint"]
        declared_version = None
    else:
        assert HAS_V1
        stamped = dict(fold_payload)
        stamped.update(mf.stamp(fold_payload))
        if fold_state == "v1_corrupt":
            stamped["model_content_fingerprint"] = "sha256:" + "0" * 64
        _write(fold, stamped)
        fold_identity = stamped["model_content_fingerprint"]
        declared_version = 1

    cal_meta = {
        "scorer_artifact": f"artifacts/walkforward_gbdt_prod_recipe_v2/{cutoff}/panel-ltr.json",
        "scorer_model_content_fingerprint": fold_identity,
    }
    if cal_state == "mismatch":
        cal_meta["scorer_model_content_fingerprint"] = "sha256:" + "f" * 64
    if cal_state == "cross_schema":
        # Fold is v1-stamped but the calibrator declares versionless.
        assert fold_state.startswith("v1")
    elif declared_version is not None:
        cal_meta["scorer_fingerprint_schema_version"] = declared_version
    _write(
        sd / f"artifacts/sim/walkforward_calibrators/{cutoff}/panel-rank-calibration.json",
        {"method": "platt", "metadata": cal_meta},
    )
    _write(
        sd / "artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json",
        {"schema_version": 1, "retrains": [{
            "artifact_uri": f"artifacts/walkforward_gbdt_prod_recipe_v2/{cutoff}/panel-ltr.json",
            "calibrator_uri": f"artifacts/sim/walkforward_calibrators/{cutoff}/panel-rank-calibration.json",
            "cutoff_date": cutoff,
            "lookahead_days": 60,
        }]},
    )

    _write(sd / "strategy_config.json", {
        "ranking": {"panel_scoring": {
            "artifact_path": "artifacts/prod/panel-ltr.alpha158_fund.json",
            "global_calibration": {
                "artifact_path": "artifacts/prod/panel-rank-calibration.json",
            },
        }},
    })
    return root


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)):
            hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


# ---------------------------------------------------------------------------
# Green paths
# ---------------------------------------------------------------------------

def test_all_legacy_green_after_step0(tmp_path) -> None:
    """The step-0 state: every artifact legacy-stamped, bindings hold."""
    root = _make_root(tmp_path)
    report = census.run_census(root)
    s = report["summary"]
    assert s["all_green"] is True
    assert s["n_red_artifacts"] == 0 and s["n_red_bindings"] == 0
    assert s["stamped_schema_counts"] == {
        "legacy": s["n_artifacts"], "v1": 0, "unstamped": 0,
    }
    # Every artifact row carries BOTH recomputes (v1 may be an error row
    # only when the tables can't classify the payload).
    for r in report["artifacts"]:
        assert r["legacy_recompute"]
        assert r["verdict"] == "GREEN"


def test_census_is_read_only(tmp_path) -> None:
    root = _make_root(tmp_path)
    before = _tree_digest(root)
    census.run_census(root)
    assert _tree_digest(root) == before


def test_exit_code_and_report_write(tmp_path, capsys) -> None:
    root = _make_root(tmp_path)
    report_path = tmp_path / "out" / "census.json"
    rc = census.main([
        "--root", str(root), "--report", str(report_path),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RESULT: GREEN" in out
    payload = json.loads(report_path.read_text())
    assert payload["read_only"] is True
    assert payload["summary"]["all_green"] is True


# ---------------------------------------------------------------------------
# Red paths (per-artifact dispatch)
# ---------------------------------------------------------------------------

def test_unstamped_artifact_is_red(tmp_path) -> None:
    root = _make_root(tmp_path, prod_state="unstamped")
    report = census.run_census(root)
    reds = [r for r in report["artifacts"] if r["verdict"] == "RED"]
    assert reds and all("UNSTAMPED" in r["reason"] for r in reds)
    assert report["summary"]["all_green"] is False


def test_legacy_stamp_drift_is_red(tmp_path) -> None:
    root = _make_root(tmp_path, prod_state="tampered")
    report = census.run_census(root)
    reds = [r for r in report["artifacts"] if r["verdict"] == "RED"]
    assert reds
    assert all("legacy stamp != legacy recompute" in r["reason"] for r in reds)


@pytest.mark.skipif(not HAS_V1, reason="needs schema-v1 renquant-common")
def test_v1_stamped_green(tmp_path) -> None:
    root = _make_root(tmp_path, fold_state="v1")
    report = census.run_census(root)
    fold_rows = [r for r in report["artifacts"] if r["family"] == "wf-fold"]
    assert fold_rows and fold_rows[0]["verdict"] == "GREEN"
    assert fold_rows[0]["stamped_schema_version"] == 1
    assert report["summary"]["stamped_schema_counts"]["v1"] == 1
    assert report["summary"]["all_green"] is True


@pytest.mark.skipif(not HAS_V1, reason="needs schema-v1 renquant-common")
def test_v1_corrupt_stamp_is_red(tmp_path) -> None:
    root = _make_root(tmp_path, fold_state="v1_corrupt", cal_state="mismatch")
    report = census.run_census(root)
    fold_rows = [r for r in report["artifacts"] if r["family"] == "wf-fold"]
    assert fold_rows[0]["verdict"] == "RED"
    assert "v1 stamp != v1 recompute" in fold_rows[0]["reason"]


@pytest.mark.skipif(
    not HAS_092_TABLES,
    reason="needs renquant-common >= 0.9.2 (stage-2 fields classified)",
)
def test_v1_dual_stamped_audit_field_checked(tmp_path) -> None:
    """Criterion (c): legacy-081 audit field vs the stripped legacy
    recompute — green when true, red when the re-stamp papered over
    a drift."""
    root = _make_root(tmp_path, fold_state="v1")
    fold = (root / STRATEGY /
            "artifacts/walkforward_gbdt_prod_recipe_v2/2026-03-02/panel-ltr.json")
    payload = json.loads(fold.read_text())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        true_legacy = mf._legacy_model_content_sha256({
            k: v for k, v in payload.items()
            if k not in census.STAGE2_ADDED_TOP_LEVEL_FIELDS
        })
    payload[census.LEGACY_AUDIT_KEY] = true_legacy
    payload["restamp_provenance"] = {"stamped_by": "step-2 tool", "grant": "x"}
    _write(fold, payload)
    report = census.run_census(root)
    fold_rows = [r for r in report["artifacts"] if r["family"] == "wf-fold"]
    assert fold_rows[0]["verdict"] == "GREEN"
    assert "legacy-081 audit holds" in fold_rows[0]["reason"]

    payload[census.LEGACY_AUDIT_KEY] = "sha256:" + "9" * 64
    _write(fold, payload)
    report = census.run_census(root)
    fold_rows = [r for r in report["artifacts"] if r["family"] == "wf-fold"]
    assert fold_rows[0]["verdict"] == "RED"
    assert "papered over" in fold_rows[0]["reason"]


# ---------------------------------------------------------------------------
# Binding dispatch
# ---------------------------------------------------------------------------

def test_binding_mismatch_is_red(tmp_path) -> None:
    root = _make_root(tmp_path, cal_state="mismatch")
    report = census.run_census(root)
    bad = [b for b in report["bindings"] if b.get("verdict") == "MISMATCH"]
    assert bad
    assert report["summary"]["n_red_bindings"] >= 1
    assert report["summary"]["all_green"] is False


@pytest.mark.skipif(not HAS_V1, reason="needs schema-v1 renquant-common")
def test_binding_cross_schema_is_red(tmp_path) -> None:
    """A v1-stamped fold with a versionless calibrator declaration is a
    cross-schema pair — never a match, even though the declared value
    equals the fold's v1 stamp byte-for-byte."""
    root = _make_root(tmp_path, fold_state="v1", cal_state="cross_schema")
    report = census.run_census(root)
    fold_bindings = [
        b for b in report["bindings"]
        if "walkforward_calibrators" in b["calibrator"]
    ]
    assert fold_bindings and fold_bindings[0]["verdict"] == "MISMATCH"
    assert "cross-schema" in fold_bindings[0]["detail"]


def test_regime_calibrator_reported_out_of_scope(tmp_path) -> None:
    root = _make_root(tmp_path)
    report = census.run_census(root)
    info = [i for i in report["info"] if "panel-calibration-BEAR" in i["path"]]
    assert info and info[0]["status"] == "OUT_OF_SCOPE"
    assert report["summary"]["all_green"] is True  # never blocking


# ---------------------------------------------------------------------------
# Manifest stamped-field agreement (§5 row 5)
# ---------------------------------------------------------------------------

def test_manifest_stamped_fields_checked_when_present(tmp_path) -> None:
    root = _make_root(tmp_path)
    manifest = (root / STRATEGY /
                "artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json")
    fold = (root / STRATEGY /
            "artifacts/walkforward_gbdt_prod_recipe_v2/2026-03-02/panel-ltr.json")
    doc = json.loads(manifest.read_text())
    doc["retrains"][0]["scorer_artifact_sha256"] = mf.artifact_sha256(fold)
    manifest.write_text(json.dumps(doc))
    report = census.run_census(root)
    rows = [r for m in report["manifest_field_checks"] for r in m["rows"]]
    assert rows and rows[0]["verdict"] == "MATCH"

    doc["retrains"][0]["scorer_artifact_sha256"] = "sha256:" + "0" * 64
    manifest.write_text(json.dumps(doc))
    report = census.run_census(root)
    rows = [r for m in report["manifest_field_checks"] for r in m["rows"]]
    assert rows and rows[0]["verdict"] == "MISMATCH"
    assert report["summary"]["n_red_manifest_rows"] == 1
    assert report["summary"]["all_green"] is False
