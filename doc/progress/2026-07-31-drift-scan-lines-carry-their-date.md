# The drift scan's own findings could not be dated

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 · closes issue #663

STATUS:    5-line output change + 6 tests. No check logic touched, no verdict changed.
WHAT:      Every line `run_surface_drift_check` emits now begins with an ISO-8601
           timestamp — the clean line, every INFO, and **each** problem separately.
WHY/DIR:   Its `StandardOutPath` is append-only with no date in the filename. A scan
           whose entire job is noticing WHEN a surface changed was writing findings
           that belonged to no run.

EVIDENCE:  §4(b) block; model-specific fields filled and marked.

```
artifact:      ops/run_surface_drift_check.py (main() output paths only)
prod or exp:   prod — com.renquant.run-surface-drift, daily 07:00
existing data: logs/rq104/launchd_run_surface_drift.out — 1 788 B, last written
               2026-07-30 07:00. Lines beginning with a date: 0 of 18.
               [VERIFIED — this session]
best-known?:   NOT APPLICABLE as a model-variant comparison — no model, no score.
               As a fix: the leading stamp is what `ops/log_attribution.py`
               (orch#648) requires to frame a record; a filename-date scheme
               (used by logs/rq105/*_2026-07-30.log) would also work but changes
               the plist, which is a machine landing.
scope:         "this is run_surface_drift_check.main(), PROD, an output-format
                change; every check, verdict and exit code is unchanged — only
                the first characters of each printed line."
```

NEXT:      The alarm lines already in the existing .out stay undatable. Nothing
           here rewrites history; it stops adding to it.

## 1. What the undated stream cost, measured

The file had accumulated:

> `launchd: com.renquant.rq105-batch-scores-export ProgramArguments CHANGED (disk=[…run_batch_scores_export.sh] != manifest=[…export_batch_scores.py]) — silent containment / job swap?`

A **CONTAINMENT PROTOCOL** alarm. Checked against the live surface
`[VERIFIED — this session]`:

```
installed plist ProgramArguments = ['/bin/zsh', '…/ops/renquant105/run_batch_scores_export.sh']
reviewed manifest program_args   = ['/bin/zsh', '…/ops/renquant105/run_batch_scores_export.sh']
```

**Identical — the alarm is historical.** The wrapper is legitimate and documents
itself (the plist previously ran the python directly with no PYTHONPATH / .env, so
any import outside the venv failed silently) and the manifest was updated to match.
The containment was lifted correctly; only the log still shouts about it.

**Nothing in the file distinguished that resolved alarm from one raised that
morning.** I was one step from reporting it as live, on the same job whose ack I had
re-dispositioned an hour earlier (#661).

## 2. The change

`stamp = _now_iso()` once per run, then:

- the clean line → `<stamp> run-surface drift scan OK`
- every INFO → `<stamp> INFO: …`
- **every problem on its own dated line** — the pre-fix code was
  `print("\n".join(problems))`, which stamps at most the first, and the containment
  alarm was **not** first.

`alert()` keeps the **unstamped** body: the ntfy transport carries its own time, and
duplicating it would push the real message past the visible length.

## 3. Mutation check

| mutation | tests that fail |
|---|---:|
| revert problems to `print("\n".join(problems))` | **2** |
| drop the stamp from the clean line only | **2** |

The one that catches both is `test_no_line_on_any_path_is_undated`, which walks all
three exit paths — so a future branch that prints without a stamp fails even if the
per-path tests still pass.

## 4. Suite

`tests/test_run_surface_drift_check.py` → **18 passed, 1 failed**. The failure is
`TestManifestGeneration::test_committed_manifest_matches_live_surface`,
**pre-existing and unrelated** — it compares the committed manifest to this machine's
live launchd surface and fails identically on `origin/main` `[VERIFIED — this session]`.
