"""A4-T1 governance — the orchestrator-owned identify -> consume -> stamp.

These are INTEGRATION tests across the real backtesting module on the path:
the wrapper's every refusal, the on-disk consequence of each (marker present
or absent, artifact bytes changed or not), replay across directories,
processes and racing threads, and the two production callers (the CLI
subcommand and the bash wrapper).
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import renquant_backtesting.wf_gate.freshness_fallback as FF

if not hasattr(FF, "A4T1_PROOF_SCHEMA"):
    # FAIL, never skip: a vacuous green here would hide a broken pairing.
    pytest.fail("renquant-backtesting on PYTHONPATH predates A4-T1 v13 "
                "(renquant-backtesting#128); the pairing is mandatory",
                pytrace=False)

from renquant_orchestrator import a4t1_governance as G  # noqa: E402
from renquant_orchestrator.cli import main as cli_main  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO / "ops" / "renquant104" / "a4t1_promote_staged.sh"
RUN_ID = "20260831T141820Z"
EXCEPTION_ID = f"a4t1_{RUN_ID}"

# ── artifact shapes replicated from the backtesting tests (not imported
#    across repos) ─────────────────────────────────────────────────────────

A4T1_AS_OF = dt.date(2026, 9, 1)
A4T1_EXPIRED = dt.date(2026, 9, 8)
A4T1_TRAINED = "2026-08-25"
A4T1_PROD = "2026-07-20"

ZERO_TRADE_OVERRIDES = dict(
    wf_reason=("FAIL: zero trades across all WF cuts; decision tree admitted "
               "no buys, so Sharpe is undefined and SPY benchmark cannot be met"),
    trade_contract={"passed": False, "reason": "no round-trip ledgers found"},
    trade_monotonicity={"passed": False, "reason": "no round-trip ledgers found"},
    alpha_economics={"passed": False, "reason": "no round-trip ledgers found"},
)
CANDIDATE_OVERRIDES = dict(
    **ZERO_TRADE_OVERRIDES,
    sanity_regime_ic={"passed": False,
                      "reason": "regime sanity IC failed: BULL_CALM,BULL_VOLATILE,CHOPPY"},
)


def _wf(genuine=0.02, verdict=False, **over):
    wf = {
        "passed": verdict,
        "diagnostic_only": False,
        "skipped_required_gates": [],
        "candidate_artifact_used": False,
        "recipe_validated": True,
        "wf_eval_scope": "walkforward_manifest",
        "wf_reason": "PASS: absolute Sharpe floor met and SPY benchmark met",
        "sanity_reason": "FAIL: shuf_ic=+0.0010 (need |·| < 0.005), genuine_ic=...",
        "sanity_shuffled_ic": 0.001,
        "sanity_placebo_ic": 0.043,
        "sanity_placebo_aligned_real_ic": 0.046,
        "sanity_placebo_absolute_rule_pass": False,
        "sanity_placebo_absolute_rule_threshold": 0.023,
        "sanity_placebo_genuine_ic": genuine,
        "sanity_regime_ic": {"passed": True, "reason": "ok"},
        "trade_contract": {"passed": True, "reason": "trade ledger contract OK"},
        "trade_monotonicity": {"passed": True, "reason": "ok"},
        "alpha_economics": {"passed": True, "reason": "ok"},
        "config_parity": {"passed": True},
        "qp_contract": None,
    }
    wf.update(over)
    return wf


def _prod(d: Path, trained=A4T1_PROD) -> Path:
    p = d / "prod.json"
    p.write_text(json.dumps({"trained_date": trained, "metadata": {}}),
                 encoding="utf-8")
    return p


def _candidate_staging(d: Path, genuine=0.0016, run_id=RUN_ID, plain=False):
    """Write a candidate-shaped staging artifact into ``d``; return
    (path, digest). ``plain=True`` = a placebo-only reject with no substance
    failures (promotes on the STANDING path, never as the candidate)."""
    d.mkdir(parents=True, exist_ok=True)
    over = {} if plain else dict(CANDIDATE_OVERRIDES)
    wf = _wf(genuine=genuine, **over)
    obj = {"trained_date": A4T1_TRAINED, "metadata": {"wf_gate_metadata": wf}}
    path = d / f"panel-ltr.alpha158_fund.weekly_{run_id}.staging.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path, FF._artifact_digest(obj)


COMMITTED_RECORD = REPO / "ops" / "governance" / "a4t1" / f"{RUN_ID}.authorization.json"


def _auth_dir(tmp: Path, digest: str, **overrides) -> Path:
    """A private authorization dir holding the COMMITTED record with the
    digest (and any overrides) replaced — the only way a synthetic artifact
    can be 'the' candidate."""
    rec = json.loads(COMMITTED_RECORD.read_text(encoding="utf-8"))
    rec["artifact_digest"] = digest
    rec.update(overrides)
    d = tmp / "auth"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN_ID}.authorization.json").write_text(json.dumps(rec, indent=2),
                                                    encoding="utf-8")
    return d


class Env:
    def __init__(self, tmp: Path, root: Path, auth: Path, digest: str):
        self.tmp, self.root, self.auth, self.digest = tmp, root, auth, digest

    def marker(self) -> Path:
        return self.root / "logs" / "weekly_wf_promote" / "a4t1_ledger" / f"{EXCEPTION_ID}.consumed.json"


@pytest.fixture
def env(tmp_path, monkeypatch) -> Env:
    """Ledger under a private data root; the committed record re-pointed at
    the synthetic digest; backtesting's pin re-pointed the same way."""
    root = tmp_path / "root"
    monkeypatch.setenv("RENQUANT_DATA_ROOT", str(root))
    _, digest = _candidate_staging(tmp_path / "probe")
    auth = _auth_dir(tmp_path, digest)
    monkeypatch.setattr(G, "AUTHORIZATION_DIR", auth)
    monkeypatch.setattr(FF, "_A4T1_CANDIDATE_ARTIFACT_DIGEST", digest)
    return Env(tmp_path, root, auth, digest)


def _promote_in(env: Env, name: str, as_of=A4T1_AS_OF, **staging_kw):
    d = env.tmp / name
    staging, _ = _candidate_staging(d, **staging_kw)
    prod = _prod(d)
    before = staging.read_bytes()
    result = G.promote_candidate(prod, staging, as_of)
    return result, staging, before


# ── the committed record itself ───────────────────────────────────────────

def test_committed_record_cross_checks_against_the_backtesting_pin():
    """No monkeypatching: the reviewed record and backtesting's constants
    must name the same exception, digest and authority, or the promotion
    refuses in production."""
    rec = G.load_authorization(RUN_ID)
    assert rec["exception_id"] == EXCEPTION_ID
    assert rec["artifact_digest"] == FF._A4T1_CANDIDATE_ARTIFACT_DIGEST
    assert rec["authority"] == FF._A4T1_CANDIDATE_AUTHORITY
    assert rec["run_id"] == FF._A4T1_CANDIDATE_RUN_ID
    lo, hi = (dt.date.fromisoformat(x) for x in rec["temporal_bounds"])
    assert lo == FF._A4T1_START and hi == FF._A4T1_EXPIRY


def test_record_missing_refuses(env, monkeypatch):
    monkeypatch.setattr(G, "AUTHORIZATION_DIR", env.tmp / "nowhere")
    result, staging, before = _promote_in(env, "a")
    assert result["status"] == "REFUSED"
    assert result["refused_on"] == "authorization_record_missing"
    assert not env.marker().exists() and staging.read_bytes() == before


@pytest.mark.parametrize("field,value", [
    ("authority", "someone-else:record.json"),
    ("run_id", "20260901T120000Z"),
    ("artifact_digest", "0" * 64),
])
def test_record_disagreeing_with_the_pin_refuses(env, field, value):
    _auth_dir(env.tmp, env.digest, **{field: value})
    result, staging, before = _promote_in(env, "a")
    assert result["status"] == "REFUSED"
    assert result["refused_on"] == "authorization_record_mismatch", result
    assert not env.marker().exists() and staging.read_bytes() == before


def test_record_wrong_schema_refuses(env):
    _auth_dir(env.tmp, env.digest, schema="a4t1_authorization.v0")
    result, *_ = _promote_in(env, "a")
    assert result["refused_on"] == "authorization_record_schema"
    assert not env.marker().exists()


# ── the wrapper's own checks, each leaving no marker and no stamp ─────────

def test_valid_promotion_consumes_then_stamps(env):
    result, staging, before = _promote_in(env, "a")
    assert result["status"] == "PROMOTED", result
    proof = result["proof"]
    FF.validate_a4t1_proof(proof, result["verdict"])  # passes
    marker = env.marker()
    assert marker.exists() and Path(result["marker_path"]) == marker
    rec = json.loads(marker.read_text())
    assert rec["stamped"] is True and "stamped_at" in rec
    assert rec["proof"] == proof and rec["as_of"] == A4T1_AS_OF.isoformat()
    assert proof["ledger_path"] == str(marker)
    meta = json.loads(staging.read_text())["metadata"]
    assert staging.read_bytes() != before
    assert meta["promotion_basis"] == FF.PROMOTION_BASIS
    assert meta["fallback_a4t1_consumption_proof"] == proof
    assert meta["fallback_a4t1_candidate_run_id"] == RUN_ID
    assert G.is_consumed(RUN_ID)


def test_fabricated_digest_refuses(env):
    d = env.tmp / "a"
    staging, _ = _candidate_staging(d)
    obj = json.loads(staging.read_text())
    obj["metadata"]["wf_gate_metadata"]["sanity_placebo_genuine_ic"] = 0.05
    staging.write_text(json.dumps(obj), encoding="utf-8")
    before = staging.read_bytes()
    result = G.promote_candidate(_prod(d), staging, A4T1_AS_OF)
    assert result["refused_on"] == "artifact_digest_mismatch", result
    assert not env.marker().exists() and staging.read_bytes() == before


def test_wrong_run_id_in_filename_refuses(env):
    result, staging, before = _promote_in(env, "a", run_id="20260901T120000Z")
    assert result["refused_on"] == "run_id_mismatch"
    assert not env.marker().exists() and staging.read_bytes() == before


def test_outside_temporal_bounds_refuses(env):
    result, staging, before = _promote_in(env, "a", as_of=A4T1_EXPIRED)
    assert result["refused_on"] == "temporal_bounds"
    assert not env.marker().exists() and staging.read_bytes() == before


def test_backtesting_verdict_refuse_is_honoured(env):
    """Fresh prod → backtesting REFUSES (prod not stale) → no consumption."""
    d = env.tmp / "a"
    staging, _ = _candidate_staging(d)
    before = staging.read_bytes()
    result = G.promote_candidate(_prod(d, trained="2026-08-20"), staging, A4T1_AS_OF)
    assert result["refused_on"] == "verdict_refused", result
    assert result["verdict"]["decision"] == "REFUSE"
    assert not env.marker().exists() and staging.read_bytes() == before


def test_standing_path_promotion_is_not_this_operations_business(env, monkeypatch):
    """An artifact that promotes on its own merit (genuine_ic above the
    standing floor, infra-only failures) carries no candidate keys — the
    narrow op refuses rather than burning the exception on it."""
    d = env.tmp / "a"
    staging, digest = _candidate_staging(d, genuine=0.025, plain=True)
    _auth_dir(env.tmp, digest)
    monkeypatch.setattr(FF, "_A4T1_CANDIDATE_ARTIFACT_DIGEST", digest)
    before = staging.read_bytes()
    result = G.promote_candidate(_prod(d), staging, A4T1_AS_OF)
    assert result["refused_on"] == "verdict_not_candidate_exception", result
    assert result["verdict"]["decision"] == "FALLBACK_PROMOTE"
    assert "a4t1_candidate_run_id" not in result["verdict"]
    assert not env.marker().exists() and staging.read_bytes() == before


# ── single consumption ────────────────────────────────────────────────────

def test_replay_across_directories_refuses(env):
    first, *_ = _promote_in(env, "dir1")
    assert first["status"] == "PROMOTED"
    second, staging2, before2 = _promote_in(env, "dir2")
    assert second["status"] == "REFUSED"
    assert second["refused_on"] == "already_consumed"
    assert second["prior_receipt_id"] == first["proof"]["receipt_id"]
    assert second["prior_stamped"] is True
    assert staging2.read_bytes() == before2


def test_corrupt_marker_counts_as_consumed(env):
    marker = env.marker()
    marker.parent.mkdir(parents=True)
    marker.write_text("CORRUPT", encoding="utf-8")
    result, staging, before = _promote_in(env, "a")
    assert result["refused_on"] == "already_consumed"
    assert result["prior_receipt_id"] is None
    assert staging.read_bytes() == before
    assert marker.read_text() == "CORRUPT"


def test_stamp_failure_leaves_the_exception_consumed(env, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(FF, "stamp", boom)
    result, staging, before = _promote_in(env, "a")
    assert result["status"] == "REFUSED" and result["refused_on"] == "stamp_failed"
    assert "disk full" in result["why"]
    assert staging.read_bytes() == before
    rec = json.loads(env.marker().read_text())
    assert rec["stamped"] is False and rec["proof"] == result["proof"]
    monkeypatch.undo()
    monkeypatch.setenv("RENQUANT_DATA_ROOT", str(env.root))
    monkeypatch.setattr(G, "AUTHORIZATION_DIR", env.auth)
    monkeypatch.setattr(FF, "_A4T1_CANDIDATE_ARTIFACT_DIGEST", env.digest)
    again, *_ = _promote_in(env, "b")
    assert again["refused_on"] == "already_consumed"
    assert again["prior_stamped"] is False


def test_concurrent_threads_consume_exactly_once(env):
    n = 8
    dirs = []
    for i in range(n):
        d = env.tmp / f"t{i}"
        _candidate_staging(d)
        _prod(d)
        dirs.append(d)
    barrier = threading.Barrier(n)

    def go(d: Path):
        barrier.wait()
        staging = next(d.glob("*.staging.json"))
        return G.promote_candidate(d / "prod.json", staging, A4T1_AS_OF)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        results = list(ex.map(go, dirs))
    statuses = [r["status"] for r in results]
    assert statuses.count("PROMOTED") == 1, statuses
    assert [r["refused_on"] for r in results if r["status"] == "REFUSED"] == ["already_consumed"] * (n - 1)
    stamped = [d for d, r in zip(dirs, results) if r["status"] == "PROMOTED"]
    assert len(stamped) == 1
    for d, r in zip(dirs, results):
        meta = json.loads(next(d.glob("*.staging.json")).read_text())["metadata"]
        assert ("promotion_basis" in meta) == (r["status"] == "PROMOTED")


# ── the production callers ───────────────────────────────────────────────

def test_cli_subcommand_promotes_and_exits_by_status(env, capsys):
    d = env.tmp / "a"
    staging, _ = _candidate_staging(d)
    prod = _prod(d)
    rc = cli_main(["a4t1-promote", "--prod", str(prod), "--staging", str(staging),
                   "--as-of", A4T1_AS_OF.isoformat()])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["status"] == "PROMOTED"
    d2 = env.tmp / "b"
    staging2, _ = _candidate_staging(d2)
    rc2 = cli_main(["a4t1-promote", "--prod", str(_prod(d2)), "--staging", str(staging2),
                    "--as-of", A4T1_AS_OF.isoformat()])
    out2 = json.loads(capsys.readouterr().out)
    assert rc2 == 1 and out2["refused_on"] == "already_consumed"


def _runner(tmp: Path, digest: str, auth: Path) -> Path:
    """A subprocess cannot see monkeypatches: this runner re-applies the two
    test-only re-pointings, then hands off to the REAL CLI main."""
    r = tmp / "runner.py"
    r.write_text(f"""#!{sys.executable}
import sys
from pathlib import Path
import renquant_backtesting.wf_gate.freshness_fallback as FF
import renquant_orchestrator.a4t1_governance as G
FF._A4T1_CANDIDATE_ARTIFACT_DIGEST = {digest!r}
G.AUTHORIZATION_DIR = Path({str(auth)!r})
argv = sys.argv[1:]
if argv[:2] == ["-m", "renquant_orchestrator"]:   # invoked as $PYTHON by the bash wrapper
    argv = argv[2:]
from renquant_orchestrator.cli import main
sys.exit(main(argv))
""", encoding="utf-8")
    r.chmod(r.stat().st_mode | stat.S_IXUSR)
    return r


def _sub_env(env: Env) -> dict:
    e = dict(os.environ)
    e["RENQUANT_DATA_ROOT"] = str(env.root)
    return e


def test_cross_process_replay_refuses(env):
    runner = _runner(env.tmp, env.digest, env.auth)
    d1, d2 = env.tmp / "p1", env.tmp / "p2"
    s1, _ = _candidate_staging(d1)
    s2, _ = _candidate_staging(d2)
    args = lambda d, s: [sys.executable, str(runner), "a4t1-promote",  # noqa: E731
                         "--prod", str(_prod(d)), "--staging", str(s),
                         "--as-of", A4T1_AS_OF.isoformat()]
    r1 = subprocess.run(args(d1, s1), capture_output=True, text=True, env=_sub_env(env))
    assert r1.returncode == 0, r1.stderr
    assert json.loads(r1.stdout)["status"] == "PROMOTED"
    r2 = subprocess.run(args(d2, s2), capture_output=True, text=True, env=_sub_env(env))
    assert r2.returncode == 1, r2.stderr
    assert json.loads(r2.stdout)["refused_on"] == "already_consumed"
    assert "promotion_basis" not in json.loads(s2.read_text())["metadata"]


def test_concurrent_processes_consume_exactly_once(env):
    runner = _runner(env.tmp, env.digest, env.auth)
    procs = []
    for i in range(4):
        d = env.tmp / f"q{i}"
        s, _ = _candidate_staging(d)
        procs.append(subprocess.Popen(
            [sys.executable, str(runner), "a4t1-promote", "--prod", str(_prod(d)),
             "--staging", str(s), "--as-of", A4T1_AS_OF.isoformat()],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=_sub_env(env)))
    outs = [p.communicate(timeout=120) for p in procs]
    codes = [p.returncode for p in procs]
    assert codes.count(0) == 1, (codes, [o[1][-500:] for o in outs])
    statuses = sorted(json.loads(o[0])["status"] for o in outs)
    assert statuses == ["PROMOTED", "REFUSED", "REFUSED", "REFUSED"]


def test_bash_wrapper_rejects_bad_arguments_before_python():
    assert WRAPPER.exists() and os.access(WRAPPER, os.X_OK)
    assert subprocess.run(["bash", "-n", str(WRAPPER)]).returncode == 0
    r = subprocess.run(["bash", str(WRAPPER), "badid", "a", "b"],
                       capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    assert r.returncode == 2 and "YYYYMMDDTHHMMSSZ" in r.stderr
    r = subprocess.run(["bash", str(WRAPPER), RUN_ID], capture_output=True, text=True)
    assert r.returncode == 2 and "usage" in r.stderr


def test_bash_wrapper_end_to_end_records_the_verdict(env):
    """The actual production caller: wrapper -> $PYTHON -m renquant_orchestrator
    a4t1-promote -> JSON tee'd into LOG_DIR -> exit code propagated."""
    runner = _runner(env.tmp, env.digest, env.auth)
    d = env.tmp / "w"
    staging, _ = _candidate_staging(d)
    prod = _prod(d)
    log_dir = env.tmp / "promote-logs"
    e = _sub_env(env)
    e.update({"PYTHON": str(runner), "LOG_DIR": str(log_dir)})
    r = subprocess.run(["bash", str(WRAPPER), RUN_ID, str(prod), str(staging)],
                       capture_output=True, text=True, env=e)
    assert r.returncode == 0, r.stderr
    recorded = json.loads((log_dir / f"{RUN_ID}.a4t1_promote.json").read_text())
    assert recorded["status"] == "PROMOTED"
    assert json.loads(staging.read_text())["metadata"]["fallback_a4t1_consumption_proof"] == recorded["proof"]
    # a second wrapper call on a fresh copy: exit 1, verdict overwritten with the refusal
    d2 = env.tmp / "w2"
    staging2, _ = _candidate_staging(d2)
    r2 = subprocess.run(["bash", str(WRAPPER), RUN_ID, str(_prod(d2)), str(staging2)],
                        capture_output=True, text=True, env=e)
    assert r2.returncode == 1
    assert json.loads((log_dir / f"{RUN_ID}.a4t1_promote.json").read_text())["refused_on"] == "already_consumed"
    # wrong RUN_ID for the file it was given: refused by the wrapper, python never runs
    r3 = subprocess.run(["bash", str(WRAPPER), "20260901T120000Z", str(prod), str(staging)],
                        capture_output=True, text=True, env=e)
    assert r3.returncode == 2 and "does not carry RUN_ID" in r3.stderr


def test_default_ledger_lives_under_the_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("RENQUANT_DATA_ROOT", str(tmp_path))
    assert G.ledger_dir() == tmp_path / "logs" / "weekly_wf_promote" / "a4t1_ledger"
    assert G.marker_path(EXCEPTION_ID).name == f"{EXCEPTION_ID}.consumed.json"
    assert not G.is_consumed(RUN_ID)
