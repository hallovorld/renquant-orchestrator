"""Tests for ``model_identity_tripwire`` — the #484 §7.2a consumer.

All bundles/manifests/records are synthetic tmp-path fixtures; alerts go to
an injected poster (or ``--quiet``). No test touches ntfy, a broker, live
state, or production paths.

Contract under test (post Codex review on #485): an identity change is
explained ONLY by a verifiable binding — the ``expected-model-identity.json``
record (or a promotions-ledger entry) naming the NEW sha. Manifest timestamps
are diagnostic metadata and can never explain a change. Missing inputs page
DEGRADED by default (a monitor that dies quiet is the #484 failure mode);
``--offline`` downgrades them to quiet notes for local forensics.
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


def binding(sha: str, generation: int = 1) -> dict:
    return {
        "schema_version": 1,
        "kind": "expected-model-identity",
        "generation": generation,
        "panel_sha": sha,
        "recorded_at": "2026-06-22T21:13:00Z",
    }


def manifest_info(deployed_at: str = "2026-06-20T12:00:00Z",
                  generation: int = 1) -> dict:
    return {
        "path": "unused",
        "generation": generation,
        "deployed_at": deployed_at,
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


# --- the contract cases -------------------------------------------------------------

def test_0625_regression_shape_alerts_outage():
    """Identity changed, binding still names the old sha -> OUTAGE page."""
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0621),
        manifest_info=manifest_info(),
    )
    assert report.verdict == mod.VERDICT_BINDING_MISMATCH
    assert report.title_tag == TAG_OUTAGE
    assert report.title == "RENQUANT-104 OUTAGE MODEL-IDENTITY 2026-06-26"
    assert report.priority == 5
    # The contradiction leads the body so ntfy truncation can never hide it.
    assert "CONTRADICTS" in report.body_lines[0]
    assert "unauthorized model is serving" in report.body_lines[0]

    poster = PosterSpy()
    fired = emit_alert(report, topic="t", poster=poster, only_alerts=True)
    assert fired and poster.calls[0]["priority"] == 5


def test_0625_regression_shape_without_binding_record_alerts_outage():
    """Same shape, no binding recorded at all: still OUTAGE (unexplained)."""
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=None,
        manifest_info=manifest_info(),
    )
    assert report.verdict == mod.VERDICT_UNEXPLAINED
    assert report.title_tag == TAG_OUTAGE
    assert report.body_lines[0].startswith("panel identity changed: 04d7a381")
    assert "UNEXPLAINED" in report.body


def test_recorded_pin_advance_passes_with_info():
    """Identity changed AND the binding names the NEW sha -> authorized.

    Round 2: a clean quiet pass ALSO needs the prior identity's own chain
    position provable (see the chain-adjacency tests below) — supply it
    here via the promotions ledger so this stays the "fully clean"
    baseline case."""
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0518, generation=2),
        manifest_info=manifest_info(generation=2),
        promotion_ledger={SHA_0621: 1},
    )
    assert report.verdict == mod.VERDICT_PIN_ADVANCE
    assert report.title_tag is None and report.title is None
    assert any("recorded pin advance" in l for l in report.body_lines)

    poster = PosterSpy()
    assert not emit_alert(report, topic="t", poster=poster, only_alerts=True)
    assert poster.calls == []


def test_manifest_timestamp_alone_never_explains_a_change():
    """Codex #485: deployed_at ordering is diagnostic, not authorization."""
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=None,
        # manifest captured AFTER the previous session — would have passed
        # the old (unsound) timestamp predicate:
        manifest_info=manifest_info(deployed_at="2026-06-25T21:00:00Z",
                                    generation=2),
    )
    assert report.verdict == mod.VERDICT_UNEXPLAINED
    assert report.title_tag == TAG_OUTAGE


def test_recorded_promotion_passes_with_info():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=None,
        manifest_info=manifest_info(),  # generation=1: the epoch floor
        promotion_ledger={SHA_0518: 1},
        offline=True,  # quiet the no-binding coverage note
    )
    assert report.verdict == mod.VERDICT_PROMOTION
    assert report.title_tag is None
    assert any("recorded promotion" in l for l in report.body_lines)


def test_unchanged_identity_matching_binding_is_quiet():
    report = mod.build_tripwire_report(
        bundle("2026-06-24", SHA_0621),
        bundle("2026-06-23", SHA_0621),
        expected_identity=binding(SHA_0621),
        manifest_info=manifest_info(),
    )
    assert report.verdict == mod.VERDICT_UNCHANGED
    assert report.title_tag is None
    assert any("identity unchanged" in l for l in report.body_lines)
    assert any("matches the recorded authorized binding" in l
               for l in report.body_lines)


def test_unchanged_but_contradicting_binding_is_outage():
    """Both sessions serving an unauthorized model is still an OUTAGE."""
    report = mod.build_tripwire_report(
        bundle("2026-06-27", SHA_0518),
        bundle("2026-06-26", SHA_0518),
        expected_identity=binding(SHA_0621),
        manifest_info=manifest_info(),
    )
    assert report.verdict == mod.VERDICT_BINDING_MISMATCH
    assert report.title_tag == TAG_OUTAGE
    assert any("unchanged" in l for l in report.body_lines)


# --- missing-input posture (DEGRADED by default; quiet under offline) ---------------

def test_missing_previous_bundle_pages_degraded_by_default():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        None,
        expected_identity=binding(SHA_0518),
        manifest_info=manifest_info(),
    )
    assert report.verdict == mod.VERDICT_COVERAGE_LOST
    assert report.title_tag == TAG_DEGRADED
    assert "previous_session_identity" in report.missing


def test_missing_latest_identity_pages_degraded_by_default():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", None),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0621),
        manifest_info=manifest_info(),
    )
    assert report.verdict == mod.VERDICT_COVERAGE_LOST
    assert report.title_tag == TAG_DEGRADED
    assert "latest_panel_identity" in report.missing


def test_missing_manifest_pages_degraded_by_default():
    report = mod.build_tripwire_report(
        bundle("2026-06-24", SHA_0621),
        bundle("2026-06-23", SHA_0621),
        expected_identity=binding(SHA_0621),
        manifest_info=None,
        manifest_problem="deployment manifest missing",
    )
    assert report.verdict == mod.VERDICT_UNCHANGED
    assert report.title_tag == TAG_DEGRADED  # coverage contribution
    assert "deployment_manifest" in report.missing


def test_offline_mode_records_missing_inputs_quietly():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        None,
        expected_identity=None,
        manifest_info=None,
        offline=True,
    )
    assert report.verdict == mod.VERDICT_COVERAGE_LOST
    assert report.title_tag is None  # fail-soft notes, no page
    assert {"previous_session_identity", "expected_identity_binding",
            "deployment_manifest"} <= set(report.missing)


def test_missing_binding_never_downgrades_an_outage():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=None,
        manifest_info=None,
    )
    assert report.verdict == mod.VERDICT_UNEXPLAINED
    assert report.title_tag == TAG_OUTAGE  # worst wins over DEGRADED notes


def test_generation_mismatch_adds_degraded_note():
    info = manifest_info()
    info["generation_status"] = "stale_or_replayed"
    report = mod.build_tripwire_report(
        bundle("2026-06-24", SHA_0621),
        bundle("2026-06-23", SHA_0621),
        expected_identity=binding(SHA_0621),
        manifest_info=info,
    )
    assert report.verdict == mod.VERDICT_UNCHANGED
    assert report.title_tag == TAG_DEGRADED
    assert any("stale_or_replayed" in l for l in report.body_lines)


# --- the expected-identity record (forward-only, atomic) ----------------------------

class TestExpectedIdentityRecord:
    def test_record_and_read_roundtrip(self, tmp_path):
        path = mod.record_expected_identity(
            tmp_path, generation=1, panel_sha=f"sha256:{SHA_0621}",
        )
        assert path.name == mod.EXPECTED_IDENTITY_FILENAME
        record, problem = mod.read_expected_identity(tmp_path)
        assert problem is None
        assert record["panel_sha"] == SHA_0621  # normalized, prefix stripped
        assert record["generation"] == 1

    def test_rollback_generation_refused(self, tmp_path):
        mod.record_expected_identity(tmp_path, generation=3, panel_sha=SHA_0621)
        with pytest.raises(mod.ExpectedIdentityError, match="FORWARD-ONLY"):
            mod.record_expected_identity(tmp_path, generation=2,
                                         panel_sha=SHA_0518)

    def test_same_generation_rebind_refused_torn_apply(self, tmp_path):
        mod.record_expected_identity(tmp_path, generation=2, panel_sha=SHA_0621)
        with pytest.raises(mod.ExpectedIdentityError, match="never reused"):
            mod.record_expected_identity(tmp_path, generation=2,
                                         panel_sha=SHA_0518)

    def test_same_day_rerun_is_idempotent(self, tmp_path):
        mod.record_expected_identity(tmp_path, generation=2, panel_sha=SHA_0621)
        mod.record_expected_identity(tmp_path, generation=2, panel_sha=SHA_0621)
        record, problem = mod.read_expected_identity(tmp_path)
        assert problem is None and record["generation"] == 2

    def test_advance_rebinds_new_generation(self, tmp_path):
        mod.record_expected_identity(tmp_path, generation=1, panel_sha=SHA_0621)
        mod.record_expected_identity(tmp_path, generation=2, panel_sha=SHA_0518)
        record, _ = mod.read_expected_identity(tmp_path)
        assert record["panel_sha"] == SHA_0518 and record["generation"] == 2

    def test_invalid_inputs_refused(self, tmp_path):
        with pytest.raises(mod.ExpectedIdentityError, match="generation"):
            mod.record_expected_identity(tmp_path, generation=0,
                                         panel_sha=SHA_0621)
        with pytest.raises(mod.ExpectedIdentityError, match="64-hex"):
            mod.record_expected_identity(tmp_path, generation=1,
                                         panel_sha="not-a-sha")

    def test_read_fail_soft_on_malformed(self, tmp_path):
        (tmp_path / mod.EXPECTED_IDENTITY_FILENAME).write_text(
            "{not json", encoding="utf-8",
        )
        record, problem = mod.read_expected_identity(tmp_path)
        assert record is None and "unreadable" in problem
        (tmp_path / mod.EXPECTED_IDENTITY_FILENAME).write_text(
            json.dumps({"kind": "wrong"}), encoding="utf-8",
        )
        record, problem = mod.read_expected_identity(tmp_path)
        assert record is None and "malformed" in problem

    def test_missing_record_is_not_a_problem(self, tmp_path):
        assert mod.read_expected_identity(tmp_path) == (None, None)

    def test_write_refused_over_malformed_record(self, tmp_path):
        (tmp_path / mod.EXPECTED_IDENTITY_FILENAME).write_text(
            "{not json", encoding="utf-8",
        )
        with pytest.raises(mod.ExpectedIdentityError, match="malformed|unreadable"):
            mod.record_expected_identity(tmp_path, generation=1,
                                         panel_sha=SHA_0621)


# --- manifest reader (fail-soft wrapper over the #477 loader) -----------------------

def test_load_manifest_info_reads_valid_manifest(tmp_path):
    path = tmp_path / "deployment-manifest.json"
    path.write_text(json.dumps(valid_manifest_payload()), encoding="utf-8")
    info, problem = mod.load_manifest_info(
        manifest_path=path, state_root=tmp_path,
    )
    assert problem is None
    assert info["generation"] == 1
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


# --- promotions ledger (round 2: sha->generation binding) ---------------------------

def test_load_promotion_ledger_binds_sha_to_generation(tmp_path):
    as_json = tmp_path / "promotions.json"
    as_json.write_text(
        json.dumps([
            {"panel_sha": f"sha256:{SHA_0518}", "generation": 2, "date": "2026-06-26"},
        ]),
        encoding="utf-8",
    )
    assert mod.load_promotion_ledger(as_json) == {SHA_0518: 2}
    as_jsonl = tmp_path / "promotions.jsonl"
    as_jsonl.write_text(
        json.dumps({"model_content_sha256": SHA_0621, "generation": 1}) + "\nnot-json\n",
        encoding="utf-8",
    )
    assert mod.load_promotion_ledger(as_jsonl) == {SHA_0621: 1}
    assert mod.load_promotion_ledger(tmp_path / "missing.json") == {}
    assert mod.load_promotion_ledger(None) == {}


def test_load_promotion_ledger_legacy_bare_sha_entries_excluded(tmp_path):
    """Migration note: a pre-round-2 entry with no ``generation`` key is
    PARSED (fail-soft — never crashes the loader) but excluded from the
    returned map, since it cannot anchor the chain-adjacency check."""
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps([{"panel_sha": f"sha256:{SHA_0518}"}]),  # no "generation"
        encoding="utf-8",
    )
    assert mod.load_promotion_ledger(legacy) == {}


def test_load_promotion_ledger_rejects_bad_generation_values(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps([
            {"sha": SHA_0518, "generation": 0},
            {"sha": SHA_0621, "generation": True},
            {"sha": "c" * 64, "generation": -1},
        ]),
        encoding="utf-8",
    )
    assert mod.load_promotion_ledger(bad) == {}


# --- chain-adjacency supporting check (round 2) --------------------------------------

def test_chain_verified_when_previous_bound_to_older_generation():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0518, generation=2),
        manifest_info=manifest_info(generation=2),
        promotion_ledger={SHA_0621: 1},  # prior identity bound to gen 1 < 2
    )
    assert report.verdict == mod.VERDICT_PIN_ADVANCE
    assert report.title_tag is None
    assert any("chain verified" in l for l in report.body_lines)


def test_chain_coverage_gap_when_previous_has_no_ledger_binding():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0518, generation=2),
        manifest_info=manifest_info(generation=2),
        # no ledger entry for SHA_0621 (the previous identity) at all
    )
    assert report.verdict == mod.VERDICT_PIN_ADVANCE  # endpoint still proven
    assert report.title_tag == TAG_DEGRADED  # but the chain gap is alertable
    assert any("chain coverage gap" in l for l in report.body_lines)


def test_chain_coverage_gap_quiet_under_offline():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0518, generation=2),
        manifest_info=manifest_info(generation=2),
        offline=True,
    )
    assert report.verdict == mod.VERDICT_PIN_ADVANCE
    assert report.title_tag is None


def test_chain_broken_when_previous_binding_is_not_older():
    """The prior identity's OWN ledger binding is not older than the active
    generation — a non-monotonic/rollback shape. This is a PROVEN
    contradiction, so it escalates to OUTAGE and is never suppressed by
    --offline (unlike the coverage-gap case above)."""
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0518, generation=2),
        manifest_info=manifest_info(generation=2),
        promotion_ledger={SHA_0621: 2},  # NOT older than the active gen 2
        offline=True,
    )
    assert report.verdict == mod.VERDICT_PIN_ADVANCE  # endpoint still proven
    assert report.title_tag == TAG_OUTAGE  # chain contradiction: never quiet
    assert any("chain BROKEN" in l for l in report.body_lines)


def test_chain_check_skipped_at_generation_one_floor():
    report = mod.build_tripwire_report(
        bundle("2026-06-26", SHA_0518),
        bundle("2026-06-25", SHA_0621),
        expected_identity=binding(SHA_0518, generation=1),
        manifest_info=manifest_info(generation=1),
    )
    assert report.verdict == mod.VERDICT_PIN_ADVANCE
    assert report.title_tag is None
    assert any("epoch floor" in l for l in report.body_lines)


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

def _write_inputs(tmp_path):
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps(bundle("2026-06-26", SHA_0518)), encoding="utf-8")
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(bundle("2026-06-25", SHA_0621)), encoding="utf-8")
    manifest = tmp_path / "deployment-manifest.json"
    manifest.write_text(json.dumps(valid_manifest_payload()), encoding="utf-8")
    return latest, previous, manifest


def test_main_exit_codes_for_the_three_cases(tmp_path, capsys):
    latest, previous, manifest = _write_inputs(tmp_path)

    # 1) the 06-25 regression shape (binding names the OLD sha) -> OUTAGE, exit 2
    mod.record_expected_identity(tmp_path, generation=1, panel_sha=SHA_0621)
    rc = mod.main([
        "--latest-bundle", str(latest), "--previous-bundle", str(previous),
        "--manifest", str(manifest), "--state-root", str(tmp_path),
        "--quiet",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2 and payload["verdict"] == mod.VERDICT_BINDING_MISMATCH

    # 2) recorded pin advance (binding re-bound to the NEW sha) -> pass, exit 0
    #    (round 2: the chain-adjacency check also needs the PRIOR identity's
    #    own generation binding to certify a fully clean pass)
    mod.record_expected_identity(tmp_path, generation=2, panel_sha=SHA_0518)
    ledger = tmp_path / "promotions.json"
    ledger.write_text(
        json.dumps([{"sha": SHA_0621, "generation": 1}]), encoding="utf-8",
    )
    rc = mod.main([
        "--latest-bundle", str(latest), "--previous-bundle", str(previous),
        "--manifest", str(manifest), "--state-root", str(tmp_path),
        "--promotions-ledger", str(ledger),
        "--quiet",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["verdict"] == mod.VERDICT_PIN_ADVANCE

    # 3) missing previous bundle -> coverage lost: DEGRADED (exit 1) by
    #    default, quiet fail-soft (exit 0) under --offline
    rc = mod.main([
        "--latest-bundle", str(latest),
        "--manifest", str(manifest), "--state-root", str(tmp_path),
        "--quiet",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1 and payload["verdict"] == mod.VERDICT_COVERAGE_LOST
    rc = mod.main([
        "--latest-bundle", str(latest),
        "--manifest", str(manifest), "--state-root", str(tmp_path),
        "--quiet", "--offline",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["verdict"] == mod.VERDICT_COVERAGE_LOST


def test_main_record_expected_mode(tmp_path, capsys):
    latest, _, manifest = _write_inputs(tmp_path)
    rc = mod.main([
        "--latest-bundle", str(latest), "--manifest", str(manifest),
        "--state-root", str(tmp_path), "--record-expected", "--quiet",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["panel_sha"] == SHA_0518
    record, problem = mod.read_expected_identity(tmp_path)
    assert problem is None and record["panel_sha"] == SHA_0518
    # re-run same day: idempotent
    assert mod.main([
        "--latest-bundle", str(latest), "--manifest", str(manifest),
        "--state-root", str(tmp_path), "--record-expected", "--quiet",
    ]) == 0
    capsys.readouterr()


def test_main_unreadable_latest_bundle_exits_3(tmp_path, capsys):
    rc = mod.main([
        "--latest-bundle", str(tmp_path / "nope.json"),
        "--state-root", str(tmp_path), "--quiet",
    ])
    capsys.readouterr()
    assert rc == 3
