"""--dev-run preflight (PR #1084 review r2 by codex): the store manifest is checked BEFORE any bar is read and a
DEV_RUN refuses an incomplete store, a dirty source tree and an existing output bundle.

r2 asks, verbatim: (1) "require every file in the computed `needed` set that exists in the gate audit to be present
and hash-matching before loading any data. If absent sector ETFs are an intentional frozen exception, bind the exact
expected absent set" — tests: missing eligible name, missing audited sector ETF, hash mismatch, unbound absent set,
complete store passes, nothing read before the check. (2) "Make DEV_RUN refuse a non-clean source tree (excluding
only declared input/output paths), use a unique UTC run identity with its own output bundle directory, and fail if
that bundle already exists. Keep smoke ergonomics separate." — tests: dirty tree refused (a real `git status` on a
tmp repository), untracked files under the declared bar store / output root are not dirt, existing bundle refused,
clean + fresh proceeds (to the store check, which is where a synthetic store is refused), smoke keeps its fixed dir.

Nothing here runs --dev-run on the development bar store; every DEV_RUN configuration below is refused before a
single parquet is opened.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import gzip
import importlib.util
import json
import pathlib
import subprocess
import sys

import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/experiments/g2v3_stage_i1_bases.py"


def _load():
    spec = importlib.util.spec_from_file_location("g2v3_stage_i1_bases_preflight", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load()
SILENT = dict(log=lambda *a, **k: None)
FIXED_NOW = dt.datetime(2026, 8, 29, 10, 15, 0, tzinfo=dt.timezone.utc)


def _forbid_parquet_reads(monkeypatch):
    """Any parquet read before the manifest check passes is a test failure, not a refusal."""
    def boom(*a, **k):
        raise AssertionError(f"parquet read before the store manifest check: {a[:1]}")
    monkeypatch.setattr(pd, "read_parquet", boom)


# --------------------------------------------------------------------------- #
# (1) store manifest, strict (DEV_RUN) mode, on a synthetic store whose audit-absent ETF set is {XLV}
# --------------------------------------------------------------------------- #
@pytest.fixture
def syn(tmp_path):
    return M._synthetic_store(tmp_path / "syn", n_names=12, n_sessions=6)


def _audit(syn):
    return M.load_census_audit(syn["census_audit"])


def _strict(syn, audit=None, expected=frozenset({"XLV"}), **kw):
    audit = audit if audit is not None else _audit(syn)
    return M.check_store_manifest(syn["bar_store"], audit, syn["sessions"], syn["sector_etf_map"], strict=True,
                                  expected_absent=expected, **kw)


def test_bound_absent_set_is_exactly_the_gate_audits_missing_sector_etfs():
    """The frozen exception equals what the committed gate audit actually lacks, computed here, not asserted."""
    assert M.EXPECTED_ABSENT_FROM_AUDIT == frozenset({"TLT", "XLC", "XLRE", "XLV"})
    files = set(M.load_census_audit(M.GATE_AUDIT)["bar_store_sha256"])
    for etf in M.EXPECTED_ABSENT_FROM_AUDIT:
        assert etf not in files, etf
    for etf in ("SPY", "GLD", "XLE", "XLF", "XLI", "XLK", "XLU", "XLY"):     # the ETFs the audit DOES carry
        assert etf in files, etf


def test_complete_store_passes_strict_and_hashes_every_needed_file(syn, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    m = _strict(syn)
    assert m["absent_from_audit"] == ["XLV"] and m["missing"] == []
    assert set(m["required"]) == set(syn["names"]) | {"SPY", "XLK", "XLF"}
    assert set(m["actual"]) == set(m["required"]) and "XLV" not in m["actual"]
    for tk, h in m["actual"].items():
        assert h == M.sha256_file(syn["bar_store"] / f"{tk}.parquet")


def test_missing_eligible_name_is_refused_before_any_read(syn, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    (syn["bar_store"] / "SYN003.parquet").unlink()
    with pytest.raises(M.StoreNotAudited, match=r"1 of the 15 audited files .* missing .*\['SYN003'\]"):
        _strict(syn)
    # non-strict (SMOKE) records it and continues — the ergonomics the dev run no longer has
    m = M.check_store_manifest(syn["bar_store"], _audit(syn), syn["sessions"], syn["sector_etf_map"], strict=False)
    assert m["missing"] == ["SYN003"] and "SYN003" not in m["actual"]


def test_missing_audited_sector_etf_is_refused(syn, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    (syn["bar_store"] / "XLF.parquet").unlink()
    with pytest.raises(M.StoreNotAudited, match=r"missing from the bar store .*\['XLF'\]"):
        _strict(syn)


def test_missing_spy_is_refused(syn, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    (syn["bar_store"] / "SPY.parquet").unlink()
    with pytest.raises(M.StoreNotAudited, match=r"\['SPY'\]"):
        _strict(syn)


def test_hash_mismatched_file_is_refused(syn, monkeypatch):
    p = syn["bar_store"] / "SYN005.parquet"
    df = pd.read_parquet(p)
    df.loc[0, "close"] *= 1.001
    df.to_parquet(p)
    _forbid_parquet_reads(monkeypatch)
    with pytest.raises(M.StoreNotAudited, match=r"1 hash mismatches \(e.g. \['SYN005'\]\)"):
        _strict(syn)


def test_absent_set_must_equal_the_bound_constant(syn, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    with pytest.raises(M.StoreNotAudited, match=r"absent from the gate audit = \['XLV'\].*bound to \[\].*re-binding"):
        _strict(syn, expected=frozenset())
    with pytest.raises(M.StoreNotAudited, match="EXPECTED_ABSENT_FROM_AUDIT"):
        _strict(syn, expected=M.EXPECTED_ABSENT_FROM_AUDIT)              # the real bound set != this store's
    # an ETF that IS in the audit but is missing from the store is "missing", never silently "absent"
    (syn["bar_store"] / "XLK.parquet").unlink()
    with pytest.raises(M.StoreNotAudited, match=r"missing from the bar store .*\['XLK'\]"):
        _strict(syn)


def test_eligible_name_absent_from_the_audit_file_set_is_refused(syn, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    audit = _audit(syn)
    del audit["bar_store_sha256"]["SYN002"]
    with pytest.raises(M.StoreNotAudited, match=r"1 eligible names / SPY are absent from the gate audit's file set"):
        _strict(syn, audit=audit)
    audit = _audit(syn)
    del audit["bar_store_sha256"]["SPY"]
    with pytest.raises(M.StoreNotAudited, match=r"\['SPY'\].*cannot vouch"):
        _strict(syn, audit=audit)


def test_unaudited_present_file_is_refused_in_both_modes(syn, monkeypatch):
    pd.read_parquet(syn["bar_store"] / "SYN000.parquet").to_parquet(syn["bar_store"] / "XLV.parquet")
    _forbid_parquet_reads(monkeypatch)
    with pytest.raises(M.StoreNotAudited, match=r"1 files absent from the audit \(e.g. \['XLV'\]\)"):
        _strict(syn)
    with pytest.raises(M.StoreNotAudited, match="unaudited store"):
        M.check_store_manifest(syn["bar_store"], _audit(syn), syn["sessions"], syn["sector_etf_map"], strict=False)


def test_build_rows_refuses_an_incomplete_manifest_under_dev_run(syn):
    """The defensive check inside build_rows: DEV_RUN never reaches the loader with a missing file."""
    audit = _audit(syn)
    m = M.check_store_manifest(syn["bar_store"], audit, syn["sessions"], syn["sector_etf_map"], strict=False)
    m["missing"] = ["SYN001"]
    cfg = M._smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                          syn["sector_etf_map"], syn["bar_store"].parent / "out", M._smoke_folds(syn["sessions"]),
                          min_names=2, dev_start=syn["sessions"][0], dev_end=syn["sessions"][-1])
    with pytest.raises(M.StoreNotAudited, match="incomplete store manifest"):
        M.build_rows(dataclasses.replace(cfg, run_status="DEV_RUN"), audit, syn["sessions"], m, **SILENT)


# --------------------------------------------------------------------------- #
# (2) DEV_RUN identity: clean tree, unique UTC run_id, own bundle, no overwrite — on a real tmp git repository
# --------------------------------------------------------------------------- #
def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def tmp_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    return repo


@pytest.fixture
def dev_cfg(tmp_path, tmp_repo, monkeypatch):
    """A DEV_RUN configuration that passes `_bind_dev_run` (real gate authorization, the gate audit) with a synthetic
    bar store whose sector_etf_map reproduces the bound absent set — so the identity checks run and the run is then
    refused AT the store manifest (1,508 eligible names are not in the synthetic store), never past it."""
    auth = M.load_gate_authorization(REPO)
    syn = M._synthetic_store(tmp_path / "syn", n_names=3, n_sessions=2)
    etf_map = {"tech": "XLK", "healthcare": "XLV", "bond": "TLT", "telecom": "XLC", "real_estate": "XLRE"}
    monkeypatch.setattr(M, "REPO", tmp_repo)
    monkeypatch.setattr(M, "_now_utc", lambda: FIXED_NOW)
    out_root = tmp_repo / "doc/research/data/2026-08-29-g2v3-i1"
    cfg = M.RunConfig(bar_store=syn["bar_store"], census_audit=M.GATE_AUDIT, spy_daily=syn["spy_daily"],
                      sector_map={}, sector_etf_map=etf_map, out_dir=out_root, run_status="DEV_RUN", gate=auth,
                      strategy_config=syn["strategy_config"])
    return dict(cfg=cfg, repo=tmp_repo, out_root=out_root, sha=_git(tmp_repo, "rev-parse", "HEAD"))


def test_dirty_tree_is_refused_before_anything_is_read_or_written(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    (dev_cfg["repo"] / "stray.txt").write_text("x")
    with pytest.raises(M.DevRunRefused, match=r"source tree is not clean: 1 entries .*stray.txt"):
        M.run_stage_i1(dev_cfg["cfg"], **SILENT)
    assert not dev_cfg["out_root"].exists()
    (dev_cfg["repo"] / "stray.txt").unlink()
    (dev_cfg["repo"] / "tracked.txt").write_text("y")                   # a modified/added tracked file is dirt too
    _git(dev_cfg["repo"], "add", "tracked.txt")
    with pytest.raises(M.DevRunRefused, match="source tree is not clean"):
        M.run_stage_i1(dev_cfg["cfg"], **SILENT)


def test_untracked_files_under_the_declared_paths_are_not_dirt(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    dev_cfg["out_root"].mkdir(parents=True)
    (dev_cfg["out_root"] / "older-bundle.txt").write_text("x")         # under the output ROOT: excluded
    store_in_repo = dev_cfg["repo"] / "bars"
    store_in_repo.mkdir()
    (store_in_repo / "AAA.parquet").write_bytes(b"x")                   # under the declared bar store: excluded
    cfg = dataclasses.replace(dev_cfg["cfg"], bar_store=store_in_repo)
    with pytest.raises(M.StoreNotAudited):                              # past the tree check; refused at the store
        M.run_stage_i1(cfg, **SILENT)
    src = M.source_state(dev_cfg["repo"], ignore=[store_in_repo, dev_cfg["out_root"]])
    assert src["clean_tree"] is True and src["n_dirty"] == 0
    assert M.source_state(dev_cfg["repo"])["clean_tree"] is False       # without the exclusions the same tree is dirty


def test_existing_bundle_is_refused_no_overwrite(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    run_id = f"i1-dev-20260829T101500Z-{dev_cfg['sha'][:8]}"
    bundle = dev_cfg["out_root"] / run_id
    bundle.mkdir(parents=True)
    (bundle / "report.json").write_text("{}")
    with pytest.raises(M.DevRunRefused, match=f"output bundle .*{run_id} already exists; refusing to overwrite"):
        M.run_stage_i1(dev_cfg["cfg"], **SILENT)
    assert (bundle / "report.json").read_text() == "{}"                  # untouched


def test_clean_and_fresh_proceeds_to_the_store_check(dev_cfg, monkeypatch):
    _forbid_parquet_reads(monkeypatch)
    src = M.source_state(dev_cfg["repo"], ignore=[dev_cfg["cfg"].bar_store, dev_cfg["out_root"]])
    run_id, bundle = M.dev_run_identity(dev_cfg["cfg"], src, FIXED_NOW)
    assert run_id == f"i1-dev-20260829T101500Z-{dev_cfg['sha'][:8]}"
    assert bundle == dev_cfg["out_root"] / run_id and not bundle.exists()
    assert M._RUN_ID.match(run_id)
    # the identity checks pass; the run is then refused at the store manifest, with nothing read or written
    with pytest.raises(M.StoreNotAudited, match=r"of the \d+ audited files this run needs are missing"):
        M.run_stage_i1(dev_cfg["cfg"], **SILENT)
    assert not dev_cfg["out_root"].exists()


def test_dev_run_identity_needs_a_commit(dev_cfg):
    with pytest.raises(M.DevRunRefused, match="cannot establish the source commit"):
        M.dev_run_identity(dev_cfg["cfg"], dict(commit=None, clean_tree=None, error="no git"), FIXED_NOW)


def test_cli_dev_run_exits_2_on_a_dirty_tree(dev_cfg, monkeypatch, capsys):
    monkeypatch.setattr(M, "dev_run_config", lambda auth: dev_cfg["cfg"])
    monkeypatch.setattr(M, "load_gate_authorization", lambda root: dev_cfg["cfg"].gate)
    (dev_cfg["repo"] / "stray.txt").write_text("x")
    assert M.main(["--dev-run"]) == 2
    assert "REFUSED --dev-run (fail closed): source tree is not clean" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# smoke keeps its ergonomics: fixed dir, overwrite, dirty tree tolerated, run_status != DEV_RUN
# --------------------------------------------------------------------------- #
def test_smoke_keeps_fixed_dir_overwrite_and_records_non_dev_status(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "_now_utc", lambda: FIXED_NOW)
    syn = M._synthetic_store(tmp_path / "syn", n_names=24, n_sessions=30)
    out = tmp_path / "out"
    cfg = M._smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                          syn["sector_etf_map"], out, M._smoke_folds(syn["sessions"]), min_names=20,
                          dev_start=syn["sessions"][0], dev_end=syn["sessions"][-1], strategy_config=syn["strategy_config"])
    r1 = M.run_stage_i1(cfg, **SILENT)
    r2 = M.run_stage_i1(cfg, **SILENT)                                   # same fixed dir, overwritten, no refusal
    assert r1["run_status"] == r2["run_status"] == "SMOKE" != "DEV_RUN"
    assert r2["provenance"]["outputs"]["bundle_dir"] == str(out) and (out / "report.json").is_file()
    assert r2["run_id"] == "i1-smoke-20260829T101500Z-" + r2["provenance"]["source"]["commit"][:8]
    assert r2["provenance"]["store_manifest_check"]["strict"] is False
    assert r2["provenance"]["store_manifest_check"]["absent_from_audit"] == ["XLV"]
    consumed = json.load(gzip.open(out / "g2v3_stage_i1_audit.json.gz"))["consumed_sha256"]
    assert set(consumed) == set(syn["names"]) | {"SPY", "XLK", "XLF"}
    assert M.validate_i1_provenance(r2, dict(consumed_sha256=consumed), REPO) == []
