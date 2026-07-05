from __future__ import annotations

import json
import os
from pathlib import Path

from renquant_orchestrator.cli import main


def _strategy_config(path: Path) -> None:
    path.write_text(
        json.dumps({
            "watchlist": ["AAPL", "MSFT"],
            "benchmark": "AAPL",
            "regime_params": {
                "BULL_CALM": {"disable_new_buys": False},
                "BULL_VOLATILE": {"disable_new_buys": False},
                "BULL_STRONG": {"disable_new_buys": False},
                "BEAR": {"disable_new_buys": False},
                "CHOPPY": {"disable_new_buys": False},
            },
            "sector_map": {"AAPL": "Technology", "MSFT": "Technology"},
            "ranking": {
                "panel_scoring": {
                    "enabled": True,
                    "kind": "xgb",
                    "artifact_path": "artifacts/prod/panel-ltr.alpha158_fund.json",
                    "global_calibration": {
                        "enabled": True,
                        "artifact_path": "artifacts/prod/panel-rank-calibration.json",
                    },
                }
            },
        }),
        encoding="utf-8",
    )


def test_daily_contract_cli_writes_run_bundle(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "strategy_config.json"
    out = tmp_path / "out"
    _strategy_config(cfg)

    rc = main([
        "daily-contract",
        "--strategy-config",
        str(cfg),
        "--output-dir",
        str(out),
        "--run-id",
        "cli-fixture",
        "--as-of",
        "2026-05-26",
        "--code-commit",
        "sha-fixture",
    ])

    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["broker_type"] == "paper"
    assert summary["broker_name"] == "paper-smoke"
    assert summary["training_calls"] == ["load", "train", "validate"]
    assert Path(summary["run_bundle_path"]).exists()
    bundle = json.loads(Path(summary["run_bundle_path"]).read_text())
    assert bundle["run_id"] == "cli-fixture"
    assert bundle["order_intents"][0]["attribution"]["source_job"] == "PanelScoringJob"
    assert (
        bundle["order_intents"][0]["attribution"]["source_task"]
        == "EmitAttributedOrderIntentsTask"
    )
    assert bundle["submitted_orders"][0]["status"] == "dry_run"


def test_daily_contract_cli_execute_uses_paper_fill(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "strategy_config.json"
    out = tmp_path / "out"
    _strategy_config(cfg)

    rc = main([
        "daily-contract",
        "--strategy-config",
        str(cfg),
        "--output-dir",
        str(out),
        "--run-id",
        "cli-execute-fixture",
        "--as-of",
        "2026-05-26",
        "--broker-type",
        "paper",
        "--broker-name",
        "paper-test",
        "--execute",
    ])

    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["dry_run"] is False
    assert summary["broker_name"] == "paper-test"
    assert summary["submitted_orders"][0]["status"] == "filled"
    assert summary["submitted_orders"][0]["price"] == 100.0


def test_live_bridge_cli_forwards_runner_args(monkeypatch, tmp_path: Path) -> None:
    import renquant_orchestrator.live_bridge as bridge

    seen = {}

    def fake_run_bridge(argv, *, mode, repo_root):
        seen["argv"] = argv
        seen["mode"] = mode
        seen["repo_root"] = repo_root
        return 17

    monkeypatch.setattr(bridge, "run_bridge", fake_run_bridge)

    rc = main([
        "live-bridge",
        "--repo-dir",
        str(tmp_path),
        "--strategy",
        "renquant_104",
        "--broker",
        "alpaca",
        "--once",
    ])

    assert rc == 17
    assert seen == {
        "argv": ["--strategy", "renquant_104", "--broker", "alpaca", "--once"],
        "mode": "live",
        "repo_root": tmp_path.resolve(),
    }


def test_live_bridge_cli_loads_env_file_before_delegating(monkeypatch, tmp_path: Path) -> None:
    import renquant_orchestrator.live_bridge as bridge

    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_API_KEY=file-key\nexport ALPACA_SECRET_KEY='file-secret'\n",
        encoding="utf-8",
    )
    seen = {}

    def fake_run_bridge(argv, *, mode, repo_root):
        seen["argv"] = argv
        seen["mode"] = mode
        seen["repo_root"] = repo_root
        seen["key"] = os.environ.get("ALPACA_API_KEY")
        seen["secret"] = os.environ.get("ALPACA_SECRET_KEY")
        return 19

    monkeypatch.setattr(bridge, "run_bridge", fake_run_bridge)

    rc = main([
        "live-bridge",
        "--repo-dir",
        str(tmp_path),
        "--env-file",
        str(env_file),
        "--broker",
        "readonly-alpaca",
        "--once",
    ])

    assert rc == 19
    assert seen == {
        "argv": ["--broker", "readonly-alpaca", "--once"],
        "mode": "live",
        "repo_root": tmp_path.resolve(),
        "key": "file-key",
        "secret": "file-secret",
    }


def test_run_job_forwards_live_bridge_args(monkeypatch, tmp_path: Path) -> None:
    import renquant_orchestrator.live_bridge as bridge

    seen = {}

    def fake_run_bridge(argv, *, mode, repo_root):
        seen["argv"] = argv
        seen["mode"] = mode
        seen["repo_root"] = repo_root
        return 23

    monkeypatch.setattr(bridge, "run_bridge", fake_run_bridge)

    rc = main([
        "run-job",
        "live_runner_bridge",
        "--",
        "--repo-dir",
        str(tmp_path),
        "--once",
    ])

    assert rc == 23
    assert seen == {
        "argv": ["--once"],
        "mode": "live",
        "repo_root": tmp_path.resolve(),
    }


def test_run_job_live_bridge_loads_env_file(monkeypatch, tmp_path: Path) -> None:
    import renquant_orchestrator.live_bridge as bridge

    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=file-key\n", encoding="utf-8")
    seen = {}

    def fake_run_bridge(argv, *, mode, repo_root):
        seen["argv"] = argv
        seen["key"] = os.environ.get("ALPACA_API_KEY")
        return 29

    monkeypatch.setattr(bridge, "run_bridge", fake_run_bridge)

    rc = main([
        "run-job",
        "live_runner_bridge",
        "--",
        "--env-file",
        str(env_file),
        "--once",
    ])

    assert rc == 29
    assert seen == {
        "argv": ["--once"],
        "key": "file-key",
    }


def test_engineering_census_cli_strict_expectation(tmp_path: Path, capsys) -> None:
    pipeline_src = tmp_path / "renquant-pipeline" / "src"
    gate_file = pipeline_src / "pkg" / "gates.py"
    gate_file.parent.mkdir(parents=True)
    gate_file.write_text("def gate(ctx):\n    ctx.buy_blocked = True\n", encoding="utf-8")
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text("{}", encoding="utf-8")

    rc = main([
        "engineering-census",
        "--github-root",
        str(tmp_path),
        "--pipeline-src",
        str(pipeline_src),
        "--strategy-config",
        str(cfg),
        "--expect-buy-blocked-writers",
        "1",
        "--strict",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["gate_writers"]["count"] == 1
    assert payload["ok"] is True


def test_engineering_census_cli_strict_returns_two_on_expectation_failure(
    tmp_path: Path,
    capsys,
) -> None:
    pipeline_src = tmp_path / "renquant-pipeline" / "src"
    pipeline_src.mkdir(parents=True)
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text("{}", encoding="utf-8")

    rc = main([
        "engineering-census",
        "--github-root",
        str(tmp_path),
        "--pipeline-src",
        str(pipeline_src),
        "--strategy-config",
        str(cfg),
        "--expect-buy-blocked-writers",
        "1",
        "--strict",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["expectation_failures"][0]["actual"] == 0


def test_agent_identity_cli_strict_returns_nonzero_on_shared_actor(monkeypatch, capsys) -> None:
    import renquant_orchestrator.agent_workflows as workflows

    monkeypatch.setattr(
        workflows,
        "github_login",
        lambda _token: "shared-operator",
    )

    rc = main([
        "agent-identity",
        "--claude-token",
        "claude-token",
        "--codex-token",
        "codex-token",
        "--strict",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ok"] is False
    assert "same GitHub login" in " ".join(out["warnings"])


def test_agent_identity_cli_non_strict_is_report_only(monkeypatch, capsys) -> None:
    import renquant_orchestrator.agent_workflows as workflows

    monkeypatch.setattr(workflows, "github_login", lambda _token: "shared-operator")

    rc = main([
        "agent-identity",
        "--claude-token",
        "claude-token",
        "--codex-token",
        "codex-token",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is False


def test_agent_workflow_merge_execute_returns_nonzero_on_identity_block(
    monkeypatch,
    capsys,
) -> None:
    import renquant_orchestrator.agent_workflows as workflows

    monkeypatch.setattr(
        workflows,
        "fetch_open_prs",
        lambda _repo, _token: [{
            "number": 1,
            "title": "ready",
            "headRefName": "claude/ready",
            "headRefOid": "sha1",
            "state": "OPEN",
            "isDraft": False,
            "url": "https://github.com/o/r/pull/1",
            "labels": [{"name": "agent:claude"}],
            "reviews": [{"state": "APPROVED", "commit_id": "sha1", "body": "reviewed by codex"}],
            "statusCheckRollup": [{"conclusion": "SUCCESS", "status": "COMPLETED"}],
            "comments": [],
            "files": [{"path": "doc/progress/2026-06-17-ready.md"}],
            "progressDocContent": (
                "# Progress\nSTATUS: delivered\nWHAT: ready\nWHY/DIR: ready\nEVIDENCE: n/a\nNEXT: none\n"
            ),
        }],
    )
    monkeypatch.setattr(
        workflows,
        "agent_identity_health",
        lambda require_actor_tokens=False: {
            "ok": False,
            "agents": {},
            "require_actor_tokens": require_actor_tokens,
            "warnings": ["claude token is missing"],
        },
    )

    rc = main([
        "agent-workflow",
        "--as",
        "claude",
        "--workflow",
        "merge",
        "--repo",
        "o/r",
        "--execute",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["merge_blocked"] is True
    assert out["executed"] == []


def test_merge_audit_cli_strict_returns_nonzero_on_missing_pre_merge_marker(
    monkeypatch,
    capsys,
) -> None:
    import renquant_orchestrator.agent_workflows as workflows

    monkeypatch.setattr(
        workflows,
        "fetch_merged_prs",
        lambda _repo, _token, limit=50: [{
            "number": 9,
            "title": "manual merge",
            "url": "https://github.com/o/r/pull/9",
            "headRefName": "codex/manual",
            "labels": [{"name": "agent:codex"}],
            "body": "",
            "mergedAt": "2026-06-09T00:10:00Z",
            "mergedBy": {"login": "owner"},
            "comments": [{
                "body": "merged by `codex` post-merge audit marker",
                "createdAt": "2026-06-09T00:10:01Z",
                "author": {"login": "owner"},
            }],
        }],
    )

    rc = main([
        "merge-audit",
        "--repo",
        "o/r",
        "--limit",
        "10",
        "--strict",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ok"] is False
    assert out["n_missing_pre_merge_audit"] == 1
    assert out["prs"][0]["status"] == "missing_pre_merge_audit"


def test_signal_pipeline_cli_json(capsys) -> None:
    rc = main(["signal-pipeline", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total_sources"] == 5
    assert out["enabled"] == 2
    assert "pit_estimate_revisions" in out["disabled_names"]


def test_ledger_query_returns_verdicts_for_date(tmp_path, capsys) -> None:
    from renquant_orchestrator.decision_ledger import connect, write_verdicts

    db = tmp_path / "ledger.db"
    conn = connect(db)
    write_verdicts(conn, "run-001", "2026-07-04", [
        {"scope": "daily", "gate": "P-MODEL-STALENESS", "verdict": "allow", "reason": "fresh"},
        {"scope": "daily", "gate": "P-WF-GATE", "verdict": "block", "reason": "placebo leak"},
    ])
    conn.close()

    rc = main(["ledger-query", "--db", str(db), "--date", "2026-07-04"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 2
    assert rows[0]["gate"] == "P-MODEL-STALENESS"
    assert rows[1]["verdict"] == "block"


def test_ledger_query_filters_by_verdict(tmp_path, capsys) -> None:
    from renquant_orchestrator.decision_ledger import connect, write_verdicts

    db = tmp_path / "ledger.db"
    conn = connect(db)
    write_verdicts(conn, "run-001", "2026-07-04", [
        {"scope": "daily", "gate": "G1", "verdict": "allow", "reason": "ok"},
        {"scope": "daily", "gate": "G2", "verdict": "block", "reason": "bad"},
    ])
    conn.close()

    rc = main(["ledger-query", "--db", str(db), "--date", "2026-07-04", "--verdict", "block"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["gate"] == "G2"


def test_ledger_query_filters_by_gate_substring(tmp_path, capsys) -> None:
    from renquant_orchestrator.decision_ledger import connect, write_verdicts

    db = tmp_path / "ledger.db"
    conn = connect(db)
    write_verdicts(conn, "run-001", "2026-07-04", [
        {"scope": "daily", "gate": "P-MODEL-STALENESS", "verdict": "allow", "reason": "ok"},
        {"scope": "daily", "gate": "P-WF-GATE", "verdict": "block", "reason": "bad"},
    ])
    conn.close()

    rc = main(["ledger-query", "--db", str(db), "--date", "2026-07-04", "--gate", "WF"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["gate"] == "P-WF-GATE"


def test_ledger_query_summary_mode(tmp_path, capsys) -> None:
    from renquant_orchestrator.decision_ledger import connect, write_verdicts

    db = tmp_path / "ledger.db"
    conn = connect(db)
    write_verdicts(conn, "run-001", "2026-07-04", [
        {"scope": "daily", "gate": "G1", "verdict": "allow", "reason": "ok"},
    ])
    write_verdicts(conn, "run-002", "2026-07-03", [
        {"scope": "daily", "gate": "G1", "verdict": "block", "reason": "bad"},
    ])
    conn.close()

    rc = main(["ledger-query", "--db", str(db), "--date", "2026-07-04", "--days", "2", "--summary"])
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["G1"]["allow"] == 1
    assert summary["G1"]["block"] == 1


def test_ledger_query_empty_db_returns_empty(tmp_path, capsys) -> None:
    db = tmp_path / "ledger.db"
    rc = main(["ledger-query", "--db", str(db), "--date", "2026-01-01"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows == []


def test_decision_pnl_cli_emits_attribution(tmp_path, capsys) -> None:
    import sqlite3

    import pandas as pd

    db = tmp_path / "runs.db"
    conn = sqlite3.connect(db)
    pd.DataFrame({
        "run_id": ["2026-06-11-live-abc"] * 3,
        "ticker": ["AAA", "BBB", "CCC"],
        "selected": [1, 0, 0],
        "blocked_by": [None, "kelly:capped_zero", None],
        "rank_score": [0.9, 0.4, 0.5],
    }).to_sql("candidate_scores", conn, index=False)
    pd.DataFrame({
        "as_of_date": ["2026-06-11"] * 3,
        "ticker": ["AAA", "BBB", "CCC"],
        "fwd_ret_5d": [0.030, -0.020, 0.005],
    }).to_sql("ticker_forward_returns", conn, index=False)
    conn.close()

    rc = main(["decision-pnl", "--db", str(db)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["return_column"] == "fwd_ret_5d"
    assert out["n_decisions"] == 3
    assert out["edge"]["n_selected"] == 1
    assert out["edge"]["n_vetoed"] == 1
    assert out["edge"]["edge"] > 0  # selected beat vetoed
    assert len(out["by_class"]) >= 2


def test_parking_sleeve_cli_computes_allocation(tmp_path, capsys) -> None:
    book_json = tmp_path / "book_state.json"
    book_json.write_text(
        json.dumps({
            "portfolio_value": 10000,
            "positions_value": 4300,
            "cash_value": 5700,
            "beta_positions": 0.43,
            "regime": "BULL_CALM",
        }),
        encoding="utf-8",
    )

    rc = main(["parking-sleeve", "--book-state-json", str(book_json)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["regime"] == "BULL_CALM"
    assert out["portfolio_value"] == 10000


# ---------------------------------------------------------------------------
# CLI delegation coverage (Codex review on #383): each of these subcommands
# is a thin nargs=REMAINDER pass-through to a target module's main(argv).
# Codex: "I also want at least focused CLI delegation coverage for the
# nontrivial pass-through cases kept here, especially replay-audit and
# edgar-harvest, because the consolidation currently reduced test coverage
# while broadening the public CLI surface." parking-sleeve already has its
# own functional test above; these cover the remaining 7 wired subcommands
# so a dispatch-to-missing-symbol regression (the exact parking-sleeve bug)
# would fail CI instead of silently landing.
# ---------------------------------------------------------------------------

def test_transfer_coefficient_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.transfer_coefficient as tc_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 7

    monkeypatch.setattr(tc_mod, "main", fake_main)
    rc = main(["transfer-coefficient", "--json"])
    assert rc == 7
    assert seen["argv"] == ["--json"]


def test_readiness_monitor_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.readiness_monitor as rm_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 3

    monkeypatch.setattr(rm_mod, "main", fake_main)
    rc = main(["readiness-monitor", "--json"])
    assert rc == 3
    assert seen["argv"] == ["--json"]


def test_conviction_replay_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.m4b_conviction_replay as m4b_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 4

    monkeypatch.setattr(m4b_mod, "main", fake_main)
    rc = main(["conviction-replay", "--dry-run"])
    assert rc == 4
    assert seen["argv"] == ["--dry-run"]


def test_m6_restamp_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.m6_restamp as m6_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 6

    monkeypatch.setattr(m6_mod, "main", fake_main)
    rc = main(["m6-restamp", "--artifacts-dir", "/tmp/test", "--dry-run"])
    assert rc == 6
    assert seen["argv"] == ["--artifacts-dir", "/tmp/test", "--dry-run"]


def test_edgar_harvest_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.sec_edgar_harvester as edgar_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 11

    monkeypatch.setattr(edgar_mod, "main", fake_main)
    rc = main(["edgar-harvest", "--dry-run"])
    assert rc == 11
    assert seen["argv"] == ["--dry-run"]


def test_entry_timing_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.entry_timing_policy as et_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 5

    monkeypatch.setattr(et_mod, "main", fake_main)
    rc = main(["entry-timing", "--json"])
    assert rc == 5
    assert seen["argv"] == ["--json"]


def test_train_gbdt_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.train_gbdt as tg_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 9

    monkeypatch.setattr(tg_mod, "main", fake_main)
    rc = main(["train-gbdt", "--staged"])
    assert rc == 9
    assert seen["argv"] == ["--staged"]


def test_patchtst_cutoff_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.patchtst_weekly_cutoff as pwc_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 13

    monkeypatch.setattr(pwc_mod, "main", fake_main)
    rc = main(["patchtst-cutoff", "--json"])
    assert rc == 13
    assert seen["argv"] == ["--json"]


def test_replay_audit_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.intraday_replay_audit as ra_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 6

    monkeypatch.setattr(ra_mod, "main", fake_main)
    rc = main(["replay-audit", "--session-date", "2026-07-01"])
    assert rc == 6
    assert seen["argv"] == ["--session-date", "2026-07-01"]


def test_risk_budget_report_cli_delegates(monkeypatch) -> None:
    import renquant_orchestrator.risk_budget.report as rb_mod

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 2

    monkeypatch.setattr(rb_mod, "main", fake_main)
    rc = main(["risk-budget-report", "--json"])
    assert rc == 2
    assert seen["argv"] == ["--json"]


def test_run_job_dispatches_outcome_observer(monkeypatch) -> None:
    import renquant_orchestrator.job_runner as runner

    seen = {}

    def fake_run_module_main(module_name, argv):
        seen["module_name"] = module_name
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(runner, "_run_module_main", fake_run_module_main)

    rc = main([
        "run-job",
        "outcome_observer",
        "--",
        "--db", "/tmp/test.db",
    ])

    assert rc == 0
    assert seen == {
        "module_name": "renquant_orchestrator.outcome_observer",
        "argv": ["--db", "/tmp/test.db"],
    }
