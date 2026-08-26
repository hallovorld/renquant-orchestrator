"""The gate1-declares / gate2-enacts comparison, and the two ways it must not lie.

The check exists because #1067 put gate 2's state in a file OUTSIDE git, so
merging the fix cannot create it. The failure it must catch is a run checkout
that syncs #1067 while `data/rq105/intraday_decisioning.armed.json` does not
exist: the pinned config still says `enabled: true` and no session decides
anything.

Two failure modes of the check itself are pinned harder than the happy path:

  * it must NOT report a finding today, when the deployed wrapper hard-exports
    and the arming file is legitimately absent — that would be a guard judging
    an object the running system does not consult;
  * it must NOT report ok in that case either. "Not checkable" is exit 2.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "ops" / "renquant105" / "rq105_arming_enactment_check.py"

_spec = importlib.util.spec_from_file_location("rq105_arming_enactment_check",
                                               MODULE_PATH)
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)


# --- fixtures: a fake umbrella root and a fake RUN checkout -------------------

POST_1067_WRAPPER = """#!/bin/sh
ARMING_FILE="$RQ_ROOT/data/rq105/intraday_decisioning.armed.json"
if ARMED_PROVENANCE=$(python3 -m renquant_orchestrator.rq105_arming "$ARMING_FILE"); then
  export RENQUANT_INTRADAY_DECISIONING=1
fi
"""

PRE_1067_WRAPPER = """#!/bin/sh
export RENQUANT_INTRADAY_DECISIONING=1
"""


def _rq_root(tmp_path, *, gate1, arming=None) -> Path:
    root = tmp_path / "RenQuant"
    cfg = root / chk.PINNED_CONFIG
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"intraday_decisioning": {"enabled": gate1}}),
                   encoding="utf-8")
    if arming is not None:
        f = root / chk.ARMING_FILE
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(arming, encoding="utf-8")
    return root


def _orch_root(tmp_path, wrapper: str, *, with_validator: bool = True) -> Path:
    root = tmp_path / "orch-run"
    w = root / chk.WRAPPER
    w.parent.mkdir(parents=True, exist_ok=True)
    w.write_text(wrapper, encoding="utf-8")
    if with_validator:
        dst = root / "src" / "renquant_orchestrator" / "rq105_arming.py"
        dst.parent.mkdir(parents=True, exist_ok=True)
        # The REAL validator, copied — the check must delegate to the code in
        # force, so a stub here would test a fiction.
        dst.write_text(
            (REPO / "src" / "renquant_orchestrator" / "rq105_arming.py")
            .read_text(encoding="utf-8"), encoding="utf-8")
    return root


ARMED_JSON = json.dumps({"armed": True, "operator": "renhao",
                         "armed_at": "2026-08-26", "authority": "orch#1049"})


def _run(rq, orch) -> int:
    return chk.main(["--rq-root", str(rq), "--orch-root", str(orch)])


# --- the finding this check exists for ---------------------------------------

def test_the_cutover_disarm_is_a_FINDING(tmp_path, capsys):
    """#1067 deployed, arming file never created — the exact hazard."""
    rq = _rq_root(tmp_path, gate1=True)                    # no arming file
    orch = _orch_root(tmp_path, POST_1067_WRAPPER)
    assert _run(rq, orch) == chk.EXIT_FINDING
    out = capsys.readouterr().out
    assert "NOT armed" in out and "absent" in out


def test_armed_false_is_a_finding_not_a_pass(tmp_path):
    """Disarming by content, with gate 1 still claiming enabled."""
    rq = _rq_root(tmp_path, gate1=True, arming=json.dumps({"armed": False}))
    assert _run(rq, _orch_root(tmp_path, POST_1067_WRAPPER)) == chk.EXIT_FINDING


def test_an_authorisation_missing_its_provenance_fields_is_a_finding(tmp_path):
    rq = _rq_root(tmp_path, gate1=True,
                  arming=json.dumps({"armed": True, "operator": "  "}))
    assert _run(rq, _orch_root(tmp_path, POST_1067_WRAPPER)) == chk.EXIT_FINDING


def test_both_gates_agreeing_is_clean(tmp_path):
    rq = _rq_root(tmp_path, gate1=True, arming=ARMED_JSON)
    assert _run(rq, _orch_root(tmp_path, POST_1067_WRAPPER)) == chk.EXIT_OK


def test_gate1_off_declares_nothing_to_enact(tmp_path):
    """The committed default is OFF; an unarmed gate 2 then agrees with it."""
    rq = _rq_root(tmp_path, gate1=False)
    assert _run(rq, _orch_root(tmp_path, POST_1067_WRAPPER)) == chk.EXIT_OK


# --- the two ways the check itself must not lie ------------------------------

def test_todays_predeploy_state_is_UNVERIFIABLE_not_a_finding(tmp_path, capsys):
    """The anti-false-positive. On 2026-08-26 the deployed wrapper hard-exports
    and the arming file does not exist — reporting that as "gate 2 not armed"
    would be judging a file the running system never reads."""
    rq = _rq_root(tmp_path, gate1=True)                    # no arming file
    orch = _orch_root(tmp_path, PRE_1067_WRAPPER, with_validator=False)
    assert _run(rq, orch) == chk.EXIT_UNVERIFIABLE
    assert "predates the arming-file gate" in capsys.readouterr().err


def test_the_predeploy_state_is_not_reported_as_OK_either(tmp_path):
    """The anti-vacuity half of the pair. An unverifiable gate must not read as
    a checked one — `ops_audit` lands exit 2 as UNUSABLE, exit 0 as clean."""
    rq = _rq_root(tmp_path, gate1=True, arming=ARMED_JSON)
    orch = _orch_root(tmp_path, PRE_1067_WRAPPER, with_validator=False)
    assert _run(rq, orch) != chk.EXIT_OK


# --- unreadable inputs are never a silent pass -------------------------------

@pytest.mark.parametrize("payload", ['{"intraday_decisioning": {}}',
                                     '{"intraday_decisioning": {"enabled": "true"}}',
                                     '{"intraday_decisioning": {"enabled": 1}}',
                                     '{"no_such_section": true}',
                                     'not json at all'])
def test_a_malformed_gate1_is_unverifiable_not_off(tmp_path, payload):
    """`"true"` is not true and `"false"` is truthy. Either read as "gate 1 is
    off" would silence this check on the config that most needs reading."""
    rq = tmp_path / "RenQuant"
    cfg = rq / chk.PINNED_CONFIG
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(payload, encoding="utf-8")
    assert _run(rq, _orch_root(tmp_path, POST_1067_WRAPPER)) == chk.EXIT_UNVERIFIABLE


def test_a_missing_pinned_config_is_unverifiable(tmp_path):
    assert _run(tmp_path / "nope",
                _orch_root(tmp_path, POST_1067_WRAPPER)) == chk.EXIT_UNVERIFIABLE


def test_an_unrecognised_wrapper_is_unverifiable_not_unarmed(tmp_path):
    """A renamed or restructured wrapper means the mechanism is unknown. Calling
    that "not armed" would be a finding derived from a failed grep."""
    rq = _rq_root(tmp_path, gate1=True, arming=ARMED_JSON)
    orch = _orch_root(tmp_path, "#!/bin/sh\necho hello\n", with_validator=False)
    assert _run(rq, orch) == chk.EXIT_UNVERIFIABLE


def test_a_wrapper_without_its_validator_is_unverifiable(tmp_path):
    """Wrapper and validator shipped apart — the gate cannot be read as one."""
    rq = _rq_root(tmp_path, gate1=True, arming=ARMED_JSON)
    orch = _orch_root(tmp_path, POST_1067_WRAPPER, with_validator=False)
    assert _run(rq, orch) == chk.EXIT_UNVERIFIABLE


def test_the_validator_is_read_from_the_DEPLOYED_checkout(tmp_path):
    """Not from this one. A deploy lag is exactly what this detector reports, so
    reading the local copy while judging the remote wrapper would hide it."""
    rq = _rq_root(tmp_path, gate1=True, arming=ARMED_JSON)
    orch = _orch_root(tmp_path, POST_1067_WRAPPER)
    (orch / "src" / "renquant_orchestrator" / "rq105_arming.py").write_text(
        "def evaluate_arming_file(path):\n"
        "    return False, 'deployed validator says no'\n", encoding="utf-8")
    assert _run(rq, orch) == chk.EXIT_FINDING


# --- the markers are pinned to the wrapper actually in this repo -------------

def test_this_repos_wrapper_is_the_arming_file_mechanism():
    """If the wrapper is reverted or the module renamed, fail HERE — not by
    silently reclassifying every future run as `hard-export`."""
    src = (REPO / chk.WRAPPER).read_text(encoding="utf-8")
    assert chk.ARMING_GATE_MARKER in src
    assert chk.gate2_mechanism(REPO) == "arming-file"


def test_the_marker_order_is_what_disambiguates_the_two_mechanisms():
    """The post-#1067 wrapper contains the hard-export line TOO, inside the
    `if`. Testing the export first would misread the new gate as the old one —
    which is the whole difference between exit 1 and exit 2."""
    src = (REPO / chk.WRAPPER).read_text(encoding="utf-8")
    assert chk.HARD_EXPORT_MARKER in src, (
        "both markers must be present for this test to mean anything")
    assert chk.gate2_mechanism(REPO) == "arming-file"


def test_a_marker_that_survives_only_in_a_COMMENT_does_not_count(tmp_path):
    """A reverted wrapper usually keeps the prose. If a mention in a comment
    counted, that wrapper would read as the arming-file gate and the absent file
    would be reported as a disarm — a finding derived from a stale sentence,
    about a mechanism the running system no longer has."""
    reverted = ("#!/bin/sh\n"
                "# gate 2 used to run renquant_orchestrator.rq105_arming against\n"
                "# data/rq105/intraday_decisioning.armed.json; reverted 2026-xx-xx\n"
                "export RENQUANT_INTRADAY_DECISIONING=1\n")
    rq = _rq_root(tmp_path, gate1=True)                    # no arming file
    orch = _orch_root(tmp_path, reverted, with_validator=False)
    assert chk.gate2_mechanism(orch) == "hard-export"
    assert _run(rq, orch) == chk.EXIT_UNVERIFIABLE


def test_the_detector_writes_nothing(tmp_path):
    """Membership rule for `ops_audit`, asserted behaviourally and not only by
    the source-regex in test_ops_audit.py."""
    rq = _rq_root(tmp_path, gate1=True, arming=ARMED_JSON)
    orch = _orch_root(tmp_path, POST_1067_WRAPPER)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    _run(rq, orch)
    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
