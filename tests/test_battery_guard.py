"""ops/battery_guard.py — page while the Mac is still on, once per discharge band."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops"))
import battery_guard as bg  # noqa: E402

DISCH = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t{p}%; discharging; 3:22 remaining present: true"
CHARG = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t{p}%; charging; 1:10 remaining present: true"
FULL = " -InternalBattery-0 (id=1)\t100%; charged; 0:00 remaining present: true"


def test_parse():
    assert bg.parse(DISCH.format(p=49)) == (49, "discharging")
    assert bg.parse(CHARG.format(p=12)) == (12, "charging")
    assert bg.parse(FULL) == (100, "charged")
    assert bg.parse("no battery here") is None


def test_pages_once_per_band_while_discharging():
    assert bg.decide(49, "discharging", None) == (False, None)
    assert bg.decide(40, "discharging", None) == (True, 40)
    assert bg.decide(38, "discharging", 40) == (False, 40)      # same band: no repeat
    assert bg.decide(25, "discharging", 40) == (True, 25)       # lower band pages again
    assert bg.decide(14, "discharging", 25) == (True, 15)
    assert bg.decide(5, "discharging", 15) == (False, 15)


def test_charging_never_pages_and_resets_the_episode():
    assert bg.decide(10, "charging", 15) == (False, None)
    assert bg.decide(10, "discharging", None) == (True, 15)     # next episode pages afresh


def test_main_pages_records_state_and_dedupes(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(bg, "alert", lambda t, b, **k: sent.append(t) or True)
    monkeypatch.setattr(bg, "STATE", tmp_path / "s.json")
    assert bg.main(DISCH.format(p=24)) == 0
    assert len(sent) == 1 and "24%" in sent[0]
    assert json.loads((tmp_path / "s.json").read_text())["band"] == 25
    assert bg.main(DISCH.format(p=23)) == 0 and len(sent) == 1   # same band
    assert bg.main(CHARG.format(p=30)) == 0 and len(sent) == 1
    assert json.loads((tmp_path / "s.json").read_text())["band"] is None


def test_unreadable_battery_state_is_loud_not_silent(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(bg, "alert", lambda t, b, **k: sent.append(t) or True)
    monkeypatch.setattr(bg, "STATE", tmp_path / "s.json")
    assert bg.main("garbage") == 1 and sent and "UNREADABLE" in sent[0]


def test_manifest_and_plist_agree():
    import hashlib
    m = json.loads((REPO / "ops/launchd_manifest.json").read_text())["jobs"]["com.renquant.battery-guard"]
    assert m["program_args"][1].endswith("/renquant-orchestrator-run/ops/battery_guard.py")
    assert m["program_args_sha256"] == hashlib.sha256(json.dumps(m["program_args"]).encode()).hexdigest()
    import plistlib
    pl = plistlib.loads((REPO / "ops/renquant104/com.renquant.battery-guard.plist").read_bytes())
    assert pl["ProgramArguments"] == m["program_args"] and pl["StartInterval"] == 900
