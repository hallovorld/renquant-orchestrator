"""Tests for scripts/prestamp_legacy_fingerprints.py (M6 stage-2 step 0).

Fixture umbrella tree only — NEVER the live tree. Hash values are always
obtained from renquant_common.model_fingerprint (imports only); the tests
skip when the sibling renquant-common checkout is not importable (the
orchestrator Makefile/pytest pythonpath provides it).

The verifier-acceptance tests import the REAL pipeline verifier code
(walk_forward loader helpers + job_panel_scoring's fail-closed assert) and
prove that a step-0 stamped artifact keeps passing them when the venv's bare
``model_content_sha256`` carries schema-v1 semantics (renquant-common 0.9.1)
— the design §3 step-0 claim, verified against code, not narrative.
"""
from __future__ import annotations

import importlib.util
import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "prestamp_legacy_fingerprints.py"
)
_spec = importlib.util.spec_from_file_location("prestamp", _SCRIPT)
prestamp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prestamp)

mf = pytest.importorskip(
    "renquant_common.model_fingerprint",
    reason="sibling renquant-common checkout not on PYTHONPATH",
)
if not hasattr(mf, "model_content_sha256_from_path"):  # pragma: no cover
    pytest.skip(
        "renquant-common lacks the 0.8.1 legacy surface "
        "(need 0.8.1 native or the 0.9.1 deprecated shims)",
        allow_module_level=True,
    )

HAS_V1 = hasattr(mf, "FINGERPRINT_SCHEMA_VERSION")

STRATEGY = "backtesting/renquant_104"
FOLD_CUTOFFS = ("2026-03-02", "2026-04-01")


def _legacy(path: Path) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return mf.model_content_sha256_from_path(path)


def _scorer_payload(seed: str, *, with_metadata: bool = True) -> dict:
    payload = {
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
    }
    if with_metadata:
        payload["metadata"] = {"score_sample_range": [-0.5, 0.2]}
    return payload


def _write(path: Path, payload: dict, *, indent: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if indent is None:
        path.write_text(json.dumps(payload, separators=(",", ":")))
    else:
        path.write_text(json.dumps(payload, indent=indent) + "\n")
    return path


def make_root(tmp_path: Path) -> Path:
    """Build a miniature umbrella tree mirroring the §3a inventory shape."""
    root = tmp_path / "umbrella"
    sd = root / STRATEGY

    prod_payload = _scorer_payload("prod", with_metadata=False)
    # The named data/ artifact and the config-resolved prod artifact carry the
    # SAME predictive content (mirrors the live tree: promote = copy).
    _write(root / "data/panel-ltr-prod-alpha158-fund-fwd60d.json", prod_payload)
    prod_art = _write(
        sd / "artifacts/prod/panel-ltr.alpha158_fund.json", prod_payload,
        indent=2,
    )
    _write(
        root / "data/shadow_analyst/panel-ltr-shadow-analyst-rev3-fwd60d.json",
        _scorer_payload("shadow-analyst"),
    )
    _write(
        root / "data/shadow_analyst/panel-ltr-shadow-baseline-noan-fwd60d.json",
        _scorer_payload("shadow-noan"),
    )

    _write(
        sd / "artifacts/prod/panel-rank-calibration.json",
        {
            "method": "platt",
            "metadata": {
                "scorer_artifact": "artifacts/prod/panel-ltr.alpha158_fund.json",
                "scorer_model_content_fingerprint": _legacy(prod_art),
                "scorer_artifact_fingerprint": _legacy(prod_art),
            },
        },
    )
    # Snapshot calibrator with a stale declaration: WARN-only, never blocking.
    _write(
        sd / "artifacts/prod/panel-rank-calibration.weekly_rollback_2026-06-15.json",
        {
            "method": "platt",
            "metadata": {
                "scorer_artifact": "artifacts/prod/panel-ltr.alpha158_fund.json",
                "scorer_model_content_fingerprint": "sha256:" + "0" * 64,
            },
        },
    )
    # Regime calibrator: declares no scorer identity (§5 row 8, out of scope).
    _write(
        sd / "artifacts/prod/panel-calibration-BEAR.json",
        {"method": "platt", "metadata": {}},
    )

    retrains = []
    for cutoff in FOLD_CUTOFFS:
        fold = _write(
            sd / f"artifacts/walkforward_gbdt_prod_recipe_v2/{cutoff}/panel-ltr.json",
            _scorer_payload(f"fold-{cutoff}"),
        )
        _write(
            sd / f"artifacts/sim/walkforward_calibrators/{cutoff}/panel-rank-calibration.json",
            {
                "method": "platt",
                "metadata": {
                    "scorer_artifact": f"artifacts/walkforward_gbdt_prod_recipe_v2/{cutoff}/panel-ltr.json",
                    "scorer_model_content_fingerprint": _legacy(fold),
                },
            },
        )
        retrains.append({
            "artifact_uri": f"artifacts/walkforward_gbdt_prod_recipe_v2/{cutoff}/panel-ltr.json",
            "calibrator_uri": f"artifacts/sim/walkforward_calibrators/{cutoff}/panel-rank-calibration.json",
            "cutoff_date": cutoff,
            "lookahead_days": 60,
        })
    _write(
        sd / "artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json",
        {"schema_version": 1, "retrains": retrains},
    )
    # A historical manifest that must be reported out-of-scope, not stamped.
    _write(
        sd / "artifacts/sim/walkforward_manifest.json",
        {"schema_version": 1, "retrains": [
            {"artifact_uri": "artifacts/old_corpus/2024-01-01/panel-ltr.json",
             "cutoff_date": "2024-01-01"},
        ]},
    )

    # PatchTST family-split lane: .pt primary + calibrator declaring a .pt
    # scorer — verification must classify FAMILY_SPLIT_NA, never block.
    _write(
        sd / "artifacts/shadow/panel-rank-calibration.pt-lane.json",
        {
            "method": "platt",
            "metadata": {
                "scorer_artifact": "../../artifacts/patchtst_shadow/model.pt",
                "scorer_model_content_fingerprint": "sha256:" + "a" * 64,
            },
        },
    )
    _write(sd / "strategy_config.json", {
        "ranking": {"panel_scoring": {
            "artifact_path": "artifacts/prod/panel-ltr.alpha158_fund.json",
            "global_calibration": {
                "artifact_path": "artifacts/prod/panel-rank-calibration.json",
            },
        }},
    })
    _write(sd / "strategy_config.shadow.json", {
        "ranking": {"panel_scoring": {
            "artifact_path": "../../artifacts/patchtst_shadow/model.pt",
            "global_calibration": {
                "artifact_path": "artifacts/shadow/panel-rank-calibration.pt-lane.json",
            },
        }},
    })
    return root


def _stamp_target_paths(root: Path) -> list[Path]:
    sd = root / STRATEGY
    return [
        root / "data/panel-ltr-prod-alpha158-fund-fwd60d.json",
        root / "data/shadow_analyst/panel-ltr-shadow-analyst-rev3-fwd60d.json",
        root / "data/shadow_analyst/panel-ltr-shadow-baseline-noan-fwd60d.json",
        sd / "artifacts/prod/panel-ltr.alpha158_fund.json",
        *[
            sd / f"artifacts/walkforward_gbdt_prod_recipe_v2/{c}/panel-ltr.json"
            for c in FOLD_CUTOFFS
        ],
    ]


def _run(root: Path, *extra: str, report: Path | None = None) -> tuple[int, dict | None]:
    argv = ["--root", str(root), *extra]
    if report is not None:
        argv += ["--report", str(report)]
    rc = prestamp.main(argv)
    payload = json.loads(report.read_text()) if report and report.exists() else None
    return rc, payload


# ---------------------------------------------------------------------------
# dry-run / plan
# ---------------------------------------------------------------------------

def test_dry_run_plans_full_inventory_and_writes_nothing(tmp_path):
    root = make_root(tmp_path)
    targets = _stamp_target_paths(root)
    before = {p: p.read_bytes() for p in targets}

    rc, report = _run(root, report=tmp_path / "report.json")

    assert rc == 0
    assert report["mode"] == "dry-run"
    assert report["summary"]["n_targets"] == len(targets) == 6
    assert report["summary"]["n_to_stamp"] == 6
    assert report["summary"]["n_refusals"] == 0
    assert report["summary"]["n_red_bindings"] == 0
    for p in targets:
        assert p.read_bytes() == before[p], f"dry-run mutated {p}"
    # No backups either.
    assert not list(root.rglob("*.bak_prestamp_*"))
    # Family coverage per §3a.
    families = {r["family"] for r in report["artifacts"]}
    assert families == {"prod", "shadow", "wf-fold"}
    # Bindings: active + 2 folds MATCH; snapshot WARN mismatch non-blocking;
    # pt-lane FAMILY_SPLIT_NA.
    verdicts = {(b["calibrator"], b["verdict"]) for b in report["bindings"]}
    assert (
        f"{STRATEGY}/artifacts/prod/panel-rank-calibration.json", "MATCH",
    ) in verdicts
    assert any(v == "FAMILY_SPLIT_NA" for _, v in verdicts)
    assert any("weekly_rollback" in c and v == "MISMATCH" for c, v in verdicts)
    # Historical manifest reported out of scope, its corpus untouched.
    assert any(
        m.endswith("walkforward_manifest.json")
        for m in report["manifests"]["out_of_scope"]
    )
    # Regime calibrator reported outside step-0 scope.
    assert any(
        i["family"] == "regime-calibrator" and i["status"] == "OUT_OF_SCOPE"
        for i in report["info"]
    )
    # The .pt primary is reported as family-split, never a stamp target.
    assert any(i["status"] == "SKIP_NON_JSON" for i in report["info"])


# ---------------------------------------------------------------------------
# apply: grant gate, banner, byte-identity, idempotence
# ---------------------------------------------------------------------------

def test_apply_without_grant_refused(tmp_path, capsys):
    root = make_root(tmp_path)
    targets = _stamp_target_paths(root)
    before = {p: p.read_bytes() for p in targets}
    rc, _ = _run(root, "--apply")
    assert rc == 2
    err = capsys.readouterr().err
    assert "landing action" in err.lower()
    assert "--grant" in err
    for p in targets:
        assert p.read_bytes() == before[p]


def test_apply_stamps_byte_identical_values_with_banner(tmp_path, capsys):
    root = make_root(tmp_path)
    targets = _stamp_target_paths(root)
    pre_legacy = {p: _legacy(p) for p in targets}
    if HAS_V1:
        pre_v1 = {
            p: mf.model_content_sha256(json.loads(p.read_text()))
            for p in targets
        }

    rc, report = _run(
        root, "--apply", "--grant", "operator grant TEST-BATCH",
        report=tmp_path / "report.json",
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "LANDING ACTION" in out and "OPERATOR GRANT REQUIRED" in out
    assert report["summary"]["n_stamped"] == 6
    for p in targets:
        payload = json.loads(p.read_text())
        stamp = payload["model_content_fingerprint"]
        # Byte-identity vs the renquant-common shim output on the file as
        # written (the 0.9.1 deprecated legacy surface).
        assert stamp == _legacy(p) == pre_legacy[p]
        engine = getattr(mf, "_legacy_model_content_sha256", None)
        if callable(engine):
            assert stamp == engine(payload)
        # Provenance nested under metadata (operational under both schemas).
        prov = payload["metadata"]["prestamp_legacy_fingerprint"]
        assert prov["operator_grant"] == "operator grant TEST-BATCH"
        assert "0.8.1" in prov["semantics"]
        # No schema version is written: versionless IS the legacy declaration.
        assert "fingerprint_schema_version" not in payload
        # Stamping perturbed NEITHER content hash.
        if HAS_V1:
            assert mf.model_content_sha256(payload) == pre_v1[p]
        # Backup exists next to the artifact.
        assert list(p.parent.glob(p.name + ".bak_prestamp_*"))
    # Bindings still hold post-write.
    assert report["summary"]["n_red_bindings"] == 0
    # Manifest-stamper follow-up is mandated once fold bytes changed.
    assert any(
        "stamp_walkforward_fingerprints.py" in f for f in report["follow_ups"]
    )


def test_apply_is_idempotent(tmp_path):
    root = make_root(tmp_path)
    rc1, _ = _run(root, "--apply", "--grant", "g1")
    assert rc1 == 0
    targets = _stamp_target_paths(root)
    after_first = {p: p.read_bytes() for p in targets}

    rc2, report2 = _run(
        root, "--apply", "--grant", "g2", report=tmp_path / "r2.json",
    )
    assert rc2 == 0
    assert report2["summary"]["n_already_stamped"] == 6
    assert report2["summary"]["n_to_stamp"] == 0
    assert report2["summary"]["n_stamped"] == 0
    for p in targets:
        assert p.read_bytes() == after_first[p], f"re-run mutated {p}"


# ---------------------------------------------------------------------------
# refusals (fail-closed)
# ---------------------------------------------------------------------------

def test_refuses_root_that_is_not_an_umbrella_tree(tmp_path, capsys):
    rc = prestamp.main(["--root", str(tmp_path)])
    assert rc == 2
    assert "does not look like the umbrella live tree" in capsys.readouterr().err


def test_refuses_manifest_outside_root(tmp_path, capsys):
    root = make_root(tmp_path)
    foreign = tmp_path / "elsewhere" / "manifest.json"
    foreign.parent.mkdir()
    foreign.write_text(json.dumps({"retrains": []}))
    rc = prestamp.main(["--root", str(root), "--manifest", str(foreign)])
    assert rc == 2
    assert "escapes --root" in capsys.readouterr().err


def test_refuses_foreign_stamp_and_blocks_the_whole_apply(tmp_path):
    root = make_root(tmp_path)
    victim = root / "data/panel-ltr-prod-alpha158-fund-fwd60d.json"
    payload = json.loads(victim.read_text())
    payload["model_content_fingerprint"] = "sha256:" + "d" * 64
    _write(victim, payload)
    others = [p for p in _stamp_target_paths(root) if p != victim]
    before = {p: p.read_bytes() for p in others}

    rc, report = _run(
        root, "--apply", "--grant", "g", report=tmp_path / "r.json",
    )
    assert rc == 2
    row = next(r for r in report["artifacts"] if "prod-alpha158" in r["path"])
    assert row["status"] == "REFUSE"
    assert "foreign stamp" in row["reason"]
    # Fail-closed: one refusal blocks every write.
    assert report["summary"]["n_stamped"] == 0
    for p in others:
        assert p.read_bytes() == before[p]


def test_refuses_already_versioned_artifact(tmp_path):
    root = make_root(tmp_path)
    victim = root / "data/shadow_analyst/panel-ltr-shadow-analyst-rev3-fwd60d.json"
    payload = json.loads(victim.read_text())
    payload["fingerprint_schema_version"] = 1
    _write(victim, payload)
    rc, report = _run(root, report=tmp_path / "r.json")
    assert rc == 2
    row = next(r for r in report["artifacts"] if "analyst-rev3" in r["path"])
    assert row["status"] == "REFUSE"
    assert "step-2 territory" in row["reason"]


def test_refuses_payload_without_predictive_content(tmp_path):
    root = make_root(tmp_path)
    sd = root / STRATEGY
    victim = (
        sd / f"artifacts/walkforward_gbdt_prod_recipe_v2/{FOLD_CUTOFFS[0]}/panel-ltr.json"
    )
    _write(victim, {"trained_date": "2026-06-15", "metadata": {}})
    rc, report = _run(root, report=tmp_path / "r.json")
    assert rc == 2
    row = next(
        r for r in report["artifacts"] if FOLD_CUTOFFS[0] in r["path"]
    )
    assert row["status"] == "REFUSE"
    assert "PREDICTIVE_CONTENT_HINTS" in row["reason"]


def test_red_binding_mismatch_blocks_apply(tmp_path):
    root = make_root(tmp_path)
    sd = root / STRATEGY
    cal = sd / "artifacts/prod/panel-rank-calibration.json"
    payload = json.loads(cal.read_text())
    payload["metadata"]["scorer_model_content_fingerprint"] = "sha256:" + "b" * 64
    _write(cal, payload)
    targets = _stamp_target_paths(root)
    before = {p: p.read_bytes() for p in targets}

    rc, report = _run(
        root, "--apply", "--grant", "g", report=tmp_path / "r.json",
    )
    assert rc == 2
    assert report["summary"]["n_red_bindings"] >= 1
    assert report["summary"]["n_stamped"] == 0
    for p in targets:
        assert p.read_bytes() == before[p]


# ---------------------------------------------------------------------------
# verifier acceptance: the stamped artifact passes the REAL verifiers
# ---------------------------------------------------------------------------

def _stamped_fixture(tmp_path):
    root = make_root(tmp_path)
    rc, _ = _run(root, "--apply", "--grant", "verifier-acceptance")
    assert rc == 0
    fold = (
        root / STRATEGY
        / f"artifacts/walkforward_gbdt_prod_recipe_v2/{FOLD_CUTOFFS[0]}/panel-ltr.json"
    )
    cal = (
        root / STRATEGY
        / f"artifacts/sim/walkforward_calibrators/{FOLD_CUTOFFS[0]}/panel-rank-calibration.json"
    )
    return root, fold, cal


def test_wf_loader_accepts_stamped_artifact(tmp_path):
    """The WF fail-closed contract passes on the stamped fold artifact.

    Uses the real ``renquant_pipeline.kernel.walk_forward.loader`` helpers
    (`_assert_calibrator_matches_entry` is `_any_fingerprints_match` over
    exactly these two lists). When the importable pipeline's bare hasher is
    v1 (renquant-common 0.9.1 convergence state), also proves the UNSTAMPED
    artifact would FAIL — the §1a.2 detonation this tool defuses.
    """
    wf = pytest.importorskip("renquant_pipeline.kernel.walk_forward.loader")
    ps = pytest.importorskip(
        "renquant_pipeline.kernel.panel_pipeline.panel_scorer"
    )
    root, fold, cal = _stamped_fixture(tmp_path)
    payload = json.loads(fold.read_text())
    stamp = payload["model_content_fingerprint"]

    scorer_fps = wf._scorer_fingerprints_from_payload(payload)
    assert stamp in scorer_fps  # the stamped-value route exists now
    calibrator = SimpleNamespace(
        metadata=json.loads(cal.read_text())["metadata"]
    )
    cal_fps = wf._calibrator_scorer_fingerprints(calibrator)
    assert wf._any_fingerprints_match(cal_fps, scorer_fps)

    unstamped = {
        k: v for k, v in payload.items() if k != "model_content_fingerprint"
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            bare = ps.model_content_sha256(unstamped)
        except Exception:  # noqa: BLE001 — v1 may raise on odd payloads
            bare = None
    if bare is not None and bare != stamp:
        # v1-semantics environment: without the stamp the fold fails closed.
        assert not wf._any_fingerprints_match(
            cal_fps, wf._scorer_fingerprints_from_payload(unstamped),
        )


@pytest.mark.skipif(
    not HAS_V1, reason="requires the renquant-common 0.9.x schema-v1 module"
)
def test_v1_divergence_is_real_and_only_the_stamp_bridges_it(tmp_path):
    """v1 hash != legacy stamp on the same payload (no-op flip impossible)."""
    root, fold, _ = _stamped_fixture(tmp_path)
    payload = json.loads(fold.read_text())
    stamp = payload["model_content_fingerprint"]
    v1 = mf.model_content_sha256(payload)
    assert v1 != stamp
    # And the stamp equals the legacy engine — the two semantics genuinely
    # diverge on this payload (label_col/lookahead_days classification).
    assert stamp == mf._legacy_model_content_sha256(payload)


def test_daily_path_assert_calibrator_matches_scorer(tmp_path):
    """The daily fail-closed check passes with the stamped active scorer.

    Scorer identity is built with the REAL renquant-common
    ``stamp_artifact_metadata`` (the exact function renquant-pipeline main
    re-exports into ``PanelScorer.load``): its ``setdefault`` must preserve
    the step-0 stamp. Then reproduces the §1a.1 armed weekly refit — a
    calibrator stamped with the v1 recompute mismatches an unstamped scorer
    (detonation), while the stamped-value precedence
    (``payload.get("model_content_fingerprint") or <recompute>``) keeps the
    refit on the legacy identity (defused).
    """
    jps = pytest.importorskip(
        "renquant_pipeline.kernel.panel_pipeline.job_panel_scoring"
    )
    root, _, _ = _stamped_fixture(tmp_path)
    prod = root / STRATEGY / "artifacts/prod/panel-ltr.alpha158_fund.json"
    payload = json.loads(prod.read_text())
    stamp = payload["model_content_fingerprint"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        meta = mf.stamp_artifact_metadata(
            {k: v for k, v in payload.items() if k != "booster_raw_json"},
            prod,
            payload=payload,
        )
    assert meta["model_content_fingerprint"] == stamp  # setdefault preserved

    ctx = SimpleNamespace(_panel_scorer=SimpleNamespace(metadata=meta))
    ok_calibrator = SimpleNamespace(
        metadata={"scorer_model_content_fingerprint": stamp}
    )
    jps._assert_calibrator_matches_scorer(
        ctx, ok_calibrator, prod, strict=True
    )  # must not raise

    if HAS_V1:
        # §1a.1 armed refit: v1-stamped calibrator vs legacy runtime identity.
        v1_value = mf.model_content_sha256(payload)
        armed = SimpleNamespace(
            metadata={"scorer_model_content_fingerprint": v1_value}
        )
        with pytest.raises(ValueError, match="fingerprint mismatch"):
            jps._assert_calibrator_matches_scorer(
                ctx, armed, prod, strict=True
            )
        # Defusal: the refit's stamped-value precedence resolves the stamped
        # legacy identity, never the v1 recompute.
        refit_identity = payload.get("model_content_fingerprint") or v1_value
        assert refit_identity == stamp
