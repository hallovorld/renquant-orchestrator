# S12 shadow freshness investigation results

**Date**: 2026-07-04
**Prereq**: design/2026-07-04-s12-shadow-freshness-diagnosis.md (PR #323, merged)

## Findings

Both candidate root causes from the diagnosis memo are **CONFIRMED**:

### Candidate A: builder-not-run — CONFIRMED

The shadow PatchTST retrain launchd plist (`com.renquant.weekly-retrain-patchtst`)
exists in the repo at `scripts/launchd/` but was **never installed**:
- `~/Library/LaunchAgents/com.renquant.weekly-retrain-patchtst.plist` does not exist
- `launchctl list | grep patchtst` returns nothing
- Retrain logs show only 4 manual runs: 2026-06-07, 06-08, 06-16, 07-03

**Fix**: install the plist (shadow-only, moves no capital):
```bash
cp scripts/launchd/com.renquant.weekly-retrain-patchtst.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.renquant.weekly-retrain-patchtst.plist
launchctl list | grep weekly-retrain-patchtst  # verify
```

### Candidate B: rawlabel data staleness — CONFIRMED (and blocking even with cadence)

The 07-03 manual retrain ran successfully but promote **correctly refused**:
- rawlabel cutoff = 2026-02-11 (142 days old, SLA = 28d = OFF-SLA)
- transformer_panel cutoff = 2026-04-02 (92d raw, but fwd-label-clipped achievable
  frontier = 2026-06-25, only 8d beyond frontier = within SLA)
- quarterly fundamentals: UNVERIFIABLE (no per-entity fiscal provenance)

The rawlabel panel (`alpha158_291_fundamental_dataset_rawlabel.parquet`)
is frozen at 2026-02-11 and has not been rebuilt — an independent blocker
to shadow freshness regardless of Candidate A. Even with a working retrain
cadence, promote will continue to refuse until rawlabel data is refreshed.

(Note: the rawlabel panel is the same dataset family affected by the
fund-freshness serving-axis clip bug (#26/#151), but the specific causal
mechanism here — a stale upstream artifact that was never refreshed — is
distinct from #26's training/serving-axis coupling defect. Both result in
staleness of the same panel, but via different paths.)

**Fix**: rebuild the rawlabel panel with fresh data. This is a data-pipeline task
in the umbrella repo (not orchestrator scope).

## Resolution status

| Cause | Status | Fix | Resolution |
|---|---|---|---|
| No retrain cadence (plist not installed) | **FIXED** | launchd plist installed | operator-authorized 2026-07-04 |
| rawlabel data frozen at 2026-02-11 | **CODE MERGED** | base-data #33 (recipe) + umbrella #442 (refresh) | merged; needs first run |

Both fixes are code-complete. The launchd plist is installed (Saturday 05:30 PT).
The rawlabel refresh mechanism is merged in base-data and umbrella. The next
`weekly_retrain_patchtst.sh` run (Saturday 05:30 or manual trigger) will rebuild
the rawlabel sidecar to bar-frontier (~1 day old) and the promote gate's rawlabel
source should go back ON-SLA.

Remaining operator action: verify the live tree's subrepo pins include the
rawlabel refresh code (base-data pin must be at or after #33). If not, a pin
bump is needed before the Saturday run.
