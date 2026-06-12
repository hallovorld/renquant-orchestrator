#!/usr/bin/env python3
"""Secrets exposure scan (#108 §16.4, lightweight pre-gitleaks).

Three checks across all 10 repos: (1) is any .env-style file TRACKED by
git; (2) do tracked files contain key-shaped strings (Alpaca key IDs are
20-char A-Z0-9 starting AK/PK; secrets are 40-char base62); (3) has a key
pattern ever been committed to HISTORY (git log -S on the live key prefix).
Read-only; findings are the deliverable.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

G = Path("/Users/renhao/git/github")
REPOS = ["RenQuant", "renquant-pipeline", "renquant-strategy-104",
         "renquant-orchestrator", "renquant-common", "renquant-model",
         "renquant-backtesting", "renquant-base-data", "renquant-execution",
         "renquant-artifacts"]
KEY_RE = re.compile(r"\b[AP]K[A-Z0-9]{16,20}\b")


def sh(cmd, cwd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd).stdout


findings = []
for r in REPOS:
    d = G / r
    if not d.exists():
        continue
    tracked_env = sh("git ls-files | grep -iE '(^|/)\\.env' || true", d).strip()
    if tracked_env:
        findings.append(f"[CRITICAL] {r}: .env-style file TRACKED: {tracked_env}")
    hits = sh("git grep -lE '\\b[AP]K[A-Z0-9]{16,20}\\b' -- "
              "':!*.ipynb' ':!*.parquet' 2>/dev/null | head -5 || true", d).strip()
    if hits:
        for f in hits.splitlines():
            ctx = sh(f"git grep -hE '\\b[AP]K[A-Z0-9]{{16,20}}\\b' -- '{f}' | head -1", d)[:60]
            findings.append(f"[REVIEW] {r}:{f}: key-shaped string ({ctx!r}...)")
    # history probe on the real live key id prefix if .env exists locally
    env = d / ".env"
    if env.exists():
        m = KEY_RE.search(env.read_text())
        if m:
            key = m.group(0)
            hist = sh(f"git log --oneline -S'{key}' | head -3", d).strip()
            if hist:
                findings.append(f"[CRITICAL] {r}: LIVE key {key[:6]}… appears in history: {hist.splitlines()[0]} → ROTATE NOW")
            else:
                findings.append(f"[OK] {r}: live key present in untracked .env only; never committed")

print(f"scanned {len(REPOS)} repos")
for f in findings or ["no findings"]:
    print(" ", f)
crit = [f for f in findings if f.startswith("[CRITICAL]")]
print(f"\nverdict: {len(crit)} CRITICAL, {len(findings)-len(crit)} other")
