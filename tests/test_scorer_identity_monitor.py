"""Unit tests for the run-over-run scorer-identity diff alarm (#274 gap).

All tests use a synthetic temp runs DB + temp artifact/log dirs and a mocked
alert sink. None touch the real runs DB, ``artifacts/prod``, a broker, or any
live state.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from renquant_orchestrator import scorer_identity_monitor as sim


BASE = datetime(2026, 6, 25, 21, 0, 0, tzinfo=timezone.utc)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_CAL = "c" * 64
SHA_SHADOW_1 = "d" * 64
SHA_SHADOW_2 = "e" * 64


# --- helpers ----------------------------------------------------------------


def _bundle(
    *,
    panel_sha: str | None = SHA_A,
    trained: str | None = "2026-06-21",
    calibrator_sha: str | None = SHA_CAL,
    shadow_sha: str | None = SHA_SHADOW_1,
) -> str:
    hashes: dict[str, str] = {}
    if panel_sha is not None:
        hashes["panel"] = f"sha256:{panel_sha}"
        hashes["ranking.panel_scoring.artifact_path"] = f"sha256:{panel_sha}"
    if calibrator_sha is not None:
        hashes["global_calibration"] = f"sha256:{calibrator_sha}"
    if shadow_sha is not None:
        hashes["ranking.panel_scoring.shadow_models[0].artifact_path"] = f"sha256:{shadow_sha}"
    bundle = {
        "schema_version": 1,
        "artifact_hashes": hashes,
        "artifact_paths": {"panel": "/prod/panel-ltr.alpha158_fund.json"},
        "panel_contract": {"ok": True, "details": {"trained_date": trained}},
    }
    return json.dumps(bundle)


def _make_db(db_path: Path, rows: list[tuple[str, datetime, str | None]]) -> None:
    """rows: (run_id, created_at, run_bundle_json)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE pipeline_runs (
                   run_id TEXT, run_date TEXT, run_type TEXT, strategy TEXT,
                   created_at TEXT, run_bundle_json TEXT)"""
        )
        for run_id, created_at, bundle in rows:
            conn.execute(
                "INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
                (
                    run_id,
                    created_at.date().isoformat(),
                    "live",
                    "renquant-104",
                    created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    bundle,
                ),
            )


@pytest.fixture
def dirs(tmp_path):
    prod = tmp_path / "prod"
    logs = tmp_path / "weekly_wf_promote"
    receipts = tmp_path / "promote_shadow_patchtst"
    prod.mkdir()
    logs.mkdir()
    receipts.mkdir()
    return prod, logs, receipts


def _report(tmp_path, dirs, rows, **kwargs):
    prod, logs, receipts = dirs
    db = tmp_path / "runs.db"
    _make_db(db, rows)
    return sim.build_report(
        db_path=db,
        prod_artifacts_dir=prod,
        promote_log_dir=logs,
        shadow_receipt_dir=receipts,
        **kwargs,
    )


def _stable_rows(n: int, *, start: datetime = BASE, **bundle_kwargs):
    return [
        (f"run-{i:03d}", start + timedelta(hours=6 * i), _bundle(**bundle_kwargs))
        for i in range(n)
    ]


# --- 1. unexplained identity change fires ------------------------------------


def test_unexplained_prod_swap_is_critical(tmp_path, dirs):
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A, trained="2026-06-21")),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B, trained="2026-05-18")),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL
    assert report["exit_code"] == 1
    assert report["n_unexplained_boundaries"] == 1
    (boundary,) = report["boundaries"]
    assert boundary["explained"] is False
    change = next(c for c in boundary["changes"] if c["lane"] == sim.LANE_PROD)
    # the alert must carry BOTH identities
    assert change["prev"]["artifact_sha256"] == SHA_A
    assert change["curr"]["artifact_sha256"] == SHA_B
    assert change["prev"]["trained_date"] == "2026-06-21"
    assert change["curr"]["trained_date"] == "2026-05-18"
    critical_lines = [l for l in report["lines"] if l.startswith("CRITICAL")]
    assert any(SHA_A[:12] in l and SHA_B[:12] in l for l in critical_lines)


def test_trained_date_change_alone_is_a_change(tmp_path, dirs):
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A, trained="2026-06-21")),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_A, trained="2026-05-18")),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


def test_unexplained_shadow_swap_is_critical(tmp_path, dirs):
    rows = [
        ("run-old", BASE, _bundle(shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=1), _bundle(shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL
    change = report["boundaries"][0]["changes"][0]
    assert change["lane"] == "shadow_models[0]"


# --- 2. explained-by-promote passes -------------------------------------------


def test_prod_swap_explained_by_rollback_marker(tmp_path, dirs):
    prod, _, _ = dirs
    boundary_date = (BASE + timedelta(days=1)).date().isoformat()
    (prod / f"panel-ltr.alpha158_fund.weekly_rollback_{boundary_date}.json").write_text(
        "{}", encoding="utf-8"
    )
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A)),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_OK
    assert report["exit_code"] == 0
    (boundary,) = report["boundaries"]
    assert boundary["explained"] is True
    assert any(line.startswith("INFO") for line in report["lines"])


def test_prod_swap_explained_by_staging_artifact(tmp_path, dirs):
    prod, _, _ = dirs
    stamp = (BASE + timedelta(hours=30)).strftime("%Y%m%dT%H%M%SZ")
    (prod / f"panel-ltr.alpha158_fund.weekly_{stamp}.staging.json").write_text(
        "{}", encoding="utf-8"
    )
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A)),
        ("run-new", BASE + timedelta(days=2), _bundle(panel_sha=SHA_B)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_OK


def test_calibrator_family_events_do_not_explain_panel_swap(tmp_path, dirs):
    """Family matching: a calibration-family record must not legitimize a
    panel-lane change."""
    prod, _, _ = dirs
    boundary_date = (BASE + timedelta(days=1)).date().isoformat()
    (prod / f"panel-rank-calibration.weekly_rollback_{boundary_date}.json").write_text(
        "{}", encoding="utf-8"
    )
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A)),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


def test_event_outside_window_does_not_explain(tmp_path, dirs):
    prod, _, _ = dirs
    (prod / "panel-ltr.alpha158_fund.weekly_rollback_2026-06-10.json").write_text(
        "{}", encoding="utf-8"
    )
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A)),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


def test_shadow_swap_explained_by_receipt(tmp_path, dirs):
    _, _, receipts = dirs
    ts = BASE + timedelta(hours=30)
    (receipts / f"{ts.strftime('%Y-%m-%dT%H%M%SZ')}.json").write_text(
        json.dumps({"promoted_at": ts.isoformat()}), encoding="utf-8"
    )
    rows = [
        ("run-old", BASE, _bundle(shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=2), _bundle(shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_OK


def test_shadow_swap_not_explained_by_prod_chain_records(tmp_path, dirs):
    """A weekly prod-chain record alone must not mask a silent shadow-only swap."""
    prod, _, _ = dirs
    boundary_date = (BASE + timedelta(days=1)).date().isoformat()
    (prod / f"panel-ltr.alpha158_fund.weekly_rollback_{boundary_date}.json").write_text(
        "{}", encoding="utf-8"
    )
    rows = [
        ("run-old", BASE, _bundle(shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=1), _bundle(shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


def test_atomic_promotion_explains_same_boundary_shadow_swap(tmp_path, dirs):
    """An EXPLAINED prod change legitimizes the same-boundary shadow flip
    (a recorded promotion swaps the lanes atomically)."""
    prod, _, _ = dirs
    boundary_date = (BASE + timedelta(days=1)).date().isoformat()
    (prod / f"panel-ltr.alpha158_fund.weekly_rollback_{boundary_date}.json").write_text(
        "{}", encoding="utf-8"
    )
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A, shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B, shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_OK
    (boundary,) = report["boundaries"]
    shadow = next(c for c in boundary["changes"] if c["lane"] == "shadow_models[0]")
    assert shadow["explained"] is True
    assert shadow["note"] is not None


# --- 3. freshness WARN (#210: 28-day cap on the served model) -----------------


def test_served_trained_age_over_28d_warns(tmp_path, dirs):
    newest = BASE + timedelta(days=1)
    old_trained = (newest - timedelta(days=40)).date().isoformat()
    rows = _stable_rows(3, trained=old_trained)
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_WARN
    assert report["exit_code"] == 2
    assert report["freshness"]["warn"] is True
    assert report["freshness"]["age_days"] > 28
    assert "#210" in report["freshness"]["summary"]


def test_served_trained_age_within_cap_is_ok(tmp_path, dirs):
    trained = (BASE + timedelta(hours=12)).date() - timedelta(days=10)
    rows = _stable_rows(3, trained=trained.isoformat())
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_OK
    assert report["freshness"]["warn"] is False


def test_missing_trained_date_warns_not_passes(tmp_path, dirs):
    """No trained_date stamped => cannot bound the served model's age =>
    WARN (never a silent pass; #423: absence of evidence is not freshness)."""
    rows = _stable_rows(3, trained=None)
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_WARN
    assert report["freshness"]["warn"] is True


def test_warn_never_masks_critical(tmp_path, dirs):
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A, trained="2026-01-01")),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B, trained="2026-01-01")),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL
    assert report["exit_code"] == 1
    assert report["freshness"]["warn"] is True  # both surfaced


# --- 4. fail-closed -----------------------------------------------------------


def test_missing_db_fails_closed(tmp_path, dirs):
    prod, logs, receipts = dirs
    report = sim.build_report(
        db_path=tmp_path / "nope.db",
        prod_artifacts_dir=prod,
        promote_log_dir=logs,
        shadow_receipt_dir=receipts,
    )
    assert report["status"] == sim.STATUS_CRITICAL
    assert report["exit_code"] == 1
    assert report["fail_closed"]


def test_empty_db_fails_closed(tmp_path, dirs):
    report = _report(tmp_path, dirs, [])
    assert report["status"] == sim.STATUS_CRITICAL
    assert any("no canonical runs" in reason for reason in report["fail_closed"])


def test_single_run_fails_closed(tmp_path, dirs):
    report = _report(tmp_path, dirs, [("run-only", BASE, _bundle())])
    assert report["status"] == sim.STATUS_CRITICAL
    assert any("fewer than two" in reason for reason in report["fail_closed"])


def test_empty_bundle_fails_closed(tmp_path, dirs):
    rows = [
        ("run-old", BASE, _bundle()),
        ("run-new", BASE + timedelta(days=1), None),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL
    assert any("empty run_bundle_json" in reason for reason in report["fail_closed"])


def test_bundle_without_panel_hash_fails_closed(tmp_path, dirs):
    rows = [
        ("run-old", BASE, _bundle()),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=None)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL
    assert any("no stamped prod panel" in reason for reason in report["fail_closed"])


def test_unparseable_bundle_fails_closed(tmp_path, dirs):
    rows = [
        ("run-old", BASE, _bundle()),
        ("run-new", BASE + timedelta(days=1), "{not json"),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


# --- 5. saturation immunity (edge-triggered by construction) -------------------


def test_stable_identity_never_fires_regardless_of_history_length(tmp_path, dirs):
    prod, logs, receipts = dirs
    trained = (BASE.date() - timedelta(days=5)).isoformat()
    db = tmp_path / "runs.db"
    _make_db(db, _stable_rows(40, trained=trained))
    kwargs = dict(
        db_path=db,
        prod_artifacts_dir=prod,
        promote_log_dir=logs,
        shadow_receipt_dir=receipts,
    )
    report = sim.build_report(**kwargs)
    assert report["status"] == sim.STATUS_OK
    assert report["boundaries"] == []
    # repeated evaluation of the same state stays quiet -- the alarm is
    # edge-triggered and cannot saturate on a level
    again = sim.build_report(**kwargs)
    assert again["status"] == sim.STATUS_OK


def test_boundary_ages_out_of_lookback(tmp_path, dirs):
    """An old (already-lived-with) swap outside the lookback window does not
    page forever: only recent boundaries are evaluated."""
    trained = (BASE - timedelta(days=6)).date().isoformat()
    rows = [("run-000", BASE - timedelta(days=30), _bundle(panel_sha=SHA_B, trained=trained))]
    # dense post-swap history: the swap boundary is ~15d old, far outside the
    # 5d lookback, and the run preceding the window already carries SHA_A
    rows += [
        (
            f"run-{i + 1:03d}",
            BASE - timedelta(days=15) + timedelta(hours=6 * i),
            _bundle(panel_sha=SHA_A, trained=trained),
        )
        for i in range(41)
    ]
    report = _report(tmp_path, dirs, rows, lookback_days=5)
    assert report["status"] == sim.STATUS_OK
    assert report["boundaries"] == []


def test_boundary_at_window_edge_uses_preceding_run_as_base(tmp_path, dirs):
    """The run immediately BEFORE the lookback window is kept as diff base, so
    a swap at the window's first run is still caught."""
    trained = BASE.date().isoformat()
    rows = [("run-000", BASE - timedelta(days=6), _bundle(panel_sha=SHA_A, trained=trained))]
    rows += [
        (f"run-{i + 1:03d}", BASE + timedelta(hours=6 * i), _bundle(panel_sha=SHA_B, trained=trained))
        for i in range(4)
    ]
    report = _report(tmp_path, dirs, rows, lookback_days=5)
    assert report["status"] == sim.STATUS_CRITICAL
    assert report["boundaries"][0]["prev_run_id"] == "run-000"


# --- 6. booster content-hash resolution ----------------------------------------


def test_booster_hash_resolved_from_prod_copy(tmp_path, dirs):
    prod, _, _ = dirs
    booster_raw = json.dumps({"trees": [1, 2, 3]})
    artifact = json.dumps({"trained_date": "2026-06-21", "booster_raw_json": booster_raw})
    (prod / "panel-ltr.alpha158_fund.json").write_text(artifact, encoding="utf-8")
    file_sha = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
    booster_sha = hashlib.sha256(booster_raw.encode("utf-8")).hexdigest()

    rows = [
        ("run-old", BASE, _bundle(panel_sha=file_sha)),
        ("run-new", BASE + timedelta(hours=6), _bundle(panel_sha=file_sha)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_OK

    resolver = sim.BoosterResolver(prod)
    assert resolver.resolve(f"sha256:{file_sha}") == booster_sha
    assert resolver.resolve(SHA_B) is None  # unknown bytes resolve to None, never raise


def test_unresolvable_booster_is_not_a_phantom_change(tmp_path, dirs):
    """Booster hash is enrichment: same stamped sha with an unresolvable
    booster must not register as an identity change."""
    rows = _stable_rows(3)
    report = _report(tmp_path, dirs, rows)  # prod dir empty -> booster None
    assert report["boundaries"] == []


# --- 7. events use filename stamps, never mtime ---------------------------------


def test_rollback_event_date_comes_from_filename_not_mtime(tmp_path, dirs):
    """The prod dir has been observed bulk-touched; a fresh mtime on an OLD
    rollback marker must not legitimize today's swap."""
    prod, logs, receipts = dirs
    marker = prod / "panel-ltr.alpha158_fund.weekly_rollback_2026-06-10.json"
    marker.write_text("{}", encoding="utf-8")  # mtime = now, filename date = old
    events = sim.collect_promote_events(
        prod_artifacts_dir=prod, promote_log_dir=logs, shadow_receipt_dir=receipts
    )
    (event,) = events
    assert event.event_date.isoformat() == "2026-06-10"


# --- 8. alerting / notify gates --------------------------------------------------


def test_critical_alert_posts_ntfy_with_both_identities(tmp_path, dirs, monkeypatch):
    posted: list[tuple[str, str, str]] = []
    monkeypatch.setattr(sim, "post_ntfy", lambda t, b, topic: posted.append((t, b, topic)))
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A, trained="2026-06-21")),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B, trained="2026-06-25")),
    ]
    report = _report(tmp_path, dirs, rows)
    alerts = sim.emit_alerts(report, topic="test-topic", notify=True, quiet=False)
    assert len(posted) == 1
    title, body, topic = posted[0]
    assert "CRITICAL" in title
    assert SHA_A[:12] in body and SHA_B[:12] in body
    assert "2026-06-21" in body and "2026-06-25" in body
    assert topic == "test-topic"
    assert alerts


def test_quiet_and_no_notify_suppress_posting(tmp_path, dirs, monkeypatch):
    posted: list = []
    monkeypatch.setattr(sim, "post_ntfy", lambda *a: posted.append(a))
    rows = [
        ("run-old", BASE, _bundle(panel_sha=SHA_A)),
        ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B)),
    ]
    report = _report(tmp_path, dirs, rows)
    sim.emit_alerts(report, topic="t", notify=False, quiet=False)
    sim.emit_alerts(report, topic="t", notify=True, quiet=True)
    assert posted == []


# --- 9. main() exit codes ---------------------------------------------------------


def _main_args(tmp_path, dirs, extra=()):
    prod, logs, receipts = dirs
    return [
        "--repo-root", str(tmp_path),
        "--db", str(tmp_path / "runs.db"),
        "--prod-artifacts-dir", str(prod),
        "--promote-log-dir", str(logs),
        "--shadow-receipt-dir", str(receipts),
        "--quiet",
        *extra,
    ]


def test_main_exit_1_on_unexplained_change(tmp_path, dirs, capsys):
    _make_db(
        tmp_path / "runs.db",
        [
            ("run-old", BASE, _bundle(panel_sha=SHA_A)),
            ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B)),
        ],
    )
    assert sim.main(_main_args(tmp_path, dirs)) == 1
    out = capsys.readouterr().out
    assert "scorer_identity_check: critical" in out


def test_main_exit_0_on_stable_identity(tmp_path, dirs, capsys):
    trained = (BASE.date() - timedelta(days=3)).isoformat()
    _make_db(tmp_path / "runs.db", _stable_rows(3, trained=trained))
    assert sim.main(_main_args(tmp_path, dirs, ["--json"])) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["schema_version"] == sim.SCHEMA_VERSION
    assert payload["owner_repo"] == "renquant-orchestrator"


def test_main_exit_2_on_warn_only(tmp_path, dirs):
    trained = (BASE.date() - timedelta(days=60)).isoformat()
    _make_db(tmp_path / "runs.db", _stable_rows(3, trained=trained))
    assert sim.main(_main_args(tmp_path, dirs)) == 2


def test_main_exit_1_on_missing_db(tmp_path, dirs):
    assert sim.main(_main_args(tmp_path, dirs)) == 1


# --- 10. backfill timeline ----------------------------------------------------------


def test_backfill_timeline_shows_boundary_and_verdicts(tmp_path, dirs, capsys):
    prod, _, _ = dirs
    explained_date = (BASE + timedelta(days=1)).date().isoformat()
    (prod / f"panel-ltr.alpha158_fund.weekly_rollback_{explained_date}.json").write_text(
        "{}", encoding="utf-8"
    )
    rows = [
        ("run-000", BASE, _bundle(panel_sha=SHA_A, trained="2026-06-21")),
        ("run-001", BASE + timedelta(hours=6), _bundle(panel_sha=SHA_A, trained="2026-06-21")),
        # explained boundary (rollback marker on its date)
        ("run-002", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B, trained="2026-06-21")),
        ("run-003", BASE + timedelta(days=2), _bundle(panel_sha=SHA_B, trained="2026-06-21")),
        # unexplained boundary (the 06-26 class of event; its window
        # [run-003 date, run-004 date] excludes the rollback marker's date)
        ("run-004", BASE + timedelta(days=4), _bundle(panel_sha=SHA_A, trained="2026-05-18")),
    ]
    _make_db(tmp_path / "runs.db", rows)
    assert sim.main(_main_args(tmp_path, dirs, ["--backfill", "10"])) == 0
    out = capsys.readouterr().out
    assert out.count("SEGMENT") == 3
    assert "BOUNDARY run-001 -> run-002  explained" in out
    assert "BOUNDARY run-003 -> run-004  *** UNEXPLAINED ***" in out
    assert "2026-06-21" in out and "2026-05-18" in out


def test_backfill_is_report_only_exit_0(tmp_path, dirs):
    _make_db(
        tmp_path / "runs.db",
        [
            ("run-old", BASE, _bundle(panel_sha=SHA_A)),
            ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_B)),
        ],
    )
    assert sim.main(_main_args(tmp_path, dirs, ["--backfill", "10"])) == 0


# --- misc: sim runs are not canonical --------------------------------------------


def test_sim_runs_are_excluded(tmp_path, dirs):
    prod, logs, receipts = dirs
    db = tmp_path / "runs.db"
    _make_db(
        db,
        [
            ("run-old", BASE, _bundle(panel_sha=SHA_A)),
            ("run-new", BASE + timedelta(days=1), _bundle(panel_sha=SHA_A)),
        ],
    )
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
            (
                "sim-run",
                (BASE + timedelta(days=1)).date().isoformat(),
                "sim",
                "renquant-104",
                (BASE + timedelta(days=1, hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                _bundle(panel_sha=SHA_B),
            ),
        )
    report = sim.build_report(
        db_path=db,
        prod_artifacts_dir=prod,
        promote_log_dir=logs,
        shadow_receipt_dir=receipts,
    )
    assert report["status"] == sim.STATUS_OK
    assert report["boundaries"] == []
