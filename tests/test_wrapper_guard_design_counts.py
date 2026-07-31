"""The design in doc/design/2026-07-30-wrapper-production-path-guard.md rests on
counts. These pin the counts so the design cannot quietly rot away from them.

codex round 1 asked to "distinguish scheduled production entry points from the one
unreviewed dev-checkout job before applying a uniform policy". Re-measured 2026-08-01
that set has **two** members, and a second entry point with no manifest row exists and
is SHIPPED. A policy written around a singleton does not describe either set.
"""

from __future__ import annotations

import json
import pathlib
import plistlib

REPO = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = json.loads((REPO / "ops" / "launchd_manifest.json").read_text(encoding="utf-8"))
JOBS = MANIFEST.get("jobs") or MANIFEST


def _roots():
    import collections

    c = collections.Counter()
    for row in JOBS.values():
        for a in (row or {}).get("program_args") or []:
            s = str(a)
            if not s.endswith((".sh", ".py")):
                continue
            c["run" if "orchestrator-run/" in s else
              "dev" if "/renquant-orchestrator/" in s else
              "renquant" if "/RenQuant/" in s else "other"] += 1
    return c


def test_the_dev_checkout_set_has_TWO_members_not_one():
    """§4.2's singleton framing. If this ever reads 1 again the design's argument
    becomes true and the section should be simplified — deliberately, not by drift."""
    assert _roots()["dev"] == 2, dict(_roots())


def test_the_manifest_root_split_is_pinned():
    r = _roots()
    assert r["renquant"] == 21 and r["run"] == 20


def test_shadow_ab_daily_manifest_and_committed_plist_DISAGREE():
    """§4.2 decides the reviewed location comes from the manifest row. Under that
    rule the committed plist names a location the rule refuses. Both cannot be right."""
    row = JOBS["com.renquant.shadow-ab-daily"]["program_args"]
    manifest_target = next(a for a in row if a.endswith(".sh"))
    d = plistlib.load(open(REPO / "deploy" / "com.renquant.shadow-ab-daily.plist", "rb"))
    plist_target = next(a for a in d["ProgramArguments"] if a.endswith(".sh"))
    assert ".subrepo_runtime" in manifest_target
    assert ".subrepo_runtime" not in plist_target
    assert manifest_target != plist_target


def test_a_SHIPPED_plist_exists_with_no_manifest_row():
    """§4.3's population is not a singleton, and this member is shipped."""
    shipped = {p.stem for p in (REPO / "deploy").glob("*.plist")}
    orphans = sorted(s for s in shipped if s not in JOBS)
    assert orphans == ["com.renquant.stops-liveness"], orphans
