"""scripts/fast_path_eligibility.py — the mechanical gate behind the small-change fast path."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import fast_path_eligibility as fp  # noqa: E402


def _f(path, add=3, dele=1, **kw):
    return {"filename": path, "additions": add, "deletions": dele, "status": "modified", **kw}


OK = [_f("doc/progress/2026-10-19-x.md"), _f("tests/test_x.py")]


def test_docs_and_tests_with_label_are_eligible():
    v = fp.evaluate(OK, ["agent:claude", "fast-path"], 0)
    assert v["eligible"] and v["reasons"] == []


def test_no_label_is_not_eligible():
    assert not fp.evaluate(OK, ["agent:claude"], 0)["eligible"]


@pytest.mark.parametrize("path", [
    "ops/renquant105/run_quote_logger.sh", "src/renquant_orchestrator/agent_workflows.py",
    "scripts/weekly_wf_promote.sh",
])
def test_anything_outside_docs_and_tests_is_refused(path):
    v = fp.evaluate([_f(path)], ["fast-path"], 0)
    assert not v["eligible"] and any("allow-list" in r for r in v["reasons"])


@pytest.mark.parametrize("path", [
    "subrepos.lock.json", "ops/launchd_manifest.json", "ops/renquant104/sentinel_acks.json",
    "doc/memory/long-term-agreements.md", ".github/workflows/ci.yml", ".github/CODEOWNERS",
    "deploy/com.renquant.x.plist", "backtesting/renquant_104/strategy_config.json",
    "backtesting/renquant_104/artifacts/prod/panel.json", "data/x.parquet",
    "doc/progress/2026-10-17-small-change-fast-path-proposal.md",
    "scripts/fast_path_eligibility.py", "tests/test_fast_path_eligibility.py",
    "doc/memory/fast-path-ledger.md",
])
def test_protected_paths_are_refused_even_when_they_look_like_docs_or_tests(path):
    v = fp.evaluate([_f(path)], ["fast-path"], 0)
    assert not v["eligible"] and any("protected" in r for r in v["reasons"]), path


def test_size_limits():
    assert not fp.evaluate([_f(f"doc/a{i}.md") for i in range(4)], ["fast-path"], 0)["eligible"]
    assert not fp.evaluate([_f("doc/a.md", add=41, dele=0)], ["fast-path"], 0)["eligible"]
    assert fp.evaluate([_f("doc/a.md", add=40, dele=0)], ["fast-path"], 0)["eligible"]


def test_daily_limit():
    assert fp.evaluate(OK, ["fast-path"], 2)["eligible"]
    assert not fp.evaluate(OK, ["fast-path"], 3)["eligible"]


def test_renaming_a_protected_file_into_docs_is_refused():
    v = fp.evaluate([_f("doc/notes.md", status="renamed", previous_filename="subrepos.lock.json")],
                    ["fast-path"], 0)
    assert not v["eligible"]


def test_unparseable_or_empty_input_fails_closed():
    assert not fp.evaluate([], ["fast-path"], 0)["eligible"]
    assert not fp.evaluate([{"filename": "doc/a.md"}], ["fast-path"], 0)["eligible"]
    assert not fp.evaluate([{"additions": 1, "deletions": 0}], ["fast-path"], 0)["eligible"]


def test_prod_path_rules_of_the_review_contract_are_a_subset_of_protected():
    sys.path.insert(0, str(REPO / "src"))
    from renquant_orchestrator.agent_workflows import PROD_PATH_RULES
    samples = ["data/x.parquet", "a/strategy_config.json", "a/live_state.json", "x/artifacts/prod/m.json",
               "backtesting/artifacts/walkforward_v2/a.jsonl"]
    for label, pat in PROD_PATH_RULES:
        hit = [s for s in samples if pat.search(s)]
        assert hit, f"sample set does not exercise {label}"
        for s in hit:
            assert any(p.search(s) for p in fp.PROTECTED), f"{label}: {s} not protected here"


def test_cli_exit_codes(tmp_path):
    def run(payload, labels, n=0, raw=None):
        p = tmp_path / "f.json"
        p.write_text(raw if raw is not None else json.dumps(payload))
        r = subprocess.run([sys.executable, str(REPO / "scripts/fast_path_eligibility.py"), "--files", str(p),
                            "--labels", labels, "--merged-24h", str(n)], capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout)
    assert run(OK, "fast-path")[0] == 0
    assert run(OK, "")[0] == 1
    rc, v = run(None, "fast-path", raw="not json")
    assert rc == 2 and not v["eligible"]


def test_workflow_reads_the_judge_from_the_base_branch_and_fails_closed():
    wf = (REPO / ".github/workflows/fast-path-eligibility.yml").read_text()
    assert "pull_request_target" in wf
    assert "ref: ${{ github.event.pull_request.base.sha }}" in wf, "judge must come from base, not the PR head"
    assert "fast-path/eligible" in wf
    assert "merged=${merged:-99}" in wf, "an unreadable merge count must fail closed (over the limit)"
