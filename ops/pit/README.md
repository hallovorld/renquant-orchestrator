# PIT estimate-snapshot scheduling — N2 landing package (#231 N2; base-data #27; design #205)

**TIME-IRREVERSIBLE**: the revision signal needs a forward-accrued as-of history; every missed
day is permanently unrecoverable (the collector's PIT invariant forbids backfill). This package
schedules the merged base-data #27 collector daily with a lapse alert.

Writes ONLY `data/estimate_snapshots/<date>/` (a dedicated non-canonical path). Observe-only:
no orders, positions, pins, gates, or canonical data paths.

| File | Role | Schedule (PT, weekdays) |
|---|---|---|
| `run_estimate_snapshotter.sh` | daily snapshot via `renquant_base_data.fmp_estimate_revisions` | 14:30 |
| `pit_liveness_check.py` | today's dated dir has parquet(s)+manifest, else ntfy | 15:00 |
| `com.renquant.pit-{estimate-snapshot,liveness}.plist` | launchd jobs | as above |

## Install (operator / lander)

```bash
# 1. Pinned base-data RUN checkout:
git clone --branch main https://github.com/hallovorld/renquant-base-data.git \
  /Users/renhao/git/github/renquant-base-data-run

# 2. Install + load (assumes the orchestrator run checkout from ops/renquant105/README):
chmod +x /Users/renhao/git/github/renquant-orchestrator-run/ops/pit/*.sh
for p in estimate-snapshot liveness; do
  cp /Users/renhao/git/github/renquant-orchestrator-run/ops/pit/com.renquant.pit-$p.plist \
     ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.renquant.pit-$p.plist
done

# 3. Smoke (safe any time; --dry-run fetches nothing):
PYTHONPATH=/Users/renhao/git/github/renquant-base-data-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python -m renquant_base_data.fmp_estimate_revisions \
  --env /Users/renhao/git/github/RenQuant/.env --dry-run
```

## Acceptance (N2 AC, #231 §1)

3 consecutive daily appends with write-time `available_at`/`fetched_at` stamps + a missed-day
alert test (rename a day dir, run the liveness check, restore).

## Notes

- FMP: the existing key already returns data on the `stable` analyst-estimates endpoint
  (probed 2026-07-02); the collector's `--min-coverage` gate will surface any plan-lock gaps —
  if coverage fails, the authorized Starter upgrade (N3) is the fix, not a code change.
- Scheduling lives here (orchestrator owns base-data primitive scheduling per the #27
  docstring + #210 ownership split); the collector itself stays in base-data.
