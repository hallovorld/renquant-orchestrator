"""Tests for ``model_identity_tripwire`` — the #484 §7.2a consumer.

All bundles/manifests are synthetic tmp-path fixtures; alerts go to an
injected poster (or ``--quiet``). No test touches ntfy, a broker, live state,
or production paths.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from renquant_orchestrator import model_identity_tripwire as mod
from renquant_orchestrator.outage_monitor import TAG_DEGRADED, TAG_OUTAGE, emit_alert


# --- synthetic fixtures ---------------------------------------------------------

#: The two panel identities from the 2026-06-25 incident (#484 §7.2a):
#: sessions 06-22..25 stamped the 06-21 model, 06-26..07-02 the regressed
#: 05-18 model.
SHA_0621 = "04d7a381" + "0" * 56
SHA_0518 = "5ce63326" + "0" * 56


def bundle(date: str, sha: str | None, run_type: str = "live") -> dict:
    payload: dict = {
        "schema_version": 1,
        "run_id": f"{date}-{run_type}-{(sha or 'deadbeef')[:8]}",
        "run_type": run_type,
        "config_hash": "sha256:" + "c" * 64,
    }
    if sha is not None:
        payload["artifact_hashes"] = {
            "panel": f"sha256:{sha}",
            "global_calibration": "sha256:" + "b" * 64,
        }
    return payload


def manifest_info(deployed_at: str, generation: int = 1) -> dict:
    return {
        "path": "unused",
        "generation": generation,
        "deployed_at": deployed_at,
        "deployed_date": deployed_at[:10],
        "state": "deployed",
        "generation_status": None,
    }


def valid_manifest_payload(deployed_at: str = "2026-06-20T12:00:00Z") -> dict:
    """A schema-v1-valid deployment manifest (passes the #477 loader)."""
    return {
        "schema_version": 1,
        "kind": "deployment-manifest",
        "generation": 1,
        "generated_at": deployed_at,
        "repos": {
            "renquant-artifacts": {
                "remote": "https://github.com/hallovorld/renquant-artifacts",
                "branch": "main",
                "commit": "a" * 40,
                "role": "artifact registry",
                "status": "active",
            },
        },
        "artifact_store": {"repo": "renquant-artifacts", "path": ""},
        "deployment": {
            "deployed_at": deployed_at,
            "deployed_by": "operator",
            "state": "captured",
            "supersedes_sha256": None,
            "verify": {
                "profile": "readonly-e2e",
                "args": {"min_admits": 1},
                "exit": 0,
                "evidence_ref": None,
            },
        },
    }


class PosterSpy:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, title, body, topic, *, priority=3, tags="chart"):
        self.calls.append({
            "title": title, "body": body, "topic": topic,
            "priority": priority, "tags": tags,
        })


# --- normalize / extract ----------------------------------------------------------

def test_normalize_sha_strips_prefix_and_case():
    assert mod.normalize_sha("sha256:ABCD") == "abcd"
    assert mod.normalize_sha("  abcd  ") == "abcd"
    assert mod.normalize_sha("sha256:") is None
    assert mod.normalize_sha(None) is None
    assert mod.normalize_sha(123) is None


def test_extract_identity_reads_panel_alias_and_session_date():
    ident = mod.extract_model_identity(bundle("2026-06-26", SHA_0518))
    assert ident.panel_sha == SHA_0518
    assert ident.session_date == "2026-06-26"
    assert ident.run_id.startswith("2026-06-26-live-")


def test_extract_identity_falls_back_to_raw_panel_scoring_key():
    payload = bundle("2026-06-26", None)
    payload["artifact_hashes"] = {
        "ranking.panel_scoring.artifact_path": f"sha256:{SHA_0518}",
    }
    assert mod.extract_model_identity(payload).panel_sha == SHA_0518


def test_extract_identity_fail_soft_on_garbage():
    assert mod.extract_model_identity(None).panel_sha is None
    assert mod.extract_model_identity({}).session_date is None


# --- the three contract cases ------------------------------------------------------

def test_0625_regression_shape_alerts_outage():
    """Identity changed, manifest shows NO pin change -> OUTAGE page."""
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        manifest_info=manifest_info("2026-06-20T12:00:00Z"),
    )
    assert report.verdict == mod.VERDICT_UNEXPLAINED
    assert report.title_tag == TAG_OUTAGE
    assert report.title == "RENQUANT-104 OUTAGE MODEL-IDENTITY 2026-06-26"
    assert report.priority == 5
    # The change line leads the body so ntfy truncation can never hide it.
    assert report.body_lines[0].startswith("panel identity changed: 04d7a381")
    assert "UNEXPLAINED" in report.body

    poster = PosterSpy()
    fired = emit_alert(report, topic="t", poster=poster, only_alerts=True)
    assert fired and poster.calls[0]["priority"] == 5


def test_pin_advance_change_passes_with_info():
    """Identity changed but the manifest records a deployment at/after the
    previous session -> legitimate, INFO line, no page."""
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        manifest_info=manifest_info("2026-06-25T21:00:00Z", generation=2),
    )
    assert report.verdict == mod.VERDICT_PIN_ADVANCE
    assert report.title_tag is None and report.title is None
    assert any("INFO explained: pin advanced" in l for l in report.body_lines)

    poster = PosterSpy()
    assert not emit_alert(report, topic="t", poster=poster, only_alerts=True)
    assert poster.calls == []


def test_recorded_promotion_passes_with_info():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        manifest_info=manifest_info("2026-06-20T12:00:00Z"),
        promotion_shas={SHA_0518},
    )
    assert report.verdict == mod.VERDICT_PROMOTION
    assert report.title_tag is None
    assert any("recorded promotion" in l for l in report.body_lines)


def test_unchanged_identity_is_quiet():
    report = mod.build_tripwire_report(
        bundle("2026-06-24", SHA_0621),
        bundle("2026-06-23", SHA_0621),
        manifest_info=manifest_info("2026-06-01T12:00:00Z"),
    )
    assert report.verdict == mod.VERDICT_UNCHANGED
    assert report.title_tag is None
    assert any("identity unchanged" in l for l in report.body_lines)


# --- fail-soft paths ---------------------------------------------------------------

def test_missing_previous_bundle_fails_soft():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        None,
        manifest_info=manifest_info("2026-06-20T12:00:00Z"),
    )
    assert report.verdict == mod.VERDICT_INSUFFICIENT
    assert report.title_tag is None
    assert "previous_session_identity" in report.missing


def test_missing_latest_identity_fails_soft():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", None),
        bundle("2026-06-25", SHA_0621),
        manifest_info=manifest_info("2026-06-20T12:00:00Z"),
    )
    assert report.verdict == mod.VERDICT_INSUFFICIENT
    assert "latest_panel_identity" in report.missing


def test_identity_change_with_missing_manifest_degrades_not_pages_outage():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        manifest_info=None,
        manifest_problem="deployment manifest missing",
    )
    assert report.verdict == mod.VERDICT_UNVERIFIABLE
    assert report.title_tag == TAG_DEGRADED
    assert "deployment_manifest" in report.missing


def test_unparseable_dates_degrade():
    latest = bundle("2026-06-26", SHA_0518)
    previous = bundle("2026-06-25", SHA_0621)
    previous["run_id"] = "no-date-here"
    report = mod.build_tripwire_report(
        latest, previous,
        manifest_info=manifest_info("2026-06-20T12:00:00Z"),
    )
    assert report.verdict == mod.VERDICT_UNVERIFIABLE
    assert report.title_tag == TAG_DEGRADED


def test_generation_mismatch_adds_degraded_note_without_downgrading_outage():
    info = manifest_info("2026-06-20T12:00:00Z")
    info["generation_status"] = "stale_or_replayed"
    outage_report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        manifest_info=info,
    )
    assert outage_report.title_tag == TAG_OUTAGE  # worst wins
    quiet_report = mod.build_tripwire_report(
        bundle("2026-06-24", SHA_0621),
        bundle("2026-06-23", SHA_0621),
        manifest_info=info,
    )
    assert quiet_report.title_tag == TAG_DEGRADED
    assert any("stale_or_replayed" in l for l in quiet_report.body_lines)


# --- manifest reader (fail-soft wrapper over the #477 loader) -----------------------

def test_load_manifest_info_reads_valid_manifest(tmp_path):
    path = tmp_path / "deployment-manifest.json"
    path.write_text(json.dumps(valid_manifest_payload()), encoding="utf-8")
    info, problem = mod.load_manifest_info(
        manifest_path=path, state_root=tmp_path,
    )
    assert problem is None
    assert info["generation"] == 1
    assert info["deployed_date"] == "2026-06-20"
    assert info["generation_status"] is None  # no durable record in tmp root


def test_load_manifest_info_fail_soft_on_missing_and_invalid(tmp_path):
    info, problem = mod.load_manifest_info(
        manifest_path=tmp_path / "nope.json", state_root=tmp_path,
    )
    assert info is None and "unreadable" in problem
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    info, problem = mod.load_manifest_info(manifest_path=bad, state_root=tmp_path)
    assert info is None and "schema validation failed" in problem


# --- promotions ledger ---------------------------------------------------------------

def test_load_promotion_shas_json_and_jsonl(tmp_path):
    as_json = tmp_path / "promotions.json"
    as_json.write_text(
        json.dumps([{"panel_sha": f"sha256:{SHA_0518}", "date": "2026-06-26"}]),
        encoding="utf-8",
    )
    assert mod.load_promotion_shas(as_json) == {SHA_0518}
    as_jsonl = tmp_path / "promotions.jsonl"
    as_jsonl.write_text(
        json.dumps({"model_content_sha256": SHA_0621}) + "\nnot-json\n",
        encoding="utf-8",
    )
    assert mod.load_promotion_shas(as_jsonl) == {SHA_0621}
    assert mod.load_promotion_shas(tmp_path / "missing.json") == set()
    assert mod.load_promotion_shas(None) == set()


# --- bundle discovery ----------------------------------------------------------------

def _write_bundle(tmp_path, name: str, payload: dict, mtime: float):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_find_session_bundles_skips_same_day_reruns(tmp_path):
    now = time.time()
    _write_bundle(tmp_path, "run_bundle_a.json", bundle("2026-06-25", SHA_0621), now - 300)
    _write_bundle(
        tmp_path, "run_bundle_rerun.json", bundle("2026-06-26", SHA_0518), now - 100,
    )
    latest = _write_bundle(
        tmp_path, "run_bundle_latest.json", bundle("2026-06-26", SHA_0518), now,
    )
    found_latest, found_previous = mod.find_session_bundles(tmp_path)
    assert found_latest == latest
    assert found_previous == tmp_path / "run_bundle_a.json"


def test_find_session_bundles_fail_soft(tmp_path):
    assert mod.find_session_bundles(tmp_path / "nope") == (None, None)
    assert mod.find_session_bundles(tmp_path) == (None, None)


# --- CLI end-to-end -------------------------------------------------------------------

def test_main_exit_codes_for_the_three_cases(tmp_path, capsys):
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps(bundle("2026-06-26", SHA_0518)), encoding="utf-8")
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(bundle("2026-06-25", SHA_0621)), encoding="utf-8")

    stale_manifest = tmp_path / "manifest-stale.json"
    stale_manifest.write_text(
        json.dumps(valid_manifest_payload("2026-06-20T12:00:00Z")), encoding="utf-8",
    )
    advanced_manifest = tmp_path / "manifest-advanced.json"
    advanced_manifest.write_text(
        json.dumps(valid_manifest_payload("2026-06-25T21:00:00Z")), encoding="utf-8",
    )

    # 1) the 06-25 regression shape -> OUTAGE, exit 2
    rc = mod.main([
        "--latest-bundle", str(latest), "--previous-bundle", str(previous),
        "--manifest", str(stale_manifest), "--state-root", str(tmp_path),
        "--quiet",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2 and payload["verdict"] == mod.VERDICT_UNEXPLAINED

    # 2) pin advance -> pass, exit 0
    rc = mod.main([
        "--latest-bundle", str(latest), "--previous-bundle", str(previous),
        "--manifest", str(advanced_manifest), "--state-root", str(tmp_path),
        "--quiet",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["verdict"] == mod.VERDICT_PIN_ADVANCE

    # 3) missing previous bundle -> fail-soft exit 0 (3 under --require-inputs)
    rc = mod.main([
        "--latest-bundle", str(latest),
        "--manifest", str(stale_manifest), "--state-root", str(tmp_path),
        "--quiet",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["verdict"] == mod.VERDICT_INSUFFICIENT
    rc = mod.main([
        "--latest-bundle", str(latest),
        "--manifest", str(stale_manifest), "--state-root", str(tmp_path),
        "--quiet", "--require-inputs",
    ])
    capsys.readouterr()
    assert rc == 3


def test_main_unreadable_latest_bundle_exits_3(tmp_path, capsys):
    rc = mod.main([
        "--latest-bundle", str(tmp_path / "nope.json"),
        "--state-root", str(tmp_path), "--quiet",
    ])
    capsys.readouterr()
    assert rc == 3
