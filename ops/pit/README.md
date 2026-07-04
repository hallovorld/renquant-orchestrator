# PIT estimate-snapshot scheduling — N2 landing package (#231 N2; base-data #27; design #205)

**TIME-IRREVERSIBLE**: the revision signal needs a forward-accrued as-of history; every missed
day is permanently unrecoverable (the collector's PIT invariant forbids backfill). This package
schedules the merged base-data #27 collector daily with a lapse alert.

Writes ONLY `data/estimate_snapshots/<date>/` (a dedicated non-canonical path). Observe-only:
no orders, positions, pins, gates, or canonical data paths.

| File | Role | Schedule (PT, weekdays) |
|---|---|---|
| `run_estimate_snapshotter.sh` | daily snapshot via `renquant_base_data.fmp_estimate_revisions`, guarded by `run_with_lock.py` (kernel-released `fcntl.flock`, non-blocking — survives SIGKILL/crash with no stale-lock state; macOS has no `flock(1)` CLI, so this is a small stdlib Python launcher instead) | 14:30 |
| `pit_liveness_check.py` | today's dated dir has ALL FOUR endpoint manifests published (`status=="ok"`, `as_of`==today, non-zero-byte parquet), NYSE-session-aware, else ntfy | 15:00 |
| `run_c1_feature_builder.sh` | C1 revision-drift feature build via `renquant_base_data.pit_revision_features` (M-SIG C1 §1.1 serving path, sprint D2): snapshot lake (READ-ONLY) → `data/pit_features/c1_revision_drift.parquet` + evidence manifest; incremental no-op when current; a failed build is RECOVERABLE (next run rebuilds deterministically), unlike a snapshot lapse | 15:30 |
| `com.renquant.pit-{estimate-snapshot,liveness,c1-features}.plist` | launchd jobs | as above |

## Install (operator / lander)

```bash
# 1. Pinned base-data RUN checkout:
git clone --branch main https://github.com/hallovorld/renquant-base-data.git \
  /Users/renhao/git/github/renquant-base-data-run

# 2. Create the log directory BEFORE loading any plist — launchd resolves
#    StandardOutPath/StandardErrorPath at job-spawn time and will NOT create
#    a missing parent directory itself; the job fails to start if this is skipped.
mkdir -p /Users/renhao/git/github/RenQuant/logs/pit_snapshots

# 3. Install + bootstrap (assumes the orchestrator run checkout from ops/renquant105/README).
#    Current-macOS launchctl verbs (load/unload are deprecated):
chmod +x /Users/renhao/git/github/renquant-orchestrator-run/ops/pit/*.sh
for p in estimate-snapshot liveness c1-features; do
  cp /Users/renhao/git/github/renquant-orchestrator-run/ops/pit/com.renquant.pit-$p.plist \
     ~/Library/LaunchAgents/
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.renquant.pit-$p.plist
done
# Force-run once now to smoke-test end to end (bypasses the schedule):
#   launchctl kickstart gui/$(id -u)/com.renquant.pit-estimate-snapshot
# Uninstall:
#   launchctl bootout gui/$(id -u)/com.renquant.pit-estimate-snapshot
#   launchctl bootout gui/$(id -u)/com.renquant.pit-liveness
#   launchctl bootout gui/$(id -u)/com.renquant.pit-c1-features

# 4. Smoke (safe any time; --dry-run fetches nothing):
PYTHONPATH=/Users/renhao/git/github/renquant-base-data-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python -m renquant_base_data.fmp_estimate_revisions \
  --env /Users/renhao/git/github/RenQuant/.env --dry-run

# 5. C1 readiness smoke (read-only; also prints the confirmatory-unlock date):
PYTHONPATH=/Users/renhao/git/github/renquant-base-data-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python -m renquant_base_data.pit_revision_features report \
  --snapshot-root /Users/renhao/git/github/RenQuant/data/estimate_snapshots
```

## Acceptance (N2 AC, #231 §1)

3 consecutive daily appends with write-time `available_at`/`fetched_at` stamps + a missed-day
alert test (rename a day dir, run the liveness check, restore) + a concurrency test (two
overlapping invocations, exactly one proceeds — see `tests/test_pit_snapshotter_scheduling.py`).

## Notes

- The lock launcher (`run_with_lock.py`) requires a plain `python3` on PATH (stdlib only,
  deliberately no project dependency) — override with `PIT_LOCK_PYTHON` if the host's `python3`
  is unsuitable. This is independent of `RQ_ROOT/.venv`, which still runs the actual collector.
- FMP: the existing key already returns data on the `stable` analyst-estimates endpoint
  (probed 2026-07-02); the collector's `--min-coverage` gate will surface any plan-lock gaps —
  if coverage fails, the authorized Starter upgrade (N3) is the fix, not a code change.
- Scheduling lives here (orchestrator owns base-data primitive scheduling per the #27
  docstring + #210 ownership split); the collector itself stays in base-data.
- C1 feature builder (`run_c1_feature_builder.sh`, 15:30 PT after snapshot+liveness): the
  M-SIG C1 (§1.1) serving path, pre-built flag-off so that when the snapshot lake matures
  (confirmatory unlock = first-snapshot anchor 2026-07-02 + 6 calendar months = 2027-01-02),
  testing + serving C1 is parameter tuning. Output `data/pit_features/` is a RESEARCH lake —
  nothing downstream consumes it yet. The builder reads the snapshot lake READ-ONLY and
  refuses (structurally, in `pit_revision_features`) any out-root overlapping the lake or a
  canonical path. C1 stays INFORMATIVE-ONLY per the spec — nothing here gates GO/KILL.
