"""The Stage I-2 --dev-run entry point must FAIL CLOSED: I-1 binding, determinism guard, tree / bundle / store
preflight, CLI exit 2 — and every report's provenance must rebuild from disk (`validate_i2_provenance`).

Prereg §1 binding: "verified on disk before any bar is read; --dev-run refuses otherwise (exit 2), refuses a dirty
tree, refuses an existing output bundle". §1.1: "fails closed unless every re-fit reproduces the I-1 overall block-t
to 4 decimals ... A mismatch is a determinism defect, not a result."

Negative binding cases run on tmp_path copies of the committed I-1 bundle (mutated one field at a time, the bound
hash re-pointed at the mutated file so the FIELD check is what fires); the positive case is the exact committed
bundle in this repository. The determinism guard is exercised in the real run flow on a synthetic store with the
meta fit forbidden. Nothing here runs --dev-run on the development bar store; every DEV_RUN configuration below is
refused before a single parquet is opened.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import gzip
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys

import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/experiments/g2v3_stage_i2_stack.py"


def _load():
    spec = importlib.util.spec_from_file_location("g2v3_stage_i2_stack_binding", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load()
I1 = M.I1
B = M.ACCEPTED_I1_BUNDLE
SILENT = dict(log=lambda *a, **k: None)
FIXED_NOW = dt.datetime(2026, 8, 29, 14, 0, 0, tzinfo=dt.timezone.utc)


def _forbid_parquet_reads(monkeypatch):
    def boom(*a, **k):
        raise AssertionError(f"parquet read before the preflight refused: {a[:1]}")
    monkeypatch.setattr(pd, "read_parquet", boom)


def _forbid_meta_fit(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a meta-learner was fitted although the run must have been refused before it")
    monkeypatch.setattr(M, "fit_meta", boom)


# --------------------------------------------------------------------------- #
# the frozen binding == the committed bundle, and the positive case
# --------------------------------------------------------------------------- #
def test_bound_constants_are_the_committed_i1_bundle_field_for_field():
    bundle = REPO / B["dir"]
    assert M.sha256_file(bundle / B["report_file"]) == B["report_sha256"]
    assert M.sha256_file(bundle / B["audit_file"]) == B["audit_sha256"]
    rep = json.loads((bundle / B["report_file"]).read_text(encoding="utf-8"))
    assert rep["run_status"] == "DEV_RUN" and rep["run_id"] == B["run_id"] and rep["stage"] == B["stage"]
    assert rep["provenance"]["source"]["commit"] == B["source_commit"] and rep["provenance"]["source"]["clean_tree"] is True
    assert rep["provenance"]["consumed_bar_manifest"]["aggregate_sha256"] == B["consumed_bar_aggregate_sha256"]
    assert rep["provenance"]["consumed_bar_manifest"]["count"] == B["consumed_bar_count"] == 1508
    assert rep["provenance"]["gate_bundle"]["run_id"] == B["gate_run_id"] == M.ACCEPTED_GATE_BUNDLE["run_id"]
    assert rep["stage_i2_trigger"]["fired"] is True
    for bb in ("B0", "B1", "B2", "B3"):
        assert rep["bases"][bb]["overall"]["block_t"] == M.EXPECTED_I1_BLOCK_T[bb]
        assert rep["bases"][bb]["overall"]["n_blocks"] == M.EXPECTED_I1_N_BLOCKS[bb]
        assert rep["bases"][bb]["passes_life_bar"] is True
    assert rep["s0_reference"]["overall"]["block_t"] == B["s0_block_t"]
    consumed = json.load(gzip.open(bundle / B["audit_file"]))["consumed_sha256"]
    assert M.manifest_aggregate(consumed) == B["consumed_bar_aggregate_sha256"] and len(consumed) == 1508
    # the I-1 harness this module imports is the blob at the bundle's commit
    assert M.sha256_file(REPO / M.I1_HARNESS_PATH) == M.I1_HARNESS_SHA256
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{B['source_commit']}:{M.I1_HARNESS_PATH}"],
                          capture_output=True, check=True).stdout
    assert M.hashlib.sha256(blob).hexdigest() == M.I1_HARNESS_SHA256


def test_committed_bundle_is_bound():
    b = M.load_i1_binding(REPO)
    assert b.run_id == B["run_id"] and b.source_commit == B["source_commit"]
    assert b.report_sha256 == B["report_sha256"] and b.audit_sha256 == B["audit_sha256"]
    assert b.consumed_bar_aggregate_sha256 == B["consumed_bar_aggregate_sha256"] and b.consumed_bar_count == 1508
    assert b.harness_sha256 == M.I1_HARNESS_SHA256 and b.surviving_bases == ("B0", "B1", "B2", "B3")
    assert b.block_t == M.EXPECTED_I1_BLOCK_T and b.n_blocks == M.EXPECTED_I1_N_BLOCKS
    rec = b.as_record()
    assert rec["expected_block_t"] == M.EXPECTED_I1_BLOCK_T and rec["surviving_bases"] == ["B0", "B1", "B2", "B3"]


# --------------------------------------------------------------------------- #
# negative binding cases on a faithful copy (no git) — file checks, one field at a time
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake(tmp_path):
    root = tmp_path / "repo"
    dst = root / B["dir"]
    shutil.copytree(REPO / B["dir"], dst)
    h = root / M.I1_HARNESS_PATH
    h.parent.mkdir(parents=True)
    shutil.copyfile(REPO / M.I1_HARNESS_PATH, h)
    return root


def _refused(root, match):
    with pytest.raises(M.I1NotBound, match=match):
        M._verify_i1_bundle_files(root)


def _report(root):
    return json.loads((root / B["dir"] / B["report_file"]).read_text(encoding="utf-8"))


def _rewrite_report(root, monkeypatch, rep):
    """Write a mutated report and re-point the bound hash at it, so the FIELD check is what refuses."""
    p = root / B["dir"] / B["report_file"]
    p.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    monkeypatch.setattr(M, "ACCEPTED_I1_BUNDLE", dict(B, report_sha256=M.sha256_file(p)))


def test_faithful_copy_passes_the_file_checks(fake):
    b = M._verify_i1_bundle_files(fake)
    assert b.run_id == B["run_id"] and b.bundle_dir == fake / B["dir"]


def test_missing_bundle_report_or_audit_is_refused(fake):
    (fake / B["dir"] / B["audit_file"]).unlink()
    _refused(fake, "g2v3_stage_i1_audit.json.gz missing")
    (fake / B["dir"] / B["report_file"]).unlink()
    _refused(fake, "report.json missing")
    shutil.rmtree(fake / B["dir"])
    _refused(fake, "bundle directory missing")


def test_tampered_report_or_audit_is_refused_by_hash(fake):
    p = fake / B["dir"] / B["report_file"]
    p.write_text(p.read_text(encoding="utf-8").replace("3.5042", "3.5043"), encoding="utf-8")
    _refused(fake, r"report.json sha256 on disk .* != bound .* \(tampered\)")
    shutil.copyfile(REPO / B["dir"] / B["report_file"], p)
    a = fake / B["dir"] / B["audit_file"]
    a.write_bytes(a.read_bytes() + b"\n")
    _refused(fake, r"g2v3_stage_i1_audit.json.gz sha256 on disk .* \(tampered\)")


@pytest.mark.parametrize("status", ["SMOKE", "DEVELOPMENT_ONLY", "GATE_RUN", None])
def test_non_dev_run_status_is_refused(fake, monkeypatch, status):
    rep = _report(fake)
    rep["run_status"] = status
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, f"report run_status {status!r} != 'DEV_RUN'")


def test_wrong_run_id_is_refused(fake, monkeypatch):
    rep = _report(fake)
    rep["run_id"] = "i1-dev-20260829T000000Z-deadbeef"
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "report run_id = 'i1-dev-20260829T000000Z-deadbeef', this harness is bound to 'i1-dev-20260829T113813Z-666484a7'")


def test_wrong_source_commit_or_dirty_i1_tree_is_refused(fake, monkeypatch):
    rep = _report(fake)
    rep["provenance"]["source"]["commit"] = "0" * 40
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "provenance.source.commit")
    rep = _report(REPO)
    rep["provenance"]["source"]["clean_tree"] = False
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "provenance.source.clean_tree = False")


def test_i1_bound_to_a_different_gate_is_refused(fake, monkeypatch):
    rep = _report(fake)
    rep["provenance"]["gate_bundle"]["run_id"] = "i0-gate-20260827-00000000"
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "provenance.gate_bundle.run_id")


def test_trigger_not_fired_or_a_base_not_surviving_is_refused(fake, monkeypatch):
    rep = _report(fake)
    rep["stage_i2_trigger"]["fired"] = False
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "stage_i2_trigger.fired = False")
    rep = _report(REPO)
    rep["bases"]["B3"]["passes_life_bar"] = False
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, r"surviving bases \('B0', 'B1', 'B2'\) != bound \('B0', 'B1', 'B2', 'B3'\) \(interpretation 1\)")


def test_block_t_or_n_blocks_disagreeing_with_the_constants_is_refused(fake, monkeypatch):
    rep = _report(fake)
    rep["bases"]["B2"]["overall"]["block_t"] = 3.5916
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, r"bases.B2.overall block_t/n_blocks = 3.5916/622, bound 3.5915/622")
    rep = _report(REPO)
    rep["bases"]["B1"]["overall"]["n_blocks"] = 510
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, r"bases.B1.overall block_t/n_blocks = 3.1837/510, bound 3.1837/511")
    rep = _report(REPO)
    rep["s0_reference"]["overall"]["block_t"] = 4.19
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "s0_reference.overall.block_t = 4.19")


def test_consumed_bar_manifest_disagreeing_is_refused(fake, monkeypatch):
    rep = _report(fake)
    rep["provenance"]["consumed_bar_manifest"]["aggregate_sha256"] = "f" * 64
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "provenance.consumed_bar_manifest.aggregate_sha256")
    # the audit's consumed map itself (rebuilt aggregate) — report restored intact, audit re-pointed
    shutil.copyfile(REPO / B["dir"] / B["report_file"], fake / B["dir"] / B["report_file"])
    a = fake / B["dir"] / B["audit_file"]
    audit = json.load(gzip.open(REPO / B["dir"] / B["audit_file"]))
    audit["consumed_sha256"].pop(sorted(audit["consumed_sha256"])[0])
    with gzip.open(a, "wt") as fh:
        json.dump(audit, fh)
    monkeypatch.setattr(M, "ACCEPTED_I1_BUNDLE", dict(B, audit_sha256=M.sha256_file(a)))
    _refused(fake, r"consumed-bar aggregate recomputed from the audit = .* over 1507 files, bound .* over 1508")


def test_i1_frozen_block_disagreeing_with_the_imported_i1_constants_is_refused(fake, monkeypatch):
    rep = _report(fake)
    rep["frozen"]["xgb_params"]["max_depth"] = 4
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "frozen.xgb_params")
    rep = _report(REPO)
    rep["frozen"]["folds"][0][0] = "2021-12-30"
    _rewrite_report(fake, monkeypatch, rep)
    _refused(fake, "frozen.folds")


def test_i1_harness_changed_or_missing_is_refused(fake):
    h = fake / M.I1_HARNESS_PATH
    h.write_text(h.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    _refused(fake, r"g2v3_stage_i1_bases.py on disk hashes to .*, bound 13c31d126.*would not be the I-1 code")
    h.unlink()
    _refused(fake, "g2v3_stage_i1_bases.py missing from the checkout")


def test_faithful_copy_outside_the_reviewed_repository_is_not_a_binding(fake):
    subprocess.run(["git", "-C", str(fake), "init", "-q"], check=True)
    with pytest.raises(M.I1NotBound, match="I-1 source commit 666484a7 is not resolvable"):
        M.load_i1_binding(fake)


def test_harness_blob_at_the_commit_must_hash_to_the_constant(monkeypatch):
    real_git = I1._git

    def fake_git(root, *args):
        r = real_git(root, *args)
        if args[0] == "show":
            return subprocess.CompletedProcess(args, 0, stdout=b"# not the harness\n", stderr=b"")
        return r
    monkeypatch.setattr(I1, "_git", fake_git)
    with pytest.raises(M.I1NotBound, match=r"at 666484a7 hashes to .*, bound 13c31d126"):
        M.load_i1_binding(REPO)


# --------------------------------------------------------------------------- #
# determinism guard in the real run flow: refused BEFORE any meta fit, nothing written
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def small_syn(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("i2det")
    syn = I1._synthetic_store(tmp / "syn", n_names=24, n_sessions=30, planted=True)
    cfg = M._smoke_config(M.smoke_base_config(syn, tmp / "out0"), tmp / "out0")
    rep = M.run_stage_i2(cfg, **SILENT)
    observed_t = {bb: rep["base_refit"]["bases"][bb]["overall"]["block_t"] for bb in M.BASE_CODES}
    observed_n = {bb: rep["base_refit"]["bases"][bb]["overall"]["n_blocks"] for bb in M.BASE_CODES}
    s0 = (rep["base_refit"]["s0_reference"]["overall"]["block_t"], rep["base_refit"]["s0_reference"]["overall"]["n_blocks"])
    return dict(tmp=tmp, syn=syn, t=observed_t, n=observed_n, s0=s0, report=rep)


def test_determinism_guard_off_by_1e4_refuses_before_any_meta_fit(small_syn, monkeypatch):
    _forbid_meta_fit(monkeypatch)
    off = dict(small_syn["t"], B0=round(small_syn["t"]["B0"] + 1e-4, 4))
    out = small_syn["tmp"] / "out_refused"
    cfg = M._smoke_config(M.smoke_base_config(small_syn["syn"], out), out, expected_block_t=off,
                          expected_n_blocks=small_syn["n"], expected_s0=small_syn["s0"])
    with pytest.raises(M.DeterminismRefused, match=r"B0: block_t .* @ 4 dp.* no meta-learner was fitted"):
        M.run_stage_i2(cfg, **SILENT)
    assert not out.exists()                                            # nothing written
    off_n = dict(small_syn["n"], B3=small_syn["n"]["B3"] + 1)
    cfg = M._smoke_config(M.smoke_base_config(small_syn["syn"], out), out, expected_block_t=small_syn["t"],
                          expected_n_blocks=off_n, expected_s0=small_syn["s0"])
    with pytest.raises(M.DeterminismRefused, match="B3: .*n_blocks"):
        M.run_stage_i2(cfg, **SILENT)
    assert not out.exists()


def test_determinism_guard_exact_proceeds_to_the_meta_fit(small_syn):
    out = small_syn["tmp"] / "out_ok"
    cfg = M._smoke_config(M.smoke_base_config(small_syn["syn"], out), out, expected_block_t=small_syn["t"],
                          expected_n_blocks=small_syn["n"], expected_s0=small_syn["s0"])
    rep = M.run_stage_i2(cfg, **SILENT)
    g = rep["base_refit"]["determinism_guard"]
    assert g["status"] == "PASS" and set(g["per_series"]) == {"B0", "B1", "B2", "B3", "s0"}
    assert all(v["match"] for v in g["per_series"].values())
    assert rep["provenance"]["determinism_guard"] == g
    assert rep["series"]["M_xgb"]["overall"]["block_t"] is not None
    # the re-fit is deterministic run to run on this machine (interpretation 5)
    assert {bb: rep["base_refit"]["bases"][bb]["overall"]["block_t"] for bb in M.BASE_CODES} == small_syn["t"]
    assert (rep["series"]["M_xgb"]["overall"]["block_t"]
            == small_syn["report"]["series"]["M_xgb"]["overall"]["block_t"])


def test_consumed_bars_differing_from_the_i1_bundle_refuse_before_any_base_fit(small_syn, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a base was fitted although the consumed-bar check must refuse first")
    monkeypatch.setattr(I1, "run_bases", boom)
    _forbid_meta_fit(monkeypatch)
    out = small_syn["tmp"] / "out_bars"
    cfg = M._smoke_config(M.smoke_base_config(small_syn["syn"], out), out, expected_consumed_aggregate="a" * 64)
    with pytest.raises(M.DeterminismRefused, match="the bars consumed by this run aggregate to .* the I-1 bundle consumed aaaaaaaaaaaa"):
        M.run_stage_i2(cfg, **SILENT)
    assert not out.exists()


# --------------------------------------------------------------------------- #
# DEV_RUN preflight on a real tmp git repository: dirty tree, existing bundle, then the store check
# --------------------------------------------------------------------------- #
def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def dev_cfg(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    auth = I1.load_gate_authorization(REPO)
    i1 = M.load_i1_binding(REPO)
    syn = I1._synthetic_store(tmp_path / "syn", n_names=3, n_sessions=2)
    etf_map = {"tech": "XLK", "healthcare": "XLV", "bond": "TLT", "telecom": "XLC", "real_estate": "XLRE"}
    monkeypatch.setattr(M, "REPO", repo)
    monkeypatch.setattr(M, "_now_utc", lambda: FIXED_NOW)
    out_root = repo / "doc/research/data/2026-08-29-g2v3-i2"
    base = I1.RunConfig(bar_store=syn["bar_store"], census_audit=I1.GATE_AUDIT, spy_daily=syn["spy_daily"],
                        sector_map={}, sector_etf_map=etf_map, out_dir=out_root, run_status="DEV_RUN", gate=auth,
                        strategy_config=syn["strategy_config"])
    cfg = M.I2Config(base=base, out_dir=out_root, run_status="DEV_RUN", i1=i1,
                     expected_block_t=dict(M.EXPECTED_I1_BLOCK_T), expected_n_blocks=dict(M.EXPECTED_I1_N_BLOCKS),
                     expected_s0=(B["s0_block_t"], B["s0_n_blocks"]),
                     expected_consumed_aggregate=B["consumed_bar_aggregate_sha256"])
    return dict(cfg=cfg, repo=repo, out_root=out_root, sha=_git(repo, "rev-parse", "HEAD"))


def test_dev_run_without_an_i1_binding_or_with_foreign_targets_is_refused(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    with pytest.raises(M.I1NotBound, match="DEV_RUN without an I1Binding"):
        M.run_stage_i2(dataclasses.replace(dev_cfg["cfg"], i1=None), **SILENT)
    with pytest.raises(M.DevRunRefused, match="determinism targets are not the frozen constants"):
        M.run_stage_i2(dataclasses.replace(dev_cfg["cfg"], expected_block_t=dict(M.EXPECTED_I1_BLOCK_T, B0=3.5)), **SILENT)
    with pytest.raises(M.DevRunRefused, match="determinism targets are not the frozen constants"):
        M.run_stage_i2(dataclasses.replace(dev_cfg["cfg"], expected_s0=None), **SILENT)
    with pytest.raises(M.GateNotAuthorized, match="DEV_RUN without a GateAuthorization"):
        M.run_stage_i2(dataclasses.replace(dev_cfg["cfg"], base=dataclasses.replace(dev_cfg["cfg"].base, gate=None)),
                       **SILENT)
    assert not dev_cfg["out_root"].exists()


def test_dirty_tree_is_refused_before_anything_is_read_or_written(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    (dev_cfg["repo"] / "stray.txt").write_text("x")
    with pytest.raises(M.DevRunRefused, match=r"source tree is not clean: 1 entries .*stray.txt"):
        M.run_stage_i2(dev_cfg["cfg"], **SILENT)
    assert not dev_cfg["out_root"].exists()


def test_existing_bundle_is_refused_no_overwrite(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    run_id = f"i2-dev-20260829T140000Z-{dev_cfg['sha'][:8]}"
    bundle = dev_cfg["out_root"] / run_id
    bundle.mkdir(parents=True)
    (bundle / "report.json").write_text("{}")
    with pytest.raises(M.DevRunRefused, match=f"output bundle .*{run_id} already exists; refusing to overwrite"):
        M.run_stage_i2(dev_cfg["cfg"], **SILENT)
    assert (bundle / "report.json").read_text() == "{}"


def test_clean_and_fresh_proceeds_to_the_store_check(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    src = I1.source_state(dev_cfg["repo"], ignore=[dev_cfg["cfg"].base.bar_store, dev_cfg["out_root"]])
    run_id, bundle = M.dev_run_identity(dev_cfg["cfg"], src, FIXED_NOW)
    assert run_id == f"i2-dev-20260829T140000Z-{dev_cfg['sha'][:8]}" and M._RUN_ID.match(run_id)
    assert bundle == dev_cfg["out_root"] / run_id and not bundle.exists()
    with pytest.raises(M.StoreNotAudited, match=r"of the \d+ audited files this run needs are missing"):
        M.run_stage_i2(dev_cfg["cfg"], **SILENT)
    assert not dev_cfg["out_root"].exists()
    with pytest.raises(M.DevRunRefused, match="cannot establish the source commit"):
        M.dev_run_identity(dev_cfg["cfg"], dict(commit=None, clean_tree=None, error="no git"), FIXED_NOW)


def test_cli_dev_run_exits_2_without_the_gate_or_the_i1_bundle_or_on_a_dirty_tree(tmp_path, dev_cfg, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(M, "REPO", empty)                       # no gate bundle => refused FIRST, exit 2
    assert M.main(["--dev-run"]) == 2
    assert "REFUSED --dev-run (fail closed): Stage I-0 gate bundle" in capsys.readouterr().err
    monkeypatch.setattr(I1, "load_gate_authorization", lambda root: dev_cfg["cfg"].base.gate)
    assert M.main(["--dev-run"]) == 2                            # gate fine, I-1 bundle missing => exit 2
    assert "REFUSED --dev-run (fail closed): Stage I-1 bundle" in capsys.readouterr().err
    monkeypatch.setattr(M, "REPO", dev_cfg["repo"])
    monkeypatch.setattr(M, "load_i1_binding", lambda root: dev_cfg["cfg"].i1)
    monkeypatch.setattr(M, "dev_run_config", lambda auth, i1: dev_cfg["cfg"])
    (dev_cfg["repo"] / "stray.txt").write_text("x")
    assert M.main(["--dev-run"]) == 2
    assert "REFUSED --dev-run (fail closed): source tree is not clean" in capsys.readouterr().err
    assert not dev_cfg["out_root"].exists()


# --------------------------------------------------------------------------- #
# provenance: a smoke with the real gate authorization + I-1 binding attached validates clean; then each claim
# is falsified one at a time
# --------------------------------------------------------------------------- #
PROVENANCE_KEYS = {"run_id", "run_status", "outputs", "source", "invocation", "timestamps_utc", "gate_bundle",
                   "i1_bundle", "inputs", "store_manifest_check", "frozen_parameters", "consumed_bar_manifest",
                   "determinism_guard"}


@pytest.fixture(scope="module")
def prov_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("i2prov")
    syn = I1._synthetic_store(tmp / "syn", n_names=24, n_sessions=30, planted=True)
    auth = I1.load_gate_authorization(REPO)
    i1 = M.load_i1_binding(REPO)
    cfg = M._smoke_config(M.smoke_base_config(syn, tmp / "out", gate=auth), tmp / "out", i1=i1)
    report = M.run_stage_i2(cfg, **SILENT)
    audit = json.load(gzip.open(tmp / "out" / "g2v3_stage_i2_audit.json.gz"))
    return dict(tmp=tmp, report=report, audit=audit)


def _fresh(prov_run):
    return copy.deepcopy(prov_run["report"]), copy.deepcopy(prov_run["audit"])


def test_provenance_is_complete_and_validates_clean(prov_run):
    rep, aud = prov_run["report"], prov_run["audit"]
    prov = rep["provenance"]
    assert PROVENANCE_KEYS <= set(prov)
    assert prov["gate_bundle"]["run_id"] == M.ACCEPTED_GATE_BUNDLE["run_id"]
    assert prov["i1_bundle"]["run_id"] == B["run_id"] and prov["i1_bundle"]["harness_sha256"] == M.I1_HARNESS_SHA256
    assert prov["frozen_parameters"]["interpretations"] == M.INTERPRETATIONS
    assert prov["consumed_bar_manifest"]["aggregate_sha256"] == M.manifest_aggregate(aud["consumed_sha256"])
    assert M.validate_i2_provenance(rep, aud, REPO) == []
    on_disk = json.load(open(prov_run["tmp"] / "out" / "report.json"))
    assert M.validate_i2_provenance(on_disk, aud, REPO) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda r, a: r["provenance"]["i1_bundle"].update(report_sha256="0" * 64), "i1_bundle.report_sha256"),
    (lambda r, a: r["provenance"]["i1_bundle"].update(harness_sha256="0" * 64), "i1_bundle.harness_sha256"),
    (lambda r, a: r["provenance"]["i1_bundle"].update(expected_block_t={"B0": 1.0}), "i1_bundle.expected_block_t"),
    (lambda r, a: r["provenance"]["gate_bundle"].update(audit_sha256="0" * 64), "gate_bundle.audit_sha256"),
    (lambda r, a: a["consumed_sha256"].pop(sorted(a["consumed_sha256"])[0]), "consumed_bar_manifest.count"),
    (lambda r, a: a["consumed_sha256"].update({sorted(a["consumed_sha256"])[0]: "f" * 64}), "aggregate rebuilt"),
    (lambda r, a: r["provenance"]["frozen_parameters"].update(meta_xgb_params=dict(M.META_XGB_PARAMS, max_depth=3)),
     "frozen_parameters.meta_xgb_params"),
    (lambda r, a: r["provenance"]["frozen_parameters"]["interpretations"].pop(), "byte-identical"),
    (lambda r, a: r["interpretations"].__setitem__(0, "edited"), "report.interpretations != INTERPRETATIONS"),
    (lambda r, a: r["prereg_interpretations"].pop(), "prereg_interpretations != the prereg's six"),
    (lambda r, a: r["outcome"].update(verdict="REFUSED"), "not a §4.4 result row"),
    (lambda r, a: r["outcome"].update(consequence="edited"), "outcome row text != OUTCOME_REGISTER"),
    (lambda r, a: r["pass_bar"].update(stage_i2_pass=not r["pass_bar"]["stage_i2_pass"]), "stage_i2_pass != P1"),
    (lambda r, a: (r["pass_bar"].update(stage_i2_pass=True),
                   [r["pass_bar"][k].update(passes=True) for k in ("P1", "P2", "P3")]),
     "outcome.verdict != the register row"),
    (lambda r, a: r["outcome"].update(binding=True), "outcome.binding"),
    (lambda r, a: r["provenance"].update(run_id="i1-smoke-20260829T140000Z-deadbeef"), "does not match i2-"),
    (lambda r, a: r["provenance"]["timestamps_utc"].update(end="2020-01-01T00:00:00Z"), "precedes start"),
    (lambda r, a: r["provenance"]["source"].update(commit="abc"), "not a 40-hex sha"),
    (lambda r, a: r["provenance"]["invocation"].update(env={}), "must record G2V3_BAR_STORE"),
    (lambda r, a: r["provenance"]["inputs"]["spy_daily"].update(sha256="0" * 64), "inputs.spy_daily.sha256"),
    (lambda r, a: r["provenance"]["inputs"].update(sector_map_sha256="0" * 64), "sector_map_sha256"),
    (lambda r, a: r["provenance"]["determinism_guard"].update(status="X"), "provenance.determinism_guard != report"),
    (lambda r, a: r["provenance"]["store_manifest_check"].update(expected_absent_from_audit=[]), "expected_absent_from_audit"),
    (lambda r, a: r["provenance"].pop("consumed_bar_manifest"), "consumed_bar_manifest missing"),
    (lambda r, a: r["provenance"].pop("determinism_guard"), "determinism_guard missing"),
])
def test_each_provenance_claim_is_falsifiable(prov_run, mutate, expect):
    rep, aud = _fresh(prov_run)
    mutate(rep, aud)
    problems = M.validate_i2_provenance(rep, aud, REPO)
    assert any(expect in p for p in problems), (expect, problems)


def test_dev_run_claims_are_held_to_the_frozen_folds_guard_and_bundles(prov_run):
    """Relabelling the smoke as DEV_RUN must surface every DEV_RUN-only requirement."""
    rep, aud = _fresh(prov_run)
    rep["run_status"] = rep["provenance"]["run_status"] = "DEV_RUN"
    rep["run_id"] = rep["provenance"]["run_id"] = rep["run_id"].replace("i2-smoke-", "i2-dev-")
    rep["outcome"]["binding"] = True
    problems = M.validate_i2_provenance(rep, aud, REPO)
    joined = "\n".join(problems)
    assert "DEV_RUN frozen_parameters.meta_folds" in joined          # the smoke used the tiny folds
    assert "DEV_RUN frozen_parameters.i1.folds" in joined
    assert "DEV_RUN determinism_guard.status = 'NOT_APPLIED', not PASS" in joined
    assert "DEV_RUN consumed-bar aggregate != the I-1 bundle's" in joined
    assert "DEV_RUN store_manifest_check.strict is not True" in joined
    assert "DEV_RUN census audit is not the gate bundle's audit" in joined
    assert "DEV_RUN outputs.bundle_dir" in joined
