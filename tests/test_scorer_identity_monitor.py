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
SHADOW_PATH = "/artifacts/shadow/panel-clf.top-decile.fwd60.json"
SHA_SHADOW_2 = "e" * 64


# --- helpers ----------------------------------------------------------------


def _bundle(
    *,
    panel_sha: str | None = SHA_A,
    trained: str | None = "2026-06-21",
    calibrator_sha: str | None = SHA_CAL,
    shadow_sha: str | None = SHA_SHADOW_1,
    shadow_path: str | None = SHADOW_PATH,
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
        "artifact_paths": {
            "panel": "/prod/panel-ltr.alpha158_fund.json",
            **({"ranking.panel_scoring.shadow_models[0].artifact_path": shadow_path}
               if shadow_path else {}),
        },
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
    assert change["lane"] == f"shadow:{SHADOW_PATH}"


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
        json.dumps(
            {
                "promoted_at": ts.isoformat(),
                "identity_before": {"expected_content_sha256": f"sha256:{SHA_SHADOW_1}"},
                "identity_after": {"expected_content_sha256": f"sha256:{SHA_SHADOW_2}"},
            }
        ),
        encoding="utf-8",
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
    shadow = next(c for c in boundary["changes"] if c["lane"] == f"shadow:{SHADOW_PATH}")
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


# --- shadow lanes are identities, not list positions -------------------------

CLF = "/artifacts/shadow/panel-clf.top-decile.fwd60.json"
PATCHTST = "/artifacts/shadow/hf_patchtst_all_seed44_model.pt"
MOM = "/artifacts/momentum/momentum_artifact_ledger.jsonl"
MOM_FAST = "/artifacts/momentum_fast/momentum_artifact_ledger.jsonl"

SHA_CLF = "1" * 64
SHA_PATCHTST = "0" * 64
SHA_MOM = "9" * 64


def _multi_shadow_bundle(entries, *, panel_sha=SHA_A, trained="2026-06-21"):
    """entries: list of (path, sha|None) stamped at consecutive shadow indices."""
    hashes = {
        "panel": f"sha256:{panel_sha}",
        "ranking.panel_scoring.artifact_path": f"sha256:{panel_sha}",
        "global_calibration": f"sha256:{SHA_CAL}",
    }
    paths = {"panel": "/prod/panel-ltr.alpha158_fund.json"}
    for i, (path, sha) in enumerate(entries):
        key = f"ranking.panel_scoring.shadow_models[{i}].artifact_path"
        hashes[key] = f"sha256:{sha}" if sha else None
        paths[key] = path
    return json.dumps({
        "schema_version": 1,
        "artifact_hashes": hashes,
        "artifact_paths": paths,
        "panel_contract": {"ok": True, "details": {"trained_date": trained}},
    })


def test_a_retired_lane_does_not_make_the_UNCHANGED_lanes_look_swapped(tmp_path, dirs):
    """The real 2026-07-31 → 2026-08-03 boundary, which reported THREE 'silent
    scorer swaps'.

    PatchTST was retired (decided 2026-08-02) and the momentum lane activated, so
    the list went `[patchtst, clf]` → `[clf, momentum]`. Keyed by INDEX that reads
    as lane0 `patchtst→clf` and lane1 `clf→momentum` — and the clf leg, whose
    artifact never changed, is counted TWICE: once as lane 0's new value and once
    as lane 1's old value. Keyed by identity, clf is silent.
    """
    rows = [
        ("run-0731", BASE, _multi_shadow_bundle([(PATCHTST, SHA_PATCHTST), (CLF, SHA_CLF)])),
        ("run-0803", BASE + timedelta(days=3),
         _multi_shadow_bundle([(CLF, SHA_CLF), (MOM, SHA_MOM)])),
    ]

    report = _report(tmp_path, dirs, rows)

    (boundary,) = report["boundaries"]
    changed = {c["lane"] for c in boundary["changes"]}
    # the lane that did not change its artifact must not appear at all
    assert f"shadow:{CLF}" not in changed
    # and the two that genuinely entered/left must
    assert f"shadow:{PATCHTST}" in changed
    assert f"shadow:{MOM}" in changed


def test_two_lanes_with_the_SAME_basename_stay_distinct(tmp_path, dirs):
    """2026-08-04 stamps `momentum/momentum_artifact_ledger.jsonl` AND
    `momentum_fast/momentum_artifact_ledger.jsonl` in two slots. Keying on the
    basename would collide and one lane would silently overwrite the other —
    losing a lane is the failure this monitor exists to prevent."""
    bundle = _multi_shadow_bundle([(CLF, SHA_CLF), (MOM, SHA_MOM), (MOM_FAST, None)])

    identity = sim.extract_identity(
        run_id="r", run_date="2026-08-04", created_at=BASE, bundle_raw=bundle)

    assert identity.usable is True
    assert f"shadow:{MOM}" in identity.lanes
    assert f"shadow:{MOM_FAST}" in identity.lanes
    assert identity.lanes[f"shadow:{MOM}"].artifact_sha is not None
    assert identity.lanes[f"shadow:{MOM_FAST}"].artifact_sha is None


def test_a_lane_REPLACED_IN_PLACE_is_still_a_swap(tmp_path, dirs):
    """Anti-vacuity: identity-keying must not make the monitor blind to the case
    it exists for — the same path serving a DIFFERENT artifact."""
    rows = [
        ("run-old", BASE, _multi_shadow_bundle([(CLF, SHA_CLF)])),
        ("run-new", BASE + timedelta(days=1), _multi_shadow_bundle([(CLF, SHA_SHADOW_2)])),
    ]

    report = _report(tmp_path, dirs, rows)

    assert report["status"] == sim.STATUS_CRITICAL
    (boundary,) = report["boundaries"]
    assert any(c["lane"] == f"shadow:{CLF}" for c in boundary["changes"])


# --- lane lifecycle is not a scorer swap (measured 2026-07-31 -> 2026-08-03) ---


def _shadow_run(run_id: str, day: str, lanes: dict[str, str]) -> sim.RunIdentity:
    """A run stamping only the given shadow lanes. A lane omitted from `lanes` is
    ABSENT from the lineup, which is how a retirement/addition actually appears."""
    return sim.RunIdentity(
        run_id=run_id,
        run_date=day,
        created_at=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        lanes={
            name: sim.LaneIdentity(lane=name, artifact_sha=sha)
            for name, sha in lanes.items()
        },
        usable=True,
    )


_PATCHTST = "shadow:artifacts/patchtst/hf_patchtst_all_seed44_model.pt"
_CLF = "shadow:artifacts/shadow/panel-clf.top-decile.fwd60.json"
_MOMENTUM = "shadow:artifacts/momentum/momentum_artifact_ledger.jsonl"


def test_retired_lane_is_not_called_a_silent_scorer_swap():
    """PatchTST left the lineup on 2026-08-02. The alert called that a swap while
    printing "(lane not stamped)" on the same line."""
    prev = _shadow_run("r1", "2026-07-31", {_PATCHTST: "sha256:07046963", _CLF: "sha256:1e644354"})
    curr = _shadow_run("r2", "2026-08-03", {_CLF: "sha256:1e644354"})

    report = sim.evaluate([prev, curr], [])

    retired = [ln for ln in report["lines"] if _PATCHTST in ln]
    assert len(retired) == 1
    assert "shadow lane retired" in retired[0]
    assert "silent scorer swap" not in retired[0]
    # The diagnosis changed; the severity did NOT.
    assert retired[0].startswith("CRITICAL:")


def test_added_lane_is_not_called_a_silent_scorer_swap():
    prev = _shadow_run("r1", "2026-07-31", {_CLF: "sha256:1e644354"})
    curr = _shadow_run("r2", "2026-08-03", {_CLF: "sha256:1e644354", _MOMENTUM: "sha256:9aa2d8c9"})

    report = sim.evaluate([prev, curr], [])

    added = [ln for ln in report["lines"] if _MOMENTUM in ln]
    assert len(added) == 1
    assert "shadow lane added" in added[0]
    assert "silent scorer swap" not in added[0]
    assert added[0].startswith("CRITICAL:")


def test_a_genuine_same_lane_substitution_is_still_called_a_silent_scorer_swap():
    """The guard against over-reach: reclassifying lifecycle events must not
    weaken the case the detector exists for."""
    prev = _shadow_run("r1", "2026-07-31", {_CLF: "sha256:1e644354"})
    curr = _shadow_run("r2", "2026-08-03", {_CLF: "sha256:deadbeef"})

    report = sim.evaluate([prev, curr], [])

    swapped = [ln for ln in report["lines"] if _CLF in ln]
    assert len(swapped) == 1
    assert "silent scorer swap" in swapped[0]
    assert "shadow lane" not in swapped[0]
    assert swapped[0].startswith("CRITICAL:")


def test_lifecycle_is_none_for_a_same_lane_substitution():
    change = sim.LaneChange(
        lane=_CLF,
        prev=sim.LaneIdentity(lane=_CLF, artifact_sha="sha256:1e644354"),
        curr=sim.LaneIdentity(lane=_CLF, artifact_sha="sha256:deadbeef"),
    )
    assert change.lifecycle is None
    assert change.as_dict()["lifecycle"] is None


# --- a receipt is evidence only for the identity transition it records ---


def _receipt(receipts, ts, before: str | None, after: str | None) -> None:
    payload: dict = {"promoted_at": ts.isoformat()}
    if before is not None:
        payload["identity_before"] = {"expected_content_sha256": before}
    if after is not None:
        payload["identity_after"] = {"expected_content_sha256": after}
    (receipts / f"{ts.strftime('%Y-%m-%dT%H%M%SZ')}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_receipt_for_another_artifact_does_not_explain_this_lane(tmp_path, dirs):
    """THE FAIL-OPEN THIS FIX EXISTS FOR. The receipt directory is
    logs/promote_shadow_patchtst, so before this fix a patchtst promotion
    explained a momentum lane change in the same window."""
    _, _, receipts = dirs
    other = "f" * 64
    _receipt(receipts, BASE + timedelta(hours=30), f"sha256:{other}", f"sha256:{other}")
    rows = [
        ("run-old", BASE, _bundle(shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=2), _bundle(shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


def test_receipt_with_no_identity_block_explains_nothing(tmp_path, dirs):
    """"Something was promoted that day" cannot say WHOSE lane it was."""
    _, _, receipts = dirs
    _receipt(receipts, BASE + timedelta(hours=30), None, None)
    rows = [
        ("run-old", BASE, _bundle(shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=2), _bundle(shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


def test_truncated_receipt_digest_still_matches_a_full_lane_digest(tmp_path, dirs):
    """MEASURED: run bundles stamp 64 hex, receipts stamp a 16-hex truncation of
    the SAME artifact. An equality test would match nothing and turn every
    boundary CRITICAL — failing the other way, since an all-red alarm stops being
    read."""
    _, _, receipts = dirs
    _receipt(
        receipts,
        BASE + timedelta(hours=30),
        f"sha256:{SHA_SHADOW_1[:16]}",
        f"sha256:{SHA_SHADOW_2[:16]}",
    )
    rows = [
        ("run-old", BASE, _bundle(shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=2), _bundle(shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_OK


def test_a_digest_prefix_shorter_than_the_floor_is_refused(tmp_path, dirs):
    """Below _MIN_DIGEST_PREFIX a prefix is a plausible collision, not an
    identity. Refusing costs a CRITICAL a human reads; accepting would hand out
    matches to unrelated artifacts."""
    _, _, receipts = dirs
    _receipt(
        receipts,
        BASE + timedelta(hours=30),
        f"sha256:{SHA_SHADOW_1[:6]}",
        f"sha256:{SHA_SHADOW_2[:6]}",
    )
    rows = [
        ("run-old", BASE, _bundle(shadow_sha=SHA_SHADOW_1)),
        ("run-new", BASE + timedelta(days=2), _bundle(shadow_sha=SHA_SHADOW_2)),
    ]
    report = _report(tmp_path, dirs, rows)
    assert report["status"] == sim.STATUS_CRITICAL


def test_genesis_receipt_explains_a_lane_addition():
    """Measured on the four real receipts: the genesis one carries
    identity_before=None with a real identity_after. "The lane was absent" and
    "the receipt names nothing" are the same claim and must match, or a
    legitimate lane addition reports unexplained forever."""
    assert sim._side_matches(sim._ABSENT, None) is True
    assert sim._side_matches(None, None) is True
    # The converse never matches: the receipt names an artifact the lane lacked.
    assert sim._side_matches(sim._ABSENT, "sha256:" + "a" * 64) is False
    assert sim._side_matches("sha256:" + "a" * 64, None) is False


# --- ledger-backed shadow lane self-legitimizes a scheduled refit append ------


def _write_linked_ledger(path: Path, rows: list[dict]) -> None:
    """Write an append-only ledger with valid prev_row_sha/row_sha linkage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    linked = []
    prev_sha = None
    for i, row in enumerate(rows):
        r = dict(row)
        r["prev_row_sha"] = prev_sha
        r["row_sha"] = f"row{i}"
        linked.append(r)
        prev_sha = r["row_sha"]
    path.write_text("\n".join(json.dumps(r) for r in linked), encoding="utf-8")


def _mom_run(run_id: str, day: str, sha: str, ledger_path: Path) -> sim.RunIdentity:
    """A run stamping ONE ledger-backed momentum shadow lane (artifact_path set
    to the absolute on-disk ledger, as the real run bundle stamps it)."""
    name = f"shadow:{ledger_path}"
    return sim.RunIdentity(
        run_id=run_id,
        run_date=day,
        created_at=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        lanes={
            name: sim.LaneIdentity(
                lane=name, artifact_sha=sha, artifact_path=str(ledger_path)
            )
        },
        usable=True,
    )


def test_ledger_backed_shadow_refit_is_not_a_silent_swap(tmp_path):
    """A scheduled weekly momentum refit appends a link-intact row within the
    boundary window → the file-sha change is legitimized, NOT a silent swap."""
    ledger = tmp_path / "artifacts" / "momentum" / "momentum_artifact_ledger.jsonl"
    _write_linked_ledger(ledger, [
        {"appended_at_utc": "2026-08-07T12:00:00Z", "artifact_content_sha256": "sha256:aaa"},
        {"appended_at_utc": "2026-08-08T12:00:06Z", "artifact_content_sha256": "sha256:bbb"},  # in-window
    ])
    prev = _mom_run("r1", "2026-08-07", "sha256:9aa2d8c9", ledger)
    curr = _mom_run("r2", "2026-08-10", "sha256:65d09112", ledger)

    report = sim.evaluate([prev, curr], [])

    assert not any("silent scorer swap" in ln for ln in report["lines"])
    assert report["status"] != sim.STATUS_CRITICAL


def test_broken_ledger_linkage_still_fires(tmp_path):
    """GUARD: a file swap that breaks the append-only linkage is NOT legitimized."""
    ledger = tmp_path / "artifacts" / "momentum" / "momentum_artifact_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"appended_at_utc": "2026-08-07T12:00:00Z", "row_sha": "r0", "prev_row_sha": None},
        {"appended_at_utc": "2026-08-08T12:00:06Z", "row_sha": "r1", "prev_row_sha": "TAMPERED"},
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    prev = _mom_run("r1", "2026-08-07", "sha256:9aa2d8c9", ledger)
    curr = _mom_run("r2", "2026-08-10", "sha256:65d09112", ledger)

    report = sim.evaluate([prev, curr], [])
    assert report["status"] == sim.STATUS_CRITICAL
    assert any("silent scorer swap" in ln for ln in report["lines"])


def test_ledger_append_outside_window_still_fires(tmp_path):
    """GUARD: a link-intact ledger with NO append inside the boundary window is
    not legitimized (the change is not tied to a contemporaneous refit)."""
    ledger = tmp_path / "artifacts" / "momentum" / "momentum_artifact_ledger.jsonl"
    _write_linked_ledger(ledger, [
        {"appended_at_utc": "2026-07-01T12:00:00Z", "artifact_content_sha256": "sha256:aaa"},
        {"appended_at_utc": "2026-07-02T12:00:00Z", "artifact_content_sha256": "sha256:bbb"},  # before window
    ])
    prev = _mom_run("r1", "2026-08-07", "sha256:9aa2d8c9", ledger)
    curr = _mom_run("r2", "2026-08-10", "sha256:65d09112", ledger)

    report = sim.evaluate([prev, curr], [])
    assert report["status"] == sim.STATUS_CRITICAL


def test_non_ledger_shadow_lane_unaffected_by_ledger_path(tmp_path):
    """A non-ledger shadow lane (e.g. clf .json) is NOT eligible for ledger
    legitimization — it still needs a receipt, unchanged."""
    change = sim.LaneChange(
        lane=_CLF,
        prev=sim.LaneIdentity(lane=_CLF, artifact_sha="sha256:1e644354",
                              artifact_path="/abs/artifacts/shadow/panel-clf.top-decile.fwd60.json"),
        curr=sim.LaneIdentity(lane=_CLF, artifact_sha="sha256:deadbeef",
                              artifact_path="/abs/artifacts/shadow/panel-clf.top-decile.fwd60.json"),
    )
    boundary = sim.Boundary(
        prev_run=_mom_run("r1", "2026-08-07", "x", tmp_path / "unused_ledger.jsonl"),
        curr_run=_mom_run("r2", "2026-08-10", "y", tmp_path / "unused_ledger.jsonl"),
        changes=[change],
    )
    ok, note = sim._ledger_append_explains(change, boundary)
    assert ok is False and note is None


def test_ledger_backed_ADDED_lane_stays_critical(tmp_path):
    """REGRESSION (codex #983 review): a lane JOINING the lineup is a membership
    change, NOT an in-place scheduled refit of an existing lane. Even a valid,
    in-window, link-intact ledger must not self-legitimize the addition — the
    monitor exists to shout exactly this lineup change, so it stays CRITICAL."""
    ledger = tmp_path / "artifacts" / "momentum" / "momentum_artifact_ledger.jsonl"
    _write_linked_ledger(ledger, [
        {"appended_at_utc": "2026-08-07T12:00:00Z", "artifact_content_sha256": "sha256:aaa"},
        {"appended_at_utc": "2026-08-08T12:00:06Z", "artifact_content_sha256": "sha256:bbb"},  # in-window
    ])
    name = f"shadow:{ledger}"
    prev = _shadow_run("r1", "2026-08-07", {_CLF: "sha256:1e644354"})  # no momentum lane yet
    curr = sim.RunIdentity(
        run_id="r2",
        run_date="2026-08-10",
        created_at=datetime.fromisoformat("2026-08-10T12:00:00+00:00"),
        lanes={
            _CLF: sim.LaneIdentity(lane=_CLF, artifact_sha="sha256:1e644354"),
            name: sim.LaneIdentity(
                lane=name, artifact_sha="sha256:65d09112", artifact_path=str(ledger)
            ),
        },
        usable=True,
    )

    report = sim.evaluate([prev, curr], [])

    added = [ln for ln in report["lines"] if str(ledger) in ln]
    assert len(added) == 1
    assert "shadow lane added" in added[0]
    assert "explained by" not in added[0]
    assert added[0].startswith("CRITICAL:")
    assert report["status"] == sim.STATUS_CRITICAL


def test_ledger_append_refuses_lineup_membership_changes(tmp_path):
    """GUARD: `_ledger_append_explains` only legitimizes an in-place same-lane
    swap (``lifecycle is None``). An added/retired lane is refused even with a
    valid in-window ledger, so the lifecycle gate — not a missing/invalid file —
    is what keeps the change CRITICAL."""
    ledger = tmp_path / "artifacts" / "momentum" / "momentum_artifact_ledger.jsonl"
    _write_linked_ledger(ledger, [
        {"appended_at_utc": "2026-08-07T12:00:00Z", "artifact_content_sha256": "sha256:aaa"},
        {"appended_at_utc": "2026-08-08T12:00:06Z", "artifact_content_sha256": "sha256:bbb"},  # in-window
    ])
    name = f"shadow:{ledger}"
    boundary = sim.Boundary(
        prev_run=_mom_run("r1", "2026-08-07", "sha256:9aa2d8c9", ledger),
        curr_run=_mom_run("r2", "2026-08-10", "sha256:65d09112", ledger),
        changes=[],
    )

    added = sim.LaneChange(
        lane=name,
        prev=sim.LaneIdentity(lane=name, artifact_sha=sim._ABSENT),
        curr=sim.LaneIdentity(
            lane=name, artifact_sha="sha256:65d09112", artifact_path=str(ledger)
        ),
    )
    assert added.lifecycle == "added"
    assert sim._ledger_append_explains(added, boundary) == (False, None)

    retired = sim.LaneChange(
        lane=name,
        prev=sim.LaneIdentity(
            lane=name, artifact_sha="sha256:9aa2d8c9", artifact_path=str(ledger)
        ),
        curr=sim.LaneIdentity(lane=name, artifact_sha=sim._ABSENT, artifact_path=str(ledger)),
    )
    assert retired.lifecycle == "retired"
    assert sim._ledger_append_explains(retired, boundary) == (False, None)
