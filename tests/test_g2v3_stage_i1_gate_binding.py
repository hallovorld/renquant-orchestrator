"""The Stage I-1 --dev-run entry point must FAIL CLOSED unless the immutable Stage I-0 GATE_RUN bundle verifies.

Born from PR #1084 review r1 (codex): "Make the development entry point fail closed unless it can load
the corrected, immutable Stage I-0 GATE_RUN bundle and verify gate_verdict=PASS, the reviewed frozen source
commit, the bundle's parameter/config and seed/input-manifest hashes, and the bundle identity expected by
this harness. Do not accept the old development-audit path as authorization."

Negative cases run on tmp_path copies of the real bundle (mutated one field at a time); the positive case is
the exact committed bundle in this repository. Nothing here touches the bar store or runs --dev-run.
"""
from __future__ import annotations

import gzip
import importlib.util
import inspect
import json
import pathlib
import shutil
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/experiments/g2v3_stage_i1_bases.py"


def _load():
    spec = importlib.util.spec_from_file_location("g2v3_stage_i1_bases_gate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load()
G = M.ACCEPTED_GATE_BUNDLE


def _read_json(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: pathlib.Path, obj):
    p.write_text(json.dumps(obj, indent=1), encoding="utf-8")


@pytest.fixture
def bundle_copy(tmp_path):
    """A faithful copy of the committed gate bundle + seed list inside a fake repo root (no git)."""
    fake = tmp_path / "repo"
    dst = fake / G["dir"]
    shutil.copytree(REPO / G["dir"], dst)
    seed = fake / G["seed_list_path"]
    seed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / G["seed_list_path"], seed)
    return fake, dst


def _refused(fake, match):
    with pytest.raises(M.GateNotAuthorized, match=match):
        M.load_gate_authorization(fake)


# --------------------------------------------------------------------------- #
# the frozen binding itself
# --------------------------------------------------------------------------- #
def test_bound_constants_are_the_reviewed_gate_bundle():
    assert G["dir"] == "doc/research/data/2026-08-29-g2v3-i0-gate-run"
    assert G["run_id"] == "i0-gate-20260829-f3d5bf7b"
    assert G["frozen_source_commit"] == "f3d5bf7bd75ffa9c0fb59f8c3bfa98fa509e8779"
    assert (G["run_status"], G["gate_verdict"]) == ("GATE_RUN", "PASS")
    assert G["report_sha256"] == "da41a706f31b3f39b9ccc9631b93a76a6cb994c8877f112ce49989916634cf44"
    assert G["audit_sha256"] == "dd5127d7326919b777acd0a6bf819dcc158c9cd02a44cd76ef7ca71fa844f3a9"
    assert G["input_manifest_aggregate_sha256"] == "a878f1caeaee863cc06c2f9b3ab0d6eba4389d656a4b4dabd731a1844cdfd4d9"
    assert G["input_manifest_count"] == 2124 and G["seed_list_count"] == 2144
    # the constants ARE the committed provenance.json, field for field
    prov = _read_json(REPO / G["dir"] / G["provenance_file"])
    assert prov["run_id"] == G["run_id"] and prov["frozen_source_commit"] == G["frozen_source_commit"]
    assert prov["seed_list"]["sha256"] == G["seed_list_sha256"]
    assert prov["code"]["census_script"]["sha256"] == G["census_script_sha256"]
    assert prov["code"]["design_doc"]["sha256"] == G["design_doc_sha256"]
    assert prov["input_manifest"]["aggregate_sha256"] == G["input_manifest_aggregate_sha256"]
    assert prov["outputs"]["report"]["sha256"] == G["report_sha256"]
    assert prov["outputs"]["audit"]["sha256"] == G["audit_sha256"]
    assert (prov["frozen_parameters"]["window"]["start"], prov["frozen_parameters"]["window"]["end"]) == G["gate_window"]
    assert G["gate_window"] == (M.DEV_START, M.DEV_END) and G["gate_h"] == M.H


def test_dev_run_reads_only_the_gate_audit_never_the_development_audit():
    assert M.GATE_AUDIT == REPO / G["dir"] / "g2v3_stage_i0_audit.json.gz"
    assert not hasattr(M, "CENSUS_AUDIT")
    text = SCRIPT.read_text(encoding="utf-8")
    assert "2026-08-27-g2v3-i0/g2v3_stage_i0_audit" not in text          # the old dev audit path is gone
    # dev_run_config takes exactly the authorization object and nothing else
    assert list(inspect.signature(M.dev_run_config).parameters) == ["auth"]
    with pytest.raises(M.GateNotAuthorized, match="GateAuthorization"):
        M.dev_run_config(None)


# --------------------------------------------------------------------------- #
# the exact accepted PASS bundle in this repository -> authorized
# --------------------------------------------------------------------------- #
def test_accepted_bundle_in_this_repo_authorizes():
    auth = M.load_gate_authorization(REPO)
    assert auth.run_id == G["run_id"]
    assert auth.frozen_source_commit == G["frozen_source_commit"]
    assert auth.gate_verdict == "PASS"
    assert auth.report_sha256 == G["report_sha256"] and auth.audit_sha256 == G["audit_sha256"]
    assert auth.input_manifest_aggregate_sha256 == G["input_manifest_aggregate_sha256"]
    assert auth.input_manifest_count == 2124
    assert auth.bear_n_eff_adj == 191.0
    assert auth.audit_path == M.GATE_AUDIT
    assert auth.provenance_sha256 == M.sha256_file(REPO / G["dir"] / "provenance.json")
    # the default repo root is the harness's own checkout
    assert M.load_gate_authorization().run_id == auth.run_id


def test_faithful_copy_passes_the_file_checks_but_is_not_authorization_outside_git(bundle_copy):
    fake, _ = bundle_copy
    auth = M._verify_gate_bundle_files(fake)
    assert auth.run_id == G["run_id"] and auth.report_sha256 == G["report_sha256"]
    _refused(fake, "not resolvable")           # no reviewed commit here => no authorization


# --------------------------------------------------------------------------- #
# negative cases, one field at a time on the copy
# --------------------------------------------------------------------------- #
def test_missing_bundle(bundle_copy):
    fake, dst = bundle_copy
    shutil.rmtree(dst)
    _refused(fake, "bundle directory missing")


@pytest.mark.parametrize("fname", ["g2v3_stage_i0_report.json", "g2v3_stage_i0_audit.json.gz", "provenance.json"])
def test_missing_bundle_file(bundle_copy, fname):
    fake, dst = bundle_copy
    (dst / fname).unlink()
    _refused(fake, f"{fname} missing")


def test_development_only_report_is_not_authorization(bundle_copy):
    fake, dst = bundle_copy
    rp = dst / "g2v3_stage_i0_report.json"
    rep = _read_json(rp)
    rep["run_status"], rep["gate_verdict"] = "DEVELOPMENT_ONLY", None
    _write_json(rp, rep)
    _refused(fake, "run_status 'DEVELOPMENT_ONLY' != 'GATE_RUN'")


def test_the_old_development_bundle_dropped_into_the_gate_dir_is_refused(bundle_copy):
    fake, dst = bundle_copy
    dev = REPO / "doc/research/data/2026-08-27-g2v3-i0"
    shutil.copyfile(dev / "g2v3_stage_i0_report.json", dst / "g2v3_stage_i0_report.json")
    shutil.copyfile(dev / "g2v3_stage_i0_audit.json.gz", dst / "g2v3_stage_i0_audit.json.gz")
    _refused(fake, "DEVELOPMENT_ONLY")


def test_failed_gate(bundle_copy):
    fake, dst = bundle_copy
    for fname, key in (("g2v3_stage_i0_report.json", "gate_verdict"), ("provenance.json", "gate_verdict")):
        obj = _read_json(dst / fname)
        obj[key] = "FAIL"
        _write_json(dst / fname, obj)
    _refused(fake, "gate_verdict 'FAIL' != 'PASS'")


def test_wrong_source_commit(bundle_copy):
    fake, dst = bundle_copy
    prov = _read_json(dst / "provenance.json")
    prov["frozen_source_commit"] = "0" * 40
    _write_json(dst / "provenance.json", prov)
    _refused(fake, "frozen_source_commit")


def test_wrong_run_id(bundle_copy):
    fake, dst = bundle_copy
    prov = _read_json(dst / "provenance.json")
    prov["run_id"] = "i0-gate-20260827-deadbeef"
    _write_json(dst / "provenance.json", prov)
    _refused(fake, "run_id")


@pytest.mark.parametrize("path", [("code", "census_script", "sha256"), ("code", "design_doc", "sha256"),
                                  ("seed_list", "sha256"), ("input_manifest", "aggregate_sha256"),
                                  ("input_manifest", "count"), ("outputs", "audit", "sha256"),
                                  ("frozen_parameters", "h")])
def test_wrong_config_script_seed_or_manifest_hash_in_provenance(bundle_copy, path):
    fake, dst = bundle_copy
    prov = _read_json(dst / "provenance.json")
    node = prov
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = 0 if isinstance(node[path[-1]], int) else "f" * 64
    _write_json(dst / "provenance.json", prov)
    _refused(fake, ".".join(path))


def test_dirty_gate_tree_is_refused(bundle_copy):
    fake, dst = bundle_copy
    prov = _read_json(dst / "provenance.json")
    prov["clean_tree"] = False
    _write_json(dst / "provenance.json", prov)
    _refused(fake, "clean_tree")


def test_tampered_report_file(bundle_copy):
    fake, dst = bundle_copy
    rp = dst / "g2v3_stage_i0_report.json"
    rep = _read_json(rp)
    rep["by_regime"]["BEAR"]["n_eff_adj"] = 999.0            # status + verdict untouched: only the hash catches it
    _write_json(rp, rep)
    _refused(fake, "g2v3_stage_i0_report.json sha256 on disk")


def test_tampered_audit_file(bundle_copy):
    fake, dst = bundle_copy
    ap = dst / "g2v3_stage_i0_audit.json.gz"
    with gzip.open(ap, "rt", encoding="utf-8") as fh:
        audit = json.load(fh)
    first = sorted(audit["bar_store_sha256"])[0]
    audit["bar_store_sha256"][first] = "0" * 64
    with gzip.open(ap, "wt", encoding="utf-8") as fh:
        json.dump(audit, fh)
    _refused(fake, "g2v3_stage_i0_audit.json.gz sha256 on disk")


def test_tampered_seed_list(bundle_copy):
    fake, _ = bundle_copy
    seed = fake / G["seed_list_path"]
    seed.write_text(seed.read_text(encoding="utf-8") + "\nZZZZ\n", encoding="utf-8")
    _refused(fake, "seed list")


def test_copy_inside_a_git_repo_without_the_frozen_commit_is_refused(bundle_copy):
    import subprocess
    fake, _ = bundle_copy
    subprocess.run(["git", "init", "-q", str(fake)], check=True)
    _refused(fake, "not resolvable")


# --------------------------------------------------------------------------- #
# the CLI: --dev-run asks for authorization BEFORE anything else and exits 2 without it
# --------------------------------------------------------------------------- #
def test_cli_dev_run_exits_2_when_the_gate_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(M, "REPO", tmp_path / "norepo")
    monkeypatch.delenv("G2V3_BAR_STORE", raising=False)
    assert M.main(["--dev-run"]) == 2
    err = capsys.readouterr().err
    assert "REFUSED --dev-run" in err and "bundle directory missing" in err
    assert not (tmp_path / "norepo").exists()                 # nothing was created or run


def test_run_stage_i1_refuses_a_dev_run_without_authorization(tmp_path):
    import dataclasses
    syn = M._synthetic_store(tmp_path / "syn", n_names=4, n_sessions=3)
    cfg = M._smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                          syn["sector_etf_map"], tmp_path / "out", M._smoke_folds(syn["sessions"]), min_names=2,
                          dev_start=syn["sessions"][0], dev_end=syn["sessions"][-1],
                          strategy_config=syn["strategy_config"])
    with pytest.raises(M.GateNotAuthorized, match="without a GateAuthorization"):
        M.run_stage_i1(dataclasses.replace(cfg, run_status="DEV_RUN"), log=lambda *a, **k: None)
    # a real authorization bound to a NON-gate audit is refused too
    auth = M.load_gate_authorization(REPO)
    with pytest.raises(M.GateNotAuthorized, match="not the gate bundle's audit"):
        M.run_stage_i1(dataclasses.replace(cfg, run_status="DEV_RUN", gate=auth), log=lambda *a, **k: None)
    assert not (tmp_path / "out").exists()
