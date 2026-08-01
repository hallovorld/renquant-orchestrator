"""Walk-forward coverage resolved from the ARTIFACT, not from a directory name.

Reviewed `[codex on orch#691]`: the first version took lane names as command-line
directory strings, so "invoking it for the GBDT directory and labeling the result clf
recreates the exact substitution this PR corrects". The tool did not prevent the error it
was written about. These tests are mostly about the ways this rewrite could still let a
number float free of the lane it belongs to.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "wf_corpus_coverage.py"


def _load():
    spec = importlib.util.spec_from_file_location("wfcc", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


C = _load()


def _manifest(tmp_path, name, n, corpus="wf_corpus", rows_key="retrains"):
    p = tmp_path / name
    p.write_text(json.dumps({rows_key: [
        {"artifact_uri": f"/x/{corpus}/2024-01-{i:02d}/panel-ltr.json",
         "cutoff_date": f"2024-01-{i:02d}"} for i in range(1, n + 1)]}),
        encoding="utf-8")
    return str(p)


def _artifact(tmp_path, name, manifest_path=None, stamped=True, legacy=False):
    block = {"passed": True}
    if manifest_path is not None:
        block["artifact_usage"] = {"manifest_path": manifest_path}
    body = {}
    if stamped:
        body["wf_gate_metadata" if legacy else "metadata"] = (
            block if legacy else {"wf_gate_metadata": block})
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


# --- the binding ------------------------------------------------------------

def test_the_corpus_is_DERIVED_from_the_artifacts_own_stamp(tmp_path):
    """The rewrite's whole point: the caller names an artifact, never a corpus."""
    m = _manifest(tmp_path, "m.json", 43, corpus="walkforward_gbdt")
    r = C.resolve(_artifact(tmp_path, "a.json", m))
    assert r["status"] == "resolved" and r["n_folds"] == 43
    assert r["corpus_dirs"] == ["walkforward_gbdt"]


def test_a_LEGACY_top_level_stamp_also_resolves_and_the_SOURCE_is_recorded(tmp_path):
    """Reading only the canonical key is how two claims got retracted this week."""
    m = _manifest(tmp_path, "m.json", 3)
    r = C.resolve(_artifact(tmp_path, "a.json", m, legacy=True))
    assert r["status"] == "resolved" and r["gate_stamp_source"] == C.LEGACY


def test_NO_GATE_STAMP_is_its_own_status_and_is_DERIVED(tmp_path):
    """The clf case. It must fall out of the resolution, not be asserted by a caller."""
    r = C.resolve(_artifact(tmp_path, "a.json", stamped=False))
    assert r["status"] == "no_gate_stamp" and r["n_folds"] == 0
    assert "no walk-forward binding" in r["note"]


def test_MANIFEST_MISSING_is_NOT_reported_as_zero_folds(tmp_path):
    """13 of 30 stamped prod artifacts name a path under /tmp. 'The pointer evaporated'
    and 'the folds never existed' are different facts."""
    r = C.resolve(_artifact(tmp_path, "a.json", "/tmp/gone_forever_12345.json"))
    assert r["status"] == "manifest_missing"
    assert "NOT evidence the folds never existed" in r["note"]


def test_an_UNRECOGNISED_manifest_shape_is_not_zero_folds(tmp_path):
    """The bug this rewrite hit: a guessed row-key list returned 0 for the real
    manifest, whose rows live under `retrains`."""
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"something_else": {"not": "a list of rows"}}),
                 encoding="utf-8")
    r = C.resolve(_artifact(tmp_path, "a.json", str(p)))
    assert r["status"] == "unrecognised_manifest_shape"
    assert "NOT zero folds" in r["note"]


def test_the_ROW_KEY_that_answered_is_RECORDED(tmp_path):
    """So a manifest shape change is visible in the report instead of quiet."""
    m = _manifest(tmp_path, "m.json", 5, rows_key="retrains")
    assert C.resolve(_artifact(tmp_path, "a.json", m))["manifest_rows_key"] == "retrains"


def test_a_manifest_spanning_TWO_corpora_is_flagged(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"retrains": [
        {"artifact_uri": "/x/corpus_a/2024-01-01/p.json"},
        {"artifact_uri": "/x/corpus_b/2024-01-02/p.json"}]}), encoding="utf-8")
    r = C.resolve(_artifact(tmp_path, "a.json", str(p)))
    assert sorted(r["corpus_dirs"]) == ["corpus_a", "corpus_b"]
    assert "more than one corpus" in r["note"]


# --- the audit's own integrity ---------------------------------------------

def test_a_MISSING_artifact_is_distinct_from_an_unstamped_one(tmp_path):
    assert C.resolve(str(tmp_path / "nope.json"))["status"] == "artifact_missing"


def test_a_NON_OBJECT_artifact_root_is_unreadable_not_unstamped(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("[]", encoding="utf-8")
    r = C.resolve(str(p))
    assert r["status"] == "artifact_unreadable" and "list" in r["why"]


def test_results_are_PER_ARTIFACT_and_never_summed(tmp_path):
    """The defect this tool exists after: one lane's folds standing in for another's."""
    rich = _artifact(tmp_path, "rich.json", _manifest(tmp_path, "m.json", 43))
    poor = _artifact(tmp_path, "poor.json", stamped=False)
    rep = C.survey([rich, poor])
    assert [r["n_folds"] for r in rep["artifacts"]] == [43, 0]
    assert "total" not in rep and "n_folds_total" not in rep
    assert all(r.get("artifact") for r in rep["artifacts"])


def test_main_EXITS_NONZERO_on_an_unstamped_artifact(tmp_path, capsys):
    rc = C.main(["--artifacts", _artifact(tmp_path, "a.json", stamped=False)])
    assert rc == 1 and "NO_GATE_STAMP" in capsys.readouterr().out


def test_main_EXITS_NONZERO_on_a_THIN_but_resolved_artifact(tmp_path, capsys):
    a = _artifact(tmp_path, "a.json", _manifest(tmp_path, "m.json", 3))
    assert C.main(["--artifacts", a, "--min-folds", "20"]) == 1
    assert "THIN" in capsys.readouterr().out


def test_ANTI_VACUITY_a_fully_covered_artifact_exits_zero(tmp_path, capsys):
    a = _artifact(tmp_path, "a.json", _manifest(tmp_path, "m.json", 43))
    assert C.main(["--artifacts", a, "--min-folds", "20"]) == 0
    assert "COVERED" in capsys.readouterr().out


def test_the_report_states_that_the_binding_comes_from_the_artifact(tmp_path, capsys):
    C.main(["--artifacts", _artifact(tmp_path, "a.json", stamped=False)])
    out = capsys.readouterr().out
    assert "ARTIFACT'S OWN gate stamp" in out and "never summed" in out


# ---------------------------------------------------------------------------
# ROUND 3 — codex on #691: `(x or {}).get(...)` is NOT a guard. A non-empty
# string is truthy, so `or {}` never fires and `.get` raises AttributeError.
# Measured before the fix: two of these three crashed.
# ---------------------------------------------------------------------------

def _raw(tmp_path, body, name="a.json"):
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


def test_a_STRING_metadata_container_FAILS_CLOSED_and_does_not_crash(tmp_path):
    """Measured pre-fix: AttributeError: 'str' object has no attribute 'get'."""
    r = C.resolve(_raw(tmp_path, {"metadata": "n/a"}))
    assert r["status"] == "malformed_gate_stamp"
    assert "str" in (r.get("gate_stamp_source") or "")


def test_a_STRING_gate_BLOCK_fails_closed(tmp_path):
    r = C.resolve(_raw(tmp_path, {"metadata": {"wf_gate_metadata": "x"}}))
    assert r["status"] == "malformed_gate_stamp"


def test_a_STRING_legacy_gate_block_fails_closed(tmp_path):
    """The legacy position needs the same guard, or the fix covers one of two doors."""
    r = C.resolve(_raw(tmp_path, {"wf_gate_metadata": "x"}))
    assert r["status"] == "malformed_gate_stamp" and "legacy" in r["gate_stamp_source"]


def test_a_STRING_artifact_usage_FAILS_CLOSED_and_does_not_crash(tmp_path):
    """The second crash site, measured pre-fix."""
    r = C.resolve(_raw(tmp_path, {"metadata": {"wf_gate_metadata":
                                               {"artifact_usage": "n/a"}}}))
    assert r["status"] == "malformed_artifact_usage" and "str" in r["note"]


def test_a_NON_STRING_manifest_path_is_MALFORMED_not_MISSING(tmp_path):
    """Measured pre-fix this reported `manifest_missing` — saying the pointer evaporated
    when in fact it is malformed. Different defect, different owner."""
    r = C.resolve(_raw(tmp_path, {"metadata": {"wf_gate_metadata":
                                               {"artifact_usage":
                                                {"manifest_path": 7}}}}))
    assert r["status"] == "malformed_manifest_path" and "int" in r["note"]


def test_an_EMPTY_manifest_path_string_is_NO_MANIFEST_NAMED(tmp_path):
    """The distinction has to cut both ways or it is just a stricter alarm."""
    r = C.resolve(_raw(tmp_path, {"metadata": {"wf_gate_metadata":
                                               {"artifact_usage":
                                                {"manifest_path": ""}}}}))
    assert r["status"] == "no_manifest_named"


# --- scheduled behaviour: drive main(), because the exit code is what a job reads ---

def test_main_EXITS_NONZERO_on_each_malformed_shape(tmp_path):
    shapes = [
        {"metadata": "n/a"},
        {"metadata": {"wf_gate_metadata": "x"}},
        {"metadata": {"wf_gate_metadata": {"artifact_usage": "n/a"}}},
        {"metadata": {"wf_gate_metadata": {"artifact_usage": {"manifest_path": 7}}}},
    ]
    for i, body in enumerate(shapes):
        a = _raw(tmp_path, body, name=f"m{i}.json")
        assert C.main(["--artifacts", a]) == 1, body


def test_main_does_not_RAISE_on_a_malformed_artifact(tmp_path, capsys):
    """A scheduled job cannot tell an uncaught exception from an alarm — `sys.exit(main())`
    turns both into a non-zero status. So the tool must return, never raise."""
    C.main(["--artifacts", _raw(tmp_path, {"metadata": "n/a"})])
    assert "MALFORMED_GATE_STAMP" in capsys.readouterr().out


def test_main_JSON_mode_also_survives_a_malformed_artifact(tmp_path, capsys):
    C.main(["--artifacts", _raw(tmp_path, {"metadata": "n/a"}), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifacts"][0]["status"] == "malformed_gate_stamp"
