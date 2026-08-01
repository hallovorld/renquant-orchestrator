"""How independent are the WF gate's economic cuts?

A count like `n_positive_cuts: 3` is only as strong as the independence of the things
counted. These tests target the ways this measurement could overstate that independence —
a dropped cut making the rest look disjoint, an absent cut set reading as clean, and
geometry being presented as an effective sample size.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "wf_cut_independence.py"


def _load():
    spec = importlib.util.spec_from_file_location("wci", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


C = _load()
D = dt.date

import re  # noqa: E402  (used by the round-3 provenance tests below)
_EVIDENCE = ROOT / "doc/research/evidence/2026-07-31-wf-cut-independence/evidence.json"


def _art(tmp_path, cuts, name="a.json", legacy=False, raw=None):
    block = raw if raw is not None else {"cuts": cuts}
    body = ({"wf_gate_metadata": block} if legacy
            else {"metadata": {"wf_gate_metadata": block}})
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


# --- the geometry -----------------------------------------------------------

def test_DISJOINT_cuts_have_redundancy_one(tmp_path):
    r = C.analyse([(D(2024, 1, 1), D(2024, 6, 30)), (D(2024, 7, 1), D(2024, 12, 31))])
    assert r["disjoint"] is True and r["overlapping_pairs"] == []
    assert abs(r["redundancy"] - 1.0) < 0.02


def test_OVERLAP_is_reported_as_a_fraction_of_the_SHORTER_window(tmp_path):
    """Against the longer window a big overlap looks small — the shorter one is what
    determines how much of an observation is not new."""
    r = C.analyse([(D(2024, 1, 1), D(2025, 1, 1)), (D(2024, 10, 1), D(2025, 1, 1))])
    p = r["overlapping_pairs"][0]
    assert p["frac_of_shorter"] == 1.0


def test_redundancy_counts_REUSED_calendar(tmp_path):
    """Two identical windows: 2x the length over 1x the calendar."""
    r = C.analyse([(D(2024, 1, 1), D(2025, 1, 1)), (D(2024, 1, 1), D(2025, 1, 1))])
    assert abs(r["redundancy"] - 2.0) < 0.01


def test_the_DISJOINT_CEILING_is_arithmetic_not_a_guess(tmp_path):
    assert C.ceiling(882, 364) == 2
    assert C.ceiling(882, 252) == 3
    assert C.ceiling(882, 182) == 4


# --- ways the measurement could overstate independence ----------------------

def test_an_UNREADABLE_cut_is_REPORTED_not_dropped(tmp_path):
    """Silently shrinking the cut set makes the remainder look more independent than it
    is — the exact quantity under measurement."""
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-12-31"},
                        {"start": "nonsense", "end": "2025-06-30"}])
    p = json.loads(pathlib.Path(a).read_text())
    cuts, bad = C._cuts(p["metadata"]["wf_gate_metadata"])
    assert len(cuts) == 1 and len(bad) == 1
    assert C.main(["--artifact", a]) == 1          # cannot pass with a cut unread


def test_a_NON_OBJECT_cut_is_reported(tmp_path):
    a = _art(tmp_path, ["2024-01-01"])
    _, bad = C._cuts(json.loads(pathlib.Path(a).read_text())
                     ["metadata"]["wf_gate_metadata"])
    assert bad and "not an object" in bad[0]


def test_an_INVERTED_cut_is_rejected_not_counted_as_negative_length(tmp_path):
    a = _art(tmp_path, [{"start": "2025-01-01", "end": "2024-01-01"}])
    cuts, bad = C._cuts(json.loads(pathlib.Path(a).read_text())
                        ["metadata"]["wf_gate_metadata"])
    assert cuts == [] and bad and "not after" in bad[0]


def test_a_NON_LIST_cuts_field_is_reported(tmp_path):
    a = _art(tmp_path, None, raw={"cuts": "three"})
    _, bad = C._cuts(json.loads(pathlib.Path(a).read_text())
                     ["metadata"]["wf_gate_metadata"])
    assert bad and "not a list" in bad[0]


def test_NO_GATE_BLOCK_exits_1_not_0(tmp_path, capsys):
    """'No cut set' must never read as 'the cuts are independent'."""
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"feature_cols": []}), encoding="utf-8")
    assert C.main(["--artifact", str(p)]) == 1
    assert "not the same as independent cuts" in capsys.readouterr().err


def test_a_MALFORMED_metadata_container_does_not_crash(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"metadata": "n/a"}), encoding="utf-8")
    assert C.main(["--artifact", str(p)]) == 1


def test_a_LEGACY_gate_block_is_read_and_the_source_recorded(tmp_path, capsys):
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-06-30"}], legacy=True)
    C.main(["--artifact", a])
    assert "legacy top-level" in capsys.readouterr().out


def test_a_MISSING_artifact_exits_2(tmp_path):
    assert C.main(["--artifact", str(tmp_path / "gone.json")]) == 2


def test_ANTI_VACUITY_disjoint_cuts_exit_ZERO(tmp_path):
    """Without this the check could flag every artifact and prove nothing."""
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-06-30"},
                        {"start": "2024-07-01", "end": "2024-12-31"}])
    assert C.main(["--artifact", a]) == 0


def test_the_report_REFUSES_to_call_geometry_an_effective_sample_size(tmp_path, capsys):
    """Redundancy is derivable from boundaries alone. Converting it to an effective n
    needs a correlation this tool does not measure — a standing correction here."""
    a = _art(tmp_path, [{"start": "2024-01-01", "end": "2024-12-31"},
                        {"start": "2024-07-01", "end": "2025-06-30"}])
    C.main(["--artifact", a])
    out = capsys.readouterr().out
    assert "not an effective sample size" in out


def test_the_EVIDENCE_MANIFEST_binds_the_published_numbers_to_their_sources():
    """codex on #696: the published 816 / 1.33x / 882 rested on a test that hard-coded a
    local absolute path and skipped in CI, with nothing binding the artifact to a
    fingerprint or recording how 882 was derived.

    The committed manifest now carries both digests and the derivation. This test checks
    the manifest itself — it runs everywhere, including CI, because it reads a checked-in
    file rather than the artifact tree.
    """
    import json
    ev = (pathlib.Path(__file__).resolve().parent.parent / "doc" / "research"
          / "evidence" / "2026-07-31-wf-cut-independence" / "evidence.json")
    assert ev.exists(), "the published numbers must ship with their evidence"
    d = json.loads(ev.read_text(encoding="utf-8"))
    assert len(d["artifact_sha256"]) == 64
    c = d["corpus"]
    assert c["status"] == "derived"
    assert len(c["manifest_sha256"]) == 64
    # The span is the subtraction, and it is shown rather than asserted.
    first = dt.date.fromisoformat(c["first_cutoff"])
    last = dt.date.fromisoformat(c["last_cutoff"])
    assert (last - first).days == c["corpus_days"] == 882
    assert c["n_folds"] == 43 and c["rows_key"] == "retrains"
    # And the headline numbers are the ones the document publishes.
    assert d["calendar_union_days"] == 816
    assert 1.33 <= d["redundancy"] <= 1.34
    assert C.ceiling(c["corpus_days"], max(d["cut_lengths_days"])) == 2


def test_the_manifest_VERIFIES_against_the_sources_when_they_are_present():
    """The half that carries the weight: recompute both digests from the files named.
    Skips loudly when the artifact tree is not on this machine — a verification that
    cannot run must not read as one that passed."""
    import hashlib, json, os
    import pytest
    ev = (pathlib.Path(__file__).resolve().parent.parent / "doc" / "research"
          / "evidence" / "2026-07-31-wf-cut-independence" / "evidence.json")
    d = json.loads(ev.read_text(encoding="utf-8"))
    root = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts"
    art = os.path.join(root, "prod", d["artifact"])
    man = os.path.join(root, "sim", d["corpus"]["manifest_path"])
    if not (os.path.exists(art) and os.path.exists(man)):
        pytest.skip("artifact tree not present on this machine")
    assert hashlib.sha256(open(art, "rb").read()).hexdigest() == d["artifact_sha256"]
    assert (hashlib.sha256(open(man, "rb").read()).hexdigest()
            == d["corpus"]["manifest_sha256"])


def test_the_REAL_artifact_reproduces_the_finding():
    """The numbers in the module docstring must stay derivable, or the docstring becomes
    an assertion with a citation attached."""
    import os
    p = ("/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/"
         "prod/panel-ltr.alpha158_fund.previous.json")
    if not os.path.exists(p):
        import pytest
        pytest.skip("live artifact not present on this machine")
    block, _ = C._gate_block(json.loads(pathlib.Path(p).read_text()))
    cuts, bad = C._cuts(block)
    r = C.analyse(cuts)
    assert bad == [] and r["n_cuts"] == 3
    assert r["calendar_union_days"] == 816 and r["sum_of_lengths_days"] == 1089
    assert 1.33 <= r["redundancy"] <= 1.34
    assert C.ceiling(882, max(r["cut_lengths_days"])) == 2


def test_DISJOINT_cuts_SEPARATED_BY_A_GAP_have_redundancy_exactly_one(tmp_path):
    """codex on #696: the first version used the OUTER SPAN, so a gap between two
    disjoint cuts counted as covered and redundancy fell BELOW 1 — making the documented
    invariant "1.00 means disjoint" false, and overstating coverage."""
    r = C.analyse([(D(2024, 1, 1), D(2024, 6, 30)),
                   (D(2025, 1, 1), D(2025, 6, 30))])      # a 6-month GAP between them
    assert r["disjoint"] is True
    assert r["redundancy"] == 1.0, r
    assert r["calendar_union_days"] == 181 + 180, r
    assert r["outer_span_days"] > r["calendar_union_days"], "the span is not the union"
    assert r["n_merged_intervals"] == 2


def test_the_outer_span_is_RETAINED_separately(tmp_path):
    """It is what a reader means by 'the cuts run from X to Y'. Conflating the two was
    the defect; dropping it would lose a real fact."""
    r = C.analyse([(D(2024, 1, 1), D(2024, 6, 30)),
                   (D(2025, 1, 1), D(2025, 6, 30))])
    assert r["outer_span_days"] == (D(2025, 6, 30) - D(2024, 1, 1)).days


def test_ADJACENT_cuts_merge_into_one_interval(tmp_path):
    """Touching, not overlapping: still disjoint, still redundancy 1.0, one interval."""
    r = C.analyse([(D(2024, 1, 1), D(2024, 7, 1)), (D(2024, 7, 1), D(2025, 1, 1))])
    assert r["redundancy"] == 1.0 and r["n_merged_intervals"] == 1


def test_redundancy_can_never_fall_BELOW_one(tmp_path):
    """The invariant the outer-span version broke, asserted directly across shapes."""
    for cuts in ([(D(2024, 1, 1), D(2024, 6, 30)), (D(2025, 1, 1), D(2025, 6, 30))],
                 [(D(2024, 1, 1), D(2025, 1, 1)), (D(2024, 7, 1), D(2025, 7, 1))],
                 [(D(2024, 1, 1), D(2024, 2, 1))]):
        assert C.analyse(cuts)["redundancy"] >= 1.0, cuts


# ---------------------------------------------------------------------------
# codex on #696, round 3: a basename and a digest let a reader VERIFY a file
# they already have; they do nothing to help a reader FIND it.
# ---------------------------------------------------------------------------

def test_every_hashed_input_names_its_REPOSITORY_ref_and_repo_relative_path():
    """The requested cross-repo provenance, asserted on the committed record.

    Reviewed: *"evidence.json has only basenames and hashes… a reader cannot locate or
    interpret the hashed inputs outside this workstation layout."* So each hashed input
    carries the repo, its remote, the ref (HEAD) and the path INSIDE that repo — which
    is what makes the digest checkable somewhere other than this machine.
    """
    rec = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    for key in ("artifact_provenance", "corpus_provenance"):
        p = rec[key]
        assert p["in_git"] is True, key
        assert p["repo"], key
        assert p["repo_remote"] and p["repo_remote"].startswith("http"), key
        assert re.fullmatch(r"[0-9a-f]{40}", p["repo_head"]), key
        rel = p["repo_relative_path"]
        assert rel and not rel.startswith("/") and ".." not in rel, key
        assert rel.endswith(p["basename"]), (key, rel, p["basename"])


def test_the_record_carries_PRODUCER_identity_from_the_artifacts_own_metadata():
    """Who made the thing, and when. Read from the artifact's own keys rather than
    reconstructed: an invented producer id would defeat the purpose more thoroughly
    than an absent one, so a field the artifact lacks stays None."""
    prod = json.loads(_EVIDENCE.read_text(encoding="utf-8"))["producer"]
    for field in ("train_run_id", "trained_date", "kind", "gate_run_at",
                  "gate_eval_scope"):
        assert field in prod, field
    assert prod["train_run_id"], "the producing run is unidentified"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", prod["trained_date"])
    assert prod["gate_eval_scope"] in ("walkforward_manifest", "static_artifact")


def test_provenance_of_a_file_OUTSIDE_any_checkout_is_absent_not_invented(tmp_path):
    """ANTI-VACUITY, and the honest branch: a fabricated repo-relative path is worse
    than none, so a file outside git reports `in_git: false` and stops there."""
    stray = tmp_path / "loose.json"
    stray.write_text("{}", encoding="utf-8")
    p = C._repo_provenance(str(stray))
    assert p["in_git"] is False
    assert p["basename"] == "loose.json"
    assert "repo_relative_path" not in p and "repo_head" not in p


def test_a_MALFORMED_cutoff_date_is_a_controlled_result_not_a_ValueError(tmp_path):
    """Codex: *"the current `date.fromisoformat` comprehension raises uncaught
    ValueError for a structurally bad upstream manifest."* A crash and a refusal are
    both non-zero; only one names the input that caused it."""
    man = tmp_path / "man.json"
    man.write_text(json.dumps({"rows": [{"cutoff_date": "2024-01-01"},
                                        {"cutoff_date": "not-a-date"}]}),
                   encoding="utf-8")
    got = C.corpus_span(str(man))
    assert got["status"] == "manifest_unreadable"
    assert "not-a-date" in got["why"]
    assert got["manifest_sha256"], "a refusal must still identify what it refused"


def test_a_WELL_FORMED_manifest_still_derives(tmp_path):
    """ANTI-VACUITY for the test above: the guard must not reject valid manifests."""
    man = tmp_path / "man.json"
    man.write_text(json.dumps({"rows": [{"cutoff_date": "2024-01-01"},
                                        {"cutoff_date": "2024-12-31"}]}),
                   encoding="utf-8")
    got = C.corpus_span(str(man))
    assert got["status"] == "derived"
    assert got["n_folds"] == 2 and got["corpus_days"] == 365


def test_the_PRODUCER_still_emits_repo_ref_and_relative_path():
    """Binds to the code, not to the committed file.

    The record test above reads `evidence.json`, so it stays green even if the tool
    stops emitting these fields — a guard validating the wrong object, caught by
    mutating `_repo_provenance` and watching nothing fail. This runs the producer
    against a file known to be inside this repository.
    """
    p = C._repo_provenance(str(_EVIDENCE))
    assert p["in_git"] is True
    assert p["repo"] and p["repo_remote"]
    assert re.fullmatch(r"[0-9a-f]{40}", p["repo_head"])
    rel = p["repo_relative_path"]
    assert rel.startswith("doc/research/evidence/") and rel.endswith("evidence.json")
    assert not rel.startswith("/")
