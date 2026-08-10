"""Controls for the serving-fidelity probe v1 (orch#958).

Fixture: a tiny runs.db + golden config + artifacts tree, exercised
through the REAL probe code path. Controls: clean PASS; identity-swap
alarm; frozen-score alarm; coverage alarm; distribution-band alarm.
"""
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np

PROBE = Path(__file__).resolve().parents[1] / "scripts" / "serving_fidelity_probe.py"
spec = importlib.util.spec_from_file_location("sfp", PROBE)
sfp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sfp)

DATE = "2026-08-07"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _fixture(tmp, *, frozen_scores=False, wrong_pin=False, few_scored=False,
             blown_std=False, mixed_identity=False):
    rng = np.random.default_rng(11)
    db = tmp / "runs.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_type TEXT, "
                "run_date TEXT, created_at TEXT, model_content_sha256 TEXT, "
                "training_cutoff TEXT)")
    con.execute("CREATE TABLE ticker_daily_state (run_id TEXT, date TEXT, "
                "ticker TEXT, panel_score REAL, regime TEXT, active_scorer TEXT)")
    # trailing 20 days + the probed day
    dates = [f"2026-07-{d:02d}" for d in range(10, 30)] + [DATE]
    for i, d in enumerate(dates):
        rid = f"r{i}"
        ident = "sha256:aaaa" if not (mixed_identity and d == DATE) else "sha256:bbbb"
        con.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
                    (rid, "live", d, f"{d}T14:00:00", "sha256:aaaa", "2026-08-02"))
        if mixed_identity and d == DATE:
            con.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
                        (rid + "b", "live", d, f"{d}T15:00:00", ident, "2026-08-02"))
        n = 6 if (few_scored and d == DATE) else 60
        scale = 25.0 if (blown_std and d == DATE) else 1.0
        for j in range(n):
            s = 0.5 if (frozen_scores and d == DATE) else float(rng.normal() * scale)
            con.execute("INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
                        (rid, d, f"T{j:02d}", s, "BULL_CALM", "blend"))
    con.commit()
    con.close()

    root = tmp / "artifacts"
    (root / "artifacts" / "prod").mkdir(parents=True)
    panel = root / "artifacts" / "prod" / "panel.json"
    panel.write_text(json.dumps({"kind": "panel"}))
    mom_dir = root / "artifacts" / "momentum"
    (mom_dir / "2026-08-02").mkdir(parents=True)
    mart = mom_dir / "2026-08-02" / "momentum_residual_v0.json"
    mart.write_text(json.dumps({"content_sha256": "cafe" * 16}))
    ledger = mom_dir / "ledger.jsonl"
    ledger.write_text(json.dumps({"cutoff_date": "2026-08-02",
                                  "artifact_content_sha256": "cafe" * 16}) + "\n")
    golden = tmp / "golden.json"
    pin = ("0" * 16) if wrong_pin else _sha(panel)[:16]
    golden.write_text(json.dumps({"ranking": {"panel_scoring": {"components": [
        {"artifact_path": "artifacts/prod/panel.json",
         "expected_content_sha256": f"sha256:{pin}"},
        {"kind": "momentum_residual",
         "artifact_path": "artifacts/momentum/ledger.jsonl"},
    ]}}}))
    return db, golden, root


def test_clean_pass(tmp_path):
    db, golden, root = _fixture(tmp_path)
    findings, stats = sfp.probe(db, golden, root, DATE)
    assert findings == []
    assert stats["n_scored"] == 60


def test_wrong_pin_alarms(tmp_path):
    db, golden, root = _fixture(tmp_path, wrong_pin=True)
    findings, _ = sfp.probe(db, golden, root, DATE)
    assert any("does not match golden pin" in f for f in findings)


def test_frozen_scores_alarm(tmp_path):
    db, golden, root = _fixture(tmp_path, frozen_scores=True)
    findings, _ = sfp.probe(db, golden, root, DATE)
    assert any("frozen-score" in f for f in findings)


def test_coverage_alarm(tmp_path):
    db, golden, root = _fixture(tmp_path, few_scored=True)
    findings, _ = sfp.probe(db, golden, root, DATE)
    assert any("coverage alarm" in f for f in findings)


def test_distribution_band_alarm(tmp_path):
    db, golden, root = _fixture(tmp_path, blown_std=True)
    findings, _ = sfp.probe(db, golden, root, DATE)
    assert any("distribution alarm" in f for f in findings)


def test_mixed_identity_alarm(tmp_path):
    db, golden, root = _fixture(tmp_path, mixed_identity=True)
    findings, _ = sfp.probe(db, golden, root, DATE)
    assert any("mixed artifact identities" in f for f in findings)


def test_scorer_switch_day_skips_distribution(tmp_path):
    # the day after a scorer switch has zero same-scorer trailing days:
    # the distribution layer must SKIP (note recorded), not alarm
    db, golden, root = _fixture(tmp_path, blown_std=True)
    con = sqlite3.connect(db)
    con.execute("UPDATE ticker_daily_state SET active_scorer='panel_ltr' WHERE date != ?", (DATE,))
    con.commit(); con.close()
    findings, stats = sfp.probe(db, golden, root, DATE)
    assert not any("distribution alarm" in f for f in findings)
    assert stats.get("trail_days_same_scorer") == 0
