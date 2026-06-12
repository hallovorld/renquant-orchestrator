from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.engineering_census import build_engineering_census


def test_engineering_census_counts_configs_and_ast_writers(tmp_path: Path) -> None:
    pipeline_src = tmp_path / "renquant-pipeline" / "src"
    mod = pipeline_src / "pkg" / "gates.py"
    mod.parent.mkdir(parents=True)
    mod.write_text(
        "\n".join(
            [
                "class Ctx: pass",
                "def gate(ctx):",
                "    ctx.buy_blocked = True",
                "    setattr(ctx, 'buy_blocked', True)",
                "    text = 'ctx.buy_blocked = True'",
                "    # ctx.buy_blocked = True",
            ]
        ),
        encoding="utf-8",
    )
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text(
        json.dumps(
            {
                "ranking": {
                    "_reason": "doc",
                    "panel_scoring": {
                        "enabled": True,
                        "why_note": "kept for census",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    payload = build_engineering_census(
        github_root=tmp_path,
        pipeline_src=pipeline_src,
        strategy_configs=[cfg],
        expect_buy_blocked_writers=2,
    )

    assert payload["ok"] is True
    assert payload["strategy_configs"][0]["recursive_keys"] == 5
    assert payload["strategy_configs"][0]["underscore_keys"] == 1
    assert payload["strategy_configs"][0]["contains_reason_keys"] == 1
    assert payload["strategy_configs"][0]["contains_note_keys"] == 1
    assert payload["gate_writers"]["count"] == 2
    assert [w["kind"] for w in payload["gate_writers"]["writers"]] == [
        "attribute_assign_true",
        "setattr_true",
    ]


def test_engineering_census_expectation_failure_is_not_ok(tmp_path: Path) -> None:
    pipeline_src = tmp_path / "renquant-pipeline" / "src"
    pipeline_src.mkdir(parents=True)
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text("{}", encoding="utf-8")

    payload = build_engineering_census(
        github_root=tmp_path,
        pipeline_src=pipeline_src,
        strategy_configs=[cfg],
        expect_buy_blocked_writers=1,
    )

    assert payload["ok"] is False
    assert payload["expectation_failures"] == [
        {
            "metric": "buy_blocked_true_writers_ast",
            "expected": 1,
            "actual": 0,
        }
    ]
