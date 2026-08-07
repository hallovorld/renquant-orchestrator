"""Would this probe have caught orch#895, and can it be fooled into silence?

The probe exists because `subrepo_pin_lag_check.py` measured lag in commit COUNT
and a `behind=1` that stranded an operator-directed risk-cap change was
indistinguishable from a `behind=1` typo fix. So the load-bearing tests here are
(a) the historical case is DETECTED, and (b) every way the answer can be unknown
refuses instead of reporting "in sync".
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops"))
import pinned_config_drift_probe as P  # noqa: E402

NAME = "renquant-strategy-104"
REL = "configs/strategy_config.json"


def _mirror(root: Path, doc: dict) -> Path:
    """A real git repo whose origin/main holds `doc`."""
    m = root / NAME
    (m / "configs").mkdir(parents=True)
    (m / REL).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    run = lambda *a: subprocess.run(["git", "-C", str(m), *a], check=True,
                                    capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("add", REL)
    run("commit", "-qm", "main")
    # origin/main without a network remote: point the ref at the local commit.
    sha = subprocess.run(["git", "-C", str(m), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    run("update-ref", "refs/remotes/origin/main", sha)
    return m


def _pinned(root: Path, doc: dict) -> Path:
    p = root / ".subrepo_runtime" / "repos" / NAME
    (p / "configs").mkdir(parents=True)
    (p / REL).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    run = lambda *a: subprocess.run(["git", "-C", str(p), *a], check=True,
                                    capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("add", REL)
    run("commit", "-qm", "pinned")
    return p


def _both(tmp_path, pinned_doc, main_doc):
    rq = tmp_path / "RQ"
    mirrors = tmp_path / "mirrors"
    mirrors.mkdir(parents=True)
    _pinned(rq, pinned_doc)
    _mirror(mirrors, main_doc)
    return rq, mirrors


class TestTheHistoricalCaseIsDetected:
    def test_the_stranded_cap_change_is_a_FINDING(self, tmp_path):
        """orch#895 exactly: main says 0.3, the pinned copy the book sizes
        against says 0.12, and the shas differ by ONE commit."""
        rq, mir = _both(tmp_path,
                        {"regime_params": {"BULL_CALM": {"max_position_pct": 0.12}}},
                        {"regime_params": {"BULL_CALM": {"max_position_pct": 0.3}}})
        r = P.compare(NAME, REL, rq=rq, mirror_root=mir)
        assert [d["key"] for d in r["diffs"]] == \
            ["regime_params.BULL_CALM.max_position_pct"]
        assert r["diffs"][0]["pinned"] == 0.12
        assert r["diffs"][0]["main"] == 0.3
        assert P.scan(rq=rq, mirror_root=mir)["n_drifted"] == 1

    def test_identical_configs_are_clean(self, tmp_path):
        doc = {"regime_params": {"BULL_CALM": {"max_position_pct": 0.3}}}
        rq, mir = _both(tmp_path, doc, dict(doc))
        assert P.compare(NAME, REL, rq=rq, mirror_root=mir)["diffs"] == []

    def test_a_differing_sha_with_an_identical_config_is_NOT_a_finding(self, tmp_path):
        """The point of a CONTENT check: a pin legitimately trails main most of
        the time. Only a behavioural difference is worth waking someone for."""
        doc = {"regime_params": {"BULL_CALM": {"max_position_pct": 0.3}}}
        rq, mir = _both(tmp_path, doc, dict(doc))
        r = P.compare(NAME, REL, rq=rq, mirror_root=mir)
        assert r["pinned_sha"] != r["main_sha"], "test premise: shas must differ"
        assert r["diffs"] == []


class TestTheDefaultIsInverted:
    def test_a_key_NOBODY_enumerated_still_reports(self, tmp_path):
        """An allow-list of 'keys that matter' would silently pass this."""
        rq, mir = _both(tmp_path,
                        {"some_future_knob": {"nested": 1}},
                        {"some_future_knob": {"nested": 2}})
        assert [d["key"] for d in P.compare(NAME, REL, rq=rq, mirror_root=mir)["diffs"]] \
            == ["some_future_knob.nested"]

    def test_a_key_present_on_only_ONE_side_reports(self, tmp_path):
        rq, mir = _both(tmp_path, {"a": 1}, {"a": 1, "b": 2})
        d = P.compare(NAME, REL, rq=rq, mirror_root=mir)["diffs"]
        assert d == [{"key": "b", "pinned": "<absent>", "main": 2}]

    def test_documentation_keys_are_the_ONLY_exemption(self, tmp_path):
        rq, mir = _both(tmp_path,
                        {"_sdl_reason": "old prose", "max_position_pct": 0.3},
                        {"_sdl_reason": "new prose", "max_position_pct": 0.3})
        assert P.compare(NAME, REL, rq=rq, mirror_root=mir)["diffs"] == []

    def test_a_reordered_list_is_a_difference(self, tmp_path):
        rq, mir = _both(tmp_path, {"watchlist": ["A", "B"]},
                        {"watchlist": ["B", "A"]})
        assert [d["key"] for d in P.compare(NAME, REL, rq=rq, mirror_root=mir)["diffs"]] \
            == ["watchlist"]


class TestSilenceIsNeverReadAsAgreement:
    def test_a_missing_pinned_config_REFUSES(self, tmp_path):
        rq, mir = _both(tmp_path, {"a": 1}, {"a": 1})
        (rq / ".subrepo_runtime" / "repos" / NAME / REL).unlink()
        with pytest.raises(P.Unusable, match="pinned config absent"):
            P.compare(NAME, REL, rq=rq, mirror_root=mir)

    def test_a_mirror_with_no_git_REFUSES(self, tmp_path):
        rq, mir = _both(tmp_path, {"a": 1}, {"a": 1})
        import shutil
        shutil.rmtree(mir / NAME / ".git")
        with pytest.raises(P.Unusable, match="no local mirror"):
            P.compare(NAME, REL, rq=rq, mirror_root=mir)

    def test_a_mirror_with_no_origin_main_REFUSES(self, tmp_path):
        rq, mir = _both(tmp_path, {"a": 1}, {"a": 1})
        subprocess.run(["git", "-C", str(mir / NAME), "update-ref", "-d",
                        "refs/remotes/origin/main"], check=True, capture_output=True)
        with pytest.raises(P.Unusable):
            P.compare(NAME, REL, rq=rq, mirror_root=mir)

    def test_malformed_pinned_json_REFUSES(self, tmp_path):
        rq, mir = _both(tmp_path, {"a": 1}, {"a": 1})
        (rq / ".subrepo_runtime" / "repos" / NAME / REL).write_text("{", encoding="utf-8")
        with pytest.raises(P.Unusable, match="pinned config unreadable"):
            P.compare(NAME, REL, rq=rq, mirror_root=mir)

    def test_a_refusal_exits_2_and_never_0(self, tmp_path):
        rq, mir = _both(tmp_path, {"a": 1}, {"a": 1})
        (rq / ".subrepo_runtime" / "repos" / NAME / REL).unlink()
        assert P.main(["--rq-root", str(rq), "--mirror-root", str(mir)]) == \
            P.EXIT_UNUSABLE

    def test_the_compared_main_sha_and_DATE_are_reported(self, tmp_path):
        """A stale mirror can make real drift look like agreement, so the probe
        must state which main it compared against and when that main was made."""
        rq, mir = _both(tmp_path, {"a": 1}, {"a": 1})
        r = P.compare(NAME, REL, rq=rq, mirror_root=mir)
        assert len(r["main_sha"]) == 40
        assert r["main_committed_at"].startswith("20")
        assert r["main_sha"][:8] in P.render({"results": [r], "refusals": []})
        assert r["main_committed_at"] in P.render({"results": [r], "refusals": []})


class TestExitCodes:
    def test_drift_exits_1(self, tmp_path):
        rq, mir = _both(tmp_path, {"max_position_pct": 0.12},
                        {"max_position_pct": 0.3})
        assert P.main(["--rq-root", str(rq), "--mirror-root", str(mir)]) == P.EXIT_DRIFT

    def test_clean_exits_0(self, tmp_path):
        rq, mir = _both(tmp_path, {"max_position_pct": 0.3},
                        {"max_position_pct": 0.3})
        assert P.main(["--rq-root", str(rq), "--mirror-root", str(mir)]) == P.EXIT_OK


def test_the_probe_never_writes():
    """Read-only by construction — the same guard the broker-parity probe carries."""
    body = (REPO / "ops" / "pinned_config_drift_probe.py").read_text(
        encoding="utf-8").split('"""', 2)[-1]
    for forbidden in ("write_text(", "open(", '"fetch"', '"checkout"', '"reset"',
                      '"pull"', "unlink(", "mkdir("):
        assert forbidden not in body, forbidden
