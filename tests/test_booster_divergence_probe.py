"""Do same-recipe boosters rank differently?

orch#692 measured that 12 distinct boosters share one admission fingerprint and stopped
there on purpose. These tests cover the ways the follow-up could overstate — or silently
fail to establish — behavioural divergence.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "booster_divergence_probe.py"
xgb = pytest.importorskip("xgboost")
np = pytest.importorskip("numpy")
pytest.importorskip("scipy")


def _load():
    spec = importlib.util.spec_from_file_location("bdp", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


P = _load()
COLS = [f"f{i}" for i in range(6)]


def _artifact(tmp_path, name, seed, cols=COLS, n=200):
    """Train a tiny booster and write it in the artifact's shape."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(cols)))
    y = X[:, seed % len(cols)] + 0.1 * rng.standard_normal(n)
    b = xgb.train({"max_depth": 3, "eta": 0.3, "verbosity": 0},
                  xgb.DMatrix(X, label=y, feature_names=cols), num_boost_round=8)
    raw = b.save_raw(raw_format="json").decode("utf-8")
    (tmp_path / name).write_text(
        json.dumps({"booster_raw_json": raw, "feature_cols": cols}), encoding="utf-8")
    return name


# --- loading ----------------------------------------------------------------

def test_boosters_are_deduplicated_BY_DIGEST(tmp_path):
    """A corpus with copies must score each MODEL once — otherwise a model present twice
    weights the summary, which is the same collapse #692 measures."""
    _artifact(tmp_path, "a.json", 1)
    (tmp_path / "a_copy.json").write_text(
        (tmp_path / "a.json").read_text(encoding="utf-8"), encoding="utf-8")
    _artifact(tmp_path, "b.json", 2)
    boosters, _ = P.load_boosters(str(tmp_path), "*.json")
    assert len(boosters) == 2


def test_an_artifact_without_a_booster_is_SKIPPED_and_reported(tmp_path):
    _artifact(tmp_path, "a.json", 1)
    (tmp_path / "bad.json").write_text(json.dumps({"feature_cols": COLS}),
                                       encoding="utf-8")
    boosters, skipped = P.load_boosters(str(tmp_path), "*.json")
    assert len(boosters) == 1 and any("no booster" in s for s in skipped)


def test_a_NON_OBJECT_artifact_is_skipped_not_crashed(tmp_path):
    (tmp_path / "x.json").write_text("[]", encoding="utf-8")
    boosters, skipped = P.load_boosters(str(tmp_path), "*.json")
    assert boosters == {} and skipped


# --- the probe --------------------------------------------------------------

def test_a_booster_compared_to_ITSELF_is_a_perfect_match(tmp_path):
    """Anti-vacuity: if identity did not score 1.0 the metric would be meaningless."""
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 2)
    boosters, _ = P.load_boosters(str(tmp_path), "*.json")
    served = next(h for h, v in boosters.items() if v[0] == "a.json")
    rep = P.probe(boosters, served, 400, 7)
    self_row = next(r for r in rep["rows"] if r["is_served"])
    assert self_row["spearman_vs_served"] == pytest.approx(1.0)
    assert self_row["top_decile_overlap"] == 1.0


def test_DIFFERENT_boosters_diverge(tmp_path):
    """Two models trained on different signal columns must not look identical, or the
    probe cannot detect the thing it exists for."""
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 4)
    boosters, _ = P.load_boosters(str(tmp_path), "*.json")
    served = next(h for h, v in boosters.items() if v[0] == "a.json")
    rep = P.probe(boosters, served, 600, 11)
    assert rep["spearman_min"] < 0.99


def test_the_probe_is_DETERMINISTIC_for_a_fixed_seed(tmp_path):
    """A number nobody can re-derive is an assertion with a citation attached."""
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 4)
    boosters, _ = P.load_boosters(str(tmp_path), "*.json")
    served = next(h for h, v in boosters.items() if v[0] == "a.json")
    r1 = P.probe(boosters, served, 300, 99)
    r2 = P.probe(boosters, served, 300, 99)
    assert r1["spearman_min"] == r2["spearman_min"]


def test_a_FEATURE_SET_MISMATCH_refuses_to_score(tmp_path):
    """Scoring different feature sets on one matrix silently compares different
    functions of different inputs."""
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 2, cols=[f"g{i}" for i in range(6)])
    boosters, _ = P.load_boosters(str(tmp_path), "*.json")
    served = next(h for h, v in boosters.items() if v[0] == "a.json")
    assert P.probe(boosters, served, 100, 1)["status"] == "feature_set_mismatch"


# --- CLI --------------------------------------------------------------------

def test_FEWER_THAN_TWO_boosters_exits_1_not_0(tmp_path, capsys):
    """'Nothing to compare' must never read as 'they agree'."""
    _artifact(tmp_path, "a.json", 1)
    rc = P.main(["--root", str(tmp_path), "--served-artifact", "a.json"])
    assert rc == 1 and "not the same as agreement" in capsys.readouterr().err


def test_the_served_artifact_must_be_NAMED_not_guessed(tmp_path, capsys):
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 2)
    rc = P.main(["--root", str(tmp_path), "--served-artifact", "nope.json"])
    assert rc == 2 and "never guessed" in capsys.readouterr().err


def test_main_EXITS_NONZERO_when_boosters_diverge(tmp_path):
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 4)
    assert P.main(["--root", str(tmp_path), "--served-artifact", "a.json",
                   "--rows", "400"]) == 1


def test_the_report_states_the_input_is_SYNTHETIC_and_REFUSES_a_direction(
        tmp_path, capsys):
    """codex on #698: an earlier version claimed correlated real inputs push tree models
    toward agreeing, making this a BOUND. That direction is not established and is not a
    general property of tree ensembles — an independent Gaussian can yield more OR less
    agreement than the served distribution. The report must now refuse the direction, not
    supply one."""
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 4)
    P.main(["--root", str(tmp_path), "--served-artifact", "a.json", "--rows", "400"])
    out = capsys.readouterr().out
    assert "SYNTHETIC PROBE ONLY" in out
    assert "MORE or LESS agreement" in out
    assert "the direction is not established" in out


def test_the_report_forbids_the_THREE_inferences_it_once_supported(tmp_path, capsys):
    """Naming them explicitly, because each was published and each has to be findable as
    withdrawn: a production cost, a bound, and a claim about real inputs."""
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 4)
    P.main(["--root", str(tmp_path), "--served-artifact", "a.json", "--rows", "400"])
    out = capsys.readouterr().out
    assert "not a cost, not a bound" in out
    assert "requires a real-panel comparison" in out


def test_the_report_STILL_states_what_the_numbers_DO_establish(tmp_path, capsys):
    """A retraction that leaves nothing standing is its own kind of over-correction: the
    functions genuinely differ, and that is worth saying."""
    _artifact(tmp_path, "a.json", 1)
    _artifact(tmp_path, "b.json", 4)
    P.main(["--root", str(tmp_path), "--served-artifact", "a.json", "--rows", "400"])
    assert "not the same FUNCTION" in capsys.readouterr().out
