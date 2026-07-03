# rq104 ops — scorer-identity monitor

Post-run monitors for the renquant_104 daily chain that key on what a run
ACTUALLY served (its own bundle stamps), not on what sits on disk.

## scorer-identity diff alarm (#274 monitoring gap)

`renquant_orchestrator.scorer_identity_monitor` diffs the stamped scorer
identity of consecutive canonical run bundles (`pipeline_runs.run_bundle_json`,
`data/runs.alpaca.db` opened `mode=ro`):

- `prod_panel` — artifact sha256 + `trained_date` + booster CONTENT hash
- `calibrator` — `global_calibration` artifact sha256
- `shadow_models[i]` — each stamped shadow-lane artifact sha256

An identity change with NO recorded promote/rollback event (weekly/monthly
staging + rollback markers under `artifacts/prod`, dated
`logs/weekly_wf_promote/<date>.log`, shadow promotion receipts under
`logs/promote_shadow_patchtst/`) is a CRITICAL silent model swap — the
2026-06-26 event class (`doc/research/2026-07-03-raw-jump-0626-diagnosis.md`).
A separate WARN fires when the served `trained_date` is over the 28-day
freshness directive (operator 2026-06-30 / RFC #210).

The alarm is edge-triggered (fires only on CHANGE), so it cannot saturate the
way the PSI drift audit did (247/247 rows CRITICAL since birth).

Exit codes: `0` ok · `1` CRITICAL (unexplained change / fail-closed) · `2`
WARN only.

### Manual runs

```bash
PY=/Users/renhao/git/github/RenQuant/.venv/bin/python
export PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src

# scheduled check (last 5 days of canonical runs)
$PY -m renquant_orchestrator.scorer_identity_monitor \
  --repo-root /Users/renhao/git/github/RenQuant

# identity timeline replay (the 06-26 event shows as *** UNEXPLAINED ***)
$PY -m renquant_orchestrator.scorer_identity_monitor \
  --repo-root /Users/renhao/git/github/RenQuant --backfill 460
```

Everything is read-only; `--notify` (used by the wrapper) posts ntfy alerts on
CRITICAL/WARN.

### Install (operator action — NOT performed by merge)

The daily-full runs at ~14:06 PT; the check is scheduled 14:30 PT Mon–Fri.

```bash
mkdir -p /Users/renhao/git/github/RenQuant/logs/rq104
cp ops/renquant104/com.renquant.rq104-scorer-identity.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.renquant.rq104-scorer-identity.plist
```

The plist points at the deployed run checkout
(`/Users/renhao/git/github/renquant-orchestrator-run`), same convention as the
`ops/renquant105` jobs — merged is not deployed until that checkout syncs.
