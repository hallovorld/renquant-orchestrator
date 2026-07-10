# State backup: compress oversized SQLite DBs instead of refusing to commit   (PR #452)

STATUS:    delivered
WHAT:      `state_backup.py` gzips any SQLite source over a configurable
           size threshold (default 95MB) instead of refusing to commit;
           non-SQLite oversized files keep the existing refuse-with-error
           behavior unchanged.
WHY/DIR:   Ops fix — the hourly multirepo state backup has been failing
           rc=1 every run since `data/runs.alpaca.db` grew past GitHub's
           100MB per-file push limit. Companion fix in the umbrella repo
           (`RenQuant#457`) addresses `backup_to_github.sh` swallowing this
           rc and reporting false success to launchd.
EVIDENCE:  n/a (ops/infra fix, not a model/data claim)
NEXT:      Merged ≠ deployed — the hourly job unblocks only after this
           machine syncs to the pin (separate operator-authorized landing
           action) and `RenQuant#457` lands.

## Problem [VERIFIED]

The hourly multirepo backup has been failing with rc=1: `data/runs.alpaca.db`
grew to 112MB, over GitHub's 100MB per-file push limit. `state_backup`
copied it into the backup repo, then `CheckFileSizeLimitsTask` raised
`files exceed GitHub 100MB push limit` before commit — every run, forever.
(Companion umbrella bug: `scripts/backup_to_github.sh` swallowed the rc and
exited 0, hiding the failure from launchd; fixed in a separate umbrella PR.)

## Fix

Oversized-file policy in `src/renquant_orchestrator/state_backup.py`:

- Any **SQLite** source larger than `compress_threshold_bytes` (default 95MB;
  `--compress-threshold-mb` / `RQ_BACKUP_COMPRESS_THRESHOLD_MB`) is no longer
  raw-copied. It is snapshotted to a temp file via the SQLite online backup
  API, `VACUUM`ed best-effort, then gzipped into the backup repo as
  `<name>.gz` (e.g. `data/runs.alpaca.db.gz`).
- Any stale raw copy of the same name is removed from the backup repo tree so
  it cannot trip the size gate; conversely a DB that shrinks back under the
  threshold drops its stale `.gz` twin.
- The sha256 of the uncompressed snapshot (the exact bytes gunzip restores)
  plus uncompressed/compressed sizes are recorded in the emitted JSON under
  `compressed`.
- **Non-SQLite** oversized files keep the refuse-with-error behavior
  (`CheckFileSizeLimitsTask` unchanged).

## Restore path (documented in the module docstring)

```
gunzip -k data/runs.alpaca.db.gz     # yields data/runs.alpaca.db
shasum -a 256 data/runs.alpaca.db    # must match the recorded sha256
```

## Tests

`tests/test_state_backup.py`:

- oversized fixture DB → `.gz` produced, stale raw removed, sha256 of the
  gunzipped bytes matches the recorded entry, restored DB queryable, commit
  proceeds; under-threshold DB in the same run stays raw.
- under-threshold run → no compression, plain-copied files byte-for-byte
  identical, raw SQLite copy intact, stale `.gz` cleaned up.
- non-SQLite oversized file → still refuses (rc=1, `committed=false`).
- threshold configurable via CLI flag and env var.

Full suite: `make test` green (3277 passed, 3 skipped).

## Deploy note

Merged ≠ deployed: the hourly job runs from the pinned/live checkouts. The
backup unblocks only after this machine syncs the orchestrator pin — pin bump
+ live-tree sync is a separate operator-authorized landing action.
