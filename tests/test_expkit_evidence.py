"""expkit.evidence — manifest stamping + verified re-read (round trip)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator.expkit.evidence import (
    build_manifest,
    canonical_json,
    json_default,
    load_and_verify_evidence,
    resolve_git_dirty,
    resolve_git_head,
    sha256_bytes,
    sha256_file,
    verify_manifest,
    write_evidence,
)


def test_sha256_helpers(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == sha256_bytes(b"abc")
    assert (
        sha256_bytes(b"abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_canonical_json_is_key_order_invariant():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_json_default_house_encoder():
    assert json_default(pd.Timestamp("2026-07-03")) == "2026-07-03"
    assert json_default(np.int64(3)) == 3
    assert json_default(np.float64(1.5)) == 1.5
    assert json_default(np.float64("nan")) is None  # non-finite -> null
    assert json_default(np.array([1, 2])) == [1, 2]
    assert json_default(Path("/x")) == "/x"


# ---------------------------------------------------------------------------
# manifest round trip
# ---------------------------------------------------------------------------
@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / "seed.txt").write_text("s")
    subprocess.run(["git", "-C", str(tmp_path), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "-m", "seed"],
        check=True,
    )
    return tmp_path


def test_manifest_round_trip(repo: Path):
    inp = repo / "input.parquet"
    inp.write_bytes(b"panel-bytes")
    manifest = build_manifest(
        repo_root=repo,
        script="scripts/toy.py",
        inputs={"panel": inp},
        input_hashes={"in_memory_panel": "deadbeef"},
        seeds=(42, 43),
        spec_sha256="s" * 64,
        argv=["--toy"],
    )
    assert manifest["inputs_sha256"]["panel"] == sha256_file(inp)
    assert manifest["code"]["git_sha"] == resolve_git_head(repo)
    assert manifest["seeds"] == [42, 43]

    payload = {"result": 1.0, "manifest": manifest}
    out = write_evidence(repo / "evidence", "toy_results.json", payload)
    loaded, verification = load_and_verify_evidence(out)
    assert loaded["result"] == 1.0
    assert verification.ok and verification.checked == 1
    # the in-memory hash is reported unverifiable, never silently passed
    assert verification.unverifiable == ["in_memory_panel"]


def test_manifest_detects_input_drift(repo: Path):
    inp = repo / "input.parquet"
    inp.write_bytes(b"v1")
    manifest = build_manifest(repo_root=repo, script="s.py", inputs={"panel": inp})
    out = write_evidence(repo / "ev", "r.json", {"manifest": manifest})
    inp.write_bytes(b"v2 -- the data refreshed under the evidence")
    with pytest.raises(ValueError, match="panel"):
        load_and_verify_evidence(out)
    _, verification = load_and_verify_evidence(out, strict=False)
    assert not verification.ok
    assert "panel" in verification.mismatched


def test_manifest_reports_missing_inputs(repo: Path):
    inp = repo / "input.parquet"
    inp.write_bytes(b"v1")
    manifest = build_manifest(repo_root=repo, script="s.py", inputs={"panel": inp})
    inp.unlink()
    v = verify_manifest(manifest)
    assert not v.ok and v.missing == ["panel"]


def test_verify_manifest_relative_paths_use_base(repo: Path):
    inp = repo / "input.parquet"
    inp.write_bytes(b"v1")
    manifest = {
        "inputs_sha256": {"panel": sha256_file(inp)},
        "input_paths": {"panel": "input.parquet"},
    }
    assert verify_manifest(manifest, base=repo).ok
    assert not verify_manifest(manifest, base=repo / "elsewhere").ok


def test_git_stamps(repo: Path):
    head = resolve_git_head(repo)
    assert head and len(head) == 40
    dirty = resolve_git_dirty(repo)
    assert dirty == {"tracked_modified": 0, "untracked": 0}
    (repo / "new.txt").write_text("x")
    assert resolve_git_dirty(repo)["untracked"] == 1
    # failure-tolerant on a non-repo
    assert resolve_git_head(repo / "nope") is None


def test_evidence_json_uses_house_encoder(tmp_path: Path):
    # np.int64 / ndarray / Timestamp are not natively serializable — the
    # house encoder must handle them (np.float64 IS a float subclass, so it
    # bypasses `default=`; the non-finite -> None rule is covered above)
    out = write_evidence(
        tmp_path,
        "r.json",
        {
            "n": np.int64(7),
            "arr": np.array([1.0, 2.0]),
            "t": pd.Timestamp("2026-01-01"),
        },
    )
    loaded = json.loads(out.read_text())
    assert loaded["n"] == 7
    assert loaded["arr"] == [1.0, 2.0]
    assert loaded["t"] == "2026-01-01"
