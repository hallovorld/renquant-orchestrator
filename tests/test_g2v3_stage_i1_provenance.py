"""Every Stage I-1 report carries a `provenance` block that `validate_i1_provenance` can REBUILD from disk.

Born from PR #1084 review r1 (codex): "Give the Stage I-1 output the same reproducibility standard before
any dev run: source commit + clean-tree status, exact invocation/run ID and UTC bounds, hashes of the Stage
I-0 gate bundle, pinned strategy config/sector maps, SPY daily input, frozen-parameter block, and aggregate
consumed-bar manifest ... complete that provenance and validate it in tests."

A synthetic smoke run in tmp_path (with the real gate authorization attached so the gate hashes are
exercised) must validate clean; then each provenance claim is falsified one at a time.
"""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
import pathlib
import re
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/experiments/g2v3_stage_i1_bases.py"


def _load():
    spec = importlib.util.spec_from_file_location("g2v3_stage_i1_bases_prov", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load()
G = M.ACCEPTED_GATE_BUNDLE

PROVENANCE_KEYS = {"run_id", "run_status", "outputs", "source", "invocation", "timestamps_utc", "gate_bundle", "inputs",
                   "store_manifest_check", "frozen_parameters", "consumed_bar_manifest"}


@pytest.fixture(scope="module")
def smoke_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("i1prov")
    syn = M._synthetic_store(tmp / "syn", planted=True)
    auth = M.load_gate_authorization(REPO)
    cfg = M._smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                          syn["sector_etf_map"], tmp / "out", M._smoke_folds(syn["sessions"]), min_names=20,
                          dev_start=syn["sessions"][0], dev_end=syn["sessions"][-1],
                          strategy_config=syn["strategy_config"], gate=auth)
    report = M.run_stage_i1(cfg, log=lambda *a, **k: None)
    audit = json.load(gzip.open(tmp / "out" / "g2v3_stage_i1_audit.json.gz"))
    return dict(tmp=tmp, syn=syn, cfg=cfg, auth=auth, report=report, audit=audit)


def _fresh(smoke_run):
    return copy.deepcopy(smoke_run["report"]), copy.deepcopy(smoke_run["audit"])


# --------------------------------------------------------------------------- #
# the block is complete and validates against disk
# --------------------------------------------------------------------------- #
def test_provenance_block_is_complete(smoke_run):
    rep, aud = smoke_run["report"], smoke_run["audit"]
    prov = rep["provenance"]
    assert PROVENANCE_KEYS <= set(prov)
    assert re.match(r"^i1-smoke-\d{8}T\d{6}Z-[0-9a-f]{8}$", prov["run_id"]) and rep["run_id"] == prov["run_id"]
    assert prov["outputs"]["bundle_dir"] == str(smoke_run["tmp"] / "out") and prov["run_status"] == "SMOKE"
    assert re.match(r"^[0-9a-f]{40}$", prov["source"]["commit"]) and isinstance(prov["source"]["clean_tree"], bool)
    assert prov["source"]["repo_root"] == str(M.REPO)
    assert prov["invocation"]["argv"] and "G2V3_BAR_STORE" in prov["invocation"]["env"]
    ts = prov["timestamps_utc"]
    assert ts["start"] <= ts["end"] and ts["start"].endswith("Z") and "own clock" in ts["derivation"]
    assert prov["run_id"].split("-")[2] == ts["start"].replace("-", "").replace(":", "")
    gate = prov["gate_bundle"]
    assert gate["run_id"] == G["run_id"] and gate["frozen_source_commit"] == G["frozen_source_commit"]
    assert gate["report_sha256"] == G["report_sha256"] and gate["audit_sha256"] == G["audit_sha256"]
    assert gate["provenance_sha256"] == M.sha256_file(REPO / G["dir"] / "provenance.json")
    inp = prov["inputs"]
    syn = smoke_run["syn"]
    assert inp["strategy_config"]["sha256"] == M.sha256_file(syn["strategy_config"])
    assert inp["spy_daily"]["sha256"] == M.sha256_file(syn["spy_daily"])
    assert inp["census_audit"]["sha256"] == M.sha256_file(syn["census_audit"])
    assert inp["sector_map_sha256"] == M.sha256_json(syn["sector_map"])
    assert inp["sector_etf_map_sha256"] == M.sha256_json(syn["sector_etf_map"])
    # the full frozen block + the frozen interpretations, byte-identical (the module list carries 12 entries:
    # the progress doc's 11 numbered readings plus the s0-reference reading; the list itself is not edited)
    fp = prov["frozen_parameters"]
    assert fp == dict(rep["frozen"], interpretations=list(M.INTERPRETATIONS))
    assert fp["interpretations"] == rep["interpretations"] == list(M.INTERPRETATIONS) and len(M.INTERPRETATIONS) == 12
    assert fp["xgb_params"] == M.XGB_PARAMS and fp["seed_base"] == 20260828 and fp["features"] == list(M.FEATURE_NAMES)
    # consumed-bar manifest: every file read (30 names + SPY + XLK + XLF), hashed from the store at run time
    man = prov["consumed_bar_manifest"]
    consumed = aud["consumed_sha256"]
    assert man["count"] == len(consumed) == 33
    assert set(consumed) == set(syn["names"]) | {"SPY", "XLK", "XLF"}
    assert man["aggregate_sha256"] == M.manifest_aggregate(consumed)
    for tk, h in consumed.items():
        assert h == M.sha256_file(syn["bar_store"] / f"{tk}.parquet")
    assert rep["inputs"]["gate_run_id"] == G["run_id"]


def test_provenance_validates_clean(smoke_run):
    assert M.validate_i1_provenance(smoke_run["report"], smoke_run["audit"], REPO) == []


def test_manifest_aggregate_is_the_gate_bundle_method():
    # the exact method text of the gate provenance, applied to the gate audit, reproduces the bound aggregate
    hashes = M.load_census_audit(M.GATE_AUDIT)["bar_store_sha256"]
    assert M.manifest_aggregate(hashes) == G["input_manifest_aggregate_sha256"] and len(hashes) == 2124
    assert M.manifest_aggregate({"B": "1", "A": "0"}) == M.hashlib.sha256(b"A 0\nB 1").hexdigest()


# --------------------------------------------------------------------------- #
# each claim falsified one at a time
# --------------------------------------------------------------------------- #
def _problems(rep, aud):
    return M.validate_i1_provenance(rep, aud, REPO)


def test_missing_block_fails(smoke_run):
    rep, aud = _fresh(smoke_run)
    del rep["provenance"]
    assert _problems(rep, aud) == ["report has no provenance block"]


def test_consumed_manifest_tamper_is_caught(smoke_run):
    rep, aud = _fresh(smoke_run)
    first = sorted(aud["consumed_sha256"])[0]
    aud["consumed_sha256"][first] = "0" * 64
    p = _problems(rep, aud)
    assert any("aggregate rebuilt from audit.consumed_sha256" in x for x in p), p
    assert any("not the census-audited files" in x for x in p), p
    rep, aud = _fresh(smoke_run)
    del aud["consumed_sha256"][first]
    assert any("consumed_bar_manifest.count" in x for x in _problems(rep, aud))


def test_input_file_tamper_is_caught(smoke_run):
    rep, aud = _fresh(smoke_run)
    sc = pathlib.Path(rep["provenance"]["inputs"]["strategy_config"]["path"])
    original = sc.read_text(encoding="utf-8")
    try:
        obj = json.loads(original)
        obj["sector_map"]["SYN000"] = "healthcare"
        sc.write_text(json.dumps(obj), encoding="utf-8")
        p = _problems(rep, aud)
        assert any("strategy_config.sha256" in x for x in p), p
        assert any("sector_map_sha256" in x for x in p), p
    finally:
        sc.write_text(original, encoding="utf-8")
    assert _problems(*_fresh(smoke_run)) == []
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["inputs"]["spy_daily"]["sha256"] = "0" * 64
    assert any("spy_daily.sha256" in x for x in _problems(rep, aud))
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["inputs"]["census_audit"]["path"] = str(smoke_run["tmp"] / "nope.gz")
    assert any("census_audit.path missing" in x for x in _problems(rep, aud))


def test_gate_bundle_hash_tamper_is_caught(smoke_run):
    for key in ("report_sha256", "audit_sha256", "provenance_sha256", "frozen_source_commit", "run_id"):
        rep, aud = _fresh(smoke_run)
        rep["provenance"]["gate_bundle"][key] = "0" * 64
        assert any(f"gate_bundle.{key}" in x for x in _problems(rep, aud)), key


def test_frozen_block_and_interpretations_are_checked(smoke_run):
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["frozen_parameters"]["h"] = 12
    p = _problems(rep, aud)
    assert any("frozen_parameters.h = 12" in x for x in p) and any("report.frozen + INTERPRETATIONS" in x for x in p)
    rep, aud = _fresh(smoke_run)
    rep["interpretations"] = rep["interpretations"][:-1] + [rep["interpretations"][-1] + " "]
    assert any("report.interpretations != INTERPRETATIONS" in x for x in _problems(rep, aud))
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["frozen_parameters"]["interpretations"][0] = "changed"
    p = _problems(rep, aud)
    assert any("frozen INTERPRETATIONS (byte-identical)" in x for x in p), p


def test_identity_and_clock_are_checked(smoke_run):
    rep, aud = _fresh(smoke_run)
    ts = rep["provenance"]["timestamps_utc"]
    ts["start"], ts["end"] = "2026-08-29T10:06:40Z", "2026-08-29T10:04:12Z"
    p = _problems(rep, aud)
    assert any("precedes start" in x for x in p), p
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["source"]["commit"] = "f3d5bf7b"
    assert any("not a 40-hex sha" in x for x in _problems(rep, aud))
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["source"]["clean_tree"] = "yes"
    assert any("clean_tree must be a bool" in x for x in _problems(rep, aud))
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["run_id"] = "i1-dev-" + rep["run_id"].split("-")[2] + "-" + rep["provenance"]["source"]["commit"][:8]
    p = _problems(rep, aud)
    assert any("kind disagrees" in x for x in p) and any("report.run_id != provenance.run_id" in x for x in p)
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["run_id"] = rep["run_id"] = "i1-smoke-20260829-" + rep["provenance"]["source"]["commit"][:8]
    assert any("does not match" in x for x in _problems(rep, aud))          # the old date-only form is rejected
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["run_id"] = rep["run_id"] = "i1-smoke-20260829T000000Z-" + rep["provenance"]["source"]["commit"][:8]
    assert any("run_id UTC instant != timestamps_utc.start" in x for x in _problems(rep, aud))
    rep, aud = _fresh(smoke_run)
    rep["provenance"]["invocation"]["argv"] = []
    assert any("invocation.argv" in x for x in _problems(rep, aud))


def test_dev_run_provenance_demands_the_gate_and_the_frozen_folds(smoke_run):
    """A report that CLAIMS DEV_RUN is held to the gate bundle, the pinned config and the frozen folds."""
    rep, aud = _fresh(smoke_run)
    rep["run_status"] = rep["provenance"]["run_status"] = "DEV_RUN"
    rep["run_id"] = rep["provenance"]["run_id"] = rep["run_id"].replace("smoke", "dev")
    rep["provenance"]["gate_bundle"] = None
    rep["provenance"]["invocation"]["env"]["G2V3_BAR_STORE"] = None
    p = _problems(rep, aud)
    assert any("DEV_RUN provenance has no gate_bundle" in x for x in p), p
    assert any("G2V3_BAR_STORE is empty" in x for x in p), p
    assert any("not the gate bundle's audit" in x for x in p), p
    assert any("DEV_RUN frozen_parameters.folds" in x for x in p), p            # the smoke's tiny folds
    assert any("DEV_RUN frozen_parameters.min_names_per_ic" in x for x in p), p
    # r3: a DEV_RUN claim is also held to a strict, complete store manifest, the bound absent set and its own bundle
    assert any("store_manifest_check.strict is not True" in x for x in p), p
    assert any("absent_from_audit ['XLV'] != EXPECTED_ABSENT_FROM_AUDIT" in x for x in p), p
    assert any("outputs.bundle_dir" in x and "not <outputs.root>/<run_id>/" in x for x in p), p
    rep, aud = _fresh(smoke_run)
    rep["run_status"] = rep["provenance"]["run_status"] = "DEV_RUN"
    rep["run_id"] = rep["provenance"]["run_id"] = rep["run_id"].replace("smoke", "dev")
    rep["provenance"]["source"]["clean_tree"] = False
    assert any("DEV_RUN source.clean_tree is not True" in x for x in _problems(rep, aud))


def test_smoke_report_on_disk_carries_the_same_provenance(smoke_run):
    on_disk = json.load(open(smoke_run["tmp"] / "out" / "report.json"))
    assert on_disk["provenance"] == smoke_run["report"]["provenance"]
    assert M.validate_i1_provenance(on_disk, smoke_run["audit"], REPO) == []
