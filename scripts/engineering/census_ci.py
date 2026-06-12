#!/usr/bin/env python3
"""Census CI — reproducible Part-I metrics for the engineering plan (#108).

Every number the plan cites, measured by command, emitting JSON with repo
SHAs. Run: python scripts/engineering/census_ci.py
"""
import json, re, subprocess, datetime
from pathlib import Path

G = Path("/Users/renhao/git/github")
def sh(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd).stdout.strip()
def loc(p): return int(sh(f"wc -l < '{p}'") or 0)
def sha(repo): return sh("git rev-parse --short HEAD", cwd=G/repo)

pipe = G/"renquant-pipeline/src/renquant_pipeline"
out = {
  "as_of": datetime.datetime.now().isoformat(timespec="seconds"),
  "shas": {r: sha(r) for r in ["RenQuant","renquant-pipeline","renquant-strategy-104","renquant-orchestrator"]},
  "god_files_loc": {
    "job_panel_scoring.py": loc(pipe/"kernel/panel_pipeline/job_panel_scoring.py"),
    "runner.py": loc(G/"RenQuant/backtesting/renquant_104/adapters/runner.py"),
    "run_wf_gate.py": loc(G/"RenQuant/scripts/run_wf_gate.py"),
  },
  "config": {},
  "buy_blocked_writers": int(sh(
    r"grep -rE 'ctx\.buy_blocked\s*=\s*True|setattr\(ctx, .buy_blocked., True\)' "
    f"'{pipe}' | wc -l")),
  "broad_except_sites": int(sh(f"grep -rE 'except Exception' '{pipe}' '{G}/RenQuant/backtesting/renquant_104/adapters' | wc -l")),
  "kernel_dict_get_sites": int(sh(f"grep -rE '\\.get\\(' '{pipe}/kernel' | wc -l")),
  "scripts": {
    "py": int(sh(f"ls '{G}/RenQuant/scripts/'*.py 2>/dev/null | wc -l")),
    "sh": int(sh(f"ls '{G}/RenQuant/scripts/'*.sh 2>/dev/null | wc -l")),
    "launchd_plists": int(sh(f"ls '{G}/RenQuant/scripts/launchd/'*.plist 2>/dev/null | wc -l")),
  },
  "string_scan_test_files": int(sh(f"grep -rln 'in SOURCE\\|read_text()' '{G}/RenQuant/tests' '{G}/renquant-pipeline/tests' 2>/dev/null | wc -l")),
}
cfg = json.load(open(G/"renquant-strategy-104/configs/strategy_config.json"))
def count(o):
    n=p=0
    if isinstance(o,dict):
        for k,v in o.items():
            n+=1; p+=bool(re.search(r"reason", k, re.I))
            a,b=count(v); n+=a; p+=b
    elif isinstance(o,list):
        for v in o: a,b=count(v); n+=a; p+=b
    return n,p
n,p = count(cfg)
out["config"] = {"lines": loc(G/"renquant-strategy-104/configs/strategy_config.json"),
                 "keys_recursive": n, "reason_keys": p}
print(json.dumps(out, indent=2))
snap = Path(__file__).parent/"census_snapshots"
snap.mkdir(exist_ok=True)
(snap/f"census_{datetime.date.today()}.json").write_text(json.dumps(out, indent=2))
