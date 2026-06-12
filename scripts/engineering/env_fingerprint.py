#!/usr/bin/env python3
"""Environment fingerprint (#108 III.5 env reproducibility).

The DRPH run fingerprint was incomplete without it: same code + same data
+ DIFFERENT numpy can score differently. Hashes python version + the full
frozen dependency set of the production venv into env_sha; writes a dated
manifest to ~/renquant-data/env_manifests/ and DIFFS against the previous
one — silent venv mutation (the shared-.venv hazard) becomes a logged event.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

VENV_PY = "/Users/renhao/git/github/RenQuant/.venv/bin/python"
OUT = Path.home() / "renquant-data/env_manifests"


def freeze() -> list[str]:
    r = subprocess.run([VENV_PY, "-m", "pip", "freeze", "--all"],
                       capture_output=True, text=True)
    return sorted(r.stdout.strip().splitlines())


def fingerprint() -> dict:
    pkgs = freeze()
    pyver = subprocess.run([VENV_PY, "-V"], capture_output=True, text=True).stdout.strip()
    blob = pyver + "\n" + "\n".join(pkgs)
    return {"env_sha": hashlib.sha256(blob.encode()).hexdigest()[:16],
            "python": pyver, "n_packages": len(pkgs), "packages": pkgs,
            "as_of": dt.datetime.now().isoformat(timespec="seconds")}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fp = fingerprint()
    prev_files = sorted(OUT.glob("env_*.json"))
    cur = OUT / f"env_{dt.date.today()}.json"
    cur.write_text(json.dumps(fp, indent=1))
    print(f"env_sha={fp['env_sha']}  {fp['python']}  {fp['n_packages']} packages → {cur.name}")
    if prev_files and prev_files[-1] != cur:
        prev = json.loads(prev_files[-1].read_text())
        if prev["env_sha"] != fp["env_sha"]:
            a, b = set(prev["packages"]), set(fp["packages"])
            print(f"ENV MUTATED since {prev['as_of'][:10]}:")
            for x in sorted(b - a)[:10]:
                print(f"  + {x}")
            for x in sorted(a - b)[:10]:
                print(f"  - {x}")
        else:
            print(f"unchanged since {prev['as_of'][:10]} ✓")
    print("wiring: env_sha joins the DRPH run_fingerprint (drph_core.py already "
          "carries the field); a mutation between two runs of the same case "
          "explains a diff before anyone blames the model.")
