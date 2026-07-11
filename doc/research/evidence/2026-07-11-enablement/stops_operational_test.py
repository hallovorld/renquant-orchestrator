#!/usr/bin/env python3
"""Software-stop registry + liveness watchdog operational test (S-FRAC stage-3
evidence item "registry freshness operational test").

READ-ONLY on all production paths: imports the PINNED runtime pipeline module
(the exact code the live loop would run), builds a registry in a SCRATCH dir
that mirrors the current live book (MU/GRMN/AVGO, 1 share each, broker-truth
qty from the 2026-07-10 intraday log + runs DB), and exercises the full
lifecycle: arm -> evaluate/heartbeat -> ratchet-refuse -> trigger -> gc
(registry-vs-positions) -> staleness watchdog -> liveness CLI exit codes.
No orders are placed anywhere; the readonly wrapper is not even loaded.

Reproducibility (Codex review of orchestrator#471, 2026-07-11): this script
previously hardcoded a one-off /private/tmp scratch path and
/Users/renhao/git/github/RenQuant absolute umbrella paths, making it
non-rerunnable from a clean checkout. All repo/scratch roots are now
REQUIRED CLI arguments — no default runtime, matching the "no default
runtime" convention used elsewhere in this repo family (e.g.
RENQUANT_SHADOW_AB_PYTHON). A clean checkout with its own umbrella tree and
a scratch directory of its choosing can rerun this unmodified.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--umbrella-root", required=True,
    help="Path to the RenQuant umbrella checkout (no default runtime). "
         "Provides .subrepo_runtime/repos/<name>/src for the pinned "
         "pipeline/common imports, data/ohlcv/<TICKER>/1d.parquet for the "
         "live-book close prices, and scripts/check_software_stops_liveness.py.",
)
parser.add_argument(
    "--scratch-dir", required=True,
    help="Writable scratch directory for the test registry + result JSON "
         "(no default runtime; never a production path).",
)
args = parser.parse_args()

UMBRELLA = Path(args.umbrella_root)
SCRATCH = Path(args.scratch_dir)
_RUNTIME_REPOS = str(UMBRELLA / ".subrepo_runtime" / "repos")
PINNED_PIPELINE_SRC = str(UMBRELLA / ".subrepo_runtime" / "repos" / "renquant-pipeline" / "src")
LIVENESS_CLI = str(UMBRELLA / "scripts" / "check_software_stops_liveness.py")

sys.dont_write_bytecode = True
# Same sibling-repo set the liveness-CLI subprocess below needs on
# PYTHONPATH (renquant_pipeline.__init__ transitively imports all of these).
for _r in ("renquant-pipeline", "renquant-common", "renquant-artifacts",
           "renquant-execution", "renquant-base-data"):
    sys.path.insert(0, f"{_RUNTIME_REPOS}/{_r}/src")
from renquant_pipeline.software_stops import (  # noqa: E402
    SoftwareStopRegistry,
    compute_staleness,
)

results = []


def record(name, ok, detail):
    results.append({"test": name, "pass": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), name, "—", detail)


REG = SCRATCH / "stops_test" / "software_stops.alpaca.json"
REG.parent.mkdir(parents=True, exist_ok=True)
if REG.exists():
    REG.unlink()

# Current live book (broker-truth 2026-07-10): MU 1, GRMN 1, AVGO 1
# closes 2026-07-10 from umbrella ohlcv (read-only)
import pandas as pd  # noqa: E402

quotes = {}
for t in ["MU", "GRMN", "AVGO"]:
    df = pd.read_parquet(str(UMBRELLA / "data" / "ohlcv" / t / "1d.parquet"))
    quotes[t] = float(df["close"].iloc[-1])
book = {t: 1.0 for t in quotes}

# 1. from_config arming semantics
cfg_off = {"execution": {"software_stops": {"enabled": False}}}
r_off = SoftwareStopRegistry.from_config(cfg_off, repo_root=str(SCRATCH / "stops_test"))
record("from_config(enabled=false) returns None (layer inert)", r_off is None, f"got {r_off}")

cfg_on = {
    "execution": {
        "software_stops": {
            "enabled": True,
            "registry_path": str(REG),
            "max_staleness_minutes": 30.0,
        }
    }
}
reg = SoftwareStopRegistry.from_config(cfg_on, broker_name="alpaca", repo_root="/")
record("from_config(enabled=true) arms", reg is not None and reg.is_armed(), f"registry file target {REG}")

# 2. register a Z9-catastrophe-distance stop (20% below current) per position
for t, q in book.items():
    reg.register(t, qty=q, stop_price=round(quotes[t] * 0.8, 2), source="manual")
snap = json.loads(REG.read_text())
record(
    "register: 3 stops persisted matching current live book",
    sorted(snap["stops"].keys()) == sorted(book.keys())
    and all(snap["stops"][t]["qty"] == 1.0 for t in book),
    f"stops={ {t: (snap['stops'][t]['qty'], snap['stops'][t]['stop_price']) for t in sorted(snap['stops'])} }",
)

# 3. evaluate: no trigger at current prices; heartbeat stamped fresh
intents = reg.evaluate(quotes)
snap = json.loads(REG.read_text())
st = compute_staleness(snap, now=datetime.datetime.now().astimezone())
record(
    "evaluate: no false trigger at current prices; heartbeat fresh",
    intents == [] and st["stale"] is False and st["age_minutes"] is not None and st["age_minutes"] < 1,
    f"intents={intents} staleness={ {k: st[k] for k in ('stale', 'age_minutes', 'n_stops')} }",
)

# 4. ratchet: attempt to LOWER the MU stop -> refused
before = json.loads(REG.read_text())["stops"]["MU"]["stop_price"]
reg.register("MU", qty=1.0, stop_price=before * 0.5, source="manual")
after = json.loads(REG.read_text())["stops"]["MU"]["stop_price"]
record("ratchet-only: lowering refused", after == before, f"stop stayed {after}")

# 5. trigger: gap below the MU stop -> full-qty exit intent with gap_pct
crash = dict(quotes)
crash["MU"] = before * 0.9  # 10% below the stop
intents = reg.evaluate(crash)
mu_hit = [i for i in intents if i["symbol"] == "MU"]
record(
    "trigger: breach emits full-qty market-exit intent with measured gap",
    len(mu_hit) == 1 and mu_hit[0]["qty"] == 1.0 and mu_hit[0]["gap_pct"] > 0.09,
    f"intent={mu_hit}",
)

# 6. gc: ghost entry (position no longer held) is dropped -> registry
#    matches current positions
reg.register("SOFI", qty=2.0, stop_price=10.0, source="manual")
reg.gc(set(book.keys()))
snap = json.loads(REG.read_text())
record(
    "gc: registry reconciled to current positions (ghost SOFI dropped)",
    sorted(snap["stops"].keys()) == sorted(book.keys()),
    f"post-gc stops={sorted(snap['stops'].keys())}",
)

# 7. liveness CLI — fresh heartbeat, forced in-session -> OK(0)
env = dict(
    os.environ,
    PYTHONPATH=":".join(
        f"{_RUNTIME_REPOS}/{r}/src"
        for r in (
            "renquant-pipeline", "renquant-common", "renquant-artifacts",
            "renquant-execution", "renquant-base-data",
        )
    ),
    PYTHONDONTWRITEBYTECODE="1",
)


def cli(*args):
    p = subprocess.run(
        [sys.executable, LIVENESS_CLI, *args],
        capture_output=True, text=True, env=env, timeout=60,
    )
    return p.returncode, (p.stdout + p.stderr).strip()


code, msg = cli("--registry", str(REG), "--force-session")
record("liveness CLI: fresh heartbeat -> exit 0 OK", code == 0, msg[:160])

# 8. missed-pass simulation: backdate heartbeat 45m (> 30m budget) -> STALE(1)
snap = json.loads(REG.read_text())
snap["last_evaluated_at"] = (
    datetime.datetime.now().astimezone() - datetime.timedelta(minutes=45)
).isoformat()
REG.write_text(json.dumps(snap))
code, msg = cli("--registry", str(REG), "--force-session")
record(
    "liveness CLI: 45m-old heartbeat (missed 12m passes) -> exit 1 STALE",
    code == 1 and "STALE" in msg,
    msg[:200],
)

# 9. off-session suppression: same stale registry, Saturday -> OK(0) by design
code, msg = cli("--registry", str(REG), "--now", "2026-07-11T12:00:00-04:00")
record("liveness CLI: off-session (Saturday) stale -> exit 0 by design", code == 0, msg[:160])

# 10. corrupt registry -> CORRUPT(2)
REG.write_text('{"version": 1, "stops": {"MU": {"qty": -5}}}')
code, msg = cli("--registry", str(REG), "--force-session")
record("liveness CLI: corrupt registry -> exit 2 CORRUPT", code == 2, msg[:160])

# 11. CURRENT LIVE STATE: default prod registry path (read-only check)
code, msg = cli("--broker", "alpaca")
record(
    "liveness CLI vs PROD default path: no registry (layer never armed) -> exit 0",
    code == 0 and "no software-stop registry" in msg,
    msg[:220],
)

out = SCRATCH / "stops_operational_test_result.json"
out.write_text(json.dumps({
    "ran_at": datetime.datetime.now().astimezone().isoformat(),
    "pinned_pipeline_src": PINNED_PIPELINE_SRC,
    "live_book_mirrored": {t: {"qty": 1.0, "close_2026_07_10": quotes[t]} for t in quotes},
    "results": results,
    "all_pass": all(r["pass"] for r in results),
}, indent=1))
print("\nwrote", out, "| all_pass =", all(r["pass"] for r in results))
